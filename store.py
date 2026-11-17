"""Tiny JSON file store for a single rider (no database to install). Folder: $BB_DATA or ./data.
Writes are atomic (temp file + rename) and throttled; call save(force=True) for things that must not be lost."""
import atexit, json, os, threading, time, uuid

DIR = os.environ.get("BB_DATA") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "data")
FILE = os.path.join(DIR, "bikebuddy.json")
LOCK = threading.RLock()
D = {}
_last = [0.0]; _dirty = [False]

def uid(): return uuid.uuid4().hex[:8]

def defaults():
    return {"bikes": {}, "active": None, "rides": [], "active_ride": None, "alerts": [], "contacts": [], "notes": [],
            "settings": {}, "shares": {}, "batt_hist": [], "places": {}}

def load():
    with LOCK:
        D.clear(); D.update(defaults())
        try:
            with open(FILE, encoding="utf-8") as f: D.update(json.load(f))
        except FileNotFoundError: pass
        except Exception as ex: print("store: could not read", FILE, ex)
        for k, v in defaults().items(): D.setdefault(k, v)

def use(folder):
    """Point the store at another folder (tests). Must be called before other modules cache references into D."""
    global DIR, FILE
    DIR = folder; FILE = os.path.join(DIR, "bikebuddy.json"); load()

def save(force=False):
    with LOCK:
        _dirty[0] = True
        if not force and time.time() - _last[0] < 5: return
        os.makedirs(DIR, exist_ok=True); tmp = FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f: json.dump(D, f, ensure_ascii=False)
        os.replace(tmp, FILE); _last[0] = time.time(); _dirty[0] = False

def flush():
    if _dirty[0]: save(force=True)

atexit.register(flush)
load()
