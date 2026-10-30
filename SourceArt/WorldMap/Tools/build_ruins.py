"""
Procedural ruined-masonry pieces for Starfall Crater (OBJ, cm). Usage: build_ruins.py <out_dir>
Every piece is built from irregular cut-stone blocks; tops are broken and blocks are missing / shifted.
Pivot at the bottom centre. UVs are box-projected at 1 UV per 2 m so the stone texture keeps a real-world scale.
"""
import math
import os
import sys

import numpy as np

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)
UV_M = 2.0


class Mesh:
    def __init__(self):
        self.V, self.N, self.T, self.F = [], [], [], []

    def box(self, c, size, yaw=0.0, tilt=(0.0, 0.0)):
        """Axis box at centre c (m), size (sx, sy, sz), rotated by yaw (deg) and small tilts (deg about x, y)."""
        sx, sy, sz = (s / 2 for s in size)
        cy, sy_ = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
        ax, ay = math.radians(tilt[0]), math.radians(tilt[1])
        Rz = np.array([[cy, -sy_, 0], [sy_, cy, 0], [0, 0, 1]])
        Rx = np.array([[1, 0, 0], [0, math.cos(ax), -math.sin(ax)], [0, math.sin(ax), math.cos(ax)]])
        Ry = np.array([[math.cos(ay), 0, math.sin(ay)], [0, 1, 0], [-math.sin(ay), 0, math.cos(ay)]])
        R = Rz @ Ry @ Rx
        faces = [((1, 0, 0), (0, 1, 0), (0, 0, 1)), ((-1, 0, 0), (0, -1, 0), (0, 0, 1)), ((0, 1, 0), (-1, 0, 0), (0, 0, 1)),
                 ((0, -1, 0), (1, 0, 0), (0, 0, 1)), ((0, 0, 1), (1, 0, 0), (0, 1, 0)), ((0, 0, -1), (1, 0, 0), (0, -1, 0))]
        ext = np.array([sx, sy, sz])
        for n, u, v in faces:
            n, u, v = np.array(n, float), np.array(u, float), np.array(v, float)
            base = len(self.V)
            corners = []
            for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
                p = n * ext + u * ext * a + v * ext * b
                corners.append(p)
            wn = R @ n
            for p in corners:
                wp = np.array(c) + R @ p
                self.V.append(wp)
                self.N.append(wn)
                # box projection in world space so neighbouring blocks don't share the same texture patch
                k = int(np.argmax(np.abs(wn)))
                uu, vv = [(1, 2), (0, 2), (0, 1)][k]
                self.T.append((wp[uu] / UV_M, wp[vv] / UV_M))
            tri = [(base, base + 1, base + 2), (base, base + 2, base + 3)]
            for t in tri:
                a_, b_, c_ = (self.V[i] for i in t)
                # importer mirrors Y: right-hand normal must point inward in the file (same rule as the terrain tiles)
                if np.dot(np.cross(b_ - a_, c_ - a_), wn) > 0:
                    t = (t[0], t[2], t[1])
                self.F.append(t)

    def write(self, name):
        with open(os.path.join(OUT, name + ".obj"), "w") as f:
            f.write("# ruin piece %s\n" % name)
            for v in self.V:
                f.write("v %.2f %.2f %.2f\n" % (v[0] * 100, v[1] * 100, v[2] * 100))
            for t in self.T:
                f.write("vt %.4f %.4f\n" % t)
            for n in self.N:
                f.write("vn %.4f %.4f %.4f\n" % tuple(n))
            for t in self.F:
                f.write("f " + " ".join("%d/%d/%d" % (i + 1, i + 1, i + 1) for i in t) + "\n")
        print(name, len(self.V), "verts", len(self.F), "tris")


def wall(m, g, length, height, thick, x0=0.0, y0=0.0, yaw=0.0, opening=None, ruin=0.55):
    """Coursed masonry wall along local +X; the top is broken away in a ragged profile; `opening` = (centre, width, height)."""
    ca, sa = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    course = 0.45
    n_c = int(height / course)
    prof_x = np.linspace(0, length, 9)
    prof_h = height * (1 - ruin * np.abs(g.normal(0, 0.5, 9)).clip(0, 1))
    prof_h[0] *= 0.6
    for i in range(n_c):
        z = i * course
        x = -g.uniform(0, 0.6) if i % 2 else 0.0
        while x < length - 0.05:
            bl = g.uniform(0.7, 1.25)
            bl = min(bl, length - x)
            cx = x + bl / 2
            top_here = np.interp(cx, prof_x, prof_h)
            skip = z + course > top_here + g.uniform(-0.2, 0.2)
            if opening and abs(cx - opening[0]) < opening[1] / 2 and z < opening[2]:
                skip = True
            if not skip and not (i > 1 and g.random() < 0.04):
                wx, wy = x0 + cx * ca, y0 + cx * sa
                m.box((wx, wy, z + course / 2), (bl - 0.03, thick * g.uniform(0.92, 1.05), course - 0.025),
                      yaw + g.uniform(-2.5, 2.5), (g.uniform(-1.5, 1.5), g.uniform(-1.5, 1.5)))
            x += bl
    if opening:     # lintel / arch stones over the opening
        oc, ow, oh = opening
        for k in range(7):
            a = math.pi * k / 6
            px = oc - math.cos(a) * ow / 2
            pz = oh + math.sin(a) * ow * 0.45
            if pz < np.interp(px, prof_x, prof_h) + 0.3:
                m.box((x0 + px * ca, y0 + px * sa, pz + 0.2), (0.55, thick * 1.02, 0.45), yaw, (0.0, -math.degrees(a - math.pi / 2) * 0.6))


def column(m, g, height, r=0.42, broken=True, x=0.0, y=0.0):
    m.box((x, y, 0.2), (r * 2.9, r * 2.9, 0.4), g.uniform(0, 90))                      # plinth
    z = 0.4
    drum = 0.7
    while z < height - 0.1:
        h_ = min(drum, height - z)
        m.box((x + g.uniform(-0.04, 0.04), y + g.uniform(-0.04, 0.04), z + h_ / 2), (r * 2, r * 2, h_ - 0.02), g.uniform(0, 90))
        m.box((x, y, z + h_ / 2), (r * 2.25, r * 1.4, h_ - 0.06), g.uniform(0, 90))   # octagonal-ish shaft
        z += h_
    if not broken:
        m.box((x, y, z + 0.2), (r * 2.8, r * 2.8, 0.4), 0)                              # capital


pieces = {}
g = np.random.default_rng(4242)
m = Mesh(); wall(m, g, 6.0, 3.6, 0.8, -3.0, 0.0); pieces["SM_Ruin_Wall6"] = m
m = Mesh(); wall(m, g, 6.0, 2.2, 0.8, -3.0, 0.0, ruin=0.8); pieces["SM_Ruin_WallLow"] = m
m = Mesh(); wall(m, g, 5.0, 4.6, 0.85, -2.5, 0.0, opening=(2.5, 1.7, 2.4), ruin=0.35); pieces["SM_Ruin_WallArch"] = m
m = Mesh(); wall(m, g, 4.5, 3.2, 0.8, -0.4, -0.4); wall(m, g, 4.0, 2.6, 0.8, -0.4, -0.4, yaw=90); pieces["SM_Ruin_Corner"] = m
m = Mesh(); column(m, g, 4.6, broken=False); pieces["SM_Ruin_Column"] = m
m = Mesh(); column(m, g, 2.1); pieces["SM_Ruin_ColumnBroken"] = m
m = Mesh()
for k in range(4):                                                                          # fallen column: drums lying in a line
    m.box((k * 0.78 + g.uniform(-0.05, 0.05), g.uniform(-0.08, 0.08), 0.42), (0.7, 0.84, 0.84), g.uniform(-6, 6), (g.uniform(0, 20), 0))
pieces["SM_Ruin_ColumnFallen"] = m
m = Mesh()
for k in range(9):                                                                          # rubble heap of cut stones
    a, r = g.uniform(0, 6.28), g.uniform(0, 1.4)
    m.box((math.cos(a) * r, math.sin(a) * r, g.uniform(0.15, 0.5)), (g.uniform(0.6, 1.1), g.uniform(0.4, 0.7), g.uniform(0.35, 0.5)),
          g.uniform(0, 180), (g.uniform(-25, 25), g.uniform(-25, 25)))
pieces["SM_Ruin_Rubble"] = m
m = Mesh()
for i in range(5):                                                                          # cracked flagstone floor
    for j in range(4):
        if g.random() < 0.82:
            m.box((i * 1.2 - 2.4 + g.uniform(-0.05, 0.05), j * 1.2 - 1.8 + g.uniform(-0.05, 0.05), 0.08 + g.uniform(-0.04, 0.04)),
                  (1.12, 1.12, 0.2), g.uniform(-3, 3), (g.uniform(-3, 3), g.uniform(-3, 3)))
pieces["SM_Ruin_Floor"] = m
for name, mm in pieces.items():
    mm.write(name)
