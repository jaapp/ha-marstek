#!/usr/bin/env python3
"""Read Marstek sensor data directly - for HA terminal use.

Usage from HA SSH:
  cd /config
  python3 read_sensors.py 192.168.7.101
"""

import asyncio
import json
import sys


async def read_marstek_data(host, port=30000):
    """Read all sensor data from Marstek device."""

    class Protocol(asyncio.DatagramProtocol):
        def __init__(self):
            self.responses = {}
            self.events = {}

        def datagram_received(self, data, addr):
            try:
                msg = json.loads(data.decode())
                msg_id = msg.get('id')
                if msg_id and msg_id in self.events:
                    self.responses[msg_id] = msg.get('result')
                    self.events[msg_id].set()
            except:
                pass

    # Create UDP client with ephemeral port (let OS choose)
    loop = asyncio.get_event_loop()
    protocol = Protocol()

    transport, _ = await loop.create_datagram_endpoint(
        lambda: protocol,
        local_addr=("0.0.0.0", 0),  # Ephemeral port
        allow_broadcast=True,
    )

    async def send_command(method, desc):
        """Send command and wait for response."""
        msg_id = f"read-{method.replace('.', '-').lower()}"
        payload = {
            "id": msg_id,
            "method": method,
            "params": {"id": 0}
        }

        event = asyncio.Event()
        protocol.events[msg_id] = event

        # Send command
        transport.sendto(json.dumps(payload).encode(), (host, port))

        # Wait for response (5s timeout)
        try:
            await asyncio.wait_for(event.wait(), timeout=5.0)
            return protocol.responses.get(msg_id)
        except asyncio.TimeoutError:
            print(f"  ⚠️  {desc}: No response (timeout)")
            return None
        finally:
            protocol.events.pop(msg_id, None)

    print(f"Reading Marstek data from {host}:{port}\n")
    print("="*80)

    # Device Info
    print("\n📋 DEVICE INFO")
    print("-"*80)
    result = await send_command("Marstek.GetDevice", "Device Info")
    if result:
        print(f"  Model: {result.get('device', 'N/A')}")
        print(f"  Firmware: v{result.get('ver', 'N/A')}")
        print(f"  IP: {result.get('ip', 'N/A')}")
        print(f"  WiFi MAC: {result.get('wifi_mac', 'N/A')}")
        print(f"  BLE MAC: {result.get('ble_mac', 'N/A')}")

    # Battery Status
    print("\n🔋 BATTERY STATUS")
    print("-"*80)
    result = await send_command("Bat.GetStatus", "Battery Status")
    if result:
        print(f"  State of Charge: {result.get('soc', 'N/A')}%")
        print(f"  Temperature: {result.get('bat_temp', 'N/A')/10:.1f}°C")
        print(f"  Capacity: {result.get('bat_capacity', 'N/A')/100:.2f} Wh")
        print(f"  Rated Capacity: {result.get('rated_capacity', 'N/A')} Wh")
        print(f"  Charging: {result.get('charg_flag', False)}")
        print(f"  Discharging: {result.get('dischrg_flag', False)}")

    # Energy System Status
    print("\n⚡ ENERGY SYSTEM")
    print("-"*80)
    result = await send_command("ES.GetStatus", "Energy System")
    if result:
        bat_power = result.get('bat_power', 0) / 10.0
        print(f"  Battery SOC: {result.get('bat_soc', 'N/A')}%")
        print(f"  Battery Power: {bat_power:.1f} W")
        print(f"  Battery State: {'charging' if bat_power > 0 else 'discharging' if bat_power < 0 else 'idle'}")
        print(f"  Grid Power: {result.get('ongrid_power', 'N/A')} W")
        print(f"  Solar Power: {result.get('pv_power', 'N/A')} W")
        print(f"  Total Solar: {result.get('total_pv_energy', 'N/A')} Wh")
        print(f"  Grid Import: {result.get('total_grid_input_energy', 'N/A')/100:.2f} Wh")
        print(f"  Grid Export: {result.get('total_grid_output_energy', 'N/A')/100:.2f} Wh")

    # Energy Meter (CT)
    print("\n📊 ENERGY METER (CT)")
    print("-"*80)
    result = await send_command("EM.GetStatus", "Energy Meter")
    if result:
        ct_connected = result.get('ct_state') == 1
        print(f"  CT Connected: {ct_connected}")
        if ct_connected:
            print(f"  Phase A: {result.get('a_power', 'N/A')} W")
            print(f"  Phase B: {result.get('b_power', 'N/A')} W")
            print(f"  Phase C: {result.get('c_power', 'N/A')} W")
            print(f"  Total: {result.get('total_power', 'N/A')} W")
        else:
            print(f"  (No CT connected)")

    # Operating Mode
    print("\n⚙️  OPERATING MODE")
    print("-"*80)
    result = await send_command("ES.GetMode", "Operating Mode")
    if result:
        print(f"  Mode: {result.get('mode', 'N/A')}")

    print("\n" + "="*80)
    print("Done!\n")

    transport.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python3 read_sensors.py <device_ip> [port]")
        print("Example: python3 read_sensors.py 192.168.7.101")
        sys.exit(1)

    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 30000

    try:
        asyncio.run(read_marstek_data(host, port))
    except KeyboardInterrupt:
        print("\nInterrupted")
    except Exception as e:
        print(f"\nError: {e}")
        import traceback
        traceback.print_exc()
