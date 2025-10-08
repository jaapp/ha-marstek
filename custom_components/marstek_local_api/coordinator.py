"""Data update coordinator for Marstek Local API."""
from __future__ import annotations

import asyncio
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


class MarstekMultiDeviceCoordinator(DataUpdateCoordinator):
    """Class to manage fetching data from multiple Marstek devices."""

    def __init__(
        self,
        hass: HomeAssistant,
        devices: list[dict[str, Any]],
        scan_interval: int = DEFAULT_SCAN_INTERVAL,
    ) -> None:
        """Initialize the multi-device coordinator."""
        self.devices = devices
        self.device_coordinators: dict[str, MarstekDataUpdateCoordinator] = {}
        self.update_count = 1

        super().__init__(
            hass,
            _LOGGER,
            name="Marstek System",
            update_interval=timedelta(seconds=scan_interval),
        )

    async def async_setup(self) -> None:
        """Set up individual device coordinators."""
        for device_data in self.devices:
            mac = device_data["mac"]

            # Create API client for this device
            api = MarstekUDPClient(
                self.hass,
                host=device_data["host"],
                port=device_data["port"],
                remote_port=device_data["port"],
            )

            try:
                await api.connect()
            except Exception as err:
                _LOGGER.error("Failed to connect to device %s: %s", mac, err)
                continue

            # Create coordinator for this device
            coordinator = MarstekDataUpdateCoordinator(
                self.hass,
                api,
                device_name=device_data.get("device", "Marstek Device"),
                firmware_version=device_data.get("firmware", 0),
                device_model=device_data.get("device", ""),
                scan_interval=self.update_interval.total_seconds(),
            )

            self.device_coordinators[mac] = coordinator

    def get_device_macs(self) -> list[str]:
        """Get list of device MACs."""
        return list(self.device_coordinators.keys())

    def get_device_data(self, mac: str) -> dict[str, Any]:
        """Get data for a specific device."""
        if mac in self.device_coordinators:
            return self.device_coordinators[mac].data or {}
        return {}

    def _calculate_aggregates(self) -> dict[str, Any]:
        """Calculate aggregate values across all devices."""
        aggregates = {}

        # Collect data from all devices
        all_device_data = []
        for mac, coordinator in self.device_coordinators.items():
            if coordinator.data:
                all_device_data.append(coordinator.data)

        if not all_device_data:
            return aggregates

        # Power aggregates
        total_power = sum(
            d.get("es", {}).get("bat_power", 0) or 0
            for d in all_device_data
        )
        aggregates["total_battery_power"] = total_power
        aggregates["total_power_in"] = sum(
            max(0, d.get("es", {}).get("bat_power", 0) or 0)
            for d in all_device_data
        )
        aggregates["total_power_out"] = sum(
            max(0, -(d.get("es", {}).get("bat_power", 0) or 0))
            for d in all_device_data
        )

        # Capacity aggregates
        aggregates["total_rated_capacity"] = sum(
            d.get("battery", {}).get("rated_capacity", 0) or 0
            for d in all_device_data
        )
        aggregates["total_remaining_capacity"] = sum(
            d.get("battery", {}).get("bat_capacity", 0) or 0
            for d in all_device_data
        )

        # Calculate weighted average SOC
        total_capacity = aggregates["total_rated_capacity"]
        if total_capacity > 0:
            weighted_soc = sum(
                (d.get("battery", {}).get("soc", 0) or 0) *
                (d.get("battery", {}).get("rated_capacity", 0) or 0)
                for d in all_device_data
            )
            aggregates["average_soc"] = weighted_soc / total_capacity
        else:
            aggregates["average_soc"] = None

        # Available capacity
        if total_capacity > 0 and aggregates["average_soc"] is not None:
            aggregates["total_available_capacity"] = (
                (100 - aggregates["average_soc"]) * total_capacity / 100
            )
        else:
            aggregates["total_available_capacity"] = None

        # Combined state
        power_values = [
            d.get("es", {}).get("bat_power", 0) or 0
            for d in all_device_data
        ]
        charging = [p > 0 for p in power_values]
        discharging = [p < 0 for p in power_values]

        if all(charging):
            aggregates["combined_state"] = "charging"
        elif all(discharging):
            aggregates["combined_state"] = "discharging"
        elif any(charging) or any(discharging):
            aggregates["combined_state"] = "mixed"
        else:
            aggregates["combined_state"] = "idle"

        # Energy aggregates
        aggregates["total_pv_energy"] = sum(
            d.get("es", {}).get("total_pv_energy", 0) or 0
            for d in all_device_data
        )
        aggregates["total_grid_import"] = sum(
            d.get("es", {}).get("total_grid_input_energy", 0) or 0
            for d in all_device_data
        )
        aggregates["total_grid_export"] = sum(
            d.get("es", {}).get("total_grid_output_energy", 0) or 0
            for d in all_device_data
        )
        aggregates["total_load_energy"] = sum(
            d.get("es", {}).get("total_load_energy", 0) or 0
            for d in all_device_data
        )
        aggregates["total_solar_power"] = sum(
            d.get("es", {}).get("pv_power", 0) or 0
            for d in all_device_data
        )
        aggregates["total_grid_power"] = sum(
            d.get("es", {}).get("ongrid_power", 0) or 0
            for d in all_device_data
        )
        aggregates["total_offgrid_power"] = sum(
            d.get("es", {}).get("offgrid_power", 0) or 0
            for d in all_device_data
        )

        return aggregates

    async def _async_update_data(self) -> dict[str, Any]:
        """Update data from all devices."""
        # Update all device coordinators in parallel
        # We call _async_update_data() and manually set the data attribute
        # since we're managing the coordinators directly
        async def update_device(mac: str, coordinator: MarstekDataUpdateCoordinator):
            try:
                data = await coordinator._async_update_data()
                coordinator.data = data  # Manually set data since we're calling _async_update_data directly
                return data
            except Exception as err:
                _LOGGER.error("Error updating device %s: %s", mac, err)
                return coordinator.data  # Return old data on error

        update_tasks = [
            update_device(mac, coordinator)
            for mac, coordinator in self.device_coordinators.items()
        ]

        await asyncio.gather(*update_tasks, return_exceptions=True)

        # Build combined data structure
        data = {
            "devices": {
                mac: coordinator.data
                for mac, coordinator in self.device_coordinators.items()
            },
            "aggregates": self._calculate_aggregates(),
        }

        return data


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
                "bat_capacity": 1.0,
                "bat_power": 1.0,
                "total_grid_input_energy": 0.01,
                "total_grid_output_energy": 0.01,
                "total_load_energy": 0.01,
            }
        else:
            scaling = {
                "bat_temp": 10.0,
                "bat_capacity": 100.0,
                "bat_power": 10.0,
                "total_grid_input_energy": 0.1,
                "total_grid_output_energy": 0.1,
                "total_load_energy": 0.1,
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
            # Check if this is truly the first update (never been run before)
            is_first_update = self.data is None
            _LOGGER.debug("Update starting - is_first_update=%s, self.data=%s", is_first_update, "None" if self.data is None else f"dict with {len(self.data)} keys")

            # Start with previous data to preserve values on partial failures
            data = dict(self.data) if self.data else {}
            if is_first_update:
                _LOGGER.debug("First update - fetching device info")
                try:
                    await asyncio.sleep(1.0)  # Delay before first API call
                    device_info = await self.api.get_device_info()
                    if device_info:
                        data["device"] = device_info
                except Exception as err:
                    _LOGGER.warning("Failed to get device info on first update: %s", err)

            # High priority - every update (15s)
            # ES.GetStatus and EM.GetStatus for real-time power/energy data
            try:
                await asyncio.sleep(1.0)  # Delay between API calls
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
                await asyncio.sleep(1.0)  # Delay between API calls
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
                    await asyncio.sleep(1.0)  # Delay between API calls
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
                        await asyncio.sleep(1.0)  # Delay between API calls
                        pv_status = await self.api.get_pv_status()
                        if pv_status:
                            data["pv"] = pv_status
                    except Exception as err:
                        _LOGGER.debug("Failed to get PV status: %s", err)

                try:
                    await asyncio.sleep(1.0)  # Delay between API calls
                    mode_status = await self.api.get_es_mode()
                    if mode_status:
                        data["mode"] = mode_status
                except Exception as err:
                    _LOGGER.debug("Failed to get mode status: %s", err)

            # Low priority - every 20th update (300s)
            # Device, WiFi, BLE - static/diagnostic data
            if self.update_count % UPDATE_INTERVAL_SLOW == 0:
                try:
                    await asyncio.sleep(1.0)  # Delay between API calls
                    device_info = await self.api.get_device_info()
                    if device_info:
                        data["device"] = device_info
                except Exception as err:
                    _LOGGER.debug("Failed to get device info: %s", err)

                try:
                    await asyncio.sleep(1.0)  # Delay between API calls
                    wifi_status = await self.api.get_wifi_status()
                    if wifi_status:
                        data["wifi"] = wifi_status
                except Exception as err:
                    _LOGGER.debug("Failed to get wifi status: %s", err)

                try:
                    await asyncio.sleep(1.0)  # Delay between API calls
                    ble_status = await self.api.get_ble_status()
                    if ble_status:
                        data["ble"] = ble_status
                except Exception as err:
                    _LOGGER.debug("Failed to get BLE status: %s", err)

            # Increment update counter
            self.update_count += 1

            # On first update, we need at least some data to proceed
            # But we're lenient - even just device info is enough
            if is_first_update and not data:
                _LOGGER.warning("First update failed - no data received, will retry")
                raise UpdateFailed("No response from device - check network connectivity")

            # If we got any new data, update the last message timestamp
            # (We compare with the preserved old data to see if anything changed)
            if data != self.data:
                self.last_message_timestamp = time.time()
                _LOGGER.debug("Updated data - at least one API call succeeded (keys: %s)", list(data.keys()))
            else:
                _LOGGER.debug("No new data this update - all API calls may have timed out, keeping old values (keys: %s)", list(data.keys()))

            # Add diagnostic data (will be recalculated on sensor access)
            data["_diagnostic"] = {
                "last_message_seconds": self._get_seconds_since_last_message(),
            }

            return data

        except MarstekAPIError as err:
            # Only fail if this is the first update (no existing data to preserve)
            if is_first_update:
                raise UpdateFailed(f"Error communicating with API: {err}") from err
            # Otherwise log and return preserved data
            _LOGGER.warning("API error during update, keeping old values: %s", err)
            return self.data if self.data else {}
        except Exception as err:
            # Only fail if this is the first update (no existing data to preserve)
            if is_first_update:
                raise UpdateFailed(f"Unexpected error: {err}") from err
            # Otherwise log and return preserved data
            _LOGGER.error("Unexpected error during update, keeping old values: %s", err, exc_info=True)
            return self.data if self.data else {}
