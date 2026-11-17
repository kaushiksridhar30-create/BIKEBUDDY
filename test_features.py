"""Offline tests for the newer features (no internet, no Gnani key). Run: python -m pytest -q test_features.py   (or python test_features.py)"""
import os, re, string, tempfile, time
os.environ["BB_DATA"] = tempfile.mkdtemp(); os.environ.pop("GNANI_API_KEY", None); os.environ.pop("LLM_KEY", None)
for k in ("TWILIO_SID", "ALERT_WEBHOOK_URL", "TELEMETRY_TOKEN"): os.environ.pop(k, None)
import pytest
import alerts, bike, demo, garage, lang, maint, nav, notify, places, rides, safety, skills, store
import app as appmod

@pytest.fixture(autouse=True)
def fresh():
    store.D.clear(); store.D.update(store.defaults()); bike.LOG = store.D["notes"]
    lang.SET.update({"name": "Buddy", "lang": "english", "speed_limit": 80, "speak_alerts": True, "rider": "Asha", "auto_odo": True})
    bike.MODE[0] = "sim"; bike.SRC.clear(); bike.STATE.clear(); bike.init()
    alerts.ACTIVE.clear(); alerts.ANN.clear(); alerts.SEQ[0] = 0; alerts.CLEAR_S[0] = 0
    safety.INC.clear(); safety.SYNC[0] = True; places._MEM.clear(); yield

class Resp:
    def __init__(s, j, code=200): s._j, s.status_code = j, code
    def json(s): return s._j
    def raise_for_status(s):
        if s.status_code >= 400: raise RuntimeError(f"HTTP {s.status_code}")

# ---------- language packs ----------
def test_language_packs_have_same_keys_and_placeholders():
    fields = lambda s: sorted(f for _, f, _, _ in string.Formatter().parse(s) if f)
    base = lang.LANGS["english"]["T"]
    for lg, pack in lang.LANGS.items():
        T = pack["T"]; assert set(T) == set(base), (lg, set(base) ^ set(T))
        for k in base:
            if k in lang_more_keys(): assert fields(T[k]) == fields(base[k]), (lg, k)

def lang_more_keys():
    import lang_more; return set(lang_more.ROWS)

# ---------- provenance and connection ----------
def test_demo_mode_is_labelled_simulated():
    assert bike.conn()["status"] == "simulated" and bike.SRC["battery"] == "sim"
    assert "demo values" in bike.health_summary()

def test_live_mode_clears_demo_values_and_never_shows_fakes():
    r = bike.ingest({"battery": 12.4, "bogus": 1, "engine_temp": 900})
    assert r["accepted"] == {"battery": 12.4} and "bogus" in r["rejected"] and "engine_temp" in r["rejected"]
    assert bike.MODE[0] == "live" and bike.view()["fuel"] is None and bike.view()["battery"] == 12.4
    assert "fuel level" in bike.answer("how much petrol")
    assert bike.conn()["status"] == "connected" and bike.SRC["battery"] == "sensor"
    with pytest.raises(PermissionError): bike.set_demo({"battery": 13})

def test_stale_and_disconnected():
    bike.ingest({"battery": 12.6}); bike.SEEN["battery"] -= 30; assert bike.conn()["status"] == "stale" and bike.view()["battery"] == 12.6
    bike.SEEN["battery"] -= 60; assert bike.conn()["status"] == "disconnected" and bike.view()["battery"] is None
    assert "not sending" in bike.health_summary()

# ---------- alerts ----------
def test_no_alerts_on_defaults():
    assert bike.warnings() == [] and alerts.active_alerts() == []

def test_tyre_low_alert_announced_once_logged_and_cleared():
    bike.set_demo({"tyre_front": 19}); a = alerts.active_alerts()
    assert a[0]["kind"] == "tyre" and "Front tyre pressure is low" in a[0]["text"]
    alerts.active_alerts(); assert len(alerts.announcements(0)) == 1                   # not repeated
    bike.set_demo({"tyre_front": 30}); assert alerts.active_alerts() == []
    assert alerts.fault_log()[0]["t1"] is not None
    bike.set_demo({"tyre_front": 19}); alerts.active_alerts(); assert len(alerts.announcements(0)) == 2   # re-armed after clearing

def test_battery_rules_depend_on_engine_state():
    bike.ingest({"battery": 11.8}); assert alerts.active_alerts()[0]["kind"] == "batt"
    bike.ingest({"battery": 12.2, "ignition": False}); assert alerts.active_alerts()[0]["kind"] == "battw"
    bike.ingest({"battery": 12.9, "ignition": True, "rpm": 3000}); assert alerts.active_alerts()[0]["kind"] == "chlow"
    bike.ingest({"battery": 15.2}); assert alerts.active_alerts()[0]["kind"] == "chhigh"
    bike.ingest({"battery": 14.1}); assert alerts.active_alerts() == []

def test_sensors_that_are_missing_raise_no_alert():
    bike.set_mode("live"); bike.ingest({"battery": 12.7}); assert alerts.active_alerts() == []

def test_rapid_tyre_pressure_drop_is_flagged_as_puncture():
    bike.set_demo({"tyre_rear": 32}); bike.set_demo({"tyre_rear": 27}); a = alerts.active_alerts()
    assert a[0]["kind"] == "drop" and a[0]["level"] == "critical" and "puncture" in a[0]["text"].lower()

def test_alert_text_in_all_languages():
    bike.set_demo({"fuel": 5})
    for lg in lang.LANGS:
        lang.SET["lang"] = lg; assert alerts.active_alerts()[0]["text"]
    assert "ಪೆಟ್ರೋಲ್" in alerts.active_alerts()[0]["text"]

def test_service_oil_chain_brake_and_doc_alerts():
    bike.set_demo({"odometer": 9000, "last_oil": 5000, "brake_pad": 10, "puc": "2020-01-01"})
    kinds = {a["kind"] for a in alerts.active_alerts()}
    assert {"svc0", "oil", "chain", "brake", "docx"} <= kinds

def test_link_lost_alert_and_reconnect_announcement():
    bike.ingest({"battery": 12.6}); bike.SEEN["battery"] -= 100
    assert any(a["kind"] == "link" for a in alerts.active_alerts())
    bike.ingest({"battery": 12.6}); alerts.active_alerts()
    assert any(x["kind"] == "linkok" for x in alerts.announcements(0))

# ---------- rides ----------
def straight(n=60, kmh=36, t0=1000.0, lat=12.97, lon=77.59):
    step = kmh / 3.6 / 111320; return [{"t": t0 + i, "lat": lat + i * step, "lon": lon, "speed": kmh, "acc": 5} for i in range(n)]

def test_distance_speed_duration():
    rides.points(straight(), "gps"); lv = rides.live()
    assert 0.55 < lv["dist_km"] < 0.62 and lv["max_kmh"] == 36
    res = rides.stop(); assert res["saved"] and res["duration_s"] == 59 and 35 < res["avg_kmh"] < 38

def test_bad_fixes_and_gps_jumps_are_ignored():
    pts = straight(10); pts[4]["lat"] += 1.0; pts[6]["acc"] = 200; pts[7]["lat"] = 999
    rides.points(pts, "gps"); assert rides.live()["dist_km"] < 0.15

def test_harsh_braking_and_acceleration_detected():
    pts = straight(20, 50)
    for i in range(10, 13): pts[i]["speed"] = 50 - (i - 9) * 13          # 50 -> 11 km/h in 3 s = about -3.6 m/s2
    for i in range(14, 17): pts[i]["speed"] = 11 + (i - 13) * 12         # then +3.3 m/s2
    r = rides.new_ride("gps", None); [rides.feed(r, p) for p in pts]; res = rides.finish(r)
    assert res["harsh_brake"] >= 1 and res["harsh_accel"] >= 1

def test_smooth_ride_scores_higher_than_aggressive_ride():
    smooth = rides.import_ride(straight(300, 40), "sim")
    pts = straight(300, 40)
    for i in range(0, 300, 20):
        pts[i]["speed"] = 60; pts[i + 1]["speed"] = 10
    rough = rides.import_ride(pts, "sim"); assert smooth["eco"] > rough["eco"] and rough["eco"] < 100

def test_odometer_auto_updates_only_for_real_gps_rides():
    before = bike.STATE["odometer"]; rides.points(straight(), "sim"); rides.stop(); assert bike.STATE["odometer"] == before
    rides.points(straight(), "gps"); rides.stop(); assert bike.STATE["odometer"] > before and bike.SRC["odometer"] == "estimate"
    assert garage.active()["profile"]["odometer"] == bike.STATE["odometer"]

def test_tiny_ride_is_discarded_and_offline_batches_flush():
    rides.points(straight(3), "gps"); assert rides.stop()["saved"] is False and store.D["rides"] == []
    pts = straight(40); rides.points(pts[:20], "gps"); rides.points(pts[20:], "gps"); assert rides.live()["n"] == 40

def test_reports_and_trend_use_stored_rides():
    demo.seed(); rep = rides.report(30)
    assert rep["rides"] >= 10 and rep["sim_rides"] == rep["rides"] and len(rep["series"]) == 30 and rep["insights"]
    assert rides.speed_trend()["points"] and rides.eco_overview()["score"] is not None
    demo.clear(); assert rides.report(30)["rides"] == 0

def test_demo_rides_detect_real_events_from_the_trace():
    assert sum(r["harsh_brake"] + r["harsh_accel"] for r in (rides.import_ride(demo.route_points(seed=s, minutes=10, t0=5000), "sim") for s in range(1, 12))) > 0

# ---------- garage ----------
def test_garage_validation_and_service_resets_counters():
    with pytest.raises(ValueError): garage.add("services", {"date": "not-a-date", "type": "service"})
    with pytest.raises(ValueError): garage.add("expenses", {"date": "2026-01-01", "cat": "fuel", "amount": "abc"})
    garage.add("services", {"date": "2026-11-01", "odo": 9000, "type": "service", "cost": 1500, "shop": "<b>X</b>"})
    p = garage.active()["profile"]; assert p["odometer"] == 9000 and p["next_service"] == 12000 and p["last_oil"] == 9000
    assert "<" not in garage.active()["services"][0]["shop"]
    bike.load_profile(); assert not {a["kind"] for a in alerts.active_alerts()} & {"svc", "svc0", "svct", "oil", "oils"}   # (chain lube is legitimately due)

def test_expenses_summary_and_docs():
    garage.add("expenses", {"date": garage.iso(garage.today()), "cat": "fuel", "amount": 500})
    garage.add("mods", {"name": "Crash guard", "cost": 2000}); garage.add("docs", {"type": "RC", "expiry": "2020-01-01"})
    s = garage.expenses_summary(); assert s["total"] == 2500 and s["by_cat"]["accessory"] == 2000
    assert any(d["type"] == "RC" and d["days"] < 0 for d in garage.docs_status())

def test_multi_bike_switch_keeps_separate_profiles():
    a = store.D["active"]; b = garage.create({"name": "Scooter", "profile": {"odometer": 100}})
    bike.switch(b["id"]); assert bike.STATE["odometer"] == 100 and bike.STATE["bike_name"] == "Scooter"
    bike.switch(a); assert bike.STATE["odometer"] == 8420
    garage.delete(b["id"]); assert list(store.D["bikes"]) == [a]
    with pytest.raises(ValueError): garage.delete(a)             # the last bike cannot be deleted

# ---------- maintenance ----------
def test_reminders_distance_and_time_and_projection():
    bike.set_demo({"odometer": 8800, "last_service_date": "2020-01-01"})
    rem = {r["key"]: r for r in maint.reminders()}
    assert rem["service"]["due_km"] == 100 and rem["service"]["basis"] == "distance + time"
    assert rem["service"]["due_days"] < 0 and rem["service"]["status"] == "overdue"      # time-based interval passed even though distance is still ok
    rides.import_ride(straight(600, 40, t0=time.time() - 3600), "gps"); assert maint.pace()["km_per_day"] > 0

def test_suggestions_are_grounded_rules():
    bike.set_demo({"odometer": 9100}); titles = " ".join(s["title"] for s in maint.suggestions()["items"]); assert "Service is overdue" in titles

def test_battery_health_needs_real_history():
    assert maint.battery_health()["status"] == "no_data"
    now = time.time()
    for i in range(10): store.D["batt_hist"].append({"t": round(now - (10 - i) * 86400), "v": 12.8 - i * 0.05, "run": False, "bike": store.D["active"]})
    h = maint.battery_health(); assert h["basis"] == "sensor" and h["trend"] == "falling" and h["est_days_to_12v"]
    store.D["batt_hist"] = [dict(x, sim=True) for x in store.D["batt_hist"]]; assert maint.battery_health()["basis"] == "simulated"

# ---------- safety ----------
def test_contacts_validation_and_limit():
    with pytest.raises(ValueError): safety.add_contact("", "123456")
    with pytest.raises(ValueError): safety.add_contact("A", "12")
    for i in range(5): safety.add_contact(f"C{i}", f"98765432{i}0")
    with pytest.raises(ValueError): safety.add_contact("X", "9876543210")

def test_share_link_is_minimal_and_revocable():
    s = safety.start_share(); safety.update_location(12.9, 77.6, 30)
    v = safety.public_view(s["token"]); assert v["lat"] == 12.9 and set(v) <= {"active", "rider", "status", "lat", "lon", "speed", "updated", "trail", "emergency"}
    safety.stop_share(s["token"]); assert safety.public_view(s["token"]) == {"active": False} and safety.public_view("nope") == {"active": False}

def test_sos_escalates_reports_simulated_delivery_and_is_idempotent(monkeypatch):
    safety.add_contact("Mom", "9876543210"); monkeypatch.setattr(places, "nearby", lambda *a, **k: {"items": [{"name": "City Hospital", "dist_m": 1200}]})
    inc = safety.sos({"lat": 12.9, "lon": 77.6, "source": "sos_button"}, "http://x/"); assert inc.status == "escalated" and inc.share["url"].startswith("http://x/track/")
    assert inc.notified[0]["status"] == "simulated" and "City Hospital" in inc.message and "maps.google.com/?q=12.9,77.6" in inc.message
    n = len(inc.timeline); safety.escalate(inc, "http://x/"); assert len(inc.timeline) == n
    assert safety.public_view(inc.share["token"])["status"] == "emergency"

def test_no_invented_location_for_a_real_emergency():
    inc = safety.sos({"source": "sos_button"}, "http://x/"); assert inc.lat is None and inc.loc == "none" and "no GPS fix" in inc.message
    assert inc.hospitals == []

def test_real_sms_is_attempted_only_when_configured(monkeypatch):
    sent = []
    monkeypatch.setenv("ALERT_WEBHOOK_URL", "http://hook"); monkeypatch.setattr(notify.requests, "post", lambda u, **k: sent.append((u, k["json"])) or Resp({}))
    assert notify.send({"name": "Mom", "phone": "9876543210"}, "hi")[0]["status"] == "sent" and sent[0][1]["to"] == "+919876543210"
    monkeypatch.setattr(notify.requests, "post", lambda *a, **k: Resp({}, 500)); assert notify.send({"name": "M", "phone": "1"}, "x")[0]["status"] == "failed"

def test_cancel_after_escalation_sends_followup(monkeypatch):
    safety.add_contact("Mom", "9876543210"); msgs = []
    monkeypatch.setattr(notify, "send", lambda c, m: msgs.append(m) or [{"contact": "Mom", "channel": "sms", "status": "sent", "detail": ""}])
    inc = safety.sos({"lat": 1, "lon": 1, "source": "sos_button"}, "http://x/"); safety.cancel(inc)
    assert inc.status == "false_alarm" and "False alarm" in msgs[-1] and safety.public_view(inc.share["token"]) == {"active": False}

# ---------- places and navigation ----------
OSM = {"elements": [{"type": "node", "id": 1, "lat": 12.98, "lon": 77.6, "tags": {"name": "Far Pump"}}, {"type": "way", "id": 2, "center": {"lat": 12.971, "lon": 77.595}, "tags": {"name": "Near Pump", "phone": "+91 80 1"}}]}

def test_places_sorted_cached_and_offline_fallback(monkeypatch):
    monkeypatch.setattr(places.requests, "post", lambda *a, **k: Resp(OSM)); r = places.nearby("fuel", 12.9716, 77.5946)
    assert [x["name"] for x in r["items"]] == ["Near Pump", "Far Pump"] and not r["stale"]
    def boom(*a, **k): raise OSError("no internet")
    monkeypatch.setattr(places.requests, "post", boom); places._MEM.clear(); r = places.nearby("fuel", 12.9716, 77.5946)
    assert r["stale"] and r["items"][0]["name"] == "Near Pump"
    with pytest.raises(places.PlacesError): places.nearby("hospital", 1.0, 1.0)

OSRM = {"code": "Ok", "routes": [{"distance": 1500, "duration": 300, "geometry": {"coordinates": [[77.5, 12.9], [77.6, 13.0]]}, "legs": [{"steps": [
    {"distance": 700, "duration": 100, "name": "MG Road", "maneuver": {"type": "depart", "location": [77.5, 12.9]}},
    {"distance": 800, "duration": 200, "name": "Church Street", "maneuver": {"type": "turn", "modifier": "left", "location": [77.55, 12.95]}},
    {"distance": 0, "duration": 0, "name": "", "maneuver": {"type": "arrive", "location": [77.6, 13.0]}}]}]}]}

def test_route_steps_are_spoken_in_every_language(monkeypatch):
    monkeypatch.setattr(nav.requests, "get", lambda *a, **k: Resp(OSRM)); r = nav.route(12.9, 77.5, 13.0, 77.6, "Cubbon Park")
    assert r["steps"][1]["text"]["english"] == "Turn left onto Church Street" and "ಎಡಕ್ಕೆ" in r["steps"][1]["text"]["kannada"] and "बाएँ" in r["steps"][1]["text"]["hindi"]
    assert r["steps"][2]["text"]["english"].startswith("You have arrived") and "Cubbon Park" in r["summary"]["english"] and r["geometry"][0] == [12.9, 77.5]

def test_navigation_errors_are_reported_not_hidden(monkeypatch):
    def boom(*a, **k): raise OSError("down")
    monkeypatch.setattr(nav.requests, "get", boom)
    with pytest.raises(nav.NavError): nav.route(1, 1, 2, 2)

# ---------- voice commands ----------
def ask(t, **ctx): return bike.answer_ex(t, ctx)

def test_voice_health_summary_example_from_the_brief():
    r = ask("Buddy, is my bike healthy?")["reply"]; assert "healthy" in r and "12.6" in r and "demo" in r

def test_voice_sos_is_only_requested_never_sent_directly():
    r = ask("SOS"); assert r["action"] == {"type": "sos"} and safety.INC == {}
    assert ask("what is my emergency contact")["action"] != {"type": "sos"}

def test_voice_ride_start_stop_and_stats():
    assert ask("start ride")["action"]["type"] == "ride_start" and rides.active()
    rides.points(straight(), "gps"); assert "Current ride" in ask("last ride summary")["reply"]
    r = ask("stop ride"); assert "Ride ended" in r["reply"] and r["action"]["type"] == "ride_stop"
    assert "Your last ride" in ask("last ride")["reply"] and "No ride is running" in ask("stop ride")["reply"]

def test_voice_in_hinglish_hindi_kannada():
    lang.SET["lang"] = "hinglish"; assert "ride shuru" in ask("ride shuru karo")["reply"].lower(); rides.stop(discard=True)
    lang.SET["lang"] = "hindi"; assert "एसओएस" in ask("एसओएस")["reply"]
    lang.SET["lang"] = "kannada"; assert ask("ಆಸ್ಪತ್ರೆ ಎಲ್ಲಿದೆ")["action"]["kind"] == "hospital"

def test_voice_navigation_extraction():
    assert ask("navigate to Indiranagar metro")["action"] == {"type": "navigate", "query": "indiranagar metro"}
    assert ask("Lalbagh ko le chalo")["action"]["query"] == "lalbagh"
    assert ask("stop navigation")["action"]["type"] == "nav_stop"

def test_voice_nearby_needs_location_then_uses_places(monkeypatch):
    assert "location" in ask("nearest petrol pump")["reply"]
    monkeypatch.setattr(places, "nearby", lambda *a, **k: {"items": [{"name": "HP Pump", "dist_m": 850}], "stale": False})
    r = ask("nearest petrol pump", lat=12.9, lon=77.6)["reply"]; assert "HP Pump" in r and "850 metres" in r
    r = ask("hospital near me", lat=12.9, lon=77.6)["reply"]; assert "108" in r
    def off(*a, **k): raise places.PlacesError("x")
    monkeypatch.setattr(places, "nearby", off); assert "without internet" in ask("service centre", lat=1, lon=1)["reply"]

def test_voice_analytics_expenses_alerts_service_history():
    demo.seed(); garage.add("expenses", {"date": garage.iso(garage.today()), "cat": "repair", "amount": 700})
    assert "eco riding score" in ask("what is my eco score")["reply"] and "rides" in ask("weekly report")["reply"]
    assert "700 rupees" in ask("how much have I spent")["reply"] and "No service records" in ask("service history")["reply"]
    assert "No active alerts" in ask("any alerts")["reply"]; bike.set_demo({"fuel": 5}); assert "Fuel is low" in ask("any alerts")["reply"]

def test_existing_voice_questions_still_work():
    assert "PSI" in ask("tyre pressure")["reply"]
    assert ask("what is the second")["reply"] == bike.T("none")          # 'second' must not trigger the eco-score intent
    assert ask("is my default setting ok")["action"] is None            # 'default' must not trigger the fault/alerts intent

# ---------- HTTP API ----------
@pytest.fixture
def client(): return appmod.app.test_client()

def test_status_and_missing_voice_key_does_not_break_replies(client):
    s = client.get("/api/status").json; assert s["conn"]["status"] == "simulated" and s["src"]["battery"]["src"] == "sim"
    r = client.post("/api/asktext", json={"text": "battery"}).json; assert r["reply"] and r["audio"] == "" and r["voice_error"]

def test_telemetry_endpoint_and_token(client, monkeypatch):
    assert client.post("/api/telemetry", json={"battery": 12.5}).json["accepted"] == {"battery": 12.5}
    monkeypatch.setenv("TELEMETRY_TOKEN", "s3"); assert client.post("/api/telemetry", json={"battery": 12.5}).status_code == 403
    assert client.post("/api/telemetry", json={"battery": 12.5}, headers={"X-Token": "s3"}).status_code == 200
    assert client.post("/api/bike/set", json={"battery": 9}).status_code == 403

def test_ride_api_roundtrip_and_analytics(client):
    pts = [dict(p, t=p["t"] + 1.7e9) for p in straight()]
    assert client.post("/api/ride/point", json={"points": pts}).json["live"]["dist_km"] > 0.5
    assert client.post("/api/ride/stop", json={}).json["saved"] is True
    rid = client.get("/api/rides").json[0]["id"]; assert len(client.get(f"/api/ride/{rid}").json["route"]) > 2
    assert client.get("/api/analytics?days=90").json["report"]["days"] == 90
    assert client.delete(f"/api/ride/{rid}").status_code == 200 and client.get(f"/api/ride/{rid}").status_code == 404

def test_sos_endpoint_and_public_tracking_page(client):
    client.post("/api/contacts", json={"name": "Mom", "phone": "9876543210"})
    r = client.post("/api/sos", json={"lat": 12.9, "lon": 77.6}).json; assert r["status"] == "escalated"
    inc = client.get("/api/incidents").json[0]; tok = inc["share"]["token"]
    pv = client.get(f"/api/track/{tok}").json; assert pv["status"] == "emergency" and pv["lat"] == 12.9 and "Mom" not in str(pv)
    assert client.get(f"/track/{tok}").status_code == 200 and client.get("/api/track/bad").json == {"active": False}

def test_crash_flow_countdown_escalation(client):
    o = client.post("/api/event", json={"speed_kmh": 40, "peak_g": 4.5, "source": "phone_sim"}).json; assert o["mode"] == "crash" and o["countdown_s"] == 30
    assert client.post("/api/escalate", json={"id": o["id"]}).json["status"] == "escalated"
    o2 = client.post("/api/event", json={"speed_kmh": 40, "peak_g": 4.5, "source": "phone_sim"}).json
    a = client.post("/api/answer", data={"id": o2["id"], "text": "haan main theek hoon"}).json; assert a["status"] == "ok"
    assert client.post("/api/event", json={"speed_kmh": 0, "peak_g": 1.0}).json["mode"] == "none"

def test_garage_api(client):
    assert client.post("/api/garage/expenses", json={"date": "2026-11-01", "cat": "fuel", "amount": "x"}).status_code == 400
    assert client.post("/api/garage/nope", json={}).status_code == 404
    new = client.post("/api/garage/bike", json={"name": "Scooter"}).json["id"]; client.post("/api/garage/switch", json={"id": new})
    assert client.get("/api/garage/active").json["name"] == "Scooter" and client.get("/api/status").json["bike"]["name"] == "Scooter"

def test_settings_persist_and_validate(client):
    s = client.post("/api/settings", json={"lang": "kannada", "speed_limit": "60", "rider": "<b>Asha</b>", "speak_alerts": False}).json
    assert s["lang"] == "kannada" and s["speed_limit"] == 60 and "<" not in s["rider"] and s["speak_alerts"] is False and store.D["settings"]["lang"] == "kannada"

if __name__ == "__main__": raise SystemExit(pytest.main(["-q", __file__]))
