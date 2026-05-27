# Cron Dashboard

A minimal localhost web dashboard for monitoring your crontab jobs. Reads `crontab -l` automatically and shows each job's schedule, last run status, next execution time, and log output — all in one dark-themed UI.

![python](https://img.shields.io/badge/python-3.8+-3776ab?style=flat&logo=python&logoColor=white)
![flask](https://img.shields.io/badge/flask-3.0-000?style=flat&logo=flask)

## Features

- **Human-readable schedule** — "Every Friday at 09:30" instead of `30 9 * * 5`
- **Live status** — OK / Failed / Waiting, inferred from log content
- **Relative times** — "next run in 4d 14h", "last run 5min ago"
- **Colored logs** — green for success lines, red for errors, yellow for warnings
- **Run now** — executes any job immediately without waiting for its schedule
- **Clear log** — wipes the log file with one click
- **Stats bar** — total jobs, OK count, failed count at a glance
- **Auto-refresh** every 60 seconds

## Setup

```bash
pip install flask croniter
python3 app.py
# open http://localhost:5555
```

## How it works

The dashboard reads your crontab via `crontab -l` on every page load. Jobs that redirect output to a log file get their logs displayed inline:

```cron
30 9 * * 5  python3 ~/automacoes/schedule_recurring.py >> ~/automacoes/barber.log 2>&1
```

## Adding friendly names

By default, the job name is derived from the script filename. To override it, edit `JOB_NAMES` at the top of `app.py`:

```python
JOB_NAMES = {
    "schedule_recurring.py": "Book beard — Heron Barbearia",
}
```

## Not meant to run 24/7

Start it when you need it, stop it when done:

```bash
python3 app.py &
kill $(lsof -ti:5555)
```
