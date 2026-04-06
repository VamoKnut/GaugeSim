from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass

import paho.mqtt.client as mqtt


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
        self._client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
        if settings.username:
            self._client.username_pw_set(settings.username, settings.password)
        if settings.tls:
            self._client.tls_set()
        self._connected = threading.Event()
        self._stop_retry = threading.Event()
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect

    def _on_connect(self, client: mqtt.Client, userdata, flags, reason_code, properties=None) -> None:
        if reason_code == 0:
            self._connected.set()

    def _on_disconnect(self, client: mqtt.Client, userdata, disconnect_flags, reason_code, properties=None) -> None:
        self._connected.clear()

    def connect(self) -> None:
        self._client.loop_start()
        self._connect_with_retry()

    def _connect_with_retry(self) -> None:
        while not self._connected.is_set() and not self._stop_retry.is_set():
            try:
                self._client.connect(self._settings.host, self._settings.port, keepalive=60)
            except Exception:
                pass
            self._connected.wait(timeout=2)
            if self._connected.is_set():
                break
            time.sleep(2)

    def publish_sample(self, payload: dict) -> None:
        self._ensure_connected()
        self._client.publish("gaugsim/sample", json.dumps(payload), qos=0, retain=False)

    def publish_status(self, status: str) -> None:
        self._ensure_connected()
        self._client.publish("gaugsim/status", json.dumps({"status": status}), qos=0, retain=False)

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
