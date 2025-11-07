"""Tests for coordinators."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.coordinator import (
    MarstekDataUpdateCoordinator,
    MarstekMultiDeviceCoordinator,
)


@pytest.fixture
def coordinator_kwargs():
    """Common coordinator initialization parameters."""
    return {
        "device_name": "Test Device",
        "firmware_version": 154,
        "device_model": "VenusE",
        "scan_interval": 60,
    }


@pytest.fixture
def frame_helper_patch(mock_hass):
    """Context manager for patching frame helper."""
    return patch("homeassistant.helpers.frame._hass.hass", mock_hass)


class TestMarstekDataUpdateCoordinator:
    """Test MarstekDataUpdateCoordinator class."""

    @pytest.mark.asyncio
    async def test_init(self, mock_hass, mock_api, mock_config_entry, coordinator_kwargs, frame_helper_patch):
        """Test coordinator initialization."""
        import asyncio
        loop = asyncio.get_event_loop()
        original_call_soon = loop.call_soon_threadsafe

        def mock_call_soon_threadsafe(callback, *args):
            try:
                return callback(*args)
            except Exception:
                pass

        loop.call_soon_threadsafe = mock_call_soon_threadsafe

        try:
            with frame_helper_patch:
                coordinator = MarstekDataUpdateCoordinator(
                    mock_hass,
                    mock_api,
                    config_entry=mock_config_entry,
                    **coordinator_kwargs,
                )

            assert coordinator.api == mock_api
            assert coordinator.firmware_version == 154
            assert coordinator.device_model == "VenusE"
        finally:
            loop.call_soon_threadsafe = original_call_soon

    @pytest.mark.asyncio
    async def test_async_update_data_success(self, mock_hass, mock_api, mock_config_entry, coordinator_kwargs, frame_helper_patch):
        """Test successful data update."""
        with frame_helper_patch:
            coordinator = MarstekDataUpdateCoordinator(
                mock_hass,
                mock_api,
                config_entry=mock_config_entry,
                **coordinator_kwargs,
            )

            mock_api.get_device_info = AsyncMock(return_value={"device": "VenusE", "ver": 154})
            mock_api.get_battery_status = AsyncMock(return_value={"soc": 80})
            mock_api.get_es_status = AsyncMock(return_value={"bat_power": 400})

            data = await coordinator._async_update_data()

            assert data is not None
            assert "device" in data

    @pytest.mark.asyncio
    async def test_async_update_data_failure(self, mock_hass, mock_api, mock_config_entry, coordinator_kwargs, frame_helper_patch):
        """Test data update with API failure."""
        with frame_helper_patch:
            coordinator = MarstekDataUpdateCoordinator(
                mock_hass,
                mock_api,
                config_entry=mock_config_entry,
                **coordinator_kwargs,
            )

            # Mock API failure - all methods return None
            for method in ("get_device_info", "get_es_status", "get_battery_status", "get_em_status", "get_es_mode"):
                setattr(mock_api, method, AsyncMock(return_value=None))

            data = await coordinator._async_update_data()
            assert isinstance(data, dict)


class TestMarstekMultiDeviceCoordinator:
    """Test MarstekMultiDeviceCoordinator class."""

    @pytest.fixture
    def test_devices(self):
        """Test device configuration."""
        return [
            {
                "host": "192.168.1.100",
                "port": 30000,
                "device": "VenusE",
                "firmware": 154,
                "ble_mac": "112233445566",
            }
        ]

    @pytest.mark.asyncio
    async def test_init(self, mock_hass, mock_config_entry, test_devices, frame_helper_patch):
        """Test multi-device coordinator initialization."""
        with frame_helper_patch:
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=test_devices,
                scan_interval=60,
                config_entry=mock_config_entry,
            )

            assert coordinator.devices == test_devices
            assert len(coordinator.device_coordinators) == 0  # Not set up yet

    def test_get_device_macs(self, mock_hass, mock_config_entry, frame_helper_patch):
        """Test getting device MACs."""
        with frame_helper_patch:
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

    def test_get_device_data(self, mock_hass, mock_config_entry, frame_helper_patch):
        """Test getting device data."""
        with frame_helper_patch:
            coordinator = MarstekMultiDeviceCoordinator(
                mock_hass,
                devices=[],
                scan_interval=60,
                config_entry=mock_config_entry,
            )

            mock_coord = Mock()
            mock_coord.data = {"battery": {"soc": 80}}
            coordinator.device_coordinators = {"112233445566": mock_coord}

            assert coordinator.get_device_data("112233445566") == {"battery": {"soc": 80}}
            assert coordinator.get_device_data("NONEXISTENT") == {}
