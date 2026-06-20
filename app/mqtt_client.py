from __future__ import annotations

import json
import logging
import threading
from typing import Optional

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


class MQTTClient:
    def __init__(
        self,
        host: str,
        port: int = 1883,
        username: Optional[str] = None,
        password: Optional[str] = None,
    ):
        self._host = host
        self._port = port
        self._connected = threading.Event()

        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if username:
            self._client.username_pw_set(username, password)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        if reason_code == 0:
            logger.info(f"Connected to MQTT broker {self._host}:{self._port}")
            self._connected.set()
        else:
            logger.error(f"MQTT connection refused: reason_code={reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        self._connected.clear()
        if reason_code != 0:
            logger.warning(f"Unexpected MQTT disconnect (reason_code={reason_code}), will reconnect")

    def connect(self, timeout: float = 10.0):
        self._client.connect(self._host, self._port, keepalive=60)
        self._client.loop_start()
        if not self._connected.wait(timeout=timeout):
            raise ConnectionError(f"Could not connect to MQTT broker at {self._host}:{self._port} within {timeout}s")

    def disconnect(self):
        self._client.loop_stop()
        self._client.disconnect()

    def publish(self, topic: str, payload, retain: bool = False, qos: int = 0):
        if isinstance(payload, (dict, list)):
            payload = json.dumps(payload, separators=(",", ":"))
        elif not isinstance(payload, str):
            payload = str(payload)

        result = self._client.publish(topic, payload, qos=qos, retain=retain)
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning(f"Failed to publish to {topic!r}: rc={result.rc}")
        else:
            logger.debug(f"Published to {topic!r}: {payload}")
