# GaugeSim

Local web app simulator for hydrological gauging stations.

## Features

- Fetches stage/discharge observations from NVE HydAPI for user-selected period, including configurable `ResolutionTime` (default `0`).
- Can also generate synthetic V-weir datasets from start/end window, resolution, and triangular stage parameters (offset + amplitude).
- Uses stage/discharge source fields on the form `<stationID>.<param>.<version>` and persists these serie IDs between runs.
- Applies independent linear transforms (`y = aX + b`) to stage and discharge.
- Crops to a base replay window by time and index.
- Replays as fake realtime values to MQTT with blue stage plots and red discharge plots.
- Publishes sample data to `gaugsim/sample` and lifecycle status to `gaugsim/status` (start/stop/restart), with console logs of outgoing MQTT payloads.
- Supports time scaling (0.1 to 1000), publish frequency (1 to 3600 sec), pause/resume/reset, and optional auto-restart.

## Run

```bash
python -m pip install -e .
streamlit run app.py
```

## Docker

```bash
docker build -t gaugesim:latest .
docker run --rm -p 8501:8501 gaugesim:latest
```

Or with compose:

```bash
docker compose up --build
```

## Notes

- UI uses UTC+1; API calls are converted to UTC.
- Missing values are interpolated.
- Settings are persisted in `.gaugesim_settings.json`.
