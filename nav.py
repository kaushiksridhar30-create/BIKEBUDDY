"""Navigation: place search (Nominatim) and routing (OSRM) -> turn-by-turn steps with spoken text in all four languages.
Both services are free public OpenStreetMap-based APIs with fair-use limits: for real use run your own or set NOMINATIM_URL / OSRM_URL.
The public OSRM demo only has a car profile, so ETAs are for a car; roads open to bikes are usually the same."""
import os, requests, lang
from rides import hav

NOMINATIM = (os.environ.get("NOMINATIM_URL") or "https://nominatim.openstreetmap.org").rstrip("/")
OSRM = (os.environ.get("OSRM_URL") or "https://router.project-osrm.org").rstrip("/")
UA = {"User-Agent": os.environ.get("HTTP_UA") or "BikeBuddy/1.0 (student project)"}
TURN = {"left": "n_left", "right": "n_right", "slight left": "n_sleft", "slight right": "n_sright", "sharp left": "n_hleft",
        "sharp right": "n_hright", "straight": "n_straight", "uturn": "n_uturn"}

class NavError(Exception): pass

def geocode(q, lat=None, lon=None, limit=5):
    p = {"q": q, "format": "jsonv2", "limit": limit, "addressdetails": 0}
    if os.environ.get("NAV_COUNTRY", "in"): p["countrycodes"] = os.environ.get("NAV_COUNTRY", "in")
    if lat is not None and lon is not None: p["viewbox"] = f"{lon - 0.5},{lat + 0.5},{lon + 0.5},{lat - 0.5}"
    try:
        r = requests.get(NOMINATIM + "/search", params=p, headers=UA, timeout=6); r.raise_for_status()
    except Exception as ex: raise NavError("offline: " + str(ex)[:100])
    return [{"name": ", ".join(x.get("display_name", "").split(", ")[:3]), "lat": float(x["lat"]), "lon": float(x["lon"]), "type": x.get("type", "")} for x in r.json()]

def phrase(man, road, lg, first=False):
    T = lang.LANGS[lg]["T"]; typ, mod = man.get("type"), man.get("modifier")
    r = T["n_onto"].format(r=road) if road else ""
    if typ == "arrive": s = T["n_arrive"]
    elif typ == "depart": s = T["n_depart"].format(r=r)
    elif typ in ("roundabout", "rotary", "roundabout turn", "exit roundabout", "exit rotary") and man.get("exit"): s = T["n_round"].format(x=man["exit"], r=r)
    else: s = T[TURN.get(mod, "n_straight")].format(r=r)
    return s[:1].upper() + s[1:]

def fmt_dist(m, lg):
    T = lang.LANGS[lg]["T"]
    return T["u_m"].format(x=max(10, int(round(m / 10.0) * 10))) if m < 1000 else T["u_km"].format(x=round(m / 1000, 1))

def route(lat1, lon1, lat2, lon2, dest_name=""):
    url = f"{OSRM}/route/v1/driving/{lon1},{lat1};{lon2},{lat2}"
    try:
        r = requests.get(url, params={"steps": "true", "geometries": "geojson", "overview": "full"}, headers=UA, timeout=8); r.raise_for_status(); j = r.json()
    except Exception as ex: raise NavError("offline: " + str(ex)[:100])
    if j.get("code") != "Ok" or not j.get("routes"): raise NavError("no route")
    rt = j["routes"][0]; leg = rt["legs"][0]; geo = [[c[1], c[0]] for c in rt["geometry"]["coordinates"]]
    if len(geo) > 2500: k = len(geo) // 2500 + 1; geo = geo[::k] + [geo[-1]]
    steps = []
    for i, s in enumerate(leg["steps"]):
        m = s["maneuver"]; road = s.get("name") or ""
        steps.append({"i": i, "dist": round(s["distance"]), "dur": round(s["duration"]), "road": road, "type": m.get("type"), "modifier": m.get("modifier"),
                      "loc": [m["location"][1], m["location"][0]], "text": {lg: phrase(m, road, lg, i == 0) for lg in lang.LANGS}})
    mins = max(1, round(rt["duration"] / 60))
    return {"dest": {"name": dest_name, "lat": lat2, "lon": lon2}, "distance_m": round(rt["distance"]), "duration_s": round(rt["duration"]), "geometry": geo, "steps": steps,
            "summary": {lg: lang.LANGS[lg]["T"]["nav_sum"].format(q=dest_name or "destination", d=fmt_dist(rt["distance"], lg), m=mins) for lg in lang.LANGS},
            "fmt": {lg: {"in": lang.LANGS[lg]["T"]["n_in"], "m": lang.LANGS[lg]["T"]["u_m"], "km": lang.LANGS[lg]["T"]["u_km"], "re": lang.LANGS[lg]["T"]["nav_re"],
                         "stop": lang.LANGS[lg]["T"]["nav_stop"]} for lg in lang.LANGS}}
