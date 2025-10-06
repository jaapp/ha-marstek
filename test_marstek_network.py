#!/usr/bin/env python3
"""Standalone Marstek network test - can be run from anywhere.

Usage:
  python3 test_marstek_network.py                    # Auto-discovery
  python3 test_marstek_network.py 192.168.7.101      # Direct IP
"""

import asyncio
import json
import socket
import sys
from datetime import datetime


class MarstekTester:
    def __init__(self):
        self.transport = None
        self.protocol = None
        self.responses = []

    async def test(self, host=None, port=30000, timeout=10):
        """Test Marstek device connectivity."""
        print(f"\n{'='*80}")
        print(f"Marstek Network Test")
        print(f"{'='*80}\n")

        print(f"Parameters:")
        print(f"  Mode: {'Direct IP' if host else 'Broadcast Discovery'}")
        if host:
            print(f"  Target: {host}")
        print(f"  Port: {port}")
        print(f"  Time: {datetime.now()}\n")

        # System info
        hostname = socket.gethostname()
        try:
            local_ip = socket.gethostbyname(hostname)
        except:
            local_ip = "unknown"

        print(f"System:")
        print(f"  Hostname: {hostname}")
        print(f"  Local IP: {local_ip}\n")

        # Create UDP socket
        print(f"Creating UDP socket...")
        try:
            loop = asyncio.get_event_loop()

            class Protocol(asyncio.DatagramProtocol):
                def __init__(self, tester):
                    self.tester = tester

                def datagram_received(self, data, addr):
                    try:
                        msg = json.loads(data.decode())
                        print(f"  ← Response from {addr[0]}:{addr[1]}")
                        self.tester.responses.append((msg, addr))
                    except:
                        pass

            self.transport, self.protocol = await loop.create_datagram_endpoint(
                lambda: Protocol(self),
                local_addr=("0.0.0.0", port),
                allow_broadcast=True,
                reuse_port=True,
            )

            sock = self.transport.get_extra_info('socket')
            print(f"  ✓ Bound to {sock.getsockname()[0]}:{sock.getsockname()[1]}\n")

        except Exception as e:
            print(f"  ✗ Failed: {e}\n")
            return False

        # Send discovery
        print(f"Sending discovery...")
        discovery = {
            "id": "test-scan",
            "method": "Marstek.Scan",
            "params": {"id": 0}
        }

        if host:
            targets = [host]
        else:
            targets = ["255.255.255.255"]
            # Try to calculate /24 broadcast too
            try:
                parts = local_ip.split('.')
                if len(parts) == 4 and not local_ip.startswith('127.'):
                    targets.append(f"{parts[0]}.{parts[1]}.{parts[2]}.255")
            except:
                pass

        for target in targets:
            self.transport.sendto(json.dumps(discovery).encode(), (target, port))
            print(f"  → Sent to {target}:{port}")

        print(f"\nWaiting {timeout}s for responses...\n")
        await asyncio.sleep(timeout)

        # Process responses
        devices = []
        for msg, addr in self.responses:
            if msg.get('id') == 'test-scan' and 'result' in msg:
                result = msg['result']
                devices.append((result, addr))

        if devices:
            print(f"{'='*80}")
            print(f"Found {len(devices)} device(s)")
            print(f"{'='*80}\n")

            for result, addr in devices:
                print(f"Device:")
                print(f"  Model: {result.get('name', 'unknown')}")
                print(f"  IP: {result.get('ip', 'unknown')}")
                print(f"  MAC: {result.get('mac', 'unknown')}")
                print(f"  Firmware: v{result.get('ver', 'unknown')}")
                print(f"  Responded from: {addr[0]}:{addr[1]}\n")

                # Test commands if we have a specific host
                if host and result.get('ip') == host:
                    await self.test_commands(host, port)

            return True
        else:
            print(f"{'='*80}")
            print(f"No devices found")
            print(f"{'='*80}\n")
            if host:
                print(f"Cannot reach {host} - check:")
                print(f"  1. Device is powered on")
                print(f"  2. Local API enabled in Marstek app")
                print(f"  3. Network routing (is {host} reachable?)")
                print(f"  4. Firewall rules\n")
            return False

    async def test_commands(self, host, port):
        """Test API commands."""
        print(f"{'='*80}")
        print(f"Testing API Commands")
        print(f"{'='*80}\n")

        commands = [
            ("Marstek.GetDevice", "Device Info"),
            ("ES.GetStatus", "Energy Status"),
            ("Bat.GetStatus", "Battery Status"),
        ]

        for method, desc in commands:
            print(f"{desc} ({method})...")
            msg_id = f"test-{method.replace('.', '-').lower()}"
            payload = {
                "id": msg_id,
                "method": method,
                "params": {"id": 0}
            }

            self.responses.clear()
            self.transport.sendto(json.dumps(payload).encode(), (host, port))

            await asyncio.sleep(3)

            success = False
            for msg, addr in self.responses:
                if msg.get('id') == msg_id and 'result' in msg:
                    result = msg['result']
                    keys = list(result.keys())[:5] if isinstance(result, dict) else []
                    print(f"  ✓ Response: {', '.join(keys)}{'...' if len(result) > 5 else ''}")
                    success = True
                    break

            if not success:
                print(f"  ✗ No response")
            print()

    async def close(self):
        if self.transport:
            self.transport.close()


async def main():
    host = sys.argv[1] if len(sys.argv) > 1 else None
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 30000

    tester = MarstekTester()
    try:
        success = await tester.test(host=host, port=port)
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\nInterrupted")
        sys.exit(1)
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        await tester.close()


if __name__ == "__main__":
    asyncio.run(main())
