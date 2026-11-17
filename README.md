# Bike Buddy
A voice-first riding companion: talk to Buddy (Kannada / Hindi / English / Hinglish), see live bike health, track rides, get proactive safety alerts, crash/SOS with live-location sharing, navigation, maintenance reminders, analytics and a digital garage. Built on Gnani Prisma (STT) + Timbre (TTS). Not an emergency service.

## Run
1. Install ffmpeg. `pip install -r requirements.txt`. Copy `.env.example` to `.env`, set `GNANI_API_KEY`.
2. `python app.py` (port 5000). Rider app: http://localhost:5000 . Responder dashboard: /dashboard . Old single-page demo: /classic .
3. Phone sensors/GPS/mic need HTTPS: `ngrok http 5000`, open the https link, set `PUBLIC_URL` to it so share links work.
4. Tests: `python test_engine.py` and `python -m pytest -q test_features.py`.

## Honest data: where every number comes from
Each value is badged: **SENSOR** (from the bike), **GPS** (phone), **YOU** (entered by you), **ESTIMATE** (computed), **SIMULATED** (demo).
- **Demo mode (default)** shows labelled simulated bike values so you can see every feature. Use the Home tab's demo tools to add sample rides/faults.
- **Live mode** starts automatically when the first real packet reaches `POST /api/telemetry`; demo values are cleared, and values older than 60 s show as unavailable instead of stale numbers.
- Missing sensors show "not available". Nothing is invented.

## Connect a real bike
POST JSON to `/api/telemetry` (set `TELEMETRY_TOKEN` and send `X-Token`). Fields: `battery_v, engine_temp, fuel_pct, tyre_front, tyre_rear, rpm, speed, odometer`. `bridge.py` forwards from a serial device (JSON lines) or an OBD-II adapter (`pip install pyserial obd`) and auto-reconnects.

## .env keys
`GNANI_API_KEY` (voice; if wrong, the app falls back to browser voice) · `LLM_KEY`, `LLM_MODEL` (optional free-form chat and suggestions) · `BB_DATA` (data folder, default ./data) · `PUBLIC_URL` · `TELEMETRY_TOKEN` · `TWILIO_SID/TOKEN/FROM` or `ALERT_WEBHOOK_URL` (real alerts) · `DEFAULT_COUNTRY_CODE` · `OVERPASS_URL`, `NOMINATIM_URL`, `OSRM_URL`, `NAV_COUNTRY`, `HTTP_UA` (maps).

## Safety behaviour
Crash/drop opens a countdown (30/45 s); silence escalates. SOS has a 5 s cancel window. **Alerts are only really sent if SMS (Twilio) or a webhook is configured**; otherwise the app says "Nothing was actually sent" and offers SMS/WhatsApp/call buttons. Live-share links expose only location and status.

## Limits
- A web page cannot track in the background: keep it open and on screen while riding.
- Hands-free "Hey Buddy" needs Chrome/Edge and the page open.
- Routing uses the public OSRM car profile; Overpass/Nominatim are fair-use public services. Nearby places are cached for offline.
- Kannada/Hindi strings should be reviewed by a native speaker.
- 3D bike loads three.js from a CDN; for offline use save it as static/vendor/three.min.js (see that folder).
- Not built: community features, background native sensing.
