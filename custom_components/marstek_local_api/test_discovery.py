#!/usr/bin/env python3
"""Standalone test script for Marstek Local API integration.

Tests the integration components using actual integration code.
No logic duplication - imports and uses integration modules directly.

Usage:
  python3 test_discovery.py              # Auto-discovery
  python3 test_discovery.py 192.168.7.101  # Test specific IP
"""

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Callable


def load_module_from_file(module_name: str, file_path: Path):
    """Load a Python module directly from a file path."""
    spec = importlib.util.spec_from_file_location(module_name, file_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


# Get paths to integration modules - same directory as this script when in custom_components
integration_path = Path(__file__).parent

# Create a fake package structure to allow relative imports
package_name = "custom_components.marstek_local_api"

# Mock homeassistant modules that are imported by integration
# Create a mock HomeAssistant class and other required classes
class MockHomeAssistant:
    """Mock HomeAssistant class."""
    pass

class MockDataUpdateCoordinator:
    """Mock DataUpdateCoordinator class."""
    def __init__(self, hass, logger, name, update_interval):
        """Mock init that accepts coordinator parameters."""
        pass

class MockUpdateFailed(Exception):
    """Mock UpdateFailed exception."""
    pass

class MockSensorDeviceClass:
    """Mock SensorDeviceClass."""
    BATTERY = "battery"
    TEMPERATURE = "temperature"
    ENERGY_STORAGE = "energy_storage"
    POWER = "power"
    ENERGY = "energy"
    SIGNAL_STRENGTH = "signal_strength"
    DURATION = "duration"
    VOLTAGE = "voltage"
    CURRENT = "current"

class MockSensorEntity:
    """Mock SensorEntity class."""
    pass

@dataclass
class MockSensorEntityDescription:
    """Mock SensorEntityDescription class."""
    key: str
    name: str | None = None
    native_unit_of_measurement: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    value_fn: Callable[[dict], Any] | None = None
    available_fn: Callable[[dict], bool] | None = None

class MockSensorStateClass:
    """Mock SensorStateClass."""
    MEASUREMENT = "measurement"
    TOTAL_INCREASING = "total_increasing"

class MockConfigEntry:
    """Mock ConfigEntry class."""
    pass

class MockDeviceInfo:
    """Mock DeviceInfo class."""
    pass

class MockCoordinatorEntity:
    """Mock CoordinatorEntity class."""
    pass

class MockAddEntitiesCallback:
    """Mock AddEntitiesCallback class."""
    pass

# Create mock modules
homeassistant_core = type(sys)('homeassistant.core')
homeassistant_core.HomeAssistant = MockHomeAssistant

homeassistant_helpers_update_coordinator = type(sys)('homeassistant.helpers.update_coordinator')
homeassistant_helpers_update_coordinator.DataUpdateCoordinator = MockDataUpdateCoordinator
homeassistant_helpers_update_coordinator.UpdateFailed = MockUpdateFailed
homeassistant_helpers_update_coordinator.CoordinatorEntity = MockCoordinatorEntity

homeassistant_components_sensor = type(sys)('homeassistant.components.sensor')
homeassistant_components_sensor.SensorDeviceClass = MockSensorDeviceClass
homeassistant_components_sensor.SensorEntity = MockSensorEntity
homeassistant_components_sensor.SensorEntityDescription = MockSensorEntityDescription
homeassistant_components_sensor.SensorStateClass = MockSensorStateClass

homeassistant_config_entries = type(sys)('homeassistant.config_entries')
homeassistant_config_entries.ConfigEntry = MockConfigEntry

homeassistant_const = type(sys)('homeassistant.const')
homeassistant_const.PERCENTAGE = "%"
homeassistant_const.UnitOfElectricCurrent = type('UnitOfElectricCurrent', (), {'AMPERE': 'A'})()
homeassistant_const.UnitOfElectricPotential = type('UnitOfElectricPotential', (), {'VOLT': 'V'})()
homeassistant_const.UnitOfEnergy = type('UnitOfEnergy', (), {'WATT_HOUR': 'Wh'})()
homeassistant_const.UnitOfPower = type('UnitOfPower', (), {'WATT': 'W'})()
homeassistant_const.UnitOfTemperature = type('UnitOfTemperature', (), {'CELSIUS': '°C'})()
homeassistant_const.UnitOfTime = type('UnitOfTime', (), {'SECONDS': 's'})()

homeassistant_helpers_entity = type(sys)('homeassistant.helpers.entity')
homeassistant_helpers_entity.DeviceInfo = MockDeviceInfo

homeassistant_helpers_entity_platform = type(sys)('homeassistant.helpers.entity_platform')
homeassistant_helpers_entity_platform.AddEntitiesCallback = MockAddEntitiesCallback

# Register mock modules
sys.modules['homeassistant'] = type(sys)('homeassistant')
sys.modules['homeassistant.core'] = homeassistant_core
sys.modules['homeassistant.helpers'] = type(sys)('homeassistant.helpers')
sys.modules['homeassistant.helpers.update_coordinator'] = homeassistant_helpers_update_coordinator
sys.modules['homeassistant.components'] = type(sys)('homeassistant.components')
sys.modules['homeassistant.components.sensor'] = homeassistant_components_sensor
sys.modules['homeassistant.config_entries'] = homeassistant_config_entries
sys.modules['homeassistant.const'] = homeassistant_const
sys.modules['homeassistant.helpers.entity'] = homeassistant_helpers_entity
sys.modules['homeassistant.helpers.entity_platform'] = homeassistant_helpers_entity_platform

# Load integration modules in dependency order
const = load_module_from_file(f"{package_name}.const", integration_path / "const.py")
api_module = load_module_from_file(f"{package_name}.api", integration_path / "api.py")
coordinator_module = load_module_from_file(f"{package_name}.coordinator", integration_path / "coordinator.py")
sensor_module = load_module_from_file(f"{package_name}.sensor", integration_path / "sensor.py")

# Extract what we need
MarstekUDPClient = api_module.MarstekUDPClient
DEFAULT_PORT = const.DEFAULT_PORT
DEVICE_MODEL_VENUS_D = const.DEVICE_MODEL_VENUS_D
FIRMWARE_THRESHOLD = const.FIRMWARE_THRESHOLD
SENSOR_TYPES = sensor_module.SENSOR_TYPES


class MockHass:
    """Mock Home Assistant object for testing."""

    def __init__(self):
        self.data = {}


# No MockCoordinator needed - we use the real coordinator from the integration


def format_value(value, unit=""):
    """Format value with unit for display."""
    if value is None:
        return "N/A"
    if isinstance(value, (int, float)):
        return f"{value}{unit}"
    return str(value)


async def discover_and_test():
    """Discover devices and test all API methods."""
    print("=" * 80)
    print("Marstek Local API Integration - Standalone Test")
    print("=" * 80)
    print()

    # Create mock hass object
    hass = MockHass()

    # Create UDP client for discovery
    print("Step 1: Discovering devices on network...")
    print(f"Broadcasting on port {DEFAULT_PORT}...")
    print()

    api = MarstekUDPClient(hass, port=DEFAULT_PORT)

    try:
        await api.connect()
        devices = await api.discover_devices(timeout=9)

        if not devices:
            print("❌ No devices found!")
            print()
            print("Troubleshooting:")
            print("  1. Ensure Marstek device is powered on")
            print("  2. Check Local API is enabled in Marstek app")
            print("  3. Verify device and computer are on same network")
            print("  4. Check firewall allows UDP port 30000")
            return

        print(f"✅ Found {len(devices)} device(s):")
        print()

        for i, device in enumerate(devices, 1):
            print(f"Device {i}:")
            print(f"  Model:       {device['name']}")
            print(f"  IP Address:  {device['ip']}")
            print(f"  MAC:         {device['mac']}")
            print(f"  Firmware:    v{device['firmware']}")
            print()

        # Test each device (reuse same API client, just set the host)
        for device_idx, device in enumerate(devices, 1):
            print("=" * 80)
            print(f"Testing Device {device_idx}: {device['name']} ({device['ip']})")
            print("=" * 80)
            print()

            # Reuse the discovery client by setting the host
            api.host = device['ip']
            firmware = device['firmware']
            is_venus_d = device['name'] == DEVICE_MODEL_VENUS_D

            # Test 1: Device Info
            print("📋 Device Information")
            print("-" * 80)
            await asyncio.sleep(1.0)  # Delay before first API call
            device_info = await api.get_device_info()
            if device_info:
                print(f"  Device Model:      {device_info.get('device', 'N/A')}")
                print(f"  Firmware Version:  {device_info.get('ver', 'N/A')}")
                print(f"  BLE MAC:           {device_info.get('ble_mac', 'N/A')}")
                print(f"  WiFi MAC:          {device_info.get('wifi_mac', 'N/A')}")
                print(f"  WiFi Name:         {device_info.get('wifi_name', 'N/A')}")
                print(f"  IP Address:        {device_info.get('ip', 'N/A')}")
            else:
                print("  ⚠️  Failed to get device info")
            print()

            # Test 2: WiFi Status
            await asyncio.sleep(1.0)  # Delay between API calls
            print("📶 WiFi Status")
            print("-" * 80)
            wifi_status = await api.get_wifi_status()
            if wifi_status:
                print(f"  SSID:              {wifi_status.get('ssid', 'N/A')}")
                print(f"  Signal Strength:   {format_value(wifi_status.get('rssi'), ' dBm')}")
                print(f"  IP Address:        {wifi_status.get('sta_ip', 'N/A')}")
                print(f"  Gateway:           {wifi_status.get('sta_gate', 'N/A')}")
                print(f"  Subnet Mask:       {wifi_status.get('sta_mask', 'N/A')}")
                print(f"  DNS Server:        {wifi_status.get('sta_dns', 'N/A')}")
            else:
                print("  ⚠️  Failed to get WiFi status")
            print()

            # Test 3: Bluetooth Status
            await asyncio.sleep(1.0)  # Delay between API calls
            print("🔵 Bluetooth Status")
            print("-" * 80)
            ble_status = await api.get_ble_status()
            if ble_status:
                print(f"  State:             {ble_status.get('state', 'N/A')}")
                print(f"  MAC Address:       {ble_status.get('ble_mac', 'N/A')}")
            else:
                print("  ⚠️  Failed to get Bluetooth status")
            print()

            # Create real coordinator instance to use actual _scale_value logic
            # Create minimal coordinator with real scaling logic
            coordinator = coordinator_module.MarstekDataUpdateCoordinator(
                hass=hass,
                api=api,
                device_name=device['name'],
                firmware_version=firmware,
                device_model=device['name'],
                scan_interval=15  # Doesn't matter for testing
            )

            # Test 4: Battery Status
            await asyncio.sleep(1.0)  # Delay between API calls
            print("🔋 Battery Status")
            print("-" * 80)
            battery_status = await api.get_battery_status()
            if battery_status:
                # Use real coordinator scaling logic
                bat_temp = coordinator._scale_value(battery_status.get('bat_temp'), 'bat_temp')
                bat_capacity = coordinator._scale_value(battery_status.get('bat_capacity'), 'bat_capacity')

                soc = battery_status.get('soc')
                rated_capacity = battery_status.get('rated_capacity')

                print(f"  State of Charge:        {format_value(soc, '%')}")
                print(f"  Temperature:            {format_value(bat_temp, '°C')}")
                print(f"  Remaining Capacity:     {format_value(bat_capacity, ' Wh')}")
                print(f"  Rated Capacity:         {format_value(rated_capacity, ' Wh')}")
                print(f"  Charging Enabled:       {battery_status.get('charg_flag', False)}")
                print(f"  Discharging Enabled:    {battery_status.get('dischrg_flag', False)}")
            else:
                print("  ⚠️  Failed to get battery status")
            print()

            # Test 5: Energy System Status
            await asyncio.sleep(1.0)  # Delay between API calls
            print("⚡ Energy System Status")
            print("-" * 80)
            es_status = await api.get_es_status()
            if es_status:
                # Use real coordinator scaling logic
                bat_power = coordinator._scale_value(es_status.get('bat_power'), 'bat_power')
                total_grid_input = coordinator._scale_value(es_status.get('total_grid_input_energy'), 'total_grid_input_energy')
                total_grid_output = coordinator._scale_value(es_status.get('total_grid_output_energy'), 'total_grid_output_energy')
                total_load = coordinator._scale_value(es_status.get('total_load_energy'), 'total_load_energy')

                # Build data dict like the real coordinator does - only add keys if data exists
                data = {
                    'es': {
                        **es_status,
                        'bat_power': bat_power,
                        'total_grid_input_energy': total_grid_input,
                        'total_grid_output_energy': total_grid_output,
                        'total_load_energy': total_load,
                    }
                }
                # Only add battery data if we have it
                if battery_status:
                    data['battery'] = battery_status

                # Use real sensor definitions for calculated values
                sensor_map = {desc.key: desc for desc in SENSOR_TYPES}
                bat_power_in = sensor_map['battery_power_in'].value_fn(data)
                bat_power_out = sensor_map['battery_power_out'].value_fn(data)
                bat_state = sensor_map['battery_state'].value_fn(data)
                # Only calculate available capacity if we have battery data
                available_capacity = sensor_map['battery_available_capacity'].value_fn(data) if battery_status else None

                print(f"  Battery SOC:            {format_value(es_status.get('bat_soc'), '%')}")
                print(f"  Battery Capacity:       {format_value(es_status.get('bat_cap'), ' Wh')}")
                print(f"  Battery Power:          {format_value(bat_power, ' W')}")
                print(f"  Battery State:          {bat_state}")
                print(f"  Battery Power In:       {format_value(bat_power_in, ' W')}")
                print(f"  Battery Power Out:      {format_value(bat_power_out, ' W')}")
                print(f"  Available Capacity:     {format_value(available_capacity, ' Wh')}")
                print(f"  Grid Power:             {format_value(es_status.get('ongrid_power'), ' W')}")
                print(f"  Off-Grid Power:         {format_value(es_status.get('offgrid_power'), ' W')}")
                print(f"  Solar Power:            {format_value(es_status.get('pv_power'), ' W')}")
                print(f"  Total Solar Energy:     {format_value(es_status.get('total_pv_energy'), ' Wh')}")
                print(f"  Total Grid Import:      {format_value(total_grid_input, ' Wh')}")
                print(f"  Total Grid Export:      {format_value(total_grid_output, ' Wh')}")
                print(f"  Total Load Energy:      {format_value(total_load, ' Wh')}")
            else:
                print("  ⚠️  Failed to get energy system status")
            print()

            # Test 6: Operating Mode
            await asyncio.sleep(1.0)  # Delay between API calls
            print("⚙️  Operating Mode")
            print("-" * 80)
            mode_status = await api.get_es_mode()
            if mode_status:
                print(f"  Current Mode:           {mode_status.get('mode', 'N/A')}")
                print(f"  Grid Power:             {format_value(mode_status.get('ongrid_power'), ' W')}")
                print(f"  Off-Grid Power:         {format_value(mode_status.get('offgrid_power'), ' W')}")
                print(f"  Battery SOC:            {format_value(mode_status.get('bat_soc'), '%')}")
            else:
                print("  ⚠️  Failed to get operating mode")
            print()

            # Test 7: Energy Meter (CT)
            await asyncio.sleep(1.0)  # Delay between API calls
            print("📊 Energy Meter (CT) Status")
            print("-" * 80)
            em_status = await api.get_em_status()
            if em_status:
                ct_state = em_status.get('ct_state')
                ct_connected = ct_state == 1
                print(f"  CT Connected:           {ct_connected}")
                if ct_connected:
                    print(f"  Phase A Power:          {format_value(em_status.get('a_power'), ' W')}")
                    print(f"  Phase B Power:          {format_value(em_status.get('b_power'), ' W')}")
                    print(f"  Phase C Power:          {format_value(em_status.get('c_power'), ' W')}")
                    print(f"  Total Power:            {format_value(em_status.get('total_power'), ' W')}")
                else:
                    print("  (No CT connected)")
            else:
                print("  ⚠️  Failed to get energy meter status")
            print()

            # Test 8: PV Status (Venus D only)
            if is_venus_d:
                await asyncio.sleep(1.0)  # Delay between API calls
                print("☀️  Solar PV Status (Venus D)")
                print("-" * 80)
                pv_status = await api.get_pv_status()
                if pv_status:
                    print(f"  PV Power:               {format_value(pv_status.get('pv_power'), ' W')}")
                    print(f"  PV Voltage:             {format_value(pv_status.get('pv_voltage'), ' V')}")
                    print(f"  PV Current:             {format_value(pv_status.get('pv_current'), ' A')}")
                else:
                    print("  ⚠️  Failed to get PV status")
                print()

    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
    finally:
        await api.disconnect()

    print()
    print("=" * 80)
    print("Test Complete!")
    print("=" * 80)


def main():
    """Run the test."""
    try:
        asyncio.run(discover_and_test())
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        sys.exit(0)


if __name__ == "__main__":
    main()
