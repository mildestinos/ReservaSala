from datetime import datetime, date, timedelta, time
import os, sys, json, calendar
from flask import Flask, request, redirect, url_for, make_response, render_template_string, flash, abort

# --- App setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey-change-me')

# --- Ajuste para persistência do JSON ---
if getattr(sys, 'frozen', False):  # Executável
    BASE_DIR = os.path.dirname(sys.executable)
else:                               # Script Python
    BASE_DIR = os.path.dirname(__file__)

JSON_PATH = os.path.join(BASE_DIR, 'events.json')
print(">>> JSON persistente em:", JSON_PATH)

# Regras de negócio
WORKDAY_START = time(9, 0)   # 09:00
WORKDAY_END   = time(17, 0)  # 17:00

def _ensure_json():
    if not os.path.exists(JSON_PATH):
        with open(JSON_PATH, 'w', encoding='utf-8') as f:
            json.dump({"events": []}, f, ensure_ascii=False, indent=2)

def _read_all():
    _ensure_json()
    with open(JSON_PATH, 'r', encoding='utf-8') as f:
        data = json.load(f)
    data.setdefault("events", [])
    return data

def _write_all(data):
    tmp = JSON_PATH + ".tmp"
    with open(tmp, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, JSON_PATH)

def _next_id(events):
    return (max((ev.get("id", 0) for ev in events), default=0) + 1)

def parse_time(hhmm: str):
    return datetime.strptime(hhmm, "%H:%M").time()

def overlaps(a_start, a_end, b_start, b_end) -> bool:
    return (a_start < b_end) and (b_start < a_end)

calendar.setfirstweekday(calendar.MONDAY)

def month_matrix(year: int, month: int):
    return calendar.monthcalendar(year, month)

def month_name_pt(month: int):
    return [
        "janeiro","fevereiro","março","abril","maio","junho",
        "julho","agosto","setembro","outubro","novembro","dezembro"
    ][month-1]

# --- Routes ---
@app.route("/")
def index():
    today = date.today()
    year = request.args.get("year", default=today.year, type=int)
    month = request.args.get("month", default=today.month, type=int)

    start_month = date(year, month, 1)
    next_month = (start_month.replace(day=28) + timedelta(days=4)).replace(day=1)

    data = _read_all()
    events = data["events"]

    events_month = [
        ev for ev in events
        if start_month.isoformat() <= ev["event_date"] < next_month.isoformat()
    ]
    events_month.sort(key=lambda ev: (ev["event_date"], ev["start_time"]))

    events_by_day = {}
    for r in events_month:
        d = int(r["event_date"].split("-")[2])
        events_by_day.setdefault(d, []).append(r)

    weeks = month_matrix(year, month)

    return render_template_string(
        TEMPLATE_INDEX,
        year=year, month=month, month_name=month_name_pt(month),
        weeks=weeks, events_by_day=events_by_day, today=today,
        wstart=WORKDAY_START.strftime("%H:%M"),
        wend=WORKDAY_END.strftime("%H:%M")
    )

@app.post("/add")
def add_event():
    title = (request.form.get("title") or "").strip()
    event_date = request.form.get("event_date")
    start_time = request.form.get("start_time")
    end_time = request.form.get("end_time")
    email = (request.form.get("email") or "").strip()

    errors = []
    if not title:
        errors.append("Título é obrigatório.")
    try:
        _ = datetime.strptime(event_date, "%Y-%m-%d").date()
    except Exception:
        errors.append("Data inválida.")
    try:
        st = parse_time(start_time)
        et = parse_time(end_time)
        if et <= st:
            errors.append("Hora de término deve ser maior que a de início.")
    except Exception:
        errors.append("Horários inválidos.")
        st = et = None

    if "@" not in email or "." not in email:
        errors.append("E-mail inválido.")

    if st and et:
        if st < WORKDAY_START or et > WORKDAY_END:
            errors.append(f"Agendamentos apenas entre {WORKDAY_START.strftime('%H:%M')} e {WORKDAY_END.strftime('%H:%M')}.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("index"))

    data = _read_all()
    events = data["events"]
    same_day = [ev for ev in events if ev["event_date"] == event_date]
    for row in same_day:
        if overlaps(parse_time(row["start_time"]), parse_time(row["end_time"]), st, et):
            flash("Horário não disponível.", "error")
            return redirect(url_for("index"))

    new_ev = {
        "id": _next_id(events),
        "title": title,
        "event_date": event_date,
        "start_time": start_time,
        "end_time": end_time,
        "email": email,
        "created_at": datetime.utcnow().isoformat()
    }
    events.append(new_ev)
    _write_all(data)

    flash("Evento reservado com sucesso!", "success")
    y, m, _ = event_date.split("-")
    return redirect(url_for("index", year=int(y), month=int(m)))

@app.post("/edit/<int:event_id>")
def edit_event(event_id: int):
    email_req = (request.form.get("email") or "").strip().lower()
    new_date = request.form.get("event_date")
    new_start = request.form.get("start_time")
    new_end   = request.form.get("end_time")

    errors = []
    try:
        _ = datetime.strptime(new_date, "%Y-%m-%d").date()
    except Exception:
        errors.append("Data inválida.")
    try:
        st = parse_time(new_start)
        et = parse_time(new_end)
        if et <= st:
            errors.append("Hora de término deve ser maior que a de início.")
    except Exception:
        errors.append("Horários inválidos.")
        st = et = None

    if st and et:
        if st < WORKDAY_START or et > WORKDAY_END:
            errors.append(f"Agendamentos apenas entre {WORKDAY_START.strftime('%H:%M')} e {WORKDAY_END.strftime('%H:%M')}.")

    data = _read_all()
    events = data["events"]
    found = next((ev for ev in events if ev["id"] == event_id), None)

    if not found:
        flash("Evento não encontrado.", "error")
        return redirect(url_for("index"))

    if (found.get("email") or "").strip().lower() != email_req:
        flash("E-mail não confere para edição.", "error")
        return redirect(url_for("index"))

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("index"))

    same_day = [ev for ev in events if ev["event_date"] == new_date and ev["id"] != event_id]
    for row in same_day:
        if overlaps(parse_time(row["start_time"]), parse_time(row["end_time"]), st, et):
            flash("Novo horário não disponível.", "error")
            return redirect(url_for("index"))

    found["event_date"] = new_date
    found["start_time"] = new_start
    found["end_time"]   = new_end
    _write_all(data)

    flash("Evento alterado com sucesso!", "success")
    y, m, _ = new_date.split("-")
    return redirect(url_for("index", year=int(y), month=int(m)))

@app.post("/delete/<int:event_id>")
def delete_event(event_id: int):
    email_req = (request.form.get("email") or "").strip().lower()
    data = _read_all()
    events = data["events"]
    found = next((ev for ev in events if ev["id"] == event_id), None)

    if not found:
        flash("Evento não encontrado.", "error")
        return redirect(url_for("index"))

    if email_req != (found["email"] or "").strip().lower():
        flash("E-mail não confere para exclusão.", "error")
        return redirect(url_for("index"))

    data["events"] = [ev for ev in events if ev["id"] != event_id]
    _write_all(data)
    flash("Evento excluído.", "success")
    return redirect(url_for("index"))

# --- Template HTML + Ticker ---
TEMPLATE_INDEX = r"""<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reserva de Sala</title>
  <style>
    :root{
      --brand-yellow:#FFD100;
      --brand-blue:#003399;
      --blue-700:#0055A5;
      --bg:#F5F7FA;
      --panel:#FFFFFF;
      --text:#1F2937;
      --muted:#6B7280;
      --border:#E5E7EB;
      --today:#0055A5;
      --event-bg:#E6EDFF;
      --event-border:#B3C6FF;
      --warn:#F59E0B;
    }
    *{box-sizing:border-box}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Helvetica,Arial;background:var(--bg);color:var(--text);margin:0;padding-bottom:40px;}
    .container{max-width:1100px;margin:0 auto;padding:24px;}
    h1{margin:0 0 16px 0;font-size:28px;color:var(--brand-blue);}
    .topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;}
    .panel{background:var(--panel);border-radius:16px;padding:14px;border:1px solid var(--border);}
    .actions{display:flex;gap:8px;align-items:center}
    button,.btn{cursor:pointer;border:none;border-radius:10px;padding:10px 14px;font-weight:700;transition:transform .02s ease, box-shadow .2s ease;}
    button:active{transform:scale(.99)}
    button.primary{background:var(--brand-blue);color:#fff;}
    button.primary:hover{background:var(--blue-700);}
    button.warn{background:var(--warn);color:#111827;}
    input{border-radius:10px;border:1px solid var(--border);background:#FFF;color:var(--text);padding:10px 12px;font-size:14px;}
    input[type="date"],input[type="time"]{padding:8px 10px;}
    .weekday{font-size:12px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:8px 0;}
    .grid{display:grid;grid-template-columns:repeat(7,1fr);gap:8px;}
    .day{background:var(--panel);border:1px solid var(--border);border-radius:14px;min-height:120px;padding:8px;display:flex;flex-direction:column;}
    .day.today{outline:3px solid var(--today);outline-offset:1px;}
    .day .head{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--muted);}
    .day .num{font-weight:700;font-size:14px;color:var(--brand-blue);}
    .events{margin-top:6px;display:flex;flex-direction:column;gap:6px;overflow-y:auto}
    .event{background:var(--event-bg);border:1px solid var(--event-border);padding:6px 8px;border-radius:10px;font-size:12px;}
    .event .time{opacity:.85}
    .msg{padding:10px 12px;border-radius:10px;margin-bottom:8px;font-size:14px;}
    .msg.error{background:#FEF2F2;border:1px solid #FCA5A5;color:#991B1B;}
    .msg.success{background:#F0FDF4;border:1px solid #86EFAC;color:#14532D;}
    .footer{font-size:12px;color:var(--muted);margin-top:12px}
    .muted{opacity:.6}
    form.inline{display:inline;}
    a.btnlink{text-decoration:none;}
    details{margin-top:6px;}
    details .editbox{display:flex;gap:6px;flex-wrap:wrap;margin-top:6px;}
    details .editbox input{font-size:12px;padding:6px 8px;}
    details .editbox button{padding:8px 10px;}
    summary{cursor:pointer;user-select:none;}
    /* ====== Ticker de Notícias ====== */
    .ticker-container {
        position: fixed;
        bottom: 0;
        width: 100%;
        background-color: #0056b3;
        color: white;
        font-size: 1.1em;
        overflow: hidden;
        white-space: nowrap;
        z-index: 9999;
    }
    .ticker {
        display: inline-block;
        padding-left: 100%;
        animation: scroll 60s linear infinite;
    }
    @keyframes scroll {
        from { transform: translateX(0); }
        to   { transform: translateX(-100%); }
    }
    .ticker a {
        color: white;
        text-decoration: none;
        margin-right: 50px;
    }
    .ticker a:hover {
        text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="container">
    <h1>Reserva de Sala de Reunião</h1>
    <div class="panel topbar">
      <div class="actions">
        <form method="get" action="/">
          <input type="hidden" name="year" value="{{ year }}"/>
          <input type="hidden" name="month" value="{{ month-1 if month>1 else 12 }}"/>
          <button class="warn" title="Mês anterior">&larr;</button>
        </form>
        <div><strong>{{ month_name }}</strong> de <strong>{{ year }}</strong></div>
        <form method="get" action="/">
          <input type="hidden" name="year" value="{{ year if month<12 else year+1 }}"/>
          <input type="hidden" name="month" value="{{ month+1 if month<12 else 1 }}"/>
          <button class="warn" title="Próximo mês">&rarr;</button>
        </form>
      </div>
      <div class="actions">
        <form method="get" action="/">
          <button class="primary" name="year" value="{{ today.year }}" formaction="/" formmethod="get">Hoje</button>
          <input type="hidden" name="month" value="{{ today.month }}"/>
        </form>
      </div>
    </div>
    {% with messages = get_flashed_messages(with_categories=true) %}
      {% if messages %}
      <div>
        {% for category, message in messages %}
          <div class="msg {{ category }}">{{ message }}</div>
        {% endfor %}
      </div>
      {% endif %}
    {% endwith %}
    <div class="panel" style="margin-bottom:14px;">
      <form method="post" action="/add">
        <div style="display:flex; gap:12px; flex-wrap:wrap;">
          <input type="text" name="title" placeholder="Nome do evento" required>
          <input type="email" name="email" placeholder="Seu e-mail" required>
          <input type="date" name="event_date" required>
          <input type="time" name="start_time" required>
          <input type="time" name="end_time" required>
          <button type="submit" class="primary">Reservar</button>
        </div>
      </form>
      <div class="footer">
        Janela de agendamento: <strong>{{ wstart }}–{{ wend }}</strong>. Conflitos são bloqueados automaticamente.
      </div>
    </div>
    <div class="weekday">Seg • Ter • Qua • Qui • Sex • Sáb • Dom</div>
    <div class="grid">
      {% for week in weeks %}
        {% for d in week %}
          {% if d == 0 %}
            <div class="day muted">
              <div class="head"><span class="num">—</span></div>
            </div>
          {% else %}
            {% set is_today = (year == today.year and month == today.month and d == today.day) %}
            <div class="day {{ 'today' if is_today else '' }}">
              <div class="head">
                <span class="num">{{ d }}</span>
                <span class="muted">{{ ['Seg','Ter','Qua','Qui','Sex','Sáb','Dom'][(loop.index0)%7] }}</span>
              </div>
              <div class="events">
                {% for ev in events_by_day.get(d, []) %}
                  <div class="event">
                    <div><strong>{{ ev['title'] }}</strong></div>
                    <div class="time">{{ ev['start_time'] }}–{{ ev['end_time'] }}</div>
                    <form class="inline" method="post" action="/delete/{{ ev['id'] }}" onsubmit="return confirm('Excluir este evento?');">
                      <input type="email" name="email" placeholder="Seu e-mail" required
                             style="border:1px solid var(--border); background:#FFF; color:var(--text);
                                    padding:6px 8px; border-radius:8px; font-size:12px; margin-right:6px; width:160px;">
                      <button type="submit" class="warn">Excluir</button>
                    </form>
                    <details>
                      <summary>Alterar</summary>
                      <form class="editbox" method="post" action="/edit/{{ ev['id'] }}">
                        <input type="email"   name="email"      placeholder="Seu e-mail (autor)" required>
                        <input type="date"    name="event_date" value="{{ ev['event_date'] }}" required>
                        <input type="time"    name="start_time" value="{{ ev['start_time'] }}" required>
                        <input type="time"    name="end_time"   value="{{ ev['end_time'] }}" required>
                        <button type="submit" class="primary">Salvar</button>
                      </form>
                    </details>
                  </div>
                {% endfor %}
                {% if not events_by_day.get(d) %}
                  <div class="muted">• Sem reservas</div>
                {% endif %}
              </div>
            </div>
          {% endif %}
        {% endfor %}
      {% endfor %}
    </div>
    <div class="footer">Sistema interno de reservas.</div>
  </div>

  <!-- === Ticker de Notícias InfoMoney === -->
  <div class="ticker-container">
      <div id="ticker" class="ticker"></div>
  </div>

  <script>
      async function fetchRSSForTicker() {
          const url = 'https://www.infomoney.com.br/feed/';
          const proxyUrl = `https://api.rss2json.com/v1/api.json?rss_url=${encodeURIComponent(url)}`;
          try {
              const response = await fetch(proxyUrl);
              const data = await response.json();
              const tickerContainer = document.getElementById('ticker');
              tickerContainer.innerHTML = "";
              data.items.forEach(item => {
                  const newsLink = document.createElement('a');
                  newsLink.href = item.link;
                  newsLink.target = '_blank';
                  newsLink.textContent = `${item.title} — `;
                  tickerContainer.appendChild(newsLink);
              });
          } catch (error) {
              console.error("Erro ao buscar o RSS:", error);
          }
      }
      fetchRSSForTicker();
      setInterval(fetchRSSForTicker, 60000);
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    _ensure_json()
    app.run(host="0.0.0.0", port=5000, debug=True)
