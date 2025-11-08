"""Tests for button platform."""
from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest

from custom_components.marstek_local_api.button import (
    MarstekAIModeButton,
    MarstekAutoModeButton,
    MarstekManualModeButton,
)
from custom_components.marstek_local_api.const import MODE_AI, MODE_AUTO, MODE_MANUAL


@pytest.fixture
def button_entity(mock_coordinator, mock_config_entry):
    """Create a button entity."""
    return MarstekAutoModeButton(
        coordinator=mock_coordinator,
        entry=mock_config_entry,
    )


@pytest.mark.parametrize(
    "button_class,mode",
    [
        (MarstekAutoModeButton, MODE_AUTO),
        (MarstekAIModeButton, MODE_AI),
        (MarstekManualModeButton, MODE_MANUAL),
    ],
)
class TestMarstekModeButtons:
    """Test all Marstek mode button types."""

    def test_init(self, button_class, mode, mock_coordinator, mock_config_entry):
        """Test button entity initialization."""
        entity = button_class(coordinator=mock_coordinator, entry=mock_config_entry)
        assert entity.coordinator == mock_coordinator

    def test_unique_id(self, button_class, mode, mock_coordinator, mock_config_entry):
        """Test button unique ID contains mode."""
        entity = button_class(coordinator=mock_coordinator, entry=mock_config_entry)
        # Unique ID should contain the mode name
        assert mode.lower() in entity.unique_id.lower() or "mode" in entity.unique_id.lower()

    @pytest.mark.asyncio
    async def test_async_press_success(
        self, button_class, mode, mock_coordinator, mock_config_entry
    ):
        """Test successful button press."""
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)

        entity = button_class(coordinator=mock_coordinator, entry=mock_config_entry)
        await entity.async_press()

        mock_coordinator.api.set_es_mode.assert_called_once()
        call_args = mock_coordinator.api.set_es_mode.call_args[0][0]
        assert call_args["mode"] == mode

    @pytest.mark.asyncio
    async def test_async_press_failure(
        self, button_class, mode, mock_coordinator, mock_config_entry
    ):
        """Test button press with API failure."""
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=False)

        entity = button_class(coordinator=mock_coordinator, entry=mock_config_entry)

        with pytest.raises(Exception):
            await entity.async_press()


class TestMarstekModeButtonSpecific:
    """Test specific button behaviors."""

    def test_auto_mode_button(self, mock_coordinator, mock_config_entry):
        """Test Auto mode button specific attributes."""
        entity = MarstekAutoModeButton(
            coordinator=mock_coordinator, entry=mock_config_entry
        )
        assert entity.coordinator == mock_coordinator

    def test_ai_mode_button(self, mock_coordinator, mock_config_entry):
        """Test AI mode button specific attributes."""
        entity = MarstekAIModeButton(
            coordinator=mock_coordinator, entry=mock_config_entry
        )
        assert entity.coordinator == mock_coordinator

    def test_manual_mode_button(self, mock_coordinator, mock_config_entry):
        """Test Manual mode button specific attributes."""
        entity = MarstekManualModeButton(
            coordinator=mock_coordinator, entry=mock_config_entry
        )
        assert entity.coordinator == mock_coordinator
