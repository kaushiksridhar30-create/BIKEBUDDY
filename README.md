# Bike Buddy
A voice-first AI riding buddy built on **Gnani Prisma (speech-to-text)** and **Gnani Timbre (text-to-speech)**.
Ask your bike about fuel, tyres, service, brakes, battery and papers in Hinglish, English, Hindi or Kannada. It speaks first in a pre-ride check, and its built-in **Crash Guard** notices a crash, asks "are you okay?", and escalates if you say help or stay silent.

> Prototype for the Great Indian AI Internship Challenge. Bike data and alerts are **simulated**. It never contacts real emergency services and is not a safety device.

## Features
- 3D bike HUD (three.js), 3 vehicles, tap a part to hear its status, parts glow red on warnings
- Multilingual voice: Hinglish, English, Hindi, Kannada. Rename your buddy by voice or settings
- 20+ bike questions, voice maintenance log, pre-ride check, mis-heard word tolerance, small talk
- **Crash Guard:** phone impact + stillness + GPS speed separates a crash from a dropped phone
- Silence counts as "not okay". Bystander voice. Emergency contact. Responder dashboard with map, timeline and impact graph
- Optional LLM (any OpenAI-compatible API) for free-form questions, grounded in bike data

## Architecture
```
Phone/Browser (mic, motion, GPS, 3D UI) -> Flask API -> Gnani Prisma (STT) -> intent rules / optional LLM
                                                    -> Gnani Timbre (TTS) -> audio back
Crash event (speed, g, trace) -> engine.decide() -> check-in -> escalate -> /dashboard
Bike data layer (simulated STATE or bike_sim.csv) is swappable for real OBD-II/CAN telemetry.
```

## Run locally
1. Install Python 3.10+ and ffmpeg. `pip install -r requirements.txt`
2. Copy `.env.example` to `.env` and add `GNANI_API_KEY`
3. `python test_engine.py` then `python app.py` and open http://localhost:5000 (dashboard at /dashboard)
4. Phone sensors need https: use a tunnel (`ngrok http 5000`) or the deployed URL

## Deploy (Render, Docker)
Push to GitHub, create a Render Web Service from the repo (Docker), set `GNANI_API_KEY` (and optionally `LLM_KEY`). `GNANI_CALL_CAP` limits voice calls per run to protect credits.

## Files
`app.py` API | `engine.py` crash logic and fuzzy matching | `bike.py` bike brain | `lang.py` language packs | `gnani.py` throttled Gnani client | `llm.py` optional LLM | `static/` UI and dashboard | `benchmark.py` noise test

## Limitations
Web page senses only while open and on screen (a native app or bike-integrated unit is the next step). Needs internet. State is in memory. Alerts are simulated. Speech accuracy for Kannada and Hindi is not benchmarked yet.
"# BIKEBUDDY" 
