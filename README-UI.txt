# Smart Bicycle Tracker – Web UI important info before implementation

this is the web dashboard UI overview important for understanding implementation, upkeep and iteration for the Smart Bicycle Tracker project for group 8a within Fletcher's CS410 , built on:

- raspberry Pi (backend host)
- ESP32 (sensor + GPS source)
- python (Flask backend)
- HTML + Tailwind CSS + Leaflet.js (frontend)

the backend exposes REST endpoints (e.g. `/live`, `/weekly_summary`, `/lock`, `/unlock`, `/alerts`) and serves a single-page dashboard at `/`.

1. what the UI currently does

1.1. overview

when you visit the dashboard (served by `backend.py`):

- you get a single-page web app (`dashboard.html`).
- it polls the backend APIs periodically and updates:
  - lock/unlock status
  - motion/alert status
  - weekly distance summary
  - recent motion alerts
  - live location on a map

the UI is mobile-friendly and should work well on phones / tablets on the same Wi-Fi as the Pi

---

1.2. files involved so far and what they do

key files for the UI layer:

- `backend.py`
  - flask app running on port `5001`
  - serves `dashboard.html` at `/`
  - provides JSON endpoints consumed by the UI:
    - `GET /alert_status`
    - `POST /lock`
    - `POST /unlock`
    - `GET /weekly_summary`
    - `GET /alerts`
    - `GET /live`
- `dashboard.html`
  - main web dashboard
  - uses Tailwind CDN for styling
  - uses Leaflet.js for map display
  - all logic is in inline JavaScript (no build tools required)

other project files (e.g. `calculate_distance.py`, `distance_summary.py`, `distance_tabs.py`, `live_location.py`, `location_storage.py`, `ride_simulator.py`, etc.) 
either feed data into the backend or are used by backend routes that power these APIs.


C. Weekly Distance Card

Data source: `GET /weekly_summary`

Expected response shape (example):

```json
[
  { "date": "2025-12-01", "distance_km": 4.23 },
  { "date": "2025-12-02", "distance_km": 1.10 }
]
