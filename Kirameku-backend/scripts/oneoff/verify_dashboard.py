# -*- coding: utf-8 -*-
import re, base64
s = open(r"F:\AI\projects\Kirameku\docs\understand-anything\index.html", encoding="utf-8").read()
print("总长度:", len(s))
print("含 nodes 键:", s.count('"nodes"'))
m = re.search(r"const DATA = (\{.*?\});", s, re.S)
print("DATA 常量存在:", bool(m))
if m:
    import json
    d = json.loads(m.group(1))
    print("  节点数:", len(d.get("nodes", [])), "边数:", len(d.get("edges", [])))
b = re.search(r"base64,([A-Za-z0-9+/=]+)\"", s)
print("引擎 base64 存在:", bool(b))
if b:
    eng = base64.b64decode(b.group(1)).decode("utf-8")
    print("  引擎长度:", len(eng))
    print("  含 step():", "function step()" in eng)
    print("  含 draw():", "function draw()" in eng)
    print("  含 showSide():", "function showSide()" in eng)
    print("  含 buildLegend():", "function buildLegend()" in eng)