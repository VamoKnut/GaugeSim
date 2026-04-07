from pathlib import Path

from gaugesim.config import AppSettings, load_settings, save_settings


def test_persist_series_ids(tmp_path: Path):
    path = tmp_path / "settings.json"
    settings = AppSettings(
        api_token="x",
        mqtt_host="h",
        mqtt_port=1883,
        stage_series_id="6.24.4.1001.1",
        discharge_series_id="7.25.5.1000.1",
    )
    save_settings(settings, path=path)
    loaded = load_settings(path=path)
    assert loaded.stage_series_id == "6.24.4.1001.1"
    assert loaded.discharge_series_id == "7.25.5.1000.1"
