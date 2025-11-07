"""Tests for coordinators."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.const import DATA_COORDINATOR, DOMAIN
from custom_components.marstek_local_api.coordinator import (
    MarstekDataUpdateCoordinator,
    MarstekMultiDeviceCoordinator,
)


class TestMarstekDataUpdateCoordinator:
    """Test MarstekDataUpdateCoordinator class."""

    @pytest.mark.asyncio
    async def test_init(self, mock_hass, mock_api, mock_config_entry):
        """Test coordinator initialization."""
        # Patch frame helper with mock_hass for this test
        # Also patch the loop's call_soon_threadsafe to prevent shutdown check
        import asyncio
        loop = asyncio.get_event_loop()
        original_call_soon = loop.call_soon_threadsafe
        
        def mock_call_soon_threadsafe(callback, *args):
            """Mock call_soon_threadsafe that doesn't trigger shutdown check."""
            # Just call the callback directly
            try:
                return callback(*args)
            except Exception:
                pass
        
        loop.call_soon_threadsafe = mock_call_soon_threadsafe
        
        try:
            with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
                coordinator = MarstekDataUpdateCoordinator(
                    mock_hass,
                    mock_api,
                    device_name="Test Device",
                    firmware_version=154,
                    device_model="VenusE",
                    scan_interval=60,
                    config_entry=mock_config_entry,
                )
                
            assert coordinator.api == mock_api
            assert coordinator.firmware_version == 154
            assert coordinator.device_model == "VenusE"
        finally:
            loop.call_soon_threadsafe = original_call_soon

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, mock_hass, mock_api, mock_config_entry):
        """Test successful data update."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            coordinator = MarstekDataUpdateCoordinator(
                mock_hass,
                mock_api,
                device_name="Test Device",
                firmware_version=154,
                device_model="VenusE",
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            # Mock API responses
            mock_api.get_device_info = AsyncMock(return_value={"device": "VenusE", "ver": 154})
            mock_api.get_battery_status = AsyncMock(return_value={"soc": 80})
            mock_api.get_es_status = AsyncMock(return_value={"bat_power": 400})
            
            data = await coordinator._async_update_data()
            
            assert data is not None
            assert "device" in data

    @pytest.mark.asyncio
    async def test_async_update_data_failure(self, mock_hass, mock_api, mock_config_entry):
        """Test data update with API failure."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            coordinator = MarstekDataUpdateCoordinator(
                mock_hass,
                mock_api,
                device_name="Test Device",
                firmware_version=154,
                device_model="VenusE",
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            # Mock API failure - all methods return None
            mock_api.get_device_info = AsyncMock(return_value=None)
            mock_api.get_es_status = AsyncMock(return_value=None)
            mock_api.get_battery_status = AsyncMock(return_value=None)
            mock_api.get_em_status = AsyncMock(return_value=None)
            mock_api.get_es_mode = AsyncMock(return_value=None)
            
            # The coordinator handles failures gracefully and returns empty/partial data
            # It doesn't raise exceptions, it just logs warnings
            data = await coordinator._async_update_data()
            
            # Should return a dict (may be empty or partial)
            assert isinstance(data, dict)


class TestMarstekMultiDeviceCoordinator:
    """Test MarstekMultiDeviceCoordinator class."""

    @pytest.mark.asyncio
    async def test_init(self, mock_hass, mock_config_entry):
        """Test multi-device coordinator initialization."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            devices = [
                {
                    "host": "192.168.1.100",
                    "port": 30000,
                    "device": "VenusE",
                    "firmware": 154,
                    "ble_mac": "112233445566",
                }
            ]
            
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=devices,
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            assert coordinator.devices == devices
            assert len(coordinator.device_coordinators) == 0  # Not set up yet

    @pytest.mark.asyncio
    async def test_async_setup(self, mock_hass, mock_config_entry):
        """Test multi-device coordinator setup."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            devices = [
                {
                    "host": "192.168.1.100",
                    "port": 30000,
                    "device": "VenusE",
                    "firmware": 154,
                    "ble_mac": "112233445566",
                }
            ]
            
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=devices,
                scan_interval=60,
                config_entry=mock_config_entry,
            )
        
        with patch("custom_components.marstek_local_api.coordinator.MarstekUDPClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client.connect = AsyncMock()
            mock_client_class.return_value = mock_client
            
            with patch("custom_components.marstek_local_api.coordinator.MarstekDataUpdateCoordinator") as mock_coord_class:
                mock_device_coord = Mock()
                mock_coord_class.return_value = mock_device_coord
                
                await coordinator.async_setup()
                
                assert len(coordinator.device_coordinators) == 1

    def test_get_device_macs(self, mock_hass, mock_config_entry):
        """Test getting device MACs."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=[],
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            coordinator.device_coordinators = {
                "112233445566": Mock(),
                "AABBCCDDEEFF": Mock(),
            }
            
            macs = coordinator.get_device_macs()
            assert len(macs) == 2
            assert "112233445566" in macs

    def test_get_device_data(self, mock_hass, mock_config_entry):
        """Test getting device data."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=[],
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            mock_coord = Mock()
            mock_coord.data = {"battery": {"soc": 80}}
            coordinator.device_coordinators = {
                "112233445566": mock_coord,
            }
            
            data = coordinator.get_device_data("112233445566")
            assert data == {"battery": {"soc": 80}}
            
            # Test non-existent device
            data = coordinator.get_device_data("NONEXISTENT")
            assert data == {}

    @pytest.mark.asyncio
    async def test_async_update_data(self, mock_hass, mock_config_entry):
        """Test multi-device data update."""
        # Patch frame helper with mock_hass for this test
        with patch("homeassistant.helpers.frame._hass.hass", mock_hass):
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=[],
                scan_interval=60,
                config_entry=mock_config_entry,
            )
            
            # Mock device coordinators
            mock_coord1 = Mock()
            mock_coord1.data = {"battery": {"soc": 80}}
            mock_coord1._async_update_data = AsyncMock(return_value={"battery": {"soc": 80}})
            
            mock_coord2 = Mock()
            mock_coord2.data = {"battery": {"soc": 90}}
            mock_coord2._async_update_data = AsyncMock(return_value={"battery": {"soc": 90}})
            
            coordinator.device_coordinators = {
                "112233445566": mock_coord1,
                "AABBCCDDEEFF": mock_coord2,
            }
            
            data = await coordinator._async_update_data()
            
            assert data is not None
            assert "devices" in data

