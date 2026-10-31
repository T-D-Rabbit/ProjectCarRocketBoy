#!/usr/bin/env python3
"""Cross-check: connectivity derived from RocketBoy.kicad_sch vs pad nets in RocketBoy.kicad_pcb."""
import sys, os, collections
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexpr import parse, find, first, val
import sch_netlist

ROOT = os.path.dirname(HERE)
sch, *_ = sch_netlist.build(os.path.join(ROOT, "RocketBoy", "RocketBoy.kicad_sch"))
sch_sets = {}
for net, items in sch.items():
    if net.startswith("unnamed-") and len(items) == 1:
        continue
    sch_sets[net.lstrip("/")] = frozenset((r, p) for r, p, n in items)

t = parse(open(os.path.join(ROOT, "RocketBoy", "RocketBoy.kicad_pcb")).read())
pcb = collections.defaultdict(set)
for fp in find(t, "footprint"):
    ref = [val(p[2]) for p in find(fp, "property") if val(p[1]) == "Reference"][0]
    for pd in find(fp, "pad"):
        net = first(pd, "net")
        num = val(pd[1])
        if net and not val(net[2]).startswith("unconnected-"):
            pcb[val(net[2]).lstrip("/")].add((ref, num))
pcb_sets = {k: frozenset(v) for k, v in pcb.items()}

ok = True
for name, s in sorted(sch_sets.items()):
    if name not in pcb_sets:
        print("MISSING IN PCB:", name, sorted(s)[:6]); ok = False
    elif pcb_sets[name] != s:
        print("DIFF", name, "sch-only:", sorted(s - pcb_sets[name])[:8], "pcb-only:", sorted(pcb_sets[name] - s)[:8]); ok = False
for name in pcb_sets:
    if name not in sch_sets:
        print("PCB-only net:", name, sorted(pcb_sets[name])[:6]); ok = False
print("schematic nets:", len(sch_sets), " pcb nets:", len(pcb_sets), " -> ", "IDENTICAL" if ok else "MISMATCH")
sys.exit(0 if ok else 1)
