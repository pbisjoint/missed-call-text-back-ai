"""Short: the hydrant color code. usage: short_hydrant.py plan | stills <out> <w> <h> <spp> <frames..> | anim <out> <w> <h> <spp> [start end]
Timeline = 30 fps (real frames); the final 60 fps comes from interpolation + 60 fps post effects."""
import sys, os, json, math, re
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
FPS = 30; VO = "vo4"
T = {t["id"]: t for t in json.load(open(f"{VO}/timings.json"))}; WD = json.load(open(f"{VO}/words.json"))
norm = lambda w: re.sub(r"[^a-z0-9]", "", w.lower())
ALIAS = {"fifteen": "1500", "thousand": "1000", "five": "500"}
def word(w, after=0.0):
    w = ALIAS.get(w, w)
    for x in WD:
        if norm(x["w"]) == w and x["s"] >= after - 1e-6: return x["s"]
    raise KeyError(w)
def fr(t): return int(round(t * FPS)) + 1
END_T = T["twist"]["end"] + 0.9; N = fr(END_T)
tc, tb = word("cap"), None
CUT = {"S1a": 0.0, "S1b": tc - 0.10, "S2": T["back"]["start"] - 0.10, "S3": T["blue"]["start"] - 0.10, "S4a": T["gor"]["start"] - 0.10,
       "S4b": word("orange", T["gor"]["start"]) - 0.12, "S5": T["red"]["start"] - 0.10, "S6a": T["turn"]["start"] - 0.10,
       "S6b": word("run", T["turn"]["start"]) - 0.10, "S7": T["twist"]["start"] - 0.10}
ORDER = list(CUT); SHOT = {}
for i, n in enumerate(ORDER):
    a = fr(CUT[n]); b = (fr(CUT[ORDER[i + 1]]) - 1) if i + 1 < len(ORDER) else N; SHOT[n] = (a, b)
if sys.argv[1] == "plan":
    print("N", N, "dur", round(END_T, 2)); [print(n, a, b, round((b - a + 1) / FPS, 2), "s") for n, (a, b) in SHOT.items()]
    print("cuts", ",".join(str(SHOT[n][0]) for n in ORDER))
    GL = [tc, word("blue", T["blue"]["start"]), word("green", T["gor"]["start"]), word("orange", T["gor"]["start"]), word("red", T["red"]["start"]), word("blue", T["turn"]["start"]), word("painted")]
    NU = [word("fifteen"), word("thousand", T["gor"]["start"]), word("five", T["gor"]["start"]), word("under", T["red"]["start"])]
    os.makedirs("out", exist_ok=True); json.dump({"order": ORDER, "shots": {n: list(SHOT[n]) for n in ORDER}, "glows": GL, "nums": NU}, open("out/sh_meta.json", "w")); sys.exit()
import zshorts as z, zh, bpy
from mathutils import Vector
mode, out = sys.argv[1], sys.argv[2]; W, H, SPP = (int(x) for x in sys.argv[3:6]); A = z.CACHE
s = z.reset(W, H, fps=FPS, samples=SPP); z.look(s, mblur=False)
s.cycles.denoising_quality = "FAST"; s.cycles.denoising_input_passes = "RGB"; s.render.use_persistent_data = True
z.sky(z.ph_hdri("abandoned_parking"), strength=0.75, rot_deg=0); z.sun(elev=17, azim=205, strength=4.6, color=(1.0, 0.82, 0.60), angle=2.5)
z.ground(z.ph_tex("asphalt_02"), size=300, tile=120)
XS = {"blue": 0.0, "green": 2.7, "orange": 5.4, "red": 8.1}
HY = {c: zh.hydrant(c, (x + 0.46, 0.05, 0), rot_z=0.0) for c, x in XS.items()}
for x in (-6, 14): z.prop(z.ph_model("street_lamp_01"), loc=(x, 3.2, 0))
# ---- glow highlights (orange rim, fades) keyed on the named word
def G(color, t, hold=0.9): zh.glow(HY[color], (fr(t), fr(t + 0.22), fr(t + hold)))
G("blue", tc); G("blue", word("blue", T["blue"]["start"]), 1.6); G("green", word("green", T["gor"]["start"]), 1.0)
G("orange", word("orange", T["gor"]["start"]), 1.0); G("red", word("red", T["red"]["start"]), 2.4); G("blue", word("blue", T["turn"]["start"]), 1.2); G("blue", word("painted"), 1.6)
# ---- big 3D numbers standing in the scene (pop in on the spoken number)
def num(txt, loc, t_in, hold=1.6, size=0.5, color=(1.0, 0.30, 0.02)):
    cu = bpy.data.curves.new("t_" + txt, "FONT"); cu.body = txt; cu.size = size; cu.extrude = 0.03; cu.align_x = "CENTER"; cu.bevel_depth = 0.01
    ob = bpy.data.objects.new("t_" + txt, cu); s.collection.objects.link(ob); ob.location = loc; ob.rotation_euler = (math.radians(90), 0, 0)
    m = bpy.data.materials.new("m_" + txt); m.use_nodes = True; nt = m.node_tree; nt.nodes.clear()
    em = nt.nodes.new("ShaderNodeEmission"); em.inputs["Color"].default_value = (*color, 1); em.inputs["Strength"].default_value = 1.7
    o = nt.nodes.new("ShaderNodeOutputMaterial"); nt.links.new(em.outputs[0], o.inputs[0]); cu.materials.append(m)
    f0 = fr(t_in)
    for f, k in ((f0 - 1, 0.001), (f0, 0.001), (f0 + 4, 1.25), (f0 + 7, 1.0), (fr(t_in + hold), 1.0), (fr(t_in + hold) + 3, 0.001)):
        ob.scale = (k, k, k); ob.keyframe_insert("scale", frame=f)
    ob.scale = (0.001,) * 3; return ob
num("1,500+", (0.0, -0.1, 1.40), word("fifteen"), hold=2.0, size=0.32)
num("1,000", (XS["green"], -0.1, 1.40), word("thousand", T["gor"]["start"]), hold=1.1, size=0.30)
num("500", (XS["orange"], -0.1, 1.40), word("five", T["gor"]["start"]), hold=1.2, size=0.30)
num("<500", (XS["red"], -0.1, 1.40), word("under", T["red"]["start"]), hold=2.4, size=0.30)
# ---- the firefighter
V = 3.8; FRM = 1.25
hero = z.character(f"{A}/q_animatedmen/FBX/Male_Casual.fbx", "Run", 1.8, N + 30)
arm = next(o for o in z._descendants(hero) if o.type == "ARMATURE")
for st in arm.animation_data.nla_tracks[0].strips: st.scale = FRM; st.repeat = st.repeat / FRM + 1
HIDDEN = (0, 0, -60); BASEZ = hero.location.z; YAW = math.pi - hero["facing"]
HERO = {}
a2, b2 = SHOT["S2"]; HERO["S2"] = (a2, b2, 17.0)
a6, b6 = SHOT["S6a"][0], SHOT["S6b"][1]; HERO["S6"] = (a6, b6, 1.3 + V * (b6 - a6) / FPS)
def hero_pos(shot, f):                                 # python mirror of the hero path (also drives the camera)
    a, _, x_a = HERO[shot]; return x_a - V * (f - a) / FPS
def hero_update(scene, *args):
    f = scene.frame_current
    for sh in ("S2", "S6"):
        a, b, _ = HERO[sh]
        if a <= f <= b: hero.location = (hero_pos(sh, f), -1.8, BASEZ); hero.rotation_euler.z = YAW; return
    hero.location = (0, 0, -60)
bpy.app.handlers.frame_change_pre.append(hero_update)
# helmet on the head bone
hb = next((b for b in arm.pose.bones if b.name.lower().endswith("head")), None)
if hb is not None:
    bpy.ops.mesh.primitive_uv_sphere_add(radius=0.30, location=(0, 0, 0)); hm = bpy.context.object; hm.name = "helmet"; hm.scale = (1.05, 1.0, 0.8)
    mt = bpy.data.materials.new("helmet"); mt.use_nodes = True; mt.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.9, 0.03, 0.03, 1)
    mt.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.35; hm.data.materials.append(mt)
    hm.parent = arm; hm.parent_type = "BONE"; hm.parent_bone = hb.name; hm.location = (0, -0.12, 0.0)
# ---- cameras: one per shot, keyed every frame, bound by markers
def ease(t): return t * t * (3 - 2 * t)
def lerp(p, q, t): return [p[i] + (q[i] - p[i]) * t for i in range(3)]
def cam_shot(name, posf, aimf, lens=30, fstop=3.2, shake=0.012):
    a, b = SHOT[name]; cd = bpy.data.cameras.new(name); cd.lens = lens; cd.dof.use_dof = True; cd.dof.aperture_fstop = fstop
    cam = bpy.data.objects.new(name, cd); s.collection.objects.link(cam); aim = bpy.data.objects.new(name + "_aim", None); s.collection.objects.link(aim); cd.dof.focus_object = aim
    c = cam.constraints.new("TRACK_TO"); c.target = aim; c.track_axis, c.up_axis = "TRACK_NEGATIVE_Z", "UP_Y"
    for f in range(a, b + 1):
        u = (f - a) / max(b - a, 1); p = posf(u, f); q = aimf(u, f)
        j = [shake * (math.sin(f * 0.9 + i * 2.1) + 0.5 * math.sin(f * 2.3 + i)) for i in range(3)]
        cam.location = Vector(p) + Vector(j); cam.keyframe_insert("location", frame=f); aim.location = q; aim.keyframe_insert("location", frame=f)
    m = s.timeline_markers.new(name, frame=a); m.camera = cam
    if s.camera is None: s.camera = cam
mv = lambda p, q, k=1.0: (lambda u, f: lerp(p, q, ease(min(u * k, 1))))
fix = lambda p: (lambda u, f: p)
cam_shot("S1a", mv((-1.1, -1.9, 0.26), (-0.45, -1.3, 0.38)), mv((0.0, 0.0, 0.62), (0.0, 0.0, 0.80)), lens=26, fstop=2.8)
cam_shot("S1b", mv((0.65, -1.15, 0.72), (0.18, -0.62, 0.70)), mv((0.0, -0.17, 0.68), (0.0, -0.17, 0.68)), lens=50, fstop=2.0)
cam_shot("S2", lambda u, f: (hero_pos("S2", f) + 2.6 - 3.2 * ease(u), -6.4, 0.9 + 0.5 * u), lambda u, f: (hero_pos("S2", f), -1.8, 1.0), lens=32)
cam_shot("S3", mv((6.4, -3.3, 0.55), (0.9, -2.0, 0.62)), mv((4.0, 0.0, 0.7), (0.0, 0.0, 1.05)), lens=32)
cam_shot("S4a", mv((3.9, -1.9, 0.55), (3.0, -1.4, 0.72)), mv((2.7, 0.0, 0.8), (2.7, 0.0, 0.85)), lens=32, fstop=2.8)
cam_shot("S4b", mv((6.6, -1.9, 0.55), (5.7, -1.4, 0.74)), mv((5.4, 0.0, 0.8), (5.4, 0.0, 0.85)), lens=32, fstop=2.8)
cam_shot("S5", mv((9.4, -2.6, 0.45), (8.4, -1.2, 0.70)), mv((8.1, 0.0, 0.8), (8.1, 0.0, 0.85)), lens=34, fstop=2.8)
cam_shot("S6a", lambda u, f: (hero_pos("S6", f) - 3.4 + 1.2 * u, -3.9, 0.35), lambda u, f: (hero_pos("S6", f), -1.8, 1.1), lens=24, fstop=4.0)
cam_shot("S6b", lambda u, f: (hero_pos("S6", f) + 1.6 - 1.0 * u, -4.2, 1.9 - 0.9 * u), lambda u, f: (hero_pos("S6", f), -1.8, 0.95), lens=28, fstop=4.0)
cam_shot("S7", mv((0.7, -1.3, 0.9), (0.14, -0.62, 0.68)), mv((0.0, -0.17, 0.70), (0.0, -0.17, 0.68)), lens=50, fstop=2.0)
s.frame_start, s.frame_end = 1, N
if mode == "stills":
    os.makedirs(out, exist_ok=True)
    for f in (int(x) for x in sys.argv[6:]):
        s.frame_set(f); s.render.filepath = f"{out}/s_{f:04d}.png"; bpy.ops.render.render(write_still=True)
else:
    a = int(sys.argv[6]) if len(sys.argv) > 6 else 1; b = int(sys.argv[7]) if len(sys.argv) > 7 else N
    os.makedirs(out, exist_ok=True); s.render.use_overwrite = False; z.render(out, start=a, end=b, step=1, prefix="f_")
