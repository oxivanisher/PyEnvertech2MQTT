"""Home Assistant MQTT discovery payload publisher."""
from __future__ import annotations

import json
import logging

from app.config import InverterConfig, MQTTConfig
from app.mqtt_client import MQTTClient

logger = logging.getLogger(__name__)

# (field, display_label, unit, device_class, state_class)
_INVERTER_SENSORS: list[tuple] = [
    ("total_power",     "Total Power",       "W",   "power",       "measurement"),
    ("total_energy",    "Total Energy",      "Wh",  "energy",      "total_increasing"),
    ("panel_count",     "Panel Count",       None,  None,          "measurement"),
    ("firmware_version","Firmware Version",  None,  None,          None),
]

_PANEL_SENSORS: list[tuple] = [
    ("input_voltage",  "Input Voltage",  "V",   "voltage",     "measurement"),
    ("power",          "Power",          "W",   "power",       "measurement"),
    ("energy",         "Energy",         "Wh",  "energy",      "total_increasing"),
    ("temperature",    "Temperature",    "°C",  "temperature", "measurement"),
    ("grid_voltage",   "Grid Voltage",   "V",   "voltage",     "measurement"),
    ("frequency",      "Frequency",      "Hz",  "frequency",   "measurement"),
]

_COMBINED_SENSORS: list[tuple] = [
    ("total_power",  "Total Power",  "W",   "power",  "measurement"),
    ("total_energy", "Total Energy", "Wh",  "energy", "total_increasing"),
    ("panel_count",  "Panel Count",  None,  None,     "measurement"),
]


def _config_payload(
    unique_id: str,
    name: str,
    state_topic: str,
    value_template: str,
    unit: str | None,
    device_class: str | None,
    state_class: str | None,
    device: dict,
) -> dict:
    payload: dict = {
        "name": name,
        "unique_id": unique_id,
        "state_topic": state_topic,
        "value_template": value_template,
        "device": device,
    }
    if unit:
        payload["unit_of_measurement"] = unit
    if device_class:
        payload["device_class"] = device_class
    if state_class:
        payload["state_class"] = state_class
    return payload


def publish_inverter_discovery(
    client: MQTTClient,
    inverter: InverterConfig,
    n_panels: int,
    mqtt_cfg: MQTTConfig,
):
    sn = inverter.serial_number
    display_name = inverter.name or f"Envertech {sn}"
    prefix = mqtt_cfg.ha_discovery_prefix
    status_topic = f"{mqtt_cfg.topic}/{sn}/status"

    inverter_device = {
        "identifiers": [f"envertech_{sn}"],
        "name": display_name,
        "manufacturer": "Envertech",
        "model": "Microinverter",
    }

    for field, label, unit, dev_class, state_class in _INVERTER_SENSORS:
        uid = f"envertech_{sn}_{field}"
        payload = _config_payload(
            unique_id=uid,
            name=f"{display_name} {label}",
            state_topic=status_topic,
            value_template=f"{{{{ value_json.{field} }}}}",
            unit=unit,
            device_class=dev_class,
            state_class=state_class,
            device=inverter_device,
        )
        client.publish(f"{prefix}/sensor/{uid}/config", json.dumps(payload), retain=True)

    for i in range(n_panels):
        panel_topic = f"{mqtt_cfg.topic}/{sn}/panel/{i}/status"
        panel_device = {
            "identifiers": [f"envertech_{sn}_panel_{i}"],
            "name": f"{display_name} Panel {i + 1}",
            "manufacturer": "Envertech",
            "model": "Panel",
            "via_device": f"envertech_{sn}",
        }
        for field, label, unit, dev_class, state_class in _PANEL_SENSORS:
            uid = f"envertech_{sn}_panel_{i}_{field}"
            payload = _config_payload(
                unique_id=uid,
                name=f"{display_name} Panel {i + 1} {label}",
                state_topic=panel_topic,
                value_template=f"{{{{ value_json.{field} }}}}",
                unit=unit,
                device_class=dev_class,
                state_class=state_class,
                device=panel_device,
            )
            client.publish(f"{prefix}/sensor/{uid}/config", json.dumps(payload), retain=True)

    logger.info(f"Published HA discovery for inverter {sn} ({n_panels} panels)")


def publish_combined_discovery(client: MQTTClient, mqtt_cfg: MQTTConfig):
    prefix = mqtt_cfg.ha_discovery_prefix
    status_topic = f"{mqtt_cfg.topic}/combined/status"
    device = {
        "identifiers": ["envertech_combined"],
        "name": "Envertech Combined",
        "manufacturer": "Envertech",
        "model": "Combined",
    }
    for field, label, unit, dev_class, state_class in _COMBINED_SENSORS:
        uid = f"envertech_combined_{field}"
        payload = _config_payload(
            unique_id=uid,
            name=f"Envertech Combined {label}",
            state_topic=status_topic,
            value_template=f"{{{{ value_json.{field} }}}}",
            unit=unit,
            device_class=dev_class,
            state_class=state_class,
            device=device,
        )
        client.publish(f"{prefix}/sensor/{uid}/config", json.dumps(payload), retain=True)
    logger.info("Published HA discovery for combined sensors")
