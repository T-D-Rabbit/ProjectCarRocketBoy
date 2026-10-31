"""Extract connectivity from the RocketBoy .kicad_sch (stdlib only).

Usage: python3 sch_netlist.py <file.kicad_sch>
Prints nets as {net: [REF.pin(name), ...]}.
"""
import sys, math, collections
from sexpr import parse, find, first, val

def rot(px, py, ang):
    a = math.radians(ang)
    c, s = round(math.cos(a)), round(math.sin(a))
    return px * c - py * s, px * s + py * c

def key(x, y):
    return (round(float(x), 2), round(float(y), 2))

def load(path):
    t = parse(open(path).read())
    libs = {}
    for s in find(first(t, "lib_symbols"), "symbol"):
        pins = []
        for sub in find(s, "symbol"):
            for p in find(sub, "pin"):
                a = first(p, "at")
                pins.append((val(first(p, "number")[1]), val(first(p, "name")[1]),
                             float(a[1]), float(a[2])))
        libs[val(s[1])] = pins
    return t, libs

def build(path):
    t, libs = load(path)
    parent = {}
    def f(a):
        parent.setdefault(a, a)
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    def u(a, b):
        parent[f(a)] = f(b)

    wires = []
    for w in find(t, "wire"):
        pts = first(w, "pts")
        xy = [key(p[1], p[2]) for p in find(pts, "xy")]
        wires.append(xy)
        u(xy[0], xy[1])

    def on_wire(pt):
        for (a, b) in wires:
            (x1, y1), (x2, y2) = a, b
            x, y = pt
            if abs((x2 - x1) * (y - y1) - (y2 - y1) * (x - x1)) < 0.02 and \
               min(x1, x2) - 0.01 <= x <= max(x1, x2) + 0.01 and \
               min(y1, y2) - 0.01 <= y <= max(y1, y2) + 0.01:
                u(pt, a)

    pinpts = []  # (key, ref, number, name)
    labels = []
    for s in find(t, "symbol"):
        lid = val(first(s, "lib_id")[1])
        at = first(s, "at")
        x, y, ang = float(at[1]), float(at[2]), float(at[3])
        mir = first(s, "mirror")
        ref = [val(p[2]) for p in find(s, "property") if val(p[1]) == "Reference"][0]
        value = [val(p[2]) for p in find(s, "property") if val(p[1]) == "Value"][0]
        for num, name, px, py in libs[lid]:
            if mir and mir[1] == "x":
                py = -py
            if mir and mir[1] == "y":
                px = -px
            rx, ry = rot(px, py, ang)
            pinpts.append((key(x + rx, y - ry), ref, num, name, lid, value))
    for l in find(t, "label"):
        at = first(l, "at")
        labels.append((key(at[1], at[2]), val(l[1])))
    junctions = [key(first(j, "at")[1], first(j, "at")[2]) for j in find(t, "junction")]
    for p in junctions:
        on_wire(p)
    for p in [p[0] for p in pinpts] + [l[0] for l in labels]:
        f(p)
        on_wire(p)
    # attach labels (same name -> same net)
    byname = collections.defaultdict(list)
    for pt, name in labels:
        byname[name].append(pt)
    for name, pts in byname.items():
        for p in pts[1:]:
            u(pts[0], p)
    # power symbols: net name = value
    pw = collections.defaultdict(list)
    for pt, ref, num, name, lid, value in pinpts:
        if lid.startswith("power:") and not lid.endswith("PWR_FLAG"):
            pw[value].append(pt)
    for name, pts in pw.items():
        for p in pts[1:]:
            u(pts[0], p)
    nets = collections.defaultdict(list)
    for pt, ref, num, name, lid, value in pinpts:
        if ref.startswith("#"):
            continue
        nets[f(pt)].append((ref, num, name))
    names = {}
    for pt, name in labels:
        names[f(pt)] = name
    for name, pts in pw.items():
        names[f(pts[0])] = name
    out = {}
    for root, items in nets.items():
        out[names.get(root, "unnamed-%s" % (root,))] = sorted(items)
    return out, t, labels, wires, pinpts

if __name__ == "__main__":
    out, *_ = build(sys.argv[1])
    for n in sorted(out):
        print(n, len(out[n]))
        for r in out[n]:
            print("   ", *r)
