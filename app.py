"""
Cron Dashboard — localhost:5555
Reads launchd LaunchAgents instead of crontab.
"""

import calendar
import json
import os
import plistlib
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from flask import Flask, jsonify, render_template_string, request

app = Flask(__name__)

LAUNCHD_AGENTS_DIR = os.path.expanduser("~/Library/LaunchAgents")
LAUNCHD_PREFIX = "com.igorcleto."

JOB_NAMES = {
    "com.igorcleto.barbeiro": "Agendar barba — Heron Barbearia",
    "com.igorcleto.reembolso-academia": "Reembolso academia — Revelo",
    "com.igorcleto.garmin-dashboard": "Garmin Dashboard — Saude e Treino",
    "com.igorcleto.nutri-dash": "Nutri-Dash — Dieta flexível",
}

# launchd weekday: 0=Sun, 1=Mon, 2=Tue, 3=Wed, 4=Thu, 5=Fri, 6=Sat
LAUNCHD_DAYS = {
    0: "domingo", 1: "segunda-feira", 2: "terça-feira",
    3: "quarta-feira", 4: "quinta-feira", 5: "sexta-feira", 6: "sábado",
}
MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def sci_to_human(sci: dict) -> str:
    """Convert StartCalendarInterval dict to human-readable Portuguese string."""
    if not sci:
        return "Sem agendamento"
    hour = sci.get("Hour", 0)
    minute = sci.get("Minute", 0)
    time_str = f"às {hour:02d}:{minute:02d}"
    weekday = sci.get("Weekday")
    dom = sci.get("Day")
    month = sci.get("Month")
    if weekday is not None:
        day_name = LAUNCHD_DAYS.get(weekday, str(weekday))
        return f"Toda {day_name} {time_str}"
    if dom is not None:
        return f"Todo dia {dom} do mês {time_str}"
    if month is not None:
        return f"Em {MONTHS_PT.get(month, month)} {time_str}"
    return f"Todo dia {time_str}"


def sci_label(sci: dict) -> str:
    """Short schedule label for the cron pill."""
    if not sci:
        return "—"
    parts = []
    if "Weekday" in sci:
        parts.append(f"wday={sci['Weekday']}")
    if "Day" in sci:
        parts.append(f"dom={sci['Day']}")
    if "Hour" in sci:
        parts.append(f"h={sci['Hour']}")
    if "Minute" in sci:
        parts.append(f"m={sci['Minute']}")
    return " ".join(parts)


def next_sci_occurrence(sci: dict):
    """Return (abs_str, rel_str) for next run of a StartCalendarInterval job."""
    if not sci:
        return "—", "—"
    now = datetime.now()
    hour = sci.get("Hour", 0)
    minute = sci.get("Minute", 0)
    weekday = sci.get("Weekday")  # launchd: 0=Sun
    dom = sci.get("Day")

    if weekday is not None:
        # Convert launchd weekday (0=Sun) to Python weekday (0=Mon)
        py_wd = (weekday - 1) % 7
        days_ahead = (py_wd - now.weekday()) % 7
        if days_ahead == 0:
            candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if now >= candidate:
                days_ahead = 7
        next_dt = (now + timedelta(days=days_ahead)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
    elif dom is not None:
        # Procura o próximo mês (a partir do atual) que tenha o dia `dom`
        # e cuja ocorrência ainda esteja no futuro. Evita ValueError quando
        # dom > nº de dias do mês (ex.: Day=31 em fevereiro).
        year, month = now.year, now.month
        next_dt = None
        for _ in range(13):
            if dom <= calendar.monthrange(year, month)[1]:
                candidate = datetime(year, month, dom, hour, minute)
                if candidate > now:
                    next_dt = candidate
                    break
            month = month % 12 + 1
            if month == 1:
                year += 1
        if next_dt is None:
            return "—", "—"
    else:
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= candidate:
            candidate += timedelta(days=1)
        next_dt = candidate

    return next_dt.strftime("%d/%m %H:%M"), time_until(next_dt)


def time_ago(dt: datetime) -> str:
    diff = datetime.now() - dt
    s = int(diff.total_seconds())
    if s < 60:
        return f"há {s}s"
    if s < 3600:
        return f"há {s // 60}min"
    if s < 86400:
        return f"há {s // 3600}h"
    return f"há {s // 86400}d"


def time_until(dt: datetime) -> str:
    diff = dt - datetime.now()
    s = int(diff.total_seconds())
    if s < 0:
        return "agora"
    if s < 60:
        return f"em {s}s"
    if s < 3600:
        return f"em {s // 60}min"
    if s < 86400:
        h = s // 3600
        m = (s % 3600) // 60
        return f"em {h}h {m}min" if m else f"em {h}h"
    d = s // 86400
    h = (s % 86400) // 3600
    return f"em {d}d {h}h" if h else f"em {d}d"


def parse_log(log_file: str):
    if not log_file or not os.path.exists(log_file):
        return [], "none", "Nunca", 0

    mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
    size = os.path.getsize(log_file)

    try:
        with open(log_file, errors="replace") as f:
            raw = f.read()
    except Exception:
        return [], "none", time_ago(mtime), 0

    lines = raw.splitlines()
    last_run = time_ago(mtime)

    colored = []
    overall = "ok"
    for text in lines[-80:]:
        low = text.lower()
        if any(w in low for w in ["traceback", "exception", "error:", "erro:", "failed", "exit: 1"]):
            cls = "err"
            overall = "fail"
        elif "⚠" in text or "sem horário" in low or "warn" in low or "falha" in low:
            cls = "warn"
        elif "✓" in text or "agendado" in low or "total agendado" in low or "sucesso" in low:
            cls = "ok"
        else:
            cls = "dim"
        colored.append({"text": text, "cls": cls})

    return colored, overall, last_run, size


def get_launchd_exit_code(label: str):
    """Return last exit code from launchctl list, or None."""
    try:
        result = subprocess.run(
            ["launchctl", "list", label],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            m = re.search(r'"LastExitStatus"\s*=\s*(\d+)', result.stdout)
            if m:
                raw = int(m.group(1))
                return raw >> 8
    except Exception:
        pass
    return None


def load_plist(path: str) -> dict:
    try:
        with open(path, "rb") as f:
            return plistlib.load(f)
    except Exception:
        try:
            result = subprocess.run(
                ["plutil", "-convert", "json", "-o", "-", path],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                return json.loads(result.stdout)
        except Exception:
            pass
    return {}


def parse_launchd():
    jobs = []
    try:
        filenames = sorted(os.listdir(LAUNCHD_AGENTS_DIR))
    except Exception:
        return jobs

    for filename in filenames:
        if not (filename.startswith(LAUNCHD_PREFIX) and filename.endswith(".plist")):
            continue

        plist_path = os.path.join(LAUNCHD_AGENTS_DIR, filename)
        plist = load_plist(plist_path)
        if not plist:
            continue

        label = plist.get("Label", filename.replace(".plist", ""))
        sci = plist.get("StartCalendarInterval") or {}

        log_file = plist.get("StandardOutPath") or plist.get("StandardErrorPath")

        prog_args = plist.get("ProgramArguments", [])
        if len(prog_args) >= 3 and prog_args[1] == "-c":
            raw_cmd = prog_args[2]
            command = (raw_cmd[:120] + "…") if len(raw_cmd) > 120 else raw_cmd
            # Fallback: extract LOG=/path from bash -c command
            if not log_file:
                m = re.search(r'LOG=([^\s;]+)', raw_cmd)
                if m:
                    log_file = m.group(1).strip('"\'')
        else:
            raw_cmd = ""
            command = " ".join(prog_args)

        short = label[len(LAUNCHD_PREFIX):] if label.startswith(LAUNCHD_PREFIX) else label
        name = JOB_NAMES.get(label, short.replace("-", " ").title())
        human = sci_to_human(sci)
        pill = sci_label(sci)
        next_abs, next_rel = next_sci_occurrence(sci)

        log_lines, status, last_run, log_size = parse_log(log_file)

        exit_code = get_launchd_exit_code(label)
        if exit_code is not None and exit_code != 0:
            status = "fail"

        jobs.append({
            "name": name,
            "label": label,
            "cron": pill,
            "human": human,
            "command": command,
            "log_file": log_file,
            "next_abs": next_abs,
            "next_rel": next_rel,
            "last_run": last_run,
            "log_lines": log_lines,
            "log_size": f"{log_size / 1024:.1f} KB" if log_size else "—",
            "status": status,
        })

    return jobs


HTML = r"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Launch Dashboard</title>
<style>
:root {
  --bg:       #0d1117;
  --surface:  #161b22;
  --surface2: #1c2128;
  --border:   #30363d;
  --text:     #e6edf3;
  --muted:    #7d8590;
  --green:    #3fb950;
  --red:      #f85149;
  --yellow:   #d29922;
  --blue:     #58a6ff;
  --purple:   #bc8cff;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', system-ui, sans-serif;
       background: var(--bg); color: var(--text); min-height: 100vh; font-size: 14px; }

header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 0 28px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  position: sticky; top: 0; z-index: 10;
}
.logo { display: flex; align-items: center; gap: 10px; font-weight: 600; font-size: 15px; }
.logo-icon { font-size: 18px; }
.header-right { display: flex; align-items: center; gap: 16px; }
.clock { font-size: 12px; color: var(--muted); font-variant-numeric: tabular-nums; }
.refresh-btn {
  background: var(--surface2); border: 1px solid var(--border);
  color: var(--text); font-size: 12px; padding: 5px 12px;
  border-radius: 6px; cursor: pointer;
}
.refresh-btn:hover { background: var(--border); }
.shutdown-btn {
  background: var(--surface2); border: 1px solid var(--border);
  color: var(--red); font-size: 12px; padding: 5px 12px;
  border-radius: 6px; cursor: pointer; transition: all 0.15s;
}
.shutdown-btn:hover { background: rgba(248,113,113,0.1); border-color: var(--red); }

.stats-bar {
  display: flex; gap: 1px;
  background: var(--border);
  border-bottom: 1px solid var(--border);
}
.stat {
  flex: 1; background: var(--surface);
  padding: 12px 20px;
  display: flex; flex-direction: column; gap: 2px;
}
.stat-val { font-size: 22px; font-weight: 700; line-height: 1; }
.stat-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; }
.stat-val.green { color: var(--green); }
.stat-val.red   { color: var(--red); }
.stat-val.blue  { color: var(--blue); }

main { padding: 24px 28px; display: grid; gap: 16px; max-width: 1100px; }

.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  overflow: hidden;
}
.card-header {
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: flex-start;
  justify-content: space-between; gap: 12px;
}
.job-name { font-weight: 600; font-size: 15px; margin-bottom: 5px; }
.job-schedule {
  font-size: 13px; color: var(--blue);
  display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
}
.cron-pill {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11px; color: var(--muted);
  background: var(--surface2); border: 1px solid var(--border);
  padding: 2px 8px; border-radius: 4px;
}
.badge {
  padding: 3px 10px; border-radius: 99px;
  font-size: 11px; font-weight: 600;
  white-space: nowrap; flex-shrink: 0;
}
.badge-ok   { background: #0d2d1a; color: var(--green); border: 1px solid #1a5c35; }
.badge-fail { background: #2d0c0c; color: var(--red);   border: 1px solid #5c1a1a; }
.badge-none { background: var(--surface2); color: var(--muted); border: 1px solid var(--border); }

.meta-row {
  padding: 12px 18px;
  border-bottom: 1px solid var(--border);
  display: flex; flex-wrap: wrap; gap: 24px;
  background: var(--surface2);
}
.meta-item { display: flex; flex-direction: column; gap: 1px; }
.meta-label { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.meta-value { font-size: 13px; font-weight: 500; }
.meta-value.green  { color: var(--green); }
.meta-value.yellow { color: var(--yellow); }
.meta-value.muted  { color: var(--muted); }

.cmd-row {
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 8px;
}
.cmd-label { font-size: 10px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); flex-shrink: 0; }
.cmd-text {
  font-family: 'SF Mono', 'Fira Code', monospace;
  font-size: 11.5px; color: var(--muted);
  word-break: break-all; flex: 1;
}

.actions-row {
  padding: 10px 18px;
  border-bottom: 1px solid var(--border);
  display: flex; gap: 8px; align-items: center;
}
.run-btn {
  background: #1a2d1a; border: 1px solid #2a5c2a;
  color: var(--green); font-size: 12px; padding: 5px 14px;
  border-radius: 6px; cursor: pointer; font-weight: 500;
}
.run-btn:hover { background: #2a4a2a; }
.run-btn:disabled { opacity: .4; cursor: not-allowed; }
.clear-btn {
  background: var(--surface2); border: 1px solid var(--border);
  color: var(--muted); font-size: 12px; padding: 5px 14px;
  border-radius: 6px; cursor: pointer;
}
.clear-btn:hover { color: var(--text); border-color: var(--muted); }
.run-status { font-size: 12px; color: var(--muted); margin-left: 4px; }

.log-header {
  padding: 8px 18px;
  display: flex; align-items: center; justify-content: space-between;
}
.log-title { font-size: 11px; text-transform: uppercase; letter-spacing: .06em; color: var(--muted); }
.log-size  { font-size: 11px; color: var(--muted); }
.log-box {
  margin: 0 18px 16px;
  background: #010409;
  border: 1px solid var(--border);
  border-radius: 8px;
  max-height: 300px; overflow-y: auto;
  padding: 12px 14px;
}
.log-box pre {
  font-family: 'SF Mono', 'Fira Code', 'Cascadia Code', monospace;
  font-size: 12px; line-height: 1.6;
  white-space: pre-wrap; word-break: break-word;
}
.l-ok   { color: var(--green); }
.l-err  { color: var(--red); }
.l-warn { color: var(--yellow); }
.l-dim  { color: #4a5568; }
.no-log { padding: 16px 18px; color: var(--muted); font-size: 13px; font-style: italic; }

.empty-state {
  padding: 60px 32px; text-align: center;
  color: var(--muted); font-size: 15px;
}

@keyframes spin { to { transform: rotate(360deg); } }
.spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border);
           border-top-color: var(--green); border-radius: 50%; animation: spin .7s linear infinite; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <span class="logo-icon">🚀</span>
    <span>Launch Dashboard</span>
  </div>
  <div class="header-right">
    <span class="clock" id="clock"></span>
    <button class="refresh-btn" onclick="location.reload()">↺ Atualizar</button>
    <button class="shutdown-btn" onclick="doShutdown()">&#9632; Encerrar</button>
  </div>
</header>

<div class="stats-bar">
  <div class="stat">
    <span class="stat-val blue">{{ jobs|length }}</span>
    <span class="stat-label">Jobs agendados</span>
  </div>
  <div class="stat">
    <span class="stat-val green">{{ jobs|selectattr('status','eq','ok')|list|length }}</span>
    <span class="stat-label">Última execução OK</span>
  </div>
  <div class="stat">
    <span class="stat-val red">{{ jobs|selectattr('status','eq','fail')|list|length }}</span>
    <span class="stat-label">Com falha</span>
  </div>
  <div class="stat">
    <span class="stat-val" style="color:var(--muted)">{{ jobs|selectattr('status','eq','none')|list|length }}</span>
    <span class="stat-label">Nunca executado</span>
  </div>
</div>

<main>
{% if jobs %}
{% for job in jobs %}
<div class="card">

  <div class="card-header">
    <div>
      <div class="job-name">{{ job.name }}</div>
      <div class="job-schedule">
        {{ job.human }}
        <span class="cron-pill">{{ job.cron }}</span>
      </div>
    </div>
    <span class="badge badge-{{ job.status if job.status != 'none' else 'none' }}">
      {% if job.status == 'ok' %}✓ OK
      {% elif job.status == 'fail' %}✗ Falhou
      {% else %}— Aguardando
      {% endif %}
    </span>
  </div>

  <div class="meta-row">
    <div class="meta-item">
      <span class="meta-label">Próxima execução</span>
      <span class="meta-value green">{{ job.next_rel }}</span>
    </div>
    <div class="meta-item">
      <span class="meta-label">Data/hora</span>
      <span class="meta-value">{{ job.next_abs }}</span>
    </div>
    <div class="meta-item">
      <span class="meta-label">Última execução</span>
      <span class="meta-value {{ 'muted' if job.last_run == 'Nunca' else '' }}">{{ job.last_run }}</span>
    </div>
    {% if job.log_file %}
    <div class="meta-item">
      <span class="meta-label">Tamanho do log</span>
      <span class="meta-value muted">{{ job.log_size }}</span>
    </div>
    {% endif %}
  </div>

  <div class="cmd-row">
    <span class="cmd-label">cmd</span>
    <span class="cmd-text">{{ job.command }}</span>
  </div>

  <div class="actions-row">
    <button class="run-btn" onclick="runJob('{{ job.label }}', this)">▶ Executar agora</button>
    {% if job.log_file %}
    <button class="clear-btn" onclick="clearLog('{{ job.log_file }}', this)">⌫ Limpar log</button>
    {% endif %}
    <span class="run-status" id="run-status-{{ loop.index0 }}"></span>
  </div>

  {% if job.log_lines %}
  <div class="log-header">
    <span class="log-title">Log — últimas {{ job.log_lines|length }} linhas</span>
    <span class="log-size">{{ job.log_size }}</span>
  </div>
  <div class="log-box" id="log-{{ loop.index0 }}">
    <pre>{% for line in job.log_lines %}<span class="l-{{ line.cls }}">{{ line.text }}</span>
{% endfor %}</pre>
  </div>
  {% elif job.log_file %}
  <div class="no-log">Nenhuma execução registrada ainda.</div>
  {% else %}
  <div class="no-log">Sem arquivo de log configurado para este job.</div>
  {% endif %}

</div>
{% endfor %}
{% else %}
<div class="card"><div class="empty-state">Nenhum LaunchAgent encontrado em ~/Library/LaunchAgents/com.igorcleto.*<br><small style="font-size:12px;margin-top:8px;display:block">Adicione plists com prefixo <code>com.igorcleto.</code></small></div></div>
{% endif %}
</main>

<script>
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleDateString('pt-BR') + ' ' + now.toLocaleTimeString('pt-BR');
}
setInterval(updateClock, 1000);
updateClock();

setTimeout(() => location.reload(), 60000);

function runJob(label, btn) {
  const idx = btn.closest('.card').querySelector('.run-status').id.split('-').pop();
  const status = document.getElementById('run-status-' + idx);
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> executando...';
  fetch('/run/' + encodeURIComponent(label), { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        status.textContent = '✓ Iniciado';
        status.style.color = 'var(--green)';
        setTimeout(() => location.reload(), 4000);
      } else {
        status.textContent = '✗ ' + (data.error || 'erro');
        status.style.color = 'var(--red)';
        btn.disabled = false;
      }
    })
    .catch(() => {
      status.textContent = '✗ Erro de conexão';
      status.style.color = 'var(--red)';
      btn.disabled = false;
    });
}

function clearLog(logFile, btn) {
  if (!confirm('Limpar o log ' + logFile + '?')) return;
  fetch('/clear-log', { method: 'POST', headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({log_file: logFile}) })
    .then(r => r.json())
    .then(data => { if (data.ok) location.reload(); });
}

document.querySelectorAll('.log-box').forEach(el => el.scrollTop = el.scrollHeight);

async function doShutdown() {
  if (!confirm('Encerrar o Launch Dashboard?')) return;
  try { await fetch('/shutdown', {method: 'POST'}); } catch(e) {}
  document.body.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100vh;color:#7d8a9a;font-family:system-ui;font-size:16px;">Dashboard encerrado.</div>';
}
</script>

</body>
</html>
"""


def get_jobs():
    return parse_launchd()


@app.route("/")
def index():
    jobs = get_jobs()
    return render_template_string(HTML, jobs=jobs)


@app.route("/run/<label>", methods=["POST"])
def run_job(label):
    try:
        subprocess.Popen(
            ["launchctl", "start", label],
            start_new_session=True,
        )
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/clear-log", methods=["POST"])
def clear_log():
    data = request.get_json()
    log_file = data.get("log_file", "")
    if not log_file or not os.path.exists(log_file):
        return jsonify({"ok": False})
    try:
        open(log_file, "w").close()
        return jsonify({"ok": True})
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)})


@app.route("/shutdown", methods=["POST"])
def shutdown():
    import signal
    os.kill(os.getpid(), signal.SIGTERM)
    return jsonify(ok=True)


if __name__ == "__main__":
    print("Dashboard: http://localhost:5555")
    app.run(host="127.0.0.1", port=5555, debug=False)
