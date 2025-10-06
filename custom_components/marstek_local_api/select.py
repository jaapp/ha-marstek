"""Select platform for Marstek Local API."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    DATA_COORDINATOR,
    DOMAIN,
    MAX_RETRIES,
    MODE_AI,
    MODE_AUTO,
    MODE_MANUAL,
    MODE_PASSIVE,
    OPERATING_MODES,
    RETRY_DELAY,
)
from .coordinator import MarstekDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek select based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    async_add_entities([MarstekOperatingModeSelect(coordinator, entry)])


class MarstekOperatingModeSelect(CoordinatorEntity, SelectEntity):
    """Representation of Marstek operating mode select."""

    _attr_options = OPERATING_MODES

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the select."""
        super().__init__(coordinator)
        mac_suffix = entry.data["mac"].replace(":", "")[-4:].upper()
        self._attr_unique_id = f"{entry.data['mac']}_operating_mode_select"
        self._attr_name = f"Operating Mode {mac_suffix}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["mac"])},
            name=f"Marstek {entry.data['device']} {mac_suffix}",
            manufacturer="Marstek",
            model=entry.data["device"],
            sw_version=str(entry.data.get("firmware", "Unknown")),
        )

    @property
    def current_option(self) -> str | None:
        """Return the current operating mode."""
        mode_data = self.coordinator.data.get("mode", {})
        return mode_data.get("mode")

    async def async_select_option(self, option: str) -> None:
        """Change the operating mode."""
        if option not in OPERATING_MODES:
            _LOGGER.error("Invalid operating mode: %s", option)
            return

        # Build config based on mode
        config = self._build_mode_config(option)

        # Retry logic as per design document
        for attempt in range(MAX_RETRIES):
            try:
                success = await self.coordinator.api.set_es_mode(config)

                if success:
                    _LOGGER.info("Successfully set operating mode to %s", option)
                    # Request immediate refresh
                    await self.coordinator.async_request_refresh()
                    return

                _LOGGER.warning(
                    "Device rejected mode change (attempt %d/%d)",
                    attempt + 1,
                    MAX_RETRIES,
                )

            except Exception as err:
                _LOGGER.error(
                    "Error setting mode (attempt %d/%d): %s",
                    attempt + 1,
                    MAX_RETRIES,
                    err,
                )

            # Wait before retry (except on last attempt)
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY)

        _LOGGER.error("Failed to set operating mode after %d attempts", MAX_RETRIES)

    def _build_mode_config(self, mode: str) -> dict:
        """Build configuration for the selected mode."""
        if mode == MODE_AUTO:
            return {
                "mode": MODE_AUTO,
                "auto_cfg": {"enable": 1},
            }
        elif mode == MODE_AI:
            return {
                "mode": MODE_AI,
                "ai_cfg": {"enable": 1},
            }
        elif mode == MODE_MANUAL:
            # Default manual mode config (all week, no power limit)
            # Users can customize via service calls in the future
            return {
                "mode": MODE_MANUAL,
                "manual_cfg": {
                    "time_num": 0,
                    "start_time": "00:00",
                    "end_time": "23:59",
                    "week_set": 127,  # All days
                    "power": 0,
                    "enable": 1,
                },
            }
        elif mode == MODE_PASSIVE:
            # Default passive mode config (no power limit, 5 min countdown)
            # Users can customize via service calls in the future
            return {
                "mode": MODE_PASSIVE,
                "passive_cfg": {
                    "power": 0,
                    "cd_time": 300,
                },
            }

        return {}
