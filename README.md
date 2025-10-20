# Marstek Local API for Home Assistant

Home Assistant integration that talks directly to Marstek Venus C/D/E batteries over the official Local API. It delivers local-only telemetry, mode control, and fleet-wide aggregation without relying on the Marstek cloud.

[![Open this repository in HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jaapp&repository=ha-marstek-local-api&category=integration)

---

## 1. Enable the Local API

1. Make sure your batteries are on the latest firmware.
2. Use the [Marstek Venus Monitor](https://rweijnen.github.io/marstek-venus-monitor/latest/) tool to enable *Local API / Open API* on each device.
3. Note the UDP port (default `30000`) and confirm the devices respond on your LAN.

<img width="230" height="129" alt="afbeelding" src="https://github.com/user-attachments/assets/035de357-fbe6-4224-8249-03abb3078fa1" />

---

## 2. Install the Integration

### Via HACS
1. Open **HACS → Integrations → Custom repositories**.
2. Add `https://github.com/jaapp/ha-marstek-local-api` as an *Integration*.
3. Install **Marstek Local API** and restart Home Assistant.

### Manual copy
1. Drop `custom_components/marstek_local_api` into your Home Assistant `custom_components` folder.
2. Restart Home Assistant.

---

## 3. Add Devices

1. Go to **Settings → Devices & Services → Add Integration** and search for **Marstek Local API**.
2. The discovery step lists every battery it finds on your network. Select one device or pick **All devices** to build a single multi-battery entry.
3. If discovery misses a unit, choose **Manual IP entry** and provide the host/port you noted earlier.

After setup you can return to **Settings → Devices & Services → Marstek Local API → Configure** to:
- Rename devices, adjust the polling interval, or add/remove batteries to the existing multi-device entry.
- Trigger discovery again when new batteries join the network.

> **Important:** If you want all batteries to live under the same config entry (and keep the virtual **Marstek System** device), use the integration’s **Configure** button to add/remove batteries. The default Home Assistant “Add Device” button creates a brand-new config entry and a separate virtual system device.


<img width="442" height="442" alt="afbeelding" src="https://github.com/user-attachments/assets/45001642-412e-4c85-aace-b495639959ff" />

---

## 4. Single Entry vs. Virtual System Battery

- **Single-device entry**: created when you add an individual battery. Each entry exposes the battery’s entities and optional operating-mode controls.
- **Multi-device entry**: created when you pick *All devices* or add more batteries through the options flow. The integration keeps one config entry containing all members and exposes a synthetic device called **“Marstek System”**.  
  - The “system” device aggregates fleet metrics (total capacity, total grid import/export, combined state, etc.).  
  - Every physical battery still appears as its own device with per-pack entities.

<img width="1037" height="488" alt="afbeelding" src="https://github.com/user-attachments/assets/40bcb48a-02e6-4c85-85a4-73751265c6f8" />

---

## 5. Entities

| Category | Sensor (entity suffix) | Unit | Notes |
| --- | --- | --- | --- |
| **Battery** | `battery_soc` | % | State of charge |
|  | `battery_temperature` | °C | Pack temperature |
|  | `battery_capacity` | kWh | Remaining capacity |
|  | `battery_rated_capacity` | kWh | Rated pack capacity |
|  | `battery_available_capacity` | kWh | Estimated energy still available before full charge |
|  | `battery_voltage` | V | Pack voltage |
|  | `battery_current` | A | Pack current (positive = charge) |
| **Energy system (ES)** | `battery_power` | W | Pack power (positive = charge) |
|  | `battery_power_in` / `battery_power_out` | W | Split charge/discharge power |
|  | `battery_state` | text | `charging` / `discharging` / `idle` |
|  | `grid_power` | W | Grid import/export (positive = import) |
|  | `offgrid_power` | W | Off-grid load |
|  | `pv_power_es` | W | Solar production reported via ES |
|  | `total_pv_energy` | kWh | Lifetime PV energy |
|  | `total_grid_import` / `total_grid_export` | kWh | Lifetime grid counters |
|  | `total_load_energy` | kWh | Lifetime load energy |
| **Energy meter / CT** | `ct_phase_a_power`, `ct_phase_b_power`, `ct_phase_c_power` | W | Per-phase measurements (if CTs installed) |
|  | `ct_total_power` | W | CT aggregate |
| **Mode** | `operating_mode` | text | Auto / AI / Manual / Passive |
| **PV (Venus D only)** | `pv_power`, `pv_voltage`, `pv_current` | W / V / A | MPPT telemetry |
| **Network** | `wifi_rssi` | dBm | Wi-Fi signal |
|  | `wifi_ssid`, `wifi_ip`, `wifi_gateway`, `wifi_subnet`, `wifi_dns` | text | Wi-Fi configuration |
| **Device info** | `device_model`, `firmware_version`, `ble_mac`, `wifi_mac`, `device_ip` | text | Identification fields |
| **Diagnostics** | `last_message_received` | seconds | Time since the last successful poll |

Every sensor listed above also exists in an aggregated form under the **Marstek System** device whenever you manage multiple batteries together (prefixed with `system_`).

---

## 6. Services

| Service | Description | Parameters |
| --- | --- | --- |
| `marstek_local_api.request_data_sync` | Triggers an immediate poll of every configured coordinator. | Optional `entry_id` to refresh a specific config entry. |

You can call the service from **Developer Tools → Services** when you need an on-demand refresh after physical changes or troubleshooting.

---

## 7. Tips & Troubleshooting

- Keep the standard polling interval (60 s) unless you have explicit reasons to slow it down. Faster intervals than 60s can lead to the battery becoming unresponsive.
- If discovery fails, double-check that the Local API remains enabled after firmware upgrades and that UDP port `30000` is accessible from Home Assistant.
- For verbose logging, append the following to `configuration.yaml`:
  ```yaml
  logger:
    logs:
      custom_components.marstek_local_api: debug
  ```

### Standalone connectivity test

In the repository you’ll find `test/test_discovery.py`, a small CLI that reuses the integration code to probe connectivity outside Home Assistant:

```bash
cd test
python3 test_discovery.py              # broadcast discovery
python3 test_discovery.py 192.168.7.101  # target a specific battery
```

It discovers all reachable batteries, exercises every Local API method, and highlights network issues before you wire the devices into your HA instance.

---

## 8. Release Notes

Version **1.0.0** focusses on a stable multi-device experience:
- kWh-based energy reporting aligned with the Marstek UI.
- Options flow for renaming, adding, and removing devices after initial setup.
- `marstek_local_api.request_data_sync` service for immediate refreshes.
- Aggregated **Marstek System** device for fleet-wide KPIs.

Enjoy running your Marstek batteries locally! Pull requests and feedback are welcome.
