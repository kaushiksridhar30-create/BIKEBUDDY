"""Bike Buddy brain: bike state WITH PROVENANCE + multilingual intent router.
Answers are TEMPLATES filled from data (no invented facts). Every value knows where it came from:
  sensor = real telemetry posted to /api/telemetry (OBD-II / CAN / BLE TPMS bridge, see bridge.py)
  sim    = demo value (shown as SIMULATED everywhere; never presented as live)
  user   = typed in by the rider in the garage      estimate = computed by us from other data
Demo mode is the default. The first real telemetry packet switches to live mode and clears every demo value."""
import re, datetime, time
import lang, engine, llm, store, garage

TELE = {"battery": 12.6, "engine_temp": 88, "fuel": 62, "tyre_front": 30, "tyre_rear": 32}   # demo values (simulation only)
OPT = ("rpm", "ignition")                                                                       # optional live-only signals
TELE_KEYS = tuple(TELE) + OPT
LIMITS = {"battery": (0, 20), "engine_temp": (-40, 250), "fuel": (0, 100), "tyre_front": (0, 80), "tyre_rear": (0, 80), "rpm": (0, 20000)}
LINK_OK_S, STALE_S = 15, 60          # connected < 15 s since last packet, stale < 60 s, then values are treated as unavailable
PSI = (28, 34); KM_PER_PCT = 4.5

STATE, SRC, SEEN, HIST = {}, {}, {}, {}
MODE = ["sim"]; LOG = store.D["notes"]

def T(key, **kw): return lang.cur()["T"][key].format(n=lang.SET["name"], **kw)
def days(d):
    try: return (datetime.date.fromisoformat(d) - datetime.date.today()).days
    except Exception: return 999

# ---------------- state, provenance, connection ----------------
def _sim_defaults():
    for k in TELE_KEYS: STATE[k] = TELE.get(k); SRC[k] = "sim" if k in TELE else "none"; SEEN.pop(k, None); HIST[k] = []

def load_profile():
    """Copy the active bike's USER-ENTERED profile into STATE (call after switching bikes or editing the garage)."""
    b = garage.active()
    for k, v in b["profile"].items():
        STATE[k] = v
        if SRC.get(k) != "sensor": SRC[k] = "user"
    STATE["bike_name"] = b["name"]; STATE["bike_model"] = b["model"]

def save_profile():
    p = garage.active()["profile"]
    for k in garage.PROFILE:
        if k in STATE: p[k] = STATE[k]
    store.save()

def set_mode(m):
    MODE[0] = m
    if m == "sim": _sim_defaults()
    else:
        for k in TELE_KEYS: STATE[k] = None; SRC[k] = "none"; SEEN.pop(k, None); HIST[k] = []

def _note(k, v, now):
    h = HIST.setdefault(k, []); h.append((now, v)); h[:] = [x for x in h if now - x[0] < 900][-300:]

def set_demo(d):
    """Demo helper behind /api/bike/set. Refused in live mode: it would let anyone fake a 'live' reading."""
    out = {}
    for k, v in d.items():
        if k not in STATE or k.startswith("bike_"): continue
        if k in TELE_KEYS and MODE[0] == "live": raise PermissionError("live mode: sensor values cannot be edited")
        STATE[k] = v; out[k] = v
        if k in TELE_KEYS: SRC[k] = "sim"; SEEN[k] = time.time(); _note(k, v, time.time())
        if k in garage.PROFILE: SRC[k] = "user"
    save_profile(); return out

def ingest(d, source="sensor"):
    """Real telemetry from a bridge. Unknown fields and impossible values are rejected, never stored."""
    if MODE[0] == "sim": set_mode("live")
    now = time.time(); ok, bad = {}, {}
    for k, v in d.items():
        if k == "odometer":
            try: STATE[k] = float(v); SRC[k] = "sensor"; ok[k] = STATE[k]; save_profile()
            except (TypeError, ValueError): bad[k] = "not a number"
            continue
        if k not in TELE_KEYS: bad[k] = "unknown field"; continue
        try: x = bool(v) if k == "ignition" else float(v)
        except (TypeError, ValueError): bad[k] = "not a number"; continue
        if k in LIMITS and not (LIMITS[k][0] <= x <= LIMITS[k][1]): bad[k] = "out of range"; continue
        x = round(x, 2) if k != "ignition" else x
        STATE[k] = x; SRC[k] = source; SEEN[k] = now; ok[k] = x; _note(k, x, now)
    if "battery" in ok: _batt_sample(ok["battery"], now)
    return {"accepted": ok, "rejected": bad}

def _batt_sample(v, now):
    h = store.D["batt_hist"]; run = running()
    if h and now - h[-1]["t"] < 600: return          # one sample per 10 minutes is plenty for a trend
    h.append({"t": round(now), "v": v, "run": run, "bike": store.D["active"]}); del h[:-2000]; store.save()

def view():
    """The values the logic may TRUST: in live mode, missing or stale readings are None (not last-known fakes)."""
    if MODE[0] == "sim": return STATE
    now, v = time.time(), dict(STATE)
    for k in TELE_KEYS:
        if k not in SEEN or now - SEEN[k] > STALE_S: v[k] = None
    return v

def running():
    s = view()
    if s.get("ignition") is not None: return bool(s["ignition"])
    if s.get("rpm") is not None: return s["rpm"] >= 500
    return None

def conn():
    if MODE[0] == "sim": return {"status": "simulated", "age": None, "mode": "sim"}
    if not SEEN: return {"status": "waiting", "age": None, "mode": "live"}
    age = time.time() - max(SEEN.values())
    return {"status": "connected" if age < LINK_OK_S else "stale" if age < STALE_S else "disconnected", "age": round(age), "mode": "live"}

def provenance():
    now = time.time()
    return {k: {"src": SRC.get(k, "user"), "age": round(now - SEEN[k]) if k in SEEN else None} for k in STATE if not k.startswith("bike_")}

# ---------------- rendering ----------------
def _na(label): return T("na", x=T(label))
def render(i):
    s = view()
    has_ = lambda *k: all(s.get(x) is not None for x in k)
    if i == "tyre" and not has_("tyre_front", "tyre_rear"):
        if has_("tyre_front"): return T("f_tf", f=s["tyre_front"]) + "."
        if has_("tyre_rear"): return T("f_tr", r=s["tyre_rear"]) + "."
        return _na("l_tyre")
    if i == "fuel" and not has_("fuel"): return _na("l_fuel")
    if i == "batt" and not has_("battery"): return _na("l_batt")
    if i == "temp" and not has_("engine_temp"): return _na("l_temp")
    return {"tyre": lambda: T("tyre", f=s["tyre_front"], r=s["tyre_rear"], lo=PSI[0], hi=PSI[1]),
            "fuel": lambda: T("fuel", p=s["fuel"], km=int(s["fuel"] * KM_PER_PCT)),
            "svc": lambda: T("svc0") if s["next_service"] - s["odometer"] <= 0 else T("svc", km=int(s["next_service"] - s["odometer"])),
            "oil": lambda: T("oil", last=s["last_oil"], since=int(s["odometer"] - s["last_oil"])),
            "batt": lambda: T("batt", v=s["battery"]), "temp": lambda: T("temp", t=s["engine_temp"]),
            "odo": lambda: T("odo", o=int(s["odometer"]), t=s["trip"]), "mil": lambda: T("mil", m=s["avg_mileage"]),
            "brake": lambda: T("brake", b=s["brake_pad"]), "chain": lambda: T("chain", k=int(s["odometer"] - s["last_chain_lube"])),
            "docs": lambda: T("docs", puc=s["puc"], ins=s["insurance"])}[i]()

def warnings():
    import alerts
    return [a["text"] for a in alerts.active_alerts()]

def precheck_text():
    w = warnings(); return T("okpre") if not w else T("warn") + " " + " ".join(w)

def health_summary():
    """'Is my bike healthy?' -> only what is actually available, plus an honest note about where it came from."""
    import alerts
    s, act, c = view(), alerts.active_alerts(), conn()["status"]; parts = []
    if s.get("battery") is not None: parts.append(T("f_batt", v=s["battery"]))
    if s.get("engine_temp") is not None: parts.append(T("f_temp", t=s["engine_temp"]))
    if s.get("fuel") is not None: parts.append(T("f_fuel", p=s["fuel"]))
    if s.get("tyre_front") is not None: parts.append(T("f_tf", f=s["tyre_front"]))
    if s.get("tyre_rear") is not None: parts.append(T("f_tr", r=s["tyre_rear"]))
    src = {"simulated": "src_sim", "connected": "src_live", "stale": "src_stale"}.get(c, "src_none")
    out = []
    if parts:
        out.append(T("h_ok") if not act else T("h_warn", k=len(act)))
        body = ", ".join(parts); out.append(body[:1].upper() + body[1:] + ".")
    out += [a["text"] for a in act[:2]]
    out.append(T(src)); return " ".join(out)

# ---------------- intent router ----------------
K = {"tyre": ["tyre", "tire", "hawa", "pressure", "psi", "टायर", "हवा", "ಟೈರ್", "ಗಾಳಿ"],
     "fuel": ["petrol", "fuel", "tank", "range", "पेट्रोल", "ईंधन", "टंकी", "ಪೆಟ್ರೋಲ್", "ಇಂಧನ", "ಟ್ಯಾಂಕ್"],
     "brake": ["brake", "ब्रेक", "ಬ್ರೇಕ್"], "chain": ["chain", "चेन", "ಚೈನ್"],
     "oil": ["oil", "ऑयल", "तेल", "ಆಯಿಲ್", "ಎಣ್ಣೆ"], "svc": ["service", "सर्विस", "ಸರ್ವಿಸ್"],
     "batt": ["battery", "batri", "bettery", "batry", "bateri", "बैटरी", "बैटरी", "ಬ್ಯಾಟರಿ", "ಬ್ಯಾಟ್ರಿ", "ಬ್ಯಾಟರೀ", "ಬ್ಯಾಟೆರಿ", "ಬ್ಯಾಟೇರಿ"],
     "temp": ["temperature", "garam", "engine", "heat", "तापमान", "गरम", "इंजन", "ತಾಪಮಾನ", "ಎಂಜಿನ್", "ಇಂಜಿನ್"],
     "odo": ["odometer", "kilometre", "kilometer", "how far", "trip", "ओडोमीटर", "किलोमीटर", "ಕಿಲೋಮೀಟರ್"],
     "mil": ["mileage", "average", "माइलेज", "एवरेज", "ಮೈಲೇಜ್"],
     "docs": ["puc", "insurance", "bima", "बीमा", "पीयूसी", "ಪಿಯುಸಿ", "ವಿಮೆ"]}
ORDER = ["tyre", "fuel", "brake", "chain", "oil", "svc", "batt", "temp", "odo", "mil", "docs"]
NAME = ["naam", "name", "नाम", "ಹೆಸರು"]
HELLO = ["hello", "hey", " hi ", "namaste", "नमस्ते", "हेलो", "ನಮಸ್ಕಾರ", "ಹಲೋ"]
SUM = ["condition", "kaisi", "haal", "status", "sab theek", "check", "healthy", "health", "स्थिति", "हाल", "कंडीशन", "सेहत", "ಸ್ಥಿತಿ", "ಹೇಗಿದೆ", "ಆರೋಗ್ಯ"]
SHOWLOG = ["show log", "log dikha", "what did i log", "kya log", "maintenance log", "लॉग दिखा", "ಲಾಗ್ ತೋರಿಸು"]
LOGW = ("log", "note", "yaad", "लॉग", "नोट", "ಲಾಗ್")
RENAME = [r"(?:naam|name)\s+([a-z]{2,15})\s+(?:rakho|rakh|rakhna|rakhdo|hai|kar do)", r"call (?:you|yourself)\s+([a-z]{2,15})",
          r"your name is\s+([a-z]{2,15})", r"(?:tumhara|aapka|your)\s+(?:naam|name)\s+([a-z]{2,15})"]
STOP = {"kya", "what", "your", "tumhara", "aapka", "my", "mera", "is", "hai", "ka", "ko", "ne", "the", "a"}
has = lambda t, ws: any(w in f" {t} " for w in ws)   # exact; fuzzy is used only as a last resort
THANKS = ["thanks", "thank you", "shukriya", "dhanyavaad", "धन्यवाद", "शुक्रिया", "ಧನ್ಯವಾದ"]
HOW = ["how are you", "kaise ho", "aap kaise", "कैसे हो", "ಹೇಗಿದ್ದೀರಾ", "ಹೇಗಿದ್ದೀಯ"]
BYE = ["bye", "goodbye", "alvida", "chalta hoon", "बाय", "अलविदा", "ಬೈ", "ವಿದಾಯ"]
CAN = ["what can you do", "kya kar sakte", "kya kar sakta", "tum kya", "क्या कर सकते", "ನೀನು ಏನು ಮಾಡ"]
HIST_ = []

def llm_context():
    """Everything the free-form LLM may use. It is told which values are demo/sensor/user so it cannot present demo data as live."""
    import alerts, rides, maint
    return {"data_source": conn()["status"], "value_sources": {k: SRC.get(k) for k in view() if view()[k] is not None and not k.startswith("bike_")},
            "active_alerts": [a["text_en"] for a in alerts.active_alerts()], "ride": rides.live(), "last_ride": rides.last_summary(),
            "maintenance": maint.brief()}

def answer(text: str, ctx=None) -> str: return answer_ex(text, ctx)["reply"]

def answer_ex(text: str, ctx=None) -> dict:
    """{'reply': spoken text, 'action': optional UI action such as navigate / sos / share}. ctx may carry lat/lon."""
    r = _answer(text, ctx or {}); return r if isinstance(r, dict) else {"reply": r, "action": None}

def _answer(text, ctx):
    t = re.sub(r"[.,?!।]", " ", text.lower()).strip()
    if not t: return T("quiet")
    for rx in RENAME:
        m = re.search(rx, t)
        if m and m.group(1) not in STOP:
            lang.SET["name"] = m.group(1).capitalize(); store.D["settings"]["name"] = lang.SET["name"]; store.save(); return T("rn")
    if has(t, SHOWLOG): return T("logs", items="; ".join(LOG[-3:])) if LOG else T("log0")
    if t.startswith(LOGW): LOG.append(t); store.save(); return T("log")
    import skills
    r = skills.route(t, text, ctx)
    if r: return {"reply": r[0], "action": r[1]}
    if llm.enabled() and not has(t, SUM):      # free-form understanding + small talk (grounded in the data above)
        try:
            r = llm.chat(text, view(), warnings(), lang.SET["name"], lang.SET["lang"], HIST_, llm_context())
            HIST_.extend([{"role": "user", "content": text}, {"role": "assistant", "content": r}]); del HIST_[:-12]
            return r
        except Exception as ex: print("LLM error:", ex)
    for i in ORDER:
        if has(t, K[i]): return render(i)
    if has(t, NAME): return T("nm")
    if has(t, THANKS): return T("thanks")
    if has(t, HOW): return T("how")
    if has(t, BYE): return T("bye")
    if has(t, CAN): return T("can")
    if has(t, HELLO): return T("hello")
    if has(t, SUM): return health_summary()
    for i in ORDER:                              # last resort: mis-heard words
        if engine.fz(t, K[i]): return render(i)
    return T("none")

def init():
    """Load saved settings and the active bike. Called once at import."""
    S = store.D["settings"]
    for k in ("name", "lang", "speed_limit", "speak_alerts", "rider", "auto_odo"):
        if k in S and (k != "lang" or S[k] in lang.LANGS): lang.SET[k] = S[k]
    _sim_defaults(); load_profile()

def switch(i):
    save_profile(); garage.get(i); store.D["active"] = i; store.save(True)
    SRC.clear(); STATE.clear(); _sim_defaults() if MODE[0] == "sim" else set_mode("live"); load_profile()

init()
