"""Tests for button platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.const import DATA_COORDINATOR, DOMAIN, MODE_AUTO
from custom_components.marstek_local_api.button import (
    MarstekModeButton,
    async_setup_entry,
)


class TestMarstekModeButton:
    """Test MarstekModeButton class."""

    def test_init(self, mock_coordinator, mock_config_entry):
        """Test button entity initialization."""
        from custom_components.marstek_local_api.button import MarstekAutoModeButton
        
        entity = MarstekAutoModeButton(
            coordinator=mock_coordinator,
            entry=mock_config_entry,
        )
        
        assert entity.coordinator == mock_coordinator

    def test_unique_id(self, mock_coordinator, mock_config_entry):
        """Test button unique ID."""
        from custom_components.marstek_local_api.button import MarstekAutoModeButton
        
        entity = MarstekAutoModeButton(
            coordinator=mock_coordinator,
            entry=mock_config_entry,
        )
        
        assert "auto_mode" in entity.unique_id.lower()

    @pytest.mark.asyncio
    async def test_async_press(self, mock_coordinator, mock_config_entry):
        """Test button press."""
        from custom_components.marstek_local_api.button import MarstekAutoModeButton
        
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
        
        entity = MarstekAutoModeButton(
            coordinator=mock_coordinator,
            entry=mock_config_entry,
        )
        
        await entity.async_press()
        
        mock_coordinator.api.set_es_mode.assert_called_once()
        call_args = mock_coordinator.api.set_es_mode.call_args[0][0]
        assert call_args["mode"] == MODE_AUTO

    @pytest.mark.asyncio
    async def test_async_press_failure(self, mock_coordinator, mock_config_entry):
        """Test button press with API failure."""
        from custom_components.marstek_local_api.button import MarstekAutoModeButton
        
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=False)
        
        entity = MarstekAutoModeButton(
            coordinator=mock_coordinator,
            entry=mock_config_entry,
        )
        
        with pytest.raises(Exception):
            await entity.async_press()


@pytest.mark.asyncio
async def test_async_setup_entry_single_device(mock_hass, mock_config_entry, mock_coordinator):
    """Test button setup for single device."""
    mock_hass.data[DOMAIN] = {
        mock_config_entry.entry_id: {DATA_COORDINATOR: mock_coordinator}
    }
    
    mock_add_entities = Mock()
    await async_setup_entry(mock_hass, mock_config_entry, mock_add_entities)
    mock_add_entities.assert_called_once()
    # Verify entities were added
    assert len(mock_add_entities.call_args[0][0]) > 0

