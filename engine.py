"""Core logic: event decision, answer classification, incident record. No network here, so it is easy to test."""
import re, time, uuid, difflib

FINE = ["theek hoon", "theek hu", "thik hoon", "main theek", "i am fine", "i'm fine", "im fine",
        "all good", "sab theek", "fine", "okay", "kuch nahi hua", "safe", "ठीक हूँ", "ठीक हूं", "सब ठीक", "ಚೆನ್ನಾಗಿದ್ದೇನೆ", "ಸರಿಯಾಗಿದ್ದೇನೆ"]
HELP = ["help", "madad", "bachao", "dard", "pain", "ambulance", "chot", "khoon", "blood", "hurt",
        "behosh", "nahi utha", "move", "not fine", "not ok", "theek nahi", "thik nahi", "मदद", "बचाओ", "दर्द", "चोट", "खून", "ठीक नहीं", "ಸಹಾಯ", "ನೋವು", "ಕಾಪಾಡಿ", "ಗಾಯ", "ರಕ್ತ", "ಸರಿಯಿಲ್ಲ", "ಚೆನ್ನಾಗಿಲ್ಲ"]
NUM = {"ek": 1, "do": 2, "teen": 3, "one": 1, "two": 2, "three": 3}

def fz(t, words, cut=0.8):
    """Substring match, plus fuzzy match on single words, so mis-heard words ('bettery') still count."""
    t = f" {t} "
    if any(w in t for w in words): return True
    toks = [x for x in t.split() if len(x) >= 5]   # short words ('hoon' vs 'khoon') are too ambiguous to fuzzy-match
    single = [w for w in words if " " not in w and len(w) >= 4]   # padded words like " chot " are exact-only
    return any(difflib.get_close_matches(x, single, n=1, cutoff=cut) for x in toks)

STRONG = ["accident", "crash", "bachao", "emergency", "ambulance", "bleeding", "khoon", " chot ", "एक्सीडेंट", "दुर्घटना", "बचाओ", "चोट", "खून",
          "ಅಪಘಾತ", "ಕಾಪಾಡಿ", "ರಕ್ತ", "ಗಾಯ"]
WEAK = ["help", "madad", "need help", "मदद", "ಸಹಾಯ"]

def is_emergency(text: str, bike_words) -> bool:
    """Spoken SOS in the normal chat flow. 'help me check my tyre' must NOT trigger it, so a bare 'help' only counts when
    the sentence is short and has no bike keyword."""
    t = re.sub(r"[.,?!।]", " ", text.lower()).strip()
    if not t: return False
    if fz(t, STRONG): return True
    return fz(t, WEAK) and len(t.split()) <= 6 and not any(w in f" {t} " for w in bike_words)

def classify(text: str) -> str:
    """help > fine > unclear. Unclear is NEVER treated as 'fine'."""
    t = text.lower()
    if fz(t, HELP): return "help"      # fuzzy only for danger words
    if any(k in t for k in FINE): return "fine"
    return "unclear"

def injured(text: str):
    m = re.search(r"(\d+|ek|do|teen|one|two|three)\s+(log|people|persons|riders)", text.lower())
    if not m: return None
    return int(m.group(1)) if m.group(1).isdigit() else NUM[m.group(1)]

def decide(speed_kmh: float, peak_g: float) -> str:
    """Speed context separates a real crash from a dropped phone."""
    if peak_g < 2.5: return "none"
    return "crash" if speed_kmh >= 15 else "drop"

def from_bike_csv(path: str) -> dict:
    """Adapter: simulated bike telemetry (t,speed_kmh,g) -> the same event a phone produces."""
    rows = [tuple(map(float, l.split(","))) for l in open(path).read().splitlines()[1:] if l.strip()]
    i = max(range(len(rows)), key=lambda k: rows[k][2])
    return {"source": "bike_sim", "speed_kmh": rows[max(i - 1, 0)][1], "peak_g": rows[i][2], "trace": [r[2] for r in rows]}

class Incident:
    def __init__(self, mode, e):
        self.id = uuid.uuid4().hex[:8]; self.mode = mode
        self.source = e.get("source", "phone"); self.speed = e.get("speed_kmh", 0); self.peak_g = e.get("peak_g", 0)
        self.lat = e.get("lat") or 12.9716; self.lon = e.get("lon") or 77.5946
        self.status = "checking"; self.injured = None; self.timeline = []
        self.trace = [round(float(x), 2) for x in (e.get("trace") or [])][:400]
        self.contact = re.sub(r"[<>&\"']", "", str(e.get("contact", "")))[:40]
        self.t0 = time.time(); self.add("system", "SOS spoken by rider" if self.source == "voice_sos" else f"{mode} detected: {self.speed:.0f} km/h, {self.peak_g:.1f} g ({self.source})")

    def add(self, who, text):
        self.timeline.append({"t": round(time.time() - self.t0, 1), "who": who, "text": text})

    def summary(self):
        said = [x["text"] for x in self.timeline if x["who"] == "rider"]
        return (f"{'Rider reported an emergency by voice' if self.source == 'voice_sos' else 'Possible road crash'} at {self.lat:.4f},{self.lon:.4f}. Speed before impact {self.speed:.0f} km/h. "
                f"Rider said: {said[-1] if said else 'nothing'}. Injured: {self.injured or 'unknown'}. Status: {self.status}. Contact: {self.contact or 'none set'}.")

    def dict(self):
        return {"id": self.id, "mode": self.mode, "status": self.status, "lat": self.lat, "lon": self.lon,
                "timeline": self.timeline, "trace": self.trace, "contact": self.contact, "summary": self.summary()}
