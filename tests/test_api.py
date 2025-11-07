"""Tests for MarstekUDPClient API."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from custom_components.marstek_local_api.api import MarstekUDPClient, MarstekAPIError
from custom_components.marstek_local_api.const import (
    COMMAND_TIMEOUT,
    DEFAULT_PORT,
    METHOD_BATTERY_STATUS,
    METHOD_ES_MODE,
    METHOD_ES_SET_MODE,
    METHOD_GET_DEVICE,
)


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant instance."""
    hass = Mock()
    return hass


@pytest.fixture
def mock_transport():
    """Mock UDP transport."""
    transport = Mock()
    transport.get_extra_info = Mock(return_value=Mock(getsockname=Mock(return_value=("0.0.0.0", 30000))))
    transport.sendto = Mock()
    transport.close = Mock()
    return transport


@pytest.fixture
def mock_protocol():
    """Mock UDP protocol."""
    protocol = Mock()
    return protocol


class TestMarstekUDPClient:
    """Test MarstekUDPClient class."""

    def test_init(self, mock_hass):
        """Test client initialization."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        assert client.hass == mock_hass
        assert client.host == "192.168.1.100"
        assert client.port == 30000
        assert client.remote_port == DEFAULT_PORT
        assert client._connected is False
        assert client.transport is None

    def test_init_with_remote_port(self, mock_hass):
        """Test client initialization with custom remote port."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000, remote_port=30001)
        assert client.remote_port == 30001

    @pytest.mark.asyncio
    async def test_connect(self, mock_hass, mock_transport, mock_protocol):
        """Test UDP connection."""
        with patch("asyncio.get_event_loop") as mock_loop:
            loop = asyncio.get_event_loop()
            mock_loop.return_value = loop
            
            with patch("asyncio.get_event_loop") as mock_get_loop:
                mock_get_loop.return_value = loop
                
                async def create_endpoint(*args, **kwargs):
                    return mock_transport, mock_protocol
                
                with patch.object(loop, "create_datagram_endpoint", side_effect=create_endpoint):
                    client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
                    await client.connect()
                    
                    assert client._connected is True
                    assert client.transport == mock_transport
                    assert client.protocol == mock_protocol

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, mock_hass):
        """Test connecting when already connected."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client._connected = True
        client.transport = Mock()
        
        await client.connect()  # Should return early without error

    @pytest.mark.asyncio
    async def test_disconnect(self, mock_hass):
        """Test UDP disconnection."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client._connected = True
        client.transport = Mock()
        client.port = 30000
        
        # Mock shared transport refcounts
        from custom_components.marstek_local_api.api import _transport_refcounts, _clients_by_port
        _transport_refcounts[30000] = 1
        _clients_by_port[30000] = [client]
        
        await client.disconnect()
        
        assert client._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, mock_hass):
        """Test disconnecting when not connected."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        await client.disconnect()  # Should return early without error

    @pytest.mark.asyncio
    async def test_send_command_success(self, mock_hass):
        """Test sending a command successfully."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client._connected = True
        client.transport = Mock()
        client.protocol = Mock()
        
        # Mock response
        response = {"id": 1, "result": {"device": "VenusE"}}
        
        async def mock_send_command(*args, **kwargs):
            # Simulate response
            await asyncio.sleep(0.01)
            return response
        
        with patch.object(client, "send_command", side_effect=mock_send_command):
            result = await client.send_command(METHOD_GET_DEVICE)
            assert result == response

    @pytest.mark.asyncio
    async def test_send_command_timeout(self, mock_hass):
        """Test command timeout."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client._connected = True
        client.transport = Mock()
        client.protocol = Mock()
        
        # Mock no response (timeout)
        async def mock_send_command(*args, **kwargs):
            await asyncio.sleep(COMMAND_TIMEOUT + 1)
            return None
        
        with patch.object(client, "send_command", side_effect=mock_send_command):
            result = await client.send_command(METHOD_GET_DEVICE, timeout=0.1, max_attempts=1)
            assert result is None

    @pytest.mark.asyncio
    async def test_get_device_info(self, mock_hass, mock_api):
        """Test get_device_info method."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        expected_response = {"id": 1, "result": {"device": "VenusE", "ver": 154}}
        client.send_command = AsyncMock(return_value=expected_response)
        
        result = await client.get_device_info()
        assert result == expected_response
        client.send_command.assert_called_once()

    @pytest.mark.asyncio
    async def test_get_battery_status(self, mock_hass):
        """Test get_battery_status method."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        expected_response = {"id": 1, "result": {"soc": 80, "bat_temp": 25.0}}
        client.send_command = AsyncMock(return_value=expected_response)
        
        result = await client.get_battery_status()
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_get_es_mode(self, mock_hass):
        """Test get_es_mode method."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        expected_response = {"id": 1, "result": {"mode": "Auto"}}
        client.send_command = AsyncMock(return_value=expected_response)
        
        result = await client.get_es_mode()
        assert result == expected_response

    @pytest.mark.asyncio
    async def test_set_es_mode_success(self, mock_hass):
        """Test set_es_mode method with success."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        # set_es_mode checks result.get("set_result"), so set_result should be at top level
        client.send_command = AsyncMock(return_value={
            "id": 1,
            "set_result": True
        })
        
        config = {"mode": "Manual", "manual_cfg": {}}
        result = await client.set_es_mode(config)
        assert result is True

    @pytest.mark.asyncio
    async def test_set_es_mode_failure(self, mock_hass):
        """Test set_es_mode method with failure."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client.send_command = AsyncMock(return_value={
            "id": 1,
            "result": {"set_result": False}
        })
        
        config = {"mode": "Manual", "manual_cfg": {}}
        result = await client.set_es_mode(config)
        assert result is False

    @pytest.mark.asyncio
    async def test_set_es_mode_no_result(self, mock_hass):
        """Test set_es_mode method with no result."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client.send_command = AsyncMock(return_value=None)
        
        config = {"mode": "Manual", "manual_cfg": {}}
        result = await client.set_es_mode(config)
        assert result is False

    @pytest.mark.asyncio
    async def test_broadcast(self, mock_hass):
        """Test broadcast method."""
        client = MarstekUDPClient(mock_hass, host=None, port=30000)
        client.transport = Mock()
        client.transport.sendto = Mock()
        
        with patch.object(client, "_get_broadcast_address", return_value="255.255.255.255"):
            await client.broadcast('{"test": "message"}')
            client.transport.sendto.assert_called_once()

    def test_register_handler(self, mock_hass):
        """Test handler registration."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        handler = Mock()
        
        client.register_handler(handler)
        assert handler in client._handlers

    def test_unregister_handler(self, mock_hass):
        """Test handler unregistration."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        handler = Mock()
        
        client.register_handler(handler)
        assert handler in client._handlers
        
        client.unregister_handler(handler)
        assert handler not in client._handlers

    def test_get_command_stats(self, mock_hass):
        """Test getting command statistics."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        client._command_stats[METHOD_GET_DEVICE] = {
            "total_attempts": 10,
            "total_success": 8,
        }
        
        stats = client.get_command_stats(METHOD_GET_DEVICE)
        assert stats is not None
        assert stats["total_attempts"] == 10
        assert stats["total_success"] == 8

    def test_get_command_stats_not_found(self, mock_hass):
        """Test getting stats for non-existent command."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        stats = client.get_command_stats(METHOD_GET_DEVICE)
        assert stats is None

    def test_get_all_command_stats(self, mock_hass):
        """Test getting all command statistics."""
        client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
        stats = client.get_all_command_stats()
        assert isinstance(stats, dict)
        assert METHOD_GET_DEVICE in stats

