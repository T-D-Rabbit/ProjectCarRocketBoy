"""Minimal STEP inspector (stdlib only): bbox, circles (holes/arcs) of a STEP file."""
import re, sys, collections

def load(path):
    t = open(path).read()
    ent = {}
    for m in re.finditer(r"#(\d+)\s*=\s*(.*?);\s*(?=#\d+\s*=|ENDSEC)", t, re.S):
        ent[int(m.group(1))] = m.group(2).replace("\n", "")
    return ent

def nums(s):
    return [float(x) for x in re.findall(r"[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?", s)]

def cart(ent, i):
    v = ent[i]
    inner = v[v.index("(", v.index("(") + 1):]
    return tuple(nums(inner))

def axis(ent, i):
    ids = [int(x) for x in re.findall(r"#(\d+)", ent[i])]
    return cart(ent, ids[0]), [cart(ent, j) for j in ids[1:3]]

def main(path):
    ent = load(path)
    pts = [cart(ent, k) for k, v in ent.items() if v.startswith("CARTESIAN_POINT")]
    pts = [p for p in pts if len(p) == 3]
    for a, n in zip("xyz", range(3)):
        vals = [p[n] for p in pts]
        print(a, min(vals), max(vals))
    circles = collections.Counter()
    for k, v in ent.items():
        if v.startswith("CIRCLE"):
            a = int(re.search(r"#(\d+)", v).group(1))
            r = float(v.rstrip(")").split(",")[-1])
            c, d = axis(ent, a)
            circles[(tuple(round(x, 2) for x in c), round(r, 2), tuple(round(x, 2) for x in d[0]))] += 1
    for k, n in sorted(circles.items()):
        print(k, n)

main(sys.argv[1])
