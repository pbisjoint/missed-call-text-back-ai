"""Short helpers: painted hydrants + glow highlight + stage. import after zshorts."""
import bpy, math
import zshorts as z
from mathutils import Vector
COL = {"blue": (0.05, 0.38, 1.0), "green": (0.03, 0.75, 0.10), "orange": (1.0, 0.33, 0.0), "red": (0.9, 0.02, 0.02)}
def _desc(o):
    for c in o.children:
        yield c; yield from _desc(c)
BONNET_Z = 0.62
def hydrant(color, loc, rot_z=0.0, scale=1.5, bonnet_z=0.62):
    """paint caps + top bonnet; returns dict(root, parts, mats) -- glow keys through glow()"""
    r = z.prop(z.ph_model("fire_hydrant"), loc=loc, rot_z=rot_z, scale=scale)
    parts = [o for o in _desc(r) if o.type == "MESH"]
    paints = []
    for o in parts:
        if "_aged" in o.name: o.hide_render = True; o.hide_viewport = True; continue
        old = o.data.materials[0]; m = old.copy(); o.data.materials[0] = m; nt = m.node_tree
        bsdf = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
        paint = nt.nodes.new("ShaderNodeRGBCurve") if False else None
        is_cap = "cap_" in o.name
        is_body = (not is_cap) and ("chain" not in o.name)
        if is_body or is_cap:
            src = bsdf.inputs["Base Color"]; link = src.links[0].from_socket if src.links else None
            mix = nt.nodes.new("ShaderNodeMix"); mix.data_type = "RGBA"; mix.inputs[7].default_value = (*COL[color], 1)
            if is_cap and link: nt.links.new(link, mix.inputs[6])
            elif is_cap: mix.inputs[6].default_value = src.default_value
            if is_cap: mix.inputs[0].default_value = 1.0
            else:
                yel = nt.nodes.new("ShaderNodeMix"); yel.data_type = "RGBA"; yel.inputs[0].default_value = 0.88; yel.inputs[7].default_value = (0.95, 0.72, 0.04, 1)
                if link: nt.links.new(link, yel.inputs[6])
                else: yel.inputs[6].default_value = src.default_value
                nt.links.new(yel.outputs[2], mix.inputs[6])
                tc = nt.nodes.new("ShaderNodeTexCoord"); sp = nt.nodes.new("ShaderNodeSeparateXYZ"); gt = nt.nodes.new("ShaderNodeMath"); gt.operation = "GREATER_THAN"
                gt.inputs[1].default_value = BONNET_Z
                nt.links.new(tc.outputs["Object"], sp.inputs[0]); nt.links.new(sp.outputs["Z"], gt.inputs[0]); nt.links.new(gt.outputs[0], mix.inputs[0])
            nt.links.new(mix.outputs[2], src)
            bsdf.inputs["Metallic"].default_value = 0.25; bsdf.inputs["Roughness"].default_value = 0.38
            paints.append((m, bsdf))
    return {"root": r, "parts": parts, "paints": paints, "color": color}
def glow(h, frames, color=(1.0, 0.40, 0.04), peak=1.0):
    """named object glows: its own paint colour lit up + orange fresnel rim, then fades (keeps the colour readable)."""
    base = COL[h["color"]]
    for m, bsdf in h["paints"]:
        nt = m.node_tree
        lw = nt.nodes.new("ShaderNodeLayerWeight"); lw.inputs["Blend"].default_value = 0.30
        em = nt.nodes.new("ShaderNodeEmission")
        mx = nt.nodes.new("ShaderNodeMix"); mx.data_type = "RGBA"; mx.inputs[6].default_value = (*base, 1); mx.inputs[7].default_value = (*color, 1)
        nt.links.new(lw.outputs["Fresnel"], mx.inputs[0]); nt.links.new(mx.outputs[2], em.inputs["Color"])
        rim = nt.nodes.new("ShaderNodeMath"); rim.operation = "MULTIPLY_ADD"; rim.inputs[1].default_value = 3.0; rim.inputs[2].default_value = 0.30
        nt.links.new(lw.outputs["Fresnel"], rim.inputs[0])
        st = nt.nodes.new("ShaderNodeMath"); st.operation = "MULTIPLY"; nt.links.new(rim.outputs[0], st.inputs[0]); st.inputs[1].default_value = 0.0
        gtn = next((n for n in nt.nodes if n.type == "MATH" and n.operation == "GREATER_THAN"), None)   # body: glow only where the bonnet paint is (else yellow body blows out to white)
        if gtn is not None:
            mk = nt.nodes.new("ShaderNodeMath"); mk.operation = "MULTIPLY"; nt.links.new(st.outputs[0], mk.inputs[0]); nt.links.new(gtn.outputs[0], mk.inputs[1])
            nt.links.new(mk.outputs[0], em.inputs["Strength"])
        else:
            nt.links.new(st.outputs[0], em.inputs["Strength"])
        out = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL"); surf = out.inputs["Surface"].links[0].from_socket
        ad = nt.nodes.new("ShaderNodeAddShader"); nt.links.new(surf, ad.inputs[0]); nt.links.new(em.outputs[0], ad.inputs[1]); nt.links.new(ad.outputs[0], out.inputs["Surface"])
        f0, f1, f2 = frames
        for f, v in ((f0 - 1, 0.0), (f0, 0.0), (f1, peak), (f1 + 6, peak * 0.7), (f2, 0.0)):
            st.inputs[1].default_value = v; st.inputs[1].keyframe_insert("default_value", frame=f)
