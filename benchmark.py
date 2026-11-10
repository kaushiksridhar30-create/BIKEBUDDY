"""Noise benchmark. Put 16 kHz mono WAVs in clips/ named fine_*.wav / help_*.wav / unclear_*.wav
(record yourself or generate with Timbre). Adds white noise at several SNRs and reports label accuracy."""
import array, glob, io, math, os, random, wave
from dotenv import load_dotenv
import gnani, engine
load_dotenv()

def add_noise(path, snr_db):
    w = wave.open(path); p = w.getparams(); s = array.array("h", w.readframes(w.getnframes()))
    rms = math.sqrt(sum(x * x for x in s) / len(s)) or 1; n = rms / (10 ** (snr_db / 20))
    out = array.array("h", [max(-32768, min(32767, int(x + random.gauss(0, n)))) for x in s])
    b = io.BytesIO(); o = wave.open(b, "wb"); o.setparams(p); o.writeframes(out.tobytes()); o.close(); return b.getvalue()

files = sorted(glob.glob("clips/*.wav"))
print("SNR(dB) | accuracy | missed 'help' (dangerous)")
for snr in [30, 20, 10, 5, 0]:
    ok = miss = helps = 0
    for f in files:
        want = os.path.basename(f).split("_")[0]
        got = engine.classify(gnani.stt(add_noise(f, snr))[0])
        ok += got == want; helps += want == "help"; miss += (want == "help" and got != "help")
    print(f"{snr:7} | {ok}/{len(files)} | {miss}/{helps}")
