"""REST endpoints for the newer features (status, telemetry, rides, analytics, safety, places, navigation, maintenance, garage, demo).
Errors: ValueError -> 400, KeyError -> 404, PermissionError -> 403 (mapped in app.py)."""
import os, time
from flask import Blueprint, jsonify, request
import alerts, bike, demo, garage, lang, maint, nav, places, rides, safety, store

bp = Blueprint("api", __name__)
def J(): return request.get_json(silent=True) or {}
def base(): return os.environ.get("PUBLIC_URL") or request.host_url

# ---------------- status: one cheap poll feeds the whole UI ----------------
@bp.get("/api/status")
def status():
    since = int(request.args.get("since", 0) or 0)
    if request.args.get("epoch") not in (None, alerts.EPOCH): since = 0          # server restarted: client cursor is meaningless
    act = alerts.active_alerts(); b = garage.active()
    return jsonify(state=bike.STATE, src=bike.provenance(), conn=bike.conn(), bike={"id": b["id"], "name": b["name"], "model": b["model"], "demo": b["demo"]},
                   alerts={"active": act, "new": alerts.announcements(since), "seq": alerts.SEQ[0], "epoch": alerts.EPOCH},
                   ride=rides.live(), sharing=len(safety.active_shares()), settings=lang.SET, now=time.time(),
                   channels=__import__("notify").channels(), contacts=len(safety.contacts()))

# ---------------- real telemetry from the bike ----------------
@bp.post("/api/telemetry")
def telemetry():
    tok = os.environ.get("TELEMETRY_TOKEN")
    if tok and request.headers.get("X-Token") != tok: raise PermissionError("bad telemetry token")
    d = J(); src = d.pop("source", "sensor")
    if src not in ("sensor", "obd", "ble", "tpms", "can"): raise ValueError("unknown source")
    return jsonify(bike.ingest(d, "sensor"))

@bp.post("/api/mode")
def mode():
    m = J().get("mode")
    if m not in ("sim", "live"): raise ValueError("mode must be sim or live")
    bike.set_mode(m); return jsonify(conn=bike.conn())

@bp.get("/api/alerts/log")
def alert_log(): return jsonify(alerts.fault_log(int(request.args.get("limit", 100))))

# ---------------- rides ----------------
@bp.post("/api/ride/start")
def ride_start():
    r, new = rides.start("sim" if J().get("source") == "sim" else "gps"); return jsonify(id=r["id"], started=new)

@bp.post("/api/ride/point")
def ride_point():
    d = J(); pts = d.get("points") or ([d] if "lat" in d else [])
    if not pts: raise ValueError("no points")
    res = rides.points(pts, "sim" if d.get("source") == "sim" else "gps")
    if pts: safety.update_location(pts[-1]["lat"], pts[-1]["lon"], pts[-1].get("speed"))
    return jsonify(**res, live=rides.live())

@bp.post("/api/ride/stop")
def ride_stop():
    r = rides.stop(discard=bool(J().get("discard")))
    return jsonify(ride={k: v for k, v in r.items() if k != "route"} if r else None, saved=bool(r and r.get("saved")))

@bp.get("/api/ride/live")
def ride_live(): return jsonify(rides.live())

@bp.get("/api/rides")
def ride_list(): return jsonify(rides.listing(int(request.args.get("limit", 50)), request.args.get("bike")))

@bp.get("/api/ride/<rid>")
def ride_get(rid): return jsonify(rides.get(rid))

@bp.delete("/api/ride/<rid>")
def ride_del(rid): rides.delete(rid); return jsonify(ok=1)

@bp.get("/api/analytics")
def analytics():
    days = max(1, min(90, int(request.args.get("days", 7))))
    return jsonify(report=rides.report(days), speed_trend=rides.speed_trend(), eco=rides.eco_overview())

# ---------------- location, contacts, sharing, SOS support ----------------
@bp.post("/api/location")
def location():
    d = J(); n = safety.update_location(d["lat"], d["lon"], d.get("speed")); return jsonify(sharing=n)

@bp.get("/api/contacts")
def contacts_list(): return jsonify(safety.contacts())

@bp.post("/api/contacts")
def contacts_add(): d = J(); return jsonify(safety.add_contact(d.get("name"), d.get("phone")))

@bp.delete("/api/contacts/<cid>")
def contacts_del(cid): safety.remove_contact(cid); return jsonify(ok=1)

@bp.post("/api/share/start")
def share_start():
    s = safety.start_share(); d = J()
    if d.get("lat") is not None: safety.update_location(d["lat"], d["lon"])
    return jsonify(token=s["token"], url=safety.url_for(s["token"], base()), expires=s["expires"])

@bp.post("/api/share/stop")
def share_stop(): safety.stop_share(J().get("token")); return jsonify(ok=1)

@bp.get("/api/shares")
def shares(): return jsonify([{"token": s["token"], "url": safety.url_for(s["token"], base()), "incident": s["incident"], "expires": s["expires"]} for s in safety.active_shares()])

@bp.get("/api/track/<tok>")      # PUBLIC by design (the contact opens it with no login). The token is the secret; the view is minimal.
def track(tok): return jsonify(safety.public_view(tok))

@bp.get("/api/emergency")
def emergency(): return jsonify(places.EMERGENCY)

# ---------------- places and navigation ----------------
def _fail(ex, kind): return jsonify(error=("offline" if kind == "net" else str(ex)), detail=str(ex)[:120]), 503

@bp.get("/api/nearby")
def nearby():
    try: return jsonify(places.nearby(request.args["kind"], request.args["lat"], request.args["lon"], limit=int(request.args.get("limit", 8))))
    except places.PlacesError as ex: return _fail(ex, "net")

@bp.get("/api/geocode")
def geocode():
    q = request.args.get("q", "").strip()
    if len(q) < 2: raise ValueError("query too short")
    f = lambda k: float(request.args[k]) if request.args.get(k) else None
    try: return jsonify(nav.geocode(q, f("lat"), f("lon")))
    except nav.NavError as ex: return _fail(ex, "net")

@bp.post("/api/route")
def route():
    d = J()
    try: return jsonify(nav.route(float(d["from"]["lat"]), float(d["from"]["lon"]), float(d["to"]["lat"]), float(d["to"]["lon"]), str(d["to"].get("name", ""))[:80]))
    except nav.NavError as ex: return _fail(ex, "net" if "offline" in str(ex) else "route")

# ---------------- maintenance ----------------
@bp.get("/api/maint")
def maintenance():
    return jsonify(reminders=maint.reminders(), suggestions=maint.suggestions(), battery=maint.battery_health(), history=maint.history(),
                   faults=alerts.fault_log(30), pace=maint.pace())

# ---------------- digital garage ----------------
@bp.get("/api/garage")
def garage_list(): return jsonify(garage.listing())

@bp.get("/api/garage/active")
def garage_active():
    b = dict(garage.active()); b["expenses_summary"] = garage.expenses_summary(b); b["docs_status"] = garage.docs_status(b); b["src"] = {"profile": "user"}
    return jsonify(b)

@bp.post("/api/garage/bike")
def garage_new(): b = garage.create(J()); return jsonify(id=b["id"])

@bp.put("/api/garage/bike/<bid>")
def garage_edit(bid):
    garage.update(bid, J())
    if bid == store.D["active"]: bike.load_profile()
    return jsonify(ok=1)

@bp.delete("/api/garage/bike/<bid>")
def garage_del(bid):
    was = bid == store.D["active"]; garage.delete(bid)
    if was: bike.switch(store.D["active"])
    return jsonify(ok=1)

@bp.post("/api/garage/switch")
def garage_switch(): bike.switch(J().get("id")); return jsonify(ok=1)

@bp.post("/api/garage/<coll>")
def garage_add(coll):
    if coll not in garage.SCHEMA: raise KeyError(coll)
    r = garage.add(coll, J()); bike.load_profile(); return jsonify(r)

@bp.delete("/api/garage/<coll>/<rid>")
def garage_rm(coll, rid):
    if coll not in garage.SCHEMA: raise KeyError(coll)
    garage.remove(coll, rid); return jsonify(ok=1)

# ---------------- demo helpers (everything created here is labelled SIMULATED) ----------------
@bp.post("/api/demo/seed")
def demo_seed(): return jsonify(demo.seed())

@bp.post("/api/demo/clear")
def demo_clear(): demo.clear(); return jsonify(ok=1)

@bp.get("/api/demo/route")
def demo_route():
    pts = demo.route_points(seed=int(time.time()) % 1000, minutes=min(15, int(request.args.get("minutes", 5))))
    return jsonify([{"dt": p["t"], "lat": p["lat"], "lon": p["lon"], "speed": round(p["speed"], 1)} for p in pts])
