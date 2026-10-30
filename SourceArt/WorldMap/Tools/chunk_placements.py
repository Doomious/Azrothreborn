"""Splits Saved/Blockout/placements.json into <80KB chunks the editor tool sandbox can read."""
import json
import os
import sys

src = sys.argv[1]
d = json.load(open(os.path.join(src, "placements.json")))
rows = [[g] + it for g, v in d["groups"].items() for it in v["items"]]
chunks, cur, size = [], [], 0
for r in rows:
    s = len(json.dumps(r, separators=(",", ":"))) + 1
    if size + s > 76000:
        chunks.append(cur)
        cur, size = [], 0
    cur.append(r)
    size += s
chunks.append(cur)
for i, c in enumerate(chunks):
    json.dump(c, open(os.path.join(src, f"chunk_{i:02d}.json"), "w"), separators=(",", ":"))
json.dump({"ocean": d["ocean"], "labels": d["labels"], "n": len(chunks)}, open(os.path.join(src, "meta.json"), "w"))
print(len(chunks), [len(c) for c in chunks])
