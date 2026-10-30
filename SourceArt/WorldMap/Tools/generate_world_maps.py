"""
Generates Unreal landscape source data from the painted world map.

Outputs (in SourceArt/WorldMap/Output):
  Heightmap_4033x2647.png        16-bit landscape heightmap
  Splat/<Layer>.png              8-bit per-layer weightmaps (sum to 255)
  Splat_Preview.png              color-coded biome classification
  Zones_Preview.png / Zones.png  named region ID map (gameplay zones)
  Emitter_Map.png                RGBA: R=lava glow, G=waterfall/mist, B=blight, A=fog/cloud
  Emitters.csv                   point list for spawning FX/settlement markers (UE world cm)
  WorldMap_Info.json             import settings (scale, z-scale, layer order)
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

SRC = sys.argv[1]
OUT = sys.argv[2]

# Landscape: 32 x 21 components of 126 quads (2x2 sections of 63) -> 4033 x 2647 verts
OUT_W, OUT_H = 4033, 2647
XY_SCALE_CM = 400.0          # 4 m per vertex -> ~16.1 km x 10.6 km
Z_SCALE = 512.0              # +-1310 m usable height range
METERS_TO_UNITS = 128.0 * 100.0 / Z_SCALE

rng = np.random.default_rng(1337)
os.makedirs(os.path.join(OUT, "Splat"), exist_ok=True)

img = np.asarray(Image.open(SRC).convert("RGB")).astype(np.float32)
H, W, _ = img.shape
r, g, b = img[..., 0], img[..., 1], img[..., 2]
lum = 0.299 * r + 0.587 * g + 0.114 * b
mx, mn = img.max(-1), img.min(-1)
sat = (mx - mn) / np.maximum(mx, 1)

# ---------------------------------------------------------------- zones
ZONES = [
    # name, polygon in source-image pixels
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
CRATER_C, CRATER_R = (800.0, 440.0), (265.0, 200.0)

zone_img = Image.new("L", (W, H), 255)
zd = ImageDraw.Draw(zone_img)
for i, (_, poly) in enumerate(ZONES):
    zd.polygon(poly, fill=i)
zone = np.asarray(zone_img).astype(np.int32)
yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
crater_r = np.sqrt(((xx - CRATER_C[0]) / CRATER_R[0]) ** 2 + ((yy - CRATER_C[1]) / CRATER_R[1]) ** 2)
CRATER_ID = len(ZONES)
zone[crater_r < 1.0] = CRATER_ID
ZONE_NAMES = [z[0] for z in ZONES] + ["Starfall Crater Rainforest"]
# fill unassigned pixels with nearest zone
unassigned = zone == 255
if unassigned.any():
    _, idx = ndi.distance_transform_edt(unassigned, return_indices=True)
    zone = zone[idx[0], idx[1]]

def inzone(name):
    return zone == ZONE_NAMES.index(name)

# ---------------------------------------------------------------- overlays to ignore (labels/legend/compass/scale)
overlay = np.zeros((H, W), bool)
for x0, y0, x1, y1 in [(8, 752, 198, 988), (35, 30, 115, 132), (222, 980, 585, 1004)]:
    overlay[y0:y1, x0:x1] = True
# label text: bright, low-sat, thin strokes surrounded by dark halo; caught as small bright specks
LABEL_BOXES = [(705, 62, 815, 105), (1295, 150, 1380, 192), (115, 192, 240, 226), (320, 318, 438, 354),
               (720, 427, 870, 480), (1325, 420, 1435, 456), (285, 538, 380, 572), (1090, 725, 1215, 760),
               (1340, 782, 1450, 802), (320, 795, 445, 815), (712, 785, 852, 826)]
for x0, y0, x1, y1 in LABEL_BOXES:
    overlay[y0:y1, x0:x1] = True

# legend/compass/scale bar sit in open ocean -> paint them deep water; labels -> inpaint from surroundings
ocean_overlay = np.zeros((H, W), bool)
for x0, y0, x1, y1 in [(0, 745, 205, 1024), (25, 22, 125, 140), (215, 975, 595, 1024)]:
    ocean_overlay[y0:y1, x0:x1] = True
img[ocean_overlay] = (18, 45, 85)
label_mask = overlay & ~ocean_overlay
valid = (~label_mask).astype(np.float32)
for sig in (4, 10, 24):
    num = ndi.gaussian_filter(img * valid[..., None], (sig, sig, 0))
    den = ndi.gaussian_filter(valid, sig)[..., None]
    fill = num / np.maximum(den, 1e-4)
    img[label_mask] = np.where(den[label_mask] > 0.05, fill[label_mask], img[label_mask])
overlay[:] = False
r, g, b = img[..., 0], img[..., 1], img[..., 2]
lum = 0.299 * r + 0.587 * g + 0.114 * b
mx, mn = img.max(-1), img.min(-1)
sat = (mx - mn) / np.maximum(mx, 1)

# ---------------------------------------------------------------- biome classification
LAYERS = ["DeepWater", "ShallowWater", "Beach", "Grass", "ForestCanopy", "Swamp", "Rock",
          "Mountain", "Snow", "Desert", "DesertRock", "Volcanic", "Lava", "Blight"]
L = {n: i for i, n in enumerate(LAYERS)}
REF = [
    ("DeepWater", (18, 45, 85)), ("DeepWater", (25, 65, 110)),
    ("ShallowWater", (40, 160, 175)), ("ShallowWater", (95, 205, 205)), ("ShallowWater", (45, 115, 140)),
    ("Beach", (225, 205, 160)), ("Beach", (200, 185, 140)),
    ("Grass", (125, 150, 55)), ("Grass", (155, 165, 75)), ("Grass", (100, 130, 45)),
    ("ForestCanopy", (30, 60, 22)), ("ForestCanopy", (50, 90, 35)), ("ForestCanopy", (70, 110, 40)),
    ("Rock", (115, 110, 100)), ("Rock", (75, 72, 68)), ("Rock", (150, 140, 125)),
    ("Snow", (235, 240, 245)), ("Snow", (200, 210, 220)),
    ("Desert", (232, 172, 105)), ("Desert", (215, 150, 85)),
    ("DesertRock", (170, 90, 50)), ("DesertRock", (130, 70, 40)),
    ("Volcanic", (40, 35, 33)), ("Volcanic", (65, 55, 50)),
    ("Lava", (240, 90, 20)), ("Lava", (255, 170, 50)), ("Lava", (200, 50, 15)),
    ("Blight", (80, 55, 95)), ("Blight", (170, 90, 220)), ("Blight", (55, 40, 60)),
]
ref_cols = np.array([c for _, c in REF], np.float32)
ref_ids = np.array([L[n] for n, _ in REF])
smooth = ndi.uniform_filter(img, size=(3, 3, 1))
d = np.stack([((smooth - c) ** 2).sum(-1) for c in ref_cols], -1)
cls = ref_ids[d.argmin(-1)]

# hue rules override nearest-colour for the common land cases (shadowed canopy was reading as rock)
sr, sg, sb = smooth[..., 0], smooth[..., 1], smooth[..., 2]
s_lum = 0.299 * sr + 0.587 * sg + 0.114 * sb
s_sat = (smooth.max(-1) - smooth.min(-1)) / np.maximum(smooth.max(-1), 1)
is_water = (sb > sr + 25) & (sb > sg - 15)
greenish = (sg > sr + 6) & (sg > sb + 6) & ~is_water
olive = (np.abs(sr - sg) < 18) & (sg > sb + 25) & (s_lum > 70) & (s_lum < 160)
cls[is_water & (s_lum < 95)] = L["DeepWater"]
cls[is_water & (s_lum >= 95)] = L["ShallowWater"]
cls[greenish & (s_lum < 95)] = L["ForestCanopy"]
cls[greenish & (s_lum >= 95)] = L["Grass"]
cls[olive & ~greenish] = L["Grass"]
cls[~is_water & ~greenish & ~olive & (s_sat < 0.18) & (s_lum < 200)] = L["Rock"]

# regional priors
fz = inzone("Frostpeak Range")
cls[fz & np.isin(cls, [L["ShallowWater"], L["DeepWater"]]) & (s_lum > 110)] = L["Snow"]  # blue-shadowed snow
cls[fz & (cls == L["Rock"])] = L["Mountain"]
ew = inzone("Emberwood Forest") | (zone == CRATER_ID)
cls[ew & (cls == L["Grass"]) & (s_lum < 120)] = L["ForestCanopy"]
cloud = (~fz) & (cls == L["Snow"])          # white blobs outside the range are clouds/mist
ash = inzone("Ashen Wastes")
cls[ash & np.isin(cls, [L["Rock"], L["ForestCanopy"], L["Blight"], L["DesertRock"]])] = L["Volcanic"]
cls[~ash & ~inzone("Sunscorch Desert") & (cls == L["Lava"])] = L["DesertRock"]
cls[~ash & (cls == L["Volcanic"])] = L["Rock"]
bl = inzone("Hollow Blight Lands")
cls[bl & np.isin(cls, [L["Rock"], L["Volcanic"], L["ForestCanopy"]]) & (sat < 0.45)] = L["Blight"]
cls[~bl & (cls == L["Blight"])] = L["Rock"]
de = inzone("Sunscorch Desert")
cls[de & (cls == L["Rock"])] = L["DesertRock"]
cls[de & (cls == L["Beach"])] = L["Desert"]
cls[~de & ~ash & (cls == L["Desert"])] = L["Beach"]
cls[~de & ~ash & (cls == L["DesertRock"])] = L["Rock"]
sw = inzone("Mosswarden Swamps")
cls[sw & np.isin(cls, [L["Grass"]])] = L["Swamp"]
cls[sw & (cls == L["ForestCanopy"]) & (lum > 70)] = L["Swamp"]
# outside deep ocean, dark blue-ish inland pixels are rivers/lakes -> shallow water
water = np.isin(cls, [L["DeepWater"], L["ShallowWater"]])

# remove overlays + clouds by nearest valid neighbour, then majority-ish cleanup
invalid = overlay | cloud
_, idx = ndi.distance_transform_edt(invalid, return_indices=True)
cls = cls[idx[0], idx[1]]
onehot = np.stack([(cls == i).astype(np.float32) for i in range(len(LAYERS))], -1)
onehot = ndi.uniform_filter(onehot, size=(5, 5, 1))
cls = onehot.argmax(-1)

# ---------------------------------------------------------------- height (meters)
land = ~np.isin(cls, [L["DeepWater"], L["ShallowWater"]])
land = ndi.binary_opening(land, iterations=1)
dist_in = ndi.distance_transform_edt(land)
dist_out = ndi.distance_transform_edt(~land)
BASE = {"DeepWater": -120, "ShallowWater": -12, "Beach": 2, "Grass": 35, "ForestCanopy": 55,
        "Swamp": 6, "Rock": 160, "Mountain": 520, "Snow": 950, "Desert": 45, "DesertRock": 170,
        "Volcanic": 260, "Lava": 230, "Blight": 110}
DETAIL = {"DeepWater": 0, "ShallowWater": 0, "Beach": 2, "Grass": 10, "ForestCanopy": 18,
          "Swamp": 3, "Rock": 110, "Mountain": 260, "Snow": 300, "Desert": 25, "DesertRock": 160,
          "Volcanic": 120, "Lava": 30, "Blight": 140}
base = np.zeros((H, W), np.float32)
amp = np.zeros((H, W), np.float32)
for n, i in L.items():
    base[cls == i] = BASE[n]
    amp[cls == i] = DETAIL[n]
base = ndi.gaussian_filter(base, 6)
amp = ndi.gaussian_filter(amp, 4)

# inland rise + ocean depth falloff
h = base + np.minimum(dist_in, 160) * 0.9 * (base > 0)
h = np.where(land, h, -8 - np.minimum(dist_out, 60) * 4.0)

# painted relief: high-pass of luminance (map is lit from upper-left)
clean_lum = lum.copy()
clean_lum[invalid] = ndi.gaussian_filter(lum, 8)[invalid]
relief = clean_lum - ndi.gaussian_filter(clean_lum, 7)
relief = ndi.gaussian_filter(relief, 1.2) / 40.0
h += np.where(land, relief * amp, 0)

# Starfall Crater: sunken basin, cliff rim, central spire
rim = 380 * np.exp(-((crater_r - 1.0) / 0.09) ** 2)
basin = np.where(crater_r < 0.95, -h * 0.75 + 25, 0) * np.clip((0.95 - crater_r) / 0.08, 0, 1)
spire = 620 * np.exp(-(((xx - 800) / 55) ** 2 + ((yy - 335) / 70) ** 2))
h += rim + basin + spire

# Frostpeak & Ashen massifs: extra uplift toward north edge
fz_soft = ndi.gaussian_filter(fz.astype(np.float32), 25)
h += fz_soft * land * 300 * np.clip(1 - yy / 230, 0, 1)
h += ndi.gaussian_filter(ash.astype(np.float32), 25) * 250 * np.exp(-(((xx - 1400) / 120) ** 2 + ((yy - 90) / 100) ** 2))

# Lava channels slightly carved
lava_mask = ndi.gaussian_filter((cls == L["Lava"]).astype(np.float32), 2)
h -= lava_mask * 40

h = ndi.gaussian_filter(h, 0.8)
# soft-compress peaks so they fit the +-1310 m range at Z scale 512
h = np.where(h > 800, 800 + (h - 800) * 0.55, h)

# ---------------------------------------------------------------- upscale + export height
def up(a, order=3):
    return ndi.zoom(a, (OUT_H / H, OUT_W / W), order=order)[:OUT_H, :OUT_W]

H_up = up(h)
# fine fractal noise so 4 m verts don't look smeared
noise = np.zeros_like(H_up)
for octave, (sig, a) in enumerate([(24, 6.0), (8, 2.5), (3, 1.0)]):
    noise += ndi.gaussian_filter(rng.standard_normal(H_up.shape).astype(np.float32), sig) * a * sig
amp_up = up(amp, 1)
H_up += noise * (0.3 + amp_up / 120.0) * (H_up > 0)
units = np.clip(32768 + H_up * METERS_TO_UNITS, 0, 65535).astype(np.uint16)
Image.fromarray(units).save(os.path.join(OUT, f"Heightmap_{OUT_W}x{OUT_H}.png"))
prev = ((H_up - H_up.min()) / (H_up.max() - H_up.min()) * 255).astype(np.uint8)
Image.fromarray(prev).resize((1536, 1008)).save(os.path.join(OUT, "Heightmap_Preview.png"))

# ---------------------------------------------------------------- splat weightmaps
weights = []
for i in range(len(LAYERS)):
    w = ndi.gaussian_filter((cls == i).astype(np.float32), 1.5)
    weights.append(up(w, 1))
weights = np.clip(np.stack(weights, 0), 0, None)
weights /= np.maximum(weights.sum(0, keepdims=True), 1e-6)
w8 = np.round(weights * 255).astype(np.uint8)
for i, n in enumerate(LAYERS):
    Image.fromarray(w8[i]).save(os.path.join(OUT, "Splat", f"{i:02d}_{n}.png"))

PALETTE = {"DeepWater": (20, 50, 100), "ShallowWater": (60, 190, 200), "Beach": (235, 220, 170),
           "Grass": (140, 175, 60), "ForestCanopy": (30, 90, 30), "Swamp": (110, 120, 50),
           "Rock": (125, 120, 115), "Mountain": (170, 165, 160), "Snow": (250, 250, 255),
           "Desert": (235, 180, 100), "DesertRock": (170, 85, 45), "Volcanic": (45, 40, 40),
           "Lava": (255, 90, 0), "Blight": (140, 70, 190)}
pal = np.array([PALETTE[n] for n in LAYERS], np.uint8)
Image.fromarray(pal[cls]).save(os.path.join(OUT, "Splat_Preview.png"))

# ---------------------------------------------------------------- zones
Image.fromarray(zone.astype(np.uint8)).resize((OUT_W, OUT_H), Image.NEAREST).save(os.path.join(OUT, "Zones.png"))
zpal = np.array([(70, 140, 200), (230, 240, 250), (90, 30, 20), (230, 170, 90), (40, 110, 40), (130, 120, 100),
                 (60, 200, 190), (120, 130, 50), (150, 60, 200), (60, 180, 120), (20, 160, 60)], np.uint8)
Image.fromarray(pal[cls] // 2 + zpal[zone] // 2).save(os.path.join(OUT, "Zones_Preview.png"))

# ---------------------------------------------------------------- emitter map
lava_glow = (ash & (r > 180) & (r - b > 120) & (sat > 0.6)).astype(np.float32)
blight_glow = (bl & (b > 150) & (r > 120) & (g < 120) & (b - g > 60)).astype(np.float32)
# waterfalls: bright, near-white, vertical streaks sitting on rock/cliff, outside snow & clouds
white = (lum > 185) & (sat < 0.18) & ~fz & ~overlay
vert = ndi.uniform_filter(white.astype(np.float32), size=(9, 2)) > 0.6
horiz = ndi.uniform_filter(white.astype(np.float32), size=(2, 9)) > 0.6
waterfall = (vert & ~horiz).astype(np.float32)
fog = ndi.gaussian_filter(cloud.astype(np.float32), 3)
fog = np.maximum(fog, 0.35 * (sw.astype(np.float32)))            # swamp ground mist
fog = np.maximum(fog, 0.25 * (crater_r < 0.95))                  # crater canopy haze
em = np.stack([ndi.gaussian_filter(lava_glow, 2), ndi.gaussian_filter(waterfall, 2),
               ndi.gaussian_filter(blight_glow, 2), fog], -1)
em = np.clip(em / np.maximum(em.reshape(-1, 4).max(0), 1e-6), 0, 1)
Image.fromarray((em * 255).astype(np.uint8)).resize((OUT_W // 2, OUT_H // 2), Image.BILINEAR) \
    .save(os.path.join(OUT, "Emitter_Map.png"))

def to_world(px, py):
    wx = (px / W) * (OUT_W - 1) * XY_SCALE_CM
    wy = (py / H) * (OUT_H - 1) * XY_SCALE_CM
    hx = int(np.clip(round(px / W * (OUT_W - 1)), 0, OUT_W - 1))
    hy = int(np.clip(round(py / H * (OUT_H - 1)), 0, OUT_H - 1))
    wz = (H_up[hy, hx]) * 100.0
    return round(wx), round(wy), round(wz)

def blobs(mask, kind, min_px, max_n):
    lab, n = ndi.label(mask > 0.5)
    out = []
    if n == 0:
        return out
    sizes = ndi.sum(np.ones_like(lab), lab, range(1, n + 1))
    cents = ndi.center_of_mass(np.ones_like(lab), lab, range(1, n + 1))
    order = np.argsort(-sizes)
    for k in order[:max_n]:
        if sizes[k] < min_px:
            break
        cy, cx = cents[k]
        out.append((kind, ZONE_NAMES[zone[int(cy), int(cx)]], *to_world(cx, cy), int(sizes[k])))
    return out

SETTLEMENTS = [(250, 385), (470, 180), (625, 88), (1210, 72), (1135, 208), (1305, 245), (1240, 345),
               (1395, 555), (1070, 580), (845, 700), (935, 850), (1030, 780), (1050, 650), (440, 760),
               (115, 520), (330, 640)]
rows = []
rows += blobs(lava_glow, "LavaGlow", 6, 60)
rows += blobs(ndi.binary_dilation(waterfall > 0.5, iterations=2), "Waterfall", 10, 60)
rows += blobs(blight_glow, "BlightCrystal", 4, 40)
rows += blobs(cloud, "CloudBank", 40, 40)
rows += [("Settlement", ZONE_NAMES[zone[y, x]], *to_world(x, y), 0) for x, y in SETTLEMENTS]
with open(os.path.join(OUT, "Emitters.csv"), "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["Type", "Zone", "X_cm", "Y_cm", "Z_cm", "SizePx"])
    wr.writerows(rows)

zone_centers = {}
for i, n in enumerate(ZONE_NAMES):
    cy, cx = ndi.center_of_mass(zone == i)
    zone_centers[n] = to_world(cx, cy)

info = {
    "heightmap": f"Heightmap_{OUT_W}x{OUT_H}.png",
    "resolution": [OUT_W, OUT_H],
    "components": [32, 21], "section_size_quads": 63, "sections_per_component": 2,
    "scale_cm": [XY_SCALE_CM, XY_SCALE_CM, Z_SCALE],
    "world_size_km": [round((OUT_W - 1) * XY_SCALE_CM / 1e5, 2), round((OUT_H - 1) * XY_SCALE_CM / 1e5, 2)],
    "height_range_m": [float(H_up.min()), float(H_up.max())],
    "sea_level_z_cm": 0,
    "layers": LAYERS,
    "zones": ZONE_NAMES,
    "zone_centers_cm": zone_centers,
    "layer_coverage_pct": {n: round(float((cls == i).mean() * 100), 2) for i, n in enumerate(LAYERS)},
    "emitter_counts": {k: sum(1 for r_ in rows if r_[0] == k) for k in {r_[0] for r_ in rows}},
}
with open(os.path.join(OUT, "WorldMap_Info.json"), "w") as f:
    json.dump(info, f, indent=2)
print(json.dumps(info, indent=2))
