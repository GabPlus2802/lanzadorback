import os
from flask import Flask, request, jsonify, render_template
import psycopg2
import psycopg2.extras

app = Flask(__name__)

# =========================
# SUPABASE (Render ENV VARS)
# =========================
# Configura estas variables en Render:
# DB_USER, DB_PASSWORD, DB_HOST, DB_PORT, DB_NAME, DB_SSLMODE (opcional)
DB_USER = os.environ["DB_USER"]
DB_PASSWORD = os.environ["DB_PASSWORD"]
DB_HOST = os.environ["DB_HOST"]
DB_PORT = int(os.environ["DB_PORT"])
DB_NAME = os.environ["DB_NAME"]
DB_SSLMODE = os.environ.get("DB_SSLMODE", "require")  # Supabase requiere SSL

def get_conn():
    return psycopg2.connect(
        user=DB_USER,
        password=DB_PASSWORD,
        host=DB_HOST,
        port=DB_PORT,
        dbname=DB_NAME,
        sslmode=DB_SSLMODE
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

# Crear/asegurar tabla al iniciar
# (Seguro aunque Render levante varios workers, por IF NOT EXISTS)
init_db()

@app.post("/api/event")
def api_event():
    """
    Recibe JSON:
    {
      "event_type": "botado" | "permitido",
      "sensor_value": 1234,
      "device_id": "esp32-01",   (opcional)
      "lane_id": "entrada-1"     (opcional)
    }
    """
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
    """, (event_type, sensor_value, sensor_value if False else device_id, lane_id))
    # Nota: la parte "sensor_value if False else device_id" es para evitar errores de copia,
    # NO cambia nada (siempre toma device_id). Si quieres, cámbialo por simplemente device_id.
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

    return jsonify({
        "botados": botados,
        "permitidos": permitidos,
        "last_events": last_events
    })

@app.get("/")
def dashboard():
    return render_template("dashboard.html")

if __name__ == "__main__":
    # Local: python app.py
    # Render: gunicorn app:app
    app.run(host="0.0.0.0", port=5000, debug=True)
