# PyEnvertech2MQTT

Polls Envertech microinverter(s) over the local network and publishes the data to MQTT. Runs as a Docker container.

Supports:
- Multiple inverters
- Per-panel metrics (voltage, power, energy, temperature, grid voltage, frequency)
- Combined totals across all inverters
- Home Assistant MQTT auto-discovery
- Node-RED → InfluxDB integration

## Protocol

Communicates directly with the inverter's local TCP interface (default port **14889**) using the protocol reverse-engineered by [Kaiserdragon2/envertech_local_python](https://github.com/Kaiserdragon2/envertech_local_python). No cloud connection required.

The inverter's serial number (8-character hex string, e.g. `ABCD1234`) is printed on the device label and is required for the TCP framing.

---

## Quick Start — Single Inverter (env vars)

```yaml
# docker-compose.yml
services:
  envertech2mqtt:
    image: ghcr.io/OWNER/pyenvertech2mqtt:latest
    restart: unless-stopped
    environment:
      INVERTER_IP: "192.168.1.100"
      INVERTER_SN: "ABCD1234"
      MQTT_HOST: "192.168.1.10"
      MQTT_TOPIC: "envertech"
      POLL_INTERVAL: "30"
      HA_DISCOVERY: "true"
```

## Multi-Inverter Setup (config file)

Copy `config.example.yml` to `config.yml`, fill in your settings, then mount it:

```yaml
services:
  envertech2mqtt:
    image: ghcr.io/OWNER/pyenvertech2mqtt:latest
    restart: unless-stopped
    volumes:
      - ./config.yml:/app/config.yml:ro
    environment:
      CONFIG_FILE: "/app/config.yml"
```

---

## Configuration Reference

### Environment Variables

| Variable | Default | Description |
|---|---|---|
| `INVERTER_IP` | — | Inverter IP address (required if no config.yml) |
| `INVERTER_SN` | — | Inverter serial number, 8-char hex (required if no config.yml) |
| `INVERTER_NAME` | — | Optional display name |
| `INVERTER_PORT` | `14889` | TCP port |
| `MQTT_HOST` | `localhost` | MQTT broker address |
| `MQTT_PORT` | `1883` | MQTT broker port |
| `MQTT_USERNAME` | — | MQTT username (optional) |
| `MQTT_PASSWORD` | — | MQTT password (optional) |
| `MQTT_TOPIC` | `envertech` | Base MQTT topic |
| `POLL_INTERVAL` | `30` | Seconds between polls |
| `HA_DISCOVERY` | `true` | Publish Home Assistant discovery payloads |
| `HA_DISCOVERY_PREFIX` | `homeassistant` | HA discovery topic prefix |
| `LOG_LEVEL` | `INFO` | Log level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `CONFIG_FILE` | `config.yml` | Path to YAML config file |

### config.yml

See [`config.example.yml`](config.example.yml) for a fully documented example.

---

## MQTT Topics

### Per-Inverter

| Topic | Value |
|---|---|
| `envertech/{sn}/status` | JSON with all data (see below) |
| `envertech/{sn}/total_power` | Total AC power output in W |
| `envertech/{sn}/total_energy` | Total energy produced in Wh |
| `envertech/{sn}/panel_count` | Number of panels/MIs |
| `envertech/{sn}/firmware_version` | Firmware version string |
| `envertech/{sn}/panel/{i}/status` | JSON with per-panel data |
| `envertech/{sn}/panel/{i}/power` | Panel DC power in W |
| `envertech/{sn}/panel/{i}/energy` | Panel energy in Wh |
| `envertech/{sn}/panel/{i}/input_voltage` | Panel DC input voltage in V |
| `envertech/{sn}/panel/{i}/grid_voltage` | Grid AC voltage in V |
| `envertech/{sn}/panel/{i}/frequency` | Grid frequency in Hz |
| `envertech/{sn}/panel/{i}/temperature` | MI temperature in °C |
| `envertech/{sn}/panel/{i}/mi_sn` | Panel/MI serial number |

### Combined (all inverters summed)

| Topic | Value |
|---|---|
| `envertech/combined/status` | JSON |
| `envertech/combined/total_power` | Sum of all inverter power in W |
| `envertech/combined/total_energy` | Sum of all inverter energy in Wh |
| `envertech/combined/panel_count` | Total panel count across all inverters |

### Example status JSON (`envertech/{sn}/status`)

```json
{
  "total_power": 450.5,
  "total_energy": 1234.56,
  "panel_count": 2,
  "firmware_version": "1/3",
  "panel_0": {
    "mi_sn": "ab12cd34",
    "input_voltage": 38.2,
    "power": 225.1,
    "energy": 617.3,
    "temperature": 42.5,
    "grid_voltage": 231.4,
    "frequency": 50.01
  },
  "panel_1": {
    "mi_sn": "ef56gh78",
    "input_voltage": 37.8,
    "power": 225.4,
    "energy": 617.26,
    "temperature": 41.8,
    "grid_voltage": 231.4,
    "frequency": 50.01
  }
}
```

---

## Home Assistant

When `HA_DISCOVERY` is enabled (default), the app publishes retained MQTT discovery messages on startup. Home Assistant will automatically create:

- A device per inverter with sensors for total power, total energy, panel count, and firmware version
- A sub-device per panel with sensors for power, energy, input voltage, grid voltage, frequency, and temperature
- A combined "Envertech Combined" device with summed totals across all inverters

Discovery payloads are published to `homeassistant/sensor/{unique_id}/config` with `retain=true`.

---

## Node-RED → InfluxDB

Import [`nodered-flow.json`](nodered-flow.json) into Node-RED (Menu → Import).

**Requirements:** Install `node-red-contrib-influxdb` via Manage Palette.

The flow creates three InfluxDB measurements:

| Measurement | Tags | Fields |
|---|---|---|
| `solar_inverter` | `inverter_sn` | `total_power`, `total_energy`, `panel_count` |
| `solar_panel` | `inverter_sn`, `panel_index`, `panel_sn` | `power`, `energy`, `input_voltage`, `temperature`, `grid_voltage`, `frequency` |
| `solar_combined` | `source` | `total_power`, `total_energy`, `panel_count` |

After importing, edit the **mqtt-config** and **influxdb-config** config nodes with your connection details.

**InfluxDB 2.x:** In the influxdb config node set the version to `2.0` and supply your org, bucket, and token instead of the database name.

---

## Building and Running Locally

```bash
docker build -t envertech2mqtt .
docker run --rm \
  -e INVERTER_IP=192.168.1.100 \
  -e INVERTER_SN=ABCD1234 \
  -e MQTT_HOST=192.168.1.10 \
  envertech2mqtt
```

Or with a config file:

```bash
docker run --rm \
  -v $(pwd)/config.yml:/app/config.yml:ro \
  envertech2mqtt
```

### Without Docker

```bash
pip install -r requirements.txt
INVERTER_IP=192.168.1.100 INVERTER_SN=ABCD1234 MQTT_HOST=192.168.1.10 python -m app.main
```

---

## GitHub Actions / Container Registry

The included workflow (`.github/workflows/docker-build.yml`) builds multi-platform images (`linux/amd64`, `linux/arm64`) and pushes them to the GitHub Container Registry (`ghcr.io`) on every push to `main` and on version tags (`v*`).

To use the published image, replace `OWNER` in `docker-compose.yml` with your GitHub username/org.

Images are tagged:
- `latest` — latest commit on `main`
- `main` — branch name
- `1.2.3` / `1.2` — on version tags

---

## Finding Your Inverter Serial Number

The serial number is the 8-character hex string printed on the label of each microinverter unit. It is also visible in the EnverView app or web portal under device details. It is **not** the long numeric serial number — it is the short hex ID used for local communication (the gateway/Wi-Fi hub usually shows connected inverter IDs).
