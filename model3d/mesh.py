"""Small triangle-mesh toolkit (pure Python): primitives, polygon-with-holes extrusion, STL/OBJ export."""
import math, struct


# ------------------------------------------------------------------ 2D polygon triangulation (with holes)
def area2(p):
    return sum(p[i][0] * p[(i + 1) % len(p)][1] - p[(i + 1) % len(p)][0] * p[i][1] for i in range(len(p)))


def ccw(p):
    return p if area2(p) > 0 else p[::-1]


def cw(p):
    return p if area2(p) < 0 else p[::-1]


def _cross(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _proper_cross(p1, p2, q1, q2):
    def s(a, b, c):
        v = _cross(a, b, c)
        return 0 if abs(v) < 1e-12 else (1 if v > 0 else -1)
    d1, d2, d3, d4 = s(q1, q2, p1), s(q1, q2, p2), s(p1, p2, q1), s(p1, p2, q2)
    return d1 * d2 < 0 and d3 * d4 < 0


def _bridge(outer, holes):
    outer = list(ccw(outer))
    holes = [cw(h) for h in holes]
    for hole in sorted(holes, key=lambda h: -max(p[0] for p in h)):
        mi = max(range(len(hole)), key=lambda i: hole[i][0])
        M = hole[mi]
        order = sorted(range(len(outer)), key=lambda i: (outer[i][0] - M[0]) ** 2 + (outer[i][1] - M[1]) ** 2)
        chosen = None
        for ci in order:
            P = outer[ci]
            ok = True
            polys = [outer] + [h for h in holes]
            for poly in polys:
                n = len(poly)
                for k in range(n):
                    a, b = poly[k], poly[(k + 1) % n]
                    if a == P or b == P or a == M or b == M:
                        continue
                    if _proper_cross(M, P, a, b):
                        ok = False
                        break
                if not ok:
                    break
            if ok:
                chosen = ci
                break
        ci = chosen if chosen is not None else order[0]
        seq = hole[mi:] + hole[:mi]
        outer = outer[:ci + 1] + seq + [M] + [outer[ci]] + outer[ci + 1:]
    return outer


def triangulate(outer, holes=()):
    poly = _bridge(outer, list(holes)) if holes else list(ccw(outer))
    n = len(poly)
    idx = list(range(n))
    tris = []
    k = 0
    guard = 0
    while len(idx) > 3 and guard < 50 * n:
        guard += 1
        m = len(idx)
        k %= m
        i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % m]
        a, b, c = poly[i0], poly[i1], poly[i2]
        ear = _cross(a, b, c) > 1e-12
        if ear:
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                p = poly[j]
                if p == a or p == b or p == c:
                    continue
                d1, d2, d3 = _cross(a, b, p), _cross(b, c, p), _cross(c, a, p)
                if d1 >= -1e-12 and d2 >= -1e-12 and d3 >= -1e-12:
                    ear = False
                    break
        if ear:
            tris.append((a, b, c))
            idx.pop(k)
        else:
            k += 1
    if len(idx) == 3:
        a, b, c = (poly[i] for i in idx)
        if abs(_cross(a, b, c)) > 1e-12:
            tris.append((a, b, c) if _cross(a, b, c) > 0 else (a, c, b))
    return tris


def circle_pts(cx, cy, r, n=24, start=0.0):
    return [(cx + r * math.cos(start + 2 * math.pi * i / n), cy + r * math.sin(start + 2 * math.pi * i / n)) for i in range(n)]


def rect_pts(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


def rrect_pts(x0, y0, x1, y1, r, n=6, top_only=False):
    """Rounded rectangle (CCW); top_only rounds only the y1 corners."""
    pts = [(x0, y0), (x1, y0)] if top_only else []
    if not top_only:
        for (cx, cy, a0) in ((x1 - r, y0 + r, -90), (x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90), (x0 + r, y0 + r, 180)):
            pts += [(cx + r * math.cos(math.radians(a0 + 90 * i / n)), cy + r * math.sin(math.radians(a0 + 90 * i / n))) for i in range(n + 1)]
        return pts
    for (cx, cy, a0) in ((x1 - r, y1 - r, 0), (x0 + r, y1 - r, 90)):
        pts += [(cx + r * math.cos(math.radians(a0 + 90 * i / n)), cy + r * math.sin(math.radians(a0 + 90 * i / n))) for i in range(n + 1)]
    return pts


# ------------------------------------------------------------------ mesh
PLANES = {
    # (u, v, w) -> (x, y, z); every mapping is right handed
    "xy": lambda u, v, w: (u, v, w),
    "yz": lambda u, v, w: (w, u, v),
    "zx": lambda u, v, w: (v, w, u),
}


class Mesh:
    def __init__(self):
        self.tris = []      # ((x,y,z),(x,y,z),(x,y,z), material)

    def add(self, a, b, c, mat):
        self.tris.append((tuple(a), tuple(b), tuple(c), mat))

    def extend(self, other):
        self.tris += other.tris

    def copy(self):
        m = Mesh()
        m.tris = list(self.tris)
        return m

    # ---- primitives
    def quad(self, a, b, c, d, mat):
        self.add(a, b, c, mat)
        self.add(a, c, d, mat)

    def box(self, cx, cy, cz, sx, sy, sz, mat):
        x0, x1, y0, y1, z0, z1 = cx - sx / 2, cx + sx / 2, cy - sy / 2, cy + sy / 2, cz - sz / 2, cz + sz / 2
        q = self.quad
        q((x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1), mat)      # +z
        q((x0, y1, z0), (x1, y1, z0), (x1, y0, z0), (x0, y0, z0), mat)      # -z
        q((x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1), mat)      # -y
        q((x1, y1, z0), (x0, y1, z0), (x0, y1, z1), (x1, y1, z1), mat)      # +y
        q((x0, y1, z0), (x0, y0, z0), (x0, y0, z1), (x0, y1, z1), mat)      # -x
        q((x1, y0, z0), (x1, y1, z0), (x1, y1, z1), (x1, y0, z1), mat)      # +x
        return self

    def extrude(self, outer, holes, w0, w1, mat, plane="xy"):
        f = PLANES[plane]
        for a, b, c in triangulate(outer, holes):
            self.add(f(*a, w1), f(*b, w1), f(*c, w1), mat)
            self.add(f(*a, w0), f(*c, w0), f(*b, w0), mat)
        loops = [ccw(outer)] + [cw(h) for h in holes]
        for poly in loops:
            n = len(poly)
            for i in range(n):
                p, q = poly[i], poly[(i + 1) % n]
                self.quad(f(*p, w0), f(*q, w0), f(*q, w1), f(*p, w1), mat)
        return self

    def cyl(self, axis, c, r, length, mat, seg=28, r2=None, caps=True):
        """Solid cylinder (or cone if r2 given) centred at c along axis 'x'|'y'|'z'."""
        plane = {"z": "xy", "x": "yz", "y": "zx"}[axis]
        f = PLANES[plane]
        r2 = r if r2 is None else r2
        w0, w1 = -length / 2, length / 2
        ring0 = circle_pts(0, 0, r, seg)
        ring1 = circle_pts(0, 0, r2, seg)
        add = lambda p: (p[0] + c[0], p[1] + c[1], p[2] + c[2])
        for i in range(seg):
            a, b = ring0[i], ring0[(i + 1) % seg]
            a1, b1 = ring1[i], ring1[(i + 1) % seg]
            self.quad(add(f(*a, w0)), add(f(*b, w0)), add(f(*b1, w1)), add(f(*a1, w1)), mat)
            if caps:
                self.add(add(f(0, 0, w1)), add(f(*a1, w1)), add(f(*b1, w1)), mat)
                self.add(add(f(0, 0, w0)), add(f(*b, w0)), add(f(*a, w0)), mat)
        return self

    def sphere(self, c, r, mat, seg=18):
        rings = seg // 2
        for i in range(rings):
            t0, t1 = math.pi * i / rings, math.pi * (i + 1) / rings
            for j in range(seg):
                p0, p1 = 2 * math.pi * j / seg, 2 * math.pi * (j + 1) / seg
                pt = lambda t, p: (c[0] + r * math.sin(t) * math.cos(p), c[1] + r * math.sin(t) * math.sin(p), c[2] + r * math.cos(t))
                a, b, cc, d = pt(t0, p0), pt(t0, p1), pt(t1, p1), pt(t1, p0)
                if i > 0:
                    self.add(a, d, b, mat)
                if i < rings - 1:
                    self.add(b, d, cc, mat)
        return self

    # ---- transforms
    def translated(self, dx, dy, dz):
        m = Mesh()
        m.tris = [((a[0] + dx, a[1] + dy, a[2] + dz), (b[0] + dx, b[1] + dy, b[2] + dz), (c[0] + dx, c[1] + dy, c[2] + dz), mt)
                  for a, b, c, mt in self.tris]
        return m

    def rotated_x(self, ang, cy=0.0, cz=0.0):
        co, si = math.cos(ang), math.sin(ang)
        r = lambda p: (p[0], cy + (p[1] - cy) * co - (p[2] - cz) * si, cz + (p[1] - cy) * si + (p[2] - cz) * co)
        m = Mesh()
        m.tris = [(r(a), r(b), r(c), mt) for a, b, c, mt in self.tris]
        return m

    def mirrored_x(self):
        m = Mesh()
        m.tris = [((-a[0], a[1], a[2]), (-c[0], c[1], c[2]), (-b[0], b[1], b[2]), mt) for a, b, c, mt in self.tris]
        return m

    def bbox(self):
        xs = [p[0] for t in self.tris for p in t[:3]]
        ys = [p[1] for t in self.tris for p in t[:3]]
        zs = [p[2] for t in self.tris for p in t[:3]]
        return (min(xs), min(ys), min(zs)), (max(xs), max(ys), max(zs))

    # ---- export
    def write_stl(self, path, name="rocketboy"):
        with open(path, "wb") as f:
            f.write(name.encode()[:80].ljust(80, b" "))
            f.write(struct.pack("<I", len(self.tris)))
            for a, b, c, _ in self.tris:
                ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
                vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
                nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
                L = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
                f.write(struct.pack("<12fH", nx / L, ny / L, nz / L, *a, *b, *c, 0))


def write_obj(groups, materials, path):
    """groups: {name: Mesh}; materials: {id: (name, (r,g,b))}.  Writes OBJ + MTL (units: mm)."""
    mtl = path[:-4] + ".mtl"
    with open(mtl, "w") as f:
        for mid, (nm, col) in materials.items():
            f.write("newmtl %s\nKd %.3f %.3f %.3f\nKa 0.1 0.1 0.1\nKs 0.2 0.2 0.2\nNs 20\n\n" % (nm, col[0] / 255, col[1] / 255, col[2] / 255))
    with open(path, "w") as f:
        f.write("# RocketBoy assembly, units mm, x right, y forward, z up\nmtllib %s\n" % os.path.basename(mtl))
        vid = {}
        vlist = []
        def vi(p):
            k = (round(p[0], 3), round(p[1], 3), round(p[2], 3))
            if k not in vid:
                vid[k] = len(vlist) + 1
                vlist.append(k)
            return vid[k]
        body = []
        for gname, mesh in groups.items():
            body.append("o %s\n" % gname)
            cur = None
            for a, b, c, mt in mesh.tris:
                if mt != cur:
                    body.append("usemtl %s\n" % materials[mt][0])
                    cur = mt
                body.append("f %d %d %d\n" % (vi(a), vi(b), vi(c)))
        for v in vlist:
            f.write("v %.3f %.3f %.3f\n" % v)
        f.write("".join(body))


import os
