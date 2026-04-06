from __future__ import annotations

import logging
import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components
from streamlit_autorefresh import st_autorefresh

from gaugesim.config import AppSettings, load_settings, save_settings
from gaugesim.hydapi import HydApiError, SeriesQuery, fetch_observations
from gaugesim.mqtt_client import GaugeMqttPublisher, MqttSettings
from gaugesim.simulator import RuntimeState, SimulatorConfig, next_payload
from gaugesim.timeseries import Transform, align_and_transform, crop_period

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

UI_TZ = timezone(timedelta(hours=1))


def init_state() -> None:
    st.session_state.setdefault("settings", load_settings())
    st.session_state.setdefault("stage_df", None)
    st.session_state.setdefault("dis_df", None)
    st.session_state.setdefault("merged_df", None)
    st.session_state.setdefault("cropped_df", None)
    st.session_state.setdefault("sim_thread", None)
    st.session_state.setdefault("sim_stop", threading.Event())
    st.session_state.setdefault("sim_pause", threading.Event())
    st.session_state.setdefault("runtime_data", {"latest_payload": None, "running": False})
    st.session_state.setdefault("mqtt", None)
    st.session_state.setdefault("sim_running", False)


def to_utc(dt_local: datetime) -> datetime:
    if dt_local.tzinfo is None:
        dt_local = dt_local.replace(tzinfo=UI_TZ)
    return dt_local.astimezone(timezone.utc)


def parse_series_id(series_id: str) -> tuple[str, str, str]:
    parts = series_id.strip().rsplit(".", 2)
    if len(parts) != 3 or any(not p for p in parts):
        raise ValueError("Series ID must be on the form <stationID>.<param>.<version>")
    return parts[0], parts[1], parts[2]


def disable_dashlane_autofill() -> None:
    components.html(
        """
        <script>
        const setAttr = () => {
          const root = window.parent.document;
          root.querySelectorAll("input, textarea").forEach((el) => {
            el.setAttribute("data-form-type", "other");
          });
        };
        setAttr();
        const observer = new MutationObserver(setAttr);
        observer.observe(window.parent.document.body, { childList: true, subtree: true });
        </script>
        """,
        height=0,
        width=0,
    )


def build_plot(
    df: pd.DataFrame,
    cursor_timestamp: datetime | None = None,
    crop_bounds: tuple[datetime, datetime] | None = None,
) -> go.Figure:
    fig = go.Figure()
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["stage"],
            mode="lines",
            name="Stage",
            line=dict(color="blue"),
        )
    )
    fig.add_trace(
        go.Scatter(
            x=df["timestamp"],
            y=df["discharge"],
            mode="lines",
            name="Discharge",
            yaxis="y2",
            line=dict(color="red"),
        )
    )

    x_min = df["timestamp"].min()
    x_max = df["timestamp"].max()

    fig.update_layout(
        xaxis=dict(title="Time", range=[x_min, x_max]),
        yaxis=dict(title="Stage [meter]"),
        yaxis2=dict(title="Discharge [m3/s]", overlaying="y", side="right"),
        legend=dict(orientation="h"),
        margin=dict(l=30, r=30, t=20, b=20),
    )

    if cursor_timestamp is not None:
        fig.add_vline(x=cursor_timestamp, line_color="red", line_dash="dot")
    if crop_bounds is not None:
        start, end = crop_bounds
        fig.add_vline(x=start, line_color="green", line_dash="dash")
        fig.add_vline(x=end, line_color="orange", line_dash="dash")
        fig.add_vrect(x0=start, x1=end, fillcolor="LightGreen", opacity=0.12, line_width=0)

    return fig


def run_simulation_loop(
    df: pd.DataFrame,
    sim_cfg: SimulatorConfig,
    mqtt: GaugeMqttPublisher,
    stop_event: threading.Event,
    pause_event: threading.Event,
    runtime_data: dict,
) -> None:
    state = RuntimeState(started_at=datetime.now(timezone.utc), paused=False, running=True)
    runtime_data["running"] = True
    mqtt.publish_status("SimulationStarted")

    while not stop_event.is_set():
        if pause_event.is_set():
            if not state.paused:
                state.paused = True
                state.pause_started_at = datetime.now(timezone.utc)
            time.sleep(0.1)
            continue

        if state.paused:
            assert state.pause_started_at is not None
            state.paused_accumulated += datetime.now(timezone.utc) - state.pause_started_at
            state.pause_started_at = None
            state.paused = False

        payload, restarted = next_payload(df, sim_cfg, state, datetime.now(timezone.utc))
        if payload is None:
            mqtt.publish_status("SimulationStopped")
            runtime_data["running"] = False
            return

        mqtt.publish_sample(payload)
        runtime_data["latest_payload"] = payload
        if restarted:
            mqtt.publish_status("SimulationRestart")

        time.sleep(sim_cfg.freq_seconds)

    mqtt.publish_status("SimulationStopped")
    runtime_data["running"] = False


def stop_simulation() -> None:
    st.session_state["sim_stop"].set()
    thr = st.session_state.get("sim_thread")
    if thr and thr.is_alive():
        thr.join(timeout=2)
    st.session_state["sim_thread"] = None
    st.session_state["sim_running"] = False
    if "runtime_data" in st.session_state:
        st.session_state["runtime_data"]["running"] = False


def main() -> None:
    st.set_page_config(page_title="GaugeSim", layout="wide")
    init_state()
    disable_dashlane_autofill()

    st.title("Hydrological Gauging Station Simulator")

    settings: AppSettings = st.session_state["settings"]
    with st.expander("Application settings", expanded=False):
        api_token = st.text_input("HydAPI token", value=settings.api_token, type="password")
        mqtt_host = st.text_input("MQTT host", value=settings.mqtt_host)
        mqtt_port = st.number_input("MQTT port", min_value=1, max_value=65535, value=int(settings.mqtt_port), step=1)
        mqtt_user = st.text_input("MQTT username", value=settings.mqtt_username)
        mqtt_pw = st.text_input("MQTT password", value=settings.mqtt_password, type="password")
        mqtt_tls = st.checkbox("Use MQTT TLS", value=settings.mqtt_tls)
        if st.button("Save settings"):
            st.session_state["settings"] = AppSettings(
                api_token=api_token,
                mqtt_host=mqtt_host,
                mqtt_port=int(mqtt_port),
                mqtt_username=mqtt_user,
                mqtt_password=mqtt_pw,
                mqtt_tls=mqtt_tls,
            )
            save_settings(st.session_state["settings"])
            st.success("Settings saved")

    st.header("1) Retrieve source data")
    c1, c2 = st.columns(2)
    stage_series_id = c1.text_input(
        "Stage serie:",
        value=settings.stage_series_id or "",
        placeholder="stationID.param.version",
    )
    discharge_series_id = c2.text_input(
        "Discharge serie:",
        value=settings.discharge_series_id or "",
        placeholder="stationID.param.version",
    )
    resolution_time = st.number_input("ResolutionTime (API)", min_value=0, value=0, step=1)

    now_local = datetime.now(UI_TZ)
    default_start = now_local - timedelta(days=3)
    default_end = now_local

    col_s, col_e = st.columns(2)
    start_local = col_s.datetime_input("Start time (UTC+1)", value=default_start)
    end_local = col_e.datetime_input("End time (UTC+1)", value=default_end)

    if st.button("Fetch data"):
        try:
            stage_station, stage_param, stage_version = parse_series_id(stage_series_id)
            dis_station, dis_param, dis_version = parse_series_id(discharge_series_id)
            stage_df = fetch_observations(
                SeriesQuery(stage_station, stage_param, stage_version, int(resolution_time)),
                to_utc(start_local),
                to_utc(end_local),
                st.session_state["settings"].api_token,
            )
            dis_df = fetch_observations(
                SeriesQuery(dis_station, dis_param, dis_version, int(resolution_time)),
                to_utc(start_local),
                to_utc(end_local),
                st.session_state["settings"].api_token,
            )

            st.session_state["stage_df"] = stage_df
            st.session_state["dis_df"] = dis_df
            st.session_state["settings"].stage_series_id = stage_series_id.strip()
            st.session_state["settings"].discharge_series_id = discharge_series_id.strip()
            save_settings(st.session_state["settings"])
            st.success(f"Fetched stage={len(stage_df)} samples, discharge={len(dis_df)} samples")
        except (HydApiError, ValueError) as exc:
            st.error(str(exc))

    if st.session_state["stage_df"] is None or st.session_state["dis_df"] is None:
        st.info("Fetch data to continue")
        return

    st.header("2) Transform and crop")
    t1, t2, t3, t4 = st.columns(4)
    a_stage = t1.number_input("Stage scale a", value=1.0)
    b_stage = t2.number_input("Stage offset b [meter]", value=0.0)
    a_dis = t3.number_input("Discharge scale a", value=1.0)
    b_dis = t4.number_input("Discharge offset b [m3/s]", value=0.0)

    merged = align_and_transform(
        st.session_state["stage_df"],
        st.session_state["dis_df"],
        Transform(a=a_stage, b=b_stage),
        Transform(a=a_dis, b=b_dis),
    )
    st.session_state["merged_df"] = merged

    min_ts = merged["timestamp"].iloc[0].to_pydatetime().astimezone(UI_TZ).replace(tzinfo=None)
    max_ts = merged["timestamp"].iloc[-1].to_pydatetime().astimezone(UI_TZ).replace(tzinfo=None)

    if "crop_dt_range" not in st.session_state:
        st.session_state["crop_dt_range"] = (min_ts, max_ts)
    if "crop_start_dt" not in st.session_state:
        st.session_state["crop_start_dt"] = min_ts
    if "crop_end_dt" not in st.session_state:
        st.session_state["crop_end_dt"] = max_ts

    # normalize any previously persisted aware datetimes into naive UTC+1 wall clock for widgets
    if st.session_state["crop_start_dt"].tzinfo is not None:
        st.session_state["crop_start_dt"] = st.session_state["crop_start_dt"].astimezone(UI_TZ).replace(tzinfo=None)
    if st.session_state["crop_end_dt"].tzinfo is not None:
        st.session_state["crop_end_dt"] = st.session_state["crop_end_dt"].astimezone(UI_TZ).replace(tzinfo=None)
    range_start, range_end = st.session_state["crop_dt_range"]
    if range_start.tzinfo is not None or range_end.tzinfo is not None:
        range_start = range_start.astimezone(UI_TZ).replace(tzinfo=None)
        range_end = range_end.astimezone(UI_TZ).replace(tzinfo=None)
        st.session_state["crop_dt_range"] = (range_start, range_end)

    current_range = st.session_state["crop_dt_range"]
    if current_range[0] < min_ts or current_range[1] > max_ts:
        st.session_state["crop_dt_range"] = (min_ts, max_ts)
        st.session_state["crop_start_dt"] = min_ts
        st.session_state["crop_end_dt"] = max_ts

    def sync_range_from_dates() -> None:
        start = st.session_state["crop_start_dt"]
        end = st.session_state["crop_end_dt"]
        if start > end:
            start, end = end, start
            st.session_state["crop_start_dt"] = start
            st.session_state["crop_end_dt"] = end
        st.session_state["crop_dt_range"] = (start, end)

    def sync_dates_from_range() -> None:
        start, end = st.session_state["crop_dt_range"]
        st.session_state["crop_start_dt"] = start
        st.session_state["crop_end_dt"] = end

    c_start, c_end = st.columns(2)
    c_start.datetime_input("Crop start (UTC+1)", key="crop_start_dt", on_change=sync_range_from_dates)
    c_end.datetime_input("Crop end (UTC+1)", key="crop_end_dt", on_change=sync_range_from_dates)
    crop_start = to_utc(st.session_state["crop_start_dt"])
    crop_end = to_utc(st.session_state["crop_end_dt"])
    cropped = crop_period(merged, crop_start, crop_end)
    st.session_state["cropped_df"] = cropped

    st.plotly_chart(
        build_plot(
            merged,
            crop_bounds=(to_utc(st.session_state["crop_start_dt"]), to_utc(st.session_state["crop_end_dt"])),
        ),
        width="stretch",
    )
    st.slider(
        "Visual crop by date/time",
        min_value=min_ts,
        max_value=max_ts,
        key="crop_dt_range",
        step=timedelta(minutes=1),
        on_change=sync_dates_from_range,
    )

    st.header("3) Simulator")
    s1, s2, s3 = st.columns(3)
    freq_sec = s1.number_input("Publish frequency (seconds)", min_value=1, max_value=3600, value=5, step=1)
    time_scale = s2.number_input("Time scaling factor", min_value=0.1, max_value=1000.0, value=1.0)
    auto_restart = s3.checkbox("Auto restart at end", value=True)

    start_btn, pause_btn, reset_btn = st.columns(3)

    if start_btn.button("Start simulator") and not st.session_state["sim_running"]:
        if st.session_state["cropped_df"] is None or st.session_state["cropped_df"].empty:
            st.warning("Cropped dataset is empty. Adjust crop range before starting simulator.")
            return
        st.session_state["sim_stop"] = threading.Event()
        st.session_state["sim_pause"] = threading.Event()
        mqtt = GaugeMqttPublisher(
            MqttSettings(
                host=st.session_state["settings"].mqtt_host,
                port=st.session_state["settings"].mqtt_port,
                username=st.session_state["settings"].mqtt_username,
                password=st.session_state["settings"].mqtt_password,
                tls=st.session_state["settings"].mqtt_tls,
            )
        )
        mqtt.connect()
        st.session_state["mqtt"] = mqtt

        sim_cfg = SimulatorConfig(freq_seconds=int(freq_sec), time_scale=float(time_scale), auto_restart=bool(auto_restart))

        runtime_data = {"latest_payload": None, "running": True}
        st.session_state["runtime_data"] = runtime_data
        thr = threading.Thread(
            target=run_simulation_loop,
            args=(st.session_state["cropped_df"], sim_cfg, mqtt, st.session_state["sim_stop"], st.session_state["sim_pause"], runtime_data),
            daemon=True,
        )
        st.session_state["sim_thread"] = thr
        st.session_state["sim_running"] = True
        thr.start()

    if pause_btn.button("Pause / Resume") and st.session_state["sim_running"]:
        if st.session_state["sim_pause"].is_set():
            st.session_state["sim_pause"].clear()
        else:
            st.session_state["sim_pause"].set()

    if reset_btn.button("Reset simulator"):
        stop_simulation()
        if st.session_state.get("mqtt"):
            st.session_state["mqtt"].close()
            st.session_state["mqtt"] = None
        st.session_state["runtime_data"] = {"latest_payload": None, "running": False}

    runtime_data = st.session_state.get("runtime_data", {"latest_payload": None, "running": False})
    st.session_state["sim_running"] = bool(runtime_data.get("running", False))

    if st.session_state["sim_running"]:
        st_autorefresh(interval=1000, key="sim-refresh")
        st.success("Simulator running")
    else:
        st.info("Simulator idle")

    payload = runtime_data.get("latest_payload")
    if payload:
        st.subheader("Current output")
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Stage [meter]", f"{payload['stage']:.3f}")
        n2.metric("Discharge [m3/s]", f"{payload['discharge']:.3f}")
        n3.metric("Original stage [meter]", f"{payload['originalStage']:.3f}")
        n4.metric("Original discharge [m3/s]", f"{payload['originalDischarge']:.3f}")
        original_ts = pd.to_datetime(payload["originalTimestamp"]).strftime("%Y-%m-%d %H:%M")
        st.caption(f"Original timestamp: {original_ts}")

        cursor = pd.to_datetime(payload["originalTimestamp"])
        st.plotly_chart(
            build_plot(
                st.session_state["cropped_df"],
                cursor_timestamp=cursor,
                crop_bounds=(to_utc(st.session_state["crop_start_dt"]), to_utc(st.session_state["crop_end_dt"])),
            ),
            width="stretch",
        )
        st.json(payload)


if __name__ == "__main__":
    main()
