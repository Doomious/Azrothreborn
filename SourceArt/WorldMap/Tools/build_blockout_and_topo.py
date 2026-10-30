"""
From the generated world maps, builds:
  Output/Topographic_Map.png       contour + hillshade + hypsometric topo map with region labels
  Saved/Blockout/placements.json   primitive placements for the in-editor blockout preview
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
from matplotlib.colors import LinearSegmentedColormap, LightSource

OUT = sys.argv[1]            # SourceArt/WorldMap/Output
SAVED = sys.argv[2]          # <project>/Saved/Blockout
os.makedirs(SAVED, exist_ok=True)
info = json.load(open(os.path.join(OUT, "WorldMap_Info.json")))
LAYERS = info["layers"]
XY = info["scale_cm"][0]
UNITS_PER_M = 128.0 * 100.0 / info["scale_cm"][2]

hm = np.asarray(Image.open(os.path.join(OUT, info["heightmap"]))).astype(np.float32)
h_m = (hm - 32768.0) / UNITS_PER_M
HH, WW = h_m.shape
wx_km = (WW - 1) * XY / 1e5
wy_km = (HH - 1) * XY / 1e5

splat = np.stack([np.asarray(Image.open(os.path.join(OUT, "Splat", f"{i:02d}_{n}.png"))) for i, n in enumerate(LAYERS)], 0)
cls_full = splat.argmax(0)

# ------------------------------------------------------------------ topographic map
step = 2
h_s = h_m[::step, ::step]
ls = LightSource(azdeg=315, altdeg=40)
land_cmap = LinearSegmentedColormap.from_list("hyps", [
    (0.00, "#1b3a5c"), (0.12, "#3f7fa8"), (0.165, "#a8d4e0"), (0.168, "#c9d9a0"),
    (0.25, "#8fb26a"), (0.40, "#c8c07a"), (0.55, "#c79a5e"), (0.72, "#9c7656"),
    (0.86, "#d8d2cc"), (1.00, "#ffffff")])
vmin, vmax = -250, 1300
rgb = ls.shade(h_s, cmap=land_cmap, vert_exag=0.08, blend_mode="soft", vmin=vmin, vmax=vmax, dx=XY / 100 * step, dy=XY / 100 * step)

fig, ax = plt.subplots(figsize=(24, 16), dpi=110)
ax.imshow(rgb, extent=[0, wx_km, wy_km, 0])
ys = np.linspace(0, wy_km, h_s.shape[0])
xs = np.linspace(0, wx_km, h_s.shape[1])
smooth_h = ndi.gaussian_filter(h_s, 2)
ax.contour(xs, ys, smooth_h, levels=np.arange(50, 1300, 50), colors="#4a3520", linewidths=0.25, alpha=0.55)
idx = ax.contour(xs, ys, smooth_h, levels=np.arange(250, 1300, 250), colors="#3a2810", linewidths=0.8, alpha=0.8)
ax.clabel(idx, fmt="%d m", fontsize=7, inline=True)
ax.contour(xs, ys, smooth_h, levels=[0], colors="#0d2438", linewidths=1.1)
ax.contour(xs, ys, smooth_h, levels=[-100, -50], colors="#2a5a80", linewidths=0.4, alpha=0.6)

for name, (cx, cy, cz) in info["zone_centers_cm"].items():
    ax.text(cx / 1e5, cy / 1e5, name.upper(), ha="center", va="center", fontsize=13, weight="bold",
            color="white", family="serif",
            bbox=dict(boxstyle="round,pad=0.3", fc=(0, 0, 0, 0.45), ec="none"))
with open(os.path.join(OUT, "Emitters.csv")) as f:
    for row in csv.DictReader(f):
        if row["Type"] == "Settlement":
            ax.plot(float(row["X_cm"]) / 1e5, float(row["Y_cm"]) / 1e5, marker="o", ms=7, mfc="#ffd24a", mec="black")
peak = np.unravel_index(np.argmax(h_m), h_m.shape)
ax.plot(peak[1] * XY / 1e5, peak[0] * XY / 1e5, marker="^", ms=11, mfc="white", mec="black")
ax.text(peak[1] * XY / 1e5 + 0.15, peak[0] * XY / 1e5, f"{h_m.max():.0f} m", fontsize=9, weight="bold")
ax.set_xlabel("km (Unreal +X)")
ax.set_ylabel("km (Unreal +Y)")
ax.set_xticks(np.arange(0, wx_km + 0.01, 1))
ax.set_yticks(np.arange(0, wy_km + 0.01, 1))
ax.grid(color="white", alpha=0.15, linewidth=0.5)
ax.set_title(f"World Topography — {wx_km:.1f} x {wy_km:.1f} km · contours 50 m (index 250 m) · sea level 0 m",
             fontsize=15, family="serif")
sm = plt.cm.ScalarMappable(cmap=land_cmap, norm=plt.Normalize(vmin, vmax))
cb = fig.colorbar(sm, ax=ax, fraction=0.025, pad=0.01)
cb.set_label("Elevation (m)")
fig.tight_layout()
fig.savefig(os.path.join(OUT, "Topographic_Map.png"))
plt.close(fig)

# ------------------------------------------------------------------ blockout placements
CELL_CM = 16000.0           # 160 m columns
EXAG = 2.0                  # vertical exaggeration for readability
BOTTOM = -3000.0
rng = np.random.default_rng(7)
cell_px = CELL_CM / XY
nx, ny = int(WW // cell_px), int(HH // cell_px)
h_cell = ndi.zoom(ndi.gaussian_filter(h_m, cell_px / 3), (ny / HH, nx / WW), order=1)
cls_votes = np.zeros((len(LAYERS), ny, nx), np.float32)
for i in range(len(LAYERS)):
    cls_votes[i] = ndi.zoom(ndi.uniform_filter((cls_full == i).astype(np.float32), int(cell_px)), (ny / HH, nx / WW), order=0)
zone_img = np.asarray(Image.open(os.path.join(OUT, "Zones.png")))
zone_cell = ndi.zoom(zone_img, (ny / HH, nx / WW), order=0)
ZONES = info["zones"]
# small cliff outcrops shouldn't win whole 160 m cells over the surrounding canopy/grass
cls_votes[LAYERS.index("Rock")] *= 0.4
swamp_z = zone_cell == ZONES.index("Mosswarden Swamps")
cls_votes[LAYERS.index("Swamp")] += swamp_z * (cls_votes[LAYERS.index("Grass")] + cls_votes[LAYERS.index("Rock")])
cls_cell = cls_votes.argmax(0)

P = {}
def put(group, x, y, z, sx, sy, sz, mesh="Cube", yaw=0):
    P.setdefault(group, {"mesh": mesh, "items": []})["items"].append(
        [int(round(x)), int(round(y)), int(round(z)), round(float(sx), 3), round(float(sy), 3), round(float(sz), 3), int(round(yaw))])

L = {n: i for i, n in enumerate(LAYERS)}
tops = np.zeros((ny, nx))
for j in range(ny):
    for i in range(nx):
        c = LAYERS[cls_cell[j, i]]
        hm_ = h_cell[j, i]
        x, y = (i + 0.5) * CELL_CM, (j + 0.5) * CELL_CM
        if hm_ <= 0.5 and c in ("DeepWater", "ShallowWater"):
            if c == "ShallowWater" or hm_ > -40:
                put("ShallowWater", x, y, 30, CELL_CM / 100, CELL_CM / 100, 0.6)
            continue
        if c in ("DeepWater", "ShallowWater"):
            c = "Beach"
        top = max(hm_, 1.0) * 100 * EXAG
        tops[j, i] = top
        put(c, x, y, (top + BOTTOM) / 2, CELL_CM / 100, CELL_CM / 100, (top - BOTTOM) / 100)

        zone = ZONES[zone_cell[j, i]]
        if c == "ForestCanopy":
            grp = "Canopy_Rainforest" if zone == "Starfall Crater Rainforest" else "Canopy_Forest"
            for _ in range(3):
                r = rng.uniform(4800, 7000)
                ox, oy = rng.uniform(-0.3, 0.3, 2) * CELL_CM
                put(grp, x + ox, y + oy, top + r * 0.55, r / 50, r / 50, r / 50 * rng.uniform(0.8, 1.15), "Sphere")
            if rng.random() < 0.35:
                put("Trunk", x, y, top + 1500, 6, 6, 30, "Cylinder")
        elif c == "Grass" and zone in ("Emberwood Forest", "Stonevale Highlands", "Starfall Crater Rainforest", "Verdant Isles") and rng.random() < 0.3:
            r = rng.uniform(2200, 3400)
            put("Canopy_Forest", x + rng.uniform(-5000, 5000), y + rng.uniform(-5000, 5000), top + r * 0.5, r / 50, r / 50, r / 50, "Sphere")
        elif c == "Swamp" and rng.random() < 0.5:
            r = rng.uniform(2000, 3000)
            ox, oy = rng.uniform(-5000, 5000, 2)
            put("Canopy_Swamp", x + ox, y + oy, top + 2400 + r * 0.4, r / 50, r / 50, r / 80, "Sphere")
            put("Trunk", x + ox, y + oy, top + 1200, 5, 5, 24, "Cylinder")
        elif c in ("Mountain", "Snow") and rng.random() < 0.6:
            ph = rng.uniform(15000, 40000) * (1.6 if c == "Snow" else 1.0)
            put("Peak_" + c, x + rng.uniform(-3000, 3000), y + rng.uniform(-3000, 3000), top + ph / 2 - 500, rng.uniform(120, 190), rng.uniform(120, 190), ph / 100, "Cone")
        elif c == "DesertRock" and rng.random() < 0.4:
            ph = rng.uniform(6000, 16000)
            put("DesertRock", x, y, top + ph / 2, rng.uniform(60, 120), rng.uniform(60, 120), ph / 100, "Cube", rng.uniform(0, 90))
        elif c in ("Volcanic", "Blight") and rng.random() < 0.25:
            ph = rng.uniform(8000, 22000)
            put("Spire_" + c, x + rng.uniform(-4000, 4000), y + rng.uniform(-4000, 4000), top + ph / 2 - 500, rng.uniform(50, 110), rng.uniform(50, 110), ph / 100, "Cone")

def top_at(xcm, ycm):
    i = int(np.clip(xcm // CELL_CM, 0, nx - 1)); j = int(np.clip(ycm // CELL_CM, 0, ny - 1))
    return tops[j, i]

with open(os.path.join(OUT, "Emitters.csv")) as f:
    for row in csv.DictReader(f):
        x, y = float(row["X_cm"]), float(row["Y_cm"])
        t = top_at(x, y)
        kind = row["Type"]
        if kind == "Settlement":
            put("Settlement_Plaza", x, y, t + 150, 250, 250, 3, "Cylinder")
            for k in range(6):
                a = k / 6 * 2 * np.pi + rng.uniform(-0.2, 0.2)
                put("Settlement_House", x + np.cos(a) * 8500, y + np.sin(a) * 8500, t + 1500,
                    rng.uniform(25, 40), rng.uniform(25, 40), 30, "Cube", np.degrees(a))
            put("Beacon", x, y, t + 25000, 4, 4, 500, "Cylinder")
        elif kind == "Waterfall":
            put("Waterfall", x, y, t - 2500, 15, 15, 120, "Cube")
        elif kind == "LavaGlow":
            put("LavaPool", x, y, t + 80, 70, 70, 2, "Cylinder")
        elif kind == "BlightCrystal":
            for _ in range(3):
                ch = rng.uniform(8000, 18000)
                put("BlightCrystal", x + rng.uniform(-3000, 3000), y + rng.uniform(-3000, 3000), t + ch / 2,
                    rng.uniform(20, 40), rng.uniform(20, 40), ch / 100, "Cone")

ocean = {"x": wx_km * 1e5 / 2, "y": wy_km * 1e5 / 2, "sx": wx_km * 1e5 / 100 * 1.6, "sy": wy_km * 1e5 / 100 * 1.6}
labels = {n: [c[0], c[1], float(top_at(c[0], c[1]))] for n, c in info["zone_centers_cm"].items()}
json.dump({"cell_cm": CELL_CM, "exag": EXAG, "groups": P, "ocean": ocean, "labels": labels},
          open(os.path.join(SAVED, "placements.json"), "w"))
print({g: len(v["items"]) for g, v in P.items()}, "total", sum(len(v["items"]) for v in P.values()), "grid", nx, ny)
