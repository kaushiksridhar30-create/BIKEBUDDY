"""Nearby petrol pumps, hospitals and motorcycle service centres from OpenStreetMap (Overpass API). Needs internet.
The last good answer per area is cached on disk, so emergency info can still be shown (marked 'stale') with no signal."""
import os, time, requests, store
from rides import hav

OVERPASS = [u for u in (os.environ.get("OVERPASS_URL"), "https://overpass-api.de/api/interpreter", "https://overpass.kumi.systems/api/interpreter") if u]
UA = {"User-Agent": os.environ.get("HTTP_UA") or "BikeBuddy/1.0 (student project)"}
FILTERS = {"fuel": ['["amenity"="fuel"]'], "hospital": ['["amenity"="hospital"]', '["healthcare"="hospital"]'],
           "service": ['["shop"="motorcycle"]', '["shop"="motorcycle_repair"]', '["craft"="motorcycle_mechanic"]']}
RADIUS = {"fuel": 5000, "service": 10000, "hospital": 15000}
EMERGENCY = {"Emergency (all services)": "112", "Ambulance": "108", "Police": "100", "Fire": "101"}   # India. Edit for other countries.
TTL = 900; _MEM = {}

class PlacesError(Exception): pass

def _parse(els, lat, lon):
    rows = {}
    for e in els:
        t = e.get("tags") or {}; la = e.get("lat") or (e.get("center") or {}).get("lat"); lo = e.get("lon") or (e.get("center") or {}).get("lon")
        if la is None or lo is None: continue
        addr = t.get("addr:full") or ", ".join(x for x in (t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:suburb") or t.get("addr:city")) if x)
        rows[(e.get("type"), e.get("id"))] = {"name": t.get("name") or t.get("name:en") or "", "lat": la, "lon": lo, "dist_m": round(hav(lat, lon, la, lo)),
                                              "phone": t.get("phone") or t.get("contact:phone") or "", "hours": t.get("opening_hours") or "", "addr": addr}
    return sorted(rows.values(), key=lambda r: r["dist_m"])

def nearby(kind, lat, lon, radius=None, limit=8, timeout=6):
    """-> {'kind','items':[{name,lat,lon,dist_m,phone,hours,addr}],'stale':bool,'age_s':int}. Raises PlacesError if offline and nothing cached."""
    if kind not in FILTERS: raise ValueError("unknown kind")
    lat, lon = float(lat), float(lon); radius = radius or RADIUS[kind]; key = f"{kind}:{round(lat, 2)}:{round(lon, 2)}"
    hit = _MEM.get(key)
    if hit and time.time() - hit[0] < TTL: return {"kind": kind, "items": hit[1][:limit], "stale": False, "age_s": round(time.time() - hit[0])}
    q = "[out:json][timeout:8];(" + "".join(f"nwr{f}(around:{radius},{lat},{lon});" for f in FILTERS[kind]) + ");out center 40;"
    err = None
    for url in OVERPASS:
        try:
            r = requests.post(url, data={"data": q}, headers=UA, timeout=timeout); r.raise_for_status()
            rows = _parse(r.json().get("elements", []), lat, lon); _MEM[key] = (time.time(), rows)
            P = store.D["places"]; P[key] = {"t": round(time.time()), "items": rows[:20]}
            for old in sorted(P, key=lambda k: P[k]["t"])[:-30]: P.pop(old, None)
            store.save(); return {"kind": kind, "items": rows[:limit], "stale": False, "age_s": 0}
        except Exception as ex: err = ex
    c = store.D["places"].get(key)
    if c: return {"kind": kind, "items": c["items"][:limit], "stale": True, "age_s": round(time.time() - c["t"])}
    raise PlacesError(str(err)[:120])
