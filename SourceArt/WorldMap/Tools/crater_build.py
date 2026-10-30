"""
Builds /Game/Maps/StarfallCrater from Saved/Crater/crater_v2.json + SourceArt/Regions/StarfallCrater/v2.
Run inside the editor:   py "<this file>" <stage> [stage ...]
Stages: clean import material terrain water foliage rocks outposts emitters save   (or: all)
"""
import json
import math
import os
import random
import sys
import time

import unreal

PROJ = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
V2 = os.path.join(PROJ, "SourceArt/Regions/StarfallCrater/v2")
DATA = json.load(open(os.path.join(PROJ, "Saved/Crater/crater_v2.json")))
ROOT = "/Game/StarfallCrater"
LOG = []

eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
sds = unreal.get_engine_subsystem(unreal.SubobjectDataSubsystem)
tools = unreal.AssetToolsHelpers.get_asset_tools()
reg = unreal.AssetRegistryHelpers.get_asset_registry()
mel = unreal.MaterialEditingLibrary


def log(msg):
    LOG.append(msg)
    unreal.log_warning("CRATER: " + msg)


def find_assets(root, cls, contains):
    out = []
    for a in reg.get_assets_by_path(root, recursive=True):
        if str(a.asset_class_path.asset_name) == cls and all(c in str(a.asset_name) for c in contains):
            out.append(str(a.package_name))
    return sorted(out)


def import_file(src, dest, name):
    t = unreal.AssetImportTask()
    t.filename = src
    t.destination_path = dest
    t.destination_name = name
    t.automated = True
    t.replace_existing = True
    t.save = False
    tools.import_asset_tasks([t])
    return unreal.load_asset(dest + "/" + name)


def new_actor(label, folder, loc=(0, 0, 0)):
    a = eas.spawn_actor_from_class(unreal.Actor, unreal.Vector(*loc))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    return a


def add_component(actor, cls):
    handles = sds.k2_gather_subobject_data_for_instance(actor)
    params = unreal.AddNewSubobjectParams(parent_handle=handles[0], new_class=cls, blueprint_context=None)
    h, fail = sds.add_new_subobject(params)
    data = unreal.SubobjectDataBlueprintFunctionLibrary.get_data(h)
    return unreal.SubobjectDataBlueprintFunctionLibrary.get_object(data)


def xf(x, y, z, yaw=0.0, s=1.0, pitch=0.0, roll=0.0):
    return unreal.Transform(location=unreal.Vector(x, y, z), rotation=unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw),
                            scale=unreal.Vector(s, s, s))


# ---------------------------------------------------------------------------------------------- stages
def stage_clean():
    for a in eas.get_all_level_actors():
        fp = str(a.get_folder_path())
        if fp.startswith("_Test") or fp.startswith("Crater"):
            eas.destroy_actor(a)
    log("cleaned")


def stage_import():
    tdir = os.path.join(V2, "Terrain")
    for t in DATA["tiles"]:
        import_file(os.path.join(tdir, t["name"] + ".obj"), ROOT + "/Terrain", "SM_" + t["name"])
    import_file(os.path.join(V2, "Water/Rivers.obj"), ROOT + "/Water", "SM_Rivers")
    import_file(os.path.join(V2, "Water/Creeks.obj"), ROOT + "/Water", "SM_Creeks")
    for n in LOG_MESHES:
        sm = import_file(os.path.join(V2, "Logs", n + ".obj"), ROOT + "/Logs", n)
        sm.get_editor_property("body_setup").set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
    tex = import_file(os.path.join(V2, "Splat_Packed_RGBA.png"), ROOT + "/Textures", "T_CraterSplat")
    tex.set_editor_property("srgb", False)
    tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    m = unreal.load_asset(ROOT + "/Terrain/SM_" + DATA["tiles"][0]["name"])
    b = m.get_bounding_box()
    log("import ok; tile0 bounds min=(%.0f,%.0f,%.0f) max=(%.0f,%.0f,%.0f)" % (b.min.x, b.min.y, b.min.z, b.max.x, b.max.y, b.max.z))


def sampler_for(tex):
    """Sampler type matching the texture's compression / colour space (shared wrap sampler keeps us under 16)."""
    cs = tex.get_editor_property("compression_settings")
    C = unreal.TextureCompressionSettings
    srgb = tex.get_editor_property("srgb")
    if cs == C.TC_NORMALMAP:
        kind = "NORMAL"
    elif cs == C.TC_MASKS:
        kind = "MASKS"
    elif cs == C.TC_GRAYSCALE:
        kind = "GRAYSCALE" if srgb else "LINEAR_GRAYSCALE"
    elif cs == C.TC_ALPHA:
        kind = "ALPHA"
    else:
        kind = "COLOR" if srgb else "LINEAR_COLOR"
    try:
        if tex.get_editor_property("virtual_texture_streaming"):
            kind = "VIRTUAL_" + kind
    except Exception:
        pass
    return getattr(unreal.MaterialSamplerType, "SAMPLERTYPE_" + kind)


def tex_sample(m, path, uv, x, y, normal=False):
    e = mel.create_material_expression(m, unreal.MaterialExpressionTextureSample, x, y)
    t = unreal.load_asset(path)
    e.set_editor_property("texture", t)
    e.set_editor_property("sampler_type", sampler_for(t))
    e.set_editor_property("sampler_source", unreal.SamplerSourceMode.SSM_WRAP_WORLD_GROUP_SETTINGS)
    if uv is not None:
        mel.connect_material_expressions(uv, "", e, "UVs")
    return e


def custom(m, desc, code, out, inputs, x, y):
    """HLSL Custom node; inputs = [(name, expr, pin)]; out = 1..4 floats."""
    c = mel.create_material_expression(m, unreal.MaterialExpressionCustom, x, y)
    c.set_editor_property("description", desc)
    c.set_editor_property("code", code)
    c.set_editor_property("output_type", getattr(unreal.CustomMaterialOutputType, "CMOT_FLOAT%d" % out))
    ins = []
    for nm, _, _ in inputs:
        ci = unreal.CustomInput()
        ci.set_editor_property("input_name", nm)
        ins.append(ci)
    c.set_editor_property("inputs", ins)
    for nm, src, pin in inputs:
        if not mel.connect_material_expressions(src, pin, c, nm):
            log("WARN custom %s: could not connect %s" % (desc, nm))
    return c


def new_material(path):
    folder, name = path.rsplit("/", 1)
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        m = unreal.load_asset(path)
        mel.delete_all_material_expressions(m)
        for e in list(mel.get_material_expressions(m)):          # UE 5.8 leaves Custom nodes behind; stale copies break compiles
            mel.delete_material_expression(m, e)
        return m
    return tools.create_asset(name, folder, unreal.Material, unreal.MaterialFactoryNew())


def world_pos(m, x, y, camera_relative=False):
    wp = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, x, y)
    if camera_relative:
        W = unreal.WorldPositionIncludedOffsets
        mode = getattr(W, "WPT_CAMERA_RELATIVE_WORLD_POSITION", None) or getattr(W, "WPT_CAMERA_RELATIVE", None)
        wp.set_editor_property("world_position_shader_offset", mode)
    return wp


def mask(m, src, chans, x, y):
    e = mel.create_material_expression(m, unreal.MaterialExpressionComponentMask, x, y)
    for c in "rgba":
        e.set_editor_property(c, c in chans)
    mel.connect_material_expressions(src, "", e, "")
    return e


def div(m, src, k, x, y):
    d = mel.create_material_expression(m, unreal.MaterialExpressionDivide, x, y)
    mel.connect_material_expressions(src, "", d, "A")
    if isinstance(k, tuple):
        kv = mel.create_material_expression(m, unreal.MaterialExpressionConstant2Vector, x - 150, y + 60)
        kv.set_editor_property("r", k[0]); kv.set_editor_property("g", k[1])
        mel.connect_material_expressions(kv, "", d, "B")
    else:
        d.set_editor_property("const_b", k)
    return d


def stage_material():
    """Crater floor on Megascans surfaces: forest floor / clover / mossy ground / muddy ground, gravel bump on all dry ground,
    noise-broken blends, triplanar mossy cliffs, damp sheen and puddles in the mud."""
    for key in ("A", "B"):
        tex = import_file(os.path.join(V2, "Splat_Mask_%s.png" % key), ROOT + "/Textures", "T_CraterMask_" + key)
        tex.set_editor_property("srgb", False)
        tex.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    gn = import_file(os.path.join(V2, "Gravel", "T_GravelBump_N.png"), ROOT + "/Textures", "T_GravelBump_N")
    gn.set_editor_property("srgb", False)
    gn.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    gm = import_file(os.path.join(V2, "Gravel", "T_GravelBump_M.png"), ROOT + "/Textures", "T_GravelBump_M")
    gm.set_editor_property("srgb", False)
    gm.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_MASKS)
    en = import_file(os.path.join(V2, "Erosion", "T_ErosionNormal.png"), ROOT + "/Textures", "T_ErosionNormal")
    en.set_editor_property("srgb", False)
    en.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_NORMALMAP)
    m = new_material(ROOT + "/Materials/M_CraterTerrain")
    MS = "/Game/Fab/Megascans/Surfaces/"
    def surf(folder, tid, res, kind):
        for a in reg.get_assets_by_path(MS + folder, recursive=True):
            if str(a.asset_name) == "T_%s_%s_%s" % (tid, res, kind):
                return str(a.package_name)
        raise RuntimeError("missing surface texture %s %s" % (tid, kind))
    FOREST, WILD = ("Forest_Floor_sfjmafua", "sfjmafua", "4K"), ("Wild_Grass_sfknaeoa", "sfknaeoa", "4K")
    CLOVER, MOSSY = ("Clover_Patches_on_Grass_sgmkajak", "sgmkajak", "2K"), ("Mossy_Rocky_Ground_vcqhcig", "vcqhcig", "2K")
    GRAVEL, STEPPE = ("Gravel_Ground_vi0maebg", "vi0maebg", "4K"), ("Rocky_Steppe_ulgmbhwn", "ulgmbhwn", "2K")
    MUD = "/Game/MuddyGroundPack/Textures/"
    JT = "/Game/JustBStudios/PostApo/Textures/"
    NOISE = "/Engine/MaterialTemplates/Textures/T_Noise01"
    wp = world_pos(m, -3000, 0)
    xy = mask(m, wp, "rg", -2800, 0)
    xz = mask(m, wp, "rb", -2800, 200)
    yz = mask(m, wp, "gb", -2800, 400)
    P = world_pos(m, -3000, 600, camera_relative=True)
    org = mel.create_material_expression(m, unreal.MaterialExpressionConstant2Vector, -3000, 900)
    org.set_editor_property("r", DATA["origin_cm"][0]); org.set_editor_property("g", DATA["origin_cm"][1])
    size = mel.create_material_expression(m, unreal.MaterialExpressionConstant2Vector, -3000, 1050)
    size.set_editor_property("r", 4032 * 160.0); size.set_editor_property("g", 3024 * 160.0)
    sub = mel.create_material_expression(m, unreal.MaterialExpressionSubtract, -2800, 900)
    mel.connect_material_expressions(xy, "", sub, "A"); mel.connect_material_expressions(org, "", sub, "B")
    muv = mel.create_material_expression(m, unreal.MaterialExpressionDivide, -2650, 950)
    mel.connect_material_expressions(sub, "", muv, "A"); mel.connect_material_expressions(size, "", muv, "B")
    mA = tex_sample(m, ROOT + "/Textures/T_CraterMask_A", muv, -2400, 900)
    mB = tex_sample(m, ROOT + "/Textures/T_CraterMask_B", muv, -2400, 1150)
    nMac = tex_sample(m, NOISE, div(m, xy, 9000.0, -2600, 1400), -2400, 1400)
    nDet = tex_sample(m, NOISE, div(m, xy, 900.0, -2600, 1650), -2400, 1650)
    S = {}
    rows = [("base", surf(*FOREST, "B"), 420.0), ("base2", surf(*WILD, "B"), 950.0), ("baseN", surf(*FOREST, "N"), 420.0),
            ("grass", surf(*CLOVER, "B"), 320.0), ("grass2", "/Game/PN_GrassLibrary/Textures/LandscapeTextures/ground_VII_albedo", 680.0),
            ("grassN", surf(*CLOVER, "N"), 320.0),
            ("moss", surf(*MOSSY, "B"), 360.0), ("moss2", JT + "T_Ground_Moss_B", 540.0), ("mossN", surf(*MOSSY, "N"), 360.0),
            ("mud", MUD + "T_MuddyGround_4K_Albedo", 460.0), ("mudN", MUD + "T_MuddyGround_4K_Normal", 460.0),
            ("path", surf(*GRAVEL, "B"), 240.0), ("pathN", surf(*GRAVEL, "N"), 240.0),
            ("grav", surf(*GRAVEL, "B"), 210.0), ("gravN", surf(*GRAVEL, "N"), 210.0),
            ("bumpN", ROOT + "/Textures/T_GravelBump_N", 95.0), ("bumpM", ROOT + "/Textures/T_GravelBump_M", 95.0)]
    yy = -2400
    for key, tp, sc in rows:
        S[key] = tex_sample(m, tp, div(m, xy, sc, -2200, yy), -2000, yy)
        yy += 230
    for key, src in (("rxy", xy), ("rxz", xz), ("ryz", yz)):
        S[key] = tex_sample(m, surf(*STEPPE, "B"), div(m, src, 1400.0, -2200, yy), -2000, yy)
        yy += 230
    S["rockN"] = tex_sample(m, surf(*STEPPE, "N"), div(m, xz, 1400.0, -2200, yy), -2000, yy); yy += 230
    S["sxz"] = tex_sample(m, NOISE, div(m, xz, (2600.0, 26000.0), -2200, yy), -2000, yy); yy += 230
    S["syz"] = tex_sample(m, NOISE, div(m, yz, (2600.0, 26000.0), -2200, yy), -2000, yy); yy += 230
    # user's erosion normal map: ridge/gully relief on the floor (two scales, second one axis-swapped to hide the repeat) and on the walls
    yx = mask(m, wp, "rg", -2800, 1900)
    swap = custom(m, "SwapXY", "return float2(v.y, v.x);", 2, [("v", div(m, yx, 1310000.0, -2650, 1900), "")], -2400, 1900)
    ERO = ROOT + "/Textures/T_ErosionNormal"
    S["eF1"] = tex_sample(m, ERO, div(m, xy, 808000.0, -2200, yy), -2000, yy); yy += 230
    S["eF2"] = tex_sample(m, ERO, swap, -2000, yy); yy += 230
    S["eXZ"] = tex_sample(m, ERO, div(m, xz, 600000.0, -2200, yy), -2000, yy); yy += 230
    S["eYZ"] = tex_sample(m, ERO, div(m, yz, 600000.0, -2200, yy), -2000, yy); yy += 230
    ero = custom(m, "ErosionNormal", """
float3 n = abs(normalize(cross(ddx(P), ddy(P))));
float3 w = n*n*n; w /= (w.x+w.y+w.z);
float3 fl = lerp(f1, f2, saturate((nM-0.35)*2.5));
float3 side = eyz*w.x + exz*w.y + fl*w.z;
return float3(side.xy, 0);""", 3, [("f1", S["eF1"], "RGB"), ("f2", S["eF2"], "RGB"), ("exz", S["eXZ"], "RGB"), ("eyz", S["eYZ"], "RGB"),
                                     ("nM", nMac, "R"), ("P", P, "")], -1600, 1700)
    up = custom(m, "Up", "float3 n = normalize(cross(ddx(P), ddy(P))); return abs(n.z);", 1, [("P", P, "")], -1600, 600)
    W = custom(m, "LayerWeights", """
float g1 = saturate(((2*mA.b-1) + 0.8*(nD-0.5) + 0.5*(nM-0.5))*3 + 0.5);
float g2 = saturate((nM-0.5)*2.5) * 0.3 * saturate(1-mA.r*2) * saturate(1-mA.g*2) * saturate(1-mB.r*2);
float m1 = saturate(((2*mB.g-1) + 0.9*(nD-0.5) + 0.4*(nM-0.5))*3 + 0.5);
float m2 = saturate((0.75-nM)*2.5) * 0.85 * saturate(1-mA.g*2) * saturate(1-mB.r*1.5) * saturate(1-mA.r*1.5);
float wet = saturate(((2*mB.r-1) + 0.7*(nD-0.5))*3 + 0.5);
wet = max(wet, saturate((nM-0.52)*3.5) * saturate((0.55-nD)*3) * 0.9 * saturate(1-mA.g*2) * saturate(1-mA.r*2));
float p = saturate(((2*mA.g-1) + 0.6*(nD-0.5))*2.5 + 0.5);
float flat = saturate((up - 0.86) * 8);
float g = max(g1, g2) * flat;
float mo = max(max(m1, m2), max(g1, g2) * (1 - flat) * 0.85);
return float4(g, mo, wet, p);""", 4,
               [("mA", mA, "RGB"), ("mB", mB, "RGB"), ("nM", nMac, "R"), ("nD", nDet, "R"), ("up", up, "")], -1600, 900)
    R = custom(m, "RockWeight", "return saturate(((2*mA.r-1) + 0.5*(nD-0.5))*3 + 0.5);", 1, [("mA", mA, "RGB"), ("nD", nDet, "R")], -1600, 1100)
    tri = custom(m, "TriplanarRock", """
float3 n = abs(normalize(cross(ddx(P), ddy(P))));
float3 w = n*n; w /= (w.x+w.y+w.z);
return ayz*w.x + axz*w.y + axy*w.z;""", 3, [("axy", S["rxy"], "RGB"), ("axz", S["rxz"], "RGB"), ("ayz", S["ryz"], "RGB"), ("P", P, "")], -1600, 1300)
    streak = custom(m, "MossStreaks", """
float3 n = abs(normalize(cross(ddx(P), ddy(P))));
return (syz*n.x + sxz*n.y) / (n.x + n.y + 1e-4);""", 1, [("sxz", S["sxz"], "R"), ("syz", S["syz"], "R"), ("P", P, "")], -1600, 1500)
    wet = custom(m, "Wetness", """
float flat = saturate((up - 0.9) * 10);
float damp = saturate(0.15 + W.z + W.y*0.3) * (1 - R*0.6);
float puddle = saturate((W.z-0.4)*4) * saturate((0.52-nD)*5) * flat;
return float2(damp, puddle);""", 2, [("W", W, ""), ("R", R, ""), ("nD", nDet, "R"), ("nM", nMac, "R"), ("up", up, "")], -1350, 1200)
    # gravel: wherever there is no water/mud/rock the ground is stony -- strong bump everywhere dry, gravel albedo in patches
    grav = custom(m, "Gravel", """
float dry = (1 - W.z) * (1 - wt.y) * (1 - R) * (1 - W.y*0.45);
float patch = saturate((nM*0.6 + nD*0.8 - 0.5)*3);
return float2(dry * (0.6 + 0.4*patch), dry * patch * 0.8);""", 2,
                  [("W", W, ""), ("R", R, ""), ("wt", wet, ""), ("nM", nMac, "R"), ("nD", nDet, "R")], -1350, 1400)
    col = custom(m, "BlendColor", """
float3 b = lerp(lerp(base, base2, 0.35) * 0.82, mud * float3(0.62, 0.55, 0.45), 0.3);
float3 g = lerp(grass, grass2 * float3(0.6, 0.7, 0.45), saturate((nD-0.45)*2)) * 0.85;
float3 c = lerp(b, g, W.x);
float3 mo = lerp(moss, moss2 * float3(0.55, 0.8, 0.4), saturate((nD-0.4)*3));
c = lerp(c, mo, W.y);
float3 md = lerp(mud * 0.75, mo * 0.7, saturate((0.6 - W.z)*2) * 0.5);
c = lerp(c, md, W.z);
c = lerp(c, gr * 0.85, gv.y);
c = lerp(c, path * 0.8, W.w);
c *= lerp(1.0, saturate(cav * 1.6), gv.x * 0.55);
float rm = saturate((st-0.5)*3)*0.6 + saturate((up-0.72)*4)*0.7;
float3 rk = lerp(rock, mo * 0.8, saturate(rm));
c = lerp(c, rk, R);
c *= lerp(1.0, 0.76, wt.x);
c = lerp(c, float3(0.035, 0.045, 0.04), wt.y * 0.85);
return c * lerp(0.82, 1.08, nM);""", 3,
                 [("base", S["base"], "RGB"), ("base2", S["base2"], "RGB"), ("grass", S["grass"], "RGB"), ("grass2", S["grass2"], "RGB"),
                  ("moss", S["moss"], "RGB"), ("moss2", S["moss2"], "RGB"), ("mud", S["mud"], "RGB"), ("path", S["path"], "RGB"),
                  ("gr", S["grav"], "RGB"), ("cav", S["bumpM"], "R"), ("rock", tri, ""),
                  ("W", W, ""), ("R", R, ""), ("nD", nDet, "R"), ("nM", nMac, "R"), ("st", streak, ""), ("up", up, ""), ("wt", wet, ""),
                  ("gv", grav, "")], -1100, 600)
    nrm = custom(m, "BlendNormal", """
float3 n = lerp(nb, ng, W.x); n = lerp(n, nm, W.y); n = lerp(n, nu, W.z*0.7); n = lerp(n, np, W.w); n = lerp(n, nr, R);
// gravel detail: whiteout-blend the generated pebble bump (and the scanned gravel normal in the gravel patches)
n = normalize(float3(n.xy + bn.xy * gv.x * 0.9 + gn.xy * gv.y * 1.1, n.z));
n = normalize(float3(n.xy + er.xy * lerp(1.8 * (1 - wt.y) * (1 - W.z*0.5), 2.4, R), n.z));      // erosion relief, strongest on the walls
n = lerp(n, float3(0,0,1), saturate(W.z*0.4 + wt.y));
return normalize(n);""", 3,
                 [("nb", S["baseN"], "RGB"), ("ng", S["grassN"], "RGB"), ("nm", S["mossN"], "RGB"), ("nu", S["mudN"], "RGB"),
                  ("np", S["pathN"], "RGB"), ("nr", S["rockN"], "RGB"), ("bn", S["bumpN"], "RGB"), ("gn", S["gravN"], "RGB"), ("er", ero, ""),
                  ("W", W, ""), ("R", R, ""), ("wt", wet, ""), ("gv", grav, "")], -1100, 900)
    rough = custom(m, "Roughness", "float r = lerp(lerp(0.9, 0.4, W.z), 0.8, R); r = lerp(r, 0.3, wt.x*0.75); return lerp(r, 0.1, wt.y);", 1,
                   [("W", W, ""), ("R", R, ""), ("wt", wet, "")], -1100, 1100)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.recompile_material(m)
    stage_watermat()
    log("materials ok")


def stage_watermat():
    wpth = ROOT + "/Materials/MI_CraterWater"
    if unreal.EditorAssetLibrary.does_asset_exist(wpth):
        mi = unreal.load_asset(wpth)
    else:
        mi = tools.create_asset("MI_CraterWater", ROOT + "/Materials", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
        mi.set_editor_property("parent", unreal.load_asset("/Game/JustBStudios/PostApo/Materials/MM_Water"))
    # deep jungle-river green, rougher surface so it stops mirroring the sky white from above
    mel.set_material_instance_vector_parameter_value(mi, "WaterColor1", unreal.LinearColor(0.015, 0.06, 0.045, 1))
    mel.set_material_instance_vector_parameter_value(mi, "WaterColor2", unreal.LinearColor(0.03, 0.11, 0.08, 1))
    mel.set_material_instance_scalar_parameter_value(mi, "Rough1", 0.12)
    mel.set_material_instance_scalar_parameter_value(mi, "Rough2", 0.2)


def stage_terrain():
    mat = unreal.load_asset(ROOT + "/Materials/M_CraterTerrain")
    for t in DATA["tiles"]:
        sm = unreal.load_asset(ROOT + "/Terrain/SM_" + t["name"])
        sm.set_material(0, mat)
        body = sm.get_editor_property("body_setup")
        body.set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        ns = sm.get_editor_property("nanite_settings")
        ns.enabled = True
        sm.set_editor_property("nanite_settings", ns)
        a = eas.spawn_actor_from_object(sm, unreal.Vector(*t["loc"]))
        a.set_actor_label("Terrain_" + t["name"])
        a.set_folder_path("Crater/Terrain")
    log("terrain placed: %d tiles" % len(DATA["tiles"]))


def stage_water():
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Water"):
            eas.destroy_actor(a)
    stage_watermat()
    for n in ("SM_Rivers", "SM_Creeks"):
        sm = unreal.load_asset(ROOT + "/Water/" + n)
        wm = ROOT + "/Materials/M_LakeWater"
        sm.set_material(0, unreal.load_asset(wm if unreal.EditorAssetLibrary.does_asset_exist(wm) else ROOT + "/Materials/MI_CraterWater"))
        a = eas.spawn_actor_from_object(sm, unreal.Vector(DATA["origin_cm"][0], DATA["origin_cm"][1], 0))
        a.set_actor_label("Water_" + n[3:])
        a.set_folder_path("Crater/Water")
        a.get_component_by_class(unreal.StaticMeshComponent).set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    log("water placed (rivers + creeks/lakes)")


MP = "/Game/Megaplant_Library"
LOG_MESHES = ["SM_Log_A", "SM_Log_B", "SM_Log_C", "SM_Log_D"]
SKINNED = {
    "SK_Alder": find_assets(MP + "/Tree_Black_Alder", "SkeletalMesh", ["Tree_Black_Alder_01_"]),
    "SK_Willow": find_assets(MP + "/Tree_Goat_Willow", "SkeletalMesh", ["Tree_Goat_Willow_01_"]),
    "SK_Elder": find_assets(MP + "/Tree_Elder", "SkeletalMesh", ["Tree_Elder_01_"]),
    "SK_Spruce": find_assets(MP + "/Tree_Norway_Spruce", "SkeletalMesh", ["Tree_Norway_Spruce_01_"]),
    "SK_Spindle": find_assets(MP + "/Shrub_European_Spindle", "SkeletalMesh", ["Shrub_European_Spindle_01_"]),
    "SK_Bilberry": find_assets(MP + "/Plant_Bilberry", "SkeletalMesh", ["Plant_Bilberry_01_"]),
    "SK_Lingonberry": find_assets(MP + "/Plant_Lingonberry", "SkeletalMesh", ["Plant_Lingonberry_01_"]),
    "SK_Reeds": find_assets(MP + "/Plant_Dry_Common_Reeds", "SkeletalMesh", ["Plant_Dry_Common_Reed_"]),
}
SKINNED["SK_Alder_Rim"] = SKINNED["SK_Alder"]
JB = "/Game/JustBStudios/PostApo/Meshes/"
STATIC = {
    "ST_PNGrass": [p for p in find_assets("/Game/PN_GrassLibrary", "StaticMesh", ["rass_"]) if p.endswith(("_01_mesh", "_02_mesh", "_01_SM"))],
    "ST_WildGrass_MS": find_assets("/Game/Fab/Megascans/Plants/Wild_Grass_vlkhcbxia", "StaticMesh", ["SM_"]),
    "ST_WildGrass_JB": [JB + n for n in ("SM_WildGrass_L_01", "SM_WildGrass_M_01", "SM_WildGrass_M_02", "SM_WildGrass_S_01", "SM_WildGrass_S_02", "SM_WildGrass_S_03")],
    "ST_Sorrel": find_assets("/Game/Fab/Megascans/Plants/Violet_Wood_Sorrel_uchkajuia", "StaticMesh", ["SM_"]),
    "ST_DeadShrub": find_assets("/Game/Fab/Megascans/Plants/Dead_Shrubs_vdknafgha", "StaticMesh", ["SM_"]),
    "ST_DryBush": [JB + "SM_DryBush_01_Short", JB + "SM_DryBush_02"],
    "ST_CypressRoots": ["/Game/Fab/Photorealistic_Swamp_Cypress_Roots_-_Nanite_Ready__Free_/SM_SwampCypress_A"],
    "ST_RockSmall": [JB + "SM_Rock_0%d" % i for i in range(1, 7)],
    "ST_RockBoulder": [JB + "SM_Rock_0%d" % i for i in (1, 2, 3, 5)],
    "ST_MossRock": [JB + "SM_Rock_0%d" % i for i in range(1, 7)],
    "ST_MossBoulder": [JB + "SM_Rock_0%d" % i for i in (1, 2, 3, 4, 5)],
    "ST_Log": [ROOT + "/Logs/" + n for n in LOG_MESHES],
    "ST_Fern": find_assets("/Game/PN_Fern/Meshes", "StaticMesh", ["fern_"]),
}
MOSSY = {"ST_RockSmall", "ST_RockBoulder", "ST_MossRock", "ST_MossBoulder"}
CULL = {"ST_Fern": 16000, "ST_MossRock": 30000, "ST_PNGrass": 9000, "ST_WildGrass_MS": 12000, "ST_WildGrass_JB": 12000, "ST_Sorrel": 7000, "ST_DeadShrub": 20000,
        "ST_DryBush": 20000, "SK_Bilberry": 9000, "SK_Lingonberry": 9000, "SK_Reeds": 15000, "SK_Spindle": 25000}
NO_COLLISION = {"ST_Fern", "ST_PNGrass", "ST_WildGrass_MS", "ST_WildGrass_JB", "ST_Sorrel", "ST_DeadShrub", "ST_DryBush"}
NO_SHADOW = {"ST_PNGrass", "ST_Sorrel", "ST_WildGrass_MS"}


FOLIAGE_CHUNK_CM = 19200.0      # one foliage actor per 192 m chunk: fits inside a 256 m World Partition cell, so it streams with it


def stage_foliage(only=None):
    rnd = random.Random(5)
    folder = "Crater/Foliage"
    C = FOLIAGE_CHUNK_CM
    cells = {}
    for group, pts in DATA["foliage"].items():
        if only and group not in only:
            continue
        meshes = SKINNED.get(group) or STATIC.get(group) or []
        if not meshes or not pts:
            log("skip %s (meshes=%d pts=%d)" % (group, len(meshes), len(pts)))
            continue
        for p in pts:
            m = meshes[rnd.randrange(len(meshes))]
            cells.setdefault((int(p[0] // C), int(p[1] // C)), {}).setdefault((group, m), []).append(p)
        log("foliage %s: %d instances over %d meshes" % (group, len(pts), len(meshes)))
    n_comp = 0
    for (cx, cy), parts in sorted(cells.items()):
        actor = new_actor("Foliage_%d_%d" % (cx, cy), folder, ((cx + 0.5) * C, (cy + 0.5) * C, 0))
        for (group, mpath), bp in sorted(parts.items()):
            asset = unreal.load_asset(mpath)
            if group.startswith("SK_"):
                comp = add_component(actor, unreal.InstancedSkinnedMeshComponent)
                comp.set_skinned_asset_and_update(asset)
                for x, y, z, yaw, s in bp:
                    comp.add_instance(xf(x, y, z - 20, yaw, s), 0, True)
            else:
                comp = add_component(actor, unreal.HierarchicalInstancedStaticMeshComponent)
                comp.set_static_mesh(asset)
                sink = 40 if "Rock" in group else 5
                if group == "ST_Log":
                    comp.add_instances([xf(r[0], r[1], r[2], r[3], r[4], pitch=r[5], roll=r[6]) for r in bp], False, True)
                    for i in range(comp.get_num_materials()):
                        comp.set_material(i, mossy_log_mi())
                else:
                    comp.add_instances([xf(x, y, z - sink * s, yaw, s, pitch=(rnd.uniform(-14, 14) if "Rock" in group else 0)) for x, y, z, yaw, s in (r[:5] for r in bp)], False, True)
                if group in MOSSY:
                    for i in range(comp.get_num_materials()):
                        comp.set_material(i, mossy_mi_for(asset))
                if group in NO_COLLISION:
                    comp.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
                if group in NO_SHADOW:
                    comp.set_cast_shadow(False)
            if group in CULL:
                comp.set_editor_property("instance_end_cull_distance", CULL[group])
            n_comp += 1
    log("foliage chunks: %d actors, %d components" % (len(cells), n_comp))


def place(mesh, x, y, z, yaw=0.0, s=(1, 1, 1), folder="Crater/Outposts", label=None, pitch=0.0, roll=0.0):
    a = eas.spawn_actor_from_object(unreal.load_asset(mesh), unreal.Vector(x, y, z))
    a.set_actor_rotation(unreal.Rotator(roll=roll, pitch=pitch, yaw=yaw), False)
    a.set_actor_scale3d(unreal.Vector(*s))
    a.set_folder_path(folder)
    if label:
        a.set_actor_label(label)
    return a


def stage_rocks():
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Rocks_Outcrops"):
            eas.destroy_actor(a)
    for i, r in enumerate(DATA["big_rocks"]):
        a = place(JB + r["mesh"], *r["loc"], yaw=r["yaw"], s=(r["scale"],) * 3, folder="Crater/Rocks_Outcrops", label="Outcrop_%02d" % i)
        c = a.get_component_by_class(unreal.StaticMeshComponent)
        for k in range(c.get_num_materials()):
            c.set_material(k, mossy_mi_for(c.static_mesh))
    log("outcrops: %d" % len(DATA["big_rocks"]))


def hut(cx, cy, z, yaw, folder, rnd, tag):
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    def P(lx, ly):
        return cx + lx * ca - ly * sa, cy + lx * sa + ly * ca
    for ix in (-1, 1):
        for iy in (-1, 1):
            x, y = P(ix * 128, iy * 128)
            place(JB + "SM_Floor_01", x, y, z + 45, yaw, folder=folder)
    for ix in (-1, 1):
        for iy in (-1, 1):
            x, y = P(ix * 245, iy * 245)
            place(JB + "SM_Plank_06", x, y, z + 145, yaw, pitch=90, folder=folder)
    x, y = P(0, 0)
    place(JB + "SM_Cloth_01", x, y, z + 300, yaw + rnd.uniform(-6, 6), s=(1.95, 1.95, 1.6), folder=folder, label=tag + "_Roof")
    x, y = P(0, 256)
    place(JB + "SM_Railing_01", x, y, z + 55, yaw, folder=folder)
    x, y = P(-300, 0)
    place(JB + "SM_Stairs_02", x, y, z + 20, yaw + 90, s=(0.6, 0.6, 0.6), folder=folder)
    for k in range(rnd.randint(2, 4)):
        x, y = P(rnd.uniform(-220, 220), rnd.uniform(-220, 220))
        place(JB + rnd.choice(["SM_Box_01", "SM_Box_02", "SM_Box_03", "SM_Barrel", "SM_PaletteBoxes_01"]), x, y, z + 63, rnd.uniform(0, 360), folder=folder)


RUIN_MESHES = ["SM_Ruin_Wall6", "SM_Ruin_WallLow", "SM_Ruin_WallArch", "SM_Ruin_Corner", "SM_Ruin_Column", "SM_Ruin_ColumnBroken",
               "SM_Ruin_ColumnFallen", "SM_Ruin_Rubble", "SM_Ruin_Floor"]


def ruin_mi():
    """Mossy cut stone: the moss master with the JB rock textures (moss climbs every upward face of every block)."""
    path = ROOT + "/Materials/Mossy/MI_Mossy_RuinStone"
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = tools.create_asset("MI_Mossy_RuinStone", ROOT + "/Materials/Mossy", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", unreal.load_asset(ROOT + "/Materials/M_MossyMaster"))
    mel.set_material_instance_texture_parameter_value(mi, "BaseColor", unreal.load_asset(JB.replace("Meshes/", "Textures/") + "T_Rock03_B"))
    mel.set_material_instance_texture_parameter_value(mi, "Normal", unreal.load_asset(JB.replace("Meshes/", "Textures/") + "T_Rock03_N"))
    mel.set_material_instance_scalar_parameter_value(mi, "MossAmount", 1.0)
    return mi


def stage_ruins():
    """Import the procedural ruin pieces and place every site from the generator (mossy stone, full collision)."""
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Ruins"):
            eas.destroy_actor(a)
    mi = ruin_mi()
    for n in RUIN_MESHES:
        sm = import_file(os.path.join(V2, "Ruins", n + ".obj"), ROOT + "/Ruins", n)
        sm.get_editor_property("body_setup").set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        sm.set_material(0, mi)
    for i, r in enumerate(DATA["ruins"]):
        place(ROOT + "/Ruins/" + r["mesh"], *r["loc"], yaw=r["yaw"], s=(r["scale"],) * 3, pitch=r.get("pitch", 0.0), roll=r.get("roll", 0.0),
              folder="Crater/Ruins", label="Ruin_%03d_%s" % (i, r["mesh"][8:]))
    log("ruins: %d pieces" % len(DATA["ruins"]))


def stage_outposts():
    """Camps are now just a clearing with the Medieval Campfire asset (flames + warm light added); no generated huts or bridges."""
    for a in eas.get_all_level_actors():
        fp = str(a.get_folder_path())
        if fp.startswith(("Crater/Outposts", "Crater/Bridges", "Crater/Campfires")) or isinstance(a, unreal.PlayerStart):
            eas.destroy_actor(a)
    for i, (x, y, z, yaw) in enumerate(DATA["campfires"]):
        place("/Game/Medieval_Campfire/Campfire", x, y, z - 5, yaw, s=(1.3, 1.3, 1.3), folder="Crater/Campfires", label="Campfire_%02d" % i)
        light = eas.spawn_actor_from_class(unreal.PointLight, unreal.Vector(x, y, z + 110))
        light.set_folder_path("Crater/Campfires")
        light.set_actor_label("Campfire_%02d_Light" % i)
        lc = light.get_component_by_class(unreal.PointLightComponent)
        lc.set_intensity(22000.0); lc.set_light_color(unreal.LinearColor(1.0, 0.45, 0.15, 1)); lc.set_attenuation_radius(3200.0)
        sp(lc, "volumetric_scattering_intensity", 2.0)
    b = DATA["outposts"]["Breach Gate"]
    pl = eas.spawn_actor_from_class(unreal.PlayerStart, unreal.Vector(b[0], b[1] + 600, b[2] + 120))
    pl.set_actor_rotation(unreal.Rotator(0, 0, -90), False)
    pl.set_folder_path("Crater")
    log("campfires: %d" % len(DATA["campfires"]))


def stage_bridges():
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Bridges"):
            eas.destroy_actor(a)
    for i, b in enumerate(DATA["bridges"]):
        ax_, ay, az = b["a"]; bx, by, bz = b["b"]
        L = math.hypot(bx - ax_, by - ay); yaw = math.degrees(math.atan2(by - ay, bx - ax_))
        n = max(2, int(L / 130))
        folder = "Crater/Bridges/Bridge_%02d" % i
        for k in range(n + 1):
            t = k / n
            x, y = ax_ + (bx - ax_) * t, ay + (by - ay) * t
            z = az + (bz - az) * t + 80 + math.sin(t * math.pi) * 120
            place(JB + "SM_Floor_02", x, y, z, yaw + 90, folder=folder)
            if k % 2 == 0:
                for side in (-1, 1):
                    ox, oy = -math.sin(math.radians(yaw)) * 110 * side, math.cos(math.radians(yaw)) * 110 * side
                    place(JB + "SM_Railing_01", x + ox, y + oy, z + 5, yaw, folder=folder)
    log("bridges: %d" % len(DATA["bridges"]))


def stage_redress_clean():
    """Remove everything that depends on the generated layout (keeps terrain, water, outcrops, lighting)."""
    n = 0
    for a in eas.get_all_level_actors():
        fp = str(a.get_folder_path())
        if fp.startswith(("Crater/Foliage", "Crater/Outposts", "Crater/Emitters", "Crater/FX", "Crater/Bridges", "Crater/Ruins", "Crater/Campfires", "Crater/Towns")) \
                or isinstance(a, unreal.PlayerStart):
            eas.destroy_actor(a)
            n += 1
    log("redress_clean removed %d actors" % n)


def stage_emitters():
    water = unreal.load_asset(ROOT + "/Materials/MI_CraterWater")
    fog = unreal.load_asset("/Game/JustBStudios/PostApo/Materials/MM_Fog")
    for e in DATA["emitters"]:
        t = e["type"]
        if t in ("Waterfall", "Mist"):   # visuals come from the Niagara fx stage; only markers here
            pass
        elif t == "Waterfall":
            tx, ty, tz = e["top"]; bx, by, bz = e["base"]
            dx, dy, dz = bx - tx, by - ty, bz - tz
            L = math.sqrt(dx * dx + dy * dy + dz * dz)
            yaw = math.degrees(math.atan2(dy, dx)); pitch = math.degrees(math.atan2(-dz, math.hypot(dx, dy)))
            a = place("/Engine/BasicShapes/Cube", (tx + bx) / 2, (ty + by) / 2, (tz + bz) / 2, yaw, s=(L / 100, 14, 0.6), pitch=-pitch,
                      folder="Crater/Emitters/Waterfalls", label="Waterfall_" + e["name"])
            c = a.get_component_by_class(unreal.StaticMeshComponent)
            c.set_material(0, water); c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
        elif t == "Mist":
            x, y, z = e["loc"]; r = e["radius"]
            for k in range(3):
                a = place("/Engine/BasicShapes/Plane", x + random.uniform(-r, r) * 0.3, y + random.uniform(-r, r) * 0.3, z + k * 900,
                          random.uniform(0, 360), s=(r / 50, r / 50, 1), folder="Crater/Emitters/Mist", label="Mist_%s_%d" % (e["name"], k))
                c = a.get_component_by_class(unreal.StaticMeshComponent)
                c.set_material(0, fog); c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION); c.set_cast_shadow(False)
        tp = eas.spawn_actor_from_class(unreal.TargetPoint, unreal.Vector(*(e.get("base") or e["loc"])))
        tp.set_actor_label("Emitter_%s_%s" % (t, e["name"]))
        tp.set_folder_path("Crater/Emitters/Markers")
        tp.tags = [unreal.Name("Emitter"), unreal.Name("Emitter_" + t)]
    log("emitters: %d" % len(DATA["emitters"]))


def stage_retile():
    """Re-import the terrain/river meshes in place (actors keep their references) and re-apply settings."""
    stage_import()
    mat = unreal.load_asset(ROOT + "/Materials/M_CraterTerrain")
    for t in DATA["tiles"]:
        sm = unreal.load_asset(ROOT + "/Terrain/SM_" + t["name"])
        sm.set_material(0, mat)
        sm.get_editor_property("body_setup").set_editor_property("collision_trace_flag", unreal.CollisionTraceFlag.CTF_USE_COMPLEX_AS_SIMPLE)
        ns = sm.get_editor_property("nanite_settings")
        ns.enabled = True
        sm.set_editor_property("nanite_settings", ns)
    for n in ("SM_Rivers", "SM_Creeks"):
        unreal.load_asset(ROOT + "/Water/" + n).set_material(0, unreal.load_asset(ROOT + "/Materials/MI_CraterWater"))
    if unreal.EditorAssetLibrary.does_asset_exist(ROOT + "/Materials/M_LakeWater"):
        unreal.load_asset(ROOT + "/Water/SM_Creeks").set_material(0, unreal.load_asset(ROOT + "/Materials/M_LakeWater"))
    log("retiled %d terrain meshes" % len(DATA["tiles"]))


def stage_fx():
    """Swap the stand-in waterfall sheets / mist cards for Niagara systems."""
    for a in eas.get_all_level_actors():
        fp = str(a.get_folder_path())
        if fp.startswith("Crater/Emitters/Waterfalls") or fp.startswith("Crater/Emitters/Mist") or fp.startswith("Crater/FX"):
            eas.destroy_actor(a)
    FX = {k: unreal.load_asset("/Game/StarfallCrater/FX/" + k) for k in
          ("NS_Crater_Waterfall", "NS_Crater_Spray", "NS_Crater_Mist", "NS_Crater_GroundMist", "NS_Crater_Campfire", "NS_Crater_Fireflies")}

    def fx(sysname, loc, folder, label, yaw=0.0):
        a = eas.spawn_actor_from_object(FX[sysname], unreal.Vector(*loc))
        a.set_actor_rotation(unreal.Rotator(0, 0, yaw), False)
        a.set_actor_label(label)
        a.set_folder_path(folder)
        return a
    n = 0
    for e in DATA["emitters"]:
        t = e["type"]
        if t == "Waterfall":
            tx, ty, tz = e["top"]; bx, by, bz = e["base"]
            yaw = math.degrees(math.atan2(by - ty, bx - tx))
            fx("NS_Crater_Waterfall", (tx, ty, tz - 300), "Crater/FX/Waterfalls", "FX_Waterfall_" + e["name"], yaw)
            fx("NS_Crater_Spray", (bx, by, bz + 150), "Crater/FX/Waterfalls", "FX_Spray_" + e["name"])
        elif t == "Mist":
            fx("NS_Crater_Mist", e["loc"], "Crater/FX/Mist", "FX_Mist_" + e["name"])
        elif t == "GroundMist":
            fx("NS_Crater_GroundMist", e["loc"], "Crater/FX/GroundMist", "FX_GroundMist_" + e["name"])
        elif t == "Campfire":
            x, y, z = e["loc"]
            fx("NS_Crater_Campfire", (x, y, z + 25), "Crater/FX/Campfires", "FX_Campfire_" + e["name"].replace(" ", ""))
        elif t == "Fireflies":
            fx("NS_Crater_Fireflies", e["loc"], "Crater/FX/Fireflies", "FX_Fireflies_%d" % n)
        n += 1
    log("fx placed for %d emitter markers" % n)


def stage_walk():
    """Automated walkthrough: trace every footpath for ground, slope, steps and blocking props."""
    world = unreal.EditorLevelLibrary.get_editor_world()
    paths = json.load(open(os.path.join(PROJ, "Saved/Crater/crater_paths.json")))
    report = {}
    for nm, pts in paths.items():
        ground, gaps, steep, blocked, blockers = [], 0, 0, 0, {}
        for x, y, _z in pts:
            hit = unreal.SystemLibrary.line_trace_single(world, unreal.Vector(x, y, 200000), unreal.Vector(x, y, -50000),
                                                         unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [], unreal.DrawDebugTrace.NONE, True)
            if hit is None or not hit.to_tuple()[0]:
                gaps += 1
                ground.append(None)
                continue
            ground.append(hit.to_tuple()[4].z)
        prev = None
        for i, (p, gz) in enumerate(zip(pts, ground)):
            if gz is None:
                continue
            if prev is not None:
                (px, py, pz) = prev
                run_ = math.hypot(p[0] - px, p[1] - py)
                if run_ > 1 and math.degrees(math.atan2(abs(gz - pz), run_)) > 40:
                    steep += 1
                # chest-height sweep between samples: anything blocking a walker?
                a_ = unreal.Vector(px, py, pz + 120); b_ = unreal.Vector(p[0], p[1], gz + 120)
                h2 = unreal.SystemLibrary.sphere_trace_single(world, a_, b_, 30.0, unreal.TraceTypeQuery.TRACE_TYPE_QUERY1, False, [],
                                                              unreal.DrawDebugTrace.NONE, True)
                if h2 is not None and h2.to_tuple()[0]:
                    blocked += 1
                    hit_actor = h2.to_tuple()[9]
                    key = hit_actor.get_actor_label() if hit_actor else "?"
                    key = key.split("_")[0] + "_" + (key.split("_")[1] if "_" in key else "")
                    blockers[key] = blockers.get(key, 0) + 1
            prev = (p[0], p[1], gz)
        report[nm] = {"samples": len(pts), "no_ground": gaps, "steep_steps_gt40deg": steep, "blocked_segments": blocked, "blockers": blockers}
    json.dump(report, open(os.path.join(PROJ, "Saved/Crater/walk_report.json"), "w"), indent=1)
    log("walk: " + json.dumps(report))


def stage_atmos():
    """Bright late-morning look: high sun from the south-east, sky light, low valley haze with blue distance."""
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            a.set_actor_rotation(unreal.Rotator(roll=0, pitch=-42, yaw=-128), False)
            lc = a.get_component_by_class(unreal.DirectionalLightComponent)
            lc.set_intensity(9.5)
            lc.set_light_color(unreal.LinearColor(1.0, 0.96, 0.9, 1))
            lc.set_editor_property("atmosphere_sun_light", True)
        elif isinstance(a, unreal.ExponentialHeightFog):
            a.set_actor_location(unreal.Vector(850000, 446000, 5600), False, False)
            fc = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
            fc.set_editor_property("fog_density", 0.0065)
            fc.set_editor_property("fog_height_falloff", 0.55)
            fc.set_editor_property("fog_inscattering_luminance", unreal.LinearColor(0.42, 0.55, 0.72, 1))
            fc.set_editor_property("start_distance", 1500.0)
            sec = fc.get_editor_property("second_fog_data")
            sec.set_editor_property("fog_density", 0.0018)
            sec.set_editor_property("fog_height_falloff", 0.05)
            sec.set_editor_property("fog_height_offset", 40000.0)
            fc.set_editor_property("second_fog_data", sec)
        elif isinstance(a, unreal.SkyLight):
            sc = a.get_component_by_class(unreal.SkyLightComponent)
            sc.set_editor_property("real_time_capture", True)
            sc.set_intensity(1.15)
    log("atmosphere set")


def stage_save():
    les.save_current_level()
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)       # World Partition actors live in their own packages
    unreal.EditorAssetLibrary.save_directory(ROOT, only_if_is_dirty=True, recursive=True)
    log("saved")


# ---------------------------------------------------------------------------------------------- moss / mist / night
MOSS_MI = {}


def mossy_master(path, log_bark=False):
    """World-aligned moss: grows on whatever faces up (follows each instance's rotation), varies per instance."""
    m = new_material(path)
    JT = "/Game/JustBStudios/PostApo/Textures/"
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -1800, -200)
    if log_bark:
        bark = tex_sample(m, "/Game/Megaplant_Library/Tree_Black_Alder/Textures/T_Black_Alder_Bark_C", tc, -1500, -300)
        nah = tex_sample(m, "/Game/Megaplant_Library/Tree_Black_Alder/Textures/T_Black_Alder_Bark_NAH", tc, -1500, -50)
        base_c, base_cp = bark, "RGB"
        base_n = custom(m, "UnpackNAH", "float2 xy = t.rg*2-1; return float3(xy, sqrt(saturate(1-dot(xy,xy))));", 3, [("t", nah, "RGB")], -1250, -50)
        base_np = ""
    else:
        bc = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -1500, -300)
        bc.set_editor_property("parameter_name", "BaseColor")
        bc.set_editor_property("texture", unreal.load_asset(JT + "T_Rock01_B"))
        bc.set_editor_property("sampler_type", sampler_for(unreal.load_asset(JT + "T_Rock01_B")))
        nn = mel.create_material_expression(m, unreal.MaterialExpressionTextureSampleParameter2D, -1500, -50)
        nn.set_editor_property("parameter_name", "Normal")
        nn.set_editor_property("texture", unreal.load_asset(JT + "T_Rock01_N"))
        nn.set_editor_property("sampler_type", sampler_for(unreal.load_asset(JT + "T_Rock01_N")))
        mel.connect_material_expressions(tc, "", bc, "UVs")
        mel.connect_material_expressions(tc, "", nn, "UVs")
        base_c, base_cp, base_n, base_np = bc, "RGB", nn, "RGB"
    wp = world_pos(m, -2000, 300)
    xy = mask(m, wp, "rg", -1800, 300)
    moss = tex_sample(m, JT + "T_Ground_Moss_B", div(m, xy, 190.0, -1650, 300), -1500, 300)
    mossn = tex_sample(m, JT + "T_Ground_Moss_N", div(m, xy, 190.0, -1650, 550), -1500, 550)
    noise = tex_sample(m, "/Engine/MaterialTemplates/Textures/T_Noise01", div(m, xy, 320.0, -1650, 800), -1500, 800)
    vn = mel.create_material_expression(m, unreal.MaterialExpressionVertexNormalWS, -1500, 1000)
    rnd = mel.create_material_expression(m, unreal.MaterialExpressionPerInstanceRandom, -1500, 1100)
    amt = mel.create_material_expression(m, unreal.MaterialExpressionScalarParameter, -1500, 1200)
    amt.set_editor_property("parameter_name", "MossAmount")
    amt.set_editor_property("default_value", 1.0)
    w = custom(m, "MossWeight", "return saturate((n.z + 0.1 + (k-0.5)*0.7 + (r-0.5)*0.5) * 3.2) * a;", 1,
               [("n", vn, ""), ("k", noise, "R"), ("r", rnd, ""), ("a", amt, "")], -1150, 900)
    tint = "float3(0.68, 0.6, 0.5)" if log_bark else "float3(0.8, 0.8, 0.82)"
    col = custom(m, "MossColor", "return lerp(b * %s, mo * float3(0.5, 0.74, 0.38), w);" % tint, 3,
                 [("b", base_c, base_cp), ("mo", moss, "RGB"), ("w", w, "")], -900, 0)
    nrm = custom(m, "MossNormal", "return normalize(lerp(b, mo, w*0.8));", 3, [("b", base_n, base_np), ("mo", mossn, "RGB"), ("w", w, "")], -900, 250)
    rough = custom(m, "MossRough", "return lerp(0.82, 0.95, w);", 1, [("w", w, "")], -900, 450)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    m.set_editor_property("used_with_instanced_static_meshes", True)
    mel.recompile_material(m)
    return m


def mossy_mi_for(mesh):
    """MI of M_MossyMaster carrying the mesh's own rock textures (JB MM_Master params BaseColor / Normal)."""
    key = mesh.get_name()
    if key in MOSS_MI:
        return MOSS_MI[key]
    path = ROOT + "/Materials/Mossy/MI_Mossy_" + key
    if unreal.EditorAssetLibrary.does_asset_exist(path):
        mi = unreal.load_asset(path)
    else:
        mi = tools.create_asset("MI_Mossy_" + key, ROOT + "/Materials/Mossy", unreal.MaterialInstanceConstant, unreal.MaterialInstanceConstantFactoryNew())
    mi.set_editor_property("parent", unreal.load_asset(ROOT + "/Materials/M_MossyMaster"))
    src = mesh.get_material(0)
    for pname in ("BaseColor", "Normal"):
        try:
            t = mel.get_material_instance_texture_parameter_value(src, pname)
            if t:
                mel.set_material_instance_texture_parameter_value(mi, pname, t)
        except Exception as ex:
            log("WARN moss MI %s %s: %r" % (key, pname, ex))
    mel.set_material_instance_scalar_parameter_value(mi, "MossAmount", 0.6 if "Mountain" in key else 1.0)
    MOSS_MI[key] = mi
    return mi


def mossy_log_mi():
    return unreal.load_asset(ROOT + "/Materials/M_MossyLog")


def stage_mossmat():
    mossy_master(ROOT + "/Materials/M_MossyMaster")
    mossy_master(ROOT + "/Materials/M_MossyLog", log_bark=True)
    for n in LOG_MESHES:
        sm = unreal.load_asset(ROOT + "/Logs/" + n)
        sm.set_material(0, mossy_log_mi())
        ns = sm.get_editor_property("nanite_settings")
        ns.enabled = True
        sm.set_editor_property("nanite_settings", ns)
    log("mossy materials ok")


def stage_mistmat():
    """Soft, lit, depth-faded sprite material for mist / spray / ground fog (picks up moonlight and campfires)."""
    m = new_material(ROOT + "/Materials/M_CraterMist")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    m.set_editor_property("translucency_lighting_mode", unreal.TranslucencyLightingMode.TLM_VOLUMETRIC_NON_DIRECTIONAL)
    m.set_editor_property("used_with_niagara_sprites", True)
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -1400, 0)
    pr = mel.create_material_expression(m, unreal.MaterialExpressionParticleRandom, -1400, 150)
    pc = mel.create_material_expression(m, unreal.MaterialExpressionParticleColor, -1400, 300)
    nuv = custom(m, "NoiseUV", "return uv*0.55 + r*7.31;", 2, [("uv", tc, ""), ("r", pr, "")], -1200, 100)
    nz = tex_sample(m, "/Engine/MaterialTemplates/Textures/T_Noise01", nuv, -1000, 100)
    op = custom(m, "MistOpacity", """
float r = saturate(1 - length(uv - 0.5) * 2); r = r*r*(3-2*r);
return r * saturate(n*1.7 - 0.25) * a;""", 1, [("uv", tc, ""), ("n", nz, "R"), ("a", pc, "A")], -750, 200)
    df = mel.create_material_expression(m, unreal.MaterialExpressionDepthFade, -500, 250)
    df.set_editor_property("fade_distance_default", 450.0)
    if not mel.connect_material_expressions(op, "", df, "Opacity"):
        mel.connect_material_expressions(op, "", df, "InOpacity")
    mel.connect_material_property(pc, "RGB", unreal.MaterialProperty.MP_BASE_COLOR)
    # moonlit mist reads slightly luminous against the dark forest
    glow = custom(m, "MistGlow", "return c * 0.22;", 3, [("c", pc, "RGB")], -500, 450)
    mel.connect_material_property(glow, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(df, "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(m)
    log("mist material ok")


def sp(obj, name, val):
    try:
        obj.set_editor_property(name, val)
    except Exception as ex:
        log("WARN %s.%s: %r" % (obj.get_class().get_name(), name, ex))


def stage_night():
    """Moonlit night: cool moon, star dome, ground-hugging fog with volumetric scattering, fixed night exposure."""
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Night"):
            eas.destroy_actor(a)
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.DirectionalLight):
            a.set_actor_rotation(unreal.Rotator(roll=0, pitch=-34, yaw=72), False)
            lc = a.get_component_by_class(unreal.DirectionalLightComponent)
            lc.set_intensity(1.5)
            lc.set_light_color(unreal.LinearColor(0.52, 0.64, 1.0, 1))
            sp(lc, "atmosphere_sun_light", True)
            sp(lc, "light_source_angle", 0.6)
            sp(lc, "atmosphere_sun_disk_color_scale", unreal.LinearColor(1.6, 1.7, 1.9, 1))
            sp(lc, "volumetric_scattering_intensity", 2.5)
        elif isinstance(a, unreal.ExponentialHeightFog):
            a.set_actor_location(unreal.Vector(850000, 446000, 5000), False, False)
            fc = a.get_component_by_class(unreal.ExponentialHeightFogComponent)
            sp(fc, "fog_density", 0.05)
            sp(fc, "fog_height_falloff", 0.9)          # dense in the first ~15 m, gone by the canopy tops
            sp(fc, "fog_inscattering_luminance", unreal.LinearColor(0.045, 0.06, 0.085, 1))
            sp(fc, "directional_inscattering_luminance", unreal.LinearColor(0.12, 0.14, 0.2, 1))
            sp(fc, "directional_inscattering_exponent", 12.0)
            sp(fc, "start_distance", 300.0)
            sp(fc, "enable_volumetric_fog", True)
            sp(fc, "volumetric_fog_scattering_distribution", 0.55)
            sp(fc, "volumetric_fog_albedo", unreal.Color(r=150, g=160, b=180, a=255))
            sp(fc, "volumetric_fog_extinction_scale", 0.7)
            sp(fc, "volumetric_fog_distance", 9000.0)
            sec = fc.get_editor_property("second_fog_data")
            sec.set_editor_property("fog_density", 0.0012)
            sec.set_editor_property("fog_height_falloff", 0.05)
            sec.set_editor_property("fog_height_offset", 40000.0)
            fc.set_editor_property("second_fog_data", sec)
        elif isinstance(a, unreal.SkyLight):
            sc = a.get_component_by_class(unreal.SkyLightComponent)
            sp(sc, "real_time_capture", True)
            sc.set_intensity(3.4)
            sp(sc, "lower_hemisphere_color", unreal.LinearColor(0.004, 0.006, 0.01, 1))
    # campfires: warmer, wider, and they light the fog
    for a in eas.get_all_level_actors():
        if isinstance(a, unreal.PointLight) and str(a.get_folder_path()).startswith("Crater/Outposts"):
            lc = a.get_component_by_class(unreal.PointLightComponent)
            lc.set_intensity(22000.0)
            lc.set_attenuation_radius(3200.0)
            sp(lc, "volumetric_scattering_intensity", 2.0)
    # star dome: additive, unlit, drawn behind everything translucent
    m = new_material(ROOT + "/Materials/M_CraterStars")
    m.set_editor_property("blend_mode", unreal.BlendMode.BLEND_ADDITIVE)
    m.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    m.set_editor_property("two_sided", True)
    sp(m, "use_translucency_vertex_fog", False)
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTextureCoordinate, -900, 0)
    sc_ = mel.create_material_expression(m, unreal.MaterialExpressionMultiply, -750, 0)
    sc_.set_editor_property("const_b", 10.0)
    mel.connect_material_expressions(tc, "", sc_, "A")
    st = tex_sample(m, "/Engine/EngineSky/T_Sky_Stars", sc_, -600, 0)
    tw = tex_sample(m, "/Engine/MaterialTemplates/Textures/T_Noise01", tc, -600, 250)
    em = custom(m, "Stars", "return pow(s, 1.6) * (0.6 + 0.8*n) * 2.2;", 3, [("s", st, "RGB"), ("n", tw, "R")], -350, 100)
    mel.connect_material_property(em, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    dome = unreal.load_asset("/Engine/EngineSky/SM_SkySphere")
    r = max(dome.get_bounding_box().max.x, 1.0)
    a = eas.spawn_actor_from_object(dome, unreal.Vector(850000, 446000, 0))
    a.set_actor_scale3d(unreal.Vector(1.0, 1.0, 1.0) * (3000000.0 / r))
    a.set_actor_label("Night_StarDome")
    a.set_folder_path("Crater/Night")
    c = a.get_component_by_class(unreal.StaticMeshComponent)
    c.set_material(0, m)
    c.set_collision_enabled(unreal.CollisionEnabled.NO_COLLISION)
    c.set_cast_shadow(False)
    sp(c, "translucency_sort_priority", -100)
    # fixed night exposure + a touch of cool grading
    pp = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(850000, 446000, 10000))
    pp.set_actor_label("Night_PostProcess")
    pp.set_folder_path("Crater/Night")
    pp.set_editor_property("unbound", True)
    s = pp.get_editor_property("settings")
    for k, v in (("auto_exposure_min_brightness", -0.6), ("auto_exposure_max_brightness", -0.6), ("auto_exposure_bias", 0.0),
                 ("bloom_intensity", 0.9), ("vignette_intensity", 0.45), ("white_temp", 7600.0)):
        try:
            s.set_editor_property(k, v)
            s.set_editor_property("override_" + k, True)
        except Exception as ex:
            log("WARN pp %s: %r" % (k, ex))
    pp.set_editor_property("settings", s)
    log("night set (moon, stars, ground fog, exposure)")


def lakes_info():
    """[(cx_cm_local, cy_cm_local, R_cm, z_cm, big)] from the generator's Region_v2.json (first entry is the great lake)."""
    info = json.load(open(os.path.join(V2, "Region_v2.json")))
    return [(lx * 100.0, ly * 100.0, r * 100.0, z * 100.0, i == 0) for i, (lx, ly, r, z) in enumerate(info["lakes"])]


def find_tex(name):
    for a in reg.get_assets_by_path("/Game/Fab/Megascans/Surfaces", recursive=True):
        if str(a.asset_name) == name:
            return str(a.package_name)
    raise RuntimeError("missing " + name)


def stage_lakewater():
    """Ocean-style rolling waves on the great lake: 5 Gerstner waves moving the surface (WPO), analytic normals + scanned
    ripple detail, foam on the crests, calm shallows near the shore. Two-sided so the surface is seen from underwater."""
    lk = lakes_info()[0]
    m = new_material(ROOT + "/Materials/M_LakeWater")
    m.set_editor_property("two_sided", True)
    m.set_editor_property("tangent_space_normal", False)
    lp = mel.create_material_expression(m, unreal.MaterialExpressionLocalPosition, -1600, 0)
    tm = mel.create_material_expression(m, unreal.MaterialExpressionTime, -1600, 150)
    waves = """
float2 c = float2(%.1f, %.1f); float2 rad = float2(44000, 52000);
float2 qq = (p.xy - c) / rad; float th = atan2(qq.y, qq.x);
float brr = length(qq) / (1 + 0.12 * cos(3 * th + 0.7) + 0.07 * cos(5 * th + 2.1));      // same wobbly shoreline as the generator
float amp = saturate((1.0 - brr) * 9);                                                  // full waves until ~10 pct from the shore
float4 W[5] = {float4(1.0, 0.35, 8500, 75), float4(0.55, 1.0, 4800, 42), float4(-0.35, 1.0, 2900, 24), float4(1.0, -0.6, 1750, 12), float4(-1.0, -0.2, 1050, 7)};
float3 off = 0; float3 nrm = float3(0, 0, 1); float crest = 0;
[unroll] for (int i = 0; i < 5; i++) {
  float2 d = normalize(W[i].xy); float k = 6.2832 / W[i].z; float sp = sqrt(980.0 / k);
  float a = W[i].w * amp; float f = k * (dot(d, p.xy) - sp * t); float q = 0.55 / (k * W[i].w * 5 + 1e-3);
  off.xy += q * a * d * cos(f); off.z += a * sin(f);
  nrm.xy -= d * k * a * cos(f); nrm.z -= q * k * a * sin(f); crest += a * sin(f);
}
%s""" % (lk[0], lk[1], "%s")
    wpo = custom(m, "GerstnerWPO", waves % "return off;", 3, [("p", lp, ""), ("t", tm, "")], -1300, 0)
    nrmw = custom(m, "GerstnerNormal", waves % "return normalize(nrm);", 3, [("p", lp, ""), ("t", tm, "")], -1300, 250)
    crest = custom(m, "GerstnerCrest", waves % "return saturate((crest - 70.0) / 50.0) * amp;", 1, [("p", lp, ""), ("t", tm, "")], -1300, 450)
    # scanned ripple detail, two pans in different directions
    wp = world_pos(m, -1900, 700)
    xy = mask(m, wp, "rg", -1750, 700)
    WN = find_tex("T_tgmjffbqx_4K_N")
    pans = []
    for k, (sc, sx, sy) in enumerate(((1800.0, 0.008, 0.003), (3200.0, -0.004, 0.007))):
        uv = div(m, xy, sc, -1600, 700 + k * 200)
        pn = mel.create_material_expression(m, unreal.MaterialExpressionPanner, -1450, 700 + k * 200)
        pn.set_editor_property("speed_x", sx); pn.set_editor_property("speed_y", sy)
        mel.connect_material_expressions(uv, "", pn, "Coordinate")
        pans.append(tex_sample(m, WN, pn, -1250, 700 + k * 200))
    tc = mel.create_material_expression(m, unreal.MaterialExpressionTexCoord if hasattr(unreal, "MaterialExpressionTexCoord")
                                        else unreal.MaterialExpressionTextureCoordinate, -1900, 1200)
    fuv = custom(m, "FlowUV", """
float2 f = (uv * 2 - 1) * 0.75;                       // ~1.4 m/s downstream
float p0 = frac(t * 0.3), p1 = frac(t * 0.3 + 0.5);
return float4(w - f * p0, w - f * p1 + 0.37);""", 4, [("uv", tc, ""), ("t", tm, ""), ("w", div(m, xy, 550.0, -1750, 1250), "")], -1600, 1200)
    fa = tex_sample(m, WN, mask(m, fuv, "rg", -1450, 1150), -1250, 1150)
    fb = tex_sample(m, WN, mask(m, fuv, "ba", -1450, 1350), -1250, 1350)
    flow = custom(m, "FlowNormal", """
float2 f = uv * 2 - 1; float mg = saturate(length(f));
float p0 = frac(t * 0.3);
float3 n = lerp(a, b, abs(1 - 2 * p0));
return float3(n.xy * mg * 0.55, mg);""", 3, [("uv", tc, ""), ("t", tm, ""), ("a", fa, "RGB"), ("b", fb, "RGB")], -1050, 1250)
    nrm = custom(m, "WaterNormal", "return normalize(float3(g.xy + (d1.xy + d2.xy) * 0.18 * (1 - fl.z) + fl.xy, g.z));", 3,
                 [("g", nrmw, ""), ("d1", pans[0], "RGB"), ("d2", pans[1], "RGB"), ("fl", flow, "")], -950, 300)
    col = custom(m, "WaterColor", "float3 c = lerp(float3(0.008, 0.03, 0.035), float3(0.03, 0.06, 0.055), fl.z); return lerp(c, float3(0.55, 0.6, 0.62), f * 0.7);", 3,
                 [("f", crest, ""), ("fl", flow, "")], -950, 500)
    rough = custom(m, "WaterRough", "return lerp(0.05, 0.35, f);", 1, [("f", crest, "")], -950, 650)
    mel.connect_material_property(col, "", unreal.MaterialProperty.MP_BASE_COLOR)
    mel.connect_material_property(nrm, "", unreal.MaterialProperty.MP_NORMAL)
    mel.connect_material_property(rough, "", unreal.MaterialProperty.MP_ROUGHNESS)
    mel.connect_material_property(wpo, "", unreal.MaterialProperty.MP_WORLD_POSITION_OFFSET)
    mel.recompile_material(m)
    for n in ("SM_Creeks", "SM_Rivers"):
        unreal.load_asset(ROOT + "/Water/" + n).set_material(0, m)
    log("lake water (gerstner waves + running creeks/rivers) ok")


def box_volume(cls, label, folder, cx, cy, z0, z1, sx, sy):
    """Spawn a brush volume (default 200 uu cube from the actor factory) and scale it to the box."""
    a = eas.spawn_actor_from_class(cls, unreal.Vector(cx, cy, (z0 + z1) / 2))
    a.set_actor_label(label)
    a.set_folder_path(folder)
    a.set_actor_scale3d(unreal.Vector(sx / 200.0, sy / 200.0, (z1 - z0) / 200.0))
    return a


def stage_swim():
    """Make every lake swimmable: water physics volumes (CharacterMovement swims inside them) filling the basin below the
    surface, plus an underwater tint. The great lake is filled with strips that follow its ellipse."""
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Swim"):
            eas.destroy_actor(a)
    ox, oy = DATA["origin_cm"]
    n_vol = 0
    for i, (lx, ly, r, z, big) in enumerate(lakes_info()):
        cx, cy = ox + lx, oy + ly
        top, bot = z + 20.0, z - (1400.0 if big else 450.0)
        boxes = []
        if big:
            RX, RY, N = 44000.0, 52000.0, 14
            for j in range(N):
                t0, t1 = -1 + 2 * j / N, -1 + 2 * (j + 1) / N
                half = RX * math.sqrt(max(0.0, 1 - max(abs(t0), abs(t1)) ** 2)) * 0.98 + RX * 0.06
                boxes.append((cx, cy + (t0 + t1) / 2 * RY, half * 2, (t1 - t0) * RY))
        else:
            boxes.append((cx, cy, r * 1.6, r * 1.6))
        for k, (bx, by, sx, sy) in enumerate(boxes):
            v = box_volume(unreal.PhysicsVolume, "Swim_Lake%d_%02d" % (i, k), "Crater/Swim", bx, by, bot, top, sx, sy)
            sp(v, "water_volume", True)
            sp(v, "fluid_friction", 0.3)
            pp = box_volume(unreal.PostProcessVolume, "Underwater_Lake%d_%02d" % (i, k), "Crater/Swim", bx, by, bot, top - 10, sx, sy)
            pp.set_editor_property("priority", 10.0)
            st = pp.get_editor_property("settings")
            for key, val in (("color_gain", unreal.Vector4(0.35, 0.75, 0.8, 1.0)), ("color_saturation", unreal.Vector4(0.7, 0.7, 0.7, 1.0)),
                             ("vignette_intensity", 0.9), ("depth_of_field_focal_distance", 300.0)):
                try:
                    st.set_editor_property(key, val)
                    st.set_editor_property("override_" + key, True)
                except Exception as ex:
                    log("WARN underwater pp %s: %r" % (key, ex))
            pp.set_editor_property("settings", st)
            n_vol += 1
    log("swim: %d water volumes (+ underwater post) across %d lakes" % (n_vol, len(lakes_info())))



def stage_nocyclone():
    """The cyclone cloud decks were removed by request: delete any leftover actors and their materials."""
    n = 0
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Cyclone"):
            eas.destroy_actor(a)
            n += 1
    for p in [ROOT + "/Materials/MI_Cyclone_%d" % i for i in range(3)] + [ROOT + "/Materials/M_CycloneClouds"]:
        if unreal.EditorAssetLibrary.does_asset_exist(p):
            unreal.EditorAssetLibrary.delete_asset(p)
    log("nocyclone: removed %d actors" % n)


def stage_towns():
    """Town / village plots (levelled and kept clear by the generator): a ring of mossy stakes marks each boundary, with an
    editor-only name label and an empty marker actor (tags: plot kind + radius) to build the settlement around."""
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/Towns"):
            eas.destroy_actor(a)
    cyl = "/Engine/BasicShapes/Cylinder"
    wood = unreal.load_asset(ROOT + "/Materials/MI_MossyLog") or unreal.load_asset(ROOT + "/Materials/M_MossyLog")
    rnd = random.Random(5)
    for pl in DATA["plots"]:
        nm, (cx, cy, cz), R = pl["name"], pl["c"], pl["r_cm"]
        folder = "Crater/Towns/" + nm
        mk = new_actor("Plot_" + nm, folder, (cx, cy, cz))
        mk.set_editor_property("tags", [unreal.Name("Plot"), unreal.Name(pl["kind"]), unreal.Name("Radius_%d" % R)])
        n = int(2 * math.pi * R / 800)                                     # a stake every ~8 m
        for k in range(n):
            if k % 9 == 4:                                                 # gaps = ways in
                continue
            a = 2 * math.pi * k / n
            x, y = cx + math.cos(a) * R, cy + math.sin(a) * R
            tall = 2.6 if k % 9 in (3, 5) else rnd.uniform(1.3, 1.8)     # gateposts either side of each gap
            st = place(cyl, x, y, cz + tall * 50 - 20, rnd.uniform(0, 360), s=(0.22, 0.22, tall), folder=folder,
                       label="%s_Stake_%02d" % (nm, k), pitch=rnd.uniform(-4, 4), roll=rnd.uniform(-4, 4))
            c = st.get_component_by_class(unreal.StaticMeshComponent)
            if wood:
                c.set_material(0, wood)
        t = eas.spawn_actor_from_class(unreal.TextRenderActor, unreal.Vector(cx, cy, cz + 900))
        t.set_actor_label("%s_Label" % nm)
        t.set_folder_path(folder)
        tc = t.get_component_by_class(unreal.TextRenderComponent)
        tc.set_text("%s (%s)" % (nm, pl["kind"]))
        tc.set_editor_property("world_size", 260.0)
        tc.set_editor_property("horizontal_alignment", unreal.HorizTextAligment.EHTA_CENTER)
        tc.set_text_render_color(unreal.Color(r=255, g=170, b=90, a=255))
        t.set_actor_hidden_in_game(True)
    log("towns: %d plots marked" % len(DATA["plots"]))


def stage_fogmist():
    """Fog of war + ground mist within visual range, one post-process material.
    * Mist: ray-marched from the camera out to MistRange through a thin layer hugging the terrain (height from Mist_Height),
      broken up by drifting noise, fading out at the edge of the range.
    * Fog of war: RT_FoWExplored (painted by BP_FogOfWar around the player during play) -> unexplored ground is hidden under a
      dark drifting shroud, explored ground outside the sight radius is dimmed. Off in the editor (FoWEnabled = 0)."""
    FXP = ROOT + "/FX"
    eal = unreal.EditorAssetLibrary
    ox, oy = DATA["origin_cm"]
    (sx, sy), (z0, z1) = DATA["mist_height"]["size_cm"], DATA["mist_height"]["z_cm"]
    # terrain height texture (16-bit grey, clamped, full precision)
    ht = import_file(os.path.join(V2, "Mist_Height.png"), FXP, "T_MistHeight")
    ht.set_editor_property("srgb", False)
    ht.set_editor_property("compression_settings", unreal.TextureCompressionSettings.TC_GRAYSCALE)
    ht.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    ht.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    sp(ht, "never_stream", True)
    # parameter collection (tweak these live in the editor)
    mpc_path = FXP + "/MPC_FogOfWar"
    mpc = unreal.load_asset(mpc_path) if eal.does_asset_exist(mpc_path) else \
        tools.create_asset("MPC_FogOfWar", FXP, unreal.MaterialParameterCollection, unreal.MaterialParameterCollectionFactoryNew())
    scal = (("FoWEnabled", 0.0), ("RevealRadius", 9000.0), ("SightRadius", VIS_CM * 0.8), ("ExploredDim", 0.45),
            ("MistRange", VIS_CM), ("MistHeight", 350.0), ("MistDensity", 0.00045), ("MistNear", 400.0))
    vecs = (("PlayerPos", unreal.LinearColor(0, 0, -1e6, 0)), ("MistColor", unreal.LinearColor(0.05, 0.065, 0.09, 1)),
            ("ShroudColor", unreal.LinearColor(0.006, 0.008, 0.013, 1)))
    def cp_(cls, n, v):
        e = cls()
        e.set_editor_property("parameter_name", n)
        e.set_editor_property("default_value", v)
        return e
    mpc.set_editor_property("scalar_parameters", [cp_(unreal.CollectionScalarParameter, n, v) for n, v in scal])
    mpc.set_editor_property("vector_parameters", [cp_(unreal.CollectionVectorParameter, n, v) for n, v in vecs])

    def cparam(m, name, x, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionCollectionParameter, x, y)
        e.set_editor_property("collection", mpc)
        e.set_editor_property("parameter_name", name)
        return e

    def tex_obj(m, tex, x, y):
        e = mel.create_material_expression(m, unreal.MaterialExpressionTextureObject, x, y)
        e.set_editor_property("texture", tex)
        return e
    # explored-area render target (RGBA8: R8 targets read back wrong in 5.8; black = unexplored)
    rt_path = FXP + "/RT_FoWExplored"
    rt = unreal.load_asset(rt_path) if eal.does_asset_exist(rt_path) else \
        tools.create_asset("RT_FoWExplored", FXP, unreal.TextureRenderTarget2D, unreal.TextureRenderTargetFactoryNew())
    rt.set_editor_property("size_x", 1024)
    rt.set_editor_property("size_y", 1024)
    rt.set_editor_property("render_target_format", unreal.TextureRenderTargetFormat.RTF_RGBA8)
    rt.set_editor_property("clear_color", unreal.LinearColor(0, 0, 0, 1))
    rt.set_editor_property("address_x", unreal.TextureAddress.TA_CLAMP)
    rt.set_editor_property("address_y", unreal.TextureAddress.TA_CLAMP)
    consts = "float2 O = float2(%.1f, %.1f); float2 S = float2(%.1f, %.1f);" % (ox, oy, sx, sy)
    # brush: drawn over the whole RT each tick, translucent so explored texels only ever get brighter
    b = new_material(FXP + "/M_FoWBrush")
    b.set_editor_property("blend_mode", unreal.BlendMode.BLEND_TRANSLUCENT)
    b.set_editor_property("shading_model", unreal.MaterialShadingModel.MSM_UNLIT)
    tc = mel.create_material_expression(b, unreal.MaterialExpressionTextureCoordinate, -700, 0)
    bo = custom(b, "RevealBrush", consts + """
float2 w = O + uv * S;
float d = length(w - pp.xy);
return (pp.z > -1e5) ? 1 - smoothstep(r * 0.7, r, d) : 0;""", 1,
                [("uv", tc, ""), ("pp", cparam(b, "PlayerPos", -700, 150), ""), ("r", cparam(b, "RevealRadius", -700, 300), "")], -400, 100)
    one = mel.create_material_expression(b, unreal.MaterialExpressionConstant, -400, -50)
    one.set_editor_property("r", 1.0)
    mel.connect_material_property(one, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.connect_material_property(bo, "", unreal.MaterialProperty.MP_OPACITY)
    mel.recompile_material(b)
    # post-process: mist + fog of war
    m = new_material(FXP + "/M_PP_FogMist")
    m.set_editor_property("material_domain", unreal.MaterialDomain.MD_POST_PROCESS)
    BL = unreal.BlendableLocation
    loc = getattr(BL, "BL_SCENE_COLOR_AFTER_DOF", None) or getattr(BL, "BL_AFTER_TONEMAPPING", None)
    sp(m, "blendable_location", loc)
    st = mel.create_material_expression(m, unreal.MaterialExpressionSceneTexture, -1400, -300)
    st.set_editor_property("scene_texture_id", unreal.SceneTextureId.PPI_POST_PROCESS_INPUT0)
    wp = mel.create_material_expression(m, unreal.MaterialExpressionWorldPosition, -1400, -150)
    cam = mel.create_material_expression(m, unreal.MaterialExpressionCameraPositionWS, -1400, -50)
    tm = mel.create_material_expression(m, unreal.MaterialExpressionTime, -1400, 50)
    ins = [("scene", st, "Color"), ("wp", wp, ""), ("cam", cam, ""), ("t", tm, ""),
           ("Hgt", tex_obj(m, ht, -1400, 150), ""), ("Nz", tex_obj(m, unreal.load_asset("/Engine/MaterialTemplates/Textures/T_Noise01"), -1400, 300), ""),
           ("Exp", tex_obj(m, rt, -1400, 450), "")]
    y = 600
    for n, _ in scal + vecs:
        if n not in ("RevealRadius",):
            ins.append((n, cparam(m, n, -1400, y), ""))
            y += 90
    code = consts + """
float3 col = scene.rgb;
float3 V = wp - cam; float dist = length(V); float3 dir = V / max(dist, 1.0);
// ---- ground mist within visual range: march through a layer hugging the terrain
float range = min(dist, MistRange);
float stp = range / 14.0; float acc = 0;
float jit = frac(sin(dot(wp.xy, float2(12.9898, 78.233))) * 43758.5453);
for (int i = 0; i < 14; i++) {
    float s = (i + jit) * stp;
    float3 q = cam + dir * s;
    float2 huv = (q.xy - O) / S;
    float hz = ZMIN + Texture2DSampleLevel(Hgt, HgtSampler, huv, 0).r * (ZMAX - ZMIN);
    float above = max(q.z - hz, 0);
    float n1 = Texture2DSampleLevel(Nz, NzSampler, q.xy / 5200.0 + t * float2(0.0035, 0.0015), 0).r;
    float n2 = Texture2DSampleLevel(Nz, NzSampler, q.xy / 1400.0 - t * float2(0.006, 0.009), 0).r;
    float wisp = saturate(n1 * 1.6 - 0.35 + (n2 - 0.5) * 0.7);
    float win = smoothstep(MistNear, MistNear * 2.5, s) * (1 - smoothstep(MistRange * 0.65, MistRange, s));
    acc += exp(-above / MistHeight) * wisp * win * stp;
}
float mist = 1 - exp(-acc * MistDensity);
col = lerp(col, MistColor.rgb, mist);
// ---- fog of war (play only): unexplored ground under a drifting shroud, explored-but-out-of-sight ground dimmed
if (FoWEnabled > 0.5 && dist < 1.5e6) {
    float2 uv = (wp.xy - O) / S;
    float inside = all(uv > 0) && all(uv < 1);
    float ex = inside * Texture2DSampleLevel(Exp, ExpSampler, uv, 0).r;
    float sight = 1 - smoothstep(SightRadius * 0.75, SightRadius, length(wp.xy - PlayerPos.xy));
    float lum = dot(col, float3(0.3, 0.59, 0.11));
    float3 dim = lerp(col, lum.xxx, 0.6) * ExploredDim;
    col = lerp(dim, col, sight);
    float c1 = Texture2DSampleLevel(Nz, NzSampler, wp.xy / 9000.0 + t * float2(0.004, -0.002), 0).r;
    float c2 = Texture2DSampleLevel(Nz, NzSampler, wp.xy / 2600.0 - t * float2(0.007, 0.004), 0).r;
    float3 shroud = ShroudColor.rgb * (0.6 + 1.2 * c1 + 0.5 * c2);
    float cover = smoothstep(0.15, 0.85, ex + (c2 - 0.5) * 0.25);
    col = lerp(shroud, col, cover);
}
return col;"""
    code = code.replace("ZMIN", "%.1f" % z0).replace("ZMAX", "%.1f" % z1)
    pp = custom(m, "FogOfWarAndMist", code, 3, ins, -900, 0)
    mel.connect_material_property(pp, "", unreal.MaterialProperty.MP_EMISSIVE_COLOR)
    mel.recompile_material(m)
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Crater/FogOfWar"):
            eas.destroy_actor(a)
    v = eas.spawn_actor_from_class(unreal.PostProcessVolume, unreal.Vector(ox + sx / 2, oy + sy / 2, 20000))
    v.set_actor_label("FogOfWar_Mist_PP")
    v.set_folder_path("Crater/FogOfWar")
    v.set_editor_property("unbound", True)
    s = v.get_editor_property("settings")
    s.set_editor_property("weighted_blendables", unreal.WeightedBlendables(array=[unreal.WeightedBlendable(weight=1.0, object=m)]))
    v.set_editor_property("settings", s)
    bp = unreal.load_asset(FXP + "/BP_FogOfWar")
    if bp:
        a = eas.spawn_actor_from_class(bp.generated_class(), unreal.Vector(ox + sx / 2, oy + sy / 2, 20000))
        a.set_actor_label("FogOfWar_Controller")
        a.set_folder_path("Crater/FogOfWar")
    log("fogmist: post-process + MPC + explored RT%s" % (" + controller" if bp else " (BP_FogOfWar missing)"))


VIS_CM = 15000.0        # visual range: fog-of-war sight radius + mist range end here (MPC MistRange)


def stage_cull():
    """Nothing beyond the visual range is drawn: foliage instances fade out from 85% of it, props / FX / lights stop drawing at
    it (the mist is fully thick there, so nothing visibly pops). Terrain, water, sky and the big wall outcrops stay.
    This saves GPU time and streamed texture / Nanite memory; the assets themselves stay loaded in RAM."""
    n = 0
    for a in eas.get_all_level_actors():
        if not str(a.get_folder_path()).startswith(("Crater/Foliage", "Crater/Ruins", "Crater/Towns", "Crater/Campfires", "Crater/FX", "Crater/Outposts")):
            continue
        for c in a.get_components_by_class(unreal.PrimitiveComponent):
            if isinstance(c, (unreal.InstancedStaticMeshComponent, unreal.InstancedSkinnedMeshComponent)):
                sp(c, "instance_start_cull_distance", int(VIS_CM * 0.85))
                sp(c, "instance_end_cull_distance", int(VIS_CM))
            else:
                sp(c, "ld_max_draw_distance", VIS_CM)
            n += 1
        for lc in a.get_components_by_class(unreal.LightComponent):
            sp(lc, "max_draw_distance", VIS_CM)
            sp(lc, "max_distance_fade_range", 2000.0)
    log("cull: %d components limited to %.0f m" % (n, VIS_CM / 100))


WP_MAP = "/Game/Maps/StarfallCrater_WP"
STREAMED = ("Crater/Foliage", "Crater/Ruins", "Crater/Towns", "Crater/Campfires", "Crater/FX", "Crater/Outposts", "Crater/Emitters", "Crater/Bridges")
WP_CELL_CM, WP_RANGE_CM = 25600, 25600     # streaming grid: loads everything within 256 m of the player (visual range is 150 m)


def stage_wpmap():
    """Start a fresh World Partition map (the old StarfallCrater map is left untouched) with the sky / light / fog actors;
    follow with: terrain water rocks ruins foliage outposts emitters fx swim towns night lakewater fogmist cull stream save."""
    if unreal.EditorAssetLibrary.does_asset_exist(WP_MAP):
        les.load_level(WP_MAP)
        stage_clean()
    else:
        les.new_level(WP_MAP, True)
    for a in eas.get_all_level_actors():
        if str(a.get_folder_path()).startswith("Lighting"):
            eas.destroy_actor(a)
    for cls, loc in ((unreal.DirectionalLight, (0, 0, 0)), (unreal.SkyAtmosphere, (0, 0, 0)), (unreal.SkyLight, (0, 0, 0)),
                     (unreal.ExponentialHeightFog, (850000, 446000, 5000)), (unreal.VolumetricCloud, (0, 0, 0))):
        a = eas.spawn_actor_from_class(cls, unreal.Vector(*loc))
        a.set_folder_path("Lighting")
    log("wpmap: %s ready" % WP_MAP)


def stage_stream():
    """Streaming: props / foliage chunks / ruins / towns / FX load only within WP_RANGE_CM of the player and are unloaded
    from memory beyond it; terrain, water, sky, lighting, fog and volumes stay loaded so the world never has holes."""
    n_on = n_off = 0
    for a in eas.get_all_level_actors():
        on = str(a.get_folder_path()).startswith(STREAMED)
        sp(a, "is_spatially_loaded", on)
        n_on += on
        n_off += not on
    w = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem).get_editor_world()
    wp = w.get_world_settings().get_editor_property("world_partition")
    # the runtime hash isn't exposed as a property in 5.8: reach the main grid of the default hash set by its object path
    grid = unreal.find_object(None, wp.get_path_name() + ".WorldPartitionRuntimeHashSet_0.RuntimePartitionLHGrid_0")
    if grid:
        sp(grid, "cell_size", WP_CELL_CM)
        sp(grid, "loading_range", WP_RANGE_CM)
        sp(grid, "b_is2d", True)
    else:
        log("WARN stream: main runtime grid not found; set Cell Size / Loading Range in World Settings > World Partition")
    log("stream: %d actors stream within %.0f m, %d always loaded" % (n_on, WP_RANGE_CM / 100, n_off))


STAGES = {"clean": stage_clean, "import": stage_import, "material": stage_material, "terrain": stage_terrain, "water": stage_water,
          "foliage": stage_foliage, "rocks": stage_rocks, "outposts": stage_outposts, "emitters": stage_emitters, "save": stage_save,
          "retile": stage_retile, "fx": stage_fx, "walk": stage_walk, "bridges": stage_bridges, "redress_clean": stage_redress_clean,
          "atmos": stage_atmos, "mossmat": stage_mossmat, "mistmat": stage_mistmat, "night": stage_night, "watermat": stage_watermat, "ruins": stage_ruins, "lakewater": stage_lakewater, "swim": stage_swim,
          "nocyclone": stage_nocyclone, "towns": stage_towns, "fogmist": stage_fogmist, "cull": stage_cull, "wpmap": stage_wpmap, "stream": stage_stream}
args = sys.argv[1:] or ["all"]
if args == ["all"]:
    args = list(STAGES)
t0 = time.time()
for st in args:
    if st.startswith("foliage:"):
        stage_foliage(set(st.split(":", 1)[1].split(",")))
        continue
    try:
        STAGES[st]()
    except Exception as ex:
        import traceback
        log("STAGE %s FAILED: %r\n%s" % (st, ex, traceback.format_exc()))
        break
log("done %s in %.0fs" % (args, time.time() - t0))
with open(os.path.join(PROJ, "Saved/Crater/build_log.txt"), "a") as f:
    f.write("\n".join(LOG) + "\n")
