"""Data update coordinator for Marstek Local API."""
from __future__ import annotations

from datetime import timedelta
import logging
import time
from typing import Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import MarstekAPIError, MarstekUDPClient
from .const import (
    DEFAULT_SCAN_INTERVAL,
    DEVICE_MODEL_VENUS_D,
    FIRMWARE_THRESHOLD,
    UPDATE_INTERVAL_FAST,
    UPDATE_INTERVAL_MEDIUM,
    UPDATE_INTERVAL_SLOW,
)

_LOGGER = logging.getLogger(__name__)


class MarstekDataUpdateCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Marstek data from the device."""

    def __init__(
        self,
        hass: HomeAssistant,
        api: MarstekUDPClient,
        device_name: str,
        firmware_version: int,
        device_model: str,
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the coordinator."""
        self.api = api
        self.firmware_version = firmware_version
        self.device_model = device_model
        self.update_count = 1  # Start at 1 to skip slow updates on first refresh
        self.last_message_timestamp: float | None = None

        super().__init__(
            hass,
            _LOGGER,
            name=f"Marstek {device_name}",
            update_interval=timedelta(seconds=scan_interval),
        )

    def _scale_value(self, value: float | None, field: str) -> float | None:
        """Scale values based on firmware version."""
        if value is None:
            return None

        # Firmware-specific scaling based on design doc
        if self.firmware_version >= FIRMWARE_THRESHOLD:
            scaling = {
                "bat_temp": 1.0,
                "bat_capacity": 1000.0,
                "bat_power": 1.0,
                "total_grid_input_energy": 10.0,
                "total_grid_output_energy": 10.0,
                "total_load_energy": 10.0,
            }
        else:
            scaling = {
                "bat_temp": 10.0,
                "bat_capacity": 100.0,
                "bat_power": 10.0,
                "total_grid_input_energy": 100.0,
                "total_grid_output_energy": 100.0,
                "total_load_energy": 100.0,
            }

        return value / scaling.get(field, 1.0)

    def _get_seconds_since_last_message(self) -> int | None:
        """Get seconds since last successful message (Design Doc §556-576)."""
        if self.last_message_timestamp is None:
            return None
        return int(time.time() - self.last_message_timestamp)

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch data from API with tiered polling strategy."""
        try:
            data = {}

            # On first update, always get device info for initial setup
            is_first_update = self.data is None or not self.data
            if is_first_update:
                _LOGGER.debug("First update - fetching device info")
                try:
                    device_info = await self.api.get_device_info()
                    if device_info:
                        data["device"] = device_info
                except Exception as err:
                    _LOGGER.warning("Failed to get device info on first update: %s", err)

            # High priority - every update (15s)
            # ES.GetStatus and EM.GetStatus for real-time power/energy data
            try:
                es_status = await self.api.get_es_status()
            except Exception as err:
                _LOGGER.debug("Failed to get ES status: %s", err)
                es_status = None

            if es_status:
                # Scale firmware-dependent values
                if "bat_power" in es_status:
                    es_status["bat_power"] = self._scale_value(
                        es_status["bat_power"], "bat_power"
                    )
                if "total_grid_input_energy" in es_status:
                    es_status["total_grid_input_energy"] = self._scale_value(
                        es_status["total_grid_input_energy"], "total_grid_input_energy"
                    )
                if "total_grid_output_energy" in es_status:
                    es_status["total_grid_output_energy"] = self._scale_value(
                        es_status["total_grid_output_energy"], "total_grid_output_energy"
                    )
                if "total_load_energy" in es_status:
                    es_status["total_load_energy"] = self._scale_value(
                        es_status["total_load_energy"], "total_load_energy"
                    )

                data["es"] = es_status

            try:
                em_status = await self.api.get_em_status()
            except Exception as err:
                _LOGGER.debug("Failed to get EM status: %s", err)
                em_status = None

            if em_status:
                data["em"] = em_status

            # Medium priority - every 4th update (60s)
            # Battery, PV, Mode - slower-changing data
            if self.update_count % UPDATE_INTERVAL_MEDIUM == 0:
                try:
                    battery_status = await self.api.get_battery_status()
                    if battery_status:
                        # Scale firmware-dependent values
                        if "bat_temp" in battery_status:
                            battery_status["bat_temp"] = self._scale_value(
                                battery_status["bat_temp"], "bat_temp"
                            )
                        if "bat_capacity" in battery_status:
                            battery_status["bat_capacity"] = self._scale_value(
                                battery_status["bat_capacity"], "bat_capacity"
                            )
                        data["battery"] = battery_status
                except Exception as err:
                    _LOGGER.debug("Failed to get battery status: %s", err)

                # Only query PV for Venus D
                if self.device_model == DEVICE_MODEL_VENUS_D:
                    try:
                        pv_status = await self.api.get_pv_status()
                        if pv_status:
                            data["pv"] = pv_status
                    except Exception as err:
                        _LOGGER.debug("Failed to get PV status: %s", err)

                try:
                    mode_status = await self.api.get_es_mode()
                    if mode_status:
                        data["mode"] = mode_status
                except Exception as err:
                    _LOGGER.debug("Failed to get mode status: %s", err)

            # Low priority - every 20th update (300s)
            # Device, WiFi, BLE - static/diagnostic data
            if self.update_count % UPDATE_INTERVAL_SLOW == 0:
                try:
                    device_info = await self.api.get_device_info()
                    if device_info:
                        data["device"] = device_info
                except Exception as err:
                    _LOGGER.debug("Failed to get device info: %s", err)

                try:
                    wifi_status = await self.api.get_wifi_status()
                    if wifi_status:
                        data["wifi"] = wifi_status
                except Exception as err:
                    _LOGGER.debug("Failed to get wifi status: %s", err)

                try:
                    ble_status = await self.api.get_ble_status()
                    if ble_status:
                        data["ble"] = ble_status
                except Exception as err:
                    _LOGGER.debug("Failed to get BLE status: %s", err)

            # Increment update counter
            self.update_count += 1

            # If we got no data at all, raise an error
            # On first update, be more lenient - just log a warning
            if not data:
                if is_first_update:
                    raise UpdateFailed("No response from device - check network connectivity")
                raise UpdateFailed("No data received from device")

            # Update last message timestamp (Design Doc §556-576)
            self.last_message_timestamp = time.time()

            # Add diagnostic data (will be recalculated on sensor access)
            data["_diagnostic"] = {
                "last_message_seconds": self._get_seconds_since_last_message(),
            }

            return data

        except MarstekAPIError as err:
            raise UpdateFailed(f"Error communicating with API: {err}") from err
        except Exception as err:
            raise UpdateFailed(f"Unexpected error: {err}") from err
