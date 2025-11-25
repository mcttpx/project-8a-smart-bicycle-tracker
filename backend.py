from flask import Flask, request, jsonify
from flask_cors import CORS
import time
import sqlite3
import webbrowser
import threading
from math import radians, sin, cos, sqrt, atan2
from datetime import datetime

app = Flask(__name__)
CORS(app)

# -----------------------------
# Motion / lock state (in-memory)
# -----------------------------
bike_locked = False
last_lat = None
last_lng = None
last_motion_time = None
alert_sent = False

MOTION_THRESHOLD_M = 2.0          # meters of movement to count as motion
ALERT_DEADLINE_SEC = 10           # must alert within 10s

# -----------------------------
# Haversine distance (km)
# -----------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371.0
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))
    return R * c  # km

# -----------------------------
# DB setup
# -----------------------------
def init_db():
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()

    # GPS points table
    c.execute("""
        CREATE TABLE IF NOT EXISTS live_location (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL,
            lng REAL,
            timestamp INTEGER
        )
    """)

    # Daily distances
    c.execute("""
        CREATE TABLE IF NOT EXISTS daily_distance (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT,
            distance REAL
        )
    """)

    # Motion alerts log
    c.execute("""
        CREATE TABLE IF NOT EXISTS motion_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            lat REAL,
            lng REAL,
            reason TEXT,
            timestamp INTEGER
        )
    """)

    conn.commit()
    conn.close()

init_db()

def log_motion_alert(lat, lng, reason):
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()
    ts = int(time.time())
    c.execute("INSERT INTO motion_alerts (lat, lng, reason, timestamp) VALUES (?, ?, ?, ?)",
              (lat, lng, reason, ts))
    conn.commit()
    conn.close()
    print(f"[ALERT] {reason} @ ({lat}, {lng}) ts={ts}")

# -------------------------------------------------
# AUTO-OPEN LIVE MAP (uses your actual file path)
# -------------------------------------------------
def open_browser():
    time.sleep(1)  # give Flask a moment to start
    map_path = "/Users/snehrojivadia/Desktop/CS 410 PROJECT/SPRINT_1/User_Story_2_Cyclist/live_map.html"
    map_url = "file://" + map_path.replace(" ", "%20")  # escape spaces for URL
    print(f"[INFO] Opening map automatically: {map_url}")
    webbrowser.open(map_url)

# -------------------------------------------------
# ESP32 (or simulator) POSTS GPS DATA HERE
# -------------------------------------------------
@app.route("/update", methods=["POST"])
def update_location():
    global last_lat, last_lng, last_motion_time, alert_sent

    data = request.get_json()
    lat = float(data.get("lat"))
    lng = float(data.get("lng"))
    ts = int(time.time())

    # compute movement since last sample (meters)
    if last_lat is not None and last_lng is not None:
        moved_m = haversine(last_lat, last_lng, lat, lng) * 1000.0
    else:
        moved_m = 0.0

    # Update in-memory last position for motion detection baseline
    last_lat, last_lng = lat, lng

    # If locked and motion exceeds threshold → trigger alert immediately
    if bike_locked and moved_m > MOTION_THRESHOLD_M:
        last_motion_time = time.time()
        if not alert_sent:
            alert_sent = True
            log_motion_alert(lat, lng, "Motion detected while locked")
            return jsonify({
                "alert": True,
                "msg": "Motion detected while locked!",
                "lat": lat,
                "lng": lng,
                "timestamp": ts
            })

    # Persist this point and update distances
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()

    # 1) insert this GPS point
    c.execute("INSERT INTO live_location (lat, lng, timestamp) VALUES (?, ?, ?)", (lat, lng, ts))

    # 2) get last 2 points to compute incremental distance
    c.execute("SELECT lat, lng FROM live_location ORDER BY id DESC LIMIT 2")
    rows = c.fetchall()
    if len(rows) == 2:
        (lat2, lon2), (lat1, lon1) = rows  # latest is (lat1, lon1)
        distance_increment_km = haversine(lat1, lon1, lat2, lon2)
    else:
        distance_increment_km = 0.0

    # 3) roll up into today's total
    today = datetime.now().strftime("%Y-%m-%d")
    c.execute("SELECT distance FROM daily_distance WHERE date=?", (today,))
    row = c.fetchone()
    if row:
        new_total = row[0] + distance_increment_km
        c.execute("UPDATE daily_distance SET distance=? WHERE date=?", (new_total, today))
    else:
        c.execute("INSERT INTO daily_distance (date, distance) VALUES (?, ?)", (today, distance_increment_km))

    conn.commit()
    conn.close()

    # Safety net: enforce the 10-second rule if motion recorded
    if bike_locked and last_motion_time is not None and not alert_sent:
        if (time.time() - last_motion_time) >= ALERT_DEADLINE_SEC:
            alert_sent = True
            log_motion_alert(lat, lng, "Auto-triggered (10s rule)")
            return jsonify({
                "alert": True,
                "msg": "Motion alert auto-triggered (10s rule)",
                "lat": lat,
                "lng": lng,
                "timestamp": ts
            })

    print(f"GPS UPDATE → lat:{lat}, lng:{lng}, moved_m:{moved_m:.2f}, time:{ts}")
    return jsonify({"status": "ok", "moved_m": round(moved_m, 2)})

# ---------------------------------------
# Latest coordinate for the map
# ---------------------------------------
@app.route("/live", methods=["GET"])
def get_live_location():
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()
    c.execute("SELECT lat, lng, timestamp FROM live_location ORDER BY id DESC LIMIT 1")
    row = c.fetchone()
    conn.close()

    if row:
        return jsonify({"lat": row[0], "lng": row[1], "timestamp": row[2]})
    else:
        return jsonify({"lat": None, "lng": None, "timestamp": None})

# ---------------------------------------
# Weekly summary (last 7 days rolled totals)
# ---------------------------------------
@app.route("/weekly_summary", methods=["GET"])
def weekly_summary():
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()
    c.execute("""
        SELECT date, distance FROM daily_distance
        ORDER BY date DESC
        LIMIT 7
    """)
    rows = c.fetchall()
    conn.close()

    summary = [{"date": d, "distance_km": round(dist, 2)} for d, dist in rows]
    return jsonify(summary)

# ---------------------------------------
# Lock / Unlock / Alert Status / Alerts list
# ---------------------------------------
@app.route("/lock", methods=["POST"])
def lock_bike():
    global bike_locked, alert_sent, last_motion_time
    bike_locked = True
    alert_sent = False
    last_motion_time = None
    return jsonify({"locked": True})

@app.route("/unlock", methods=["POST"])
def unlock_bike():
    global bike_locked, alert_sent, last_motion_time
    bike_locked = False
    alert_sent = False
    last_motion_time = None
    return jsonify({"locked": False})

@app.route("/alert_status", methods=["GET"])
def alert_status():
    return jsonify({
        "locked": bike_locked,
        "alert_sent": alert_sent,
        "last_motion_time": last_motion_time
    })

@app.route("/alerts", methods=["GET"])
def list_alerts():
    conn = sqlite3.connect("gps_data.db")
    c = conn.cursor()
    c.execute("SELECT lat, lng, reason, timestamp FROM motion_alerts ORDER BY id DESC LIMIT 25")
    rows = c.fetchall()
    conn.close()
    return jsonify([
        {"lat": lat, "lng": lng, "reason": reason, "timestamp": ts}
        for (lat, lng, reason, ts) in rows
    ])

# ---------------------------------------
# Boot + run
# ---------------------------------------
print("Backend ready. Motion alerts will fire if locked and movement > 2 m (≤10 s).")

if __name__ == "__main__":
    threading.Thread(target=open_browser).start()
    app.run(host="0.0.0.0", port=5001)
