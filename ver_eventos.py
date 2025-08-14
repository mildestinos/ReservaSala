import sqlite3

conn = sqlite3.connect("events.db")
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("SELECT * FROM events ORDER BY event_date, start_time")
rows = cur.fetchall()

if not rows:
    print("Nenhum evento encontrado.")
else:
    for row in rows:
        print(f"{row['id']} | {row['title']} | {row['event_date']} {row['start_time']}–{row['end_time']} | {row['email']}")

conn.close()
