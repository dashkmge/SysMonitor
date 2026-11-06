"""
SysMonitor - system monitoring dashboard.

Stack: psutil (system data) + Streamlit (UI) + requests (Telegram Bot API).
Run:   streamlit run app.py
Config: TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID via environment variables or a
        .env file (see .env.example); both can also be entered in the sidebar.
"""
from __future__ import annotations

import html
import json
import os
import platform
import socket
import time
from datetime import datetime

import altair as alt
import pandas as pd
import psutil
import requests
import streamlit as st
from dotenv import load_dotenv

load_dotenv()  # read .env if present

HISTORY_LEN = 120                    # samples kept for the charts
EVENT_LOG_LEN = 100                  # events kept in the log
CPU_SAMPLE_SECONDS = 0.5             # CPU is measured over this window (smoother, independent of other calls)
SUSTAIN_SAMPLES = 3                  # consecutive samples above the threshold before an alert fires
DISK_PATH = os.path.abspath(os.sep)  # root of the current volume

ACCENT, DANGER, MUTED = "#7c5ce0", "#d9534f", "#8a8a96"

st.set_page_config(page_title="SysMonitor", layout="wide")

# ----------------------------------------------------------------- styling
# NOTE: no blank lines inside this block - Markdown would end the HTML block.
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap');
:root { --bg:#0b0b0e; --panel:rgba(255,255,255,.03); --line:rgba(255,255,255,.08);
        --accent:#7c5ce0; --danger:#d9534f; --text:#e4e4e7; --muted:#8a8a96; }
html, body, [class*="css"], .stApp { font-family:'IBM Plex Sans','Segoe UI',system-ui,sans-serif; }
.stApp { background: radial-gradient(1200px 500px at 85% -10%, rgba(124,92,224,.10), transparent 60%), var(--bg); }
#MainMenu, footer, [data-testid="stDeployButton"] { visibility:hidden; }
header[data-testid="stHeader"] { background:transparent; }
.block-container { padding-top:2.2rem; max-width:1440px; }
/* header */
.hdr { display:flex; justify-content:space-between; align-items:flex-end; padding-bottom:18px; border-bottom:1px solid var(--line); margin-bottom:18px; }
.hdr-title { font-size:1.7rem; font-weight:600; color:#fff; letter-spacing:-.01em; }
.hdr-sub { color:var(--muted); font-size:.85rem; margin-top:4px; display:flex; gap:18px; flex-wrap:wrap; }
.badge { border:1px solid rgba(124,92,224,.55); color:#b7a6f5; background:rgba(124,92,224,.10); border-radius:999px; padding:3px 12px; font-size:.78rem; }
.meta { color:var(--muted); font-size:.82rem; padding-top:10px; display:flex; gap:22px; flex-wrap:wrap; }
.meta b { color:var(--text); font-weight:500; font-family:'IBM Plex Mono',monospace; }
.section { color:var(--muted); font-size:.82rem; margin:30px 0 10px; padding-top:14px; border-top:1px solid var(--line); }
/* metric cards */
.card { background:var(--panel); border:1px solid var(--line); border-radius:8px; padding:16px 18px 14px; backdrop-filter:blur(6px); }
.card.breach { border-color:rgba(217,83,79,.55); box-shadow:0 0 0 1px rgba(217,83,79,.15), 0 0 28px rgba(217,83,79,.08); }
.card-label { color:var(--muted); font-size:.82rem; }
.card-value { color:#fff; font-family:'IBM Plex Mono',monospace; font-size:2rem; font-weight:500; line-height:1.25; margin-top:6px; }
.card-value small { color:var(--muted); font-size:1rem; margin-left:2px; }
.card-detail { color:var(--muted); font-size:.78rem; margin-top:2px; font-family:'IBM Plex Mono',monospace; }
.bar { height:3px; background:rgba(255,255,255,.07); border-radius:2px; margin-top:14px; overflow:hidden; }
.bar span { display:block; height:100%; background:var(--accent); box-shadow:0 0 10px rgba(124,92,224,.7); }
.card.breach .bar span { background:var(--danger); box-shadow:0 0 10px rgba(217,83,79,.6); }
.alert { border:1px solid rgba(217,83,79,.45); border-left:3px solid var(--danger); background:rgba(217,83,79,.07); color:#f0c4c3; border-radius:6px; padding:10px 14px; margin:12px 0 14px; font-size:.88rem; }
.alert b { color:#fff; font-weight:600; margin-right:10px; }
/* chart panels and event log */
.panel-head { display:flex; justify-content:space-between; color:var(--text); font-size:.9rem; margin:4px 0 8px; }
.panel-head span:last-child { color:var(--muted); font-family:'IBM Plex Mono',monospace; font-size:.82rem; }
.log { border:1px solid var(--line); border-radius:8px; background:var(--panel); font-family:'IBM Plex Mono',monospace; font-size:.78rem; }
.log-row { display:grid; grid-template-columns:84px 64px 1fr; gap:10px; padding:7px 14px; border-bottom:1px solid rgba(255,255,255,.05); }
.log-row:last-child { border-bottom:0; }
.log-ts { color:var(--muted); }
.lvl-info { color:#a99bea; } .lvl-warn { color:#d3a24a; } .lvl-error { color:#e5706c; }
.log-msg { color:var(--text); word-break:break-word; }
.log-empty { color:var(--muted); padding:14px; }
/* sidebar */
section[data-testid="stSidebar"] { background:#0e0e12; border-right:1px solid var(--line); }
.sb-brand { color:#fff; font-weight:600; font-size:1.05rem; }
.sb-group { color:var(--muted); font-size:.8rem; margin:22px 0 4px; padding-top:12px; border-top:1px solid var(--line); }
.note { font-size:.8rem; padding:8px 10px; border-radius:6px; margin-top:8px; border:1px solid var(--line); }
.note.ok { color:#b7a6f5; border-color:rgba(124,92,224,.45); background:rgba(124,92,224,.08); }
.note.err { color:#f0c4c3; border-color:rgba(217,83,79,.45); background:rgba(217,83,79,.07); }
[data-testid="stWidgetLabel"] p { color:var(--muted); font-size:.82rem; }
div[data-baseweb="input"], div[data-baseweb="base-input"] { background:#15151a !important; border-radius:6px; }
div[data-baseweb="input"] { border:1px solid rgba(255,255,255,.09); }
div[data-baseweb="input"]:focus-within { border-color:var(--accent); box-shadow:0 0 0 1px rgba(124,92,224,.45); }
/* flat enterprise buttons */
.stButton > button, .stDownloadButton > button, button[data-testid="stBaseButton-secondary"] {
  background:#15151a; color:var(--text); border:1px solid rgba(255,255,255,.12); border-radius:6px;
  font-weight:500; padding:.5rem 1rem; box-shadow:none; transition:background .15s ease, border-color .15s ease, box-shadow .15s ease; }
.stButton > button:hover, .stDownloadButton > button:hover, button[data-testid="stBaseButton-secondary"]:hover {
  background:rgba(124,92,224,.14); border-color:rgba(124,92,224,.65); color:#fff; box-shadow:0 0 0 1px rgba(124,92,224,.25), 0 0 18px rgba(124,92,224,.18); }
.stButton > button:active, .stDownloadButton > button:active { background:rgba(124,92,224,.24); }
.stDownloadButton > button { width:100%; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)


# -------------------------------------------------------------------- data
def gb(value: int) -> float:
    """Bytes -> gigabytes, rounded."""
    return round(value / 1024 ** 3, 2)


def collect_metrics() -> dict:
    """Take one sample of CPU, RAM and disk usage."""
    mem, disk = psutil.virtual_memory(), psutil.disk_usage(DISK_PATH)
    return {
        "time": datetime.now(),
        "cpu": psutil.cpu_percent(interval=CPU_SAMPLE_SECONDS),
        "ram": mem.percent, "ram_used": gb(mem.used), "ram_total": gb(mem.total),
        "disk": disk.percent, "disk_used": gb(disk.used), "disk_total": gb(disk.total),
    }


def build_report(m: dict) -> dict:
    """Hardware status report for the JSON export (contains no credentials)."""
    try:
        freq = psutil.cpu_freq()  # not available on every platform/container
    except (OSError, NotImplementedError):
        freq = None
    return {
        "generated_at": m["time"].isoformat(timespec="seconds"),
        "host": {
            "name": socket.gethostname(),
            "os": platform.platform(),
            "uptime_hours": round((time.time() - psutil.boot_time()) / 3600, 2),
        },
        "cpu": {
            "percent": m["cpu"],
            "cores_physical": psutil.cpu_count(logical=False),
            "cores_logical": psutil.cpu_count(),
            "frequency_mhz": round(freq.current) if freq else None,
        },
        "ram": {"percent": m["ram"], "used_gb": m["ram_used"], "total_gb": m["ram_total"]},
        "disk": {"path": DISK_PATH, "percent": m["disk"], "used_gb": m["disk_used"], "total_gb": m["disk_total"]},
    }


# ---------------------------------------------------------------- event log
def log_event(level: str, message: str) -> None:
    """Append an entry to the in-session event log."""
    st.session_state.events.append((datetime.now().strftime("%H:%M:%S"), level, message))
    del st.session_state.events[:-EVENT_LOG_LEN]


# ---------------------------------------------------------------- Telegram
def server_secret(name: str) -> str:
    """Credential kept on the server: environment/.env first, then Streamlit secrets."""
    value = os.getenv(name, "")
    if value:
        return value
    try:
        return str(st.secrets.get(name, ""))
    except Exception:  # no secrets file configured
        return ""


def send_telegram(token: str, chat_id: str, text: str) -> tuple[bool, str]:
    """Send a message through the Telegram Bot API. Returns (success, detail)."""
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=10)
        if resp.ok:
            return True, "OK"
        return False, f"HTTP {resp.status_code}: {resp.text[:150]}"
    except requests.RequestException as exc:
        return False, str(exc).replace(token, "***")  # never leak the token


def handle_alerts(m: dict, threshold: int, cooldown_min: int, token: str, chat_id: str) -> list:
    """Check CPU/RAM against the threshold, log state changes and notify Telegram.
    Returns the (metric, value) pairs that exceeded the threshold for SUSTAIN_SAMPLES samples in a row."""
    over = [(name, m[key]) for name, key in (("CPU", "cpu"), ("RAM", "ram")) if m[key] > threshold]
    # Debounce: one-off spikes must not raise an alert, the breach has to last several samples in a row
    st.session_state.breach_streak = st.session_state.breach_streak + 1 if over else 0
    breached = over if st.session_state.breach_streak >= SUSTAIN_SAMPLES else []
    was_breached = st.session_state.in_breach
    st.session_state.in_breach = bool(breached)

    if not breached:
        if was_breached:
            log_event("INFO", "All monitored metrics are back below the threshold")
        return breached

    summary = ", ".join(f"{name} {value:.1f}%" for name, value in breached)
    if not was_breached:  # log once per incident, not on every sample
        log_event("WARN", f"Threshold {threshold}% exceeded: {summary}")
    if not (token and chat_id):
        if not was_breached:
            log_event("WARN", "Telegram is not configured, notification skipped")
        return breached

    # Anti-spam: at most one notification per cooldown period
    if time.time() - st.session_state.last_alert < cooldown_min * 60:
        return breached

    text = "\n".join(
        [f"SysMonitor alert on {socket.gethostname()}"]
        + [f"{name}: {value:.1f}% (threshold {threshold}%)" for name, value in breached]
        + [f"Time: {datetime.now():%Y-%m-%d %H:%M:%S}"]
    )
    ok, detail = send_telegram(token, chat_id, text)
    st.session_state.last_alert = time.time()  # also on failure, so errors are not retried every sample
    log_event("INFO" if ok else "ERROR", "Telegram alert delivered" if ok else f"Telegram delivery failed: {detail}")
    return breached


# ------------------------------------------------------------------ widgets
def metric_card(label: str, value: float, detail: str, bar: float, breach: bool = False, text: str | None = None) -> str:
    """HTML for one metric card (single line: Markdown would break on blank lines)."""
    shown = f"{value:.1f}<small>%</small>" if text is None else text
    return (
        f'<div class="card{" breach" if breach else ""}"><div class="card-label">{label}</div>'
        f'<div class="card-value">{shown}</div><div class="card-detail">{detail}</div>'
        f'<div class="bar"><span style="width:{max(0.0, min(bar, 100.0)):.1f}%"></span></div></div>'
    )


def make_chart(df: pd.DataFrame, column: str, threshold: int | None = None) -> alt.Chart:
    """Area chart on a fixed 0-100% axis with an optional dashed threshold line."""
    fill = alt.Gradient(
        gradient="linear", x1=1, x2=1, y1=1, y2=0,
        stops=[alt.GradientStop(color="rgba(124,92,224,0.0)", offset=0),
               alt.GradientStop(color="rgba(124,92,224,0.32)", offset=1)],
    )
    y_scale = alt.Scale(domain=[0, 100])
    area = (
        alt.Chart(df)
        .mark_area(color=fill, interpolate="monotone", line={"color": ACCENT, "strokeWidth": 1.6})
        .encode(
            x=alt.X("time:T", title=None, axis=alt.Axis(format="%H:%M:%S", tickCount=4)),
            y=alt.Y(f"{column}:Q", title=None, scale=y_scale,
                    axis=alt.Axis(values=[0, 25, 50, 75, 100], labelExpr="datum.value + '%'")),
        )
    )
    chart = area
    if threshold is not None:
        rule = (
            alt.Chart(pd.DataFrame({"limit": [threshold]}))
            .mark_rule(color=DANGER, strokeDash=[4, 4], strokeWidth=1)
            .encode(y=alt.Y("limit:Q", scale=y_scale))
        )
        chart = area + rule
    return (
        chart.properties(height=200, width="container")
        .configure(background="transparent")
        .configure_view(fill="rgba(255,255,255,0.025)", stroke="rgba(255,255,255,0.08)")
        .configure_axis(domain=False, tickColor="transparent", gridColor="rgba(255,255,255,0.05)",
                        labelColor=MUTED, labelFontSize=10, labelFont="IBM Plex Mono, monospace", labelPadding=6)
        .configure_axisX(grid=False)
    )


def render_log() -> None:
    """Newest-first event log."""
    events = st.session_state.events[-12:][::-1]
    if not events:
        st.markdown('<div class="log"><div class="log-empty">No events recorded.</div></div>', unsafe_allow_html=True)
        return
    rows = "".join(
        f'<div class="log-row"><span class="log-ts">{ts}</span>'
        f'<span class="lvl-{level.lower()}">{level.lower()}</span>'
        f'<span class="log-msg">{html.escape(msg)}</span></div>'
        for ts, level, msg in events
    )
    st.markdown(f'<div class="log">{rows}</div>', unsafe_allow_html=True)


# ------------------------------------------------------------------ sidebar
st.session_state.setdefault("history", [])
st.session_state.setdefault("events", [])
st.session_state.setdefault("last_alert", 0.0)
st.session_state.setdefault("in_breach", False)
st.session_state.setdefault("breach_streak", 0)

with st.sidebar:
    st.markdown('<div class="sb-brand">SysMonitor</div>', unsafe_allow_html=True)
    st.markdown('<div class="sb-group">Alerting</div>', unsafe_allow_html=True)
    threshold = st.slider("Alert threshold", 50, 95, 85, format="%d%%",
                          help="Notify when CPU or RAM usage exceeds this value.")
    cooldown = st.number_input("Cooldown (minutes)", 1, 60, 5,
                               help="Minimum time between two Telegram notifications.")
    st.markdown('<div class="sb-group">Collection</div>', unsafe_allow_html=True)
    refresh = st.select_slider("Refresh interval (seconds)", options=[1, 2, 3, 5, 10], value=2)
    st.markdown('<div class="sb-group">Telegram</div>', unsafe_allow_html=True)
    env_token, env_chat = server_secret("TELEGRAM_BOT_TOKEN"), server_secret("TELEGRAM_CHAT_ID")
    # Server-side values are not sent to the browser: the fields stay empty and act as an override.
    token = st.text_input("Bot token", type="password",
                          placeholder="Using server configuration" if env_token else "123456:ABC-DEF...") or env_token
    chat_id = st.text_input("Chat ID",
                            placeholder="Using server configuration" if env_chat else "e.g. 123456789") or env_chat
    if st.button("Send test message"):
        if token and chat_id:
            ok, detail = send_telegram(token, chat_id, f"SysMonitor test message from {socket.gethostname()}")
            log_event("INFO" if ok else "ERROR", "Test message delivered" if ok else f"Test message failed: {detail}")
            st.markdown(
                '<div class="note ok">Test message delivered.</div>' if ok
                else f'<div class="note err">Delivery failed: {html.escape(detail)}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown('<div class="note err">Bot token and Chat ID are required.</div>', unsafe_allow_html=True)

# ------------------------------------------------------------------- header
st.markdown(
    f'<div class="hdr"><div><div class="hdr-title">SysMonitor</div>'
    f'<div class="hdr-sub"><span>Host {html.escape(socket.gethostname())}</span>'
    f'<span>{html.escape(platform.system())} {html.escape(platform.release())}</span>'
    f'<span>Volume {html.escape(DISK_PATH)}</span></div></div><div class="badge">Live</div></div>',
    unsafe_allow_html=True,
)


@st.fragment(run_every=refresh)  # re-runs on its own without reloading the page
def live_dashboard(threshold: int, cooldown: int, token: str, chat_id: str, refresh: int) -> None:
    m = collect_metrics()
    history = st.session_state.history
    prev = history[-1] if history else m
    history.append(m)
    del history[:-HISTORY_LEN]
    peak = {k: max(h[k] for h in history) for k in ("cpu", "ram", "disk")}

    breached = handle_alerts(m, threshold, cooldown, token, chat_id)
    over = {name for name, _ in breached}

    # Toolbar: status line on the left, export on the right
    info, export = st.columns([4, 1])
    armed = "armed" if token and chat_id else "not configured"
    info.markdown(
        f'<div class="meta"><span>Last sample <b>{m["time"]:%H:%M:%S}</b></span>'
        f'<span>Interval <b>{refresh}s</b></span><span>Threshold <b>{threshold}%</b></span>'
        f'<span>Telegram <b>{armed}</b></span></div>',
        unsafe_allow_html=True,
    )
    export.download_button(
        "Export JSON report",
        data=json.dumps(build_report(m), ensure_ascii=False, indent=2),
        file_name=f"hw_report_{m['time']:%Y%m%d_%H%M%S}.json",
        mime="application/json",
        key="export",
    )

    if breached:
        detail = ", ".join(f"{n} at {v:.1f}%" for n, v in breached)
        st.markdown(f'<div class="alert"><b>Threshold exceeded</b>{detail} (limit {threshold}%)</div>', unsafe_allow_html=True)

    # Metric cards
    c1, c2, c3, c4 = st.columns(4)
    c1.markdown(metric_card("CPU usage", m["cpu"], f'delta {m["cpu"] - prev["cpu"]:+.1f} pp, peak {peak["cpu"]:.1f}%',
                            m["cpu"], "CPU" in over), unsafe_allow_html=True)
    c2.markdown(metric_card("Memory usage", m["ram"], f'{m["ram_used"]:.1f} / {m["ram_total"]:.1f} GB, peak {peak["ram"]:.1f}%',
                            m["ram"], "RAM" in over), unsafe_allow_html=True)
    c3.markdown(metric_card("Disk usage", m["disk"], f'{m["disk_used"]:.0f} / {m["disk_total"]:.0f} GB on {html.escape(DISK_PATH)}',
                            m["disk"]), unsafe_allow_html=True)
    top = max(m["cpu"], m["ram"])
    c4.markdown(metric_card("Status", top, f"highest of CPU and RAM {top:.1f}%, limit {threshold}%",
                            top, bool(breached), text="Alert" if breached else "Normal"), unsafe_allow_html=True)

    # Live charts
    st.markdown(f'<div class="section">Time series, last {len(history)} samples</div>', unsafe_allow_html=True)
    df = pd.DataFrame(history)
    for col, (title, key, limit) in zip(
        st.columns(3), (("CPU utilization", "cpu", threshold), ("Memory utilization", "ram", threshold), ("Disk utilization", "disk", None))
    ):
        col.markdown(f'<div class="panel-head"><span>{title}</span><span>{m[key]:.1f}%</span></div>', unsafe_allow_html=True)
        col.altair_chart(make_chart(df, key, limit), theme=None)

    st.markdown('<div class="section">Event log</div>', unsafe_allow_html=True)
    render_log()


live_dashboard(threshold, cooldown, token, chat_id, refresh)
