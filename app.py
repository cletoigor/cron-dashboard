"""
Cron Dashboard — localhost:5555
"""

import os
import re
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

from croniter import croniter
from dotenv import load_dotenv
from flask import Flask, jsonify, render_template_string, request

load_dotenv()

app = Flask(__name__)

# Nomes amigáveis opcionais para comandos específicos
JOB_NAMES = {
    "schedule_recurring.py": "Agendar barba — Heron Barbearia",
}

DAYS_PT = {
    0: "domingo", 1: "segunda-feira", 2: "terça-feira",
    3: "quarta-feira", 4: "quinta-feira", 5: "sexta-feira",
    6: "sábado", 7: "domingo",
}
MONTHS_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril",
    5: "maio", 6: "junho", 7: "julho", 8: "agosto",
    9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def cron_to_human(expr: str) -> str:
    try:
        parts = expr.split()
        if len(parts) != 5:
            return expr
        mn, hr, dom, month, dow = parts

        # Time part
        if mn == "*" and hr == "*":
            time_part = "todo minuto"
        elif mn.startswith("*/"):
            time_part = f"a cada {mn[2:]} minutos"
        elif hr.startswith("*/"):
            time_part = f"a cada {hr[2:]} horas"
        else:
            try:
                time_part = f"às {int(hr):02d}:{int(mn):02d}"
            except ValueError:
                time_part = f"às {hr}:{mn}"

        # Frequency part
        if dow != "*":
            days = []
            for d in dow.split(","):
                d = d.strip()
                if "-" in d:
                    start, end = d.split("-")
                    days += [DAYS_PT.get(i, str(i)) for i in range(int(start), int(end) + 1)]
                else:
                    days.append(DAYS_PT.get(int(d), d))
            freq = "toda " + " e ".join(days)
        elif dom != "*":
            freq = f"todo dia {dom} do mês"
        elif month != "*":
            m_name = MONTHS_PT.get(int(month), month)
            freq = f"em {m_name}"
        else:
            freq = "todo dia"

        if time_part == "todo minuto":
            return "A cada minuto"
        return f"{freq.capitalize()} {time_part}"
    except Exception:
        return expr


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
        return [], "none", "Nunca"

    mtime = datetime.fromtimestamp(os.path.getmtime(log_file))
    size = os.path.getsize(log_file)

    try:
        with open(log_file, errors="replace") as f:
            raw = f.read()
    except Exception:
        return [], "none", time_ago(mtime)

    lines = raw.splitlines()
    last_run = time_ago(mtime)

    # Colorize lines
    colored = []
    overall = "ok"
    for text in lines[-80:]:
        low = text.lower()
        if any(w in low for w in ["traceback", "exception", "error:", "erro:", "failed"]):
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


def parse_crontab():
    try:
        result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
        lines = result.stdout.splitlines() if result.returncode == 0 else []
    except Exception:
        lines = []

    jobs = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue

        cron_expr = " ".join(parts[:5])
        full_command = parts[5]

        log_match = re.search(r'>>\s*(\S+)', full_command)
        log_file = log_match.group(1) if log_match else None

        command = re.sub(r'\s*>>\s*\S+\s*2>&1', '', full_command).strip()
        command = re.sub(r'\s*2>&1', '', command).strip()

        name = next(
            (n for key, n in JOB_NAMES.items() if key in command),
            Path(command.split()[-1]).name if command.split() else command[:50],
        )

        try:
            cron_obj = croniter(cron_expr, datetime.now())
            next_dt = cron_obj.get_next(datetime)
            next_abs = next_dt.strftime("%d/%m %H:%M")
            next_rel = time_until(next_dt)
        except Exception:
            next_abs = next_rel = "—"

        log_lines, status, last_run, *rest = parse_log(log_file)
        log_size = rest[0] if rest else 0

        jobs.append({
            "name": name,
            "cron": cron_expr,
            "human": cron_to_human(cron_expr),
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
<title>Cron Dashboard</title>
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

/* ── Header ── */
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

/* ── Stats bar ── */
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

/* ── Main layout ── */
main { padding: 24px 28px; display: grid; gap: 16px; max-width: 1100px; }

/* ── Card ── */
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

/* ── Meta row ── */
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

/* ── Command ── */
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

/* ── Actions ── */
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

/* ── Log ── */
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

/* ── Empty ── */
.empty-state {
  padding: 60px 32px; text-align: center;
  color: var(--muted); font-size: 15px;
}

/* ── Spinner ── */
@keyframes spin { to { transform: rotate(360deg); } }
.spinner { display: inline-block; width: 12px; height: 12px; border: 2px solid var(--border);
           border-top-color: var(--green); border-radius: 50%; animation: spin .7s linear infinite; }
</style>
</head>
<body>

<header>
  <div class="logo">
    <span class="logo-icon">⏱</span>
    <span>Cron Dashboard</span>
  </div>
  <div class="header-right">
    <span class="clock" id="clock"></span>
    <button class="refresh-btn" onclick="location.reload()">↺ Atualizar</button>
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
    <button class="run-btn" onclick="runJob({{ loop.index0 }}, this)">▶ Executar agora</button>
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
<div class="card"><div class="empty-state">Nenhum job no crontab ainda.<br><small style="font-size:12px;margin-top:8px;display:block">Adicione entradas com <code>crontab -e</code></small></div></div>
{% endif %}
</main>

<script>
// Live clock
function updateClock() {
  const now = new Date();
  document.getElementById('clock').textContent =
    now.toLocaleDateString('pt-BR') + ' ' + now.toLocaleTimeString('pt-BR');
}
setInterval(updateClock, 1000);
updateClock();

// Auto-refresh page every 60s
setTimeout(() => location.reload(), 60000);

// Run job now
function runJob(idx, btn) {
  const status = document.getElementById('run-status-' + idx);
  btn.disabled = true;
  status.innerHTML = '<span class="spinner"></span> executando...';
  fetch('/run/' + idx, { method: 'POST' })
    .then(r => r.json())
    .then(data => {
      if (data.ok) {
        status.textContent = '✓ Iniciado';
        status.style.color = 'var(--green)';
        setTimeout(() => location.reload(), 3000);
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

// Clear log
function clearLog(logFile, btn) {
  if (!confirm('Limpar o log ' + logFile + '?')) return;
  fetch('/clear-log', { method: 'POST', headers: {'Content-Type':'application/json'},
                        body: JSON.stringify({log_file: logFile}) })
    .then(r => r.json())
    .then(data => { if (data.ok) location.reload(); });
}

// Scroll log boxes to bottom
document.querySelectorAll('.log-box').forEach(el => el.scrollTop = el.scrollHeight);
</script>

</body>
</html>
"""


def get_jobs():
    return parse_crontab()


@app.route("/")
def index():
    jobs = get_jobs()
    return render_template_string(HTML, jobs=jobs)


@app.route("/run/<int:job_idx>", methods=["POST"])
def run_job(job_idx):
    jobs = get_jobs()
    if job_idx >= len(jobs):
        return jsonify({"ok": False, "error": "job não encontrado"})
    job = jobs[job_idx]
    cmd = job["command"]
    try:
        log_file = job.get("log_file")
        if log_file:
            full_cmd = f"{cmd} >> {log_file} 2>&1"
        else:
            full_cmd = cmd
        subprocess.Popen(full_cmd, shell=True, start_new_session=True)
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


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 5555))
    print(f"Dashboard: http://{host}:{port}")
    app.run(host=host, port=port, debug=False)
