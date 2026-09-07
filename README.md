# Launch Dashboard

A minimal localhost web dashboard for monitoring your macOS **launchd** agents. Reads your `~/Library/LaunchAgents/com.igorcleto.*.plist` files automatically and shows each job's schedule, last run status, next execution time, and log output — all in one dark-themed UI.

![python](https://img.shields.io/badge/python-3.8+-3776ab?style=flat&logo=python&logoColor=white)
![flask](https://img.shields.io/badge/flask-3.0-000?style=flat&logo=flask)

## Features

- **Human-readable schedule** — "Every Tuesday at 11:30" instead of a raw `StartCalendarInterval`
- **Live status** — OK / Failed / Waiting, from log content and `launchctl` exit code
- **Relative times** — "next run in 4d 14h", "last run 5min ago"
- **Colored logs** — green for success lines, red for errors, yellow for warnings
- **Run now** — triggers any agent immediately via `launchctl start`
- **Clear log** — wipes the log file with one click
- **Stats bar** — total jobs, OK count, failed count at a glance
- **Auto-refresh** every 60 seconds

## Setup

```bash
pip install flask
./launch.sh          # boots app.py (if down) and opens the browser
# or: python3 app.py  → http://localhost:5555
```

## How it works

On every page load the dashboard scans `~/Library/LaunchAgents/` for plists prefixed
`com.igorcleto.`, parses each one, and renders it as a card. The schedule comes from the
plist's `StartCalendarInterval` (`Weekday` / `Day` / `Hour` / `Minute`); logs come from
`StandardOutPath` / `StandardErrorPath` (with a `LOG=/path` fallback parsed from a
`bash -c` command). "Run now" calls `launchctl start <label>`.

## Adding friendly names

By default, the job name is derived from the plist label. To override it, edit `JOB_NAMES`
at the top of `app.py`:

```python
JOB_NAMES = {
    "com.igorcleto.barbeiro": "Book beard — Heron Barbearia",
}
```

## Not meant to run 24/7

Start it when you need it, stop it when done (there is also an **Encerrar** button in the UI):

```bash
./launch.sh
kill $(lsof -ti:5555)
```
