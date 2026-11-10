"""Optional LLM for free-form understanding and small talk (any OpenAI-compatible API, e.g. Groq free tier).
Set LLM_KEY in .env to enable. Speech stays on Gnani Prisma/Timbre. Swap in Evon later by changing LLM_URL/LLM_MODEL."""
import os, json, requests
NAMES = {"hinglish": "Hinglish (Hindi written in Roman letters)", "english": "English",
         "hindi": "Hindi in Devanagari script", "kannada": "Kannada in Kannada script"}
def enabled(): return bool(os.environ.get("LLM_KEY"))

def chat(text, state, warnings, name, lang, history):
    sysmsg = (f"You are {name}, a friendly voice buddy for a motorcycle rider. Reply in {NAMES[lang]}. Maximum 2 short spoken "
              "sentences, no markdown, no emojis, numbers as digits. For any fact about the bike use ONLY BIKE DATA; if a fact is missing say "
              "you do not have it. The speech recogniser may mis-hear words, so infer what the rider most likely meant. Small talk is fine. "
              "Never give medical advice. If the rider says they are hurt, say help is being arranged. "
              f"BIKE DATA: {json.dumps(state)}. ACTIVE WARNINGS: {warnings}")
    r = requests.post(os.environ.get("LLM_URL", "https://api.groq.com/openai/v1/chat/completions"),
        headers={"Authorization": "Bearer " + os.environ["LLM_KEY"]}, timeout=8,
        json={"model": os.environ.get("LLM_MODEL", "llama-3.1-8b-instant"), "max_tokens": 120, "temperature": 0.4,
              "messages": [{"role": "system", "content": sysmsg}] + history[-6:] + [{"role": "user", "content": text}]})
    r.raise_for_status(); return r.json()["choices"][0]["message"]["content"].strip()
