"""Tests for sensor platform."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.marstek_local_api.sensor import (
    AGGREGATE_SENSOR_TYPES,
    PV_SENSOR_TYPES,
    SENSOR_TYPES,
    MarstekSensor,
    MarstekSensorEntityDescription,
)


@pytest.fixture
def sample_sensor_data():
    """Sample data covering all sensor categories."""
    return {
        "device": {
            "device": "VenusE",
            "ver": 154,
            "ble_mac": "112233445566",
            "wifi_mac": "AABBCCDDEEFF",
            "ip": "192.168.1.100",
        },
        "battery": {
            "soc": 80,
            "bat_temp": 25.0,
            "bat_capacity": 2000.0,
            "rated_capacity": 2560.0,
            "bat_voltage": 48.0,
            "bat_current": 10.5,
            "error_code": 0,
            "dischrg_flag": True,
            "charg_flag": True,
        },
        "es": {
            "bat_power": 400,
            "ongrid_power": 100,
            "offgrid_power": 0,
            "pv_power": 500,
            "total_pv_energy": 10000,
            "total_grid_input_energy": 8000,
            "total_grid_output_energy": 5000,
            "total_load_energy": 12000,
            "bat_soc": 80,
        },
        "em": {
            "ct_state": 1,
            "a_power": 100,
            "b_power": 150,
            "c_power": 120,
            "total_power": 370,
            "parse_state": "ok",
        },
        "wifi": {
            "rssi": -50,
            "ssid": "TestNetwork",
            "sta_ip": "192.168.1.100",
            "sta_gate": "192.168.1.1",
            "sta_mask": "255.255.255.0",
            "sta_dns": "192.168.1.1",
        },
        "ble": {
            "state": "connect",
        },
        "pv": {
            "pv_power": 500,
            "pv_voltage": 40.0,
            "pv_current": 12.5,
        },
        "mode": {
            "mode": "Auto",
        },
        "_diagnostic": {
            "last_message_seconds": 5,
        },
    }


@pytest.fixture
def sample_aggregate_data():
    """Sample aggregate data for multi-device sensors."""
    return {
        "aggregates": {
            "total_battery_power": 800,
            "total_power_in": 1000,
            "total_power_out": 200,
            "total_rated_capacity": 5120.0,
            "total_remaining_capacity": 4000.0,
            "total_available_capacity": 3500.0,
            "total_soc": 78.125,
            "total_pv_power": 1000,
            "total_grid_power": 200,
            "total_offgrid_power": 0,
            "total_pv_energy": 20000,
            "total_grid_input_energy": 16000,
            "total_grid_output_energy": 10000,
            "total_load_energy": 24000,
        },
        "devices": {
            "112233445566": {},
            "AABBCCDDEEFF": {},
        },
    }


@pytest.fixture
def sensor_entity(mock_coordinator, mock_config_entry, sample_sensor_data):
    """Create a sensor entity with sample data."""
    mock_coordinator.data = sample_sensor_data
    description = MarstekSensorEntityDescription(
        key="battery_soc",
        name="Battery SOC",
    )
    return MarstekSensor(
        coordinator=mock_coordinator,
        entity_description=description,
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

    @pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
    def test_sensor_value_function(
        self, mock_coordinator, mock_config_entry, sample_sensor_data, sensor_type
    ):
        """Test all sensor value functions with sample data."""
        mock_coordinator.data = sample_sensor_data
        # Mock is_category_fresh to return True for all categories
        mock_coordinator.is_category_fresh = Mock(return_value=True)

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # Value function should not raise an exception
        value = entity.native_value
        # Value can be None, a number, or a string - all are valid
        assert value is None or isinstance(value, (int, float, str))

    @pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
    def test_sensor_with_empty_data(
        self, mock_coordinator, mock_config_entry, sensor_type
    ):
        """Test sensors handle empty data gracefully."""
        mock_coordinator.data = {}
        mock_coordinator.is_category_fresh = Mock(return_value=True)

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # Should not raise, may return None
        value = entity.native_value
        assert value is None or isinstance(value, (int, float, str))

    @pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
    def test_sensor_availability(
        self, mock_coordinator, mock_config_entry, sample_sensor_data, sensor_type
    ):
        """Test sensor availability logic."""
        mock_coordinator.data = sample_sensor_data

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # With data, sensor should be available
        assert entity.available is True

        # With empty data, sensor should be unavailable
        mock_coordinator.data = {}
        assert entity.available is False

        # With None data, sensor should be unavailable
        mock_coordinator.data = None
        assert entity.available is False

    @pytest.mark.parametrize("sensor_type", SENSOR_TYPES)
    def test_sensor_attributes(
        self, mock_coordinator, mock_config_entry, sample_sensor_data, sensor_type
    ):
        """Test sensor entity attributes."""
        mock_coordinator.data = sample_sensor_data
        mock_coordinator.is_category_fresh = Mock(return_value=True)

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        # Check that key is in unique_id
        assert sensor_type.key in entity.unique_id

        # Check device info is set
        assert entity.device_info is not None
        assert ("marstek_local_api", "112233445566") in entity.device_info["identifiers"]


class TestPVSensors:
    """Test PV-specific sensors."""

    @pytest.mark.parametrize("sensor_type", PV_SENSOR_TYPES)
    def test_pv_sensor_value_function(
        self, mock_coordinator, mock_config_entry, sample_sensor_data, sensor_type
    ):
        """Test PV sensor value functions."""
        mock_coordinator.data = sample_sensor_data
        mock_coordinator.is_category_fresh = Mock(return_value=True)

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            entry=mock_config_entry,
        )

        value = entity.native_value
        assert value is None or isinstance(value, (int, float))


class TestAggregateSensors:
    """Test aggregate sensors for multi-device setups."""

    @pytest.mark.parametrize("sensor_type", AGGREGATE_SENSOR_TYPES)
    def test_aggregate_sensor_value_function(
        self, mock_coordinator, mock_config_entry, sample_aggregate_data, sensor_type
    ):
        """Test aggregate sensor value functions."""
        from custom_components.marstek_local_api.sensor import MarstekAggregateSensor

        mock_coordinator.data = sample_aggregate_data

        entity = MarstekAggregateSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            system_unique_id="test_system",
            device_count=2,
        )

        value = entity.native_value
        assert value is None or isinstance(value, (int, float))

    @pytest.mark.parametrize("sensor_type", AGGREGATE_SENSOR_TYPES)
    def test_aggregate_sensor_availability(
        self, mock_coordinator, mock_config_entry, sample_aggregate_data, sensor_type
    ):
        """Test aggregate sensor availability."""
        from custom_components.marstek_local_api.sensor import MarstekAggregateSensor

        mock_coordinator.data = sample_aggregate_data

        entity = MarstekAggregateSensor(
            coordinator=mock_coordinator,
            entity_description=sensor_type,
            system_unique_id="test_system",
            device_count=2,
        )

        assert entity.available is True

        # With empty aggregates, should be unavailable
        mock_coordinator.data = {"aggregates": {}}
        assert entity.available is False


class TestSensorEdgeCases:
    """Test edge cases and error handling."""

    def test_sensor_with_none_value_function(self, mock_coordinator, mock_config_entry):
        """Test sensor with no value function."""
        description = MarstekSensorEntityDescription(
            key="test_sensor",
            name="Test Sensor",
            value_fn=None,
        )

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )

        assert entity.native_value is None

    def test_sensor_with_custom_available_fn(
        self, mock_coordinator, mock_config_entry, sample_sensor_data
    ):
        """Test sensor with custom availability function."""
        mock_coordinator.data = sample_sensor_data

        def custom_available_fn(data):
            return data.get("battery") is not None

        description = MarstekSensorEntityDescription(
            key="test_sensor",
            name="Test Sensor",
            available_fn=custom_available_fn,
        )

        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )

        assert entity.available is True

        mock_coordinator.data = {}
        assert entity.available is False
