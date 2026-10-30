"""Decodes a saved CaptureViewport MCP result into a PNG: decode_capture.py <result.txt> <out.png>"""
import base64
import json
import sys

raw = open(sys.argv[1], encoding="utf-8").read()
obj = json.loads(raw)
if isinstance(obj, list):
    obj = json.loads(obj[0]["text"]) if "text" in obj[0] else obj[0]
if isinstance(obj, dict) and "text" in obj:
    obj = json.loads(obj["text"])
img = obj["returnValue"]["image"]["data"]
open(sys.argv[2], "wb").write(base64.b64decode(img))
print("saved", sys.argv[2])
