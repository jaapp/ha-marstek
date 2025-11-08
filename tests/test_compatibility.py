"""Tests for compatibility module."""
from __future__ import annotations

import pytest

from custom_components.marstek_local_api.compatibility import CompatibilityMatrix


class TestCompatibilityMatrix:
    """Test CompatibilityMatrix class."""

    def test_init(self):
        """Test compatibility matrix initialization."""
        matrix = CompatibilityMatrix("VenusE", 154)
        assert matrix is not None
        assert matrix.device_model == "VenusE"
        assert matrix.firmware_version == 154

    def test_scale_value(self):
        """Test value scaling."""
        # Test with older firmware (HW 2.0, FW < 154)
        matrix_old = CompatibilityMatrix("VenusE", 100)
        scaled = matrix_old.scale_value(10000, "bat_capacity")
        assert scaled == 100.0  # centi-Wh to Wh (10000 / 100)
        
        # Test with newer firmware (HW 2.0, FW >= 154)
        matrix_new = CompatibilityMatrix("VenusE", 154)
        scaled = matrix_new.scale_value(2000, "bat_capacity")
        assert scaled == 2000.0  # Wh (2000 / 1)

    def test_scale_value_hw3(self):
        """Test value scaling for HW 3.0."""
        matrix = CompatibilityMatrix("VenusE 3.0", 139)
        scaled = matrix.scale_value(250, "bat_temp")
        assert scaled == 25.0  # deca-°C to °C (250 / 10)

    def test_scale_value_not_found(self):
        """Test scaling for unknown field."""
        matrix = CompatibilityMatrix("VenusE", 154)
        scaled = matrix.scale_value(100, "unknown_field")
        assert scaled == 100.0  # Default no scaling

    def test_get_info(self):
        """Test get_info method."""
        matrix = CompatibilityMatrix("VenusE 3.0", 154)
        info = matrix.get_info()
        assert info["device_model"] == "VenusE 3.0"
        assert info["base_model"] == "VenusE"
        assert info["hardware_version"] == "3.0"
        assert info["firmware_version"] == 154

