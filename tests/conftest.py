"""Fixtures for Marstek Local API tests."""
from __future__ import annotations

import asyncio
import sys
from concurrent import futures
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mock missing dependencies before any imports
sys.modules["aiodhcpwatcher"] = Mock()
# Create a proper mock module structure for aiodiscover
aiodiscover_mock = Mock()
aiodiscover_mock.discovery = Mock()
sys.modules["aiodiscover"] = aiodiscover_mock
sys.modules["aiodiscover.discovery"] = aiodiscover_mock.discovery
sys.modules["cached_ipaddress"] = Mock()
# Mock the dhcp component to avoid all its dependencies
dhcp_mock = Mock()
sys.modules["homeassistant.components.dhcp"] = dhcp_mock

from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

# Mock Home Assistant frame helper before importing coordinator
# Set it to a mock object so the check passes
import homeassistant.helpers.frame as frame_module
frame_module._hass.hass = Mock()

# Patch run_callback_threadsafe at import time to avoid event loop shutdown issues
def _patched_run_callback_threadsafe(loop, callback, *args):
    """Patched version that never checks for shutdown."""
    future = futures.Future()
    try:
        result = callback(*args)
        future.set_result(result)
    except Exception as e:
        future.set_exception(e)
    return future

# Patch it before any coordinator imports
import homeassistant.util.async_ as async_module
async_module.run_callback_threadsafe = _patched_run_callback_threadsafe

from custom_components.marstek_local_api.const import CONF_PORT, DOMAIN


@pytest.fixture
def mock_api():
    """Mock MarstekUDPClient."""
    api = AsyncMock()
    api.connect = AsyncMock()
    api.disconnect = AsyncMock()
    api.get_device_info = AsyncMock(return_value={
        "device": "VenusE",
        "ver": 154,
        "ble_mac": "112233445566",
        "wifi_mac": "AABBCCDDEEFF",
        "wifi_name": "TestNetwork",
        "ip": "192.168.1.100",
    })
    api.get_wifi_status = AsyncMock(return_value={
        "ssid": "TestNetwork",
        "rssi": -50,
        "sta_ip": "192.168.1.100",
        "sta_gate": "192.168.1.1",
        "sta_mask": "255.255.255.0",
        "sta_dns": "192.168.1.1",
    })
    api.get_ble_status = AsyncMock(return_value={
        "state": "connect",
        "ble_mac": "112233445566",
    })
    api.get_battery_status = AsyncMock(return_value={
        "soc": 80,
        "charg_flag": True,
        "dischrg_flag": True,
        "bat_temp": 25.0,
        "bat_capacity": 2000.0,
        "rated_capacity": 2560.0,
    })
    api.get_es_status = AsyncMock(return_value={
        "bat_soc": 80,
        "bat_cap": 2560,
        "pv_power": 500,
        "ongrid_power": 100,
        "offgrid_power": 0,
        "bat_power": 400,
        "total_pv_energy": 10000,
        "total_grid_output_energy": 5000,
        "total_grid_input_energy": 8000,
        "total_load_energy": 12000,
    })
    # Track current mode for verification
    current_mode = {"mode": "Auto"}
    
    async def get_es_mode():
        """Return current mode."""
        return {
            "mode": current_mode["mode"],
            "ongrid_power": 100,
            "offgrid_power": 0,
            "bat_soc": 80,
        }
    
    async def set_es_mode(config):
        """Set mode and update current_mode."""
        if isinstance(config, dict) and "mode" in config:
            current_mode["mode"] = config["mode"]
        return True
    
    api.get_es_mode = AsyncMock(side_effect=get_es_mode)
    api.set_es_mode = AsyncMock(side_effect=set_es_mode)
    api.get_em_status = AsyncMock(return_value={
        "ct_state": 1,
        "a_power": 100,
        "b_power": 150,
        "c_power": 120,
        "total_power": 370,
    })
    api.get_pv_status = AsyncMock(return_value={
        "pv_power": 500,
        "pv_voltage": 40.0,
        "pv_current": 12.5,
    })
    # get_command_stats is a synchronous method, not async
    api.get_command_stats = Mock(return_value={
        "total_attempts": 0,
        "total_success": 0,
        "total_timeouts": 0,
        "last_latency": None,
        "last_attempt": None,
        "last_success": None,
        "last_error": None,
    })
    return api


@pytest.fixture
def mock_coordinator(mock_api):
    """Mock MarstekDataUpdateCoordinator."""
    from custom_components.marstek_local_api.coordinator import MarstekDataUpdateCoordinator
    
    coordinator = Mock(spec=MarstekDataUpdateCoordinator)
    coordinator.api = mock_api
    coordinator.device_model = "VenusE"  # Add device_model attribute
    coordinator.data = {
        "device": {"device": "VenusE", "ver": 154, "ble_mac": "112233445566"},
        "battery": {"soc": 80, "bat_temp": 25.0},
        "es": {"bat_power": 400},
        "mode": {"mode": "Auto"},
    }
    coordinator.async_request_refresh = AsyncMock()
    return coordinator


@pytest.fixture
def mock_config_entry():
    """Mock config entry."""
    entry = Mock()
    entry.entry_id = "test_entry_id"
    entry.data = {
        CONF_HOST: "192.168.1.100",
        CONF_PORT: 30000,
        "device": "VenusE",
        "firmware": 154,
        "ble_mac": "112233445566",
        "wifi_mac": "AABBCCDDEEFF",
    }
    entry.options = {}
    return entry


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant."""
    hass = Mock(spec=HomeAssistant)
    hass.data = {DOMAIN: {}}
    hass.services = Mock()
    hass.services.has_service = Mock(return_value=False)
    hass.services.async_register = Mock()  # async_register is actually synchronous in HA
    hass.services.async_remove = Mock()
    hass.states = Mock()
    hass.states.get = Mock(return_value=None)
    # Add attributes needed by DataUpdateCoordinator
    hass.loop_thread_id = None
    hass.loop = Mock()  # Add loop attribute
    # Add config attribute needed by some components
    hass.config = Mock()
    hass.config.config_dir = "/tmp/test_config"
    return hass


@pytest.fixture
def mock_device_registry():
    """Mock device registry."""
    with patch("homeassistant.helpers.device_registry.async_get") as mock_get:
        registry = Mock()
        device = Mock()
        device.id = "test_device_id"
        device.identifiers = {(DOMAIN, "112233445566")}
        device.config_entries = {"test_entry_id"}
        registry.async_get = Mock(return_value=device)
        mock_get.return_value = registry
        yield mock_get


@pytest.fixture(autouse=True)
def mock_frame_helper():
    """Mock Home Assistant frame helper to avoid 'Frame helper not set up' errors."""
    # Import the constant to check for shutdown
    try:
        from homeassistant.util.async_ import _SHUTDOWN_RUN_CALLBACK_THREADSAFE
    except ImportError:
        _SHUTDOWN_RUN_CALLBACK_THREADSAFE = "_shutdown_run_callback_threadsafe"
    
    def mock_run_callback_threadsafe(loop, callback, *args):
        """Mock run_callback_threadsafe to avoid event loop shutdown errors."""
        # Remove shutdown attribute from loop if present to prevent the check
        if hasattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE):
            try:
                delattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE)
            except (AttributeError, TypeError):
                pass
        
        # Call the callback directly (synchronous) to avoid event loop issues
        future = futures.Future()
        try:
            result = callback(*args)
            future.set_result(result)
        except Exception as e:
            future.set_exception(e)
        return future
    
    def mock_report_usage(*args, **kwargs):
        """Mock report_usage to avoid calling run_callback_threadsafe."""
        # Just do nothing - we don't need to report usage in tests
        pass
    
    # Replace both the function and frame.report_usage
    with patch("homeassistant.util.async_.run_callback_threadsafe", new=mock_run_callback_threadsafe):
        with patch("homeassistant.helpers.frame.report_usage", new=mock_report_usage):
            # Also ensure the event loop doesn't have the shutdown attribute
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if hasattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE):
                    try:
                        delattr(loop, _SHUTDOWN_RUN_CALLBACK_THREADSAFE)
                    except (AttributeError, TypeError):
                        pass
            except RuntimeError:
                # No event loop running, that's fine
                pass
            yield

