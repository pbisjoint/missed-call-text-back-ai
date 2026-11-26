"""usage: cb_vo.py <outdir> [exaggeration] [cfg_weight] [temperature] [seed]
Reads <outdir>/lines.json [{id,text,gap}], synthesizes with Chatterbox (MIT) line by line, trims, lays out on a timeline,
masters (EQ, compression, loudnorm) -> vo.wav (48 kHz), writes timings.json (per line) and words.json (Whisper word timings)."""
import os, sys, json, subprocess
os.environ.setdefault("TQDM_DISABLE", "1")
import numpy as np, soundfile as sf, torch
out = sys.argv[1]; ex = float(sys.argv[2]) if len(sys.argv) > 2 else 0.35
cfg = float(sys.argv[3]) if len(sys.argv) > 3 else 0.5; tp = float(sys.argv[4]) if len(sys.argv) > 4 else 0.7
seed = int(sys.argv[5]) if len(sys.argv) > 5 else 7
lines = json.load(open(os.path.join(out, "lines.json")))
from chatterbox.tts import ChatterboxTTS
m = ChatterboxTTS.from_pretrained(device="cpu"); SR = m.sr
def trim(w, thr=0.012, pad=int(0.04 * SR)):
    idx = np.where(np.abs(w) > thr)[0]
    return w if len(idx) == 0 else w[max(idx[0] - pad, 0): idx[-1] + pad]
tracks, t, timings = [], 0.4, []
for L in lines:
    torch.manual_seed(seed)
    w = m.generate(L["text"], exaggeration=ex, cfg_weight=cfg, temperature=tp).squeeze().numpy().astype(np.float32)
    w = trim(w); fi = int(0.01 * SR); w[:fi] *= np.linspace(0, 1, fi); w[-fi:] *= np.linspace(1, 0, fi)
    d = len(w) / SR; timings.append({"id": L["id"], "text": L["text"], "start": round(t, 3), "end": round(t + d, 3)})
    tracks.append((t, w)); print("LINE", L["id"], round(d, 2), flush=True); t += d + L["gap"]
buf = np.zeros(int((t + 0.8) * SR), dtype=np.float32)
for s, w in tracks: a = int(s * SR); buf[a:a + len(w)] += w
raw = os.path.join(out, "vo_raw.wav"); sf.write(raw, buf, SR)
chain = "highpass=f=80,equalizer=f=250:width_type=q:w=1:g=-1.5,acompressor=threshold=-21dB:ratio=3:attack=4:release=70:makeup=4,equalizer=f=3200:width_type=q:w=1:g=2.5,lowpass=f=11000,loudnorm=I=-16:TP=-1.5:LRA=7"
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", raw, "-af", chain, "-ar", "48000", os.path.join(out, "vo.wav")], check=True)
json.dump(timings, open(os.path.join(out, "timings.json"), "w"), indent=1)
from faster_whisper import WhisperModel
wm = WhisperModel("base.en", device="cpu", compute_type="int8")
segs, _ = wm.transcribe(os.path.join(out, "vo.wav"), word_timestamps=True, language="en", beam_size=5, condition_on_previous_text=False)
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for sg in segs for w in sg.words]
json.dump(words, open(os.path.join(out, "words.json"), "w"), indent=1); print("WORDS", len(words), "END", round(t, 2), flush=True)
