"""Service helpers for the Marstek Local API integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MODE_PASSIVE,
    SERVICE_REQUEST_SYNC,
    SERVICE_SET_PASSIVE_MODE,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REQUEST_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)

SERVICE_SET_PASSIVE_MODE_SCHEMA = vol.Schema(
    {
        vol.Required("entity_id"): cv.entity_id,
        vol.Required("power"): vol.All(vol.Coerce(int), vol.Range(min=-10000, max=10000)),
        vol.Required("duration"): vol.All(vol.Coerce(int), vol.Range(min=1, max=86400)),
    }
)


def _find_coordinator_for_entity(hass: HomeAssistant, entity_id: str) -> MarstekDataUpdateCoordinator | None:
    """Find the coordinator that manages the given entity."""
    domain_data = hass.data.get(DOMAIN, {})

    for entry_id, entry_payload in domain_data.items():
        coordinator = entry_payload.get(DATA_COORDINATOR)

        if isinstance(coordinator, MarstekMultiDeviceCoordinator):
            # Check if entity belongs to any device in this multi-device coordinator
            # For now, return the first device coordinator that matches
            # The entity_id should contain device-specific information
            for device_coordinator in coordinator.device_coordinators.values():
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

    async def _async_set_passive_mode(call: ServiceCall) -> None:
        """Set passive mode with specified power and duration."""
        entity_id = call.data["entity_id"]
        power = call.data["power"]
        duration = call.data["duration"]

        # Find coordinator
        coordinator = _find_coordinator_for_entity(hass, entity_id)
        if not coordinator:
            raise HomeAssistantError(f"Could not find coordinator for entity: {entity_id}")

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
            success = await coordinator.api.set_es_mode(config)
            if success:
                _LOGGER.info(
                    "Successfully set passive mode: power=%dW, duration=%ds for %s",
                    power,
                    duration,
                    entity_id,
                )
                # Refresh coordinator
                await coordinator.async_request_refresh()
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
    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_SET_PASSIVE_MODE)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister integration level services."""
    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        hass.services.async_remove(DOMAIN, SERVICE_REQUEST_SYNC)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)

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
