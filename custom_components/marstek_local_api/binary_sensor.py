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
from .coordinator import MarstekDataUpdateCoordinator

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
        name="Charging Enabled",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
    ),
    MarstekBinarySensorEntityDescription(
        key="discharging_enabled",
        name="Discharging Enabled",
        value_fn=lambda data: data.get("battery", {}).get("dischrg_flag", False),
    ),
    # Bluetooth connection
    MarstekBinarySensorEntityDescription(
        key="bluetooth_connected",
        name="Bluetooth Connected",
        device_class=BinarySensorDeviceClass.CONNECTIVITY,
        value_fn=lambda data: data.get("ble", {}).get("state") == BLE_STATE_CONNECT,
    ),
    # CT connection
    MarstekBinarySensorEntityDescription(
        key="ct_connected",
        name="CT Connected",
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
        self._attr_unique_id = f"{entry.data['mac']}_{entity_description.key}"
        mac_suffix = entry.data["mac"].replace(":", "")[-4:].upper()
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.data["mac"])},
            name=f"Marstek {entry.data['device']} {mac_suffix}",
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
        """Return if entity is available."""
        if self.entity_description.available_fn:
            return self.entity_description.available_fn(self.coordinator.data)
        return super().available
