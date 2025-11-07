"""Tests for sensor platform."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from custom_components.marstek_local_api.const import DATA_COORDINATOR, DOMAIN
from custom_components.marstek_local_api.sensor import (
    MarstekSensor,
    async_setup_entry,
)


class TestMarstekSensor:
    """Test MarstekSensor class."""

    def test_init(self, mock_coordinator, mock_config_entry):
        """Test sensor entity initialization."""
        from custom_components.marstek_local_api.sensor import MarstekSensorEntityDescription
        
        description = MarstekSensorEntityDescription(
            key="battery_soc",
            name="Battery SOC",
        )
        
        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )
        
        assert entity.coordinator == mock_coordinator

    def test_unique_id(self, mock_coordinator, mock_config_entry):
        """Test sensor unique ID."""
        from custom_components.marstek_local_api.sensor import MarstekSensorEntityDescription
        
        description = MarstekSensorEntityDescription(
            key="battery_soc",
            name="Battery SOC",
        )
        
        entity = MarstekSensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )
        
        assert "battery_soc" in entity.unique_id

    def test_native_value(self, mock_coordinator, mock_config_entry):
        """Test native value calculation."""
        from custom_components.marstek_local_api.sensor import MarstekSensorEntityDescription
        
        mock_coordinator.data = {
            "battery": {"soc": 80},
        }
        
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
        from custom_components.marstek_local_api.sensor import MarstekSensorEntityDescription
        
        mock_coordinator.data = {
            "battery": {"soc": 80},
        }
        
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


@pytest.mark.asyncio
async def test_async_setup_entry_single_device(mock_hass, mock_config_entry, mock_coordinator):
    """Test sensor setup for single device."""
    mock_hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
    }
    
    mock_add_entities = Mock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()
    # Verify entities were added
    assert len(mock_add_entities.call_args[0][0]) > 0

