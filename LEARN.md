# Learn as you build: what each piece teaches

## Tech used
- **Flask (Python REST API):** `app.py` exposes endpoints (/api/event, /api/answer...). Skill: designing small HTTP APIs.
- **Browser sensors:** `DeviceMotionEvent` (accelerometer), Geolocation (speed), MediaRecorder (mic). Skill: Web APIs, permissions, HTTPS.
- **Gnani Prisma (STT) + Timbre (TTS):** `gnani.py`. Skill: calling third-party AI APIs, timing them, handling failures.
- **ffmpeg:** converts browser audio (webm) to 16 kHz mono WAV. Skill: audio formats and why models need specific ones.
- **Rule-based NLP:** `engine.classify()`. Skill: explainable decisions, and why rules beat an LLM when safety matters.
- **Adapter pattern:** `engine.from_bike_csv()` turns bike data into the same event a phone makes. Skill: separating input sources from logic.
- **Polling dashboard:** `dashboard.html` fetches /api/incidents every 2 s. Skill: simple real-time UI (next step: WebSockets).

## How the flow works
1. `rider.html` watches the accelerometer. Impact above 25 m/s2 (about 2.5 g), then 2.5 s of stillness (low standard deviation) = event.
2. It POSTs speed + peak g to `/api/event`. `decide()` says crash (moving) or drop (standing).
3. Timbre speaks the check-in. The page records 6 s of your answer.
4. `/api/answer`: Prisma transcribes, `classify()` returns fine / help / unclear.
5. fine = cancel. help, or unclear in a crash = escalate (alert, bystander voice, dashboard).
6. Silence escalates on purpose: the worst victims cannot speak.

## Try these to level up
- Add unit tests for more Hinglish phrases in `test_engine.py`. Find phrases that break `classify()`.
- Replace polling with Flask-SocketIO. Compare latency.
- Add free-fall detection (m < 3 for 80 ms before impact) and measure false alarms.
- Run `benchmark.py`, plot accuracy vs SNR with matplotlib, and explain the curve.
- Move STT calls into a background thread so the server handles two incidents at once.

## Interview questions you can now answer
- Why not trigger on a spike alone? (Phones get dropped constantly. Speed context cuts false alarms.)
- Why rules, not an LLM, for the answer? (Predictable, instant, auditable, safe default on doubt.)
- What breaks in production? (Background sensing needs a native app, no signal means no cloud STT, helmet noise, privacy under the DPDP Act.)
- How would a bike maker use it? (Write one adapter like `from_bike_csv` for real bike telemetry.)
- What does your benchmark prove? (Label accuracy by noise level. It does NOT prove crash-detection accuracy.)

## Bike Buddy layer (bike.py)
- **Intent routing:** keywords map speech to an intent (tyre, fuel, service...). Skill: NLU basics. Upgrade path: an LLM (Evon) with the same data as context.
- **Template answers from data:** the bot reads STATE and fills a sentence, so it cannot invent a tyre pressure. Skill: grounding, a core GenAI safety idea.
- **Telemetry is simulated:** STATE mimics what OBD-II/CAN would give. Replacing it is the OEM integration story.
- **Proactive warnings:** warnings() runs rules on data, so the bike speaks first in the pre-ride check. Skill: rule engines.
- **Interview line:** "Voice layer, intent layer and data layer are separate, so each can be swapped."

## Full-feature layer (what was added)
- **Provenance model** (`bike.py`): every value carries a source tag; demo vs live mode; stale = unavailable. Skill: honest data design.
- **Alerts engine** (`alerts.py`): rules, hysteresis, spoken once per occurrence, fault log. Skill: avoiding alert spam.
- **Ride analytics** (`rides.py`): GPS filtering, harsh braking from consecutive speeds, eco score (an estimate).
- **Maintenance** (`maint.py`): distance + time reminders, riding-pace projection, battery trend regression.
- **Safety** (`safety.py`, `notify.py`): tokenised share link, idempotent escalation, honest "simulated" delivery.
- **Navigation** (`places.py`, `nav.py`): Overpass, Nominatim, OSRM with localized turn text.
- **Voice router** (`skills.py`): intents return (reply, action); the client performs actions, so voice never sends SOS by itself.
- Interview line: "Voice, intent, data, alert and safety layers are separate, and the UI never shows a value without its source."
