#!/usr/bin/env python3
"""Builds the single-file, double-click simulator  RocketBoy_Simulator.html  (no server, no internet, no install).

    python3 simulation/run_all.py          # once: writes results/route_30hz.json
    python3 simulation/build_web_sim.py
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "model3d"))
import web_params
import build_model as BM


def pack(mesh):
    p, m = [], []
    for a, b, c, mt in mesh.tris:
        for v in (a, b, c):
            p += [round(v[0], 1), round(v[1], 1), round(v[2], 1)]
        m.append(mt)
    return {"p": p, "m": m}


groups = BM.build_all()
route = json.load(open(os.path.join(HERE, "results", "route_30hz.json")))["route"]
data = {"rw": BM.R_W, "mats": [[n, c[0], c[1], c[2]] for i, (n, c) in sorted(BM.MATERIALS.items())],
        "body": pack(groups["body"]), "wheel": pack(groups["wheel_right"]),
        "params": web_params.build(), "route": route}
html = open(os.path.join(HERE, "web", "sim_template.html")).read()
core = open(os.path.join(HERE, "web", "sim_core.js")).read().replace("'use strict';\n", "")
html = html.replace("/*SIMCORE*/", core).replace("/*DATA*/null", json.dumps(data, separators=(",", ":")))
out = os.path.join(ROOT, "RocketBoy_Simulator.html")
open(out, "w").write(html)
print("wrote", out, "%.0f kB" % (len(html) / 1024))
