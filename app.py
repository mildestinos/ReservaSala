from datetime import datetime, date, timedelta, time
import sqlite3
import os
from flask import Flask, request, redirect, url_for, make_response, render_template_string, flash, abort

# --- App setup ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'devkey-change-me')
DB_PATH = os.path.join(os.path.dirname(__file__), 'events.db')

# Regras de negócio
WORKDAY_START = time(9, 0)   # 09:00
WORKDAY_END   = time(17, 0)  # 17:00

# (Opcional) token para assinatura ICS segmentada
ICS_TOKEN = os.getenv("ICS_TOKEN")  # ex.: ICS_TOKEN=cliente123

# --- DB helpers ---
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            event_date TEXT NOT NULL,         -- YYYY-MM-DD
            start_time TEXT NOT NULL,         -- HH:MM (24h)
            end_time TEXT NOT NULL,           -- HH:MM (24h)
            email TEXT NOT NULL,
            created_at TEXT NOT NULL          -- ISO timestamp
        );
        """
    )
    conn.commit()
    conn.close()

def parse_time(hhmm: str):
    return datetime.strptime(hhmm, "%H:%M").time()

def overlaps(a_start, a_end, b_start, b_end) -> bool:
    # Interseção em intervalos [a_start, a_end) e [b_start, b_end)
    return (a_start < b_end) and (b_start < a_end)

# --- Calendar generation ---
import calendar
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

    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT * FROM events
        WHERE event_date >= ? AND event_date < ?
        ORDER BY event_date, start_time
        """,
        (start_month.isoformat(), next_month.isoformat())
    )
    rows = cur.fetchall()
    conn.close()

    events_by_day = {}
    for r in rows:
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
    event_date = request.form.get("event_date")  # YYYY-MM-DD
    start_time = request.form.get("start_time")  # HH:MM
    end_time = request.form.get("end_time")      # HH:MM
    email = (request.form.get("email") or "").strip()

    errors = []
    if not title:
        errors.append("Título é obrigatório.")
    try:
        _ = datetime.strptime(event_date, "%Y-%m-%d").date()
    except Exception:
        errors.append("Data inválida (use o seletor de data).")
    try:
        st = parse_time(start_time)
        et = parse_time(end_time)
        if et <= st:
            errors.append("Hora de término deve ser maior que a hora de início.")
    except Exception:
        errors.append("Horários inválidos (use o seletor de hora).")
        st = et = None

    if "@" not in email or "." not in email:
        errors.append("E-mail inválido.")

    # Janela 09:00–17:00
    if st and et:
        if st < WORKDAY_START or et > WORKDAY_END:
            errors.append(f"Agendamentos permitidos apenas entre {WORKDAY_START.strftime('%H:%M')} e {WORKDAY_END.strftime('%H:%M')}.")

    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("index"))

    # Conflito: mesmo dia + sobreposição -> "Horário não disponível."
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT start_time, end_time FROM events WHERE event_date = ?", (event_date,))
    existing = cur.fetchall()
    for row in existing:
        if overlaps(parse_time(row["start_time"]), parse_time(row["end_time"]), st, et):
            conn.close()
            flash("Horário não disponível.", "error")
            return redirect(url_for("index"))

    # Inserção
    cur.execute(
        """
        INSERT INTO events (title, event_date, start_time, end_time, email, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (title, event_date, start_time, end_time, email, datetime.utcnow().isoformat())
    )
    conn.commit()
    conn.close()
    flash("Evento reservado com sucesso!", "success")
    y, m, _ = event_date.split("-")
    return redirect(url_for("index", year=int(y), month=int(m)))

# --- ICS export + endpoints para assinatura pelo Outlook ---
@app.get("/export.ics")
def export_ics():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM events ORDER BY event_date, start_time")
    rows = cur.fetchall()
    conn.close()

    ics_lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Sala de Reunião//PT-BR//EN",
    ]
    for r in rows:
        dt = datetime.strptime(r["event_date"], "%Y-%m-%d").date()
        st = datetime.combine(dt, parse_time(r["start_time"]))
        et = datetime.combine(dt, parse_time(r["end_time"]))
        ics_lines.extend([
            "BEGIN:VEVENT",
            f"UID:{r['id']}@sala.local",
            f"DTSTAMP:{datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
            f"DTSTART:{st.strftime('%Y%m%dT%H%M00')}",
            f"DTEND:{et.strftime('%Y%m%dT%H%M00')}",
            f"SUMMARY:{r['title']}",
            f"DESCRIPTION:Reservado por {r['email']}",
            "END:VEVENT",
        ])
    ics_lines.append("END:VCALENDAR")

    content = "\r\n".join(ics_lines)
    resp = make_response(content)
    resp.headers["Content-Type"] = "text/calendar; charset=utf-8"
    resp.headers["Content-Disposition"] = "attachment; filename=reservas_sala.ics"
    return resp

# URL estável para assinatura no Outlook (webcal/HTTPS)
@app.get("/calendar.ics")
def calendar_ics():
    return export_ics()

# URL com token (opcional) para segmentar acesso
@app.get("/calendar/<token>.ics")
def calendar_ics_token(token: str):
    if ICS_TOKEN and token != ICS_TOKEN:
        return abort(403)
    return export_ics()

# --- Exclusão com verificação de autoria (e-mail deve bater com o criador) ---
@app.post("/delete/<int:event_id>")
def delete_event(event_id: int):
    email_req = (request.form.get("email") or "").strip().lower()

    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT id, email FROM events WHERE id = ?", (event_id,))
    row = cur.fetchone()

    if not row:
        conn.close()
        flash("Evento não encontrado.", "error")
        return redirect(url_for("index"))

    email_owner = (row["email"] or "").strip().lower()
    if email_req != email_owner:
        conn.close()
        flash("Apenas quem criou o evento pode excluir (e-mail não confere).", "error")
        return redirect(url_for("index"))

    cur.execute("DELETE FROM events WHERE id = ?", (event_id,))
    conn.commit()
    conn.close()
    flash("Evento excluído.", "success")
    return redirect(url_for("index"))

# --- Template (paleta estilo Correios + crédito) ---
TEMPLATE_INDEX = r"""
<!doctype html>
<html lang="pt-br">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Reserva de Sala</title>
  <style>
    :root{
      --brand-yellow:#FFD100;   /* destaque/CTA */
      --brand-blue:#003399;     /* institucional */
      --blue-700:#0055A5;       /* apoio/hover */
      --bg:#F5F7FA;             /* fundo app */
      --panel:#FFFFFF;          /* painéis/cartões */
      --text:#1F2937;           /* texto primário */
      --muted:#6B7280;          /* texto secundário */
      --border:#E5E7EB;         /* bordas sutis */
      --today:#0055A5;          /* destaque dia atual */
      --event-bg:#E6EDFF;       /* chip de evento */
      --event-border:#B3C6FF;
      --warn:#F59E0B;           /* avisos */
    }

    *{box-sizing:border-box}
    body{font-family:system-ui,-apple-system,Segoe UI,Roboto,Ubuntu,Cantarell,Noto Sans,Helvetica,Arial;background:var(--bg);color:var(--text);margin:0;}
    .container{max-width:1100px;margin:0 auto;padding:24px;}
    h1{margin:0 0 16px 0;font-size:28px;color:var(--brand-blue);}

    .topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:14px;}
    .panel{background:var(--panel);border-radius:16px;padding:14px;border:1px solid var(--border);}

    .actions{display:flex;gap:8px;align-items:center}
    button,.btn{cursor:pointer;border:none;border-radius:10px;padding:10px 14px;font-weight:700;transition:transform .02s ease, box-shadow .2s ease;}
    button:active{transform:scale(.99)}
    button.primary{background:var(--brand-blue);color:#fff;}
    button.primary:hover{background:var(--blue-700);}
    button.accent{background:var(--brand-yellow);color:#1f2937;}
    button.accent:hover{filter:brightness(0.95);}
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
        <a class="btnlink" href="/calendar.ics"><button type="button" class="accent">Assinar .ics</button></a>
        <a class="btnlink" href="/export.ics"><button type="button" class="accent">Exportar .ics</button></a>
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

    <div class="footer">Dica: assine o <em>.ics</em> no Outlook para sincronização automática.</div>
  </div>

  <!-- Créditos institucionais -->
  <div class="footer" style="text-align:center; margin:16px 0 24px;">
    Desenvolvido por <strong>@ericvieira</strong>
  </div>
</body>
</html>
"""

if __name__ == "__main__":
    init_db()
    app.run(host="0.0.0.0", port=5000, debug=True)
