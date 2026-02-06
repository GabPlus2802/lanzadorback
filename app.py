from flask import Flask, request, jsonify, render_template
import psycopg2
import psycopg2.extras
import json

app = Flask(__name__)

# =========================
# CONFIG desde archivo secreto
# =========================
# Render: montaremos este archivo como secret en /etc/secrets/db.json
CONFIG_PATH = "/etc/secrets/db.json"

with open(CONFIG_PATH, "r", encoding="utf-8") as f:
    cfg = json.load(f)

DB_USER = cfg["DB_USER"]
DB_PASSWORD = cfg["DB_PASSWORD"]
DB_HOST = cfg["DB_HOST"]
DB_PORT = int(cfg["DB_PORT"])
DB_NAME = cfg["DB_NAME"]
DB_SSLMODE = cfg.get("DB_SSLMODE", "require")

def get_conn():
    return psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        sslmode=DB_SSLMODE,
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS public.events (
            id BIGSERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            event_type TEXT NOT NULL CHECK (event_type IN ('botado','permitido')),
            sensor_value INT,
            device_id TEXT,
            lane_id TEXT
        );
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS events_created_at_idx ON public.events (created_at DESC);")
    cur.execute("CREATE INDEX IF NOT EXISTS events_type_idx ON public.events (event_type);")
    conn.commit()
    cur.close()
    conn.close()

# Render ejecuta múltiples workers: esto es seguro porque usamos IF NOT EXISTS
init_db()

@app.post("/api/event")
def api_event():
    data = request.get_json(force=True, silent=True) or {}

    event_type = data.get("event_type")
    sensor_value = data.get("sensor_value")
    device_id = data.get("device_id")
    lane_id = data.get("lane_id")

    if event_type not in ("botado", "permitido"):
        return jsonify({"ok": False, "error": "event_type inválido. Use 'botado' o 'permitido'"}), 400

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO public.events (event_type, sensor_value, device_id, lane_id)
        VALUES (%s, %s, %s, %s)
        RETURNING id, created_at
    """, (event_type, sensor_value, device_id, lane_id))
    row = cur.fetchone()
    conn.commit()
    cur.close()
    conn.close()

    return jsonify({"ok": True, "id": row[0], "created_at": row[1].isoformat()})

@app.get("/api/stats")
def api_stats():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT COUNT(*)::int AS c FROM public.events WHERE event_type='botado'")
    botados = cur.fetchone()["c"]

    cur.execute("SELECT COUNT(*)::int AS c FROM public.events WHERE event_type='permitido'")
    permitidos = cur.fetchone()["c"]

    cur.execute("""
        SELECT id, event_type, sensor_value, device_id, lane_id, created_at
        FROM public.events
        ORDER BY created_at DESC
        LIMIT 50
    """)
    last_events = cur.fetchall()

    cur.close()
    conn.close()

    for ev in last_events:
        if ev.get("created_at"):
            ev["created_at"] = ev["created_at"].isoformat()

    return jsonify({"botados": botados, "permitidos": permitidos, "last_events": last_events})

@app.get("/")
def dashboard():
    return render_template("dashboard.html")

# Render usa gunicorn; esto es solo para local
if __name__ == "__main__":
    app.ru
