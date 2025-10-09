# Marstek Local API Integration for Home Assistant

---

## ⚠️⚠️⚠️ MASSIVE WARNING - READ THIS OR YOUR KITTEN GETS IT ⚠️⚠️⚠️

### 🚨 ALPHA/BETA SOFTWARE - COMPLETELY UNTESTED 🚨

**THIS INTEGRATION IS IN EARLY DEVELOPMENT AND HAS NOT BEEN TESTED IN PRODUCTION**

#### 🔥 PROCEED AT YOUR OWN RISK 🔥

- ❌ **NOT PRODUCTION READY**
- ❌ **NO GUARANTEES OF STABILITY**
- ❌ **MAY BREAK YOUR HOME ASSISTANT INSTANCE**
- ❌ **MAY CAUSE UNEXPECTED DEVICE BEHAVIOR**
- ❌ **COULD CRASH AND BURN AT ANY MOMENT**
- ❌ **WILL PROBABLY EAT YOUR KITTEN** 🐱
- ❌ **YOU HAVE BEEN WARNED**

**By installing this integration, you acknowledge:**
- ✅ This is experimental, untested software
- ✅ You accept 100% responsibility for anything that breaks
- ✅ You have backups of your Home Assistant configuration
- ✅ You won't blame anyone when things go sideways
- ✅ You understand your kittens are in mortal danger 🐱
- ✅ You're doing this for science/fun/stupidity

**Seriously, back up your shit before installing this.**

---

## What is this thing?

Home Assistant integration for Marstek energy storage systems using the official Local API (Rev 1.0). This integration provides comprehensive monitoring and control of Marstek Venus C/D/E devices without requiring cloud connectivity.

## Features

- **Local Control**: No cloud dependency, all communication is local via UDP
- **Comprehensive Monitoring**: Battery status, energy flows, grid/CT data, solar production
- **Operating Mode Control**: Switch between Auto, AI, Manual, and Passive modes
- **Energy Dashboard Integration**: Built-in support for Home Assistant Energy Dashboard
- **Automatic Discovery**: Finds Marstek devices on your network automatically
- **Tiered Polling**: Optimized 60 s / 300 s / 600 s refresh tiers per sensor category
- **Adaptive Retries**: UDP command retries with exponential backoff to avoid flooding the device

## Supported Devices

- Venus C
- Venus E
- Venus D (with additional PV sensors)

## Requirements

- Home Assistant 2024.1.0 or newer
- Marstek device with Local API enabled (configure in Marstek mobile app)
- Network connectivity to device

## Installation

⚠️ **Remember: This is alpha software. Back up your Home Assistant before installing!** ⚠️

### Option 1: HACS Custom Repository (Recommended for the Brave)

1. Open HACS in Home Assistant
2. Go to "Integrations"
3. Click the three dots in the top right and select "Custom repositories"
4. Add `https://github.com/jaapp/ha-marstek` and select "Integration" as the category
5. Find "Marstek Local API" in the list and click "Download"
6. Restart Home Assistant
7. Add the integration via Settings → Devices & Services

### Option 2: Manual Git Clone (For the Truly Fearless)

```bash
# SSH into your Home Assistant instance
cd /config/custom_components

# Clone the repository
git clone https://github.com/jaapp/ha-marstek.git marstek_local_api

# Restart Home Assistant
```

Then add the integration via Settings → Devices & Services → Add Integration → "Marstek Local API"

### Option 3: Manual Download

1. Download the latest release (or just grab the code)
2. Copy the `custom_components/marstek_local_api` directory to your Home Assistant `custom_components` directory
3. Restart Home Assistant
4. Add the integration via Settings → Devices & Services

## Configuration

### Enable Local API on Marstek Device

Before configuring the integration, you must enable the Local API feature in the Marstek mobile app:

1. Open the Marstek app
2. Navigate to your device settings
3. Enable "Local API" or "Open API"
4. Note the UDP port (default: 30000)

### Add Integration

1. In Home Assistant, go to Settings → Devices & Services
2. Click "+ Add Integration"
3. Search for "Marstek Local API"
4. The integration will automatically discover devices on your network
5. Select your device or choose "Manual IP entry" if discovery fails
6. Click "Submit"

## Entities

The integration creates the following entities:

### Sensors

| Category | Entities | Refresh cadence |
| --- | --- | --- |
| **Energy system (ES)** | Battery Power<br>Battery Power In / Out<br>Battery State<br>Grid Power<br>Off-Grid Power<br>Solar Power<br>Total PV / Grid / Load Energy | Every 60 s |
| **Battery** | State of Charge<br>Temperature<br>Remaining Capacity<br>Rated Capacity<br>Available Capacity | Every 60 s |
| **Operating mode** | Operating Mode | Every 300 s |
| **Energy meter / CT (EM)** | Phase A Power<br>Phase B Power<br>Phase C Power<br>Total Power | Every 300 s |
| **Solar (Venus D only)** | PV Power<br>PV Voltage<br>PV Current | Every 300 s |
| **Network** | WiFi Signal Strength<br>SSID<br>IP Address<br>Gateway<br>Subnet<br>DNS | Every 600 s |
| **Device** | Device Model<br>Firmware Version<br>Bluetooth MAC<br>WiFi MAC<br>Device IP | Every 600 s |
| **Diagnostics** | Last message age | Every 60 s |

### Binary Sensors

- Charging Enabled
- Discharging Enabled
- Bluetooth Connected
- CT Connected

### Select

- Operating Mode (Auto / AI / Manual / Passive)

## Energy Dashboard Setup

After installing the integration, configure Home Assistant's Energy Dashboard:

### 1. Grid Energy

Go to Settings → Dashboards → Energy → Add Grid Consumption

- **Grid Consumption:** `sensor.marstek_total_grid_import`
- **Grid Return:** `sensor.marstek_total_grid_export`

### 2. Solar Production

_(Venus D only)_

Go to Settings → Dashboards → Energy → Add Solar Production

- **Solar Production:** `sensor.marstek_total_pv_energy`

### 3. Battery Storage

Go to Settings → Dashboards → Energy → Add Battery System

Configure:
- **Energy going in to the battery:** `sensor.marstek_battery_power_in`
- **Energy going out of the battery:** `sensor.marstek_battery_power_out`

Home Assistant will automatically convert these power sensors to cumulative energy.

### 4. Load Energy (Optional)

Go to Settings → Dashboards → Energy → Add Individual Device

- **Home Consumption:** `sensor.marstek_total_load_energy`

## Diagnostics

Use Settings → System → Diagnostics → Marstek Local API to download a JSON snapshot with per-battery poll statistics (requested vs. observed interval, command latency, timeout counters, success rates, last message age). Share this file when reporting issues so we can see whether the device keeps up with the configured cadence.

## Firmware Version Handling

The integration automatically detects firmware version and applies appropriate value scaling:

- Firmware < 154: Uses legacy scaling factors
- Firmware >= 154: Uses new scaling factors

This ensures accurate readings across all firmware versions.

## Development Status

**Current State: ALPHA - Testing Phase**

What works (probably):
- ✅ UDP communication
- ✅ Device discovery
- ✅ Sensor entities
- ✅ Energy storage mode controls
- ✅ DHCP automatic detection

What's untested:
- ❓ Everything in a real production environment
- ❓ Long-term stability
- ❓ Edge cases
- ❓ Multi-device setups
- ❓ Different network configurations
- ❓ Kitten safety 🐱

What's missing:
- ❌ Comprehensive testing
- ❌ User feedback
- ❌ Bug fixes for issues we don't know about yet
- ❌ HACS validation
- ❌ Proper documentation (this README is a start)

## Known Limitations

- UDP communication can be unreliable on some networks
- No individual cell voltage monitoring (use BLE Gateway for this)
- Manual mode and Passive mode use default configurations (future versions will allow customization)
- **This is alpha software - expect bugs, crashes, and general weirdness**

## TODO

- Add a pytest-based Home Assistant test suite that exercises config flows, coordinators, entities, and the diagnostics handler.
- Refactor entities to use translation keys with localized strings and mark diagnostic sensors/selects with `entity_category`.
- Replace blocking subprocess calls in the UDP client with executor-friendly helpers to keep the event loop responsive.
- Polish documentation and UX (professional README tone, My Home Assistant link, configuration guides) before targeting Platinum quality.

## Troubleshooting

### Device Not Discovered

- Ensure Local API is enabled in Marstek app
- Check that device and Home Assistant are on the same network
- Try manual IP entry with device's IP address
- Verify firewall allows UDP port 30000

### Connection Issues

- Restart the Marstek device
- Restart Home Assistant
- Check network connectivity
- Ensure only one integration instance per device

### No Data Updates / Sensors Show "Unavailable"

- Check that the device is powered on
- Verify network connection
- Check Home Assistant logs for errors
- Try removing and re-adding the integration
- Enable debug logging (see below) to diagnose network issues
- Run the network diagnostic test (see below)

### Enable Debug Logging

To get detailed diagnostic information, add the following to your `configuration.yaml`:

```yaml
logger:
  default: info
  logs:
    custom_components.marstek_local_api: debug
    custom_components.marstek_local_api.api: debug
    custom_components.marstek_local_api.coordinator: debug
```

Then restart Home Assistant and check **Settings → System → Logs** for detailed debug output.

Debug logs will show:
- UDP socket connection details
- Command payloads being sent
- Responses received from the device
- Network errors and timeouts
- Handler registration and message routing

### Network Diagnostic Test

The integration includes a standalone network test script that you can run directly on your Home Assistant device:

```bash
# SSH into your Home Assistant instance
cd /config/custom_components/marstek_local_api

# Run the network test
python3 test_network.py
```

This test will:
- Discover devices on your network
- Test all API commands
- Display detailed network communication
- Help identify connectivity issues

The test script uses the same code as the integration, so if it works here but fails in HA, the issue is likely related to HA's networking environment.

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/jaapp/ha-marstek/issues).

## Credits

Based on:
- Official Marstek Device Open API Rev 1.0 documentation
- [homey-marstek-connector](https://github.com/jaapp/homey-marstek-connector) reference implementation

## License

This project is licensed under the MIT License.
### Update Cadence & Retries

- Default refresh interval is 60 seconds; you can choose any value between 60 s and 900 s in the integration options.
- Fast tier (power/energy telemetry) updates every cycle (~60 s), medium tier (battery/PV/mode/CT) every 5th cycle (~300 s), slow diagnostics every 10th cycle (~600 s).
- All UDP commands include a capped exponential backoff with jitter to drain stale packets and minimise queue pressure.
- **Diagnostics export**: download detailed polling/latency statistics via Home Assistant's diagnostics panel to verify the device keeps up with the configured cadence.
