from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass
class Transform:
    a: float = 1.0
    b: float = 0.0


def align_and_transform(
    stage_df: pd.DataFrame,
    discharge_df: pd.DataFrame,
    stage_transform: Transform,
    discharge_transform: Transform,
) -> pd.DataFrame:
    stage = stage_df.rename(columns={"value": "originalStage"}).copy()
    dis = discharge_df.rename(columns={"value": "originalDischarge"}).copy()

    timeline = pd.Index(sorted(set(stage["timestamp"]).union(set(dis["timestamp"]))), name="timestamp")

    stage = stage.set_index("timestamp").reindex(timeline).interpolate(method="time", limit_direction="both")
    dis = dis.set_index("timestamp").reindex(timeline).interpolate(method="time", limit_direction="both")

    merged = pd.concat([stage, dis], axis=1).reset_index()
    merged["stage"] = stage_transform.a * merged["originalStage"] + stage_transform.b
    merged["discharge"] = discharge_transform.a * merged["originalDischarge"] + discharge_transform.b

    return merged[["timestamp", "stage", "discharge", "originalStage", "originalDischarge"]]


def crop_period(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    cropped = df[(df["timestamp"] >= start) & (df["timestamp"] <= end)].copy()
    return cropped.reset_index(drop=True)


def interpolate_at(df: pd.DataFrame, at: pd.Timestamp) -> dict[str, float | pd.Timestamp]:
    series = df.set_index("timestamp").sort_index()
    if at <= series.index[0]:
        row = series.iloc[0]
        row_ts = series.index[0]
    elif at >= series.index[-1]:
        row = series.iloc[-1]
        row_ts = series.index[-1]
    else:
        expanded = series.reindex(series.index.union([at])).sort_index().interpolate(method="time")
        row = expanded.loc[at]
        row_ts = at

    return {
        "timestamp": row_ts,
        "stage": float(row["stage"]),
        "discharge": float(row["discharge"]),
        "originalStage": float(row["originalStage"]),
        "originalDischarge": float(row["originalDischarge"]),
    }
