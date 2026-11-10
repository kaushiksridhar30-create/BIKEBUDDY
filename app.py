import base64, subprocess
from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
import gnani, engine, lang
load_dotenv()
app = Flask(__name__, static_folder="static")
INC = {}
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
    L = lang.cur(); return base64.b64encode(gnani.tts(t, voice=L["voice"], language=L["tts"])[0]).decode()

def open_incident(e):
    mode = engine.decide(float(e.get("speed_kmh", 0)), float(e.get("peak_g", 0)))
    if mode == "none": return jsonify(mode="none")
    inc = engine.Incident(mode, e); INC[inc.id] = inc
    inc.add("assistant", bike.T(mode))
    return jsonify(id=inc.id, mode=mode, text=bike.T(mode), audio=speak(bike.T(mode)))

@app.get("/")
def home(): return send_from_directory("static", "rider.html")
@app.get("/classic")
def classic(): return send_from_directory("static", "classic.html")
@app.get("/dashboard")
def dash(): return send_from_directory("static", "dashboard.html")

@app.post("/api/event")
def event(): return open_incident(request.json)

@app.post("/api/sim")   # replay simulated bike telemetry through the SAME pipeline
def sim(): return open_incident(engine.from_bike_csv("bike_sim.csv"))

@app.post("/api/answer")
def answer():
    inc = INC[request.form["id"]]; text = listen(); label = engine.classify(text)
    inc.add("rider", text or "(no answer)"); inc.injured = engine.injured(text) or inc.injured
    if label == "fine" or (inc.mode == "drop" and label == "unclear"):
        inc.status = "ok"; inc.add("assistant", bike.T("fine"))
        return jsonify(status="ok", text=text, audio=speak(bike.T("fine")))
    inc.status = "escalated"; inc.add("assistant", bike.T("esc")); inc.add("system", f"ALERT sent to {inc.contact or 'contacts'} + responders (simulated)")
    return jsonify(status="escalated", text=text, audio=speak(bike.T("esc")), bystander=True)

@app.post("/api/bystander")
def bystander():
    inc = INC[request.form["id"]]; text = listen(); inc.add("bystander", text or "(no reply)")
    return jsonify(text=text)

@app.post("/api/cancel")
def cancel():
    inc = INC[request.json["id"]]; inc.status = "false_alarm"; inc.add("rider", "cancelled"); return jsonify(ok=1)

@app.get("/api/incidents")
def incidents(): return jsonify([i.dict() for i in reversed(list(INC.values()))])

import bike
@app.post("/api/ask")
def ask():
    text = listen()
    if engine.is_emergency(text, [w for v in bike.K.values() for w in v]):      # "I met with an accident" / "help"
        def num(k):
            try: return float(request.form.get(k, ""))
            except ValueError: return None
        inc = engine.Incident("sos", {"source": "voice_sos", "contact": request.form.get("contact", ""), "lat": num("lat"), "lon": num("lon")})
        INC[inc.id] = inc; inc.status = "escalated"; inc.injured = engine.injured(text)
        reply = bike.T("sos")
        inc.add("rider", text); inc.add("assistant", reply)
        inc.add("system", f"ALERT sent to {inc.contact or 'contacts'} + responders with location (simulated)")
        return jsonify(text=text, reply=reply, audio=speak(reply), emergency=True, id=inc.id)
    reply = bike.answer(text)
    return jsonify(text=text, reply=reply, audio=speak(reply))

@app.post("/api/precheck")
def precheck():
    return jsonify(reply=bike.precheck_text(), warnings=len(bike.warnings()), audio=speak(bike.precheck_text()))

@app.get("/api/bike")
def bike_state(): return jsonify(state=bike.STATE, warnings=bike.warnings(), log=bike.LOG)

@app.post("/api/bike/set")   # demo helper: change a value, e.g. {"tyre_front": 19}
def bike_set():
    bike.STATE.update({k: v for k, v in request.json.items() if k in bike.STATE}); return jsonify(ok=1)

@app.post("/api/settings")
def settings():
    j = request.json or {}
    if j.get("lang") in lang.LANGS: lang.SET["lang"] = j["lang"]
    if j.get("name"): lang.SET["name"] = str(j["name"]).strip()[:15] or "Buddy"
    return jsonify(lang.SET)

@app.get("/api/say")
def say():
    k = request.args.get("k", "")
    if k not in ("by", "hello"): return jsonify(error="bad key"), 400
    return jsonify(audio=speak(bike.T(k)))

@app.errorhandler(Exception)
def on_error(ex):
    print("SERVER ERROR:", ex); return jsonify(error=str(ex)[:200]), 500

@app.post("/api/asktext")
def asktext():
    reply = bike.answer(request.json.get("text", "")); return jsonify(reply=reply, audio=speak(reply))

if __name__ == "__main__":
    import os; app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=os.environ.get("DEBUG") == "1")
