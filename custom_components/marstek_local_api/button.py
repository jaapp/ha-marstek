"""Button platform for Marstek Local API."""
from __future__ import annotations

import asyncio
import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    RETRY_DELAY,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek buttons based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = []

    # Check if multi-device or single-device mode
    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        # Multi-device mode - create button entities for each device
        for mac in coordinator.get_device_macs():
            device_coordinator = coordinator.device_coordinators[mac]
            device_data = next(d for d in coordinator.devices if (d.get("ble_mac") or d.get("wifi_mac")) == mac)

            entities.extend([
                MarstekMultiDeviceAutoModeButton(
                    coordinator=coordinator,
                    device_coordinator=device_coordinator,
                    device_mac=mac,
                    device_data=device_data,
                ),
                MarstekMultiDeviceAIModeButton(
                    coordinator=coordinator,
                    device_coordinator=device_coordinator,
                    device_mac=mac,
                    device_data=device_data,
                ),
                MarstekMultiDeviceManualModeButton(
                    coordinator=coordinator,
                    device_coordinator=device_coordinator,
                    device_mac=mac,
                    device_data=device_data,
                ),
            ])
    else:
        # Single device mode
        entities.extend([
            MarstekAutoModeButton(coordinator, entry),
            MarstekAIModeButton(coordinator, entry),
            MarstekManualModeButton(coordinator, entry),
        ])

    async_add_entities(entities)


class MarstekModeButton(CoordinatorEntity, ButtonEntity):
    """Base class for Marstek mode buttons."""

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
        mode: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self._mode = mode
        self._attr_has_entity_name = True
        device_mac = entry.data.get("ble_mac") or entry.data.get("wifi_mac")
        self._attr_unique_id = f"{device_mac}_{mode.lower()}_mode_button"
        self._attr_name = name
        self._attr_icon = icon
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {entry.data['device']}",
            manufacturer="Marstek",
            model=entry.data["device"],
            sw_version=str(entry.data.get("firmware", "Unknown")),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.coordinator.data is not None and len(self.coordinator.data) > 0

    async def async_press(self) -> None:
        """Handle the button press."""
        config = self._build_mode_config()

        success = False
        last_error: str | None = None

        try:
            # Retry logic
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    if await self.coordinator.api.set_es_mode(config):
                        _LOGGER.info("Successfully set operating mode to %s", self._mode)
                        success = True
                        break

                    last_error = "device rejected mode change"
                    _LOGGER.warning(
                        "Device rejected mode change to %s (attempt %d/%d)",
                        self._mode,
                        attempt,
                        MAX_RETRIES,
                    )

                except Exception as err:
                    last_error = str(err)
                    _LOGGER.error(
                        "Error setting mode to %s (attempt %d/%d): %s",
                        self._mode,
                        attempt,
                        MAX_RETRIES,
                        err,
                    )

                # Wait before retry (except on last attempt)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
        finally:
            await self._refresh_mode_data()

        if success:
            return

        _LOGGER.error(
            "Failed to set operating mode to %s after %d attempts",
            self._mode,
            MAX_RETRIES,
        )
        message = f"Failed to set operating mode to {self._mode}"
        if last_error:
            message = f"{message}: {last_error}"
        raise HomeAssistantError(message)

    async def _refresh_mode_data(self) -> None:
        """Force a coordinator refresh so entities reflect the latest state."""
        try:
            await self.coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning("Failed to refresh data after mode change: %s", err)

    def _build_mode_config(self) -> dict:
        """Build configuration for the selected mode."""
        if self._mode == MODE_AUTO:
            return {
                "mode": MODE_AUTO,
                "auto_cfg": {"enable": 1},
            }
        elif self._mode == MODE_AI:
            return {
                "mode": MODE_AI,
                "ai_cfg": {"enable": 1},
            }
        elif self._mode == MODE_MANUAL:
            return {
                "mode": MODE_MANUAL,
            }

        return {}


class MarstekAutoModeButton(MarstekModeButton):
    """Button to switch to Auto mode."""

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the Auto mode button."""
        super().__init__(coordinator, entry, MODE_AUTO, "Auto mode", "mdi:auto-mode")


class MarstekAIModeButton(MarstekModeButton):
    """Button to switch to AI mode."""

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the AI mode button."""
        super().__init__(coordinator, entry, MODE_AI, "AI mode", "mdi:brain")


class MarstekManualModeButton(MarstekModeButton):
    """Button to switch to Manual mode."""

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the Manual mode button."""
        super().__init__(coordinator, entry, MODE_MANUAL, "Manual mode", "mdi:calendar-clock")


class MarstekMultiDeviceModeButton(CoordinatorEntity, ButtonEntity):
    """Base class for Marstek mode buttons in multi-device mode."""

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
        mode: str,
        name: str,
        icon: str,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator)
        self.device_coordinator = device_coordinator
        self.device_mac = device_mac
        self._mode = mode
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_mac}_{mode.lower()}_mode_button"
        self._attr_name = name
        self._attr_icon = icon

        # Extract last 4 chars of MAC for device name differentiation
        mac_suffix = device_mac.replace(":", "")[-4:]

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {device_data.get('device', 'Device')} {mac_suffix}",
            manufacturer="Marstek",
            model=device_data.get("device", "Unknown"),
            sw_version=str(device_data.get("firmware", "Unknown")),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        device_data = self.coordinator.get_device_data(self.device_mac)
        return device_data is not None and len(device_data) > 0

    async def async_press(self) -> None:
        """Handle the button press."""
        config = self._build_mode_config()

        success = False
        last_error: str | None = None

        try:
            # Retry logic
            for attempt in range(1, MAX_RETRIES + 1):
                try:
                    if await self.device_coordinator.api.set_es_mode(config):
                        _LOGGER.info(
                            "Successfully set operating mode to %s for device %s",
                            self._mode,
                            self.device_mac,
                        )
                        success = True
                        break

                    last_error = "device rejected mode change"
                    _LOGGER.warning(
                        "Device %s rejected mode change to %s (attempt %d/%d)",
                        self.device_mac,
                        self._mode,
                        attempt,
                        MAX_RETRIES,
                    )

                except Exception as err:
                    last_error = str(err)
                    _LOGGER.error(
                        "Error setting mode to %s for device %s (attempt %d/%d): %s",
                        self._mode,
                        self.device_mac,
                        attempt,
                        MAX_RETRIES,
                        err,
                    )

                # Wait before retry (except on last attempt)
                if attempt < MAX_RETRIES:
                    await asyncio.sleep(RETRY_DELAY)
        finally:
            await self._refresh_mode_data()

        if success:
            return

        _LOGGER.error(
            "Failed to set operating mode to %s for device %s after %d attempts",
            self._mode,
            self.device_mac,
            MAX_RETRIES,
        )
        message = (
            f"Failed to set operating mode to {self._mode} for device {self.device_mac}"
        )
        if last_error:
            message = f"{message}: {last_error}"
        raise HomeAssistantError(message)

    async def _refresh_mode_data(self) -> None:
        """Force a refresh on the device and aggregate coordinators."""
        try:
            await self.device_coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Failed to refresh device %s data after mode change: %s",
                self.device_mac,
                err,
            )

        try:
            await self.coordinator.async_refresh()
        except Exception as err:
            _LOGGER.warning(
                "Failed to refresh aggregate data after mode change for %s: %s",
                self.device_mac,
                err,
            )

    def _build_mode_config(self) -> dict:
        """Build configuration for the selected mode."""
        if self._mode == MODE_AUTO:
            return {
                "mode": MODE_AUTO,
                "auto_cfg": {"enable": 1},
            }
        elif self._mode == MODE_AI:
            return {
                "mode": MODE_AI,
                "ai_cfg": {"enable": 1},
            }
        elif self._mode == MODE_MANUAL:
            return {
                "mode": MODE_MANUAL,
            }

        return {}


class MarstekMultiDeviceAutoModeButton(MarstekMultiDeviceModeButton):
    """Button to switch to Auto mode in multi-device mode."""

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the Auto mode button."""
        super().__init__(
            coordinator, device_coordinator, device_mac, device_data, MODE_AUTO, "Auto mode", "mdi:auto-mode"
        )


class MarstekMultiDeviceAIModeButton(MarstekMultiDeviceModeButton):
    """Button to switch to AI mode in multi-device mode."""

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the AI mode button."""
        super().__init__(
            coordinator, device_coordinator, device_mac, device_data, MODE_AI, "AI mode", "mdi:brain"
        )


class MarstekMultiDeviceManualModeButton(MarstekMultiDeviceModeButton):
    """Button to switch to Manual mode in multi-device mode."""

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the Manual mode button."""
        super().__init__(
            coordinator, device_coordinator, device_mac, device_data, MODE_MANUAL, "Manual mode", "mdi:calendar-clock"
        )
