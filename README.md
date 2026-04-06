# GaugeSim

Local web app simulator for hydrological gauging stations.

## Features

- Fetches stage/discharge observations from NVE HydAPI for user-selected period.
- Applies independent linear transforms (`y = aX + b`) to stage and discharge.
- Crops to a base replay window by time and index.
- Replays as fake realtime values to MQTT.
- Publishes sample data to `gaugsim/sample` and lifecycle status to `gaugsim/status`.
- Supports time scaling (0.1 to 1000), publish frequency (1 to 3600 sec), pause/resume/reset, and optional auto-restart.

## Run

```bash
python -m pip install -e .
streamlit run app.py
```

## Notes

- UI uses UTC+1; API calls are converted to UTC.
- Missing values are interpolated.
- Settings are persisted in `.gaugesim_settings.json`.
