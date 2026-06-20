from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class InverterConfig:
    ip: str
    serial_number: str
    name: Optional[str] = None
    port: int = 14889


@dataclass
class MQTTConfig:
    host: str
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    topic: str = "envertech"
    ha_discovery: bool = True
    ha_discovery_prefix: str = "homeassistant"


@dataclass
class AppConfig:
    mqtt: MQTTConfig
    inverters: list[InverterConfig]
    poll_interval: int = 30
    log_level: str = "INFO"


def _env_bool(key: str, default: bool) -> bool:
    val = os.environ.get(key)
    if val is None:
        return default
    return val.lower() not in ("false", "0", "no")


def load_config(config_path: Optional[str] = None) -> AppConfig:
    config_path = config_path or os.environ.get("CONFIG_FILE", "config.yml")
    raw: dict = {}

    if Path(config_path).exists():
        with open(config_path) as f:
            raw = yaml.safe_load(f) or {}
        logger.info(f"Loaded configuration from {config_path}")
    else:
        logger.info(f"No config file found at {config_path!r}, falling back to environment variables")

    mqtt_raw = raw.get("mqtt", {})
    mqtt = MQTTConfig(
        host=mqtt_raw.get("host") or os.environ.get("MQTT_HOST", "localhost"),
        port=int(mqtt_raw.get("port") or os.environ.get("MQTT_PORT", 1883)),
        username=mqtt_raw.get("username") or os.environ.get("MQTT_USERNAME") or None,
        password=mqtt_raw.get("password") or os.environ.get("MQTT_PASSWORD") or None,
        topic=mqtt_raw.get("topic") or os.environ.get("MQTT_TOPIC", "envertech"),
        ha_discovery=mqtt_raw.get("ha_discovery", _env_bool("HA_DISCOVERY", True)),
        ha_discovery_prefix=mqtt_raw.get("ha_discovery_prefix") or os.environ.get("HA_DISCOVERY_PREFIX", "homeassistant"),
    )

    if "inverters" in raw:
        inverters = [
            InverterConfig(
                ip=inv["ip"],
                serial_number=str(inv["serial_number"]),
                name=inv.get("name"),
                port=int(inv.get("port", 14889)),
            )
            for inv in raw["inverters"]
        ]
    else:
        ip = os.environ.get("INVERTER_IP")
        sn = os.environ.get("INVERTER_SN")
        if not ip or not sn:
            raise ValueError(
                "No inverters configured. Either:\n"
                "  - Set INVERTER_IP and INVERTER_SN environment variables, or\n"
                "  - Mount a config.yml with an 'inverters' list (see config.example.yml)"
            )
        inverters = [
            InverterConfig(
                ip=ip,
                serial_number=sn,
                name=os.environ.get("INVERTER_NAME"),
                port=int(os.environ.get("INVERTER_PORT", 14889)),
            )
        ]

    poll_interval = int(raw.get("poll_interval") or os.environ.get("POLL_INTERVAL", 30))
    log_level = raw.get("log_level") or os.environ.get("LOG_LEVEL", "INFO")

    return AppConfig(
        mqtt=mqtt,
        inverters=inverters,
        poll_interval=poll_interval,
        log_level=log_level,
    )
