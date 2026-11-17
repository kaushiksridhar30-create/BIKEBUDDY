"""Safety: emergency contacts, tokenised live-location sharing, SOS, and escalation of a crash / SOS incident.
Escalation = (1) mark the incident, (2) create a live tracking link, (3) look up the nearest hospitals, (4) message every contact.
Step 4 uses notify.py: real SMS/webhook only if configured, otherwise reported honestly as 'simulated'."""
import re, secrets, threading, time
import engine, lang, notify, places, store

INC = {}                        # incident id -> engine.Incident (in memory)
SYNC = [False]                  # tests set True to run dispatch inline
SHARE_HOURS = 12
LOCK = threading.RLock()

# ---------------- contacts ----------------
def contacts(): return store.D["contacts"]

def add_contact(name, phone):
    name = re.sub(r"[<>&\"']", "", (name or "").strip())[:30]; digits = re.sub(r"\D", "", phone or "")
    if not name: raise ValueError("name is required")
    if not 6 <= len(digits) <= 15: raise ValueError("phone number must have 6 to 15 digits")
    if len(store.D["contacts"]) >= 5: raise ValueError("up to 5 emergency contacts")
    c = {"id": store.uid(), "name": name, "phone": ("+" if (phone or "").strip().startswith("+") else "") + digits}
    store.D["contacts"].append(c); store.save(True); return c

def remove_contact(cid):
    n = len(store.D["contacts"]); store.D["contacts"] = [c for c in store.D["contacts"] if c["id"] != cid]
    if len(store.D["contacts"]) == n: raise KeyError("not found")
    store.save(True)

# ---------------- live location sharing ----------------
def _live(s): return s["active"] and time.time() < s["expires"]

def start_share(incident=None, hours=SHARE_HOURS):
    with LOCK:
        for s in store.D["shares"].values():
            if _live(s) and s.get("incident") == incident: return s
        tok = secrets.token_urlsafe(16)
        s = store.D["shares"][tok] = {"token": tok, "created": time.time(), "expires": time.time() + hours * 3600, "active": True, "incident": incident,
                                      "lat": None, "lon": None, "speed": None, "t": None, "trail": []}
        for old in [k for k, v in store.D["shares"].items() if time.time() > v["expires"] + 86400]: store.D["shares"].pop(old, None)
        store.save(True); return s

def stop_share(tok):
    s = store.D["shares"].get(tok)
    if not s: raise KeyError("not found")
    s["active"] = False; store.save(True)

def active_shares(): return [s for s in store.D["shares"].values() if _live(s)]

def update_location(lat, lon, speed=None):
    """Called every few seconds by the rider's phone while a share, SOS or ride is active."""
    lat, lon = float(lat), float(lon)
    if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError("bad coordinates")
    now = time.time()
    for s in active_shares():
        s.update(lat=lat, lon=lon, speed=speed, t=now)
        if not s["trail"] or abs(s["trail"][-1][0] - lat) + abs(s["trail"][-1][1] - lon) > 0.00008: s["trail"].append([round(lat, 6), round(lon, 6), round(now)]); del s["trail"][:-300]
    for i in INC.values():
        if i.status in ("escalated", "checking") and i.loc != "demo": i.lat, i.lon, i.loc = lat, lon, "gps"
    store.save()
    return len(active_shares())

def public_view(tok):
    """What a contact sees. Deliberately minimal: first name, position, speed, status. No bike, ride or contact data."""
    s = store.D["shares"].get(tok)
    if not s or not _live(s): return {"active": False}
    st = "ok"
    if s.get("incident") in INC: st = {"escalated": "emergency", "checking": "checking", "false_alarm": "ok"}.get(INC[s["incident"]].status, "ok")
    return {"active": True, "rider": lang.SET.get("rider") or "Rider", "status": st, "lat": s["lat"], "lon": s["lon"], "speed": s["speed"], "updated": s["t"],
            "trail": s["trail"][-120:], "emergency": places.EMERGENCY}

def url_for(tok, base): return f"{base.rstrip('/')}/track/{tok}"

# ---------------- incidents ----------------
def message(inc, link, hospital=None):
    who = lang.SET.get("rider") or "Rider"
    head = {"sos": f"SOS from {who}.", "crash": f"{who} may have crashed (impact detected).", "drop": f"Alert for {who}."}[inc.mode]
    loc = f" Location: https://maps.google.com/?q={inc.lat},{inc.lon}" if inc.lat is not None else " Location unknown (no GPS fix)."
    h = f" Nearest hospital: {hospital['name'] or 'unnamed'} ({hospital['dist_m'] / 1000:.1f} km)." if hospital else ""
    return f"{head}{loc} Live: {link}{h} Sent by Bike Buddy. Please call them or 112."

def escalate(inc, base_url, reason=""):
    if inc.status == "escalated" and inc.notified: return inc          # idempotent: a second trigger never double-sends
    inc.status = "escalated"
    inc.add("system", f"ESCALATED{': ' + reason if reason else ''}")
    t = threading.Thread(target=dispatch, args=(inc, base_url), daemon=True)
    if SYNC[0]: dispatch(inc, base_url)
    else: t.start()
    return inc

def dispatch(inc, base_url):
    with LOCK:
        if inc.notified: return
        inc.notified = [{"contact": "-", "channel": "pending", "status": "pending", "detail": ""}]
    sh = start_share(incident=inc.id)
    if inc.lat is not None: sh.update(lat=inc.lat, lon=inc.lon, t=time.time())
    inc.share = {"token": sh["token"], "url": url_for(sh["token"], base_url)}; inc.add("system", "Live tracking link created")
    hosp = None
    if inc.lat is not None:
        try:
            inc.hospitals = places.nearby("hospital", inc.lat, inc.lon, limit=3, timeout=4)["items"]; hosp = inc.hospitals[0] if inc.hospitals else None
            if hosp: inc.add("system", f"Nearest hospital: {hosp['name'] or 'unnamed'}, {hosp['dist_m'] / 1000:.1f} km")
        except Exception: inc.add("system", "Hospital lookup failed (offline). Call 108 / 112.")
    msg = message(inc, inc.share["url"], hosp); res = []
    cs = contacts()
    if not cs: res.append({"contact": "-", "channel": "none", "status": "no_contacts", "detail": "No emergency contacts saved"}); inc.add("system", "No emergency contacts saved: add one in Safety")
    for c in cs:
        for r in notify.send(c, msg):
            res.append(r); inc.add("system", f"Alert to {c['name']}: {r['status'].upper()} via {r['channel']}" + (" (nothing was actually sent)" if r["status"] == "simulated" else ""))
    inc.notified = res; inc.message = msg

def open_incident(mode, e):
    inc = engine.Incident(mode, e); INC[inc.id] = inc; return inc

def sos(e, base_url):
    inc = open_incident("sos", e); inc.add("rider", "pressed SOS"); return escalate(inc, base_url, "SOS pressed")

def cancel(inc, base_url=""):
    was = inc.status == "escalated"
    inc.status = "false_alarm"; inc.add("rider", "cancelled")
    if inc.share:
        try: stop_share(inc.share["token"])
        except KeyError: pass
    if was and inc.notified:
        who = lang.SET.get("rider") or "Rider"
        for c in contacts(): notify.send(c, f"False alarm: {who} is safe. Ignore the earlier Bike Buddy alert.")
        inc.add("system", "Follow-up sent: false alarm")
