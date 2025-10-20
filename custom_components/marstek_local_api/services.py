"""Service helpers for the Marstek Local API integration."""
from __future__ import annotations

import logging

import voluptuous as vol

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import config_validation as cv

from .const import DATA_COORDINATOR, DOMAIN, SERVICE_REQUEST_SYNC
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)

SERVICE_REQUEST_SYNC_SCHEMA = vol.Schema(
    {
        vol.Optional("entry_id"): cv.string,
    }
)


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

    _LOGGER.info("Registered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)


async def async_unload_services(hass: HomeAssistant) -> None:
    """Unregister integration level services."""
    if hass.services.has_service(DOMAIN, SERVICE_REQUEST_SYNC):
        hass.services.async_remove(DOMAIN, SERVICE_REQUEST_SYNC)
        _LOGGER.debug("Unregistered service %s.%s", DOMAIN, SERVICE_REQUEST_SYNC)


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
