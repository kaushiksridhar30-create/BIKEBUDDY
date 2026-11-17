"""Alert delivery to emergency contacts. A channel is used ONLY if you configured it in .env; otherwise the result is
reported as 'simulated' and the UI says so. We never claim a message was sent when it was not.
  Twilio SMS : TWILIO_SID, TWILIO_TOKEN, TWILIO_FROM       Webhook (Zapier / IFTTT / n8n / your server): ALERT_WEBHOOK_URL
  DEFAULT_COUNTRY_CODE (default +91) is added to 10-digit numbers."""
import os, re, requests

def norm_phone(p):
    d = re.sub(r"[^\d+]", "", p or "")
    if d.startswith("+"): return d
    d = d.lstrip("0")
    return (os.environ.get("DEFAULT_COUNTRY_CODE", "+91") + d) if len(d) == 10 else ("+" + d if len(d) > 10 else d)

def channels():
    c = []
    if os.environ.get("TWILIO_SID") and os.environ.get("TWILIO_TOKEN") and os.environ.get("TWILIO_FROM"): c.append("sms")
    if os.environ.get("ALERT_WEBHOOK_URL"): c.append("webhook")
    return c

def send(contact, message):
    """-> list of {'contact','channel','status':'sent'|'failed'|'simulated','detail'} (one per configured channel)."""
    out, to = [], norm_phone(contact.get("phone"))
    for ch in channels():
        try:
            if ch == "sms":
                r = requests.post(f"https://api.twilio.com/2010-04-01/Accounts/{os.environ['TWILIO_SID']}/Messages.json", timeout=10,
                                  auth=(os.environ["TWILIO_SID"], os.environ["TWILIO_TOKEN"]), data={"To": to, "From": os.environ["TWILIO_FROM"], "Body": message})
            else:
                r = requests.post(os.environ["ALERT_WEBHOOK_URL"], timeout=10, json={"kind": "bikebuddy_alert", "to": to, "name": contact.get("name"), "message": message})
            r.raise_for_status(); out.append({"contact": contact.get("name"), "channel": ch, "status": "sent", "detail": ""})
        except Exception as ex: out.append({"contact": contact.get("name"), "channel": ch, "status": "failed", "detail": str(ex)[:100]})
    return out or [{"contact": contact.get("name"), "channel": "none", "status": "simulated", "detail": "No SMS/webhook configured in .env, so nothing was sent"}]
