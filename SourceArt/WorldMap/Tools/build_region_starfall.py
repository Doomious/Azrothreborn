"""
Starfall Crater Rainforest — high-detail regional landscape data.

Region: 4033 x 3025 verts @ 160 cm  (~6.45 x 4.84 km), placed so it overlays the world landscape.
Same Z encoding as the world heightmap (Z scale 512, sea level = 32768) so heights line up.

Outputs (SourceArt/Regions/StarfallCrater/):
  Heightmap_4033x3025.png      16-bit heightmap
  Splat/<NN>_<Layer>.png       weightmaps (sum 255)
  Density/<Name>.png           foliage density masks for PCG / foliage spawners
  River_Mask.png               river channels (for water bodies / spline tracing)
  Features.csv                 waterfalls, mist banks, spire, clearing, etc. in WORLD cm
  Region_Info.json             import settings + world offset
  Topographic_Crater.png       10 m contour map with features labelled
  Splat_Preview.png / Heightmap_Preview.png
"""
import csv
import json
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, LinearSegmentedColormap

SRC, WORLD_OUT, OUT = sys.argv[1], sys.argv[2], sys.argv[3]
os.makedirs(os.path.join(OUT, "Splat"), exist_ok=True)
os.makedirs(os.path.join(OUT, "Density"), exist_ok=True)
winfo = json.load(open(os.path.join(WORLD_OUT, "WorldMap_Info.json")))

RW, RH = 4033, 3025                 # 32 x 24 components of 126 quads
XY_CM = 160.0
Z_SCALE = winfo["scale_cm"][2]
UNITS_PER_M = 128.0 * 100.0 / Z_SCALE
WORLD_W, WORLD_H = winfo["resolution"]
WORLD_XY = winfo["scale_cm"][0]

concept = Image.open(SRC).convert("RGB")
SW, SH = concept.size
CM_PER_SRC_PX = (WORLD_W - 1) * WORLD_XY / SW          # ~1050 cm per concept pixel

# region placement (world cm), centred on the crater
CRATER_C_SRC = (810.0, 425.0)
span_x_cm, span_y_cm = (RW - 1) * XY_CM, (RH - 1) * XY_CM
origin_x = CRATER_C_SRC[0] * CM_PER_SRC_PX - span_x_cm / 2
origin_y = CRATER_C_SRC[1] * CM_PER_SRC_PX - span_y_cm / 2
origin_x, origin_y = round(origin_x / WORLD_XY) * WORLD_XY, round(origin_y / WORLD_XY) * WORLD_XY

yy, xx = np.mgrid[0:RH, 0:RW].astype(np.float32)
wx = origin_x + xx * XY_CM                 # world cm
wy = origin_y + yy * XY_CM
sx, sy = wx / CM_PER_SRC_PX, wy / CM_PER_SRC_PX      # concept-image pixel coords
rng = np.random.default_rng(2026)

def fractal(shape, scales, seed):
    g = np.random.default_rng(seed)
    out = np.zeros(shape, np.float32)
    for sig, amp in scales:
        n = ndi.gaussian_filter(g.standard_normal(shape).astype(np.float32), sig)
        out += n / (n.std() + 1e-6) * amp
    return out

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

# ---------------------------------------------------------------- sample concept art + world height into region
src_box = (int(sx.min()) - 2, int(sy.min()) - 2, int(sx.max()) + 3, int(sy.max()) + 3)
crop = np.asarray(concept.crop(src_box)).astype(np.float32)
cy_, cx_ = sy - src_box[1], sx - src_box[0]
img = np.stack([ndi.map_coordinates(crop[..., c], [cy_, cx_], order=1) for c in range(3)], -1)
r, g, b = img[..., 0], img[..., 1], img[..., 2]
lum = 0.299 * r + 0.587 * g + 0.114 * b

whm = np.asarray(Image.open(os.path.join(WORLD_OUT, winfo["heightmap"]))).astype(np.float32)
world_h = ndi.map_coordinates((whm - 32768) / UNITS_PER_M, [wy / WORLD_XY, wx / WORLD_XY], order=1)
world_h = ndi.gaussian_filter(world_h, 12)

# ---------------------------------------------------------------- crater geometry
RX, RY = 250.0, 178.0                         # inner-wall ellipse, concept px
dxs, dys = (sx - CRATER_C_SRC[0]) / RX, (sy - CRATER_C_SRC[1]) / RY
ang = np.arctan2(dys, dxs)
# irregular rim: angular noise (periodic) + small-scale jaggedness
k = np.arange(1, 9)
phase = rng.uniform(0, 2 * np.pi, len(k))
amps = 0.05 / k ** 0.9
rim_wobble = sum(a * np.cos(kk * ang + p) for a, kk, p in zip(amps, k, phase))
cr = np.sqrt(dxs ** 2 + dys ** 2) / (1 + rim_wobble)
cr = cr + fractal(cr.shape, [(6, 0.004), (20, 0.006)], 11)

FLOOR = 55.0
floor = FLOOR + fractal(cr.shape, [(160, 9), (50, 5), (14, 1.5)], 1)
rim_top = np.maximum(world_h, 240) + 120 + fractal(cr.shape, [(90, 35), (25, 12)], 2)
# south rim is jagged rocky ridges in the art, north is taller sheer wall
rim_top += 60 * np.clip(-dys, 0, 1)
outer = world_h + 25

wall = smoothstep(0.955, 1.0, cr)                       # near-vertical cliff band
ledges = 0.06 * np.sin(cr * 900) * smoothstep(0.955, 0.975, cr) * (1 - smoothstep(0.985, 1.0, cr))
wall = np.clip(wall + ledges, 0, 1)
talus = smoothstep(0.86, 0.955, cr) * 22                # scree apron at the wall foot
inside = floor + talus + (rim_top - floor - talus) * wall
outside_fall = smoothstep(1.0, 1.28, cr)
h = np.where(cr < 1.0, inside, rim_top + (outer - rim_top) * outside_fall)

# central spire (north of centre) with ridged faces
SP = (797.0, 352.0)
dsp = np.sqrt(((sx - SP[0]) / 50.0) ** 2 + ((sy - SP[1]) / 68.0) ** 2)
ridges = 1 - np.abs(fractal(cr.shape, [(10, 1.0)], 3))
spire = 640 * np.clip(1 - dsp, 0, 1) ** 1.25 * (0.85 + 0.15 * ridges)
spire += 70 * np.clip(1 - dsp / 1.6, 0, 1) ** 2               # forested skirt
h = np.maximum(h, floor + spire) * (cr < 1.0) + h * (cr >= 1.0)

# jungle hummocks on the floor
h += (cr < 0.95) * np.abs(fractal(cr.shape, [(35, 6), (12, 2)], 4))

# ---------------------------------------------------------------- rivers from the painted water
water_px = (b > r + 25) & (b > g - 15) & (lum > 40)
water_px = ndi.binary_opening(water_px, iterations=2)
water_px = ndi.binary_closing(water_px, iterations=3)
lab, n = ndi.label(water_px)
sizes = ndi.sum(water_px, lab, range(1, n + 1))
keep = np.isin(lab, 1 + np.nonzero(sizes > 4000)[0])
river = ndi.binary_dilation(keep, iterations=3)
river_soft = ndi.gaussian_filter(river.astype(np.float32), 6)
bank = ndi.gaussian_filter(river.astype(np.float32), 22)
local_ground = ndi.gaussian_filter(h, 40)
carve = np.where(cr < 0.955, 7.0, 4.0)
h = h - river_soft * carve - bank * 2.0
h = np.where(river_soft > 0.5, np.minimum(h, local_ground - carve * 0.8), h)

# clearing island inside the southern river loop
CL = (812.0, 537.0)
dcl = np.sqrt(((sx - CL[0]) / 20.0) ** 2 + ((sy - CL[1]) / 15.0) ** 2)
h = h * (1 - smoothstep(1.0, 0.6, dcl)) + (FLOOR + 6) * smoothstep(1.0, 0.6, dcl)

# waterfall notches cut into the rim (angles from the art)
FALLS = [("Waterfall_NW", 662, 315), ("Waterfall_N1", 785, 288), ("Waterfall_N2", 829, 274), ("Waterfall_E", 1040, 432)]
for _, fx, fy in FALLS:
    d = np.sqrt((sx - fx) ** 2 + (sy - fy) ** 2)
    notch = np.exp(-(d / 4.0) ** 2) * 45 * (cr > 0.95)
    h -= notch
    pool = np.exp(-(d / 9.0) ** 2) * (cr < 0.97)              # plunge pool at the base
    h -= pool * 8

h += fractal(h.shape, [(3, 0.35), (1.2, 0.12)], 5)           # micro detail
h = ndi.gaussian_filter(h, 0.7)

units = np.clip(32768 + h * UNITS_PER_M, 0, 65535).astype(np.uint16)
Image.fromarray(units).save(os.path.join(OUT, f"Heightmap_{RW}x{RH}.png"))
prev = ((h - h.min()) / (h.max() - h.min()) * 255).astype(np.uint8)
Image.fromarray(prev).resize((1344, 1008)).save(os.path.join(OUT, "Heightmap_Preview.png"))
Image.fromarray((river_soft > 0.5).astype(np.uint8) * 255).save(os.path.join(OUT, "River_Mask.png"))

# ---------------------------------------------------------------- splat layers
gy, gx = np.gradient(h, XY_CM / 100.0)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
greenish = (g > r + 6) & (g > b + 6)
dark_canopy = ndi.gaussian_filter((greenish & (lum < 95)).astype(np.float32), 8)
light_green = ndi.gaussian_filter((greenish & (lum >= 95)).astype(np.float32), 8)

LAYERS = ["Canopy", "RainforestFloor", "Clearing", "PlateauGrass", "MossyRock", "CliffRock", "Talus", "Mud", "RiverBed"]
W = {}
crater_floor = smoothstep(0.97, 0.94, cr)
W["CliffRock"] = smoothstep(42, 55, slope)
W["MossyRock"] = smoothstep(26, 38, slope) * (1 - W["CliffRock"])
flat = 1 - W["CliffRock"] - W["MossyRock"]
W["RiverBed"] = flat * smoothstep(0.55, 0.85, river_soft)
W["Mud"] = flat * np.clip(bank * 1.6 - W["RiverBed"], 0, 1)
rest = np.clip(flat - W["RiverBed"] - W["Mud"], 0, 1)
W["Talus"] = rest * crater_floor * smoothstep(0.86, 0.93, cr)
rest = np.clip(rest - W["Talus"], 0, 1)
clearing = np.maximum(smoothstep(1.0, 0.6, dcl), light_green * crater_floor * 0.8)
W["Clearing"] = rest * clearing
rest = np.clip(rest - W["Clearing"], 0, 1)
W["Canopy"] = rest * np.clip(crater_floor * (0.55 + dark_canopy) + (1 - crater_floor) * dark_canopy * 0.8, 0, 1)
rest = np.clip(rest - W["Canopy"], 0, 1)
W["RainforestFloor"] = rest * crater_floor
W["PlateauGrass"] = np.clip(rest - W["RainforestFloor"], 0, 1)
stack = np.stack([W[n] for n in LAYERS], 0)
stack /= np.maximum(stack.sum(0, keepdims=True), 1e-6)
w8 = np.round(stack * 255).astype(np.uint8)
for i, n in enumerate(LAYERS):
    Image.fromarray(w8[i]).save(os.path.join(OUT, "Splat", f"{i:02d}_{n}.png"))
PAL = np.array([(30, 85, 30), (70, 95, 40), (140, 180, 70), (150, 165, 80), (95, 110, 80),
                (115, 105, 95), (150, 140, 120), (100, 80, 55), (40, 120, 140)], np.float32)
prev = np.tensordot(stack.transpose(1, 2, 0), PAL, axes=1).astype(np.uint8)
Image.fromarray(prev).resize((1344, 1008)).save(os.path.join(OUT, "Splat_Preview.png"))

# ---------------------------------------------------------------- foliage density maps
dens = {
    "Trees_Emergent": W["Canopy"] * smoothstep(0.3, 0.8, dark_canopy + crater_floor * 0.3) * (slope < 30),
    "Trees_Canopy": (W["Canopy"] + 0.4 * W["RainforestFloor"]) * (slope < 35),
    "Understory_Ferns": (W["RainforestFloor"] + 0.6 * W["Canopy"] + 0.5 * W["MossyRock"]) * (slope < 40),
    "Vines_Cliff": W["CliffRock"] * crater_floor * (1 - smoothstep(0.98, 1.0, cr)),
    "Grass_Clearing": W["Clearing"] + 0.6 * W["PlateauGrass"],
    "Reeds_Riverbank": W["Mud"],
}
for n, d in dens.items():
    Image.fromarray((np.clip(d, 0, 1) * 255).astype(np.uint8)).resize((2017, 1513), Image.BILINEAR) \
        .save(os.path.join(OUT, "Density", f"{n}.png"))

# ---------------------------------------------------------------- features
def src_to_local(px, py):
    return (px * CM_PER_SRC_PX - origin_x) / XY_CM, (py * CM_PER_SRC_PX - origin_y) / XY_CM

def feature(kind, name, px, py, note=""):
    lx, ly = src_to_local(px, py)
    ix, iy = int(np.clip(lx, 0, RW - 1)), int(np.clip(ly, 0, RH - 1))
    return [kind, name, round(px * CM_PER_SRC_PX), round(py * CM_PER_SRC_PX), round(float(h[iy, ix]) * 100), note]

rows = []
for nm, fx, fy in FALLS:
    # top of fall = rim, bottom = plunge pool a little inward
    vx, vy = CRATER_C_SRC[0] - fx, CRATER_C_SRC[1] - fy
    vl = np.hypot(vx, vy)
    rows.append(feature("WaterfallTop", nm, fx - vx / vl * 3, fy - vy / vl * 3))
    rows.append(feature("WaterfallBase", nm, fx + vx / vl * 6, fy + vy / vl * 6))
MIST = [("Mist_W", 605, 480), ("Mist_NE", 925, 360), ("Mist_SE", 935, 560), ("Mist_E", 1000, 445), ("Mist_N", 820, 300)]
for nm, mx_, my_ in MIST:
    rows.append(feature("MistBank", nm, mx_, my_))
rows.append(feature("Landmark", "Starfall Spire (summit)", *SP))
rows.append(feature("Landmark", "Clearing Island", *CL))
lx_, ly_ = np.unravel_index(np.argmin(np.where(cr < 0.9, h, 1e9)), h.shape)
with open(os.path.join(OUT, "Features.csv"), "w", newline="") as f:
    wr = csv.writer(f)
    wr.writerow(["Type", "Name", "X_cm", "Y_cm", "Z_cm", "Note"])
    wr.writerows(rows)

info = {
    "heightmap": f"Heightmap_{RW}x{RH}.png",
    "resolution": [RW, RH], "components": [32, 24], "section_size_quads": 63, "sections_per_component": 2,
    "scale_cm": [XY_CM, XY_CM, Z_SCALE],
    "landscape_location_cm": [origin_x, origin_y, 0],
    "size_km": [round(span_x_cm / 1e5, 2), round(span_y_cm / 1e5, 2)],
    "height_range_m": [float(h.min()), float(h.max())],
    "crater_floor_m": FLOOR, "spire_summit_m": float(h[int(src_to_local(*SP)[1]), int(src_to_local(*SP)[0])]),
    "layers": LAYERS, "density_maps": list(dens),
    "layer_coverage_pct": {n: round(float(stack[i].mean() * 100), 2) for i, n in enumerate(LAYERS)},
}
json.dump(info, open(os.path.join(OUT, "Region_Info.json"), "w"), indent=2)

# ---------------------------------------------------------------- crater topo map
step = 3
hs = h[::step, ::step]
ext_km = [origin_x / 1e5, (origin_x + span_x_cm) / 1e5, (origin_y + span_y_cm) / 1e5, origin_y / 1e5]
cmap = LinearSegmentedColormap.from_list("rf", [(0, "#2d5a3a"), (0.12, "#4f8a4a"), (0.3, "#9bb86a"),
                                                (0.5, "#c8b878"), (0.7, "#a58260"), (1, "#f0ece6")])
rgb = LightSource(315, 40).shade(hs, cmap=cmap, vert_exag=1.0, blend_mode="soft", dx=XY_CM / 100 * step, dy=XY_CM / 100 * step,
                                 vmin=20, vmax=float(h.max()))
riv = (river_soft[::step, ::step] > 0.5)
rgb[riv] = rgb[riv] * 0.3 + np.array([0.25, 0.55, 0.75, 1]) * 0.7
fig, ax = plt.subplots(figsize=(20, 15), dpi=110)
ax.imshow(rgb, extent=ext_km)
xs_ = np.linspace(ext_km[0], ext_km[1], hs.shape[1])
ys_ = np.linspace(ext_km[3], ext_km[2], hs.shape[0])
sm_h = ndi.gaussian_filter(hs, 1.5)
ax.contour(xs_, ys_, sm_h, levels=np.arange(0, 1400, 10), colors="#3a2a18", linewidths=0.18, alpha=0.5)
ci = ax.contour(xs_, ys_, sm_h, levels=np.arange(50, 1400, 50), colors="#2a1a08", linewidths=0.6, alpha=0.8)
ax.clabel(ci, fmt="%d m", fontsize=6, inline=True)
for row in rows:
    kind, nm, X, Y = row[0], row[1], row[2] / 1e5, row[3] / 1e5
    style = {"WaterfallTop": ("v", "#7fd4ff", 10), "WaterfallBase": ("o", "#ffffff", 6),
             "MistBank": ("s", "#dddddd", 8), "Landmark": ("*", "#ffd24a", 16)}[kind]
    ax.plot(X, Y, marker=style[0], color=style[1], mec="black", ms=style[2])
    if kind != "WaterfallBase":
        ax.text(X + 0.04, Y - 0.04, f"{nm} ({row[4] / 100:.0f} m)", fontsize=9, weight="bold", color="white",
                bbox=dict(boxstyle="round,pad=0.2", fc=(0, 0, 0, 0.5), ec="none"))
ax.set_title(f"Starfall Crater Rainforest — {info['size_km'][0]} x {info['size_km'][1]} km · 1.6 m/vertex · contours 10 m (index 50 m) · world coords (km)",
             fontsize=13, family="serif")
ax.set_xlabel("World X (km)"); ax.set_ylabel("World Y (km)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "Topographic_Crater.png"))
print(json.dumps(info, indent=2))
