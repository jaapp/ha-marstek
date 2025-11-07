"""Tests for sensor platform."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.marstek_local_api.sensor import (
    MarstekSensor,
    MarstekSensorEntityDescription,
)


@pytest.fixture
def sensor_description():
    """Create a sensor entity description."""
    return MarstekSensorEntityDescription(
        key="battery_soc",
        name="Battery SOC",
    )


@pytest.fixture
def sensor_entity(mock_coordinator, mock_config_entry, sensor_description):
    """Create a sensor entity."""
    return MarstekSensor(
        coordinator=mock_coordinator,
        entity_description=sensor_description,
        entry=mock_config_entry,
    )


class TestMarstekSensor:
    """Test MarstekSensor class."""

    def test_init(self, sensor_entity, mock_coordinator):
        """Test sensor entity initialization."""
        assert sensor_entity.coordinator == mock_coordinator

    def test_unique_id(self, sensor_entity):
        """Test sensor unique ID."""
        assert "battery_soc" in sensor_entity.unique_id

    def test_native_value(self, mock_coordinator, mock_config_entry):
        """Test native value calculation."""
        mock_coordinator.data = {"battery": {"soc": 80}}

        description = MarstekSensorEntityDescription(
            key="battery_soc",
            name="Battery SOC",
            value_fn=lambda data: data.get("battery", {}).get("soc"),
        )

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )

        assert entity.native_value == 80

    def test_available(self, mock_coordinator, mock_config_entry):
        """Test availability."""
        mock_coordinator.data = {"battery": {"soc": 80}}

        description = MarstekSensorEntityDescription(
            key="battery_soc",
            name="Battery SOC",
            available_fn=lambda data: data.get("battery") is not None,
        )

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )

        assert entity.available is True
