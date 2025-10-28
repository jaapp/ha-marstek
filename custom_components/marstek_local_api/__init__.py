"""The Marstek Local API integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .api import MarstekUDPClient
from .const import (
    CONF_PORT,
    DATA_COORDINATOR,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator
from .services import async_setup_services, async_unload_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Marstek Local API from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Get scan interval from options (Design Doc §297-302)
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    # Check if this is a multi-device or single-device entry
    if "devices" in entry.data:
        # Multi-device mode
        _LOGGER.info("Setting up multi-device entry with %d devices", len(entry.data["devices"]))

        # Create multi-device coordinator
        coordinator = MarstekMultiDeviceCoordinator(
            hass,
            devices=entry.data["devices"],
            scan_interval=scan_interval,
            config_entry=entry,
        )

        # Set up device coordinators
        await coordinator.async_setup()

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

    else:
        # Single device mode (legacy/backwards compatibility)
        _LOGGER.info("Setting up single-device entry")

        # Create API client
        # Bind to same port as device (required by Marstek protocol)
        # Use reuse_port to allow multiple instances
        api = MarstekUDPClient(
            hass,
            host=entry.data[CONF_HOST],
            port=entry.data[CONF_PORT],  # Bind to device port (with reuse_port)
            remote_port=entry.data[CONF_PORT],  # Send to device port
        )

        # Connect to device
        try:
            await api.connect()
        except Exception as err:
            _LOGGER.error("Failed to connect to Marstek device: %s", err)
            return False

        # Create coordinator
        coordinator = MarstekDataUpdateCoordinator(
            hass,
            api,
            device_name=entry.data.get("device", "Marstek Device"),
            firmware_version=entry.data.get("firmware", 0),
            device_model=entry.data.get("device", ""),
            scan_interval=scan_interval,
            config_entry=entry,
        )

        # Fetch initial data
        await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    if len(hass.data[DOMAIN]) == 1:
        await async_setup_services(hass)

    # Register options update listener
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))

    # Forward entry setup to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_reload_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the config entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    # Unload platforms
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        # Disconnect API(s)
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

        if isinstance(coordinator, MarstekMultiDeviceCoordinator):
            # Disconnect all device APIs
            for device_coordinator in coordinator.device_coordinators.values():
                await device_coordinator.api.disconnect()
        else:
            # Single device coordinator
            await coordinator.api.disconnect()

        # Remove entry from domain data
        hass.data[DOMAIN].pop(entry.entry_id)

        if not hass.data[DOMAIN]:
            await async_unload_services(hass)

    return unload_ok
