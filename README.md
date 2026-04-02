# eink-dashboard

An AppDaemon app for Home Assistant that renders a power flow dashboard on a Waveshare 7.5" V2 e-paper display driven by an ESP32.

## Overview

The app generates a 480×800 portrait image every 60 seconds showing:

- **Power flow diagram** — solar, grid, system (Victron), home load, and battery with directional arrows indicating active flow
- **Energy today** — solar yield, grid import/export, and net consumption in kWh
- **Statuses** — grid lost alarm, cat box last emptied, pool pump state

The image is saved as both a human-readable PNG and a 1-bit BIN file. The ESP32 fetches the BIN over HTTP and writes it directly to the display buffer.

## Hardware

- Waveshare 7.5" e-Paper HAT V2 (800×480, UC8179 controller, model `7.50inV2alt` in ESPHome)
- ESP32

## Screenshot

![Dashboard screenshot](screenshot.png)

## Setup

### AppDaemon

Place `eink_dashboard.py` in your AppDaemon `apps/` directory and add to `apps.yaml`:

```yaml
eink_dashboard:
  module: eink_dashboard
  class: EinkDashboard
  out_dir: /homeassistant/www
  fonts_dir: /homeassistant/esphome/apps/dashboard/fonts
  system_label: "YOUR SYSTEM"
  render_interval: 60

  # Power sensors (all have defaults matching a Victron/MQTT setup)
  sensor_solar: sensor.victron_mqtt_system_0_system_dc_pv_power
  sensor_grid: sensor.victron_grid_power
  sensor_battery: sensor.victron_mqtt_system_0_system_dc_battery_power
  sensor_batt_soc: sensor.victron_mqtt_system_0_system_dc_battery_soc
  sensor_load: sensor.victron_consumption
  sensor_inverter_state: sensor.victron_mqtt_vebus_274_vebus_inverter_state

  # Daily energy sensors
  sensor_solar_today: sensor.victron_mqtt_solarcharger_288_solarcharger_yield_today
  sensor_import_daily: sensor.grid_import_daily
  sensor_export_daily: sensor.grid_export_daily

  # Status entities
  status_grid_lost: sensor.victron_mqtt_vebus_274_vebus_inverter_alarm_grid_lost
  status_cat_box: binary_sensor.magnet_cat_box_contact
  status_cat_box_dt: input_datetime.cat_box_last_emptied
  status_pool_pump: switch.poolpump1_relay
```

### Fonts

The app uses [Gotham Rounded](https://www.typography.com/fonts/gotham-rounded) (Bold + Book) and [Material Design Icons](https://github.com/Templarian/MaterialDesign-Webfont). Place the TTF files in the `fonts_dir`:

- `GothamRnd-Bold.ttf`
- `GothamRnd-Book.ttf`
- `materialdesignicons-webfont.ttf`

### Sensors

The following Home Assistant entities are expected:

| Entity | Description |
|--------|-------------|
| `sensor.victron_mqtt_system_0_system_dc_pv_power` | Solar power (W) |
| `sensor.victron_grid_power` | Grid power (W, positive=import) |
| `sensor.victron_mqtt_system_0_system_dc_battery_power` | Battery power (W, positive=discharge) |
| `sensor.victron_mqtt_system_0_system_dc_battery_soc` | Battery state of charge (%) |
| `sensor.victron_consumption` | Home load (W) |
| `sensor.victron_mqtt_vebus_274_vebus_inverter_state` | Inverter state label |
| `sensor.victron_mqtt_vebus_274_vebus_inverter_alarm_grid_lost` | Grid lost alarm |
| `sensor.victron_mqtt_solarcharger_288_solarcharger_yield_today` | Solar yield today (kWh) |
| `sensor.grid_import_daily` | Grid import today (kWh) |
| `sensor.grid_export_daily` | Grid export today (kWh) |
| `binary_sensor.magnet_cat_box_contact` | Cat box contact sensor |
| `input_datetime.cat_box_last_emptied` | Cat box last emptied timestamp |
| `switch.poolpump1_relay` | Pool pump switch |
