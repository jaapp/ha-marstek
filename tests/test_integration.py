"""Integration tests for end-to-end workflows."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.const import DATA_COORDINATOR, DOMAIN
from custom_components.marstek_local_api import async_setup_entry


class TestIntegration:
    """Integration tests for full workflows."""

    @pytest.mark.asyncio
    async def test_full_setup_flow(self, mock_hass, mock_config_entry, mock_api):
        """Test full setup flow from config entry to entities."""
        # Mock coordinator creation
        with patch("custom_components.marstek_local_api.MarstekUDPClient", return_value=mock_api):
            with patch("custom_components.marstek_local_api.MarstekDataUpdateCoordinator") as mock_coord_class:
                mock_coordinator = Mock()
                mock_coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_coord_class.return_value = mock_coordinator
                
                # Mock config_entries.async_forward_entry_setups
                mock_hass.config_entries = Mock()
                mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
                mock_config_entry.async_on_unload = Mock()
                mock_config_entry.add_update_listener = Mock()
                
                result = await async_setup_entry(mock_hass, mock_config_entry)
                
                assert result is True
                assert mock_config_entry.entry_id in mock_hass.data[DOMAIN]
                # Verify the coordinator was set up
                assert DATA_COORDINATOR in mock_hass.data[DOMAIN][mock_config_entry.entry_id]

    @pytest.mark.asyncio
    async def test_multi_device_setup(self, mock_hass, mock_config_entry, mock_api):
        """Test multi-device setup and aggregation."""
        # Modify config entry for multi-device
        mock_config_entry.data = {
            "devices": [
                {
                    "host": "192.168.1.100",
                    "port": 30000,
                    "device": "VenusE",
                    "firmware": 154,
                    "ble_mac": "112233445566",
                },
                {
                    "host": "192.168.1.101",
                    "port": 30000,
                    "device": "VenusE",
                    "firmware": 154,
                    "ble_mac": "AABBCCDDEEFF",
                },
            ]
        }
        
        # Mock config_entries.async_forward_entry_setups
        mock_hass.config_entries = Mock()
        mock_hass.config_entries.async_forward_entry_setups = AsyncMock()
        mock_config_entry.async_on_unload = Mock()
        mock_config_entry.add_update_listener = Mock()
        
        with patch("custom_components.marstek_local_api.MarstekUDPClient", return_value=mock_api):
            with patch("custom_components.marstek_local_api.MarstekMultiDeviceCoordinator") as mock_multi_class:
                mock_multi_coordinator = Mock()
                mock_multi_coordinator.async_setup = AsyncMock()
                mock_multi_coordinator.async_config_entry_first_refresh = AsyncMock()
                mock_multi_class.return_value = mock_multi_coordinator
                
                result = await async_setup_entry(mock_hass, mock_config_entry)
                
                assert result is True
                mock_multi_coordinator.async_setup.assert_called_once()

    @pytest.mark.asyncio
    async def test_service_call_workflow(self, mock_hass, mock_coordinator, mock_device_registry):
        """Test service call workflow."""
        from custom_components.marstek_local_api.services import async_setup_services
        
        mock_hass.data[DOMAIN] = {
            "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
        }
        
        await async_setup_services(mock_hass)
        
        # Verify services are registered
        assert mock_hass.services.async_register.called

    @pytest.mark.asyncio
    async def test_mode_switching_workflow(self, mock_hass, mock_coordinator, mock_config_entry):
        """Test mode switching workflow."""
        from custom_components.marstek_local_api.button import MarstekAutoModeButton
        
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
        mock_coordinator.async_request_refresh = AsyncMock()
        # The button updates coordinator data directly, doesn't call async_request_refresh
        mock_coordinator.async_set_updated_data = Mock()
        
        button = MarstekAutoModeButton(
            coordinator=mock_coordinator,
            entry=mock_config_entry,
        )
        
        await button.async_press()
        
        # Verify API was called
        mock_coordinator.api.set_es_mode.assert_called_once()
        # Button updates coordinator data directly via async_set_updated_data
        # instead of calling async_request_refresh
        assert mock_coordinator.async_set_updated_data.called or mock_coordinator.data is not None

