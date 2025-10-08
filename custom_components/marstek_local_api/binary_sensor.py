"""Binary sensor platform for Marstek Local API."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    BLE_STATE_CONNECT,
    CT_STATE_CONNECTED,
    DATA_COORDINATOR,
    DOMAIN,
)
from .coordinator import MarstekDataUpdateCoordinator, MarstekMultiDeviceCoordinator

_LOGGER = logging.getLogger(__name__)


@dataclass
class MarstekBinarySensorEntityDescription(BinarySensorEntityDescription):
    """Describes Marstek binary sensor entity."""

    value_fn: Callable[[dict], bool] | None = None
    available_fn: Callable[[dict], bool] | None = None


BINARY_SENSOR_TYPES: tuple[MarstekBinarySensorEntityDescription, ...] = (
    # Battery charging/discharging flags
    MarstekBinarySensorEntityDescription(
        key="charging_enabled",
        name="Charging enabled",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
    ),
    MarstekBinarySensorEntityDescription(
        key="discharging_enabled",
        name="Discharging enabled",
        value_fn=lambda data: data.get("battery", {}).get("dischrg_flag", False),
    ),
    # Bluetooth connection
    MarstekBinarySensorEntityDescription(
        key="bluetooth_connected",
        name="Bluetooth connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("ble", {}).get("state") == BLE_STATE_CONNECT,
    ),
    # CT connection
    MarstekBinarySensorEntityDescription(
        key="ct_connected",
        name="CT connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("em", {}).get("ct_state") == CT_STATE_CONNECTED,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Marstek binary sensor based on a config entry."""
    coordinator = hass.data[DOMAIN][entry.entry_id][DATA_COORDINATOR]

    entities = []

    # Check if multi-device or single-device mode
    if isinstance(coordinator, MarstekMultiDeviceCoordinator):
        # Multi-device mode - create binary sensors for each device
        for mac in coordinator.get_device_macs():
            device_coordinator = coordinator.device_coordinators[mac]
            device_data = next(d for d in coordinator.devices if d["mac"] == mac)

            for description in BINARY_SENSOR_TYPES:
                entities.append(
                    MarstekMultiDeviceBinarySensor(
                        coordinator=coordinator,
                        device_coordinator=device_coordinator,
                        entity_description=description,
                        device_mac=mac,
                        device_data=device_data,
                    )
                )
    else:
        # Single device mode (legacy)
        for description in BINARY_SENSOR_TYPES:
            entities.append(
                MarstekBinarySensor(
                    coordinator=coordinator,
                    entity_description=description,
                    entry=entry,
                )
            )

    async_add_entities(entities)


class MarstekBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Marstek binary sensor."""

    entity_description: MarstekBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: MarstekDataUpdateCoordinator,
        entity_description: MarstekBinarySensorEntityDescription,
        entry: ConfigEntry,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
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


class MarstekMultiDeviceBinarySensor(CoordinatorEntity, BinarySensorEntity):
    """Representation of a Marstek binary sensor in multi-device mode."""

    entity_description: MarstekBinarySensorEntityDescription

    def __init__(
        self,
        coordinator: MarstekMultiDeviceCoordinator,
        device_coordinator: MarstekDataUpdateCoordinator,
        entity_description: MarstekBinarySensorEntityDescription,
        device_mac: str,
        device_data: dict,
    ) -> None:
        """Initialize the binary sensor."""
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
    def is_on(self) -> bool | None:
        """Return true if the binary sensor is on."""
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
