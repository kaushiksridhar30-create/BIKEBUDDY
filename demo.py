"""Demo data generator. EVERYTHING here is labelled source='sim' and shown as SIMULATED in the app. It exists so a judge can see analytics
and the map without riding for weeks. Rides are fed through the SAME pipeline as real GPS (rides.feed), so harsh braking is genuinely detected from the speed trace."""
import math, random, time
import rides, store

def route_points(seed=1, minutes=12, lat=12.9716, lon=77.5946, t0=0.0):
    """1 Hz GPS-like trace with stops, turns, cruising and a few deliberate hard brakes / hard accelerations."""
    R = random.Random(seed); n = int(minutes * 60); v = 0.0; target = 35.0; h = R.uniform(0, 6.28); pts = []; ev = {}
    for _ in range(R.randint(0, 3)): ev[R.randint(60, n - 30)] = "brake"
    for _ in range(R.randint(0, 2)): ev[R.randint(40, n - 30)] = "accel"
    hold = 0
    for i in range(n):
        if i in ev: hold = 3; mode = ev[i]
        if hold:
            hold -= 1
            if mode == "brake" and v >= 25: v = max(0, v - 3.6 * 3.4)
            elif mode == "accel": v = min(60, v + 3.6 * 2.9)
        else:
            if i % R.randint(25, 60) == 0: target = R.choice([0, 20, 30, 38, 45, 52]) if R.random() < .8 else 0
            v += max(-3.6 * 1.2, min(3.6 * 1.3, target - v))
        h += R.gauss(0, .02) + (R.choice([-1.4, 1.4]) if R.random() < .01 else 0)
        d = v / 3.6; lat += d * math.cos(h) / 111320; lon += d * math.sin(h) / (111320 * math.cos(math.radians(lat)))
        pts.append({"t": t0 + i, "lat": lat, "lon": lon, "speed": max(0, v + R.gauss(0, .3)), "acc": 6})
    return pts

def seed(days=21, rides_n=14):
    """Fill the last few weeks with simulated rides and a simulated battery history. Idempotent: removes earlier simulated data first."""
    clear(); R = random.Random(7); now = time.time(); out = []
    for k in range(rides_n):
        day = R.randint(0, days - 1) if k else 0
        t0 = now - day * 86400 - R.randint(0, 6) * 3600 - 3600
        out.append(rides.import_ride(route_points(seed=k + 3, minutes=R.randint(8, 30), t0=t0), "sim"))
    h = store.D["batt_hist"]
    for i in range(24):
        t = now - (24 - i) * 86400 * 0.9
        h.append({"t": round(t), "v": round(12.75 - i * 0.012 + R.gauss(0, .015), 2), "run": False, "bike": store.D["active"], "sim": True})
    store.save(True); return {"rides": len(out)}

def clear():
    store.D["rides"] = [r for r in store.D["rides"] if r["source"] != "sim"]
    store.D["batt_hist"] = [h for h in store.D["batt_hist"] if not h.get("sim")]; store.save(True)
