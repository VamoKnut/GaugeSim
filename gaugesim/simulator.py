from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import pandas as pd

from gaugesim.timeseries import interpolate_at


@dataclass
class SimulatorConfig:
    freq_seconds: float
    time_scale: float
    auto_restart: bool


@dataclass
class RuntimeState:
    started_at: datetime
    paused: bool = False
    pause_started_at: datetime | None = None
    paused_accumulated: timedelta = timedelta(0)
    running: bool = True


def simulated_elapsed_seconds(now: datetime, state: RuntimeState) -> float:
    if state.paused and state.pause_started_at is not None:
        base = state.pause_started_at
    else:
        base = now
    elapsed = base - state.started_at - state.paused_accumulated
    return max(0.0, elapsed.total_seconds())


def next_payload(
    df: pd.DataFrame,
    config: SimulatorConfig,
    state: RuntimeState,
    now: datetime,
) -> tuple[dict | None, bool]:
    if not state.running:
        return None, False
    if df.empty:
        state.running = False
        return None, False

    elapsed_real = simulated_elapsed_seconds(now, state)
    elapsed_series = elapsed_real * config.time_scale

    start_ts = df["timestamp"].iloc[0]
    end_ts = df["timestamp"].iloc[-1]
    total_series_sec = (end_ts - start_ts).total_seconds()

    if total_series_sec <= 0:
        sample = interpolate_at(df, start_ts)
        return _payload_from(sample, now), False

    if elapsed_series > total_series_sec:
        if config.auto_restart:
            cycles = int(elapsed_series // total_series_sec)
            state.started_at = state.started_at + timedelta(seconds=(cycles * total_series_sec) / config.time_scale)
            elapsed_series = elapsed_series % total_series_sec
            restarted = True
        else:
            state.running = False
            return None, False
    else:
        restarted = False

    series_time = start_ts + pd.Timedelta(seconds=elapsed_series)
    sample = interpolate_at(df, series_time)
    return _payload_from(sample, now), restarted


UI_TZ = timezone(timedelta(hours=1))


def _payload_from(sample: dict, now: datetime) -> dict:
    return {
        "timeStamp": now.astimezone(UI_TZ).isoformat(),
        "stage": sample["stage"],
        "discharge": sample["discharge"],
        "originalStage": sample["originalStage"],
        "originalDischarge": sample["originalDischarge"],
        "originalTimestamp": pd.Timestamp(sample["timestamp"]).astimezone(UI_TZ).isoformat(),
    }
