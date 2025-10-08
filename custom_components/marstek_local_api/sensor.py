"""Sensor platform for Marstek Local API."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DATA_COORDINATOR, DEVICE_MODEL_VENUS_D, DOMAIN
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class MarstekSensorEntityDescription(SensorEntityDescription):
    """Describes Marstek sensor entity."""

    value_fn: Callable[[dict], any] | None = None
    available_fn: Callable[[dict], bool] | None = None


SENSOR_TYPES: tuple[MarstekSensorEntityDescription, ...] = (
    # Battery sensors
    MarstekSensorEntityDescription(
        key="battery_soc",
        name="State of charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("battery", {}).get("soc"),
    ),
    MarstekSensorEntityDescription(
        key="battery_temperature",
        name="Temperature",
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("battery", {}).get("bat_temp"),
    ),
    MarstekSensorEntityDescription(
        key="battery_capacity",
        name="Remaining capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("battery", {}).get("bat_capacity"),
    ),
    MarstekSensorEntityDescription(
        key="battery_rated_capacity",
        name="Rated capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        value_fn=lambda data: data.get("battery", {}).get("rated_capacity"),
    ),
    # Energy System sensors
    MarstekSensorEntityDescription(
        key="battery_power",
        name="Power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("es", {}).get("bat_power"),
    ),
    # Calculated battery sensors (Design Doc §174-202)
    MarstekSensorEntityDescription(
        key="battery_power_in",
        name="Power in",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: max(0, data.get("es", {}).get("bat_power", 0) or 0),
    ),
    MarstekSensorEntityDescription(
        key="battery_power_out",
        name="Power out",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: max(0, -(data.get("es", {}).get("bat_power", 0) or 0)),
    ),
    MarstekSensorEntityDescription(
        key="battery_state",
        name="State",
        value_fn=lambda data: (
            "charging" if (data.get("es", {}).get("bat_power", 0) or 0) > 0
            else "discharging" if (data.get("es", {}).get("bat_power", 0) or 0) < 0
            else "idle"
        ),
    ),
    MarstekSensorEntityDescription(
        key="battery_available_capacity",
        name="Available capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: (
            (100 - (data.get("battery", {}).get("soc", 0) or 0))
            * (data.get("battery", {}).get("rated_capacity", 0) or 0)
            / 100
            if data.get("battery", {}).get("soc") is not None
            and data.get("battery", {}).get("rated_capacity") is not None
            else None
        ),
    ),
    MarstekSensorEntityDescription(
        key="grid_power",
        name="Grid power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("es", {}).get("ongrid_power"),
    ),
    MarstekSensorEntityDescription(
        key="offgrid_power",
        name="Off-grid power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("es", {}).get("offgrid_power"),
    ),
    MarstekSensorEntityDescription(
        key="pv_power_es",
        name="Solar power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("es", {}).get("pv_power"),
    ),
    MarstekSensorEntityDescription(
        key="total_pv_energy",
        name="Total solar energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("es", {}).get("total_pv_energy"),
    ),
    MarstekSensorEntityDescription(
        key="total_grid_import",
        name="Total grid import",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("es", {}).get("total_grid_input_energy"),
    ),
    MarstekSensorEntityDescription(
        key="total_grid_export",
        name="Total grid export",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("es", {}).get("total_grid_output_energy"),
    ),
    MarstekSensorEntityDescription(
        key="total_load_energy",
        name="Total load energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("es", {}).get("total_load_energy"),
    ),
    # Energy Meter / CT sensors
    MarstekSensorEntityDescription(
        key="ct_phase_a_power",
        name="CT phase A power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("em", {}).get("a_power"),
    ),
    MarstekSensorEntityDescription(
        key="ct_phase_b_power",
        name="CT phase B power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("em", {}).get("b_power"),
    ),
    MarstekSensorEntityDescription(
        key="ct_phase_c_power",
        name="CT phase C power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("em", {}).get("c_power"),
    ),
    MarstekSensorEntityDescription(
        key="ct_total_power",
        name="CT total power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("em", {}).get("total_power"),
    ),
    # WiFi sensors
    MarstekSensorEntityDescription(
        key="wifi_rssi",
        name="WiFi signal strength",
        native_unit_of_measurement="dBm",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("wifi", {}).get("rssi"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_ssid",
        name="WiFi SSID",
        value_fn=lambda data: data.get("wifi", {}).get("ssid"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_ip",
        name="WiFi IP address",
        value_fn=lambda data: data.get("wifi", {}).get("sta_ip"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_gateway",
        name="WiFi gateway",
        value_fn=lambda data: data.get("wifi", {}).get("sta_gate"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_subnet",
        name="WiFi subnet mask",
        value_fn=lambda data: data.get("wifi", {}).get("sta_mask"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_dns",
        name="WiFi DNS server",
        value_fn=lambda data: data.get("wifi", {}).get("sta_dns"),
    ),
    # Device info sensors
    MarstekSensorEntityDescription(
        key="device_model",
        name="Model",
        value_fn=lambda data: data.get("device", {}).get("device"),
    ),
    MarstekSensorEntityDescription(
        key="firmware_version",
        name="Firmware version",
        value_fn=lambda data: data.get("device", {}).get("ver"),
    ),
    MarstekSensorEntityDescription(
        key="ble_mac",
        name="Bluetooth MAC",
        value_fn=lambda data: data.get("device", {}).get("ble_mac"),
    ),
    MarstekSensorEntityDescription(
        key="wifi_mac",
        name="WiFi MAC",
        value_fn=lambda data: data.get("device", {}).get("wifi_mac"),
    ),
    MarstekSensorEntityDescription(
        key="device_ip",
        name="IP address",
        value_fn=lambda data: data.get("device", {}).get("ip"),
    ),
    # Diagnostic sensors (Design Doc §556-576, §679-688)
    MarstekSensorEntityDescription(
        key="last_message_received",
        name="Last message received",
        native_unit_of_measurement=UnitOfTime.SECONDS,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("_diagnostic", {}).get("last_message_seconds"),
    ),
    # Operating mode
    MarstekSensorEntityDescription(
        key="operating_mode",
        name="Operating mode",
        value_fn=lambda data: data.get("mode", {}).get("mode"),
    ),
)

# PV sensors (Venus D only)
PV_SENSOR_TYPES: tuple[MarstekSensorEntityDescription, ...] = (
    MarstekSensorEntityDescription(
        key="pv_power",
        name="PV power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("pv", {}).get("pv_power"),
    ),
    MarstekSensorEntityDescription(
        key="pv_voltage",
        name="PV voltage",
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("pv", {}).get("pv_voltage"),
    ),
    MarstekSensorEntityDescription(
        key="pv_current",
        name="PV current",
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("pv", {}).get("pv_current"),
    ),
)

# Aggregate sensors (multi-device only)
AGGREGATE_SENSOR_TYPES: tuple[MarstekSensorEntityDescription, ...] = (
    MarstekSensorEntityDescription(
        key="system_total_power",
        name="Total battery power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_battery_power"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_power_in",
        name="Total power in",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_power_in"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_power_out",
        name="Total power out",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_power_out"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_rated_capacity",
        name="Total rated capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        value_fn=lambda data: data.get("aggregates", {}).get("total_rated_capacity"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_remaining_capacity",
        name="Total remaining capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_remaining_capacity"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_available_capacity",
        name="Total available capacity",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY_STORAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_available_capacity"),
    ),
    MarstekSensorEntityDescription(
        key="system_average_soc",
        name="Average state of charge",
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("average_soc"),
    ),
    MarstekSensorEntityDescription(
        key="system_combined_state",
        name="Combined state",
        value_fn=lambda data: data.get("aggregates", {}).get("combined_state"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_solar_power",
        name="Total solar power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_solar_power"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_pv_energy",
        name="Total solar energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("aggregates", {}).get("total_pv_energy"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_grid_power",
        name="Total grid power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_grid_power"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_grid_import",
        name="Total grid import",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("aggregates", {}).get("total_grid_import"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_grid_export",
        name="Total grid export",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("aggregates", {}).get("total_grid_export"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_load_energy",
        name="Total load energy",
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda data: data.get("aggregates", {}).get("total_load_energy"),
    ),
    MarstekSensorEntityDescription(
        key="system_total_offgrid_power",
        name="Total off-grid power",
        native_unit_of_measurement=UnitOfPower.WATT,
        device_class=SensorDeviceClass.POWER,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.get("aggregates", {}).get("total_offgrid_power"),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = []

    # Check if multi-device or single-device mode
    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        # Multi-device mode - create sensors for each device + aggregate sensors
        for mac in coordinator.get_device_macs():
            device_coordinator = coordinator.device_coordinators[mac]
            device_data = next(d for d in coordinator.devices if (d.get("ble_mac") or d.get("wifi_mac")) == mac)

            # Add standard sensors for this device
            for description in SENSOR_TYPES:
                entities.append(
                    MarstekMultiDeviceSensor(
                        coordinator=coordinator,
                        device_coordinator=device_coordinator,
                        entity_description=description,
                        device_mac=mac,
                        device_data=device_data,
                    )
                )

            # Add PV sensors if Venus D
            if device_coordinator.device_model == DEVICE_MODEL_VENUS_D:
                for description in PV_SENSOR_TYPES:
                    entities.append(
                        MarstekMultiDeviceSensor(
                            coordinator=coordinator,
                            device_coordinator=device_coordinator,
                            entity_description=description,
                            device_mac=mac,
                            device_data=device_data,
                        )
                    )

        # Add aggregate/system sensors
        # Create a synthetic unique ID for the system device
        all_macs = sorted(coordinator.get_device_macs())
        system_unique_id = "_".join(all_macs)

        for description in AGGREGATE_SENSOR_TYPES:
            entities.append(
                MarstekAggregateSensor(
                    coordinator=coordinator,
                    entity_description=description,
                    system_unique_id=system_unique_id,
                    device_count=len(all_macs),
                )
            )

    else:
        # Single device mode (legacy)
        # Add standard sensors
        for description in SENSOR_TYPES:
            entities.append(
                MarstekSensor(
                    coordinator=coordinator,
                    entity_description=description,
                    entry=entry,
                )
            )

        # Add PV sensors if Venus D
        if coordinator.device_model == DEVICE_MODEL_VENUS_D:
            for description in PV_SENSOR_TYPES:
                entities.append(
                    MarstekSensor(
                        coordinator=coordinator,
                        entity_description=description,
                        entry=entry,
                    )
                )

    async_add_entities(entities)


class MarstekSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Marstek sensor."""

    entity_description: MarstekSensorEntityDescription

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entity_description: MarstekSensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_has_entity_name = True
        device_mac = entry.data.get("ble_mac") or entry.data.get("wifi_mac")
        self._attr_unique_id = f"{device_mac}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, device_mac)},
            name=f"Marstek {entry.data['device']}",
            manufacturer="Marstek",
            model=entry.data["device"],
            sw_version=str(entry.data.get("firmware", "Unknown")),
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available - keep sensors available if we have data."""
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self.coordinator.data)
        # Keep entity available if we have any data at all (prevents "unknown" on transient failures)
        return self.coordinator.data is not None and len(self.coordinator.data) > 0


class MarstekMultiDeviceSensor(CoordinatorEntity, SensorEntity):
    """Representation of a Marstek sensor in multi-device mode."""

    entity_description: MarstekSensorEntityDescription

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        entity_description: MarstekSensorEntityDescription,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self.device_coordinator = device_coordinator
        self.device_mac = device_mac
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{device_mac}_{entity_description.key}"

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
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.value_fn:
            device_data = self.coordinator.get_device_data(self.device_mac)
            return self.entity_description.value_fn(device_data)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available - keep sensors available if we have data."""
        if self.entity_description.available_fn:
            device_data = self.coordinator.get_device_data(self.device_mac)
            return self.entity_description.available_fn(device_data)
        # Keep entity available if device has any data at all (prevents "unknown" on transient failures)
        device_data = self.coordinator.get_device_data(self.device_mac)
        return device_data is not None and len(device_data) > 0


class MarstekAggregateSensor(CoordinatorEntity, SensorEntity):
    """Representation of an aggregate Marstek sensor across multiple devices."""

    entity_description: MarstekSensorEntityDescription

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        entity_description: MarstekSensorEntityDescription,
        system_unique_id: str,
        device_count: int,
    ) -> None:
        """Initialize the aggregate sensor."""
        super().__init__(coordinator)
        self.entity_description = entity_description
        self._attr_has_entity_name = True
        self._attr_unique_id = f"{system_unique_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"system_{system_unique_id}")},
            name=f"Marstek System ({device_count} batteries)",
            manufacturer="Marstek",
            model="System",
        )

    @property
    def native_value(self):
        """Return the state of the sensor."""
        if self.entity_description.value_fn:
            return self.entity_description.value_fn(self.coordinator.data)
        return None

    @property
    def available(self) -> bool:
        """Return if entity is available - keep sensors available if we have data."""
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self.coordinator.data)
        # Keep entity available if we have any aggregate data (prevents "unknown" on transient failures)
        aggregates = self.coordinator.data.get("aggregates", {})
        return aggregates is not None and len(aggregates) > 0
