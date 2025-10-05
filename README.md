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
- **Tiered Polling**: Optimized update intervals for different sensor types

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

**Battery**
- State of Charge (%)
- Temperature (°C)
- Remaining Capacity (Wh)
- Rated Capacity (Wh)
- Available Capacity (Wh)
- Battery Power (W)
- Battery Power In (W)
- Battery Power Out (W)
- Battery State (charging/discharging/idle)

**Energy System**
- Grid Power (W)
- Off-Grid Power (W)
- Solar Power (W)
- Total Solar Energy (Wh)
- Total Grid Import (Wh)
- Total Grid Export (Wh)
- Total Load Energy (Wh)

**Energy Meter / CT**
- Phase A Power (W)
- Phase B Power (W)
- Phase C Power (W)
- Total Power (W)

**Solar (Venus D only)**
- PV Power (W)
- PV Voltage (V)
- PV Current (A)

**Network**
- WiFi Signal Strength (dBm)
- WiFi SSID
- WiFi IP Address
- WiFi Gateway
- WiFi Subnet Mask
- WiFi DNS Server

**Device**
- Device Model
- Firmware Version
- Bluetooth MAC
- WiFi MAC
- Device IP Address
- Operating Mode
- Last Message Received (seconds)

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

## Polling Strategy

The integration uses an optimized tiered polling strategy to minimize network traffic:

- **Every 15s**: Energy System, Energy Meter (real-time power data)
- **Every 60s**: Battery, Solar, Operating Mode
- **Every 300s**: Device info, WiFi, Bluetooth (static data)

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

### No Data Updates

- Check that the device is powered on
- Verify network connection
- Check Home Assistant logs for errors
- Try removing and re-adding the integration

## Support

For issues and feature requests, please visit the [GitHub repository](https://github.com/jaapp/ha-marstek/issues).

## Credits

Based on:
- Official Marstek Device Open API Rev 1.0 documentation
- [homey-marstek-connector](https://github.com/jaapp/homey-marstek-connector) reference implementation

## License

This project is licensed under the MIT License.
