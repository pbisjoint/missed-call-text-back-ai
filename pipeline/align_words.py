"""usage: align_words.py <vo_dir>  -> words.json [{w,s,e}] from vo.wav via faster-whisper (decodes with ffmpeg, avoids PyAV)."""
import os, sys, json, subprocess
import numpy as np, soundfile as sf
d = sys.argv[1]; tmp = os.path.join(d, "vo16k.wav")
subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(d, "vo.wav"), "-ac", "1", "-ar", "16000", tmp], check=True)
a, _ = sf.read(tmp, dtype="float32")
from faster_whisper import WhisperModel
wm = WhisperModel("base.en", device="cpu", compute_type="int8")
segs, _ = wm.transcribe(a, word_timestamps=True, language="en", beam_size=5, condition_on_previous_text=False)
words = [{"w": w.word.strip(), "s": round(w.start, 3), "e": round(w.end, 3)} for sg in segs for w in sg.words]
json.dump(words, open(os.path.join(d, "words.json"), "w"), indent=1); print(len(words), "words")
