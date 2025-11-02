"""Service helpers for the Marstek Local API integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import time

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MAX_SCHEDULE_SLOTS,
    MODE_MANUAL,
    SERVICE_CLEAR_MANUAL_SCHEDULES,
    SERVICE_REQUEST_SYNC,
    SERVICE_SET_MANUAL_SCHEDULE,
    SERVICE_SET_MANUAL_SCHEDULES,
    WEEKDAY_MAP,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REQUEST_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)

# Schedule service schemas
SERVICE_SET_MANUAL_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("time_num"): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_SCHEDULE_SLOTS - 1)),
        vol.Required("start_time"): cv.time,
        vol.Required("end_time"): cv.time,
        vol.Optional("days", default=list(WEEKDAY_MAP.keys())): vol.All(
            cv.ensure_list, [vol.In(WEEKDAY_MAP.keys())]
        ),
        vol.Optional("power", default=0): vol.Coerce(int),  # Negative=charge, positive=discharge, 0=no limit
        vol.Optional("enabled", default=True): cv.boolean,
    }
)

SERVICE_SET_MANUAL_SCHEDULES_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("schedules"): [
            vol.Schema(
                {
                    vol.Required("time_num"): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_SCHEDULE_SLOTS - 1)),
                    vol.Required("start_time"): cv.time,
                    vol.Required("end_time"): cv.time,
                    vol.Optional("days", default=list(WEEKDAY_MAP.keys())): vol.All(
                        cv.ensure_list, [vol.In(WEEKDAY_MAP.keys())]
                    ),
                    vol.Optional("power", default=0): vol.Coerce(int),  # Negative=charge, positive=discharge, 0=no limit
                    vol.Optional("enabled", default=True): cv.boolean,
                }
            )
        ],
    }
)

SERVICE_CLEAR_MANUAL_SCHEDULES_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
    }
)


def _days_to_week_set(days: list[str]) -> int:
    """Convert list of day names to week_set bitmap."""
    return sum(WEEKDAY_MAP[day] for day in days)


def _find_coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> MarstekDataUpdateCoordinator | None:
    """Find the coordinator that manages the given entity."""
    domain_data = hass.data.get(DOMAIN, {})

    for entry_id, entry_payload in domain_data.items():
        coordinator = entry_payload.get(DATA_COORDINATOR)

        if isinstance(coordinator, MarstekMultiDeviceCoordinator):
            # Check if entity belongs to any device in this multi-device coordinator
            for device_coordinator in coordinator.device_coordinators.values():
                # Entity IDs contain the device MAC, we can check if this coordinator matches
                # For now, just return the first device coordinator
                # TODO: Better entity -> coordinator mapping
                return device_coordinator
        elif isinstance(coordinator, MarstekDataUpdateCoordinator):
            return coordinator

    return None


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration level services."""

    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        return

    async def _async_request_sync(call: ServiceCall) -> None:
        """Trigger an on-demand refresh across configured coordinators."""
        entry_id: str | None = call.data.get("entry_id")
        domain_data = hass.data.get(DOMAIN)

        if not domain_data:
            _LOGGER.debug("Request sync skipped - integration has no active entries")
            return

        if entry_id:
            entry_payload = domain_data.get(entry_id)
            if not entry_payload:
                _LOGGER.warning(
                    "request_data_sync service received unknown entry_id: %s",
                    entry_id,
                )
                return
            await _async_refresh_entry(entry_id, entry_payload)
            return

        for current_entry_id, entry_payload in domain_data.items():
            await _async_refresh_entry(current_entry_id, entry_payload)

    hass.services.async_register(
        DOMAIN,
        SERVICE_REQUEST_SYNC,
        _async_request_sync,
        schema=SERVICE_REQUEST_SYNC_SCHEMA,
    )

    async def _async_set_manual_schedule(call: ServiceCall) -> None:
        """Set a single manual mode schedule."""
        entity_id = call.data["entity_id"]
        time_num = call.data["time_num"]
        start_time: time = call.data["start_time"]
        end_time: time = call.data["end_time"]
        days = call.data["days"]
        power = call.data["power"]
        enabled = call.data["enabled"]

        # Find coordinator
        coordinator = _find_coordinator_for_entity(hass, entity_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for entity: {entity_id}")

        # Build manual_cfg
        manual_cfg = {
            "time_num": time_num,
            "start_time": start_time.strftime("%H:%M"),
            "end_time": end_time.strftime("%H:%M"),
            "week_set": _days_to_week_set(days),
            "power": power,
            "enable": 1 if enabled else 0,
        }

        config = {
            "mode": MODE_MANUAL,
            "manual_cfg": manual_cfg,
        }

        # Set mode via API
        try:
            success = await coordinator.api.set_es_mode(config)
            if success:
                _LOGGER.info(
                    "Successfully set manual schedule %d for %s", time_num, entity_id
                )
                # Refresh coordinator
                await coordinator.async_request_refresh()
            else:
                raise HomeAssistantError(
                    f"Device rejected schedule configuration for slot {time_num}"
                )
        except Exception as err:
            _LOGGER.error("Error setting manual schedule: %s", err)
            raise HomeAssistantError(f"Failed to set manual schedule: {err}") from err

    async def _async_set_manual_schedules(call: ServiceCall) -> None:
        """Set multiple manual mode schedules at once."""
        entity_id = call.data["entity_id"]
        schedules = call.data["schedules"]

        coordinator = _find_coordinator_for_entity(hass, entity_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for entity: {entity_id}")

        _LOGGER.info("Setting %d manual schedules for %s", len(schedules), entity_id)

        failed_slots = []

        # Set each schedule sequentially
        for schedule in schedules:
            time_num = schedule["time_num"]
            start_time: time = schedule["start_time"]
            end_time: time = schedule["end_time"]
            days = schedule["days"]
            power = schedule["power"]
            enabled = schedule["enabled"]

            manual_cfg = {
                "time_num": time_num,
                "start_time": start_time.strftime("%H:%M"),
                "end_time": end_time.strftime("%H:%M"),
                "week_set": _days_to_week_set(days),
                "power": power,
                "enable": 1 if enabled else 0,
            }

            config = {
                "mode": MODE_MANUAL,
                "manual_cfg": manual_cfg,
            }

            try:
                success = await coordinator.api.set_es_mode(config)
                if success:
                    _LOGGER.debug("Successfully set schedule slot %d", time_num)
                else:
                    _LOGGER.warning("Device rejected schedule slot %d", time_num)
                    failed_slots.append(time_num)
            except Exception as err:
                _LOGGER.error("Error setting schedule slot %d: %s", time_num, err)
                failed_slots.append(time_num)

            # Small delay between calls for reliability
            await asyncio.sleep(0.5)

        # Refresh coordinator after all schedules are set
        await coordinator.async_request_refresh()

        if failed_slots:
            raise HomeAssistantError(
                f"Failed to set schedules for slots: {failed_slots}"
            )

        _LOGGER.info("Successfully set all %d schedules", len(schedules))

    async def _async_clear_manual_schedules(call: ServiceCall) -> None:
        """Clear all manual schedules by disabling all slots."""
        entity_id = call.data["entity_id"]

        coordinator = _find_coordinator_for_entity(hass, entity_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for entity: {entity_id}")

        _LOGGER.info("Clearing all manual schedules for %s", entity_id)

        failed_slots = []

        # Disable all 10 schedule slots
        for i in range(MAX_SCHEDULE_SLOTS):
            config = {
                "mode": MODE_MANUAL,
                "manual_cfg": {
                    "time_num": i,
                    "start_time": "00:00",
                    "end_time": "00:00",
                    "week_set": 0,  # No days
                    "power": 0,
                    "enable": 0,  # Disabled
                },
            }

            try:
                success = await coordinator.api.set_es_mode(config)
                if not success:
                    _LOGGER.warning("Device rejected clearing schedule slot %d", i)
                    failed_slots.append(i)
            except Exception as err:
                _LOGGER.error("Error clearing schedule slot %d: %s", i, err)
                failed_slots.append(i)

            # Small delay between calls
            await asyncio.sleep(0.3)

        # Refresh coordinator
        await coordinator.async_request_refresh()

        if failed_slots:
            raise HomeAssistantError(
                f"Failed to clear schedules for slots: {failed_slots}"
            )

        _LOGGER.info("Successfully cleared all manual schedules")

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MANUAL_SCHEDULE,
        _async_set_manual_schedule,
        schema=SERVICE_SET_MANUAL_SCHEDULE_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_MANUAL_SCHEDULES,
        _async_set_manual_schedules,
        schema=SERVICE_SET_MANUAL_SCHEDULES_SCHEMA,
    )

    hass.services.async_register(
        DOMAIN,
        SERVICE_CLEAR_MANUAL_SCHEDULES,
        _async_clear_manual_schedules,
        schema=SERVICE_CLEAR_MANUAL_SCHEDULES_SCHEMA,
    )

    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULE)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULES)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_CLEAR_MANUAL_SCHEDULES)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister integration level services."""
    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        hass.services.async_remove(DOMAIN, SERVICE_REQUEST_SYNC)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)

    if hass.services.has_service(DOMAIN, SERVICE_SET_MANUAL_SCHEDULE):
        hass.services.async_remove(DOMAIN, SERVICE_SET_MANUAL_SCHEDULE)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULE)

    if hass.services.has_service(DOMAIN, SERVICE_SET_MANUAL_SCHEDULES):
        hass.services.async_remove(DOMAIN, SERVICE_SET_MANUAL_SCHEDULES)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULES)

    if hass.services.has_service(DOMAIN, SERVICE_CLEAR_MANUAL_SCHEDULES):
        hass.services.async_remove(DOMAIN, SERVICE_CLEAR_MANUAL_SCHEDULES)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_CLEAR_MANUAL_SCHEDULES)


async def _async_refresh_entry(entry_id: str, payload: dict) -> None:
    """Refresh a single config entry."""
    coordinator = payload.get(DATA_COORDINATOR)
    if coordinator is None:
        _LOGGER.debug("No coordinator stored for entry %s", entry_id)
        return

    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        _LOGGER.debug("Requesting multi-device sync for entry %s", entry_id)
        await coordinator.async_request_refresh()
        for mac, device_coordinator in coordinator.device_coordinators.items():
            if isinstance(device_coordinator, MarstekDataUpdateCoordinator):
                await device_coordinator.async_request_refresh()
                _LOGGER.debug("Requested device-level sync for %s (%s)", mac, entry_id)
    elif isinstance(coordinator, MarstekDataUpdateCoordinator):
        _LOGGER.debug("Requesting single-device sync for entry %s", entry_id)
        await coordinator.async_request_refresh()
    else:
        _LOGGER.debug(
            "Coordinator type %s not recognised for entry %s",
            type(coordinator),
            entry_id,
        )
