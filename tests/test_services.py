"""Tests for services."""
from __future__ import annotations

from datetime import time
from unittest.mock import AsyncMock, Mock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.marstek_local_api.const import (
    DATA_COORDINATOR,
    DOMAIN,
    MODE_MANUAL,
    MODE_PASSIVE,
)
from custom_components.marstek_local_api.services import (
    _resolve_device_context,
    async_setup_services,
)


async def test_set_manual_schedule_service(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_manual_schedule service."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_manual_handler = None
    for call in call_args:
        if call[0][1] == "set_manual_schedule":
            set_manual_handler = call[0][2]
            break
    
    assert set_manual_handler is not None
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "time_num": 0,
        "start_time": time(8, 0),
        "end_time": time(20, 0),
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "power": 100,
        "enabled": True,
    }
    
    # Call the service
    await set_manual_handler(service_call)
    
    # Verify API was called with correct config
    expected_config = {
        "mode": MODE_MANUAL,
        "manual_cfg": {
            "time_num": 0,
            "start_time": "08:00",
            "end_time": "20:00",
            "week_set": 127,  # All days
            "power": 100,
            "enable": 1,
        },
    }
    mock_coordinator.api.set_es_mode.assert_called_once_with(expected_config)


async def test_set_passive_mode_service(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_passive_mode service."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_passive_handler = None
    for call in call_args:
        if call[0][1] == "set_passive_mode":
            set_passive_handler = call[0][2]
            break
    
    assert set_passive_handler is not None
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "power": 500,
        "duration": 7200,
    }
    
    # Call the service
    await set_passive_handler(service_call)
    
    # Verify API was called with correct config
    expected_config = {
        "mode": MODE_PASSIVE,
        "passive_cfg": {
            "power": 500,
            "cd_time": 7200,
        },
    }
    mock_coordinator.api.set_es_mode.assert_called_once_with(expected_config)


async def test_set_manual_schedule_service_failure(mock_hass, mock_coordinator, mock_device_registry):
    """Test set_manual_schedule service with API failure."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    mock_coordinator.api.set_es_mode = AsyncMock(return_value=False)
    
    await async_setup_services(mock_hass)
    
    # Get the registered service handler
    call_args = mock_hass.services.async_register.call_args_list
    set_manual_handler = None
    for call in call_args:
        if call[0][1] == "set_manual_schedule":
            set_manual_handler = call[0][2]
            break
    
    # Create a mock service call
    service_call = Mock()
    service_call.data = {
        "device_id": "test_device_id",
        "time_num": 0,
        "start_time": time(8, 0),
        "end_time": time(20, 0),
        "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
        "power": 100,
        "enabled": True,
    }
    
    # Should raise HomeAssistantError
    with pytest.raises(HomeAssistantError):
        await set_manual_handler(service_call)


async def test_resolve_device_context(mock_hass, mock_coordinator, mock_device_registry):
    """Test helper function to resolve device context."""
    # Setup
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: mock_coordinator}
    }
    
    coordinator, aggregate_coordinator, device_identifier = _resolve_device_context(mock_hass, "test_device_id")
    
    assert coordinator == mock_coordinator
    # For single-device coordinator, device_identifier is None
    assert device_identifier is None
    assert aggregate_coordinator is None


async def test_resolve_device_context_not_found(mock_hass, mock_device_registry):
    """Test helper function with device not found."""
    # Setup with no coordinator
    mock_hass.data[DOMAIN] = {}
    
    with pytest.raises(HomeAssistantError, match="Integration has no active entries"):
        _resolve_device_context(mock_hass, "test_device_id")


async def test_set_manual_schedules_service_multi_device(mock_hass, mock_coordinator, mock_api, mock_device_registry):
    """Test set_manual_schedules service for multi-device setup."""
    from custom_components.marstek_local_api.coordinator import MarstekMultiDeviceCoordinator
    from custom_components.marstek_local_api.const import SERVICE_SET_MANUAL_SCHEDULES, DOMAIN
    
    # Create a second mock API with mode tracking
    second_api = AsyncMock()
    second_current_mode = {"mode": "Auto"}
    
    async def second_get_es_mode():
        return {
            "mode": second_current_mode["mode"],
            "ongrid_power": 100,
            "offgrid_power": 0,
            "bat_soc": 80,
        }
    
    async def second_set_es_mode(config):
        if isinstance(config, dict) and "mode" in config:
            second_current_mode["mode"] = config["mode"]
        return True
    
    second_api.get_es_mode = AsyncMock(side_effect=second_get_es_mode)
    second_api.set_es_mode = AsyncMock(side_effect=second_set_es_mode)
    
    # Create a second coordinator
    second_coordinator = Mock()
    second_coordinator.api = second_api
    second_coordinator.async_request_refresh = AsyncMock()
    
    # Ensure mock_coordinator.api.set_es_mode is properly set up as AsyncMock
    if not hasattr(mock_coordinator.api, 'set_es_mode') or not isinstance(mock_coordinator.api.set_es_mode, AsyncMock):
        mock_coordinator.api.set_es_mode = AsyncMock(return_value=True)
    
    # Create a mock multi-device coordinator
    multi_coordinator = Mock(spec=MarstekMultiDeviceCoordinator)
    multi_coordinator.device_coordinators = {
        "112233445566": mock_coordinator,
        "AABBCCDDEEFF": second_coordinator,
    }
    multi_coordinator.async_request_refresh = AsyncMock()
    # Add data attribute needed by _apply_local_mode_state
    multi_coordinator.data = {
        "devices": {
            "112233445566": mock_coordinator.data,
            "AABBCCDDEEFF": second_coordinator.data if hasattr(second_coordinator, 'data') else {},
        }
    }
    
    mock_hass.data[DOMAIN] = {
        "test_entry_id": {DATA_COORDINATOR: multi_coordinator}
    }
    
    # Set up device registry properly - device needs to have identifiers and config_entries
    import homeassistant.helpers.device_registry as dr_module
    with patch("homeassistant.helpers.device_registry.async_get", mock_device_registry):
        # The mock_device_registry fixture already returns a device with identifiers
        # Make sure it has the right config_entries
        device = Mock()
        device.id = "test_device_id"
        device.identifiers = {(DOMAIN, "112233445566")}  # Match one of the coordinators
        device.config_entries = {"test_entry_id"}
        registry = Mock()
        registry.async_get = Mock(return_value=device)
        mock_device_registry.return_value = registry
        
        await async_setup_services(mock_hass)
        
        # Verify the service was registered
        call_args = mock_hass.services.async_register.call_args_list
        set_schedules_handler = None
        for call in call_args:
            if len(call[0]) >= 2 and call[0][1] == SERVICE_SET_MANUAL_SCHEDULES:
                set_schedules_handler = call[0][2]
                break
        
        assert set_schedules_handler is not None
        
        # Create a mock service call
        from datetime import time as dt_time
        service_call = Mock()
        schedule_data = {
            "time_num": 0,
            "start_time": dt_time(8, 0),  # Use time object, not string
            "end_time": dt_time(20, 0),  # Use time object, not string
            "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],  # List of day names matching WEEKDAY_MAP
            "power": 100,
            "enabled": 1,  # Use 'enabled' instead of 'enable'
        }
        service_call.data = {
            "device_id": "test_device_id",  # Use device_id for multi-device
            "schedules": [schedule_data],
        }
        
        # Call the service
        await set_schedules_handler(service_call)
        
        # Verify API was called - the service resolves device_coordinator from multi_coordinator.device_coordinators
        # and calls set_es_mode on that coordinator's API
        # The device identifier "112233445566" maps to mock_coordinator in device_coordinators
        # The service successfully set the schedule (we see the log "Successfully set schedule slot 0")
        # Verify that set_es_mode was called on mock_coordinator.api (the one matching the device identifier)
        assert mock_coordinator.api.set_es_mode.called, f"set_es_mode should have been called. Call count: {mock_coordinator.api.set_es_mode.call_count}"

