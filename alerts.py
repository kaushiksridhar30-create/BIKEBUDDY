"""Proactive alerts. Rules look at the TRUSTED view of the data (bike.view) and produce 'conditions'.
tick() turns conditions into announcements: spoken once per occurrence (critical ones repeat every 5 min until fixed),
and every occurrence is written to the fault log. Missing sensors produce no alert (we never guess)."""
import threading, time
import bike, garage, store, lang, rides

LOCK = threading.RLock()
SEV = {"info": 0, "warn": 1, "critical": 2}
REPEAT_S = {"critical": 300, "warn": 0, "info": 0}      # 0 = announce once, re-arm only after the condition clears
CLEAR_S = [10]                                          # a condition must stay clear this long before it can re-announce (stops flapping)
ACTIVE, ANN, SEQ = {}, [], [0]
EPOCH = store.uid()                                     # changes on server restart so clients know to reset their cursor
EN = lang.LANGS["english"]["T"]

def conditions():
    s = bike.view(); out = []
    def add(key, kind, level, src, **p): out.append({"key": key, "kind": kind, "level": level, "src": src, "p": p})
    sr = lambda k: bike.SRC.get(k, "user")
    run = bike.running(); v = s.get("battery")
    if v is not None:
        if v < 12.0: add("batt", "batt", "critical", sr("battery"), v=v)
        elif run is False and v < 12.4: add("batt", "battw", "warn", sr("battery"), v=v)
        elif run is True and v < 13.2: add("batt", "chlow", "warn", sr("battery"), v=v)
        elif run is True and v > 14.9: add("batt", "chhigh", "critical", sr("battery"), v=v)
    if s.get("engine_temp") is not None and s["engine_temp"] > 105: add("temp", "temp", "critical", sr("engine_temp"), t=s["engine_temp"])
    f = s.get("fuel")
    if f is not None and f < 15: add("fuel", "fuel", "critical" if f < 8 else "warn", sr("fuel"), p=f, km=int(f * bike.KM_PER_PCT))
    for k, w in (("tyre_front", "w_front"), ("tyre_rear", "w_rear")):
        p = s.get(k)
        if p is None: continue
        hist = [x[1] for x in bike.HIST.get(k, []) if time.time() - x[0] < 600]
        if hist and max(hist) - p >= 3: add(k, "drop", "critical", sr(k), w=w, a=max(hist), p=p)
        elif p < bike.PSI[0]: add(k, "tyre", "warn", sr(k), w=w, p=p, lo=bike.PSI[0], hi=bike.PSI[1])
        elif p > bike.PSI[1] + 4: add(k, "tyreh", "warn", sr(k), w=w, p=p, lo=bike.PSI[0], hi=bike.PSI[1])
    o = s.get("odometer")
    if o is not None:
        rem = s["next_service"] - o
        if rem <= 0: add("svc", "svc0", "warn", "estimate", km=int(-rem))
        elif rem <= 200: add("svc", "svc", "info", "estimate", km=int(rem))
        m = months_since(s.get("last_service_date"))
        if m is not None and m >= s.get("service_months", 6): add("svct", "svct", "warn", "estimate", m=m)
        since = o - s["last_oil"]
        if since >= s.get("oil_km", 3000): add("oil", "oil", "warn", "estimate", km=int(since))
        elif since >= 0.9 * s.get("oil_km", 3000): add("oil", "oils", "info", "estimate", km=int(s.get("oil_km", 3000) - since))
        if o - s["last_chain_lube"] >= s.get("chain_km", 500): add("chain", "chain", "info", "estimate", km=int(o - s["last_chain_lube"]))
    if s.get("brake_pad") is not None and s["brake_pad"] < 20: add("brake", "brake", "warn", "user", b=s["brake_pad"])
    for d in garage.docs_status():
        if d["days"] is None or d["days"] > 30: continue
        if d["days"] < 0: add("doc:" + d["id"], "docx", "warn", "user", d=d["type"])
        else: add("doc:" + d["id"], "doc", "warn", "user", d=d["type"], c=d["days"])
    if bike.conn()["status"] == "disconnected": add("link", "link", "warn", "sensor")
    lv = rides.live(); lim = lang.SET.get("speed_limit") or 0
    if lv and lim and (lv.get("speed") or 0) > lim: add("speed", "speed", "info", "gps", s=round(lv["speed"]), l=lim)
    return out

def months_since(d):
    import datetime
    try: x = datetime.date.fromisoformat(d)
    except (TypeError, ValueError): return None
    return (datetime.date.today().year - x.year) * 12 + datetime.date.today().month - x.month - (datetime.date.today().day < x.day)

def text(a, lg=None):
    L = lang.LANGS[lg or lang.SET["lang"]]["T"]; p = dict(a["p"])
    if "w" in p: p["w"] = L[p["w"]]
    return L["al_" + a["kind"]].format(n=lang.SET["name"], **p)

def _announce(c, kind=None):
    SEQ[0] += 1; c = dict(c, kind=kind or c["kind"])
    ANN.append({"seq": SEQ[0], "key": c["key"], "level": c["level"], "kind": c["kind"], "text": text(c), "text_en": text(c, "english"), "ts": time.time(), "src": c["src"]})
    del ANN[:-100]

def _log_open(c):
    e = {"id": store.uid(), "key": c["key"], "kind": c["kind"], "level": c["level"], "text": text(c, "english"), "src": c["src"],
         "t0": round(time.time()), "t1": None, "bike": store.D["active"]}
    store.D["alerts"].append(e); del store.D["alerts"][:-500]; store.save(); return e

def tick():
    now = time.time(); cond = {c["key"]: c for c in conditions()}
    with LOCK:
        for key, c in cond.items():
            st = ACTIVE.get(key)
            if st and st["kind"] != c["kind"]:                      # same sensor, different problem (e.g. weak -> critical)
                _close(key, st, now); st = None
            if not st:
                ACTIVE[key] = st = {"since": now, "level": c["level"], "kind": c["kind"], "ann": 0, "clear": None, "log": _log_open(c)}
            st["clear"] = None; st["c"] = c
            rep = REPEAT_S[c["level"]]
            if st["ann"] == 0 or (rep and now - st["ann"] >= rep): _announce(c); st["ann"] = now
        for key in list(ACTIVE):
            if key in cond: continue
            st = ACTIVE[key]; st["clear"] = st["clear"] or now
            if now - st["clear"] >= CLEAR_S[0]:
                _close(key, st, now)
                if key == "link" and bike.conn()["status"] in ("connected", "stale"): _announce({"key": "link", "kind": "linkok", "level": "info", "src": "sensor", "p": {}})

def _close(key, st, now):
    st["log"]["t1"] = round(now); ACTIVE.pop(key, None); store.save()

def active_alerts():
    tick()
    with LOCK:
        rows = [{"key": k, "kind": st["c"]["kind"], "level": st["c"]["level"], "src": st["c"]["src"], "since": round(st["since"]),
                 "text": text(st["c"]), "text_en": text(st["c"], "english")} for k, st in ACTIVE.items() if "c" in st and st["clear"] is None]
    return sorted(rows, key=lambda r: (-SEV[r["level"]], r["since"]))

def announcements(since=0):
    with LOCK: return [a for a in ANN if a["seq"] > since]

def fault_log(limit=100):
    return list(reversed(store.D["alerts"][-limit:]))
