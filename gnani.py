"""Gnani STT (Prisma) + TTS (Timbre) REST wrapper with throttling, retry on 429/5xx, and TTS caching."""
import os, time, threading, requests
BASE = "https://api.vachana.ai"
_lock, _last, _cache, _calls = threading.Lock(), [0.0], {}, [0]
CAP = int(os.environ.get('GNANI_CALL_CAP', '400'))   # protects your credits on a public demo

def _headers():
    key = os.environ.get("GNANI_API_KEY")
    if not key: raise RuntimeError("Set GNANI_API_KEY in .env")
    return {"X-API-Key-ID": key}

def _post(url, **kw):
    """One call at a time, 0.45 s apart; back off and retry when Gnani says 'too many requests'."""
    _calls[0] += 1
    if _calls[0] > CAP: raise RuntimeError("Demo call limit reached, please try again later")
    for n in range(5):
        with _lock:
            time.sleep(max(0, 0.45 - (time.time() - _last[0])))
            r = requests.post(url, timeout=60, **kw); _last[0] = time.time()
        if r.status_code in (429, 500, 502, 503):
            try: wait = float(r.headers.get("Retry-After", 0))
            except ValueError: wait = 0
            time.sleep(min(wait or 1.5 * (n + 1), 8)); continue
        r.raise_for_status(); return r
    r.raise_for_status(); return r

def stt(wav_bytes: bytes, language_code="en-IN", fmt="transcribe"):
    t = time.time()
    r = _post(f"{BASE}/stt/v3", headers=_headers(), files={"audio_file": ("audio.wav", wav_bytes, "audio/wav")},
              data={"language_code": language_code, "format": fmt})
    return r.json().get("transcript", ""), time.time() - t

def tts(text, voice="Poorvi", language="hi-en", model="timbre-v2.5", sample_rate=24000, speed=1.0):
    key = (text, voice, language, model, sample_rate, speed)
    if key in _cache: return _cache[key], 0.0          # repeated lines cost no API call
    t = time.time()
    r = _post(f"{BASE}/api/v1/tts/inference", headers={**_headers(), "Content-Type": "application/json"},
              json={"text": text, "voice": voice, "model": model, "language": language, "speed": speed,
                    "audio_config": {"sample_rate": sample_rate, "num_channels": 1, "sample_width": 2,
                                     "encoding": "linear_pcm", "container": "wav"}})
    _cache[key] = r.content
    return r.content, time.time() - t
