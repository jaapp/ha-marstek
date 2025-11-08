"""Tests for MarstekUDPClient API."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, Mock, patch

import pytest

from custom_components.marstek_local_api.api import MarstekUDPClient
from custom_components.marstek_local_api.const import (
    DEFAULT_PORT,
    METHOD_GET_DEVICE,
)


@pytest.fixture
def mock_hass():
    """Mock HomeAssistant instance."""
    return Mock()


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
    return Mock()


@pytest.fixture
def client(mock_hass):
    """Create a MarstekUDPClient instance."""
    return MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)


class TestMarstekUDPClient:
    """Test MarstekUDPClient class."""

    def test_init(self, client, mock_hass):
        """Test client initialization."""
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
        loop = asyncio.get_event_loop()

        async def create_endpoint(*args, **kwargs):
            return mock_transport, mock_protocol

        with patch.object(loop, "create_datagram_endpoint", side_effect=create_endpoint):
            client = MarstekUDPClient(mock_hass, host="192.168.1.100", port=30000)
            await client.connect()

            assert client._connected is True
            assert client.transport == mock_transport
            assert client.protocol == mock_protocol

    @pytest.mark.asyncio
    async def test_connect_already_connected(self, client):
        """Test connecting when already connected."""
        client._connected = True
        client.transport = Mock()

        await client.connect()  # Should return early without error

    @pytest.mark.asyncio
    async def test_disconnect(self, client):
        """Test UDP disconnection."""
        from custom_components.marstek_local_api.api import _clients_by_port, _transport_refcounts

        client._connected = True
        client.transport = Mock()
        client.port = 30000
        _transport_refcounts[30000] = 1
        _clients_by_port[30000] = [client]

        await client.disconnect()

        assert client._connected is False

    @pytest.mark.asyncio
    async def test_disconnect_not_connected(self, client):
        """Test disconnecting when not connected."""
        await client.disconnect()  # Should return early without error

    @pytest.mark.asyncio
    async def test_broadcast(self, mock_hass):
        """Test broadcast method."""
        client = MarstekUDPClient(mock_hass, host=None, port=30000)
        client.transport = Mock()
        client.transport.sendto = Mock()

        with patch.object(client, "_get_broadcast_address", return_value="255.255.255.255"):
            await client.broadcast('{"test": "message"}')
            client.transport.sendto.assert_called_once()

    def test_register_handler(self, client):
        """Test handler registration."""
        handler = Mock()
        client.register_handler(handler)
        assert handler in client._handlers

    def test_unregister_handler(self, client):
        """Test handler unregistration."""
        handler = Mock()
        client.register_handler(handler)
        assert handler in client._handlers

        client.unregister_handler(handler)
        assert handler not in client._handlers

    def test_get_command_stats(self, client):
        """Test getting command statistics."""
        client._command_stats[METHOD_GET_DEVICE] = {
            "total_attempts": 10,
            "total_success": 8,
        }

        stats = client.get_command_stats(METHOD_GET_DEVICE)
        assert stats is not None
        assert stats["total_attempts"] == 10
        assert stats["total_success"] == 8

    def test_get_command_stats_not_found(self, client):
        """Test getting stats for non-existent command."""
        stats = client.get_command_stats(METHOD_GET_DEVICE)
        assert stats is None

    def test_get_all_command_stats(self, client):
        """Test getting all command statistics."""
        stats = client.get_all_command_stats()
        assert isinstance(stats, dict)
        assert METHOD_GET_DEVICE in stats
