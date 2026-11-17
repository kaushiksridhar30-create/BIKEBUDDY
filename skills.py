"""Voice-command router for rides, safety, analytics, nearby places and navigation (Kannada / Hindi / English / Hinglish keywords).
route() returns (spoken reply, optional UI action) or None to let the normal bike-Q&A handle it. Replies are filled from data, never invented.
Dangerous actions (SOS) are only REQUESTED here; the app shows a cancellable countdown before anything is sent."""
import re
import alerts, garage, lang, maint, nav, places, rides, store
from bike import T, has

SOS = ["sos", "emergency", "ambulance", "i crashed", "i have crashed", "accident ho gaya", "accident hua", "bachao", "एसओएस", "इमरजेंसी", "एम्बुलेंस", "आपातकाल", "बचाओ", "ಎಸ್ಒಎಸ್", "ತುರ್ತು", "ಆಂಬುಲೆನ್ಸ್"]
SHARE = ["share my location", "share location", "live location", "location share", "location bhejo", "लोकेशन शेयर", "लाइव लोकेशन", "ಲೊಕೇಶನ್ ಶೇರ್", "ಲೈವ್ ಲೊಕೇಶನ್"]
R_START = ["start ride", "start my ride", "ride start", "begin ride", "ride shuru", "ride chalu", "राइड शुरू", "राइड चालू", "ರೈಡ್ ಶುರು", "ರೈಡ್ ಪ್ರಾರಂಭ"]
R_STOP = ["stop ride", "end ride", "end my ride", "finish ride", "ride stop", "ride band", "ride khatam", "राइड बंद", "राइड खत्म", "राइड ख़त्म", "ರೈಡ್ ನಿಲ್ಲಿಸು", "ರೈಡ್ ಮುಗಿ"]
R_STAT = ["last ride", "ride summary", "today's ride", "ride today", "distance today", "aaj kitna", "pichli ride", "आज कितना", "पिछली राइड", "ಇಂದು ಎಷ್ಟು", "ಕೊನೆಯ ರೈಡ್"]
ECO = [" eco ", "eco score", "riding score", "इको", "ಇಕೋ"]
BEHAVE = ["harsh", "sudden brak", "hard brak", "riding behav", "how am i riding", "kaisa chala raha", "अचानक ब्रेक", "ಹಠಾತ್"]
WEEK = ["weekly", "this week", "week report", "monthly", "this month", "is hafte", "is mahine", "हफ्ते", "महीने", "ವಾರ", "ತಿಂಗಳ"]
SPEND = ["spent", "expense", "kharcha", "खर्च", "ಖರ್ಚು", "repair cost"]
SVCH = ["last service", "service history", "pichli service", "पिछली सर्विस"]
ALERTS = ["any alert", "any warning", "alerts", "warnings", "any problem", "koi problem", "koi dikkat", " fault", "समस्या", "दिक्कत", "चेतावनी", "ಸಮಸ್ಯೆ"]
NAV_STOP = ["stop navigation", "cancel navigation", "navigation band", "नेविगेशन बंद", "ನ್ಯಾವಿಗೇಶನ್ ನಿಲ್ಲಿಸು"]
NEAR = ["nearest", "nearby", "near me", "paas", "najdik", "nazdeek", "aas paas", "पास", "नज़दीक", "नजदीक", "ಹತ್ತಿರ"]
KIND = {"fuel": ["petrol pump", "petrol bunk", "fuel station", "gas station", "petrol station", "पेट्रोल पंप", "ಪೆಟ್ರೋಲ್ ಬಂಕ್", "ಪೆಟ್ರೋಲ್ ಪಂಪ್"],
        "hospital": ["hospital", "aspatal", "अस्पताल", "ಆಸ್ಪತ್ರೆ", "clinic"],
        "service": ["service centre", "service center", "garage", "mechanic", "workshop", "सर्विस सेंटर", "ಸರ್ವಿಸ್ ಸೆಂಟರ್", "ಗ್ಯಾರೇಜ್"]}
NAV_RX = [r"(?:navigate|navigation|take me|directions?|route|drive me|drive)\s+(?:to|for)\s+(.+)",
          r"(.+?)\s+(?:ko\s+)?(?:le chalo|chalo|jana hai|jaana hai|navigate kar|ka rasta|ka route)\b",
          r"(.+?)\s*(?:ले चलो|जाना है|का रास्ता)", r"(.+?)\s*(?:ಗೆ|ಕ್ಕೆ)\s*(?:ಹೋಗ|ದಾರಿ|ಕರೆದುಕೊಂಡು)"]
FILLER = re.compile(r"^(?:please|mujhe|muje|buddy|the|my)\s+|\s+(?:please|karo|kijiye)$")

def _km(x): return f"{x:.1f}".rstrip("0").rstrip(".")
def _mins(s): return max(1, round(s / 60))

def route(t, raw, ctx):
    if has(t, SOS) and not has(t, ["contact", "number"]): return T("sos_ack"), {"type": "sos"}
    if has(t, SHARE): return T("share_ack"), {"type": "share"}
    if has(t, NAV_STOP): return T("nav_stop"), {"type": "nav_stop"}
    if has(t, R_STOP):
        res = rides.stop()
        if not res: return T("ride_off"), {"type": "ride_stop"}
        return T("ride_stop", km=_km(res["dist_km"]), min=_mins(res["duration_s"]), avg=round(res["avg_kmh"])), {"type": "ride_stop"}
    if has(t, R_START):
        _, new = rides.start("gps"); return T("ride_start" if new else "ride_on"), {"type": "ride_start"}
    if has(t, R_STAT): return _ride_stats(), {"type": "open", "tab": "ride"}
    if has(t, ECO):
        o = rides.eco_overview()
        return (T("eco", s=o["score"], c=o["count"]) if o["score"] is not None else T("eco_none")), {"type": "open", "tab": "ride"}
    if has(t, BEHAVE):
        a = rides.report(7)
        if not a["rides"]: return T("week_none"), None
        if a["harsh_brake"] + a["harsh_accel"] == 0: return T("behave_good"), None
        return T("behave", hb=a["harsh_brake"], ha=a["harsh_accel"], km=_km(a["km"])), None
    if has(t, WEEK):
        d = 30 if has(t, ["monthly", "this month", "is mahine", "महीने", "ತಿಂಗಳ"]) else 7; a = rides.report(d)
        if not a["rides"]: return T("week_none"), None
        return T("week", d=d, c=a["rides"], km=_km(a["km"]), hb=a["harsh_brake"], ha=a["harsh_accel"], s=a["eco"] if a["eco"] is not None else "-"), {"type": "open", "tab": "ride"}
    if has(t, SPEND):
        e = garage.expenses_summary()
        return (T("spend", amt=round(e["last_30d"]), tot=round(e["total"])) if e["count"] else T("spend_none")), {"type": "open", "tab": "garage"}
    if has(t, SVCH):
        s = garage.last_service()
        return (T("svch", date=s["date"], odo=int(s.get("odo") or 0)) if s else T("svch_none")), {"type": "open", "tab": "service"}
    if has(t, ALERTS):
        a = alerts.active_alerts()
        return (T("al_none") if not a else T("h_warn", k=len(a)) + " " + " ".join(x["text"] for x in a[:3])), {"type": "open", "tab": "service"}
    for kind, words in KIND.items():
        if has(t, words) or (has(t, NEAR) and (kind == "fuel" and has(t, ["petrol", "fuel", "पेट्रोल", "ಪೆಟ್ರೋಲ್"]))):
            return _nearby(kind, ctx), {"type": "nearby", "kind": kind}
    for rx in NAV_RX:
        m = re.search(rx, t)
        if m:
            q = FILLER.sub("", m.group(1).strip()).strip()
            if len(q) >= 2: return T("nav_to", q=q), {"type": "navigate", "query": q}
    return None

def _ride_stats():
    lv = rides.live()
    if lv: return T("ride_live", km=_km(lv["dist_km"]), s=lv["speed"])
    last = rides.last_summary()
    if not last: return T("ride_none")
    import datetime
    out = []
    today = [x for x in store.D["rides"] if datetime.date.fromtimestamp(x["start"]) == datetime.date.today()]
    if today: out.append(T("ride_today", km=_km(sum(x["dist_km"] for x in today)), c=len(today)))
    out.append(T("ride_last", km=_km(last["dist_km"]), min=_mins(last["duration_s"]), avg=round(last["avg_kmh"]), mx=last["max_kmh"]))
    if last["source"] == "sim": out.append(T("ride_sim"))
    return " ".join(out)

def _nearby(kind, ctx):
    if ctx.get("lat") is None or ctx.get("lon") is None: return T("near_loc")
    kd = T("k_" + kind)
    try: r = places.nearby(kind, ctx["lat"], ctx["lon"], limit=3, timeout=5)
    except places.PlacesError: return T("near_off")
    if not r["items"]: return T("near_none", kind=kd)
    p = r["items"][0]; d = nav.fmt_dist(p["dist_m"], lang.SET["lang"])
    s = T("near", kind=kd, name=p["name"] or kd, d=d)
    return s + (" " + T("near_er") if kind == "hospital" else "")
