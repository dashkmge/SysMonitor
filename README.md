# SysMonitor

A compact system monitoring dashboard built with Python. It shows live CPU, memory and disk usage, lets you set an alert threshold, and sends a Telegram message when CPU or RAM goes above it.

Stack: **psutil** (system data), **Streamlit** (web UI and charts), **requests** (Telegram Bot API).

## Features

- Live CPU, memory and disk usage as metric cards and time-series charts (last 120 samples).
- Adjustable alert threshold (50-95%) and refresh interval (1-10 s).
- Telegram notification when CPU or RAM exceeds the threshold, with a cooldown to prevent spam.
- Event log that records threshold breaches, recoveries and Telegram delivery results.
- One-click export of a hardware status report as a JSON file.
- "Send test message" button to verify the Telegram setup.
- Dark, minimal interface with custom CSS.

## Project structure

```
sysmonitor/
├── app.py                  # the whole application
├── requirements.txt        # Python dependencies
├── start.bat / start.sh    # one-click launchers (Windows / Linux, macOS)
├── .env.example            # template for Telegram credentials
├── .gitignore              # keeps .env and secrets out of Git
└── .streamlit/
    └── config.toml         # base dark theme
```

## Quick start

Requires Python 3.9 or newer.

```bash
git clone https://github.com/<your-user>/sysmonitor.git
cd sysmonitor

python -m venv .venv
.venv\Scripts\activate            # Windows
# source .venv/bin/activate       # Linux / macOS

pip install -r requirements.txt
streamlit run app.py
```

The dashboard opens at http://localhost:8501. Monitoring works immediately; Telegram alerts need the setup below.

**One-click launch:** on Windows double-click `start.bat`; on Linux/macOS run `./start.sh`. On the first run it creates the virtual environment and installs the dependencies, then starts the app and keeps running while its window is open.

## Telegram setup

1. Open **@BotFather** in Telegram, send `/newbot` and follow the steps. You receive a **bot token**.
2. Open a chat with your new bot and send it any message (a bot cannot message you first).
3. Find your **chat ID**: open `https://api.telegram.org/bot<TOKEN>/getUpdates` and look for `"chat":{"id": ...}`, or message **@userinfobot**.
4. Give the credentials to the app in one of these ways:

| Method | How |
|---|---|
| `.env` file | Copy `.env.example` to `.env` and fill in the two values |
| Environment variables | `set TELEGRAM_BOT_TOKEN=...` (Windows) or `export TELEGRAM_BOT_TOKEN=...` (Linux/macOS), same for `TELEGRAM_CHAT_ID` |
| Streamlit secrets | `.streamlit/secrets.toml` with `TELEGRAM_BOT_TOKEN = "..."` and `TELEGRAM_CHAT_ID = "..."` (never commit this file) |
| Sidebar | Type them into the **Bot token** and **Chat ID** fields (kept only for the current browser session) |

Values from the server (`.env`, environment, secrets) are never sent to the browser. The sidebar fields stay empty and show "Using server configuration"; anything you type there overrides the server values.

Press **Send test message** in the sidebar to confirm everything works.

## Using the dashboard

### Sidebar

| Setting | Meaning |
|---|---|
| Alert threshold | CPU or RAM usage above this value counts as an incident |
| Cooldown (minutes) | Minimum time between two Telegram notifications |
| Refresh interval (seconds) | How often a new sample is taken and the charts update |
| Bot token / Chat ID | Telegram credentials (see above) |
| Send test message | Sends a test message and records the result in the event log |

### Main area

- **Status line:** time of the last sample, refresh interval, threshold and whether Telegram is configured.
- **Export JSON report:** downloads the current hardware state (see format below).
- **Metric cards:** CPU, Memory, Disk and Status. Each shows the current percentage and a usage bar. CPU shows the change since the previous sample (`pp` = percentage points) and the peak of the visible window; Memory and Disk show used / total gigabytes. The Status card shows the higher of CPU and RAM against the threshold. A card turns red when it exceeds the limit.
- **Time series:** one chart per metric on a fixed 0-100% scale. The dashed red line is the alert threshold (CPU and Memory).
- **Event log:** newest first. A breach is logged once per incident, not on every sample.

## How alerting works

1. Every refresh the app samples CPU (measured over a 0.5 s window), RAM and disk with `psutil`.
2. If CPU or RAM stays above the threshold for 3 samples in a row (this filters out one-off spikes; see `SUSTAIN_SAMPLES` in `app.py`), a `WARN` entry is logged and, when credentials are available, a message is sent through the Telegram Bot API (`sendMessage`).
3. After a notification (successful or not) the app stays silent for the cooldown period, even if the load stays high.
4. When both metrics drop below the threshold again, an `INFO` entry is logged.

Disk usage is displayed but does not trigger alerts.

Example message:

```
SysMonitor alert on my-pc
CPU: 91.2% (threshold 85%)
Time: 2026-11-06 14:32:10
```

## JSON report

```json
{
  "generated_at": "2026-11-06T14:32:10",
  "host": { "name": "my-pc", "os": "Windows-11-10.0.26100-SP0", "uptime_hours": 5.2 },
  "cpu": { "percent": 23.4, "cores_physical": 8, "cores_logical": 16, "frequency_mhz": 3200 },
  "ram": { "percent": 54.1, "used_gb": 8.6, "total_gb": 15.9 },
  "disk": { "path": "C:\\", "percent": 61.0, "used_gb": 290.3, "total_gb": 476.0 }
}
```

The report never contains credentials.

## Publishing the project

### 1. Put the code on GitHub

GitHub stores the code. It cannot run Streamlit apps itself (GitHub Pages only serves static files).

```bash
git init
git add .
git status                  # make sure .env is NOT in the list
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/<your-user>/sysmonitor.git
git push -u origin main
```

Create the empty repository on github.com first (without a README, since you already have one).

### 2. Run it online with Streamlit Community Cloud (free)

1. Sign in at https://share.streamlit.io with your GitHub account and allow access to the repository.
2. Click **Create app** (or **New app**), choose the repository, the `main` branch and the main file `app.py`.
3. Open **Advanced settings** and pick Python 3.11 or newer.
4. Click **Deploy**. After a few minutes the app is available at `https://<name>.streamlit.app`.
5. Later changes: push to GitHub and the app updates automatically.

Community Cloud is free for public apps. Free apps are shared and limited in resources (roughly 1 GB of memory), and an app that receives no traffic for 12 hours goes to sleep until someone opens it again.

### Read this before deploying

- **A hosted app monitors the server, not your computer.** `psutil` reads the machine the app runs on. On Community Cloud that is a shared cloud container, so you will see its numbers, not your PC's. To monitor your own computer, run the app locally.
- **Alerts only work while a browser tab is open.** Sampling happens inside the Streamlit session. Closing the tab stops monitoring. A sleeping cloud app does not monitor anything.
- **Never set `TELEGRAM_CHAT_ID` in the secrets of a public app.** Anyone with the link could press "Send test message" or trigger alerts to your chat. For a public demo there are two safe options: leave the secrets empty and let visitors enter their own token and chat ID in the sidebar, or store only `TELEGRAM_BOT_TOKEN` (one shared bot). In that case visitors press Start on your bot and type only their own chat ID. The token stays on the server and is never sent to the browser.
- **Never commit `.env` or `.streamlit/secrets.toml`.** If a token leaks, revoke it in @BotFather with `/revoke`.
- After the first successful deploy, pin versions in `requirements.txt` (`pip freeze`) so a new release cannot break the app unexpectedly.

### Other hosting options

Any service that can run a Python process or a Docker container works (your own server, a VPS, a container platform). You are then responsible for authentication, resources and cost.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Telegram is not configured" in the event log | Set the token and chat ID (see Telegram setup) |
| `Delivery failed: HTTP 401` | The bot token is wrong or was revoked |
| `Delivery failed: HTTP 400` ("chat not found") | Wrong chat ID, or you have not sent a message to the bot yet |
| Fonts look different | The UI loads IBM Plex from Google Fonts; offline it falls back to system fonts |
| Streamlit complains about an unknown parameter | Upgrade Streamlit: `pip install -U streamlit` (the dashboard needs 1.37 or newer) |

## License

Add a license of your choice (for example MIT) before publishing.
