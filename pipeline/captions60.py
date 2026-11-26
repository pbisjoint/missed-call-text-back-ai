"""Word-by-word karaoke captions (current spoken word in yellow) rendered as a transparent PNG sequence at 24 fps.
usage: captions.py <vo_dir> <out_dir> <w> <h> <duration_s>   (needs PIL: use system python3)"""
import sys, os, re, json, difflib
from PIL import Image, ImageDraw, ImageFont
FPS = int(os.environ.get("CAPFPS", 24)); YELLOW = (255, 225, 26, 255); WHITE = (255, 255, 255, 255)
FONTS = ["/usr/share/fonts/truetype/google-fonts/ofl/montserrat/Montserrat[wght].ttf", "/usr/share/fonts/truetype/google-fonts/Poppins-Bold.ttf",
         "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]
def font(size):
    for p in FONTS:
        if os.path.exists(p):
            f = ImageFont.truetype(p, size)
            try: f.set_variation_by_name("ExtraBold")
            except Exception: pass
            return f
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
def word_times(vo_dir):
    lines = json.load(open(os.path.join(vo_dir, "timings.json"))); wh = json.load(open(os.path.join(vo_dir, "words.json")))
    sw = []                                                     # script words with line index
    for li, L in enumerate(lines):
        for w in L["text"].split(): sw.append({"w": w, "line": li, "s": None, "e": None})
    a, b = [norm(x["w"]) for x in sw], [norm(x["w"]) for x in wh]
    for i, j, n in difflib.SequenceMatcher(None, a, b, autojunk=False).get_matching_blocks():
        for k in range(n): sw[i + k]["s"], sw[i + k]["e"] = wh[j + k]["s"], wh[j + k]["e"]
    for i, x in enumerate(sw):                                  # interpolate unmatched words inside their line window
        if x["s"] is None:
            p = next((k for k in range(i - 1, -1, -1) if sw[k]["s"] is not None and sw[k]["line"] == x["line"]), None)
            q = next((k for k in range(i + 1, len(sw)) if sw[k]["s"] is not None and sw[k]["line"] == x["line"]), None)
            L = lines[x["line"]]; t0 = sw[p]["e"] if p is not None else L["start"]; t1 = sw[q]["s"] if q is not None else L["end"]
            run = [k for k in range(len(sw)) if sw[k]["s"] is None and sw[k]["line"] == x["line"] and (p is None or k > p) and (q is None or k < q)]
            idx = run.index(i); step = (t1 - t0) / len(run); x["s"], x["e"] = t0 + idx * step, t0 + (idx + 1) * step
    return sw, lines
def chunks(sw, W=360, maxw=3):
    f = font(int(W * 0.13)); out, cur = [], []
    wid = lambda ws: sum(f.getlength(t) for t in ws) + f.getlength(" ") * (len(ws) - 1)
    for x in sw:
        x["t"] = re.sub(r"[.,!?;:]", "", x["w"]).upper()
        if cur and (wid([c["t"] for c in cur] + [x["t"]]) > W * 0.88 or len(cur) >= maxw or cur[-1]["line"] != x["line"]): out.append(cur); cur = []
        cur.append(x)
        if re.search(r"[.!?,]$", x["w"]): out.append(cur); cur = []
    if cur: out.append(cur)
    return out
def draw_chunk(W, H, chunk, active, scale=1.0):
    words = [c["t"] for c in chunk]; size = int(W * 0.13 * scale); f = font(size); sp = f.getlength(" "); ws = [f.getlength(t) for t in words]; tot = sum(ws) + sp * (len(words) - 1)
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0)); d = ImageDraw.Draw(im); x = (W - tot) / 2; y = int(H * 0.64); sw_ = max(3, int(size * 0.16))
    for i, t in enumerate(words):
        col = YELLOW if i == active else WHITE
        d.text((x + 2, y + 4), t, font=f, fill=(0, 0, 0, 150), stroke_width=sw_, stroke_fill=(0, 0, 0, 150))       # soft drop shadow
        d.text((x, y), t, font=f, fill=col, stroke_width=sw_, stroke_fill=(0, 0, 0, 255)); x += ws[i] + sp
    return im
if __name__ == "__main__":
    vo, out, W, H, D = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), float(sys.argv[5]); os.makedirs(out, exist_ok=True)
    sw, lines = word_times(vo); ch = chunks(sw, W); n = int(D * FPS) + FPS; blank = Image.new("RGBA", (W, H), (0, 0, 0, 0)); cache = {}
    for i, c in enumerate(ch):                                  # chunk window: first word start -> (hold to next chunk if close)
        c0 = c[0]["s"]; c1 = c[-1]["e"] + 0.18
        if i + 1 < len(ch) and ch[i + 1][0]["s"] - c[-1]["e"] < 1.2: c1 = ch[i + 1][0]["s"] - 0.01      # hold through short pauses: never a blank gap
        for x in c: x["_w"] = (c0, c1)
        c.append({"_chunk": (c0, c1)}) if False else None
    for fi in range(n):
        t = fi / FPS; state = None
        for c in ch:
            c0, c1 = c[0]["_w"]
            if c0 <= t < c1:
                act = max([k for k, x in enumerate(c) if x["s"] <= t] or [0]); pop = min((t - c0) * 24, 3.0)
                scale = [0.82, 1.08, 1.0, 1.0][int(pop)]; state = (id(c), act, scale); chunk = c; break
        if state is None: im = blank
        else:
            if state not in cache: cache[state] = draw_chunk(W, H, chunk, state[1], state[2])
            im = cache[state]
        im.save(os.path.join(out, f"cap_{fi + 1:04d}.png"))
    print("captions", len(ch), "chunks,", n, "frames")
