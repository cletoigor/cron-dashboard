# Cron Dashboard

A minimal localhost web dashboard to monitor your crontab jobs — logs, status, next run, and quick actions.

![dark theme dashboard](https://img.shields.io/badge/theme-dark-0d1117?style=flat)
![python](https://img.shields.io/badge/python-3.8+-3776ab?style=flat&logo=python&logoColor=white)
![flask](https://img.shields.io/badge/flask-3.0-000?style=flat&logo=flask)

## Features

- **Human-readable schedule** — "Every Tuesday at 11:30" instead of `30 11 * * 2`
- **Live status** — OK / Failed / Waiting, inferred from log content
- **Relative times** — "next run in 4d 14h", "last run 5min ago"
- **Colored logs** — green for success lines, red for errors, yellow for warnings
- **Run now** button — executes the job immediately without waiting for the schedule
- **Clear log** button — wipes the log file
- **Stats bar** — total jobs, OK count, failed count
- **Auto-refresh** every 60 seconds

## Setup

```bash
pip install flask croniter
python3 app.py
# open http://localhost:5555
```

## How it works

The dashboard reads your crontab with `crontab -l` automatically. Any job that redirects output to a log file (`>> /path/to/file.log 2>&1`) will have its log displayed.

```cron
30 11 * * 2  python3 ~/automacoes/myjob.py >> ~/automacoes/myjob.log 2>&1
```

## Adding friendly names

Edit `JOB_NAMES` at the top of `app.py`:

```python
JOB_NAMES = {
    "myjob.py": "My automation — friendly name",
}
```

## Not meant to run 24/7

Start it when you need it, kill it when done:

```bash
# start
python3 app.py &

# stop
kill $(lsof -ti:5555)
```
