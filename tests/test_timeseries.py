from datetime import timezone

import pandas as pd

from gaugesim.timeseries import Transform, align_and_transform, crop_period, interpolate_at


def _df(values):
    return pd.DataFrame(
        {
            "timestamp": pd.to_datetime(["2026-01-01T00:00:00Z", "2026-01-01T00:10:00Z"], utc=True),
            "value": values,
        }
    )


def test_align_transform_and_interpolate():
    stage = _df([1.0, 3.0])
    dis = _df([10.0, 30.0])

    merged = align_and_transform(stage, dis, Transform(a=2.0, b=1.0), Transform(a=0.5, b=-1.0))
    assert list(merged.columns) == ["timestamp", "stage", "discharge", "originalStage", "originalDischarge"]
    assert merged.iloc[0]["stage"] == 3.0
    assert merged.iloc[-1]["discharge"] == 14.0

    t = pd.Timestamp("2026-01-01T00:05:00Z")
    row = interpolate_at(merged, t)
    assert row["stage"] == 5.0
    assert row["discharge"] == 9.0


def test_crop_period():
    stage = _df([1.0, 3.0])
    dis = _df([10.0, 30.0])
    merged = align_and_transform(stage, dis, Transform(), Transform())
    start = pd.Timestamp("2026-01-01T00:01:00Z")
    end = pd.Timestamp("2026-01-01T00:09:00Z")
    cropped = crop_period(merged, start, end)
    assert cropped.empty
