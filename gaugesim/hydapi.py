from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import requests

API_URL = "https://hydapi.nve.no/api/v1/Observations"


@dataclass
class SeriesQuery:
    station_id: str
    parameter: str
    version: str
    resolution_time: int = 0

    @property
    def series_id(self) -> str:
        return f"{self.station_id}:{self.parameter}:{self.version}"


class HydApiError(RuntimeError):
    pass


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def _extract_rows(payload: Any) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []

    if isinstance(payload, dict):
        if isinstance(payload.get("data"), list):
            for item in payload["data"]:
                if isinstance(item, dict):
                    if isinstance(item.get("observations"), list):
                        candidates.extend(x for x in item["observations"] if isinstance(x, dict))
                    else:
                        candidates.append(item)
        if isinstance(payload.get("observations"), list):
            candidates.extend(x for x in payload["observations"] if isinstance(x, dict))

    if isinstance(payload, list):
        candidates.extend(x for x in payload if isinstance(x, dict))

    return candidates


def fetch_observations(
    query: SeriesQuery,
    start_utc: datetime,
    end_utc: datetime,
    token: str,
    timeout_sec: int = 30,
) -> pd.DataFrame:
    params = {
        "StationId": query.station_id,
        "Parameter": query.parameter,
        "Version": query.version,
        "ResolutionTime": query.resolution_time,
        "ReferenceTime": f"{_as_utc(start_utc).isoformat()}/{_as_utc(end_utc).isoformat()}",
    }
    headers = {"X-API-Key": token}

    response = requests.get(API_URL, params=params, headers=headers, timeout=timeout_sec)
    if response.status_code != 200:
        raise HydApiError(f"HydAPI returned HTTP {response.status_code}: {response.text[:300]}")

    try:
        payload = response.json()
    except ValueError as exc:
        raise HydApiError("HydAPI returned non-JSON payload") from exc

    rows = _extract_rows(payload)
    if not rows:
        raise HydApiError("No observations found for selected series and time window")

    parsed: list[dict[str, Any]] = []
    for row in rows:
        timestamp = (
            row.get("time")
            or row.get("timestamp")
            or row.get("referenceTime")
            or row.get("observationTime")
            or row.get("dateTime")
        )
        value = row.get("value")
        if value is None and isinstance(row.get("observedValue"), dict):
            value = row["observedValue"].get("value")
        if timestamp is None or value is None:
            continue
        parsed.append({"timestamp": pd.to_datetime(timestamp, utc=True), "value": float(value)})

    if not parsed:
        raise HydApiError("Unable to parse observation timestamps/values from API response")

    df = pd.DataFrame(parsed).drop_duplicates("timestamp").sort_values("timestamp")
    return df.reset_index(drop=True)
