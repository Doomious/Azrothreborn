"""
Starfall Crater v2 — walkable, dressed region.

Design (local metres, origin = region top-left, +x east, +y south; world cm = ORIGIN + local*100):
  * Crater floor ~55 m, gentle rolling ground (<12 deg), talus apron, sheer outer wall to the rim.
  * Two walkable entrances: the Southern Breach canyon (river exit) and the West Ledge Road cut into the wall.
  * Designed river network: four waterfalls -> braided channels -> loop around Clearing Island -> Breach.
  * Six outposts on flattened pads, joined by a path network with bridges at river crossings.
  * Foliage / rock scatter driven by density masks, with "negative" (no-spawn) space on paths, pads, rivers, cliffs.

Outputs -> SourceArt/Regions/StarfallCrater/v2/
  Heightmap_4033x3025.png, Splat/*.png, Splat_Packed_RGBA.png, Negative_Mask.png, Emitter_Map.png,
  Topographic_v2.png, Preview_v2.png, Region_v2.json
  Terrain/Tile_X_Y.obj, Water/Rivers.obj
Outputs -> Saved/Crater/  placement json consumed by the in-editor build script
"""
import json
import math
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import LightSource, LinearSegmentedColormap

OUT, SAVED = sys.argv[1], sys.argv[2]
for d in ("Splat", "Terrain", "Water"):
    os.makedirs(os.path.join(OUT, d), exist_ok=True)
os.makedirs(SAVED, exist_ok=True)

RW, RH, CELL = 4033, 3025, 1.6                 # landscape-ready grid (m)
ORIGIN_CM = (528000.0, 204400.0)
Z_SCALE = 512.0
UNITS_PER_M = 128.0 * 100.0 / Z_SCALE
W_M, H_M = (RW - 1) * CELL, (RH - 1) * CELL
rng = np.random.default_rng(77)

yy, xx = np.mgrid[0:RH, 0:RW].astype(np.float32)
X, Y = xx * CELL, yy * CELL

def fractal(scales, seed):
    g = np.random.default_rng(seed)
    out = np.zeros((RH, RW), np.float32)
    for sig, amp in scales:
        n = ndi.gaussian_filter(g.standard_normal((RH, RW)).astype(np.float32), sig)
        out += n / (n.std() + 1e-6) * amp
    return out

def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)

def src_px(px, py):                            # concept-art pixel -> local metres
    return (px * 1050.0 - ORIGIN_CM[0]) / 100.0, (py * 1050.0 - ORIGIN_CM[1]) / 100.0

# ------------------------------------------------------------------ crater frame
C = np.array(src_px(810, 425))
RX, RY = 2625.0, 1869.0
dx, dy = (X - C[0]) / RX, (Y - C[1]) / RY
ang = np.arctan2(dy, dx)
k = np.arange(1, 8)
ph = rng.uniform(0, 2 * np.pi, len(k))
wob = sum((0.035 / kk ** 0.9) * np.cos(kk * ang + p) for kk, p in zip(k, ph))
cr = np.sqrt(dx ** 2 + dy ** 2) / (1 + wob)

def ell(a_deg, r=1.0):
    a = math.radians(a_deg)
    return np.array([C[0] + RX * r * math.cos(a), C[1] + RY * r * math.sin(a)])

# ------------------------------------------------------------------ base terrain
FLOOR = 56.0
floor = FLOOR + fractal([(260, 3.5), (90, 1.6), (30, 0.5)], 1)
floor -= 5.0 * smoothstep(0.2, 0.9, (Y - C[1]) / RY) * (cr < 1)        # floor tilts gently to the south breach
rim_top = 360 + fractal([(260, 55), (60, 14)], 2) + 90 * np.clip(-dy, 0, 1) - 60 * np.clip(dy, 0, 1)
plateau = 260 + fractal([(300, 40), (80, 8)], 3) - 0.04 * np.maximum(cr - 1.0, 0) * 2600

# sheer walls with vertical buttresses/gullies: offset the wall radius by high-frequency angular noise
ga = np.random.default_rng(31)
groove = sum(ga.uniform(0.002, 0.005) / (1 + kk / 60) * np.cos(kk * ang + ga.uniform(0, 6.28)) for kk in range(24, 140, 7))
crw = cr + groove
wall = smoothstep(0.962, 0.992, crw) ** 0.8                     # near-vertical face, slight overhang feel at the top
talus = smoothstep(0.84, 0.962, crw) ** 1.6 * 30
inside = floor + talus + (rim_top - floor - talus) * wall
# flat forested shelf along the top of the rim, then the outer slope
outside = rim_top + (plateau - rim_top) * smoothstep(1.10, 1.30, cr)
h = np.where(crw < 1.0, inside, outside).astype(np.float32)
h += np.where((crw > 0.97) & (crw < 1.0), np.abs(fractal([(4, 1.0), (12, 1.5)], 32)) * 6, 0)   # rock strata relief

# central spire: tall, slender, ridged pyramid with a forested skirt
SP = np.array(src_px(797, 352))
su, sv = (X - SP[0]), (Y - SP[1])
rot = math.radians(18)
pu, pv = su * math.cos(rot) - sv * math.sin(rot), su * math.sin(rot) + sv * math.cos(rot)
d_rad = np.sqrt((su / 470.0) ** 2 + (sv / 560.0) ** 2)
d_pyr = np.maximum(np.abs(pu) / 430.0, np.abs(pv) / 500.0)        # four faces / four ridges
dsp = 0.55 * d_pyr + 0.45 * d_rad
sang = np.arctan2(sv, su)
gully = 1 - 0.07 * np.abs(np.sin(9 * sang + 1.3)) - 0.05 * np.abs(fractal([(6, 1.0)], 4))
SPIRE_H = 880.0
spire = SPIRE_H * np.clip(1 - dsp, 0, 1) ** 1.55 * gully + 55 * np.clip(1 - dsp / 1.45, 0, 1) ** 2
spire = np.zeros_like(h)          # the spire was removed: the crater centre is a large lake now (see "great lake" below)

# ------------------------------------------------------------------ polylines helpers
def densify(pts, step=4.0):
    pts = np.asarray(pts, float)
    # Catmull-Rom through control points
    P = np.vstack([pts[0], pts, pts[-1]])
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        n = max(2, int(np.linalg.norm(p2 - p1) / step))
        for t in np.linspace(0, 1, n, endpoint=False):
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2 + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-1])
    return np.array(out)

def raster_line(poly, values):
    """centreline raster: mask + value grid + index grid of nearest centreline."""
    m = np.zeros((RH, RW), bool)
    v = np.zeros((RH, RW), np.float32)
    ix = np.clip((poly[:, 0] / CELL).round().astype(int), 0, RW - 1)
    iy = np.clip((poly[:, 1] / CELL).round().astype(int), 0, RH - 1)
    m[iy, ix] = True
    v[iy, ix] = values
    return m, v

def corridor(polys_vals):
    m = np.zeros((RH, RW), bool)
    v = np.zeros((RH, RW), np.float32)
    for poly, vals in polys_vals:
        mm, vv = raster_line(poly, vals)
        v[mm] = vv[mm]
        m |= mm
    dist, (iy, ix) = ndi.distance_transform_edt(~m, return_indices=True)
    return dist * CELL, v[iy, ix]

def sample(arr, pts):
    return ndi.map_coordinates(arr, [pts[:, 1] / CELL, pts[:, 0] / CELL], order=1, mode="nearest")

def smooth1d(v, n):
    if n < 2:
        return v
    k_ = np.ones(n) / n
    pad = np.pad(v, n, mode="edge")
    return np.convolve(pad, k_, mode="same")[n:-n]

# ------------------------------------------------------------------ rivers
FALLS_ART = {"NW": src_px(662, 315), "N1": src_px(785, 288), "N2": src_px(829, 274), "E": src_px(1040, 432)}
# the painted fall marks sit just inside the crater; move each one out along its bearing to the actual rim crest
FALLS = {}
for _nm, _p in FALLS_ART.items():
    _a = math.degrees(math.atan2((_p[1] - C[1]) / RY, (_p[0] - C[0]) / RX))
    _cands = np.array([ell(_a, r) for r in np.linspace(0.97, 1.06, 60)])
    _z = sample(h, _cands)
    FALLS[_nm] = tuple(_cands[int(np.argmax(_z))])
def inward(p, d):
    v = C - np.array(p)
    return np.array(p) + v / np.linalg.norm(v) * d
ISLAND = np.array(src_px(812, 537))
RIVERS = {
    "West":   [inward(FALLS["NW"], 160), (1640, 1500), (1560, 2000), (1620, 2600), (1930, 3100), (2480, 3440), (2950, 3470)],
    "Spire_W": [inward(FALLS["N1"], 150), (2620, 1350), (2380, 1850), (2150, 2300), (1700, 2480)],
    "East":   [inward(FALLS["N2"], 150), (3720, 1380), (3930, 2000), (4120, 2620), (4010, 3120), (3600, 3440), (3480, 3470)],
    "East_Falls": [inward(FALLS["E"], 150), (5000, 2600), (4500, 2650), (4130, 2640)],
    "Loop_W": [(2950, 3470), (2960, 3660), (3080, 3830), (3200, 3880)],
    "Loop_E": [(3480, 3470), (3500, 3640), (3420, 3820), (3200, 3880)],
    "Outflow": [(3200, 3880), (3130, 4100), (3090, 4400), (3070, 4837)],
}
RIVER_W = {"West": 22, "Spire_W": 16, "East": 22, "East_Falls": 16, "Loop_W": 18, "Loop_E": 18, "Outflow": 30}
river_polys = []
for name, pts in RIVERS.items():
    poly = densify(pts, 3.0)
    river_polys.append((name, poly))

# Southern Breach canyon: cut through the south rim along the outflow
breach_poly = densify([(3150, 3950), (3110, 4150), (3085, 4450), (3070, 4837)], 3.0)
bd, _ = corridor([(breach_poly, np.zeros(len(breach_poly)))])
canyon_floor = np.interp(Y, [3950, 4300, 4837], [52, 44, 36]).astype(np.float32)
canyon = smoothstep(260, 70, bd)
h = h * (1 - canyon) + np.minimum(h, canyon_floor + 0.02 * bd) * canyon

# water surface height along each river (monotonic downhill), bed = surface - depth
river_info = []
for name, poly in river_polys:
    g = sample(h, poly)
    g = smooth1d(g, 40)
    surf = np.minimum.accumulate(np.minimum(g - 2.2, 54.0))       # never climbs downstream
    river_info.append((name, poly, surf))
# make joins consistent: clamp each river start to <= its source fall pool level (54)
rd, rsurf = corridor([(p, s) for _, p, s in river_info])
rw = np.zeros((RH, RW), np.float32)
for name, poly, _ in river_info:
    d_, _x = corridor([(poly, np.zeros(len(poly)))])
    rw = np.maximum(rw, (d_ < RIVER_W[name] * 0.5).astype(np.float32) * RIVER_W[name])
half_w = ndi.grey_dilation(rw, size=5) * 0.5
half_w = np.where(half_w > 0, half_w, 10.0)
river_core = rd < half_w
bank = smoothstep(half_w + 22, half_w, rd)
bed = rsurf - 1.6 - 0.8 * smoothstep(half_w, 0, rd)
h = np.where(river_core, np.minimum(h, bed), h * (1 - bank) + np.minimum(h, rsurf + 0.6 + (rd - half_w).clip(0) * 0.12) * bank)

# plunge pools + waterfall notches
for nm, p in FALLS.items():
    p = np.array(p)
    d = np.hypot(X - p[0], Y - p[1])
    h -= np.exp(-(d / 14.0) ** 2) * 40 * (cr > 0.96)
    pool_c = inward(p, 120)
    dp = np.hypot(X - pool_c[0], Y - pool_c[1])
    h = np.where(dp < 45, np.minimum(h, 51.0 - 2.5 * (1 - dp / 45)), h)

# ------------------------------------------------------------------ outposts (flattened pads) + paths
OUTPOSTS = {
    "Breach Gate":      np.array([3150.0, 3990.0]),
    "Clearing Island":  ISLAND.copy(),
    "Spire-Foot Shrine": np.array([3110.0, 2420.0]),
    "Falls Landing":    np.array([3250.0, 1080.0]),
    "West Grove":       np.array([1420.0, 2880.0]),
    "East Pools":       inward(FALLS["E"], 330),
}
PAD_R = {"Breach Gate": 45, "Clearing Island": 55, "Spire-Foot Shrine": 50, "Falls Landing": 45, "West Grove": 60, "East Pools": 45}

# West Ledge Road: bench cut into the wall, rim (a=214) down to the talus (a=162)
ledge_pts, ledge_z = [], []
a_top, a_bot = 214.0, 160.0
n_l = 700
for i in range(n_l):
    t = i / (n_l - 1)
    a = a_top + (a_bot - a_top) * t
    top = ell(a, 1.0);
    ztop = float(sample(h, np.array([ell(a, 1.03)]))[0])
    zbot = FLOOR + 14
    z = ztop + (zbot - ztop) * t
    # find radius on the wall where the original surface equals z (bench sits on the face)
    rs = np.linspace(0.90, 1.04, 160)
    zs = sample(h, np.array([ell(a, r) for r in rs]))
    j = int(np.argmin(np.abs(zs - z)))
    ledge_pts.append(ell(a, rs[j] - 0.004))
    ledge_z.append(z)
ledge_pts = np.array(ledge_pts)
ledge_z = smooth1d(np.array(ledge_z), 15)
RIM_OVERLOOK = ell(a_top, 1.035)

PATHS = {
    "Breach_to_Island":  [OUTPOSTS["Breach Gate"], (3190, 3860), OUTPOSTS["Clearing Island"]],
    "Island_to_Shrine":  [OUTPOSTS["Clearing Island"], (3290, 3300), (3200, 2900), OUTPOSTS["Spire-Foot Shrine"]],
    "Shrine_to_Falls":   [OUTPOSTS["Spire-Foot Shrine"], (3520, 2250), (3650, 1750), (3500, 1300), OUTPOSTS["Falls Landing"]],
    "Shrine_to_West":    [OUTPOSTS["Spire-Foot Shrine"], (2700, 2600), (2150, 2780), (1750, 2850), OUTPOSTS["West Grove"]],
    "West_to_Ledge":     [OUTPOSTS["West Grove"], (1150, 2980), tuple(ledge_pts[-1])],
    "Shrine_to_East":    [OUTPOSTS["Spire-Foot Shrine"], (3700, 2620), (4350, 2760), (4900, 2700), OUTPOSTS["East Pools"]],
    "Breach_out":        [OUTPOSTS["Breach Gate"], (3165, 4200), (3120, 4500), (3105, 4837)],
}
path_polys = []
for nm, pts in PATHS.items():
    pts = [np.array(p, float) for p in pts]
    # footpaths meander: jitter interior control points sideways, then follow the ground (light smoothing only)
    jit = np.random.default_rng(sum(map(ord, nm)))
    wavy = [pts[0]]
    for a_, b_ in zip(pts[:-1], pts[1:]):
        seg = b_ - a_
        n_ = max(1, int(np.linalg.norm(seg) / 70))
        perp = np.array([-seg[1], seg[0]]) / (np.linalg.norm(seg) + 1e-6)
        for t in np.linspace(0, 1, n_ + 1)[1:]:
            off = jit.uniform(-9, 9) if t < 1 else 0.0
            wavy.append(a_ + seg * t + perp * off)
    poly = densify(wavy, 2.0)
    g = smooth1d(sample(h, poly), 9)
    path_polys.append((nm, poly, g))
LEDGE = (ledge_pts, ledge_z)       # carved separately below: a cliff bench must be wider than the 4 m mesh grid

# pads
pad_mask = np.zeros((RH, RW), np.float32)
for nm, p in OUTPOSTS.items():
    d = np.hypot(X - p[0], Y - p[1])
    z0 = float(np.median(sample(h, np.array([p + [math.cos(a) * PAD_R[nm] * 0.6, math.sin(a) * PAD_R[nm] * 0.6] for a in np.linspace(0, 6.28, 24)]))))
    if nm == "Clearing Island":
        z0 = max(z0, 54.5)
    w_ = smoothstep(PAD_R[nm] + 35, PAD_R[nm], d)
    h = h * (1 - w_) + z0 * w_
    pad_mask = np.maximum(pad_mask, smoothstep(PAD_R[nm] + 5, PAD_R[nm] - 5, d))
    OUTPOSTS[nm] = np.array([p[0], p[1], z0])

pd, pz = corridor([(p, z) for _, p, z in path_polys])
PATH_HALF = 1.2
edge_noise = fractal([(2.5, 0.45), (8, 0.35)], 21)                  # ragged, trodden edges
pdn = pd + edge_noise
path_core = smoothstep(PATH_HALF + 0.9, PATH_HALF - 0.4, pdn)
path_blend = smoothstep(PATH_HALF + 3.5, PATH_HALF, pd)
over_water = river_core & (pz < rsurf + 0.5)
h = np.where(over_water, h, h * (1 - path_blend) + (pz - 0.10 * path_core) * path_blend)

# West Ledge Road: a 10 m bench cut into the crater wall (flat across, gentle grade along)
ld, lz = corridor([LEDGE])
ledge_flat = smoothstep(9.0, 5.0, ld)
h = h * (1 - ledge_flat) + lz * ledge_flat
ledge_core = smoothstep(4.5, 3.0, ld + edge_noise * 0.5)
path_core = np.maximum(path_core, ledge_core)
path_blend = np.maximum(path_blend, ledge_flat)
pd = np.minimum(pd, ld)
path_polys.append(("Ledge_Road", LEDGE[0], LEDGE[1]))

# ------------------------------------------------------------------ small lakes in floor hollows, fed by spring creeks
hollow = h - ndi.gaussian_filter(h, 25)                          # negative = local depression
dist_pad = np.min([np.hypot(X - p[0], Y - p[1]) for p in OUTPOSTS.values()], axis=0)
# great lake where the spire stood: wobbly ellipse, ~9 m deep, shelving shore
BRX, BRY = 440.0, 520.0
bth = np.arctan2((Y - SP[1]) / BRY, (X - SP[0]) / BRX)
brr = np.hypot((X - SP[0]) / BRX, (Y - SP[1]) / BRY) / (1 + 0.12 * np.cos(3 * bth + 0.7) + 0.07 * np.cos(5 * bth + 2.1))
bring = np.array([SP + np.array([math.cos(a) * BRX, math.sin(a) * BRY]) * 1.15 for a in np.linspace(0, 6.28, 64)])
BIG_Z = float(np.percentile(sample(h, bring), 25)) - 0.5 - 0.7      # sunk ~2 ft below the old level
# coastline: the land shelves down to the water at a gentle ~4.5% grade over ~200 m (cut where high, filled where low),
# and keeps shelving under the surface before dropping to the 9 m deep middle
coast_z = BIG_Z - 0.25 + (brr - 1) * 480.0 * 0.045
coast = smoothstep(1.45, 1.0, brr)
h = np.where(brr < 1, BIG_Z - 0.25 - 9.0 * np.clip(1 - brr ** 2, 0, 1) ** 1.3,
             h * (1 - coast) + coast_z * coast)
lake_ok = (cr < 0.85) & (brr > 1.9) & (rd > half_w + 110) & (pd > 70) & (dist_pad > 200)
lg = np.random.default_rng(55)
cy_, cx_ = np.nonzero(lake_ok[::25, ::25])
cand = np.column_stack([cx_ * 25 * CELL, cy_ * 25 * CELL])
score = sample(hollow, cand) + lg.uniform(0, 1.2, len(cand))
LAKES = [{"c": SP.copy(), "R": 480.0, "z": BIG_Z, "big": True}]
for i in np.argsort(score):
    p = cand[i]
    if all(np.hypot(*(p - q["c"])) > 560 for q in LAKES):
        LAKES.append({"c": p, "R": float(lg.uniform(30, 58)), "ph": lg.uniform(0, 6.28, 2)})
    if len(LAKES) == 8:
        break
lake_mask = np.zeros((RH, RW), bool)
lake_lvl = np.full((RH, RW), -1e3, np.float32)
lake_mask = brr < 1
lake_lvl = np.where(brr < 1.25, BIG_Z, -1e3).astype(np.float32)
for L_ in LAKES[1:]:
    c, R = L_["c"], L_["R"]
    th = np.arctan2(Y - c[1], X - c[0])
    rr = np.hypot(X - c[0], Y - c[1]) / (R * (1 + 0.2 * np.cos(2 * th + L_["ph"][0]) + 0.1 * np.cos(3 * th + L_["ph"][1])))
    ring = np.array([c + np.array([math.cos(a), math.sin(a)]) * R * 1.15 for a in np.linspace(0, 6.28, 48)])
    zs = float(np.percentile(sample(h, ring), 20)) - 0.4
    L_["z"] = zs
    basin = zs - 2.6 * np.clip(1 - rr ** 2, 0, 1) ** 0.6 - 0.3
    shore = smoothstep(1.6, 1.0, rr)
    h = np.where(rr < 1, np.minimum(h, basin), h * (1 - shore) + np.maximum(np.minimum(h, zs + 0.35 + (rr - 1) * R * 0.12), zs + 0.3) * shore)
    lake_mask |= rr < 1
    lake_lvl = np.where(rr < 1.25, np.maximum(lake_lvl, zs), lake_lvl)

def meander(pts, seed, amp=13.0, seg_len=32.0):
    g_ = np.random.default_rng(seed)
    out = [np.array(pts[0], float)]
    for a_, b_ in zip(pts[:-1], pts[1:]):
        a_, b_ = np.array(a_, float), np.array(b_, float)
        seg = b_ - a_
        n_ = max(1, int(np.linalg.norm(seg) / seg_len))
        perp = np.array([-seg[1], seg[0]]) / (np.linalg.norm(seg) + 1e-6)
        for t in np.linspace(0, 1, n_ + 1)[1:]:
            out.append(a_ + seg * t + perp * (g_.uniform(-amp, amp) if t < 1 else 0.0))
    return densify(out, 2.0)

CREEKS = []           # (poly, surface)
for li, L_ in enumerate(LAKES):
    c, R, zs = L_["c"], L_["R"], L_["z"]
    # spring creeks: pick sources uphill whose straight run needs the shallowest trench
    opts = []
    for a in np.linspace(0, 360, 16, endpoint=False):
        for dist in ((R + 260, R + 420, R + 600) if L_.get("big") else (320, 450, 600)):
            s = c + np.array([math.cos(math.radians(a)), math.sin(math.radians(a))]) * dist
            if not (0 < s[0] < W_M and 0 < s[1] < H_M):
                continue
            if sample((cr < 0.9).astype(np.float32) * (spire < 30) * (rd > half_w + 30) * (dist_pad > 120), np.array([s]))[0] < 0.5:
                continue
            line = densify([s, c + (s - c) / np.linalg.norm(s - c) * R * 0.6], 6.0)
            g = sample(h, line)
            surf = np.maximum(np.minimum.accumulate(g - 0.5), zs)
            trench = float(np.max(g - surf))
            if g[0] > zs + 1.5:
                opts.append((trench - 0.004 * (g[0] - zs), a, s))
    opts.sort(key=lambda o: o[0])
    used = []
    for tr, a, s in opts:
        if tr > 3.0 or any(abs((a - u + 180) % 360 - 180) < 70 for u in used):
            continue
        used.append(a)
        poly = meander([s, (s + c) / 2, c + (s - c) / np.linalg.norm(s - c) * R * 0.6], 300 + li * 7 + len(used))
        g = smooth1d(sample(h, poly), 5)
        CREEKS.append((poly, np.maximum(np.minimum.accumulate(g - 0.5), zs)))
        if len(used) == (4 if L_.get("big") else 2):
            break
    # outflow to the nearest river
    rmask_pts = np.column_stack(np.nonzero(river_core[::4, ::4]))[:, ::-1] * 4 * CELL
    j = int(np.argmin(np.hypot(rmask_pts[:, 0] - c[0], rmask_pts[:, 1] - c[1])))
    tgt = rmask_pts[j]
    if np.hypot(*(tgt - c)) < 1100:
        start = c + (tgt - c) / np.linalg.norm(tgt - c) * R * 0.6
        poly = meander([start, (start + tgt) / 2, tgt], 400 + li)
        g = smooth1d(sample(h, poly), 5)
        rs_end = float(sample(rsurf, np.array([tgt]))[0])
        CREEKS.append((poly, np.maximum(np.minimum.accumulate(np.minimum(g - 0.5, zs)), rs_end)))
cd, csurf = corridor(CREEKS) if CREEKS else (np.full((RH, RW), 1e4, np.float32), np.zeros((RH, RW), np.float32))
CREEK_HALF = 4.0 + 1.5 * (fractal([(60, 1.0)], 41) * 0.5 + 0.5)
creek_core = (cd < CREEK_HALF) & ~lake_mask & ~river_core
cbank = smoothstep(CREEK_HALF + 16, CREEK_HALF, cd) * ~lake_mask * ~river_core
cbed = csurf - 0.25 - 0.45 * smoothstep(CREEK_HALF, 0, cd) ** 0.7
ford = smoothstep(3.5, 1.5, pd)                                                   # shallow fords where footpaths cross
h_c = np.where(creek_core, np.minimum(h, cbed), h * (1 - cbank) + np.minimum(h, csurf + 0.2 + np.clip(cd - CREEK_HALF, 0, None) * 0.12) * cbank)
h = h_c * (1 - ford) + np.maximum(h_c, h - 0.3) * ford
wet_core = river_core | creek_core | lake_mask
lake_d = ndi.distance_transform_edt(~lake_mask) * CELL
wdist = np.minimum.reduce([np.clip(rd - half_w, 0, None), np.clip(cd - CREEK_HALF, 0, None), lake_d])
wbank = np.maximum(bank, np.maximum(cbank, smoothstep(10, 0, lake_d) * ~lake_mask))

h += fractal([(3, 0.12), (1.2, 0.05)], 9) * (1 - path_core) * (~wet_core)
h = ndi.gaussian_filter(h, 0.6)

# ------------------------------------------------------------------ natural shorelines
# one smoothed water level per water cell (no stair-steps along creeks), then every bank within 14 m of the water is lifted
# to sit just above that level: the waterline becomes the smooth intersection of flat water with gently rising ground
surf_core = np.where(lake_mask, lake_lvl, np.where(river_core, rsurf, csurf)).astype(np.float32)
wc = wet_core.astype(np.float32)
surf_sm = np.where(lake_mask, lake_lvl, ndi.gaussian_filter(surf_core * wc, 5) / np.maximum(ndi.gaussian_filter(wc, 5), 1e-4)).astype(np.float32)
wd_px, (wiy, wix) = ndi.distance_transform_edt(~wet_core, return_indices=True)
surf_near = surf_sm[wiy, wix]
wd_m = wd_px * CELL
lift = smoothstep(14.0, 0.0, wd_m) * (~wet_core)
h = h + lift * np.clip(surf_near + 0.15 + wd_m * 0.04 - h, 0, None)

# ------------------------------------------------------------------ slope, splat, negatives
gy, gx = np.gradient(h, CELL)
slope = np.degrees(np.arctan(np.hypot(gx, gy)))
crater_in = cr < 0.97
LAYERS = ["ForestFloor", "Moss", "Grass", "Path", "Mud", "RiverBed", "Talus", "Cliff"]
Wt = {}
Wt["Cliff"] = smoothstep(36, 46, slope)
rest = 1 - Wt["Cliff"]
Wt["RiverBed"] = rest * wet_core
rest = rest - Wt["RiverBed"]
beach = smoothstep(0.94, 1.0, brr) * smoothstep(1.13, 1.04, brr) * (0.75 + 0.25 * fractal([(5, 1.0)], 17))   # gravel/sand shoreline
Wt["Path"] = rest * np.maximum(np.maximum(path_core, beach), pad_mask * 0.25 * smoothstep(0.45, 0.6, fractal([(10, 1.0)], 16) * 0.5 + 0.5))
rest = rest - Wt["Path"]
# wet ground: mud pans in every hollow plus scattered puddly patches across the forest floor
mudpatch = np.maximum(smoothstep(-0.12, -0.55, hollow), smoothstep(0.6, 0.74, fractal([(22, 1.0), (6, 0.4)], 14) * 0.5 + 0.5) * 0.85)
mudpatch *= crater_in * (slope < 14) * (1 - path_core)
Wt["Mud"] = rest * np.clip(np.maximum.reduce([bank * 1.2, wbank * 0.9, mudpatch]) * (0.75 + 0.25 * fractal([(6, 1.0)], 12)), 0, 1)
rest = rest - Wt["Mud"]
Wt["Talus"] = rest * smoothstep(0.86, 0.94, cr) * crater_in + rest * smoothstep(24, 34, slope) * (1 - crater_in)
rest = rest - Wt["Talus"]
clear = smoothstep(0.35, 0.65, fractal([(120, 1.0)], 10) * 0.5 + 0.5) * 0.6 + smoothstep(140, 60, np.min([np.hypot(X - p[0], Y - p[1]) for p in OUTPOSTS.values()], axis=0))
# grass spills over the floor in drifts and rings every shoreline; moss carpets the shaded, damp ground
shore = smoothstep(26, 6, wdist) * (~wet_core)
drift = smoothstep(0.42, 0.62, fractal([(70, 1.0), (14, 0.35)], 13) * 0.5 + 0.5) * 0.55
grass = np.clip(np.maximum.reduce([clear, shore * 0.8, drift]) * crater_in + (1 - crater_in) * 0.75, 0, 1)
Wt["Grass"] = rest * grass
rest = rest - Wt["Grass"]
# moss: broad carpets + distinct cushion patches + everything near water and around the mud
clumps = smoothstep(0.5, 0.64, fractal([(5, 1.0), (2, 0.35)], 15) * 0.5 + 0.5)
moss = np.clip(smoothstep(0.2, 0.5, fractal([(40, 1.0), (9, 0.3)], 11) * 0.5 + 0.5) + clumps * 0.8 + smoothstep(40, 10, wdist) * 0.6
               + ndi.gaussian_filter(mudpatch, 6) * 0.7, 0, 1)
Wt["Moss"] = rest * moss
Wt["ForestFloor"] = np.clip(rest - Wt["Moss"], 0, 1)
stack = np.clip(np.stack([Wt[n] for n in LAYERS]), 0, None)
stack /= np.maximum(stack.sum(0, keepdims=True), 1e-6)
for i, n in enumerate(LAYERS):
    Image.fromarray(np.round(stack[i] * 255).astype(np.uint8)).save(os.path.join(OUT, "Splat", f"{i:02d}_{n}.png"))
L = {n: stack[i] for i, n in enumerate(LAYERS)}
packed = np.stack([L["Cliff"] + L["Talus"] * 0.6, L["Path"], L["Grass"] + L["Moss"] * 0.35, np.clip(L["Mud"] + L["RiverBed"], 0, 1)], -1)
Image.fromarray((np.clip(packed, 0, 1) * 255).astype(np.uint8)).resize((2048, 1536), Image.BILINEAR).save(os.path.join(OUT, "Splat_Packed_RGBA.png"))

# ------------------------------------------------------------------ ruins + campfires: at the old camp clearings and other open glades
rg = np.random.default_rng(808)
SITES = [(nm, p[:2].copy(), PAD_R[nm]) for nm, p in OUTPOSTS.items() if nm != "Breach Gate"]
glade = ndi.gaussian_filter(L["Grass"] * crater_in * (slope < 8) * (wdist > 35) * (brr > 1.5), 8)
gy_, gx_ = np.nonzero((glade > 0.35)[::20, ::20])
cands = np.column_stack([gx_ * 20 * CELL, gy_ * 20 * CELL])
rg.shuffle(cands)
for c in cands:
    if all(np.hypot(*(c - q[1])) > 520 for q in SITES) and sample(dist_pad, np.array([c]))[0] > 300:
        SITES.append(("Glade %d" % len(SITES), c, 30))
    if len(SITES) >= 15:
        break
RUINS, CAMPFIRES = [], []
def piece(mesh, site_c, yaw0, lx, ly, yaw=0.0, s=1.0, sink=0.25, pitch=0.0, roll=0.0):
    ca, sa = math.cos(math.radians(yaw0)), math.sin(math.radians(yaw0))
    q = site_c + np.array([lx * ca - ly * sa, lx * sa + ly * ca])
    z = float(sample(h, np.array([q]))[0]) - sink
    RUINS.append({"mesh": mesh, "loc": [ORIGIN_CM[0] + q[0] * 100, ORIGIN_CM[1] + q[1] * 100, z * 100],
                  "yaw": float(yaw0 + yaw), "pitch": pitch, "roll": roll, "scale": s})
for k, (nm, c, R) in enumerate(SITES):
    yaw0 = rg.uniform(0, 360)
    kind = ["hall", "colonnade", "keep"][k % 3]
    off = 10.0 if nm in OUTPOSTS else 0.0                 # ruins sit at the edge of an old camp clearing, the fire in the middle
    if kind == "hall":                                    # roofless hall: broken perimeter walls, arch doorway, inner columns
        for lx, ly, yw, m_ in ((off, -6, 0, "SM_Ruin_Wall6"), (off + 6, -6, 0, "SM_Ruin_WallLow"), (off + 9.4, -2.5, 90, "SM_Ruin_Wall6"),
                               (off + 9.4, 3, 90, "SM_Ruin_WallLow"), (off + 3, 6, 180, "SM_Ruin_WallArch"), (off - 3.4, 2, 270, "SM_Ruin_Corner")):
            if rg.random() < 0.85:
                piece(m_, c, yaw0, lx, ly, yw + rg.uniform(-3, 3))
        for j in range(3):
            piece(rg.choice(["SM_Ruin_Column", "SM_Ruin_ColumnBroken"]), c, yaw0, off + 1 + j * 3, 0, rg.uniform(0, 90))
        piece("SM_Ruin_Floor", c, yaw0, off + 3, 0, rg.uniform(-5, 5), sink=0.15)
    elif kind == "colonnade":                             # a row of columns, some fallen, with a wall fragment behind
        for j in range(6):
            r_ = rg.random()
            m_ = "SM_Ruin_Column" if r_ < 0.4 else ("SM_Ruin_ColumnBroken" if r_ < 0.8 else "SM_Ruin_ColumnFallen")
            piece(m_, c, yaw0, off - 7 + j * 3.2, -4, rg.uniform(0, 360) if m_ == "SM_Ruin_ColumnFallen" else rg.uniform(0, 90))
        piece("SM_Ruin_Wall6", c, yaw0, off, -8.5, rg.uniform(-4, 4))
        piece("SM_Ruin_WallArch", c, yaw0, off + 6.5, -8.5, rg.uniform(-4, 4))
    else:                                                 # small keep: four broken corners around a rubble-filled floor
        for j, (lx, ly) in enumerate(((-4, -4), (4, -4), (4, 4), (-4, 4))):
            if rg.random() < 0.9:
                piece("SM_Ruin_Corner", c, yaw0, off + lx, ly, 90 * j + 90)
        piece("SM_Ruin_Floor", c, yaw0, off, 0, sink=0.15)
    for j in range(rg.integers(3, 7)):                    # rubble and loose drums scattered around
        a, r_ = rg.uniform(0, 6.28), rg.uniform(4, 15)
        piece(rg.choice(["SM_Ruin_Rubble", "SM_Ruin_Rubble", "SM_Ruin_ColumnFallen"]), c, yaw0, off + math.cos(a) * r_, math.sin(a) * r_,
              rg.uniform(0, 360), s=rg.uniform(0.8, 1.2), sink=0.3)
    if nm in OUTPOSTS or k % 2 == 0:                      # campfire in the clearing (every camp + every other glade)
        q = c + (np.array([-9.0, 0]) if nm not in OUTPOSTS else np.zeros(2))
        CAMPFIRES.append([ORIGIN_CM[0] + q[0] * 100, ORIGIN_CM[1] + q[1] * 100, float(sample(h, np.array([q]))[0]) * 100, float(rg.uniform(0, 360))])
ruin_mask = np.zeros((RH, RW), np.float32)
for nm, c, R in SITES:
    ruin_mask = np.maximum(ruin_mask, smoothstep(30, 22, np.hypot(X - c[0], Y - c[1])))
negative = np.clip(np.maximum.reduce([path_blend * 0.999, pad_mask, wet_core.astype(np.float32), bank * 0.7, cbank * 0.5, Wt["Cliff"], ruin_mask]), 0, 1)
Image.fromarray((negative * 255).astype(np.uint8)).save(os.path.join(OUT, "Negative_Mask.png"))

units = np.clip(32768 + h * UNITS_PER_M, 0, 65535).astype(np.uint16)
Image.fromarray(units).save(os.path.join(OUT, f"Heightmap_{RW}x{RH}.png"))

# ------------------------------------------------------------------ terrain tiles (OBJ, 4 m grid, cm, tile-local)
STEP = 4.0
TX, TY = 8, 6
sub = max(1, int(round(STEP / CELL)))
gxs = np.arange(0, W_M + 0.01, STEP)
gys = np.arange(0, H_M + 0.01, STEP)
HG = ndi.map_coordinates(h, np.meshgrid(gys / CELL, gxs / CELL, indexing="ij"), order=1)
nxv, nyv = len(gxs), len(gys)
tiles = []
xb = np.linspace(0, nxv - 1, TX + 1).round().astype(int)
yb = np.linspace(0, nyv - 1, TY + 1).round().astype(int)
for ty in range(TY):
    for tx in range(TX):
        x0, x1, y0, y1 = xb[tx], xb[tx + 1], yb[ty], yb[ty + 1]
        sx, sy = gxs[x0:x1 + 1], gys[y0:y1 + 1]
        hz = HG[y0:y1 + 1, x0:x1 + 1]
        ox, oy = gxs[x0] * 100, gys[y0] * 100
        ny_, nx_ = hz.shape
        name = f"Tile_{tx}_{ty}"
        with open(os.path.join(OUT, "Terrain", name + ".obj"), "w") as f:
            f.write(f"# Starfall crater terrain tile {name}\n")
            VX, VY = np.meshgrid(sx * 100 - ox, sy * 100 - oy)
            for vx_, vy_, vz_ in zip(VX.ravel(), VY.ravel(), (hz * 100).ravel()):
                f.write(f"v {vx_:.1f} {vy_:.1f} {vz_:.1f}\n")
            UX, UY = np.meshgrid(sx / W_M, sy / H_M)
            for u_, v_ in zip(UX.ravel(), UY.ravel()):
                f.write(f"vt {u_:.6f} {1 - v_:.6f}\n")
            gyy, gxx = np.gradient(hz, STEP)
            nrm = np.dstack([-gxx, -gyy, np.ones_like(hz)])
            nrm /= np.linalg.norm(nrm, axis=2, keepdims=True)
            for n_ in nrm.reshape(-1, 3):
                f.write(f"vn {n_[0]:.4f} {n_[1]:.4f} {n_[2]:.4f}\n")
            idx = np.arange(ny_ * nx_).reshape(ny_, nx_) + 1
            a_, b_, c_, d_ = idx[:-1, :-1].ravel(), idx[:-1, 1:].ravel(), idx[1:, 1:].ravel(), idx[1:, :-1].ravel()
            for A, B, Cc, D in zip(a_, b_, c_, d_):
                f.write(f"f {A}/{A}/{A} {D}/{D}/{D} {Cc}/{Cc}/{Cc}\nf {A}/{A}/{A} {Cc}/{Cc}/{Cc} {B}/{B}/{B}\n")
        tiles.append({"name": name, "loc": [ORIGIN_CM[0] + ox, ORIGIN_CM[1] + oy, 0]})

# river water ribbons: one OBJ, world-relative to ORIGIN
# terrain as the 4 m mesh actually renders it (bilinear between grid points) -- water edges are tucked just under this
h_mesh = ndi.map_coordinates(HG, [yy * CELL / STEP, xx * CELL / STEP], order=1).astype(np.float32)
wmask = ndi.binary_dilation(river_core, iterations=8)
for nm, p in FALLS.items():
    pc = inward(p, 120)
    wmask |= np.hypot(X - pc[0], Y - pc[1]) < 48
ws = 2
wm = wmask[::ws, ::ws]
wsurf = surf_near[::ws, ::ws].copy()
for nm, p in FALLS.items():
    pc = inward(p, 120)
    pool = np.hypot(X - pc[0], Y - pc[1])[::ws, ::ws] < 48
    wsurf = np.where(pool, np.maximum(wsurf, 50.6), wsurf)
# flow direction baked into the UVs (u, v = 0.5 + 0.5 * downstream dir) so the water material can scroll ripples downstream
def flow_angles(polys):
    vals = []
    for poly in polys:
        d = np.gradient(poly, axis=0)
        vals.append((poly, np.arctan2(d[:, 1], d[:, 0])))
    return corridor(vals)[1]
r_ang = flow_angles([p for _, p, _ in river_info])
c_ang = flow_angles([p for p, _ in CREEKS]) if CREEKS else np.zeros((RH, RW), np.float32)
vid = -np.ones(wm.shape, int)
ys_, xs_ = np.nonzero(wm)
vid[ys_, xs_] = np.arange(len(ys_)) + 1
with open(os.path.join(OUT, "Water", "Rivers.obj"), "w") as f:
    for y_, x_ in zip(ys_, xs_):
        f.write(f"v {x_ * ws * CELL * 100:.1f} {y_ * ws * CELL * 100:.1f} {wsurf[y_, x_] * 100:.1f}\n")
    for y_, x_ in zip(ys_, xs_):
        a = r_ang[y_ * ws, x_ * ws]
        f.write(f"vt {0.5 + 0.5 * math.cos(a):.4f} {1 - (0.5 + 0.5 * math.sin(a)):.4f}\n")
    f.write("vn 0 0 1\n")
    for y_, x_ in zip(ys_, xs_):
        if y_ + 1 < wm.shape[0] and x_ + 1 < wm.shape[1]:
            a_, b_, c_, d_ = vid[y_, x_], vid[y_, x_ + 1], vid[y_ + 1, x_ + 1], vid[y_ + 1, x_]
            if min(a_, b_, c_, d_) > 0:
                f.write(f"f {a_}/{a_}/1 {d_}/{d_}/1 {c_}/{c_}/1\nf {a_}/{a_}/1 {c_}/{c_}/1 {b_}/{b_}/1\n")

# creek + lake water: one OBJ at full grid resolution (creeks are only a few metres wide)
cwm = ndi.binary_dilation(creek_core | lake_mask, iterations=8) & ~ndi.binary_dilation(river_core, iterations=1)
cws = np.where(lake_lvl > -100, lake_lvl, surf_near).astype(np.float32)
still = lake_lvl > -100                                   # lakes are still water (flow 0), creeks run downstream
cvid = -np.ones(cwm.shape, int)
ys_, xs_ = np.nonzero(cwm)
cvid[ys_, xs_] = np.arange(len(ys_)) + 1
with open(os.path.join(OUT, "Water", "Creeks.obj"), "w") as f:
    for y_, x_ in zip(ys_, xs_):
        f.write(f"v {x_ * CELL * 100:.1f} {y_ * CELL * 100:.1f} {cws[y_, x_] * 100:.1f}\n")
    for y_, x_ in zip(ys_, xs_):
        a, mg = c_ang[y_, x_], 0.0 if still[y_, x_] else 1.0
        f.write(f"vt {0.5 + 0.5 * mg * math.cos(a):.4f} {1 - (0.5 + 0.5 * mg * math.sin(a)):.4f}\n")
    f.write("vn 0 0 1\n")
    for y_, x_ in zip(ys_, xs_):
        if y_ + 1 < RH and x_ + 1 < RW:
            a_, b_, c_, d_ = cvid[y_, x_], cvid[y_, x_ + 1], cvid[y_ + 1, x_ + 1], cvid[y_ + 1, x_]
            if min(a_, b_, c_, d_) > 0:
                f.write(f"f {a_}/{a_}/1 {d_}/{d_}/1 {c_}/{c_}/1\nf {a_}/{a_}/1 {c_}/{c_}/1 {b_}/{b_}/1\n")

# ------------------------------------------------------------------ scatter
def to_world(pts):
    z = sample(h, pts)
    return np.column_stack([ORIGIN_CM[0] + pts[:, 0] * 100, ORIGIN_CM[1] + pts[:, 1] * 100, z * 100])

def scatter(density, spacing, seed, max_n=None):
    g = np.random.default_rng(seed)
    gx_ = np.arange(spacing / 2, W_M, spacing)
    gy_ = np.arange(spacing / 2, H_M, spacing)
    P = np.array(np.meshgrid(gx_, gy_)).reshape(2, -1).T
    P = P + g.uniform(-0.45, 0.45, P.shape) * spacing
    P = P[(P[:, 0] > 0) & (P[:, 0] < W_M) & (P[:, 1] > 0) & (P[:, 1] < H_M)]
    d = sample(density, P)
    keep = g.random(len(P)) < d
    P = P[keep]
    if max_n and len(P) > max_n:
        P = P[g.choice(len(P), max_n, replace=False)]
    return P

free = (1 - negative)
dist_play = np.min([np.hypot(X - p[0], Y - p[1]) for p in OUTPOSTS.values()], axis=0)
play = np.maximum(smoothstep(420, 120, pd), smoothstep(500, 150, dist_play))     # playable core gets full density
floor_area = crater_in & (spire < 160)
canopy = free * floor_area * (L["ForestFloor"] + L["Moss"] + 0.3 * L["Grass"]) * (slope < 24)
canopy_d = canopy * (0.35 + 0.65 * play)
river_edge = free * smoothstep(40, 8, wdist) * (slope < 20)
talus_d = free * L["Talus"] * (slope < 32)
rim_d = free * (cr > 1.02) * (slope < 22)
clearing_d = free * L["Grass"] * (slope < 20)
spire_skirt = free * crater_in * (spire > 20) * (slope < 34)

FOL = {}
def add(group, pts, sc, seed, yaw=True):
    g = np.random.default_rng(seed)
    w = to_world(pts)
    s = g.uniform(sc[0], sc[1], len(pts))
    yv = g.uniform(0, 360, len(pts)) if yaw else np.zeros(len(pts))
    FOL[group] = np.column_stack([w, yv, s]).round(1).tolist()

# skinned (Megaplant) — sizes are real-world; rainforest emergents scaled up a little
# closed rainforest canopy: giant emergents everywhere on the floor (reference: unbroken umbrella-crowned canopy)
closed = canopy * 0.95 + river_edge * 0.4
add("SK_Alder",   scatter(closed, 17, 101, 24000), (2.2, 3.4), 201)
add("SK_Willow",  scatter(closed * 0.55 + river_edge * 0.8, 21, 102, 10000), (2.4, 3.6), 202)
add("SK_Elder",   scatter((canopy_d * 0.7 + spire_skirt * 0.5) * (0.3 + 0.7 * play), 12, 103, 8000), (1.6, 3.2), 203)
# tree line along the flat rim shelf (reference: forest silhouette along the cliff tops)
rim_shelf = free * smoothstep(0.995, 1.01, cr) * smoothstep(1.16, 1.10, cr) * (slope < 25)
add("SK_Alder_Rim", scatter(rim_shelf, 15, 121, 8000), (1.8, 3.0), 221)
add("SK_Spruce",  scatter(rim_d * 0.6 + talus_d * 0.25 + spire_skirt * 0.35 + canopy * 0.12, 20, 104, 9000), (0.9, 1.5), 204)
add("SK_Spindle", scatter(canopy_d * 0.7 + clearing_d * 0.2, 9, 105, 14000), (0.8, 1.6), 205)
add("SK_Bilberry", scatter(canopy_d * 0.9 + river_edge * 0.4, 5, 106, 22000), (1.0, 1.9), 206)
add("SK_Lingonberry", scatter((canopy_d + clearing_d) * 0.75, 5, 107, 20000), (1.0, 1.9), 207)
add("SK_Reeds",   scatter(free * smoothstep(14, 2, wdist) * floor_area + ndi.gaussian_filter(mudpatch, 2) * free * 0.5, 4, 108, 14000), (0.9, 1.4), 208)
# static grass / ground plants (playable core + clearings)
grass_core = clearing_d * (0.25 + 0.75 * play) + free * play * 0.25 * floor_area
add("ST_PNGrass",   scatter(grass_core, 2.2, 109, 140000), (0.8, 1.4), 209)
add("ST_WildGrass_MS", scatter(clearing_d * 0.6 + rim_d * 0.4, 4.0, 110, 30000), (0.8, 1.2), 210)
add("ST_WildGrass_JB", scatter(clearing_d * play * 0.5 + river_edge * 0.3, 4.0, 111, 15000), (0.8, 1.3), 211)
add("ST_Sorrel",    scatter(canopy_d * (0.35 + 0.65 * play) + river_edge * 0.5, 2.4, 112, 90000), (0.9, 1.7), 212)
add("ST_Fern",      scatter(canopy_d * 0.9 + river_edge * 0.6, 3.0, 122, 70000), (1.2, 2.2), 222)
add("ST_DeadShrub", scatter(talus_d * 0.7 + rim_d * 0.15, 6, 113, 5000), (0.8, 1.4), 213)
add("ST_DryBush",   scatter(talus_d * 0.4 + rim_d * 0.1, 9, 114, 2500), (0.6, 1.1), 214)
add("ST_CypressRoots", scatter(river_edge * 0.25, 18, 115, 1500), (1.0, 2.2), 215)
# rocks
rock_small = scatter(talus_d * 0.5 + river_edge * 0.08 + free * smoothstep(PATH_HALF + 7, PATH_HALF + 3, pd) * 0.06, 10, 116, 2500)
add("ST_RockSmall", rock_small, (0.03, 0.12), 216)
add("ST_RockBoulder", scatter(talus_d * 0.18 + canopy * 0.006 + rim_d * 0.02, 30, 117, 900), (0.15, 0.6), 217)
# mossy rocks all through the forest floor, thicker along creeks and lake shores
add("ST_MossRock", scatter(canopy * 0.22 + river_edge * 0.35 + spire_skirt * 0.15, 11, 118, 9000), (0.035, 0.14), 218)
add("ST_MossBoulder", scatter(canopy * 0.05 + river_edge * 0.06 + spire_skirt * 0.05, 26, 119, 1800), (0.18, 0.42), 219)

# fallen mossy logs: lie along the ground (pitch follows the slope), never across paths, pads or water
def logs(density, spacing, seed, max_n, half=5.0):
    g = np.random.default_rng(seed)
    P = scatter(density, spacing, seed, max_n * 2)
    out = []
    for p in P:
        yaw = g.uniform(0, 360)
        d = np.array([math.cos(math.radians(yaw)), math.sin(math.radians(yaw))]) * half
        ends = np.array([p - d, p, p + d])
        if sample(negative, ends).max() > 0.35 or sample(slope, ends).max() > 22:
            continue
        za, zc, zb = sample(h, ends)
        pitch = math.degrees(math.atan2(zb - za, 2 * half))
        out.append([ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, (max(0.5 * (za + zb), zc - 0.2) - 0.15) * 100,
                    yaw, g.uniform(0.75, 1.25), pitch, g.uniform(-25, 25)])
        if len(out) >= max_n:
            break
    return [list(np.round(r, 1)) for r in out]
FOL["ST_Log"] = logs(canopy * 0.35 + river_edge * 0.25 + spire_skirt * 0.2, 24, 141, 2600)

# big wall/outcrop pieces (SM_Mountain_*): ring around the wall foot and on the rim, sunk in
BIG = []
for i, a in enumerate(np.linspace(0, 360, 26, endpoint=False) + rng.uniform(-5, 5, 26)):
    if 150 < a < 222 or 80 < a < 100:     # keep the ledge road and breach clear
        continue
    p = ell(a, 0.955)
    z = float(sample(h, np.array([p]))[0])
    BIG.append({"mesh": ["SM_Mountain_01", "SM_Mountain_02"][i % 2], "loc": [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, z * 100 - 9000],
                "yaw": float(rng.uniform(0, 360)), "scale": float(rng.uniform(0.18, 0.3))})

# outposts -> world, bridges where paths cross rivers
OUT_W = {nm: [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, p[2] * 100] for nm, p in OUTPOSTS.items()}
BRIDGES = []
for nm, poly, z in path_polys:
    wet = river_core[np.clip((poly[:, 1] / CELL).astype(int), 0, RH - 1), np.clip((poly[:, 0] / CELL).astype(int), 0, RW - 1)]
    lab, n = ndi.label(wet)
    for j in range(1, n + 1):
        ids = np.nonzero(lab == j)[0]
        a_, b_ = max(ids[0] - 4, 0), min(ids[-1] + 4, len(poly) - 1)
        pa, pb = poly[a_], poly[b_]
        za = float(sample(h, np.array([pa]))[0]); zb = float(sample(h, np.array([pb]))[0])
        BRIDGES.append({"a": [ORIGIN_CM[0] + pa[0] * 100, ORIGIN_CM[1] + pa[1] * 100, za * 100],
                        "b": [ORIGIN_CM[0] + pb[0] * 100, ORIGIN_CM[1] + pb[1] * 100, zb * 100]})

# ------------------------------------------------------------------ emitters
EMIT = []
for nm, p in FALLS.items():
    top = np.array(p); base = inward(p, 120)
    zt = float(sample(h, np.array([inward(p, -30)]))[0]); zb = 51.0
    EMIT.append({"type": "Waterfall", "name": nm, "top": [ORIGIN_CM[0] + top[0] * 100, ORIGIN_CM[1] + top[1] * 100, zt * 100],
                 "base": [ORIGIN_CM[0] + base[0] * 100, ORIGIN_CM[1] + base[1] * 100, zb * 100]})
    EMIT.append({"type": "Mist", "name": nm + "_spray", "loc": [ORIGIN_CM[0] + base[0] * 100, ORIGIN_CM[1] + base[1] * 100, (zb + 8) * 100], "radius": 6000})
# low mist drifting through the canopy, a cloud collar on the spire, and haze along the cliff foot
for i, p in enumerate(scatter(floor_area.astype(np.float32) * free * 0.9, 380, 131, 48)):
    z = float(sample(h, np.array([p]))[0]) + rng.uniform(35, 70)
    EMIT.append({"type": "Mist", "name": "Canopy_%02d" % i, "loc": [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, z * 100], "radius": 9000})
for i, a in enumerate(np.linspace(0, 360, 9, endpoint=False)):
    p = SP + np.array([math.cos(math.radians(a)) * BRX, math.sin(math.radians(a)) * BRY]) * (0.35 if i % 2 else 0.7)
    EMIT.append({"type": "GroundMist", "name": "GreatLake_%d" % i, "loc": [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, BIG_Z * 100 + 150]})
for i, a in enumerate(np.linspace(0, 360, 12, endpoint=False) + 9):
    p = ell(a, 0.93)
    z = float(sample(h, np.array([p]))[0]) + 60
    EMIT.append({"type": "Mist", "name": "WallFoot_%02d" % i, "loc": [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, z * 100], "radius": 14000})
for nm, (px, py) in {"W": (605, 480), "NE": (925, 360), "SE": (935, 560), "E": (1000, 445)}.items():
    p = np.array(src_px(px, py))
    EMIT.append({"type": "Mist", "name": "Bank_" + nm, "loc": [ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, (float(sample(h, np.array([p]))[0]) + 25) * 100], "radius": 15000})
for i, cf in enumerate(CAMPFIRES):
    EMIT.append({"type": "Campfire", "name": "Fire_%02d" % i, "loc": cf[:3]})
for p in scatter(clearing_d * play * 0.02, 40, 120, 60):
    w = to_world(np.array([p]))[0]
    EMIT.append({"type": "Fireflies", "name": "ff", "loc": [float(w[0]), float(w[1]), float(w[2]) + 150]})
# night ground mist: a low blanket over the whole floor, pooling over the lakes and creeks
gm_d = (floor_area & (slope < 26)).astype(np.float32) * (0.55 + 0.45 * smoothstep(60, 0, wdist))
for i, p in enumerate(scatter(gm_d, 150, 151, 260)):
    w = to_world(np.array([p]))[0]
    EMIT.append({"type": "GroundMist", "name": "GM_%03d" % i, "loc": [float(w[0]), float(w[1]), float(w[2]) + 120]})
for i, L_ in enumerate(LAKES):
    c = L_["c"]
    EMIT.append({"type": "GroundMist", "name": "Lake_%d" % i, "loc": [ORIGIN_CM[0] + c[0] * 100, ORIGIN_CM[1] + c[1] * 100, L_["z"] * 100 + 100]})
    for k in range(3):
        a = k * 2.1 + i
        q = c + np.array([math.cos(a), math.sin(a)]) * L_["R"] * 1.3
        EMIT.append({"type": "Fireflies", "name": "lake%d_%d" % (i, k), "loc": [ORIGIN_CM[0] + q[0] * 100, ORIGIN_CM[1] + q[1] * 100, float(sample(h, np.array([q]))[0]) * 100 + 180]})
em_img = np.zeros((RH // 2, RW // 2, 4), np.float32)
for e in EMIT:
    p = np.array(e.get("base", e.get("loc")))
    lx, ly = (p[0] - ORIGIN_CM[0]) / 100 / CELL / 2, (p[1] - ORIGIN_CM[1]) / 100 / CELL / 2
    ch = {"Waterfall": 0, "Mist": 3, "GroundMist": 3, "Campfire": 1, "Fireflies": 2}[e["type"]]
    rr = {"Waterfall": 40, "Mist": 120, "GroundMist": 70, "Campfire": 15, "Fireflies": 25}[e["type"]]
    yy2, xx2 = np.ogrid[0:RH // 2, 0:RW // 2]
    em_img[..., ch] = np.maximum(em_img[..., ch], np.exp(-(((xx2 - lx) ** 2 + (yy2 - ly) ** 2) / (rr ** 2))))
Image.fromarray((em_img * 255).astype(np.uint8)).save(os.path.join(OUT, "Emitter_Map.png"))

# ------------------------------------------------------------------ write placement + info
place = {"ruins": RUINS, "campfires": CAMPFIRES, "origin_cm": ORIGIN_CM, "tiles": tiles, "foliage": FOL, "big_rocks": BIG, "outposts": OUT_W, "bridges": BRIDGES,
         "emitters": EMIT, "rim_overlook": [ORIGIN_CM[0] + RIM_OVERLOOK[0] * 100, ORIGIN_CM[1] + RIM_OVERLOOK[1] * 100,
                                             float(sample(h, np.array([RIM_OVERLOOK]))[0]) * 100]}
json.dump(place, open(os.path.join(SAVED, "crater_v2.json"), "w"))
json.dump({nm: [[ORIGIN_CM[0] + p[0] * 100, ORIGIN_CM[1] + p[1] * 100, float(z_) * 100] for p, z_ in zip(poly[::3], np.asarray(z)[::3])]
           for nm, poly, z in path_polys}, open(os.path.join(SAVED, "crater_paths.json"), "w"))
info = {"region_origin_cm": ORIGIN_CM, "landscape": {"resolution": [RW, RH], "scale_cm": [160, 160, Z_SCALE], "components": [32, 24]},
        "height_range_m": [float(h.min()), float(h.max())], "layers": LAYERS,
        "foliage_counts": {k: len(v) for k, v in FOL.items()}, "big_rocks": len(BIG), "bridges": len(BRIDGES), "lakes": [[round(L_["c"][0]), round(L_["c"][1]), round(L_["R"]), round(L_["z"], 1)] for L_ in LAKES], "creeks": len(CREEKS),
        "outposts": {k: [round(v[0]), round(v[1]), round(v[2])] for k, v in OUT_W.items()},
        "emitters": {t: sum(1 for e in EMIT if e["type"] == t) for t in {e["type"] for e in EMIT}},
        "walkable_pct_floor": float((slope[crater_in & (spire < 160)] < 30).mean() * 100),
        "path_max_grade_deg": float(np.percentile(slope[path_core > 0.9], 99))}
json.dump(info, open(os.path.join(OUT, "Region_v2.json"), "w"), indent=2)

# ------------------------------------------------------------------ previews
st = 3
hs = h[::st, ::st]
cmap = LinearSegmentedColormap.from_list("rf", [(0, "#2a5236"), (0.1, "#4b7f45"), (0.3, "#93ad66"), (0.55, "#bfae78"), (0.8, "#9a7a5c"), (1, "#efeae4")])
rgb = LightSource(315, 40).shade(hs, cmap=cmap, vert_exag=1.0, blend_mode="soft", dx=CELL * st, dy=CELL * st, vmin=30, vmax=float(h.max()))
rgb[..., :3][wet_core[::st, ::st]] = [0.25, 0.55, 0.75]
pc = path_core[::st, ::st] > 0.5
rgb[..., :3][pc] = [0.85, 0.72, 0.5]
fig, ax = plt.subplots(figsize=(20, 15), dpi=110)
ext = [0, W_M / 1000, H_M / 1000, 0]
ax.imshow(rgb, extent=ext)
xs_ = np.linspace(0, W_M / 1000, hs.shape[1]); ys_ = np.linspace(0, H_M / 1000, hs.shape[0])
ax.contour(xs_, ys_, ndi.gaussian_filter(hs, 1.5), levels=np.arange(0, 1200, 10), colors="#3a2a18", linewidths=0.15, alpha=0.45)
ci = ax.contour(xs_, ys_, ndi.gaussian_filter(hs, 1.5), levels=np.arange(50, 1200, 50), colors="#2a1a08", linewidths=0.55, alpha=0.8)
ax.clabel(ci, fmt="%d m", fontsize=6)
for nm, p in OUTPOSTS.items():
    ax.plot(p[0] / 1000, p[1] / 1000, "o", ms=13, mfc="#ffd24a", mec="black")
    ax.text(p[0] / 1000 + 0.06, p[1] / 1000 - 0.05, nm, fontsize=11, weight="bold", color="white", bbox=dict(fc=(0, 0, 0, 0.55), ec="none"))
for nm, p in FALLS.items():
    ax.plot(p[0] / 1000, p[1] / 1000, "v", ms=12, mfc="#7fd4ff", mec="black")
ax.plot(RIM_OVERLOOK[0] / 1000, RIM_OVERLOOK[1] / 1000, "^", ms=13, mfc="white", mec="black")
ax.text(RIM_OVERLOOK[0] / 1000 + 0.06, RIM_OVERLOOK[1] / 1000, "Rim Overlook / Ledge Road", fontsize=10, weight="bold", color="white", bbox=dict(fc=(0, 0, 0, 0.55), ec="none"))
for b in BRIDGES:
    ax.plot([(b["a"][0] - ORIGIN_CM[0]) / 1e5, (b["b"][0] - ORIGIN_CM[0]) / 1e5], [(b["a"][1] - ORIGIN_CM[1]) / 1e5, (b["b"][1] - ORIGIN_CM[1]) / 1e5], "-", color="#6b3b1b", lw=4)
ax.set_title("Starfall Crater v2 — walkable layout: paths (tan), rivers (blue), outposts (gold), waterfalls (blue ▼), bridges (brown) · contours 10/50 m", fontsize=13, family="serif")
ax.set_xlabel("km (local, +X east)"); ax.set_ylabel("km (local, +Y south)")
fig.tight_layout(); fig.savefig(os.path.join(OUT, "Topographic_v2.png")); plt.close(fig)

PAL = np.array([(60, 80, 40), (70, 110, 50), (130, 165, 70), (190, 160, 110), (95, 75, 55), (50, 110, 140), (150, 140, 125), (115, 108, 100)], np.float32)
prev = np.tensordot(stack.transpose(1, 2, 0), PAL, axes=1).astype(np.uint8)
Image.fromarray(prev).resize((1344, 1008)).save(os.path.join(OUT, "Splat_Preview_v2.png"))
print(json.dumps(info, indent=2))
