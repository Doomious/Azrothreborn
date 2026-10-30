"""
Procedural fallen-log meshes for Starfall Crater (OBJ, cm). Usage: build_logs.py <out_dir>
Each log lies along +X, pivot at the bottom centre (sits on the ground at z=0).
UVs: bark wraps u 0.01-0.48 of the Megaplant alder bark atlas, v runs along the log at the atlas aspect (2:1);
broken ends use the lighter wood strip (u 0.53-0.73).
"""
import math
import os
import sys

import numpy as np

OUT = sys.argv[1]
os.makedirs(OUT, exist_ok=True)

#        name     length m  radius m  bend m  taper  root flare
LOGS = [("SM_Log_A", 6.0, 0.34, 0.25, 0.20, False),
        ("SM_Log_B", 9.0, 0.45, 0.45, 0.28, False),
        ("SM_Log_C", 12.0, 0.58, 0.70, 0.32, False),
        ("SM_Log_D", 10.0, 0.62, 0.40, 0.35, True)]
SEG = 28


def build(name, length, r0, bend, taper, roots, seed):
    g = np.random.default_rng(seed)
    nring = int(length / 0.22) + 1
    xs = np.linspace(-length / 2, length / 2, nring)
    t = (xs - xs[0]) / length
    bump_l = np.interp(t, np.linspace(0, 1, 12), g.uniform(-0.06, 0.06, 12))
    ang_ph = g.uniform(0, 6.28, 3)
    V, VT, VN, F = [], [], [], []

    def radius(i, th):
        r = r0 * (1 - taper * t[i]) * (1 + bump_l[i])
        r *= 1 + 0.035 * math.cos(3 * th + ang_ph[0]) + 0.025 * math.cos(5 * th + ang_ph[1] + 4 * t[i])
        if roots and t[i] < 0.09:
            k = (0.09 - t[i]) / 0.09
            r *= 1 + 0.9 * k ** 1.5 * (0.75 + 0.25 * abs(math.cos(3 * th + ang_ph[2])))
        return r

    circ = 2 * math.pi * r0
    jag = {0: g.uniform(-0.18, 0.18, SEG + 1), nring - 1: g.uniform(-0.18, 0.18, SEG + 1)}
    jag[0][-1] = jag[0][0]
    jag[nring - 1][-1] = jag[nring - 1][0]
    centre = []
    for i in range(nring):
        cy = bend * math.sin(math.pi * t[i])                      # gentle sideways bow
        cz = r0 + 0.12 * bend * math.sin(2 * math.pi * t[i])
        centre.append((xs[i], cy, cz))
        for j in range(SEG + 1):
            th = -math.pi / 2 + 2 * math.pi * j / SEG             # seam on the underside
            r = radius(i, th)
            x = xs[i] + (jag[i][j] if i in jag else 0.0)
            V.append((x, cy + r * math.cos(th), cz + r * math.sin(th)))
            VN.append((0.0, math.cos(th), math.sin(th)))
            VT.append((0.01 + 0.47 * j / SEG, xs[i] / (2 * circ)))
    for i in range(nring - 1):
        for j in range(SEG):
            a = i * (SEG + 1) + j
            b, c, d = a + 1, a + SEG + 2, a + SEG + 1
            # same handedness as the terrain tiles: right-hand normal points inward before the Y flip
            F.append(((a, a, a), (c, c, c), (b, b, b)))
            F.append(((a, a, a), (d, d, d), (c, c, c)))
    # broken / sawn ends: a fan to a slightly recessed centre, wood-strip UVs
    for i, sgn in ((0, -1), (nring - 1, 1)):
        base = len(V)
        cx, cy, cz = centre[i]
        V.append((cx - sgn * 0.08, cy, cz))
        VT.append((0.63, 0.5))
        VN.append((sgn, 0.0, 0.0))
        for j in range(SEG + 1):
            th = -math.pi / 2 + 2 * math.pi * j / SEG
            V.append(V[i * (SEG + 1) + j])
            VT.append((0.63 + 0.1 * math.cos(th), 0.5 + 0.4 * math.sin(th)))
            VN.append((sgn, 0.0, 0.0))
        for j in range(SEG):
            p, q = base + 1 + j, base + 2 + j
            tri = ((base, base, base), (q, q, q), (p, p, p)) if sgn > 0 else ((base, base, base), (p, p, p), (q, q, q))
            F.append(tri)
    with open(os.path.join(OUT, name + ".obj"), "w") as f:
        f.write("# fallen log %s\n" % name)
        for v in V:
            f.write("v %.2f %.2f %.2f\n" % (v[0] * 100, v[1] * 100, v[2] * 100))
        for vt in VT:
            f.write("vt %.5f %.5f\n" % (vt[0], 1 - vt[1]))
        for vn in VN:
            f.write("vn %.4f %.4f %.4f\n" % vn)
        for tri in F:
            # outward winding for UE (counter-clockwise seen from outside after the importer's Y mirror)
            f.write("f " + " ".join("%d/%d/%d" % (k[0] + 1, k[1] + 1, k[2] + 1) for k in tri) + "\n")
    print(name, len(V), "verts", len(F), "tris")


for k, spec in enumerate(LOGS):
    build(*spec, seed=900 + k)
