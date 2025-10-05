# Marstek Local API - Test Suite

## Overview

This test suite validates the integration components in isolation without requiring a full Home Assistant installation.

## Test Scripts

### `test_discovery.py`

Standalone test script that:
- Discovers Marstek devices on the local network
- Tests all API methods (device info, WiFi, BLE, battery, energy system, etc.)
- Applies firmware-specific value scaling
- Calculates derived sensors (power in/out, battery state, available capacity)
- Displays all sensor data in a formatted terminal output

## Requirements

- Python 3.10+
- No additional dependencies required (uses only stdlib)
- Marstek device with Local API enabled

## Running Tests

### Quick Test

```bash
cd marstek-local-api
python3 test/test_discovery.py
```

### Expected Output

If devices are found:
```
================================================================================
Marstek Local API Integration - Standalone Test
================================================================================

Step 1: Discovering devices on network...
Broadcasting on port 30000...

✅ Found 1 device(s):

Device 1:
  Model:       VenusE
  IP Address:  192.168.1.10
  MAC:         AABBCCDDEEFF
  Firmware:    v111

================================================================================
Testing Device 1: VenusE (192.168.1.10)
================================================================================

📋 Device Information
--------------------------------------------------------------------------------
  Device Model:      VenusE
  Firmware Version:  111
  BLE MAC:           AABBCCDDEEFF
  WiFi MAC:          AABBCCDDEEFF
  WiFi Name:         MY_WIFI
  IP Address:        192.168.1.10

📶 WiFi Status
--------------------------------------------------------------------------------
  SSID:              MY_WIFI
  Signal Strength:   -45 dBm
  IP Address:        192.168.1.10
  Gateway:           192.168.1.1
  Subnet Mask:       255.255.255.0
  DNS Server:        192.168.1.1

🔋 Battery Status
--------------------------------------------------------------------------------
  State of Charge:        98%
  Temperature:            25.0°C
  Remaining Capacity:     2508.0 Wh
  Rated Capacity:         2560.0 Wh
  Available Capacity:     51.2 Wh
  Charging Enabled:       True
  Discharging Enabled:    True

⚡ Energy System Status
--------------------------------------------------------------------------------
  Battery Power:          -150 W
  Battery State:          discharging
  Battery Power In:       0 W
  Battery Power Out:      150 W
  Grid Power:             100 W
  Total Grid Import:      1607 Wh
  Total Grid Export:      844 Wh

[... more sections ...]
```

If no devices found:
```
❌ No devices found!

Troubleshooting:
  1. Ensure Marstek device is powered on
  2. Check Local API is enabled in Marstek app
  3. Verify device and computer are on same network
  4. Check firewall allows UDP port 30000
```

## How It Works

The test script:

1. **Loads Integration Components Directly**
   - Uses `importlib.util` to load integration modules without Home Assistant
   - Creates fake package structure in `sys.modules` to support relative imports
   - Mocks Home Assistant framework modules (homeassistant.core, etc.)
   - Loads actual integration code: `api.py`, `const.py`, `coordinator.py`, `sensor.py`
   - No Home Assistant installation required

2. **Discovers Devices**
   - Broadcasts UDP discovery message on port 30000
   - Waits 9 seconds for responses
   - Parses device information from responses

3. **Tests All API Methods**
   - Connects to each discovered device
   - Calls all API methods (GetDevice, WiFi, BLE, Battery, ES, EM, PV)
   - Uses **actual coordinator scaling logic** (no duplication)
   - Uses **actual sensor value_fn lambdas** for calculated sensors (no duplication)

4. **Displays Results**
   - Formatted terminal output with sections
   - Shows all sensor values with units
   - Handles missing/null values gracefully

## Testing Strategy

This test script validates:
- ✅ UDP communication and discovery protocol
- ✅ API method implementations
- ✅ Firmware version detection and value scaling (using real coordinator code)
- ✅ Calculated sensor logic (using real sensor definitions)
- ✅ Error handling and graceful degradation

**Key Principle**: The test imports and uses the actual integration code - no logic duplication. This ensures:
- Changes to scaling logic are automatically reflected in tests
- Changes to sensor calculations are automatically reflected in tests
- Tests validate the real implementation, not a reimplementation

## Integration with HACS

While this test runs standalone, it uses the **actual integration components** from:
- `custom_components/marstek_local_api/api.py` - UDP client and API methods
- `custom_components/marstek_local_api/const.py` - Constants and thresholds
- `custom_components/marstek_local_api/coordinator.py` - Firmware scaling logic
- `custom_components/marstek_local_api/sensor.py` - Sensor definitions and calculated values

This ensures the test validates the real code that will run in Home Assistant.

## Troubleshooting

### Import Errors

If you get import errors, ensure you're running from the repository root:
```bash
cd /path/to/marstek-local-api
python3 test/test_discovery.py
```

### No Devices Found

- Check device is powered on and connected to WiFi
- Verify Local API is enabled in Marstek mobile app
- Ensure computer and device are on same network
- Check firewall allows UDP port 30000

### Timeout Errors

- Discovery timeout is 9 seconds (configurable in code)
- API command timeout is 15 seconds per method
- Network congestion may cause delays

## Future Tests

Planned additions:
- Unit tests for value scaling logic
- Mock device responses for CI/CD
- Performance tests for concurrent device polling
- Integration tests with Home Assistant test framework
