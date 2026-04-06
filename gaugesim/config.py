from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path

CONFIG_PATH = Path(".gaugesim_settings.json")


@dataclass
class AppSettings:
    api_token: str = ""
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_tls: bool = False
    stage_series_id: str = ""
    discharge_series_id: str = ""


DEFAULT_SETTINGS = AppSettings(
    api_token="v2oV4jC/k0WmNM1z2Dp+Wg==",
    mqtt_host="localhost",
    mqtt_port=1883,
)


def load_settings(path: Path = CONFIG_PATH) -> AppSettings:
    if not path.exists():
        return DEFAULT_SETTINGS
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return AppSettings(
            api_token=payload.get("api_token", ""),
            mqtt_host=payload.get("mqtt_host", "localhost"),
            mqtt_port=int(payload.get("mqtt_port", 1883)),
            mqtt_username=payload.get("mqtt_username", ""),
            mqtt_password=payload.get("mqtt_password", ""),
            mqtt_tls=bool(payload.get("mqtt_tls", False)),
            stage_series_id=payload.get("stage_series_id", ""),
            discharge_series_id=payload.get("discharge_series_id", ""),
        )
    except (json.JSONDecodeError, OSError, ValueError, TypeError):
        return DEFAULT_SETTINGS


def save_settings(settings: AppSettings, path: Path = CONFIG_PATH) -> None:
    path.write_text(json.dumps(asdict(settings), indent=2), encoding="utf-8")
