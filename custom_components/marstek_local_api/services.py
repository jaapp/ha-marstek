"""Service helpers for the Marstek Local API integration."""
from __future__ import annotations

import asyncio
import logging
from datetime import time

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import device_registry as dr

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MAX_SCHEDULE_SLOTS,
    MODE_MANUAL,
    MODE_PASSIVE,
    SERVICE_CLEAR_MANUAL_SCHEDULES,
    SERVICE_REQUEST_SYNC,
    SERVICE_SET_MANUAL_SCHEDULE,
    SERVICE_SET_MANUAL_SCHEDULES,
    SERVICE_SET_PASSIVE_MODE,
    WEEKDAY_MAP,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REQUEST_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
        vol.Optional("device_id"): cv.string,
    }
)

# Schedule service schemas
def _days_to_week_set(days: list[str]) -> int:
    """Convert list of day names to week_set bitmap."""
    return sum(WEEKDAY_MAP[day] for day in days)


SERVICE_SET_MANUAL_SCHEDULE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
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
        vol.Required("device_id"): cv.string,
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
        vol.Required("device_id"): cv.string,
    }
)

SERVICE_SET_PASSIVE_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("device_id"): cv.string,
        vol.Required("power"): vol.All(vol.Coerce(int), vol.Range(min=-10000, max=10000)),
        vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1, max=86400)),
    }
)


def _resolve_device_context(
    hass: HomeAssistant,
    device_id: str,
) -> tuple[MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator | None, str | None]:
    """Resolve the per-device coordinator (and aggregate coordinator if any) for a Home Assistant device."""
    domain_data = hass.data.get(DOMAIN)
    if not domain_data:
        raise HomeAssistantError("Integration has no active entries")

    device_registry = dr.async_get(hass)
    device_entry = device_registry.async_get(device_id)
    if not device_entry:
        raise HomeAssistantError(f"Unknown device_id: {device_id}")

    if not device_entry.config_entries:
        raise HomeAssistantError(
            f"Device {device_id} is not associated with any Marstek config entry"
        )

    for entry_id in device_entry.config_entries:
        entry_payload = domain_data.get(entry_id)
        if not entry_payload:
            continue

        coordinator = entry_payload.get(DATA_COORDINATOR)
        if coordinator is None:
            continue

        if isinstance(coordinator, MarstekDataUpdateCoordinator):
            return coordinator, None, None

        device_identifier: str | None = None
        for domain, identifier in device_entry.identifiers:
            if domain == DOMAIN:
                device_identifier = identifier
                break

        if not device_identifier:
            raise HomeAssistantError(
                f"Device {device_id} lacks Marstek identifiers"
            )

        if device_identifier.startswith("system_"):
            raise HomeAssistantError(
                f"Device {device_id} targets the aggregate system; please choose a specific battery device"
            )

        device_coordinator = coordinator.device_coordinators.get(device_identifier)
        if device_coordinator is None:
            # Fallback to case-insensitive comparison
            for mac, candidate in coordinator.device_coordinators.items():
                if mac.lower() == device_identifier.lower():
                    device_coordinator = candidate
                    device_identifier = mac
                    break

        if device_coordinator is None:
            raise HomeAssistantError(
                f"Could not find device coordinator for device {device_id}"
            )

        return device_coordinator, coordinator, device_identifier

    raise HomeAssistantError(
        f"Device {device_id} is not part of an active Marstek config entry"
    )


async def _refresh_after_write(
    device_coordinator: MarstekDataUpdateCoordinator,
    aggregate_coordinator: MarstekMultiDeviceCoordinator | None,
) -> None:
    """Refresh device/aggregate coordinators after a state-changing operation."""
    try:
        await device_coordinator.async_request_refresh()
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning("Failed to refresh device coordinator after write: %s", err)

    if aggregate_coordinator:
        try:
            await aggregate_coordinator.async_request_refresh()
        except Exception as err:  # noqa: BLE001
            _LOGGER.warning("Failed to refresh aggregate coordinator after write: %s", err)


def _apply_local_mode_state(
    device_coordinator: MarstekDataUpdateCoordinator,
    aggregate_coordinator: MarstekMultiDeviceCoordinator | None,
    device_identifier: str | None,
    mode: str,
    mode_payload: dict | None = None,
) -> None:
    """Update cached coordinator data so operating mode sensors reflect changes immediately."""
    device_data = dict(device_coordinator.data or {})
    mode_state: dict[str, object] = {"mode": mode}
    if mode_payload:
        mode_state.update(mode_payload)

    current_mode = dict(device_data.get("mode") or {})
    current_mode.update(mode_state)
    device_data["mode"] = current_mode
    device_coordinator.async_set_updated_data(device_data)

    if aggregate_coordinator and device_identifier:
        aggregate_data = dict(aggregate_coordinator.data or {})
        devices = dict(aggregate_data.get("devices") or {})
        devices[device_identifier] = device_data
        aggregate_data["devices"] = devices
        aggregate_coordinator.async_set_updated_data(aggregate_data)


async def async_setup_services(hass: HomeAssistant) -> None:
    """Register integration level services."""

    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        return

    async def _async_request_sync(call: ServiceCall) -> None:
        """Trigger an on-demand refresh across configured coordinators."""
        entry_id: str | None = call.data.get("entry_id")
        device_id: str | None = call.data.get("device_id")
        domain_data = hass.data.get(DOMAIN)

        if not domain_data:
            _LOGGER.debug("Request sync skipped - integration has no active entries")
            return

        if device_id:
            device_registry = dr.async_get(hass)
            device_entry = device_registry.async_get(device_id)
            if not device_entry:
                raise HomeAssistantError(f"Unknown device_id: {device_id}")

            if not device_entry.config_entries:
                raise HomeAssistantError(
                    f"Device {device_id} is not associated with any Marstek config entry"
                )

            refreshed = False
            for candidate_entry_id in device_entry.config_entries:
                entry_payload = domain_data.get(candidate_entry_id)
                if not entry_payload:
                    continue
                await _async_refresh_entry(candidate_entry_id, entry_payload)
                refreshed = True

            if not refreshed:
                raise HomeAssistantError(
                    f"Device {device_id} is not part of an active Marstek config entry"
                )
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
        device_id = call.data["device_id"]
        time_num = call.data["time_num"]
        start_time: time = call.data["start_time"]
        end_time: time = call.data["end_time"]
        days = call.data["days"]
        power = call.data["power"]
        enabled = call.data["enabled"]

        device_coordinator, aggregate_coordinator, device_identifier = _resolve_device_context(
            hass,
            device_id,
        )
        target_label = device_identifier or device_id

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
            success = await device_coordinator.api.set_es_mode(config)
            if success:
                _LOGGER.info(
                    "Successfully set manual schedule %d for %s",
                    time_num,
                    target_label,
                )
                _apply_local_mode_state(
                    device_coordinator,
                    aggregate_coordinator,
                    device_identifier,
                    MODE_MANUAL,
                    {"manual_cfg": manual_cfg},
                )
                hass.async_create_task(
                    _refresh_after_write(device_coordinator, aggregate_coordinator)
                )
            else:
                raise HomeAssistantError(
                    f"Device rejected schedule configuration for slot {time_num}"
                )
        except Exception as err:
            _LOGGER.error("Error setting manual schedule: %s", err)
            raise HomeAssistantError(f"Failed to set manual schedule: {err}") from err

    async def _async_set_manual_schedules(call: ServiceCall) -> None:
        """Set multiple manual mode schedules at once."""
        device_id = call.data["device_id"]
        schedules = call.data["schedules"]

        device_coordinator, aggregate_coordinator, device_identifier = _resolve_device_context(
            hass,
            device_id,
        )
        target_label = device_identifier or device_id

        _LOGGER.info("Setting %d manual schedules for %s", len(schedules), target_label)

        failed_slots = []
        any_success = False

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
                success = await device_coordinator.api.set_es_mode(config)
                if success:
                    _LOGGER.debug("Successfully set schedule slot %d", time_num)
                    any_success = True
                else:
                    _LOGGER.warning("Device rejected schedule slot %d", time_num)
                    failed_slots.append(time_num)
            except Exception as err:
                _LOGGER.error("Error setting schedule slot %d: %s", time_num, err)
                failed_slots.append(time_num)

            # Small delay between calls for reliability
            await asyncio.sleep(0.5)

        # Refresh coordinator after all schedules are set
        if any_success:
            _apply_local_mode_state(
                device_coordinator,
                aggregate_coordinator,
                device_identifier,
                MODE_MANUAL,
            )
        hass.async_create_task(
            _refresh_after_write(device_coordinator, aggregate_coordinator)
        )

        if failed_slots:
            raise HomeAssistantError(
                f"Failed to set schedules for slots: {failed_slots}"
            )

        _LOGGER.info("Successfully set all %d schedules", len(schedules))

    async def _async_clear_manual_schedules(call: ServiceCall) -> None:
        """Clear all manual schedules by disabling all slots."""
        device_id = call.data["device_id"]

        device_coordinator, aggregate_coordinator, device_identifier = _resolve_device_context(
            hass,
            device_id,
        )
        target_label = device_identifier or device_id

        _LOGGER.info("Clearing all manual schedules for %s", target_label)

        failed_slots = []
        any_success = False

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
                success = await device_coordinator.api.set_es_mode(config)
                if success:
                    any_success = True
                else:
                    _LOGGER.warning("Device rejected clearing schedule slot %d", i)
                    failed_slots.append(i)
            except Exception as err:
                _LOGGER.error("Error clearing schedule slot %d: %s", i, err)
                failed_slots.append(i)

            # Small delay between calls
            await asyncio.sleep(0.3)

        # Refresh coordinator
        if any_success:
            _apply_local_mode_state(
                device_coordinator,
                aggregate_coordinator,
                device_identifier,
                MODE_MANUAL,
            )
        hass.async_create_task(
            _refresh_after_write(device_coordinator, aggregate_coordinator)
        )

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

    async def _async_set_passive_mode(call: ServiceCall) -> None:
        """Set passive mode with specified power and duration."""
        device_id = call.data["device_id"]
        power = call.data["power"]
        duration = call.data["duration"]

        device_coordinator, aggregate_coordinator, device_identifier = _resolve_device_context(
            hass,
            device_id,
        )
        target_label = device_identifier or device_id

        # Build passive mode config
        config = {
            "mode": MODE_PASSIVE,
            "passive_cfg": {
                "power": power,
                "cd_time": duration,
            },
        }

        # Set mode via API
        try:
            success = await device_coordinator.api.set_es_mode(config)
            if success:
                _LOGGER.info(
                    "Successfully set passive mode: power=%dW, duration=%ds for %s",
                    power,
                    duration,
                    target_label,
                )
                _apply_local_mode_state(
                    device_coordinator,
                    aggregate_coordinator,
                    device_identifier,
                    MODE_PASSIVE,
                    {"passive_cfg": config["passive_cfg"]},
                )
                hass.async_create_task(
                    _refresh_after_write(device_coordinator, aggregate_coordinator)
                )
            else:
                raise HomeAssistantError(
                    f"Device rejected passive mode configuration (power={power}W, duration={duration}s)"
                )
        except Exception as err:
            _LOGGER.error("Error setting passive mode: %s", err)
            raise HomeAssistantError(f"Failed to set passive mode: {err}") from err

    hass.services.async_register(
        DOMAIN,
        SERVICE_SET_PASSIVE_MODE,
        _async_set_passive_mode,
        schema=SERVICE_SET_PASSIVE_MODE_SCHEMA,
    )

    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULE)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_MANUAL_SCHEDULES)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_CLEAR_MANUAL_SCHEDULES)
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_PASSIVE_MODE)


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

    if hass.services.has_service(DOMAIN, SERVICE_SET_PASSIVE_MODE):
        hass.services.async_remove(DOMAIN, SERVICE_SET_PASSIVE_MODE)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_SET_PASSIVE_MODE)


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
