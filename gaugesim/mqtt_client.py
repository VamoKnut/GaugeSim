from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt

logger = logging.getLogger(__name__)


@dataclass
class MqttSettings:
    host: str
    port: int
    username: str = ""
    password: str = ""
    tls: bool = False


class GaugeMqttPublisher:
    def __init__(self, settings: MqttSettings) -> None:
        self._settings = settings
        self._client = mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
            protocol=mqtt.MQTTv5,
        )
        if settings.username.strip():
            self._client.username_pw_set(settings.username, settings.password)
            logger.info("MQTT auth: username/password enabled")
        else:
            logger.info("MQTT auth: anonymous connection (no username)")
        if settings.tls:
            self._client.tls_set()
        self._connected = threading.Event()
        self._stop_retry = threading.Event()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0:
            logger.info("MQTT connected to %s:%s", self._settings.host, self._settings.port)
            self._connected.set()
        else:
            logger.warning("MQTT connect returned non-zero reason code: %s", reason_code)

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        reason_text = str(reason_code)
        if "Normal disconnection" in reason_text:
            logger.info("MQTT disconnected (reason_code=%s)", reason_code)
        else:
            logger.warning("MQTT disconnected (reason_code=%s)", reason_code)
        self._connected.clear()

    def connect(self) -> None:
        self._client.loop_start()
        self._connect_with_retry()

    def _connect_with_retry(self) -> None:
        while not self._connected.is_set() and not self._stop_retry.is_set():
            try:
                self._client.connect(self._settings.host, self._settings.port, keepalive=60)
            except Exception as exc:
                logger.warning("MQTT connect retry failed: %s", exc)
            self._connected.wait(timeout=2)
            if self._connected.is_set():
                break
            time.sleep(2)

    def publish_sample(self, payload: dict) -> None:
        self._ensure_connected()
        payload_json = json.dumps(payload)
        logger.info("MQTT -> gaugsim/sample %s", payload_json)
        self._client.publish("gaugsim/sample", payload_json, qos=0, retain=False)

    def publish_status(self, status: str) -> None:
        self._ensure_connected()
        payload_json = json.dumps({"status": status})
        logger.info("MQTT -> gaugsim/status %s", payload_json)
        self._client.publish("gaugsim/status", payload_json, qos=0, retain=False)

    def _ensure_connected(self) -> None:
        if not self._connected.is_set():
            self._connect_with_retry()

    def close(self) -> None:
        self._stop_retry.set()
        self._client.loop_stop()
        try:
            self._client.disconnect()
        except Exception:
            pass
