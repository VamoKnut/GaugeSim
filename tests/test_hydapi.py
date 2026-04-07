from datetime import datetime, timezone

from gaugesim.hydapi import SeriesQuery, fetch_observations


class DummyResponse:
    def __init__(self):
        self.status_code = 200

    def json(self):
        return {
            "observations": [
                {"timestamp": "2026-01-01T00:00:00Z", "value": 1.2},
                {"timestamp": "2026-01-01T00:01:00Z", "value": 1.3},
            ]
        }



def test_fetch_observations_includes_resolution_time(monkeypatch):
    captured = {}

    def fake_get(url, params, headers, timeout):
        captured["url"] = url
        captured["params"] = params
        captured["headers"] = headers
        return DummyResponse()

    monkeypatch.setattr("gaugesim.hydapi.requests.get", fake_get)

    df = fetch_observations(
        SeriesQuery("12.34.0", "1001", "1", 0),
        datetime(2026, 1, 1, tzinfo=timezone.utc),
        datetime(2026, 1, 2, tzinfo=timezone.utc),
        token="abc",
    )

    assert len(df) == 2
    assert captured["params"]["ResolutionTime"] == 0
