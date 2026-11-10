"""Bike Buddy brain: simulated bike state + multilingual intent router. Answers are TEMPLATES filled from data (no invented facts).
Replace STATE with OBD-II / CAN / OEM telemetry of the same shape for a real bike."""
import re, datetime
import lang, engine, llm
STATE = {"odometer": 8420, "trip": 36, "next_service": 8900, "last_oil": 7900, "last_chain_lube": 8100,
         "fuel": 62, "tyre_front": 30, "tyre_rear": 32, "battery": 12.6, "engine_temp": 88, "brake_pad": 70,
         "avg_mileage": 42, "puc": "2027-02-01", "insurance": "2027-03-15"}
PSI = (28, 34); KM_PER_PCT = 4.5; LOG = []

def T(key, **kw): return lang.cur()["T"][key].format(n=lang.SET["name"], **kw)
def days(d):
    try: return (datetime.date.fromisoformat(d) - datetime.date.today()).days
    except Exception: return 999

def render(i):
    s = STATE
    return {"tyre": lambda: T("tyre", f=s["tyre_front"], r=s["tyre_rear"], lo=PSI[0], hi=PSI[1]),
            "fuel": lambda: T("fuel", p=s["fuel"], km=int(s["fuel"] * KM_PER_PCT)),
            "svc": lambda: T("svc0") if s["next_service"] - s["odometer"] <= 0 else T("svc", km=s["next_service"] - s["odometer"]),
            "oil": lambda: T("oil", last=s["last_oil"], since=s["odometer"] - s["last_oil"]),
            "batt": lambda: T("batt", v=s["battery"]), "temp": lambda: T("temp", t=s["engine_temp"]),
            "odo": lambda: T("odo", o=s["odometer"], t=s["trip"]), "mil": lambda: T("mil", m=s["avg_mileage"]),
            "brake": lambda: T("brake", b=s["brake_pad"]), "chain": lambda: T("chain", k=s["odometer"] - s["last_chain_lube"]),
            "docs": lambda: T("docs", puc=s["puc"], ins=s["insurance"])}[i]()

def bad():
    s, b = STATE, []
    if min(s["tyre_front"], s["tyre_rear"]) < PSI[0]: b.append("tyre")
    if s["fuel"] < 15: b.append("fuel")
    if s["next_service"] - s["odometer"] <= 200: b.append("svc")
    if s["battery"] < 12.0: b.append("batt")
    if s["engine_temp"] > 105: b.append("temp")
    if s["brake_pad"] < 20: b.append("brake")
    if s["odometer"] - s["last_chain_lube"] >= 500: b.append("chain")
    if min(days(s["puc"]), days(s["insurance"])) <= 30: b.append("docs")
    return b

def warnings(): return [render(i) for i in bad()]
def precheck_text():
    b = bad(); return T("okpre") if not b else T("warn") + " " + " ".join(render(i) for i in b)

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
SUM = ["condition", "kaisi", "haal", "status", "sab theek", "check", "स्थिति", "हाल", "कंडीशन", "ಸ್ಥಿತಿ", "ಹೇಗಿದೆ"]
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
HIST = []

def answer(text: str) -> str:
    t = re.sub(r"[.,?!।]", " ", text.lower()).strip()
    if not t: return T("quiet")
    for rx in RENAME:
        m = re.search(rx, t)
        if m and m.group(1) not in STOP:
            lang.SET["name"] = m.group(1).capitalize(); return T("rn")
    if has(t, SHOWLOG): return T("logs", items="; ".join(LOG[-3:])) if LOG else T("log0")
    if t.startswith(LOGW): LOG.append(t); return T("log")
    if llm.enabled() and not has(t, SUM):      # free-form understanding + small talk (grounded in STATE)
        try:
            r = llm.chat(text, STATE, warnings(), lang.SET["name"], lang.SET["lang"], HIST)
            HIST.extend([{"role": "user", "content": text}, {"role": "assistant", "content": r}]); del HIST[:-12]
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
    if has(t, SUM): return precheck_text()
    for i in ORDER:                              # last resort: mis-heard words
        if engine.fz(t, K[i]): return render(i)
    return T("none")
