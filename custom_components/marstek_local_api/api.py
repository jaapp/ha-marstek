"""Marstek Local API UDP client."""
from __future__ import annotations

import asyncio
import json
import logging
import socket
from typing import Any
from uuid import uuid4

from .const import (
    COMMAND_TIMEOUT,
    DEFAULT_PORT,
    DISCOVERY_BROADCAST_INTERVAL,
    DISCOVERY_TIMEOUT,
    METHOD_BATTERY_STATUS,
    METHOD_BLE_STATUS,
    METHOD_EM_STATUS,
    METHOD_ES_MODE,
    METHOD_ES_SET_MODE,
    METHOD_ES_STATUS,
    METHOD_GET_DEVICE,
    METHOD_PV_STATUS,
    METHOD_WIFI_STATUS,
)

_LOGGER = logging.getLogger(__name__)


class MarstekUDPClient:
    """UDP client for Marstek Local API communication."""

    def __init__(self, hass, host: str | None = None, port: int = DEFAULT_PORT, remote_port: int | None = None) -> None:
        """Initialize the UDP client.

        Args:
            hass: Home Assistant instance
            host: Target host IP (None for broadcast)
            port: Local port to bind to (0 for ephemeral)
            remote_port: Remote port to send to (defaults to DEFAULT_PORT)
        """
        self.hass = hass
        self.host = host
        self.port = port
        self.remote_port = remote_port or DEFAULT_PORT
        self.transport: asyncio.DatagramTransport | None = None
        self.protocol: MarstekProtocol | None = None
        self._handlers: list = []
        self._connected = False

    async def connect(self) -> None:
        """Connect to the UDP socket."""
        if self._connected and self.transport:
            return

        loop = asyncio.get_event_loop()

        # Create UDP endpoint with port reuse to allow multiple instances
        self.transport, self.protocol = await loop.create_datagram_endpoint(
            lambda: MarstekProtocol(self),
            local_addr=("0.0.0.0", self.port),
            allow_broadcast=True,
            reuse_port=True,  # Allow multiple binds to same port
        )

        self._connected = True
        _LOGGER.debug("UDP socket connected on port %s", self.port)

    async def disconnect(self) -> None:
        """Disconnect from the UDP socket."""
        if self.transport:
            self.transport.close()
            self.transport = None
            self.protocol = None
            self._connected = False
            _LOGGER.debug("UDP socket disconnected")

    def register_handler(self, handler) -> None:
        """Register a message handler."""
        if handler not in self._handlers:
            self._handlers.append(handler)

    def unregister_handler(self, handler) -> None:
        """Unregister a message handler."""
        if handler in self._handlers:
            self._handlers.remove(handler)

    async def _handle_message(self, data: bytes, addr: tuple) -> None:
        """Handle incoming UDP message."""
        try:
            message = json.loads(data.decode())
            _LOGGER.debug("Received message from %s: %s", addr, message)

            # Call all registered handlers
            for handler in self._handlers:
                try:
                    # Handler can be sync or async
                    result = handler(message, addr)
                    if asyncio.iscoroutine(result):
                        await result
                except Exception as err:
                    _LOGGER.error("Error in message handler: %s", err)

        except json.JSONDecodeError as err:
            _LOGGER.error("Failed to decode JSON message: %s", err)

    async def send_command(
        self,
        method: str,
        params: dict | None = None,
        timeout: int = COMMAND_TIMEOUT,
    ) -> dict | None:
        """Send a command and wait for response."""
        if not self._connected:
            await self.connect()

        if params is None:
            params = {"id": 0}

        # Generate unique message ID
        msg_id = f"homeassistant-{uuid4().hex[:8]}"
        payload = {
            "id": msg_id,
            "method": method,
            "params": params,
        }

        # Create event for response
        response_event = asyncio.Event()
        response_data = {}

        def handler(message, addr):
            """Handle command response."""
            if message.get("id") == msg_id:
                if self.host and addr[0] != self.host:
                    return  # Wrong device
                response_data.update(message)
                response_event.set()

        # Register temporary handler
        self.register_handler(handler)

        try:
            # Send command
            await self._send_to_host(json.dumps(payload))

            # Wait for response
            await asyncio.wait_for(response_event.wait(), timeout=timeout)

            if "error" in response_data:
                error = response_data["error"]
                raise MarstekAPIError(
                    f"API error {error.get('code')}: {error.get('message')}"
                )

            return response_data.get("result")

        except asyncio.TimeoutError:
            _LOGGER.warning("Command %s timed out after %ss", method, timeout)
            return None
        finally:
            self.unregister_handler(handler)

    async def _send_to_host(self, message: str) -> None:
        """Send message to specific host or broadcast."""
        if not self.transport:
            raise MarstekAPIError("Not connected")

        if self.host:
            # Send to specific host on remote port
            self.transport.sendto(
                message.encode(),
                (self.host, self.remote_port)
            )
        else:
            # Broadcast
            await self.broadcast(message)

    async def broadcast(self, message: str) -> None:
        """Broadcast a message."""
        if not self.transport:
            await self.connect()

        # Get broadcast address
        broadcast_addr = self._get_broadcast_address()

        self.transport.sendto(
            message.encode(),
            (broadcast_addr, self.remote_port)
        )
        _LOGGER.debug("Broadcast message: %s", message)

    def _get_broadcast_addresses(self) -> list[str]:
        """Get all broadcast addresses for available networks.

        Uses simple heuristic: broadcast on /24 of primary interface and global broadcast.
        This works for most home networks and avoids VPN interfaces.
        """
        import struct
        import subprocess

        broadcast_addrs = set()

        try:
            # Parse ifconfig to get all network interfaces and their IPs
            result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=2)
            current_ip = None

            for line in result.stdout.split('\n'):
                # Parse inet lines
                if '\tinet ' in line:
                    parts = line.strip().split()
                    if len(parts) >= 2 and parts[0] == 'inet':
                        ip = parts[1]

                        # Skip loopback
                        if ip.startswith('127.'):
                            continue

                        # Parse netmask if present
                        netmask = None
                        if 'netmask' in parts:
                            idx = parts.index('netmask')
                            if idx + 1 < len(parts):
                                mask_hex = parts[idx + 1]
                                # Skip point-to-point /32 (VPN) interfaces
                                if mask_hex == '0xffffffff':
                                    continue

                                # Convert hex netmask to dotted decimal
                                try:
                                    mask_int = int(mask_hex, 16)
                                    netmask = socket.inet_ntoa(struct.pack('>I', mask_int))
                                except (ValueError, OSError):
                                    pass

                        # Check for explicit broadcast address
                        if 'broadcast' in parts:
                            idx = parts.index('broadcast')
                            if idx + 1 < len(parts):
                                broadcast_addrs.add(parts[idx + 1])
                        elif netmask:
                            # Calculate broadcast address
                            try:
                                ip_int = struct.unpack('>I', socket.inet_aton(ip))[0]
                                mask_int = struct.unpack('>I', socket.inet_aton(netmask))[0]
                                broadcast_int = ip_int | (~mask_int & 0xffffffff)
                                broadcast = socket.inet_ntoa(struct.pack('>I', broadcast_int))
                                broadcast_addrs.add(broadcast)
                            except (ValueError, OSError):
                                pass
                        else:
                            # Assume /24 network
                            parts_ip = ip.split(".")
                            if len(parts_ip) == 4:
                                broadcast_addrs.add(f"{parts_ip[0]}.{parts_ip[1]}.{parts_ip[2]}.255")

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as err:
            _LOGGER.debug("Could not parse ifconfig: %s, using fallback", err)

        # If we found nothing, use global broadcast as fallback
        if not broadcast_addrs:
            broadcast_addrs.add("255.255.255.255")

        return list(broadcast_addrs)

    def _get_broadcast_address(self) -> str:
        """Get primary broadcast address (for backward compatibility)."""
        addrs = self._get_broadcast_addresses()
        return addrs[0] if addrs else "255.255.255.255"

    async def discover_devices(self, timeout: int = DISCOVERY_TIMEOUT) -> list[dict]:
        """Discover Marstek devices on the network."""
        devices = []
        discovered_macs = set()

        def handler(message, addr):
            """Handle discovery responses."""
            if message.get("id") == "homeassistant-discover" and "result" in message:
                result = message["result"]
                mac = result.get("wifi_mac")

                if mac and mac not in discovered_macs:
                    discovered_macs.add(mac)
                    devices.append({
                        "name": result.get("device", "Unknown"),
                        "ip": addr[0],
                        "mac": mac,
                        "firmware": result.get("ver", 0),
                        "ble_mac": result.get("ble_mac"),
                        "wifi_name": result.get("wifi_name"),
                    })

        # Register handler
        self.register_handler(handler)

        try:
            # Get all broadcast addresses
            broadcast_addrs = self._get_broadcast_addresses()
            _LOGGER.debug("Broadcasting to networks: %s", broadcast_addrs)

            # Broadcast discovery message repeatedly on all networks
            end_time = asyncio.get_event_loop().time() + timeout
            message = json.dumps({
                "id": "homeassistant-discover",
                "method": METHOD_GET_DEVICE,
                "params": {"ble_mac": "0"}
            })

            while asyncio.get_event_loop().time() < end_time:
                # Broadcast to all networks
                for broadcast_addr in broadcast_addrs:
                    if self.transport:
                        self.transport.sendto(
                            message.encode(),
                            (broadcast_addr, self.remote_port)
                        )
                await asyncio.sleep(DISCOVERY_BROADCAST_INTERVAL)

        finally:
            self.unregister_handler(handler)

        return devices

    # API method helpers
    async def get_device_info(self) -> dict | None:
        """Get device information."""
        return await self.send_command(METHOD_GET_DEVICE, {"ble_mac": "0"})

    async def get_wifi_status(self) -> dict | None:
        """Get WiFi status."""
        return await self.send_command(METHOD_WIFI_STATUS)

    async def get_ble_status(self) -> dict | None:
        """Get Bluetooth status."""
        return await self.send_command(METHOD_BLE_STATUS)

    async def get_battery_status(self) -> dict | None:
        """Get battery status."""
        return await self.send_command(METHOD_BATTERY_STATUS)

    async def get_pv_status(self) -> dict | None:
        """Get PV (solar) status."""
        return await self.send_command(METHOD_PV_STATUS)

    async def get_es_status(self) -> dict | None:
        """Get energy system status."""
        return await self.send_command(METHOD_ES_STATUS)

    async def get_es_mode(self) -> dict | None:
        """Get energy system operating mode."""
        return await self.send_command(METHOD_ES_MODE)

    async def get_em_status(self) -> dict | None:
        """Get energy meter (CT) status."""
        return await self.send_command(METHOD_EM_STATUS)

    async def set_es_mode(self, config: dict) -> bool:
        """Set energy system operating mode."""
        result = await self.send_command(
            METHOD_ES_SET_MODE,
            {"id": 0, "config": config}
        )

        if result and result.get("set_result"):
            return True
        return False


class MarstekProtocol(asyncio.DatagramProtocol):
    """Protocol for handling UDP datagrams."""

    def __init__(self, client: MarstekUDPClient) -> None:
        """Initialize the protocol."""
        self.client = client

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        """Handle received datagram."""
        # Schedule the handler in the event loop
        asyncio.create_task(self.client._handle_message(data, addr))

    def error_received(self, exc: Exception) -> None:
        """Handle protocol errors."""
        _LOGGER.error("Protocol error: %s", exc)


class MarstekAPIError(Exception):
    """Exception for Marstek API errors."""
