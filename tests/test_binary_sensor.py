"""Tests for binary sensor platform."""
from __future__ import annotations

from unittest.mock import Mock, patch

import pytest

from custom_components.marstek_local_api.const import DATA_COORDINATOR, DOMAIN
from custom_components.marstek_local_api.binary_sensor import (
    MarstekBinarySensor,
    async_setup_entry,
)


class TestMarstekBinarySensor:
    """Test MarstekBinarySensor class."""

    def test_init(self, mock_coordinator, mock_config_entry):
        """Test binary sensor entity initialization."""
        from custom_components.marstek_local_api.binary_sensor import MarstekBinarySensorEntityDescription
        
        description = MarstekBinarySensorEntityDescription(
            key="charging_enabled",
            name="Charging Enabled",
        )
        
        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )
        
        assert entity.coordinator == mock_coordinator

    def test_is_on(self, mock_coordinator, mock_config_entry):
        """Test is_on value."""
        from custom_components.marstek_local_api.binary_sensor import MarstekBinarySensorEntityDescription
        
        mock_coordinator.data = {
            "battery": {"charg_flag": True},
        }
        
        description = MarstekBinarySensorEntityDescription(
            key="charging_enabled",
            name="Charging Enabled",
            value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
        )
        
        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )
        
        assert entity.is_on is True

    def test_is_on_false(self, mock_coordinator, mock_config_entry):
        """Test is_on value when false."""
        from custom_components.marstek_local_api.binary_sensor import MarstekBinarySensorEntityDescription
        
        mock_coordinator.data = {
            "battery": {"charg_flag": False},
        }
        
        description = MarstekBinarySensorEntityDescription(
            key="charging_enabled",
            name="Charging Enabled",
            value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
        )
        
        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=description,
            entry=mock_config_entry,
        )
        
        assert entity.is_on is False


@pytest.mark.asyncio
async def test_async_setup_entry_single_device(mock_hass, mock_config_entry, mock_coordinator):
    """Test binary sensor setup for single device."""
    mock_hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
    }
    
    mock_add_entities = Mock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()
    # Verify entities were added
    assert len(mock_add_entities.call_args[0][0]) > 0

