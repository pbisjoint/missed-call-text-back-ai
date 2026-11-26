"""usage: assemble60.py <frames30_dir> <vo_dir> <final.mp4> <w> <h> <shots_json>   (system python3; PIL+numpy)
frames30: f_%04d.png at 30 fps real frames. shots_json: {"order":[names],"shots":{name:[a,b]}}.
Per shot: ffmpeg minterpolate 30->60, then true-60fps post: drift zoom, smash zooms, shake, whip blur at cuts, glow bloom; captions + sound."""
import sys, os, json, subprocess, tempfile, re, math, random
import numpy as np
from PIL import Image, ImageFilter, ImageChops
frames, vodir, final, W, H, SJ = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), json.load(open(sys.argv[6]))
HERE = os.path.dirname(os.path.abspath(__file__)); tmp = tempfile.mkdtemp(prefix="asm60_")
run = lambda *a, **k: subprocess.run(list(a), check=True, **k)
T = {t["id"]: t for t in json.load(open(os.path.join(vodir, "timings.json")))}; WD = json.load(open(os.path.join(vodir, "words.json")))
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
ALIAS = {"fifteen": "1500", "thousand": "1000", "five": "500"}
def word(w, after=0.0):
    w = ALIAS.get(w, w)
    for x in WD:
        if norm(x["w"]) == w and x["s"] >= after - 1e-6: return x["s"]
    raise KeyError(w)
order, SH = SJ["order"], SJ["shots"]
# ---- 1) interpolate each shot 30 -> 60 fps
clips, starts, n60 = [], [], 0
for k, n in enumerate(order):
    a, b = SH[n]; cnt = b - a + 1; clip = os.path.join(tmp, f"c{k}.mkv")
    run("ffmpeg", "-y", "-loglevel", "error", "-framerate", "30", "-start_number", str(a), "-i", os.path.join(frames, "f_%04d.png"), "-frames:v", str(cnt),
        "-vf", "minterpolate=fps=60:mi_mode=mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1,tpad=stop_mode=clone:stop=4", "-frames:v", str(2 * cnt), "-c:v", "libx264", "-crf", "8", "-preset", "ultrafast", "-pix_fmt", "yuv420p", clip)
    clips.append(clip); starts.append(n60); n60 += 2 * cnt
D = n60 / 60.0; print("frames60", n60, "dur", round(D, 2), flush=True)
open(os.path.join(tmp, "list.txt"), "w").write("".join(f"file '{c}'\n" for c in clips)); joined = os.path.join(tmp, "joined.mkv")
run("ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", os.path.join(tmp, "list.txt"), "-c", "copy", joined)
# ---- 2) events (seconds): smash zooms (t, dur, peak), shakes (t, dur, px), whip cuts
ZOOM = [(word("secret"), 0.16, 1.30), (word("fifteen"), 0.18, 1.18), (word("barely"), 0.16, 1.22), (word("run", T["turn"]["start"]), 0.16, 1.20), (word("painted"), 0.20, 1.32)]
SHAKE = [(word("secret"), 0.30, 14), (word("trickle"), 0.35, 18), (word("fire", 22.0), 0.45, 22)]
WHIP = {"S2", "S3", "S4a", "S4b", "S5", "S6a", "S6b"}
cutf = {n: starts[i] for i, n in enumerate(order)}
ease = lambda t: t * t * (3 - 2 * t)
def hblur(im, frac):
    if frac < 0.004: return im
    w = max(int(W * (1 - frac)), 8); return im.resize((w, H), Image.BILINEAR).resize((W, H), Image.BILINEAR)
def bloom(im):
    sm = im.resize((W // 3, H // 3), Image.BILINEAR); arr = np.asarray(sm).astype(np.float32) / 255
    lum = arr.max(axis=2); sat = arr.max(axis=2) - arr.min(axis=2)
    mask = np.clip((lum - 0.80) * 5, 0, 1) * np.clip(sat * 2.4, 0.15, 1)
    hot = Image.fromarray((arr * mask[..., None] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(7)).resize((W, H), Image.BILINEAR)
    return ImageChops.screen(im, Image.eval(hot, lambda v: min(255, int(v * 1.35))))
shot_of = np.zeros(n60, dtype=int)
for i, st in enumerate(starts): shot_of[st:(starts[i + 1] if i + 1 < len(starts) else n60)] = i
# ---- 3) captions at 60 fps
capdir = os.path.join(tmp, "caps"); env = dict(os.environ, CAPFPS="60"); run("python3", os.path.join(HERE, "captions60.py"), vodir, capdir, str(W), str(H), f"{D:.3f}", env=env)
# ---- 4) sound design
S = []; ms = lambda x: int(max(x, 0) * 1000)
for n in order:
    if n in WHIP: S.append(("whoosh", "anoisesrc=d=0.5:c=pink:a=0.7,highpass=f=600,lowpass=f=7000,afade=t=in:d=0.2,afade=t=out:st=0.2:d=0.3", cutf[n] / 60 - 0.17, 0.5))
for t0, dur, pk in ZOOM: S.append(("thud", "sine=f=62:d=0.28,afade=t=out:st=0.02:d=0.26", t0 - 0.02, 1.9)); S.append(("zip", "anoisesrc=d=0.22:c=white:a=0.5,highpass=f=2500,afade=t=out:st=0.02:d=0.2", t0 - 0.06, 0.25))
for g in SJ.get("glows", []): S.append(("ding", "sine=f=1568:d=0.7,afade=t=out:st=0.01:d=0.69", g, 0.28)); S.append(("ding2", "sine=f=2349:d=0.5,afade=t=out:st=0.01:d=0.49", g + 0.05, 0.15))
for tn in SJ.get("nums", []): S.append(("pop", "sine=f=520:d=0.12,afade=t=out:st=0.01:d=0.11", tn, 0.5))
S.append(("boom", "sine=f=46:d=1.2,afade=t=out:st=0.04:d=1.1", T["twist"]["end"] + 0.05, 2.6))
si, parts = [], []
for i, (lab, src, dl, g) in enumerate(S):
    si += ["-f", "lavfi", "-i", src]; d = ms(dl); parts.append(f"[{i + 1}]adelay={d}|{d},volume={g}[a{i}]")
fc = ";".join(parts) + ";[0]anull[vo];[vo]" + "".join(f"[a{i}]" for i in range(len(S))) + f"amix=inputs={len(S) + 1}:normalize=0,alimiter=limit=0.85:level=0,atrim=0:{D:.3f}[a]"
sfx = os.path.join(tmp, "audio.wav"); run("ffmpeg", "-y", "-loglevel", "error", "-i", os.path.join(vodir, "vo.wav"), *si, "-filter_complex", fc, "-map", "[a]", sfx)
# ---- 5) true-60fps effects pass -> encoder
dec = subprocess.Popen(["ffmpeg", "-loglevel", "error", "-i", joined, "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], stdout=subprocess.PIPE)
grade = "eq=contrast=1.06:saturation=1.12,vignette=PI/6,unsharp=5:5:0.5,fade=t=out:st=%.3f:d=0.15,format=yuv420p" % (D - 0.15)
enc = subprocess.Popen(["ffmpeg", "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-framerate", "60", "-i", "-", "-i", sfx, "-vf", grade,
                        "-c:v", "libx264", "-crf", "16", "-preset", "veryfast", "-r", "60", "-c:a", "aac", "-b:a", "160k", "-shortest", final], stdin=subprocess.PIPE)
random.seed(3); fsz = W * H * 3
for i in range(n60):
    buf = dec.stdout.read(fsz)
    if len(buf) < fsz: break
    im = Image.frombytes("RGB", (W, H), buf); k = shot_of[i]; name = order[k]; t = i / 60.0; ts = t - starts[k] / 60.0
    shot_len = ((starts[k + 1] if k + 1 < len(starts) else n60) - starts[k]) / 60.0
    zoom = 1.0 + 0.035 * ts / max(shot_len, 0.1)                                # nothing holds still: drift push
    for t0, dur, pk in ZOOM:
        if starts[k] / 60.0 <= t0 <= t: zoom = max(zoom, 1.0 + (pk - 1.0) * ease(min((t - t0) / dur, 1.0)) + 0.02 * ts)
    dx = dy = 0.0
    for t0, dur, px in SHAKE:
        if t0 <= t < t0 + dur: d = 1 - (t - t0) / dur; dx += px * d * math.sin((t - t0) * 140); dy += px * d * math.cos((t - t0) * 170) * 0.8
    lf = i - starts[k]; lt = (starts[k + 1] if k + 1 < len(starts) else n60) - 1 - i      # frames since shot start / until its end
    shiftx, blurf = 0.0, 0.0
    if name in WHIP and lf < 6: p = (6 - lf) / 7.0; shiftx = -W * 0.55 * p * p * (1 if k % 2 else -1); blurf = 0.20 * p
    if k + 1 < len(order) and order[k + 1] in WHIP and lt < 6: p = (6 - lt) / 7.0; shiftx = W * 0.55 * p * p * (1 if (k + 1) % 2 else -1); blurf = 0.20 * p
    tx, ty = dx - shiftx, dy
    im = im.transform((W, H), Image.AFFINE, (1 / zoom, 0, W / 2 - (W / 2 + tx) / zoom, 0, 1 / zoom, H / 2 - (H / 2 + ty) / zoom), resample=Image.BILINEAR)
    im = hblur(im, blurf); im = bloom(im)
    cp = os.path.join(capdir, f"cap_{i + 1:04d}.png")
    if os.path.exists(cp): im = im.convert("RGBA"); im.alpha_composite(Image.open(cp)); im = im.convert("RGB")
    enc.stdin.write(im.tobytes())
enc.stdin.close(); enc.wait()
r = subprocess.run(["ffmpeg", "-nostats", "-i", final, "-af", "ebur128=peak=true", "-f", "null", "-"], capture_output=True, text=True).stderr
I = re.findall(r"I:\s+(-?[\d.]+) LUFS", r); Pk = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", r)
print(f"WROTE {final} {D:.2f}s loudness={I[-1] if I else '?'} LUFS peak={Pk[-1] if Pk else '?'} dBFS")
