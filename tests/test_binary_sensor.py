"""Tests for binary sensor platform."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.marstek_local_api.binary_sensor import (
    BINARY_SENSOR_TYPES,
    MarstekBinarySensor,
    MarstekBinarySensorEntityDescription,
)
from custom_components.marstek_local_api.const import BLE_STATE_CONNECT, CT_STATE_CONNECTED


@pytest.fixture
def sample_binary_sensor_data():
    """Sample data covering all binary sensor types."""
    return {
        "battery": {
            "charg_flag": True,
            "dischrg_flag": False,
        },
        "ble": {
            "state": BLE_STATE_CONNECT,
        },
        "em": {
            "ct_state": CT_STATE_CONNECTED,
        },
    }


@pytest.fixture
def binary_sensor_entity(mock_coordinator, mock_config_entry, sample_binary_sensor_data):
    """Create a binary sensor entity with sample data."""
    mock_coordinator.data = sample_binary_sensor_data
    description = MarstekBinarySensorEntityDescription(
        key="charging_enabled",
        name="Charging Enabled",
        value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
    )
    return MarstekBinarySensor(
        coordinator=mock_coordinator,
        entity_description=description,
        entry=mock_config_entry,
    )


class TestMarstekBinarySensor:
    """Test MarstekBinarySensor class."""

    def test_init(self, binary_sensor_entity, mock_coordinator):
        """Test binary sensor entity initialization."""
        assert binary_sensor_entity.coordinator == mock_coordinator

    @pytest.mark.parametrize("sensor_type", BINARY_SENSOR_TYPES)
    def test_binary_sensor_value_function(
        self, mock_coordinator, mock_config_entry, sample_binary_sensor_data, sensor_type
    ):
        """Test all binary sensor value functions."""
        mock_coordinator.data = sample_binary_sensor_data

        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # Value should be a boolean
        value = entity.is_on
        assert isinstance(value, bool)

    @pytest.mark.parametrize("sensor_type", BINARY_SENSOR_TYPES)
    def test_binary_sensor_with_empty_data(
        self, mock_coordinator, mock_config_entry, sensor_type
    ):
        """Test binary sensors handle empty data gracefully."""
        mock_coordinator.data = {}

        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # Should return False (default) or not raise
        value = entity.is_on
        assert isinstance(value, bool)

    @pytest.mark.parametrize("sensor_type", BINARY_SENSOR_TYPES)
    def test_binary_sensor_availability(
        self, mock_coordinator, mock_config_entry, sample_binary_sensor_data, sensor_type
    ):
        """Test binary sensor availability logic."""
        mock_coordinator.data = sample_binary_sensor_data

        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        assert entity.available is True

        mock_coordinator.data = {}
        assert entity.available is False

        mock_coordinator.data = None
        assert entity.available is False

    @pytest.mark.parametrize(
        "sensor_key,data_path,true_value,false_value",
        [
            ("charging_enabled", {"battery": {"charg_flag": True}}, True, False),
            ("discharging_enabled", {"battery": {"dischrg_flag": True}}, True, False),
            (
                "bluetooth_connected",
                {"ble": {"state": BLE_STATE_CONNECT}},
                True,
                False,
            ),
            (
                "ct_connected",
                {"em": {"ct_state": CT_STATE_CONNECTED}},
                True,
                False,
            ),
        ],
    )
    def test_binary_sensor_states(
        self,
        mock_coordinator,
        mock_config_entry,
        sensor_key,
        data_path,
        true_value,
        false_value,
    ):
        """Test binary sensor states for each sensor type."""
        # Find the sensor type
        sensor_type = next(s for s in BINARY_SENSOR_TYPES if s.key == sensor_key)

        # Test True state
        mock_coordinator.data = data_path
        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )
        assert entity.is_on == true_value

        # Test False state
        mock_coordinator.data = {}
        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )
        assert entity.is_on == false_value
