"""Smart ride tracking + analytics.
GPS points in -> distance, speed, duration, route, harsh braking / acceleration, eco score out.
Provenance: distance/speed/route/events are GPS-DERIVED (source 'gps', or 'sim' for demo rides). The eco score and insights are ESTIMATES."""
import math, statistics, time, datetime
import store, lang

BRAKE_MS2, ACCEL_MS2, MIN_BRAKE_KMH = -3.0, 2.5, 15     # harsh thresholds (about 0.3 g and 0.25 g)
MAX_ACC_M, MAX_KMH, MOVE_KMH = 50, 220, 3               # ignore poor fixes, impossible jumps; below MOVE_KMH we count as stopped
ROUTE_MAX = 400

def hav(la1, lo1, la2, lo2):
    p1, p2 = math.radians(la1), math.radians(la2); dp = p2 - p1; dl = math.radians(lo2 - lo1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))

# ---------------- one ride, built incrementally ----------------
def new_ride(src="gps", t0=None, bike_id=None):
    return {"id": store.uid(), "bike": bike_id or store.D["active"], "start": t0, "source": src, "pts": [], "dist_m": 0.0, "max_kmh": 0.0,
            "moving_s": 0.0, "over_s": 0.0, "events": [], "last": None, "recent": [], "n": 0, "mean": 0.0, "m2": 0.0, "n_in": 0, "n_bad": 0}

def feed(r, p, limit=0):
    """Add one GPS sample {t, lat, lon, speed (km/h, optional), acc (m, optional)}. Returns 'ok' or why it was ignored."""
    try:
        t, la, lo = float(p["t"]), float(p["lat"]), float(p["lon"])
        acc = float(p["acc"]) if p.get("acc") is not None else None
        sp = float(p["speed"]) if p.get("speed") is not None else None
    except (KeyError, TypeError, ValueError): r["n_bad"] += 1; return "bad"
    if t > 1e11: t /= 1000                                        # tolerate JavaScript millisecond timestamps
    if not (-90 <= la <= 90 and -180 <= lo <= 180) or not math.isfinite(t) or (sp is not None and not (0 <= sp <= 400)):
        r["n_bad"] += 1; return "bad"
    if acc is not None and acc > MAX_ACC_M: return "poor_fix"
    if r["start"] is None: r["start"] = t
    last = r["last"]; v = sp if sp is not None else 0.0; moved = 0.0
    if last:
        dt = t - last[0]
        if dt <= 0: return "old"
        moved = hav(last[1], last[2], la, lo); implied = moved / dt * 3.6
        if implied > MAX_KMH: r["n_bad"] += 1; return "jump"
        if sp is None: v = implied if dt <= 30 else 0.0
        if v > MAX_KMH: return "jump"
        if moved >= 4 or v >= 5: r["dist_m"] += moved
        r["moving_s"] += min(dt, 10) if v >= MOVE_KMH else 0
        if limit and v > limit: r["over_s"] += min(dt, 10)
        if 0.5 <= dt <= 4:                                      # harsh events need consecutive samples
            a = (v - last[3]) / 3.6 / dt
            kind = "harsh_brake" if (a <= BRAKE_MS2 and last[3] >= MIN_BRAKE_KMH) else "harsh_accel" if a >= ACCEL_MS2 else None
            if kind and not any(e["type"] == kind and t - e["t"] < 5 for e in r["events"][-4:]):
                r["events"].append({"t": t, "type": kind, "lat": la, "lon": lo, "a": round(a, 2), "v0": round(last[3]), "v1": round(v)})
    r["recent"] = (r["recent"] + [v])[-3:]
    sv = statistics.median(r["recent"])                         # median of 3 removes single GPS speed spikes from the max
    r["max_kmh"] = max(r["max_kmh"], sv)
    if v >= MOVE_KMH:                                           # Welford: running mean/variance of moving speed, for the smoothness penalty
        r["n"] += 1; dlt = v - r["mean"]; r["mean"] += dlt / r["n"]; r["m2"] += dlt * (v - r["mean"])
    r["n_in"] += 1
    if not r["pts"] or moved >= 5 or t - r["pts"][-1][0] >= 10:
        if len(r["pts"]) < 20000: r["pts"].append([t, round(la, 6), round(lo, 6), round(v, 1)])
    r["last"] = [t, la, lo, v]; return "ok"

def eco_score(dist_km, brakes, accels, over_frac, cv):
    """ESTIMATE, 0-100. Heuristic: smooth riding scores high. Penalties: harsh events per 10 km, share of time over the speed limit,
    and jerky speed (coefficient of variation above 0.35). Not calibrated against measured fuel use."""
    if dist_km < 0.5: return None
    s = 100 - min(40, (brakes + accels) / dist_km * 10 * 6) - min(30, over_frac * 60) - min(15, max(0, cv - 0.35) * 30)
    return round(max(0, s))

def finish(r, end_t=None):
    pts = r["pts"]; end = end_t or (r["last"][0] if r["last"] else r["start"] or time.time()); start = r["start"] or end
    dist = r["dist_m"] / 1000; dur = max(0, end - start); mov = r["moving_s"]
    sd = math.sqrt(r["m2"] / r["n"]) if r["n"] > 1 else 0; cv = sd / r["mean"] if r["mean"] else 0
    hb = sum(e["type"] == "harsh_brake" for e in r["events"]); ha = sum(e["type"] == "harsh_accel" for e in r["events"])
    over = r["over_s"] / mov if mov else 0
    step = max(1, len(pts) // ROUTE_MAX)
    b = store.D["bikes"].get(r["bike"], {})
    return {"id": r["id"], "bike": r["bike"], "bike_name": b.get("name", ""), "start": round(start), "end": round(end), "duration_s": round(dur), "moving_s": round(mov),
            "dist_km": round(dist, 2), "avg_kmh": round(dist / (dur / 3600), 1) if dur > 30 else 0, "moving_avg_kmh": round(dist / (mov / 3600), 1) if mov > 30 else 0,
            "max_kmh": round(r["max_kmh"]), "harsh_brake": hb, "harsh_accel": ha, "over_pct": round(over * 100), "events": r["events"][:60],
            "eco": eco_score(dist, hb, ha, over, cv), "source": r["source"], "route": [[p[1], p[2]] for p in pts[::step]] + ([[pts[-1][1], pts[-1][2]]] if pts and step > 1 else [])}

# ---------------- the live ride (persisted so a server restart does not lose it) ----------------
def active(): return store.D.get("active_ride")

def start(src="gps"):
    a = active()
    if a: return a, False
    store.D["active_ride"] = new_ride(src, None); store.D["active_ride"]["started_at"] = time.time(); store.save(True)
    return store.D["active_ride"], True

def points(pts, src="gps"):
    """Batch of samples (also used to flush an offline queue). Auto-starts a ride so no data is lost."""
    r, _ = start(src); res = {"ok": 0, "ignored": 0}
    for p in pts[:2000]:
        out = feed(r, p, lang.SET.get("speed_limit") or 0); res["ok" if out == "ok" else "ignored"] += 1
    store.save(); return res

def stop(discard=False):
    r = store.D.get("active_ride")
    if not r: return None
    store.D["active_ride"] = None; res = finish(r, r["last"][0] if r["last"] else r.get("started_at"))
    if discard or res["dist_km"] < 0.05: store.save(True); return dict(res, saved=False)
    store.D["rides"].append(res); del store.D["rides"][:-500]
    if res["source"] == "gps" and lang.SET.get("auto_odo", True): _add_odometer(res["dist_km"], res["bike"])
    store.save(True); return dict(res, saved=True)

def _add_odometer(km, bike_id):
    import bike
    if bike_id != store.D["active"] or bike.SRC.get("odometer") == "sensor": return      # the bike's own odometer wins
    bike.STATE["odometer"] = round(bike.STATE.get("odometer", 0) + km, 1); bike.STATE["trip"] = round(bike.STATE.get("trip", 0) + km, 1)
    bike.SRC["odometer"] = "estimate"; bike.save_profile()

def import_ride(pts, src="sim", bike_id=None):
    r = new_ride(src, None, bike_id)
    for p in pts: feed(r, p, lang.SET.get("speed_limit") or 0)
    res = finish(r); store.D["rides"].append(res); store.D["rides"].sort(key=lambda x: x["start"]); del store.D["rides"][:-500]; store.save(True); return res

def live():
    r = active()
    if not r: return None
    last = r["last"]; fresh = last and time.time() - last[0] < 20 if r["source"] == "gps" else bool(last)
    dur = (last[0] - r["start"]) if last and r["start"] else 0
    dist = r["dist_m"] / 1000
    return {"id": r["id"], "source": r["source"], "dist_km": round(dist, 2), "duration_s": round(dur), "speed": round(last[3]) if fresh else 0,
            "avg_kmh": round(dist / (dur / 3600), 1) if dur > 30 else 0, "max_kmh": round(r["max_kmh"]),
            "events": len(r["events"]), "pos": [last[1], last[2]] if last else None, "n": r["n_in"]}

def listing(limit=50, bike_id=None):
    rows = [x for x in store.D["rides"] if not bike_id or x["bike"] == bike_id]
    return [{k: v for k, v in x.items() if k not in ("route", "events")} for x in reversed(rows[-limit:])]

def get(rid):
    for x in store.D["rides"]:
        if x["id"] == rid: return x
    raise KeyError("no such ride")

def delete(rid):
    n = len(store.D["rides"]); store.D["rides"] = [x for x in store.D["rides"] if x["id"] != rid]
    if len(store.D["rides"]) == n: raise KeyError("no such ride")
    store.save(True)

def last_summary():
    rows = store.D["rides"]
    if not rows: return None
    x = rows[-1]; return {k: x[k] for k in ("start", "dist_km", "duration_s", "avg_kmh", "max_kmh", "harsh_brake", "harsh_accel", "eco", "source")}

# ---------------- analytics (all derived from stored rides) ----------------
def _day(ts): return datetime.date.fromtimestamp(ts)

def _agg(rows):
    km = sum(x["dist_km"] for x in rows); hrs = sum(x["duration_s"] for x in rows) / 3600
    eco = [(x["eco"], x["dist_km"]) for x in rows if x["eco"] is not None]
    return {"rides": len(rows), "km": round(km, 1), "hours": round(hrs, 2), "avg_kmh": round(km / hrs, 1) if hrs > 0.01 else 0,
            "max_kmh": max([x["max_kmh"] for x in rows], default=0), "harsh_brake": sum(x["harsh_brake"] for x in rows),
            "harsh_accel": sum(x["harsh_accel"] for x in rows),
            "eco": round(sum(e * w for e, w in eco) / sum(w for _, w in eco)) if eco else None}

def report(days=7, include_sim=True, bike_id=None):
    today = datetime.date.today(); lo = today - datetime.timedelta(days=days - 1); plo = lo - datetime.timedelta(days=days)
    allr = [x for x in store.D["rides"] if (include_sim or x["source"] != "sim") and (not bike_id or x["bike"] == bike_id)]
    cur = [x for x in allr if _day(x["start"]) >= lo]; prev = [x for x in allr if plo <= _day(x["start"]) < lo]
    series = []
    for i in range(days):
        d = lo + datetime.timedelta(days=i); rs = [x for x in cur if _day(x["start"]) == d]
        series.append({"date": d.isoformat(), "km": round(sum(x["dist_km"] for x in rs), 1), "rides": len(rs)})
    a, p = _agg(cur), _agg(prev)
    out = {"days": days, **a, "series": series, "prev": p, "sim_rides": sum(x["source"] == "sim" for x in cur),
           "km_change_pct": round((a["km"] - p["km"]) / p["km"] * 100) if p["km"] else None, "source": "gps-derived; eco score is an estimate"}
    out["insights"] = insights(a, cur); return out

def insights(a, rows):
    """Plain-language riding behaviour insights. Rule-based, derived from the numbers above (estimates, not diagnoses)."""
    out = []; km = a["km"]
    if not rows: return ["No rides in this period yet. Start a ride to see insights."]
    lim = lang.SET.get("speed_limit") or 0
    hb100 = a["harsh_brake"] / km * 100 if km else 0; ha100 = a["harsh_accel"] / km * 100 if km else 0
    if a["harsh_brake"] + a["harsh_accel"] == 0: out.append("Smooth riding: no sudden braking or hard acceleration detected.")
    if hb100 >= 8: out.append(f"You braked hard {a['harsh_brake']} times ({hb100:.0f} per 100 km). Look further ahead and ease off the throttle earlier.")
    if ha100 >= 8: out.append(f"{a['harsh_accel']} hard accelerations ({ha100:.0f} per 100 km). Rolling on the throttle gently saves fuel and tyres.")
    over = [x["over_pct"] for x in rows if x.get("over_pct") is not None]
    if lim and over and statistics.mean(over) >= 15: out.append(f"About {statistics.mean(over):.0f}% of your riding time was above your {lim} km/h limit.")
    ecos = [x["eco"] for x in rows if x["eco"] is not None]
    if len(ecos) >= 4 and statistics.mean(ecos[-2:]) - statistics.mean(ecos[:2]) >= 5: out.append("Your eco score is improving over this period. Keep it up.")
    if len(ecos) >= 4 and statistics.mean(ecos[:2]) - statistics.mean(ecos[-2:]) >= 5: out.append("Your eco score has dropped recently. Check for more stop-and-go or harsher braking.")
    if a["avg_kmh"] and a["avg_kmh"] < 20: out.append("Low average speed suggests heavy traffic. Mileage is usually lowest in stop-and-go riding.")
    return out or ["Riding looks steady. No unusual patterns found."]

def speed_trend(n=20, include_sim=True):
    rows = [x for x in store.D["rides"] if (include_sim or x["source"] != "sim") and x["avg_kmh"]][-n:]
    pts = [{"id": x["id"], "start": x["start"], "avg": x["avg_kmh"], "max": x["max_kmh"], "source": x["source"]} for x in rows]
    slope = None
    if len(pts) >= 4:
        xs = list(range(len(pts))); ys = [p["avg"] for p in pts]; mx, my = statistics.mean(xs), statistics.mean(ys)
        den = sum((x - mx) ** 2 for x in xs); slope = round(sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den, 2) if den else 0
    return {"points": pts, "slope_kmh_per_ride": slope, "trend": None if slope is None else "rising" if slope > 0.3 else "falling" if slope < -0.3 else "steady"}

def eco_overview(n=5):
    rows = [x for x in store.D["rides"] if x["eco"] is not None][-n:]
    return {"count": len(rows), "score": round(sum(x["eco"] for x in rows) / len(rows)) if rows else None,
            "history": [{"start": x["start"], "eco": x["eco"], "source": x["source"]} for x in store.D["rides"][-20:] if x["eco"] is not None], "basis": "estimate"}
