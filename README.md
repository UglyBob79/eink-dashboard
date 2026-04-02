# eink-dashboard

An AppDaemon app for Home Assistant that renders a power flow dashboard as a 480×800 image for any e-paper display, for instance a Waveshare 7.5" V2 driven by an ESP32.

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
  fonts_dir: /path/to/fonts
  system_label: "YOUR SYSTEM"
  render_interval: 60

  # Power sensors
  sensor_solar: sensor.your_solar_power
  sensor_grid: sensor.your_grid_power          # positive=import, negative=export
  sensor_battery: sensor.your_battery_power    # positive=discharge
  sensor_batt_soc: sensor.your_battery_soc
  sensor_load: sensor.your_home_load
  sensor_inverter_state: sensor.your_inverter_state

  # Daily energy strip (optional, omit or set false to hide)
  show_energy_today: true
  sensor_solar_today: sensor.your_solar_today
  sensor_import_daily: sensor.your_grid_import_daily
  sensor_export_daily: sensor.your_grid_export_daily

  # Status entities
  status_grid_lost: sensor.your_grid_lost_alarm  # state "Alarm" = lost
  status_cat_box: binary_sensor.your_cat_box
  status_cat_box_dt: input_datetime.your_cat_box_last_emptied
  status_pool_pump: switch.your_pool_pump
```

All entity keys are required. If any entity is missing or unavailable at render time, an error screen listing the affected entities is shown on the display instead.

### Fonts

The app uses [Gotham Rounded](https://www.typography.com/fonts/gotham-rounded) (Bold + Book) and [Material Design Icons](https://github.com/Templarian/MaterialDesign-Webfont). Place the TTF files in the `fonts_dir`:

- `GothamRnd-Bold.ttf`
- `GothamRnd-Book.ttf`
- `materialdesignicons-webfont.ttf`
