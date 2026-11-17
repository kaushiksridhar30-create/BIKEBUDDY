"""Digital garage: bikes (multi-bike), documents, service records, repair expenses, accessories/mods.
Everything here is USER-ENTERED data. It is stored per bike in store.D["bikes"]. Validation is strict because the UI renders it."""
import datetime, store

DATE = "date"; NUM = "num"; STR = "str"
PROFILE = {"odometer": NUM, "trip": NUM, "next_service": NUM, "last_oil": NUM, "last_chain_lube": NUM, "brake_pad": NUM,
           "avg_mileage": NUM, "puc": DATE, "insurance": DATE, "service_km": NUM, "service_months": NUM, "oil_km": NUM,
           "chain_km": NUM, "last_service_date": DATE, "last_oil_date": DATE}
SCHEMA = {
    "docs": {"type": (STR, 30, 1), "number": (STR, 40, 0), "expiry": (DATE, 0, 0), "note": (STR, 120, 0)},
    "services": {"date": (DATE, 0, 1), "odo": (NUM, 0, 0), "type": (STR, 20, 1), "cost": (NUM, 0, 0), "shop": (STR, 60, 0), "note": (STR, 200, 0)},
    "expenses": {"date": (DATE, 0, 1), "cat": (STR, 20, 1), "amount": (NUM, 0, 1), "note": (STR, 120, 0)},
    "mods": {"date": (DATE, 0, 0), "name": (STR, 60, 1), "cost": (NUM, 0, 0), "note": (STR, 120, 0)},
}
SERVICE_TYPES = ("service", "oil", "chain", "brake", "tyre", "battery", "repair", "other")
EXPENSE_CATS = ("fuel", "service", "repair", "parts", "insurance", "accessory", "other")

def today(): return datetime.date.today()
def iso(d): return d.isoformat()

def default_profile():
    t = today()
    return {"odometer": 8420, "trip": 36, "next_service": 8900, "last_oil": 7900, "last_chain_lube": 8100, "brake_pad": 70,
            "avg_mileage": 42, "puc": iso(t + datetime.timedelta(days=90)), "insurance": iso(t + datetime.timedelta(days=130)),
            "service_km": 3000, "service_months": 6, "oil_km": 3000, "chain_km": 500, "last_service_date": "", "last_oil_date": ""}

def clean_val(kind, v, maxlen, name):
    if kind == NUM:
        if v in ("", None): return None
        try: x = float(v)
        except (TypeError, ValueError): raise ValueError(f"{name} must be a number")
        if x != x or abs(x) > 1e9: raise ValueError(f"{name} is out of range")
        return int(x) if x == int(x) else round(x, 2)
    if kind == DATE:
        v = (v or "").strip()
        if not v: return ""
        try: datetime.date.fromisoformat(v)
        except ValueError: raise ValueError(f"{name} must be a date like 2026-12-31")
        return v
    s = str(v if v is not None else "").strip()
    return s.replace("<", "").replace(">", "")[:maxlen]

def clean(d, schema):
    out = {}
    for k, (kind, maxlen, req) in schema.items():
        v = clean_val(kind, d.get(k), maxlen, k)
        if req and v in ("", None): raise ValueError(f"{k} is required")
        if v not in ("", None): out[k] = v
    return out

def ensure():
    """First run: one sample bike so the demo is not empty. It is marked demo so the UI can say 'sample data'."""
    B = store.D["bikes"]
    if not B:
        i = store.uid(); B[i] = {"id": i, "name": "My Bike", "model": "Sample motorcycle", "reg": "", "year": "", "demo": True,
                                 "profile": default_profile(), "docs": [], "services": [], "expenses": [], "mods": []}
        store.D["active"] = i; store.save(True)
    if store.D["active"] not in B: store.D["active"] = next(iter(B)); store.save(True)

def active(): ensure(); return store.D["bikes"][store.D["active"]]
def get(i):
    b = store.D["bikes"].get(i)
    if not b: raise KeyError("no such bike")
    return b

def _fields(b, d):
    for k, n in (("name", 40), ("model", 60), ("reg", 20), ("year", 6)):
        if k in d: b[k] = clean_val(STR, d[k], n, k)
    if not b.get("name"): b["name"] = "My Bike"
    pr = d.get("profile") or {}
    for k, kind in PROFILE.items():
        if k in pr:
            v = clean_val(kind, pr[k], 0, k)
            if v is not None: b["profile"][k] = v
    if pr: b["demo"] = False        # the rider edited the numbers, so they are no longer sample values

def create(d):
    i = store.uid()
    b = {"id": i, "name": "", "model": "", "reg": "", "year": "", "demo": False, "profile": default_profile(), "docs": [], "services": [], "expenses": [], "mods": []}
    b["profile"].update({"trip": 0, "last_service_date": "", "last_oil_date": ""})
    _fields(b, d); store.D["bikes"][i] = b; store.save(True); return b

def update(i, d): b = get(i); _fields(b, d); store.save(True); return b

def delete(i):
    if len(store.D["bikes"]) <= 1: raise ValueError("you need at least one bike")
    get(i); del store.D["bikes"][i]; ensure(); store.save(True)

def listing():
    ensure()
    return {"active": store.D["active"], "bikes": [{k: b[k] for k in ("id", "name", "model", "reg", "year", "demo")} | {"odometer": b["profile"].get("odometer")}
                                                    for b in store.D["bikes"].values()]}

def add(coll, d):
    b = active(); rec = clean(d, SCHEMA[coll]); rec["id"] = store.uid()
    if coll == "services" and rec["type"] not in SERVICE_TYPES: raise ValueError("unknown service type")
    if coll == "expenses" and rec["cat"] not in EXPENSE_CATS: raise ValueError("unknown expense category")
    if coll == "mods": rec.setdefault("date", iso(today()))
    b[coll].append(rec)
    if coll == "services": apply_service(b, rec)
    store.save(True); return rec

def remove(coll, rid):
    b = active(); n = len(b[coll]); b[coll] = [r for r in b[coll] if r["id"] != rid]
    if len(b[coll]) == n: raise KeyError("not found")
    store.save(True)

def apply_service(b, r):
    """A service record resets the matching maintenance counters. This is how 'time since last service' stays honest."""
    p = b["profile"]; odo = r.get("odo")
    if odo is not None and odo > p.get("odometer", 0): p["odometer"] = odo
    odo = odo if odo is not None else p.get("odometer", 0)
    if r["type"] == "service": p["last_service_date"] = r["date"]; p["next_service"] = odo + p.get("service_km", 3000); p["last_oil"] = odo; p["last_oil_date"] = r["date"]
    elif r["type"] == "oil": p["last_oil"] = odo; p["last_oil_date"] = r["date"]
    elif r["type"] == "chain": p["last_chain_lube"] = odo
    elif r["type"] == "brake": p["brake_pad"] = 100
    b["demo"] = False

def last_service(b=None):
    b = b or active(); s = [r for r in b["services"] if r["type"] == "service"]
    return max(s, key=lambda r: r["date"]) if s else None

def expenses_summary(b=None):
    b = b or active(); rows = [{"date": r["date"], "cat": r["cat"], "amount": r["amount"], "src": "expense"} for r in b["expenses"]]
    rows += [{"date": r["date"], "cat": "service" if r["type"] != "repair" else "repair", "amount": r["cost"], "src": "service"} for r in b["services"] if r.get("cost")]
    rows += [{"date": r.get("date") or iso(today()), "cat": "accessory", "amount": r["cost"], "src": "mod"} for r in b["mods"] if r.get("cost")]
    cut = iso(today() - datetime.timedelta(days=30))
    by_cat, by_month = {}, {}
    for r in rows:
        by_cat[r["cat"]] = by_cat.get(r["cat"], 0) + r["amount"]; m = r["date"][:7]; by_month[m] = by_month.get(m, 0) + r["amount"]
    return {"total": round(sum(r["amount"] for r in rows), 2), "last_30d": round(sum(r["amount"] for r in rows if r["date"] >= cut), 2),
            "by_cat": {k: round(v, 2) for k, v in sorted(by_cat.items(), key=lambda x: -x[1])},
            "by_month": {k: round(by_month[k], 2) for k in sorted(by_month)[-6:]}, "count": len(rows)}

def docs_status(b=None):
    """All documents with an expiry, including PUC and insurance from the profile. days<0 means expired."""
    b = b or active(); out = []
    for t, k in (("PUC", "puc"), ("Insurance", "insurance")):
        if b["profile"].get(k): out.append({"type": t, "expiry": b["profile"][k], "id": k})
    out += [{"type": d["type"], "expiry": d["expiry"], "id": d["id"]} for d in b["docs"] if d.get("expiry")]
    for d in out:
        try: d["days"] = (datetime.date.fromisoformat(d["expiry"]) - today()).days
        except ValueError: d["days"] = None
    return out
