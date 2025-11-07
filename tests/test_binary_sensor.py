"""Tests for binary sensor platform."""
from __future__ import annotations

from unittest.mock import Mock

import pytest

from custom_components.marstek_local_api.binary_sensor import (
    MarstekBinarySensor,
    MarstekBinarySensorEntityDescription,
)


@pytest.fixture
def binary_sensor_description():
    """Create a binary sensor entity description."""
    return MarstekBinarySensorEntityDescription(
        key="charging_enabled",
        name="Charging Enabled",
        value_fn=lambda data: data.get("battery", {}).get("charg_flag", False),
    )


@pytest.fixture
def binary_sensor_entity(mock_coordinator, mock_config_entry, binary_sensor_description):
    """Create a binary sensor entity."""
    return MarstekBinarySensor(
        coordinator=mock_coordinator,
        entity_description=binary_sensor_description,
        entry=mock_config_entry,
    )


class TestMarstekBinarySensor:
    """Test MarstekBinarySensor class."""

    def test_init(self, binary_sensor_entity, mock_coordinator):
        """Test binary sensor entity initialization."""
        assert binary_sensor_entity.coordinator == mock_coordinator

    @pytest.mark.parametrize("charg_flag,expected", [(True, True), (False, False)])
    def test_is_on(self, mock_coordinator, mock_config_entry, binary_sensor_description, charg_flag, expected):
        """Test is_on value."""
        mock_coordinator.data = {"battery": {"charg_flag": charg_flag}}

        entity = MarstekBinarySensor(
            coordinator=mock_coordinator,
            entity_description=binary_sensor_description,
            entry=mock_config_entry,
        )

        assert entity.is_on is expected
