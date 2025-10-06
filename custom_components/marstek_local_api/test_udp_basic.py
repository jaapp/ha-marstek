#!/usr/bin/env python3
"""Basic UDP network test - no dependencies on HA modules.

Run this on your HA device to test UDP broadcast capability.

Usage:
  python3 test_udp_basic.py                    # Auto-discovery via broadcast
  python3 test_udp_basic.py 192.168.7.101      # Test specific IP address
  python3 test_udp_basic.py 192.168.7.101 30000  # Custom port
"""

import asyncio
import json
import socket
import sys
from datetime import datetime


class UDPTester:
    def __init__(self):
        self.transport = None
        self.protocol = None
        self.responses = []

    async def test_discovery(self, host=None, port=30000, timeout=10):
        """Test UDP discovery (broadcast or direct)."""
        print(f"\n{'='*80}")
        print(f"UDP Network Diagnostic Test")
        print(f"{'='*80}\n")

        print(f"Test Parameters:")
        print(f"  Mode: {'Direct IP' if host else 'Broadcast Discovery'}")
        if host:
            print(f"  Target Host: {host}")
        print(f"  Port: {port}")
        print(f"  Timeout: {timeout}s")
        print(f"  Time: {datetime.now()}\n")

        # Get network info
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "unknown"

        print(f"System Info:")
        print(f"  Hostname: {hostname}")
        print(f"  Local IP: {local_ip}")
        print(f"  Python: {sys.version.split()[0]}\n")

        # Create UDP socket
        print(f"Step 1: Creating UDP socket...")
        try:
            loop = asyncio.get_event_loop()

            class Protocol(asyncio.DatagramProtocol):
                def __init__(self, tester):
                    self.tester = tester

                def datagram_received(self, data, addr):
                    try:
                        msg = json.loads(data.decode())
                        print(f"  ✅ Response from {addr[0]}:{addr[1]}")
                        print(f"     Data: {msg}")
                        self.tester.responses.append((msg, addr))
                    except Exception as e:
                        print(f"  ⚠️  Invalid response from {addr}: {e}")

                def error_received(self, exc):
                    print(f"  ❌ Protocol error: {exc}")

            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: Protocol(self),
                local_addr=("0.0.0.0", port),
                allow_broadcast=True,
                reuse_port=True,
            )

            sock = self.transport.get_extra_info('socket')
            sock_name = sock.getsockname()
            print(f"  ✅ Socket bound to {sock_name[0]}:{sock_name[1]}")
            print(f"  ✅ Broadcast enabled: {sock.getsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST)}")
            print(f"  ✅ Port reuse: {sock.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT)}\n")

        except Exception as e:
            print(f"  ❌ Failed to create socket: {e}\n")
            import traceback
            traceback.print_exc()
            return False

        # Determine target addresses
        if host:
            # Direct IP mode
            print(f"Step 2: Using direct IP address...")
            target_addrs = [host]
            print(f"  Target: {host}\n")
        else:
            # Broadcast discovery mode
            print(f"Step 2: Testing broadcast addresses...")
            target_addrs = self._get_broadcast_addresses()
            print(f"  Found {len(target_addrs)} broadcast address(es):")
            for addr in target_addrs:
                print(f"    - {addr}")
            print()

        # Send discovery messages
        print(f"Step 3: Sending discovery messages...")
        discovery_msg = {
            "id": "test-discovery",
            "method": "Marstek.Scan",
            "params": {"id": 0}
        }
        msg_str = json.dumps(discovery_msg)

        for addr in target_addrs:
            try:
                self.transport.sendto(msg_str.encode(), (addr, port))
                print(f"  ✅ Sent to {addr}:{port}")
            except Exception as e:
                print(f"  ❌ Failed to send to {addr}:{port} - {e}")

        print(f"\nStep 4: Waiting {timeout}s for responses...")
        await asyncio.sleep(timeout)

        # Results
        print(f"\n{'='*80}")
        print(f"Results")
        print(f"{'='*80}\n")

        if self.responses:
            print(f"✅ Found {len(self.responses)} device(s):\n")
            devices = []
            for msg, addr in self.responses:
                result = msg.get('result', {})
                print(f"Device from {addr[0]}:{addr[1]}:")
                print(f"  Model: {result.get('name', 'unknown')}")
                print(f"  IP: {result.get('ip', 'unknown')}")
                print(f"  MAC: {result.get('mac', 'unknown')}")
                print(f"  Firmware: v{result.get('ver', 'unknown')}")
                print()
                if result.get('ip'):
                    devices.append(result.get('ip'))

            # If we found devices, test API commands
            if devices and host:
                print(f"{'='*80}")
                print(f"Testing API Commands on {host}")
                print(f"{'='*80}\n")
                await self.test_commands(host, port)

            return True
        else:
            print(f"❌ No devices found\n")
            print(f"Possible causes:")
            print(f"  1. Device not powered on")
            print(f"  2. Local API not enabled in Marstek app")
            print(f"  3. Device on different network/VLAN")
            print(f"  4. Firewall blocking UDP port {port}")
            print(f"  5. Network doesn't support broadcast")
            print(f"  6. Wrong broadcast address calculation\n")
            return False

    async def test_commands(self, host, port, timeout=5):
        """Test actual API commands."""
        commands = [
            ("Marstek.GetDevice", "Device Info"),
            ("ES.GetStatus", "Energy System Status"),
            ("Bat.GetStatus", "Battery Status"),
        ]

        for method, description in commands:
            print(f"Testing {description} ({method})...")
            msg_id = f"test-{method.lower().replace('.', '-')}"
            payload = {
                "id": msg_id,
                "method": method,
                "params": {"id": 0}
            }

            # Clear previous responses
            self.responses.clear()

            # Send command
            self.transport.sendto(json.dumps(payload).encode(), (host, port))

            # Wait for response
            await asyncio.sleep(timeout)

            # Check response
            found = False
            for msg, addr in self.responses:
                if msg.get('id') == msg_id and 'result' in msg:
                    print(f"  ✅ Success - received response")
                    result = msg.get('result', {})
                    # Show a sample of the data
                    if isinstance(result, dict):
                        keys = list(result.keys())[:5]
                        print(f"     Data keys: {', '.join(keys)}{' ...' if len(result) > 5 else ''}")
                    found = True
                    break

            if not found:
                print(f"  ❌ No response or error")

            print()

    def _get_broadcast_addresses(self):
        """Get broadcast addresses using multiple methods."""
        addrs = set()

        # Method 1: Global broadcast
        addrs.add("255.255.255.255")

        # Method 2: Using netifaces if available
        try:
            import netifaces
            for iface in netifaces.interfaces():
                try:
                    addrs_info = netifaces.ifaddresses(iface)
                    if netifaces.AF_INET in addrs_info:
                        for addr_info in addrs_info[netifaces.AF_INET]:
                            if 'broadcast' in addr_info:
                                addrs.add(addr_info['broadcast'])
                except:
                    pass
        except ImportError:
            pass

        # Method 3: Parse ifconfig/ip output
        try:
            import subprocess
            try:
                result = subprocess.run(['ip', 'addr'], capture_output=True, text=True, timeout=2)
                output = result.stdout
            except:
                result = subprocess.run(['ifconfig'], capture_output=True, text=True, timeout=2)
                output = result.stdout

            # Look for broadcast addresses
            import re
            broadcasts = re.findall(r'broadcast\s+(\d+\.\d+\.\d+\.\d+)', output)
            for bc in broadcasts:
                addrs.add(bc)
        except:
            pass

        # Method 4: Calculate from local IP (assume /24)
        try:
            hostname = socket.gethostname()
            local_ip = socket.gethostbyname(hostname)
            if local_ip and not local_ip.startswith('127.'):
                parts = local_ip.split('.')
                if len(parts) == 4:
                    broadcast = f"{parts[0]}.{parts[1]}.{parts[2]}.255"
                    addrs.add(broadcast)
        except:
            pass

        return sorted(list(addrs))

    async def close(self):
        """Close the transport."""
        if self.transport:
            self.transport.close()


async def main():
    # Parse command line arguments
    host = None
    port = 30000

    if len(sys.argv) > 1:
        host = sys.argv[1]
        if len(sys.argv) > 2:
            try:
                port = int(sys.argv[2])
            except ValueError:
                print(f"Error: Invalid port number '{sys.argv[2]}'")
                print(f"Usage: {sys.argv[0]} [host] [port]")
                sys.exit(1)

    tester = UDPTester()
    try:
        success = await tester.test_discovery(host=host, port=port)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
