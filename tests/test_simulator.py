from datetime import datetime, timezone

import pandas as pd

from gaugesim.simulator import RuntimeState, SimulatorConfig, next_payload


def test_next_payload_stops_when_no_restart():
    df = pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:00:10Z"], utc=True),
            "stage": [1.0, 2.0],
            "discharge": [4.0, 5.0],
            "originalStage": [1.0, 2.0],
            "originalDischarge": [4.0, 5.0],
        }
    )

    cfg = SimulatorConfig(freq_seconds=1.0, time_scale=1.0, auto_restart=False)
    state = RuntimeState(started_at=datetime(2026, 1, 1, tzinfo=timezone.utc))

    payload, restarted = next_payload(df, cfg, state, datetime(2026, 1, 1, 0, 0, 11, tzinfo=timezone.utc))
    assert payload is None
    assert restarted is False
    assert state.running is False
