import base64, os, subprocess
from dotenv import load_dotenv
load_dotenv()                                   # before store is imported, so BB_DATA in .env is honoured
from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException
import gnani, engine, lang, bike, safety, store
from api import bp
app = Flask(__name__, static_folder="static")
app.register_blueprint(bp)
INC = safety.INC
VOICE = {"err": ""}

def base_url(): return os.environ.get("PUBLIC_URL") or request.host_url
def wav16k(b):
    p = subprocess.run(["ffmpeg", "-loglevel", "error", "-i", "pipe:0", "-ac", "1", "-ar", "16000", "-f", "wav", "pipe:1"],
                       input=b, capture_output=True)
    if p.returncode: raise RuntimeError("ffmpeg failed: " + p.stderr.decode()[:200])
    return p.stdout

LAST = {"err": ""}
def listen():
    LAST["err"] = ""
    if "text" in request.form: return request.form["text"].strip()   # typed fallback when no mic
    f = request.files.get("audio")
    if not f: LAST["err"] = "no audio received"; return ""
    data = f.read(); print("audio received:", len(data), "bytes")
    if len(data) < 1500: LAST["err"] = f"mic recorded almost nothing ({len(data)} bytes)"; return ""
    try: return gnani.stt(wav16k(data), lang.cur()["stt"])[0].strip()
    except Exception as ex: LAST["err"] = str(ex)[:200]; print("STT error:", ex); return ""

@app.get("/api/lasterr")
def lasterr(): return jsonify(err=LAST["err"])

def speak(t):
    """Gnani Timbre voice. Never raises: if the voice service fails (bad key, no internet) we return '' and the page speaks with the browser voice."""
    try:
        L = lang.cur(); VOICE["err"] = ""
        return base64.b64encode(gnani.tts(t, voice=L["voice"], language=L["tts"])[0]).decode()
    except Exception as ex:
        VOICE["err"] = ("Gnani voice rejected the API key (401). Check GNANI_API_KEY in .env and restart." if "401" in str(ex) else str(ex))[:200]
        print("TTS error:", ex); return ""

def voice(t): return {"audio": speak(t), "voice_error": VOICE["err"], "tts_lang": lang.cur()["stt"]}

def open_incident(e):
    mode = engine.decide(float(e.get("speed_kmh", 0)), float(e.get("peak_g", 0)))
    if mode == "none": return jsonify(mode="none")
    inc = safety.open_incident(mode, e); inc.add("assistant", bike.T(mode))
    if not e.get("contact"): inc.contact = ", ".join(c["name"] for c in safety.contacts())[:40]
    return jsonify(id=inc.id, mode=mode, text=bike.T(mode), countdown_s=30 if mode == "crash" else 45, **voice(bike.T(mode)))

@app.get("/")
def home(): return send_from_directory("static", "rider.html")
@app.get("/classic")
def classic(): return send_from_directory("static", "classic.html")
@app.get("/dashboard")
def dash(): return send_from_directory("static", "dashboard.html")
@app.get("/track/<tok>")
def track_page(tok): return send_from_directory("static", "track.html")
@app.get("/sw.js")
def sw():
    r = send_from_directory("static", "sw.js"); r.headers["Service-Worker-Allowed"] = "/"; r.headers["Cache-Control"] = "no-cache"; return r

@app.post("/api/event")
def event(): return open_incident(request.json)

@app.post("/api/sim")   # replay simulated bike telemetry through the SAME pipeline
def sim(): return open_incident(engine.from_bike_csv("bike_sim.csv"))

@app.post("/api/answer")
def answer():
    inc = INC[request.form["id"]]; text = listen(); label = engine.classify(text)
    inc.add("rider", text or "(no answer)"); inc.injured = engine.injured(text) or inc.injured
    if inc.status == "escalated": return jsonify(status="escalated", text=text, **voice(bike.T("esc")), bystander=True)
    if label == "fine" or (inc.mode == "drop" and label == "unclear"):
        inc.status = "ok"; inc.add("assistant", bike.T("fine"))
        return jsonify(status="ok", text=text, **voice(bike.T("fine")))
    inc.add("assistant", bike.T("esc")); safety.escalate(inc, base_url(), "rider asked for help" if label == "help" else "no clear answer")
    return jsonify(status="escalated", text=text, bystander=True, **voice(bike.T("esc")))

@app.post("/api/escalate")      # the on-screen countdown ran out with no answer: silence escalates on purpose
def escalate():
    inc = INC[request.json["id"]]
    if inc.status in ("checking",): inc.add("assistant", bike.T("esc")); safety.escalate(inc, base_url(), request.json.get("reason", "no response"))
    return jsonify(status=inc.status, **voice(bike.T("esc")))

@app.post("/api/sos")
def sos():
    j = request.json or {}
    inc = safety.sos({"lat": j.get("lat"), "lon": j.get("lon"), "source": "sos_button", "contact": ", ".join(c["name"] for c in safety.contacts())[:40]}, base_url())
    return jsonify(id=inc.id, status=inc.status, text=bike.T("esc"), **voice(bike.T("esc")))

@app.post("/api/bystander")
def bystander():
    inc = INC[request.form["id"]]; text = listen(); inc.add("bystander", text or "(no reply)")
    return jsonify(text=text)

@app.post("/api/cancel")
def cancel():
    inc = INC[request.json["id"]]; safety.cancel(inc, base_url()); return jsonify(ok=1)

@app.get("/api/incidents")
def incidents(): return jsonify([i.dict() for i in reversed(list(INC.values()))])

def _ctx():
    j = request.get_json(silent=True) or {}
    def f(k):
        v = request.form.get(k, j.get(k))
        try: return float(v) if v not in (None, "", "null", "undefined") else None
        except ValueError: return None
    return {"lat": f("lat"), "lon": f("lon")}

@app.post("/api/ask")
def ask():
    text = listen(); r = bike.answer_ex(text, _ctx())
    return jsonify(text=text, reply=r["reply"], action=r["action"], **voice(r["reply"]))

@app.post("/api/precheck")
def precheck():
    t = bike.precheck_text(); return jsonify(reply=t, warnings=len(bike.warnings()), **voice(t))

@app.get("/api/bike")
def bike_state(): return jsonify(state=bike.STATE, warnings=bike.warnings(), log=bike.LOG)

@app.post("/api/bike/set")   # DEMO helper: change a simulated value, e.g. {"tyre_front": 19}. Refused in live mode.
def bike_set(): bike.set_demo(request.json or {}); return jsonify(ok=1)

@app.post("/api/settings")
def settings():
    j = request.json or {}; S = store.D["settings"]
    if j.get("lang") in lang.LANGS: lang.SET["lang"] = S["lang"] = j["lang"]
    if j.get("name"): lang.SET["name"] = S["name"] = str(j["name"]).strip()[:15] or "Buddy"
    if "rider" in j: lang.SET["rider"] = S["rider"] = (str(j["rider"]).strip().replace("<", "").replace(">", "")[:20] or "Rider")
    if "speed_limit" in j:
        try: lang.SET["speed_limit"] = S["speed_limit"] = max(0, min(200, int(j["speed_limit"])))
        except (TypeError, ValueError): pass
    for k in ("speak_alerts", "auto_odo"):
        if k in j: lang.SET[k] = S[k] = bool(j[k])
    store.save(True); return jsonify(lang.SET)

@app.get("/api/say")
def say():
    k = request.args.get("k", "")
    if k not in ("by", "hello"): return jsonify(error="bad key"), 400
    return jsonify(**voice(bike.T(k)))

@app.post("/api/tts")   # speak any short text (alerts, turn-by-turn). Cached in gnani.py, so repeats cost nothing.
def tts():
    t = str((request.json or {}).get("text", ""))[:400]
    return jsonify(**voice(t)) if t else (jsonify(error="no text"), 400)

@app.errorhandler(Exception)
def on_error(ex):
    if isinstance(ex, HTTPException): return jsonify(error=ex.description), ex.code
    if isinstance(ex, KeyError): return jsonify(error="not found: " + str(ex)[:80]), 404
    if isinstance(ex, ValueError): return jsonify(error=str(ex)[:200]), 400
    if isinstance(ex, PermissionError): return jsonify(error=str(ex)[:200]), 403
    print("SERVER ERROR:", repr(ex)); return jsonify(error=str(ex)[:200]), 500

@app.post("/api/asktext")
def asktext():
    r = bike.answer_ex((request.json or {}).get("text", ""), _ctx()); return jsonify(reply=r["reply"], action=r["action"], **voice(r["reply"]))

if __name__ == "__main__": app.run(host="0.0.0.0", port=5000, debug=True)
