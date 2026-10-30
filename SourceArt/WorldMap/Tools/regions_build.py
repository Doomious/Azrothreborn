"""
Splits /Game/azrothreborn into the 11 Titan Walks regions so collaborators can each own one region.
Run inside the editor:   py "<this file>" <stage> [stage ...]
Stages:
  layers    create one Editor data layer per region (/Game/Maps/Regions/DL_<NN>_<Name>) and register it in the world
  assign    put every actor whose bounds centre lies in a region into that region's data layer, then save
  volumes   place one LocationVolume per region (outliner folder "Regions") for loading it in the World Partition window
  manifest  write Docs/Regions/regions.json (region outlines and bounds) and Docs/Regions/actor_owners.tsv
            (actor file -> region); re-run after adding actors so Tools/region_check.sh knows about them
  all       layers assign volumes manifest

Region outlines are the zone polygons from generate_world_maps.py, converted to world centimetres, so they match
SourceArt/WorldMap/Output/Zones.png. Editor data layers only affect what is loaded in the editor, never the game.
"""
import json
import math
import os
import sys

import unreal

PROJ = unreal.Paths.convert_relative_path_to_full(unreal.Paths.project_dir())
MAP = "/Game/azrothreborn"
DL_ROOT = "/Game/Maps/Regions"
OUT_DIR = os.path.join(PROJ, "Saved/Regions")
DOCS_DIR = os.path.join(PROJ, "Docs/Regions")
LOG = []

# Same constants as generate_world_maps.py: source image is 1536 x 1024, landscape 4033 x 2647 verts at 4 m.
SRC_W, SRC_H = 1536.0, 1024.0
OUT_W, OUT_H = 4033, 2647
XY_SCALE_CM = 400.0
SX, SY = (OUT_W - 1) * XY_SCALE_CM / SRC_W, (OUT_H - 1) * XY_SCALE_CM / SRC_H
Z_MIN, Z_MAX = -30000.0, 140000.0

ZONES = [
    ("Stormreach Isles", [(0, 0), (450, 0), (180, 180), (180, 350), (40, 380), (0, 400)]),
    ("Frostpeak Range", [(430, 0), (1090, 0), (1080, 120), (950, 190), (800, 225), (620, 190), (480, 130)]),
    ("Ashen Wastes", [(1060, 0), (1536, 0), (1536, 290), (1400, 300), (1250, 320), (1150, 260), (1080, 150)]),
    ("Sunscorch Desert", [(1130, 260), (1400, 300), (1536, 290), (1536, 560), (1350, 600), (1150, 600), (1060, 520), (1050, 380)]),
    ("Emberwood Forest", [(180, 180), (450, 0), (480, 130), (620, 190), (560, 300), (520, 420), (420, 450), (260, 440), (180, 350)]),
    ("Stonevale Highlands", [(0, 400), (40, 380), (180, 350), (260, 440), (420, 450), (500, 560), (470, 680), (300, 700), (150, 640), (0, 600)]),
    ("Ember Coast", [(0, 600), (150, 640), (300, 700), (470, 680), (600, 750), (560, 1024), (0, 1024)]),
    ("Mosswarden Swamps", [(500, 560), (560, 600), (900, 620), (940, 700), (950, 1000), (560, 1024), (600, 750), (470, 680)]),
    ("Hollow Blight Lands", [(900, 620), (1060, 560), (1250, 600), (1320, 700), (1290, 900), (1120, 1024), (950, 1000), (940, 700)]),
    ("Verdant Isles", [(1250, 600), (1350, 600), (1536, 560), (1536, 1024), (1120, 1024), (1290, 900), (1320, 700)]),
]
CRATER_NAME = "Starfall Crater Rainforest"
CRATER_C, CRATER_R = (800.0, 440.0), (265.0, 200.0)
REGION_NAMES = [z[0] for z in ZONES] + [CRATER_NAME]
COLORS = [(70, 140, 200), (230, 240, 250), (90, 30, 20), (230, 170, 90), (40, 110, 40), (130, 120, 100),
          (60, 200, 190), (120, 130, 50), (150, 60, 200), (60, 180, 120), (20, 160, 60)]

# Actors every region shares; nobody edits these without agreeing first. The landscape here is only a 20 m leftover
# patch far below the world (the ground is BO_ blockout tiles), so its proxies are shared too.
SHARED_CLASSES = {"Landscape", "LandscapeStreamingProxy", "WorldPartitionHLOD", "WorldDataLayers",
                  "WorldPartitionMiniMap", "SkyLight", "SkyAtmosphere", "VolumetricCloud", "ExponentialHeightFog",
                  "DirectionalLight", "PlayerStart", "WorldSettings", "LocationVolume"}
SHARED_MIN_SIZE_CM = 200000.0   # anything wider than 2 km (ocean plane, sky sphere) spans several regions

dles = unreal.get_editor_subsystem(unreal.DataLayerEditorSubsystem)
ues = unreal.get_editor_subsystem(unreal.UnrealEditorSubsystem)
les = unreal.get_editor_subsystem(unreal.LevelEditorSubsystem)
eas = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
eal = unreal.EditorAssetLibrary
wpl = unreal.WorldPartitionBlueprintLibrary


def log(msg):
    LOG.append(msg)
    unreal.log_warning("REGIONS: " + msg)


def key(i):
    return "%02d_%s" % (i + 1, REGION_NAMES[i].replace(" ", ""))


# ---------------------------------------------------------------- geometry (source-image pixels)
def to_px(x_cm, y_cm):
    return x_cm / SX, y_cm / SY


def in_poly(px, py, poly):
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if (yi > py) != (yj > py) and px < (xj - xi) * (py - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def seg_dist(px, py, a, b):
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / max(dx * dx + dy * dy, 1e-9)))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def region_of(x_cm, y_cm):
    """Same rules as generate_world_maps.py: crater ellipse wins, then polygons (later ones overwrite earlier), then
    nearest polygon for the few pixels no polygon covers."""
    px, py = to_px(x_cm, y_cm)
    if math.hypot((px - CRATER_C[0]) / CRATER_R[0], (py - CRATER_C[1]) / CRATER_R[1]) < 1.0:
        return len(ZONES)
    hit = None
    for i, (_, poly) in enumerate(ZONES):
        if in_poly(px, py, poly):
            hit = i
    if hit is not None:
        return hit
    best, best_d = 0, 1e18
    for i, (_, poly) in enumerate(ZONES):
        d = min(seg_dist(px, py, poly[k], poly[(k + 1) % len(poly)]) for k in range(len(poly)))
        if d < best_d:
            best, best_d = i, d
    return best


def region_bounds_cm(i):
    if i == len(ZONES):
        pts = [(CRATER_C[0] - CRATER_R[0], CRATER_C[1] - CRATER_R[1]), (CRATER_C[0] + CRATER_R[0], CRATER_C[1] + CRATER_R[1])]
    else:
        pts = ZONES[i][1]
    xs, ys = [p[0] * SX for p in pts], [p[1] * SY for p in pts]
    return [min(xs), min(ys), Z_MIN], [max(xs), max(ys), Z_MAX]


def region_outline_cm(i):
    if i == len(ZONES):
        return [[round((CRATER_C[0] + CRATER_R[0] * math.cos(a)) * SX), round((CRATER_C[1] + CRATER_R[1] * math.sin(a)) * SY)]
                for a in [k * math.pi / 16 for k in range(32)]]
    return [[round(x * SX), round(y * SY)] for x, y in ZONES[i][1]]


# ---------------------------------------------------------------- helpers
def world():
    w = ues.get_editor_world()
    if w.get_path_name().split(".")[0] != MAP:
        les.load_level(MAP)
        w = ues.get_editor_world()
    return w


def desc_class(d):
    return str(d.native_class.get_name()) if d.native_class else "?"


def desc_region(d):
    c = d.bounds.get_center() if hasattr(d.bounds, "get_center") else None
    if c is None:
        c = unreal.Vector((d.bounds.min.x + d.bounds.max.x) / 2, (d.bounds.min.y + d.bounds.max.y) / 2, 0)
    return region_of(c.x, c.y)


def is_shared(d):
    b = d.bounds
    return desc_class(d) in SHARED_CLASSES or max(b.max.x - b.min.x, b.max.y - b.min.y) > SHARED_MIN_SIZE_CM


def layer_instance(i):
    asset = unreal.load_asset("%s/DL_%s" % (DL_ROOT, key(i)))
    return asset, (dles.get_data_layer_instance(asset) if asset else None)


# ---------------------------------------------------------------- stages
def stage_layers():
    w = world()
    for i in range(len(REGION_NAMES)):
        name = "DL_" + key(i)
        path = "%s/%s" % (DL_ROOT, name)
        if eal.does_asset_exist(path):
            asset = unreal.load_asset(path)
        else:
            asset = unreal.AssetToolsHelpers.get_asset_tools().create_asset(name, DL_ROOT, unreal.DataLayerAsset, unreal.DataLayerFactory())
        asset.set_editor_property("data_layer_type", unreal.DataLayerType.EDITOR)
        r, g, b = COLORS[i]
        asset.set_editor_property("debug_color", unreal.Color(b, g, r, 255))
        eal.save_loaded_asset(asset, False)
        inst = dles.get_data_layer_instance(asset)
        if inst is None:
            params = unreal.DataLayerCreationParameters()
            params.set_editor_property("data_layer_asset", asset)
            inst = dles.create_data_layer_instance(params)
            log("created data layer instance %s -> %s" % (name, inst))
        else:
            log("data layer %s already registered" % name)
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


def stage_assign():
    world()
    descs = wpl.get_actor_descs()
    by_region = {}
    skipped = 0
    for d in descs:
        if is_shared(d):
            skipped += 1
            continue
        by_region.setdefault(desc_region(d), []).append(d)
    log("assign: %d actors to place, %d shared skipped" % (sum(len(v) for v in by_region.values()), skipped))
    for i in sorted(by_region):
        asset, inst = layer_instance(i)
        if inst is None:
            raise RuntimeError("data layer for %s missing; run the 'layers' stage first" % key(i))
        todo = [d for d in by_region[i] if asset.get_path_name() not in [str(x) for x in d.data_layer_assets]]
        done = 0
        for s in range(0, len(todo), 1000):
            batch = todo[s:s + 1000]
            guids = [d.guid for d in batch]
            wpl.load_actors(guids)
            actors = [a for a in (unreal.find_object(None, str(d.actor_path)) for d in batch) if a]
            actors = [a for a in actors if dles.is_actor_valid_for_data_layer_instances(a, [inst])]
            dles.add_actors_to_data_layer(actors, inst)
            unreal.EditorLoadingAndSavingUtils.save_packages([a.get_package() for a in actors], True)
            wpl.unload_actors(guids)
            done += len(actors)
        log("%s: %d actors (%d already assigned)" % (key(i), done, len(by_region[i]) - len(todo)))


def stage_volumes():
    w = world()
    existing = {a.get_actor_label(): a for a in unreal.GameplayStatics.get_all_actors_of_class(w, unreal.LocationVolume)}
    for i in range(len(REGION_NAMES)):
        label = "Region_" + key(i)
        lo, hi = region_bounds_cm(i)
        centre = unreal.Vector((lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2)
        a = existing.get(label) or eas.spawn_actor_from_class(unreal.LocationVolume, centre)
        a.set_actor_label(label)
        a.set_actor_location(centre, False, False)
        # LocationVolume's default brush is a 200 cm cube
        a.set_actor_scale3d(unreal.Vector((hi[0] - lo[0]) / 200.0, (hi[1] - lo[1]) / 200.0, (hi[2] - lo[2]) / 200.0))
        a.set_folder_path("Regions")
        log("volume %s at %s" % (label, centre))
    unreal.EditorLoadingAndSavingUtils.save_dirty_packages(True, True)


def stage_manifest():
    world()
    descs = wpl.get_actor_descs()
    regions = []
    for i in range(len(REGION_NAMES)):
        lo, hi = region_bounds_cm(i)
        regions.append({"id": i + 1, "key": key(i), "name": REGION_NAMES[i], "data_layer": "%s/DL_%s" % (DL_ROOT, key(i)),
                        "location_volume": "Region_" + key(i), "bounds_cm": [lo, hi], "outline_cm": region_outline_cm(i),
                        "actor_count": 0})
    actors = []
    for d in descs:
        cls = desc_class(d)
        pkg = str(d.actor_package)
        if is_shared(d):
            owner = "Shared"
        else:
            r = desc_region(d)
            owner = key(r)
            regions[r]["actor_count"] += 1
        actors.append([pkg, owner, cls, str(d.label)])
    actors.sort()
    os.makedirs(DOCS_DIR, exist_ok=True)
    json.dump({"map": MAP, "regions": regions}, open(os.path.join(DOCS_DIR, "regions.json"), "w"), indent=1)
    # One line per actor file, read by Tools/region_check.sh: <file under Content/> TAB <owner> TAB <class> TAB <label>
    with open(os.path.join(DOCS_DIR, "actor_owners.tsv"), "w", newline="\n") as f:
        f.write("file\towner\tclass\tlabel\n")
        for pkg, owner, cls, label in actors:
            f.write("%s.uasset\t%s\t%s\t%s\n" % (pkg.replace("/Game/", "Content/", 1), owner, cls, label))
    log("manifest: %d actors, %s" % (len(actors), ", ".join("%s=%d" % (r["key"], r["actor_count"]) for r in regions)))


STAGES = {"layers": stage_layers, "assign": stage_assign, "volumes": stage_volumes, "manifest": stage_manifest}

if __name__ == "__main__":
    args = sys.argv[1:] or ["all"]
    if args == ["all"]:
        args = ["layers", "assign", "volumes", "manifest"]
    try:
        for s in args:
            log("stage " + s)
            STAGES[s]()
        log("done")
    except Exception:
        import traceback
        log("ERROR " + traceback.format_exc())
    os.makedirs(OUT_DIR, exist_ok=True)
    open(os.path.join(OUT_DIR, "regions_build_log.txt"), "w").write("\n".join(LOG))
