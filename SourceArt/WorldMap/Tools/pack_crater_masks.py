"""Packs the crater splat layers into two RGB (no alpha) mask textures for the terrain material.
   Mask_A: R = cliff + 0.6*talus, G = path, B = grass
   Mask_B: R = mud + riverbed,     G = moss,  B = talus
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

d = sys.argv[1]
names = ["ForestFloor", "Moss", "Grass", "Path", "Mud", "RiverBed", "Talus", "Cliff"]
L = {n: np.asarray(Image.open(os.path.join(d, "Splat", f"{i:02d}_{n}.png"))).astype(np.float32) / 255 for i, n in enumerate(names)}
a = np.dstack([L["Cliff"] + 0.6 * L["Talus"], L["Path"], L["Grass"]])
b = np.dstack([L["Mud"] + L["RiverBed"], L["Moss"], L["Talus"]])
for name, arr in (("Splat_Mask_A.png", a), ("Splat_Mask_B.png", b)):
    Image.fromarray((np.clip(arr, 0, 1) * 255).astype(np.uint8), "RGB").resize((2048, 1536), Image.BILINEAR).filter(ImageFilter.GaussianBlur(1.0)).save(os.path.join(d, name))
    print("wrote", name)
