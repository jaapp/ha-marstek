"""Tests for button platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.marstek_local_api.button import MarstekAutoModeButton
from custom_components.marstek_local_api.const import MODE_AUTO


@pytest.fixture
def button_entity(mock_coordinator, mock_config_entry):
    """Create a button entity."""
    return MarstekAutoModeButton(
        coordinator=mock_coordinator,
        entry=mock_config_entry,
    )


class TestMarstekModeButton:
    """Test MarstekModeButton class."""

    def test_init(self, button_entity, mock_coordinator):
        """Test button entity initialization."""
        assert button_entity.coordinator == mock_coordinator

    def test_unique_id(self, button_entity):
        """Test button unique ID."""
        assert "auto_mode" in button_entity.unique_id.lower()

    @pytest.mark.asyncio
    async def test_async_press(self, button_entity, mock_coordinator):
        """Test button press."""
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)

        await button_entity.async_press()

        mock_coordinator.api.set_es_mode.assert_called_once()
        call_args = mock_coordinator.api.set_es_mode.call_args[0][0]
        assert call_args["mode"] == MODE_AUTO

    @pytest.mark.asyncio
    async def test_async_press_failure(self, button_entity, mock_coordinator):
        """Test button press with API failure."""
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=False)

        with pytest.raises(Exception):
            await button_entity.async_press()
