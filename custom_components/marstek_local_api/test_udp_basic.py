#!/usr/bin/env python3
"""Basic UDP network test - no dependencies on HA modules.

Run this on your HA device to test UDP broadcast capability.
Usage: python3 test_udp_basic.py
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

    async def test_discovery(self, port=30000, timeout=10):
        """Test UDP broadcast discovery."""
        print(f"\n{'='*80}")
        print(f"UDP Network Diagnostic Test")
        print(f"{'='*80}\n")

        print(f"Test Parameters:")
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

        # Test broadcast addresses
        print(f"Step 2: Testing broadcast addresses...")
        broadcast_addrs = self._get_broadcast_addresses()
        print(f"  Found {len(broadcast_addrs)} broadcast address(es):")
        for addr in broadcast_addrs:
            print(f"    - {addr}")
        print()

        # Send discovery broadcasts
        print(f"Step 3: Sending discovery broadcasts...")
        discovery_msg = {
            "id": "test-discovery",
            "method": "Marstek.Scan",
            "params": {"id": 0}
        }
        msg_str = json.dumps(discovery_msg)

        for addr in broadcast_addrs:
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
            for msg, addr in self.responses:
                result = msg.get('result', {})
                print(f"Device from {addr[0]}:{addr[1]}:")
                print(f"  Model: {result.get('name', 'unknown')}")
                print(f"  IP: {result.get('ip', 'unknown')}")
                print(f"  MAC: {result.get('mac', 'unknown')}")
                print(f"  Firmware: v{result.get('ver', 'unknown')}")
                print()
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
    tester = UDPTester()
    try:
        success = await tester.test_discovery()
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
