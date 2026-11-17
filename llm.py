"""Optional LLM for free-form understanding, small talk and rewriting maintenance advice (any OpenAI-compatible API, e.g. Groq free tier).
Set LLM_KEY in .env to enable. Speech stays on Gnani Prisma/Timbre. Swap in Evon later by changing LLM_URL/LLM_MODEL."""
import os, json, re, requests
NAMES = {"hinglish": "Hinglish (Hindi written in Roman letters)", "english": "English",
         "hindi": "Hindi in Devanagari script", "kannada": "Kannada in Kannada script"}
def enabled(): return bool(os.environ.get("LLM_KEY"))

def _post(messages, max_tokens, temperature):
    r = requests.post(os.environ.get("LLM_URL", "https://api.groq.com/openai/v1/chat/completions"),
        headers={"Authorization": "Bearer " + os.environ["LLM_KEY"]}, timeout=8,
        json={"model": os.environ.get("LLM_MODEL", "llama-3.1-8b-instant"), "max_tokens": max_tokens, "temperature": temperature, "messages": messages})
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()

def chat(text, state, warnings, name, lang, history, ctx=None):
    sysmsg = (f"You are {name}, a friendly voice buddy for a motorcycle rider. Reply in {NAMES[lang]}. Maximum 2 short spoken "
              "sentences, no markdown, no emojis, numbers as digits. For any fact about the bike use ONLY the data below; if a fact is missing say "
              "you do not have it. Values are tagged in value_sources: 'sim' means DEMO data, so say it is demo data and never call it live; 'sensor' is real "
              "live data; 'user' was typed in by the rider; 'estimate' is calculated. If data_source is not 'connected', do not claim the readings are live. "
              "The speech recogniser may mis-hear words, so infer what the rider most likely meant. Small talk is fine. "
              "Never give medical advice. If the rider says they are hurt, say help is being arranged. "
              f"BIKE DATA: {json.dumps(state, default=str)}. ACTIVE WARNINGS: {warnings}. CONTEXT: {json.dumps(ctx or {}, default=str)}")
    return _post([{"role": "system", "content": sysmsg}] + history[-6:] + [{"role": "user", "content": text}], 120, 0.4)

def suggest(items, state, pace):
    """Rewrite rule-generated maintenance items into 2-4 short, friendly tips. Must not add facts. Returns [{priority,title,why,basis}]."""
    msg = ("You are a motorcycle maintenance assistant. Rewrite these maintenance findings as at most 4 short tips for the rider. "
           "Use ONLY the facts given; do not invent numbers or dates. Reply with a JSON array only: [{\"title\":str,\"why\":str}]. "
           f"FINDINGS: {json.dumps(items)} BIKE DATA: {json.dumps(state, default=str)} RIDING PACE: {json.dumps(pace)}")
    raw = _post([{"role": "user", "content": msg}], 400, 0.2)
    arr = json.loads(re.search(r"\[.*\]", raw, re.S).group(0))
    return [{"priority": i + 1, "title": str(a["title"])[:90], "why": str(a["why"])[:220], "basis": "ai-generated estimate"} for i, a in enumerate(arr[:4])]
