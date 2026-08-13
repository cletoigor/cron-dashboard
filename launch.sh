#!/bin/bash
# Sobe o Cron/Launch Dashboard (se ainda nao estiver no ar) e abre no navegador.
# Reusado pelo Cron-Dash.app (Dock) e pela skill /cron-dash.
DIR="/Users/igorcleto/cron_dashboard"
PY="/Library/Frameworks/Python.framework/Versions/3.8/bin/python3"
cd "$DIR" || exit 1
if ! lsof -ti:5555 >/dev/null 2>&1; then
  "$PY" "$DIR/app.py" >/tmp/cron_dash.log 2>&1 &
  for _ in $(seq 1 25); do
    lsof -ti:5555 >/dev/null 2>&1 && break
    sleep 0.3
  done
fi
open "http://localhost:5555"
