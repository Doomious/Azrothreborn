"""Negates Y on v/vn lines of OBJ files (the UE OBJ importer mirrors Y). Usage: flip_obj_y.py <dir> [<dir> ...]"""
import glob
import os
import sys

for d in sys.argv[1:]:
    for path in glob.glob(os.path.join(d, "*.obj")):
        out = []
        with open(path) as f:
            for line in f:
                if line.startswith("v ") or line.startswith("vn "):
                    p = line.split()
                    p[2] = str(-float(p[2]))
                    line = " ".join(p) + "\n"
                out.append(line)
        with open(path, "w") as f:
            f.writelines(out)
        print("flipped", os.path.basename(path))
