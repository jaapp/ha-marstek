"""The Marstek Local API integration."""
from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .api import MarstekUDPClient
from .const import CONF_PORT, DATA_COORDINATOR, DEFAULT_SCAN_INTERVAL, DOMAIN
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SELECT]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Marstek Local API from a config entry."""
    hass.data.setdefault(DOMAIN, {})

    # Create API client
    # Use ephemeral port (0) for local binding, send to device on configured port
    api = MarstekUDPClient(
        hass,
        host=entry.data[CONF_HOST],
        port=0,  # Bind to any available port
        remote_port=entry.data[CONF_PORT],  # Send to device port
    )

    # Connect to device
    try:
        await api.connect()
    except Exception as err:
        _LOGGER.error("Failed to connect to Marstek device: %s", err)
        return False

    # Get scan interval from options (Design Doc §297-302)
    scan_interval = entry.options.get("scan_interval", DEFAULT_SCAN_INTERVAL)

    # Create coordinator
    coordinator = MarstekDataUpdateCoordinator(
        hass,
        api,
        device_name=entry.data.get("device", "Marstek Device"),
        firmware_version=entry.data.get("firmware", 0),
        device_model=entry.data.get("device", ""),
        scan_interval=scan_interval,
    )

    # Fetch initial data
    await coordinator.async_config_entry_first_refresh()

    # Store coordinator
    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

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
        # Disconnect API
        coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]
        await coordinator.api.disconnect()

        # Remove entry from domain data
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok
