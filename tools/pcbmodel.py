"""Minimal PCB model + geometry helpers + design-rule checker (stdlib only).

The model is intentionally small: pads / tracks / vias / one pour zone.  It is used by
build_pcb.py to (a) emit a KiCad 9 .kicad_pcb and (b) run an independent sanity check
(clearance, connectivity, edge distance) because KiCad itself is not available in the
build sandbox.  It is NOT a replacement for running KiCad's DRC.
"""
import math, collections

# ------------------------------------------------------------------ geometry

def rot_pt(px, py, deg):
    """KiCad rotation: positive angle = counter-clockwise on screen (y axis points down)."""
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return px * c + py * s, -px * s + py * c


def seg_seg_dist(a, b, c, d):
    def cross(o, p, q):
        return (p[0] - o[0]) * (q[1] - o[1]) - (p[1] - o[1]) * (q[0] - o[0])
    d1, d2 = cross(c, d, a), cross(c, d, b)
    d3, d4 = cross(a, b, c), cross(a, b, d)
    if ((d1 > 0) != (d2 > 0)) and ((d3 > 0) != (d4 > 0)) and d1 * d2 < 0 and d3 * d4 < 0:
        return 0.0
    return min(pt_seg_dist(a, c, d), pt_seg_dist(b, c, d), pt_seg_dist(c, a, b), pt_seg_dist(d, a, b))


def pt_seg_dist(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    L2 = dx * dx + dy * dy
    if L2 == 0:
        return math.hypot(p[0] - a[0], p[1] - a[1])
    t = max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


class Shape:
    """Copper shape: kind in {'cap','rect'}.  'cap' = capsule (segment with radius; a circle is a
    zero-length capsule).  'rect' = axis-aligned rectangle (cx,cy,hw,hh)."""
    __slots__ = ("kind", "net", "layer", "g", "ref", "bbox", "tag")

    def __init__(self, kind, net, layer, g, ref="", tag=""):
        self.kind, self.net, self.layer, self.g, self.ref, self.tag = kind, net, layer, g, ref, tag
        if kind == "cap":
            x1, y1, x2, y2, r = g
            self.bbox = (min(x1, x2) - r, min(y1, y2) - r, max(x1, x2) + r, max(y1, y2) + r)
        else:
            cx, cy, hw, hh = g
            self.bbox = (cx - hw, cy - hh, cx + hw, cy + hh)


def shape_dist(a, b):
    """Edge-to-edge distance (0 if touching/overlapping, negative not reported)."""
    if a.kind == "cap" and b.kind == "cap":
        d = seg_seg_dist(a.g[:2], a.g[2:4], b.g[:2], b.g[2:4])
        return max(0.0, d - a.g[4] - b.g[4])
    if a.kind == "rect" and b.kind == "cap":
        a, b = b, a
    if a.kind == "cap" and b.kind == "rect":
        x1, y1, x2, y2, r = a.g
        cx, cy, hw, hh = b.g
        xmin, xmax, ymin, ymax = cx - hw, cx + hw, cy - hh, cy + hh
        # segment intersects rect?  sample + edge tests
        corners = [(xmin, ymin), (xmax, ymin), (xmax, ymax), (xmin, ymax)]
        inside = lambda p: xmin <= p[0] <= xmax and ymin <= p[1] <= ymax
        if inside((x1, y1)) or inside((x2, y2)):
            return 0.0
        best = 1e9
        for i in range(4):
            best = min(best, seg_seg_dist((x1, y1), (x2, y2), corners[i], corners[(i + 1) % 4]))
        return max(0.0, best - r)
    # rect-rect
    ax, ay, ahw, ahh = a.g
    bx, by, bhw, bhh = b.g
    dx = max(0.0, abs(ax - bx) - ahw - bhw)
    dy = max(0.0, abs(ay - by) - ahh - bhh)
    return math.hypot(dx, dy)


# ------------------------------------------------------------------ board model

class Pad:
    def __init__(self, ref, num, net, x, y, kind, w, h, drill=0.0, layers=("F.Cu", "B.Cu"), name=""):
        self.ref, self.num, self.net = ref, num, net
        self.x, self.y, self.kind, self.w, self.h, self.drill = x, y, kind, w, h, drill
        self.layers, self.name = layers, name

    def shapes(self):
        out = []
        for L in self.layers:
            if self.kind in ("circle",):
                out.append(Shape("cap", self.net, L, (self.x, self.y, self.x, self.y, self.w / 2), self.ref + "." + str(self.num)))
            elif self.kind == "oval":
                if self.w >= self.h:
                    d = (self.w - self.h) / 2
                    out.append(Shape("cap", self.net, L, (self.x - d, self.y, self.x + d, self.y, self.h / 2), self.ref + "." + str(self.num)))
                else:
                    d = (self.h - self.w) / 2
                    out.append(Shape("cap", self.net, L, (self.x, self.y - d, self.x, self.y + d, self.w / 2), self.ref + "." + str(self.num)))
            else:  # rect / roundrect
                out.append(Shape("rect", self.net, L, (self.x, self.y, self.w / 2, self.h / 2), self.ref + "." + str(self.num)))
        return out


class Track:
    def __init__(self, layer, net, width, pts):
        self.layer, self.net, self.width, self.pts = layer, net, width, pts

    def shapes(self):
        return [Shape("cap", self.net, self.layer, (a[0], a[1], b[0], b[1], self.width / 2), "trk")
                for a, b in zip(self.pts, self.pts[1:])]


class Via:
    def __init__(self, x, y, net, dia=0.8, drill=0.4):
        self.x, self.y, self.net, self.dia, self.drill = x, y, net, dia, drill

    def shapes(self):
        return [Shape("cap", self.net, L, (self.x, self.y, self.x, self.y, self.dia / 2), "via") for L in ("F.Cu", "B.Cu")]


class Board:
    def __init__(self):
        self.pads, self.tracks, self.vias = [], [], []
        self.holes = []       # (x, y, drill) non-plated or plated drills (for hole-to-hole / edge)
        self.outline = None   # (x0, y0, x1, y1, r)
        self.zones = []       # dict(net, layer, poly)
        self.keepouts = []

    # --- helpers
    def track(self, layer, net, width, *pts):
        t = Track(layer, net, width, [tuple(p) for p in pts])
        self.tracks.append(t)
        return t

    def via(self, x, y, net, dia=0.8, drill=0.4):
        v = Via(x, y, net, dia, drill)
        self.vias.append(v)
        return v

    def all_shapes(self):
        S = []
        for p in self.pads:
            S += p.shapes()
        for t in self.tracks:
            S += t.shapes()
        for v in self.vias:
            S += v.shapes()
        return S


def check_clearance(board, clearance=0.2, verbose=True):
    """Pairwise same-layer clearance between shapes of different nets (zone not considered)."""
    shapes = board.all_shapes()
    byl = collections.defaultdict(list)
    for s in shapes:
        byl[s.layer].append(s)
    errs = []
    for L, lst in byl.items():
        # simple uniform grid broad-phase
        cell = 10.0
        grid = collections.defaultdict(list)
        for i, s in enumerate(lst):
            b = s.bbox
            for gx in range(int((b[0] - clearance) // cell), int((b[2] + clearance) // cell) + 1):
                for gy in range(int((b[1] - clearance) // cell), int((b[3] + clearance) // cell) + 1):
                    grid[(gx, gy)].append(i)
        seen = set()
        for ids in grid.values():
            for ii in range(len(ids)):
                for jj in range(ii + 1, len(ids)):
                    i, j = ids[ii], ids[jj]
                    if (i, j) in seen:
                        continue
                    seen.add((i, j))
                    a, b = lst[i], lst[j]
                    if a.net == b.net and a.net:
                        continue
                    if a.ref and a.ref == b.ref and a.ref not in ("trk", "via"):
                        continue
                    ab, bb = a.bbox, b.bbox
                    if ab[0] - clearance > bb[2] or bb[0] - clearance > ab[2] or ab[1] - clearance > bb[3] or bb[1] - clearance > ab[3]:
                        continue
                    d = shape_dist(a, b)
                    if d < clearance - 1e-6:
                        errs.append((L, round(d, 3), a.ref or a.tag, a.net, b.ref or b.tag, b.net, a.g, b.g))
    return errs


def check_connectivity(board, netnames, zone_nets=("GND",)):
    """Union pads/tracks/vias by touching copper of the same net on the same layer (vias join layers).
    Returns {net: [groups]} for nets that are split into >1 islands (zone nets are reported
    separately, because they are completed by the pour)."""
    shapes = board.all_shapes()
    parent = {}
    def f(x):
        while parent.setdefault(x, x) != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    def u(a, b):
        parent[f(a)] = f(b)
    idx = list(range(len(shapes)))
    byk = collections.defaultdict(list)
    for i, s in enumerate(shapes):
        byk[(s.layer, s.net)].append(i)
    for (L, net), ids in byk.items():
        if not net:
            continue
        for ii in range(len(ids)):
            a = shapes[ids[ii]]
            for jj in range(ii + 1, len(ids)):
                b = shapes[ids[jj]]
                ab, bb = a.bbox, b.bbox
                if ab[0] > bb[2] or bb[0] > ab[2] or ab[1] > bb[3] or bb[1] > ab[3]:
                    continue
                if shape_dist(a, b) <= 1e-6:
                    u(ids[ii], ids[jj])
    # join the two layer copies of a through-hole pad / via
    owner = collections.defaultdict(list)
    for i, s in enumerate(shapes):
        if s.ref and s.ref not in ("trk", "via"):
            owner[s.ref].append(i)
    for ref, ids in owner.items():
        for k in ids[1:]:
            u(ids[0], k)
    # vias: connect their 2 layer-shapes
    vi = [i for i, s in enumerate(shapes) if s.tag == "" and s.ref == "via"]
    pos = collections.defaultdict(list)
    for i in vi:
        pos[tuple(shapes[i].g[:2])].append(i)
    for ids in pos.values():
        for k in ids[1:]:
            u(ids[0], k)
    # collect pads per net and see if they are in the same island
    res = {}
    padsets = collections.defaultdict(list)
    for i, s in enumerate(shapes):
        if s.ref and s.ref not in ("trk", "via") and s.net:
            padsets[s.net].append((s.ref, f(i)))
    for net, lst in padsets.items():
        groups = collections.defaultdict(set)
        for ref, root in lst:
            groups[root].add(ref)
        if len(groups) > 1:
            res[net] = [sorted(g) for g in groups.values()]
    return res


def pour_check(board, outline, zone_net="GND", clearance=0.4, edge=0.5, step=0.25):
    """Approximate B.Cu pour fill: which GND pads / vias / tracks end up in which connected copper
    region?  Cells blocked by foreign copper (+clearance) or by the board edge are removed; GND
    copper counts as open.  Returns (components, unreachable) where components maps component-id ->
    list of GND item names."""
    from collections import deque
    x0, y0, x1, y1, r = outline
    gx0, gy0 = x0 + edge, y0 + edge
    nx = int((x1 - x0 - 2 * edge) / step) + 1
    ny = int((y1 - y0 - 2 * edge) / step) + 1
    blocked = bytearray(nx * ny)
    shapes = [s for s in board.all_shapes() if s.layer == "B.Cu"]
    # drilled holes of NPTH (mounting holes) block the pour as well
    for (hx, hy, d) in board.holes:
        if d >= 3.0:
            shapes.append(Shape("cap", "HOLE", "B.Cu", (hx, hy, hx, hy, d / 2 + 0.2)))
    gnd = []
    for s in shapes:
        if s.net == zone_net:
            gnd.append(s)
            continue
        c = clearance
        b = s.bbox
        ia, ib = max(0, int((b[0] - c - gx0) / step) - 1), min(nx - 1, int((b[2] + c - gx0) / step) + 1)
        ja, jb = max(0, int((b[1] - c - gy0) / step) - 1), min(ny - 1, int((b[3] + c - gy0) / step) + 1)
        for j in range(ja, jb + 1):
            py = gy0 + j * step
            for i in range(ia, ib + 1):
                px = gx0 + i * step
                if s.kind == "cap":
                    d = pt_seg_dist((px, py), s.g[:2], s.g[2:4]) - s.g[4]
                else:
                    cx, cy, hw, hh = s.g
                    dx, dy = max(0.0, abs(px - cx) - hw), max(0.0, abs(py - cy) - hh)
                    d = math.hypot(dx, dy)
                if d < c:
                    blocked[j * nx + i] = 1
    # rounded corners: block cells outside the rounded rectangle
    for j in range(ny):
        py = gy0 + j * step
        for i in range(nx):
            px = gx0 + i * step
            for (cx, cy) in ((x0 + r, y0 + r), (x1 - r, y0 + r), (x0 + r, y1 - r), (x1 - r, y1 - r)):
                if (px < x0 + r and cx == x0 + r or px > x1 - r and cx == x1 - r) and (py < y0 + r and cy == y0 + r or py > y1 - r and cy == y1 - r):
                    if math.hypot(px - cx, py - cy) > r - edge:
                        blocked[j * nx + i] = 1
    comp = [0] * (nx * ny)
    cid = 0
    for start in range(nx * ny):
        if blocked[start] or comp[start]:
            continue
        cid += 1
        q = deque([start]); comp[start] = cid
        while q:
            k = q.popleft()
            i, j = k % nx, k // nx
            for ni, nj in ((i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)):
                if 0 <= ni < nx and 0 <= nj < ny:
                    kk = nj * nx + ni
                    if not blocked[kk] and not comp[kk]:
                        comp[kk] = cid
                        q.append(kk)
    sizes = collections.Counter(c for c in comp if c)
    res = collections.defaultdict(list)
    unreachable = []
    for s in gnd:
        # sample cells within the shape's own area (+0.6 mm for thermal spokes) and take any open one
        b = s.bbox
        found = set()
        ia, ib = max(0, int((b[0] - 0.7 - gx0) / step)), min(nx - 1, int((b[2] + 0.7 - gx0) / step))
        ja, jb = max(0, int((b[1] - 0.7 - gy0) / step)), min(ny - 1, int((b[3] + 0.7 - gy0) / step))
        for j in range(ja, jb + 1):
            for i in range(ia, ib + 1):
                c_ = comp[j * nx + i]
                if c_:
                    found.add(c_)
        if not found:
            unreachable.append(s.ref or s.tag)
        else:
            # choose the biggest region it touches
            best = max(found, key=lambda c_: sizes[c_])
            res[best].append(s.ref or s.tag)
    return sizes, res, unreachable
