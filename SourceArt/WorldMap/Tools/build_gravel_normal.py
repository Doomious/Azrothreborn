"""
Tileable gravel bump: packed rounded pebbles of mixed size over fine grit -> tangent-space normal map + cavity/AO mask.
Usage: build_gravel_normal.py <out_dir>   (writes T_GravelBump_N.png, T_GravelBump_M.png at 1024^2)
"""
import os
import sys

import numpy as np
from PIL import Image
from scipy import ndimage as ndi

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
S = 1024
g = np.random.default_rng(31)
yy, xx = np.mgrid[0:S, 0:S].astype(np.float32)
H = np.zeros((S, S), np.float32)
ID = np.zeros((S, S), np.float32)

# pebbles: largest first, each an elongated dome; wrap around the edges so the tile repeats seamlessly
for count, rmin, rmax in ((420, 16, 30), (1600, 8, 16), (5200, 3, 8)):
    for _ in range(count):
        cx, cy = g.uniform(0, S, 2)
        r = g.uniform(rmin, rmax)
        el = g.uniform(0.55, 1.0)
        a = g.uniform(0, np.pi)
        x0, x1, y0, y1 = int(cx - r - 2), int(cx + r + 3), int(cy - r - 2), int(cy + r + 3)
        xs = np.arange(x0, x1) % S
        ys = np.arange(y0, y1) % S
        lx, ly = np.meshgrid(np.arange(x0, x1) - cx, np.arange(y0, y1) - cy)
        u = (lx * np.cos(a) + ly * np.sin(a)) / r
        v = (-lx * np.sin(a) + ly * np.cos(a)) / (r * el)
        d = u * u + v * v
        facet = 1 + 0.25 * np.sign(np.sin(3 * np.arctan2(v, u) + g.uniform(0, 6.28)))       # chipped, angular faces
        dome = np.clip(1 - d * facet, 0, 1) ** 0.6 * r * 0.6 * g.uniform(0.7, 1.1)
        sub = H[np.ix_(ys, xs)]
        take = dome > sub
        sub[take] = dome[take]
        H[np.ix_(ys, xs)] = sub
        ids = ID[np.ix_(ys, xs)]
        ids[take] = g.random()
        ID[np.ix_(ys, xs)] = ids

# chipped / faceted surfaces and fine grit between stones
def tile_noise(sigma, amp, seed):
    n = np.random.default_rng(seed).standard_normal((S, S)).astype(np.float32)
    n = ndi.gaussian_filter(n, sigma, mode="wrap")
    return n / (n.std() + 1e-6) * amp
H += tile_noise(1.0, 0.35, 1) + tile_noise(2.5, 0.45, 2)
H = ndi.gaussian_filter(H, 0.8, mode="wrap")

gx = (np.roll(H, -1, 1) - np.roll(H, 1, 1)) * 0.5
gy = (np.roll(H, -1, 0) - np.roll(H, 1, 0)) * 0.5
strength = 1.5
n = np.dstack([-gx * strength, gy * strength, np.ones_like(H)])
n /= np.linalg.norm(n, axis=2, keepdims=True)
Image.fromarray(((n * 0.5 + 0.5) * 255).astype(np.uint8), "RGB").save(os.path.join(OUT, "T_GravelBump_N.png"))

cav = np.clip((H - ndi.gaussian_filter(H, 6, mode="wrap")) * 0.08 + 0.6, 0, 1)      # R: cavity / AO between stones
Image.fromarray((np.dstack([cav, ID, np.clip(H / H.max(), 0, 1)]) * 255).astype(np.uint8), "RGB").save(os.path.join(OUT, "T_GravelBump_M.png"))
print("gravel bump written")
