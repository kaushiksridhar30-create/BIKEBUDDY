"""Predictive maintenance. Reminders by distance AND time, a battery-health trend from real voltage history,
a riding-pace projection ('you will reach your service in about N days'), and suggestions.
Everything here is an ESTIMATE built from USER-ENTERED service data plus measured data; the basis is always returned so the UI can say so."""
import datetime, hashlib, json, statistics, time
import bike, garage, store, llm, rides

def _date(s):
    try: return datetime.date.fromisoformat(s)
    except (TypeError, ValueError): return None

def _due_date(last, months):
    d = _date(last)
    return d + datetime.timedelta(days=round(months * 30.44)) if d and months else None

def pace(days=30):
    """Average km/day from recent rides. Real (gps) rides are preferred; simulated rides are used only if there are no real ones, and flagged."""
    cut = time.time() - days * 86400; rows = [x for x in store.D["rides"] if x["start"] >= cut and x["bike"] == store.D["active"]]
    real = [x for x in rows if x["source"] != "sim"]; use = real or rows
    if not use: return {"km_per_day": None, "rides": 0, "basis": "none"}
    return {"km_per_day": round(sum(x["dist_km"] for x in use) / days, 1), "rides": len(use), "basis": "gps" if real else "simulated"}

def _status(rem_km, rem_days, interval_km):
    if (rem_km is not None and rem_km <= 0) or (rem_days is not None and rem_days <= 0): return "overdue"
    if (rem_km is not None and rem_km <= max(200, 0.1 * (interval_km or 0))) or (rem_days is not None and rem_days <= 14): return "soon"
    return "ok"

def reminders():
    s = bike.STATE; odo = s.get("odometer", 0); today = datetime.date.today(); pc = pace(); out = []
    def item(key, title, rem_km, interval_km, due_on, note=""):
        rem_days = (due_on - today).days if due_on else None
        proj = round(rem_km / pc["km_per_day"]) if rem_km and rem_km > 0 and pc["km_per_day"] else None
        used = 1 - rem_km / interval_km if (rem_km is not None and interval_km) else None
        out.append({"key": key, "title": title, "due_km": None if rem_km is None else round(rem_km), "due_days": rem_days,
                    "due_on": due_on.isoformat() if due_on else None, "interval_km": interval_km, "progress": None if used is None else round(max(0, min(1, used)), 2),
                    "status": _status(rem_km, rem_days, interval_km), "projected_days": proj, "projected_basis": pc["basis"] if proj else None,
                    "basis": "distance + time" if due_on else "distance", "note": note})
    item("service", "Service", s["next_service"] - odo, s.get("service_km", 3000), _due_date(s.get("last_service_date"), s.get("service_months", 6)))
    item("oil", "Oil change", s.get("oil_km", 3000) - (odo - s["last_oil"]), s.get("oil_km", 3000), _due_date(s.get("last_oil_date"), s.get("service_months", 6)))
    item("chain", "Chain lube", s.get("chain_km", 500) - (odo - s["last_chain_lube"]), s.get("chain_km", 500), None)
    bp = s.get("brake_pad")
    if bp is not None: out.append({"key": "brake", "title": "Brake pads", "due_km": None, "due_days": None, "due_on": None, "interval_km": None, "progress": round(1 - bp / 100, 2),
                                   "status": "overdue" if bp < 10 else "soon" if bp < 20 else "ok", "projected_days": None, "projected_basis": None,
                                   "basis": "user-entered at last check", "note": f"{bp}% pad life left"})
    for d in garage.docs_status():
        if d["days"] is None: continue
        out.append({"key": "doc:" + d["id"], "title": d["type"], "due_km": None, "due_days": d["days"], "due_on": d["expiry"], "interval_km": None, "progress": None,
                    "status": "overdue" if d["days"] < 0 else "soon" if d["days"] <= 30 else "ok", "projected_days": None, "projected_basis": None, "basis": "expiry date", "note": ""})
    return out

def history(limit=100):
    rows = sorted(garage.active()["services"], key=lambda r: (r["date"], r.get("odo") or 0), reverse=True)[:limit]
    notes = [{"id": "n%d" % i, "date": "", "type": "note", "note": n} for i, n in enumerate(store.D["notes"][-20:])]
    return {"services": rows, "voice_notes": notes}

def battery_health():
    """Trend of RESTING battery voltage (engine known to be off), sampled every 10 min from live telemetry. Needs 5+ samples over 2+ days."""
    me = store.D["active"]; rows = [h for h in store.D["batt_hist"] if h["bike"] == me]
    if not rows: return {"status": "no_data", "basis": "none", "message": "No battery history yet. It builds up from live sensor readings while the engine is off."}
    sim = all(h.get("sim") for h in rows); basis = "simulated" if sim else "sensor"
    rest = [h for h in rows if h["run"] is False][-400:]
    if not rest: return {"status": "no_data", "basis": basis, "message": "Battery readings exist, but none were taken with the engine known to be off."}
    last = statistics.mean(h["v"] for h in rest[-3:]); span = (rest[-1]["t"] - rest[0]["t"]) / 86400
    out = {"basis": basis, "samples": len(rest), "resting_v": round(last, 2), "span_days": round(span, 1)}
    out["status"] = "good" if last >= 12.6 else "ok" if last >= 12.4 else "weak" if last >= 12.0 else "poor"
    if len(rest) < 5 or span < 2: out.update(trend="collecting", message="Collecting data to estimate a trend."); return out
    xs = [(h["t"] - rest[0]["t"]) / 86400 for h in rest]; ys = [h["v"] for h in rest]; mx, my = statistics.mean(xs), statistics.mean(ys)
    den = sum((x - mx) ** 2 for x in xs); slope = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den if den else 0
    out["trend_v_per_week"] = round(slope * 7, 3); out["trend"] = "falling" if slope * 7 < -0.05 else "rising" if slope * 7 > 0.05 else "steady"
    if slope < 0 and last > 12.0:
        d = (last - 12.0) / -slope; out["est_days_to_12v"] = round(d) if d < 365 else None
    out["message"] = {"falling": "Resting voltage is falling. Estimate only; get the battery and charging system checked if it continues.",
                      "steady": "Resting voltage is steady.", "rising": "Resting voltage is rising (recent charge or ride)."}[out["trend"]]
    return out

def suggestions():
    """Rule-based by default (always available, always grounded). If an LLM key is set, the model rewrites them using the same data."""
    out = []; rem = {r["key"]: r for r in reminders()}; pc = pace(); bh = battery_health()
    for k, why in (("service", "Regular servicing prevents bigger repair bills."), ("oil", "Old oil wears the engine faster."), ("chain", "A dry chain wears the sprockets and wastes power.")):
        r = rem[k]; km = r["due_km"]
        if r["status"] == "overdue": out.append({"priority": 1, "title": f"{r['title']} is overdue", "why": why, "basis": "estimate"})
        elif r["status"] == "soon":
            when = f" At your recent pace (~{pc['km_per_day']} km/day) that is about {r['projected_days']} days away." if r["projected_days"] else ""
            out.append({"priority": 2, "title": f"{r['title']} due in {km} km" if km is not None and km > 0 else f"{r['title']} is coming up", "why": why + when, "basis": "estimate"})
    bp = rem.get("brake")
    if bp and bp["status"] != "ok": out.append({"priority": 1 if bp["status"] == "overdue" else 2, "title": "Check brake pads", "why": bp["note"] + ". Worn pads lengthen stopping distance.", "basis": "user-entered"})
    if bh.get("status") in ("weak", "poor"): out.append({"priority": 1 if bh["status"] == "poor" else 2, "title": "Battery looks weak", "why": f"Resting voltage about {bh['resting_v']} V.", "basis": bh["basis"]})
    if bh.get("trend") == "falling": out.append({"priority": 2, "title": "Battery voltage is trending down", "why": bh["message"], "basis": bh["basis"]})
    for k, r in rem.items():
        if k.startswith("doc:") and r["status"] != "ok": out.append({"priority": 1 if r["status"] == "overdue" else 2, "title": f"{r['title']} {'expired' if r['status']=='overdue' else 'expires soon'}", "why": f"Expiry date {r['due_on']}.", "basis": "user-entered"})
    rows = [x for x in store.D["rides"][-10:] if x["dist_km"] > 3]
    if rows and sum(x["harsh_brake"] for x in rows) / sum(x["dist_km"] for x in rows) * 100 >= 8:
        out.append({"priority": 3, "title": "Frequent hard braking wears pads and tyres", "why": "Smoother braking extends pad and tyre life.", "basis": "gps-derived"})
    out.sort(key=lambda x: x["priority"])
    res = {"items": out, "ai": False, "pace": pc}
    if llm.enabled() and out:
        try: res["items"] = _llm_rewrite(out); res["ai"] = True
        except Exception as ex: print("LLM suggestion error:", ex)
    return res

_CACHE = {}
def _llm_rewrite(items):
    key = hashlib.md5(json.dumps(items, sort_keys=True).encode()).hexdigest()
    if key in _CACHE and time.time() - _CACHE[key][0] < 600: return _CACHE[key][1]
    out = llm.suggest(items, bike.view(), pace()); _CACHE[key] = (time.time(), out); return out

def brief():
    """Short maintenance summary for the voice assistant's context."""
    return {r["key"]: {"status": r["status"], "due_km": r["due_km"], "due_days": r["due_days"]} for r in reminders() if r["key"] in ("service", "oil", "chain", "brake")}
