from __future__ import annotations

import asyncio
import logging
import sys
import time

from app.config import AppConfig, InverterConfig, load_config
from app.ha_discovery import publish_combined_discovery, publish_inverter_discovery
from app.mqtt_client import MQTTClient
from app.protocol import InverterClient


def _setup_logging(level: str):
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-8s %(name)s: %(message)s",
        stream=sys.stdout,
    )


async def _fetch(inverter: InverterConfig) -> tuple[dict, int | None]:
    client = InverterClient(ip=inverter.ip, port=inverter.port, sn=inverter.serial_number)
    try:
        return await client.fetch()
    except (OSError, asyncio.TimeoutError) as exc:
        logging.getLogger(__name__).warning(
            f"Connection error for {inverter.ip} ({inverter.serial_number}): {exc}"
        )
        return {}, None
    except Exception as exc:
        logging.getLogger(__name__).error(
            f"Error fetching from {inverter.ip} ({inverter.serial_number}): {exc}"
        )
        return {}, None


def _publish_inverter(mqtt: MQTTClient, base_topic: str, sn: str, data: dict):
    mqtt.publish(f"{base_topic}/{sn}/status", data)

    for key in ("total_power", "total_energy", "panel_count", "firmware_version"):
        if key in data:
            mqtt.publish(f"{base_topic}/{sn}/{key}", data[key])

    for panel_key, panel_data in data.items():
        if not panel_key.startswith("panel_") or not isinstance(panel_data, dict):
            continue
        idx = panel_key.split("_", 1)[1]
        mqtt.publish(f"{base_topic}/{sn}/panel/{idx}/status", panel_data)
        for field, value in panel_data.items():
            mqtt.publish(f"{base_topic}/{sn}/panel/{idx}/{field}", value)


def _publish_combined(mqtt: MQTTClient, base_topic: str, results: list[dict]):
    combined = {
        "total_power": round(sum(d.get("total_power", 0) for d in results), 2),
        "total_energy": round(sum(d.get("total_energy", 0) for d in results), 2),
        "panel_count": sum(d.get("panel_count", 0) for d in results),
    }
    mqtt.publish(f"{base_topic}/combined/status", combined)
    for key, val in combined.items():
        mqtt.publish(f"{base_topic}/combined/{key}", val)


async def poll_once(config: AppConfig, mqtt: MQTTClient, ha_published: set):
    logger = logging.getLogger(__name__)
    tasks = [_fetch(inv) for inv in config.inverters]
    results = await asyncio.gather(*tasks)

    valid: list[dict] = []
    for inverter, (data, n_panels) in zip(config.inverters, results):
        if not data:
            continue

        sn = inverter.serial_number
        if config.mqtt.ha_discovery and sn not in ha_published and n_panels is not None:
            publish_inverter_discovery(mqtt, inverter, n_panels, config.mqtt)
            ha_published.add(sn)

        _publish_inverter(mqtt, config.mqtt.topic, sn, data)
        valid.append(data)
        logger.info(
            f"[{sn}] {n_panels} panel(s) — "
            f"{data.get('total_power')} W / {data.get('total_energy')} Wh total"
        )

    if valid:
        _publish_combined(mqtt, config.mqtt.topic, valid)

        if config.mqtt.ha_discovery and "combined" not in ha_published:
            publish_combined_discovery(mqtt, config.mqtt)
            ha_published.add("combined")


async def run(config: AppConfig):
    logger = logging.getLogger(__name__)
    mqtt = MQTTClient(
        host=config.mqtt.host,
        port=config.mqtt.port,
        username=config.mqtt.username,
        password=config.mqtt.password,
    )
    mqtt.connect()
    ha_published: set[str] = set()

    logger.info(
        f"Polling {len(config.inverters)} inverter(s) every {config.poll_interval}s"
    )
    try:
        while True:
            t0 = time.monotonic()
            await poll_once(config, mqtt, ha_published)
            elapsed = time.monotonic() - t0
            await asyncio.sleep(max(0.0, config.poll_interval - elapsed))
    except KeyboardInterrupt:
        logger.info("Interrupted, shutting down")
    finally:
        mqtt.disconnect()


def main():
    config = load_config()
    _setup_logging(config.log_level)
    asyncio.run(run(config))


if __name__ == "__main__":
    main()
