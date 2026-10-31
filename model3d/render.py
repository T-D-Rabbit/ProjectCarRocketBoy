"""Dependency-free software renderer (z-buffer, flat shading) + PNG/GIF writers for the 3D previews."""
import math, struct, zlib


class Camera:
    def __init__(self, eye, target, fov=35.0, up=(0, 0, 1)):
        self.eye, self.target, self.fov = eye, target, fov
        f = [target[i] - eye[i] for i in range(3)]
        L = math.sqrt(sum(c * c for c in f))
        f = [c / L for c in f]
        r = [f[1] * up[2] - f[2] * up[1], f[2] * up[0] - f[0] * up[2], f[0] * up[1] - f[1] * up[0]]
        Lr = math.sqrt(sum(c * c for c in r))
        r = [c / Lr for c in r]
        u = [r[1] * f[2] - r[2] * f[1], r[2] * f[0] - r[0] * f[2], r[0] * f[1] - r[1] * f[0]]
        self.f, self.r, self.u = f, r, u

    def to_cam(self, p):
        d = (p[0] - self.eye[0], p[1] - self.eye[1], p[2] - self.eye[2])
        return (d[0] * self.r[0] + d[1] * self.r[1] + d[2] * self.r[2],
                d[0] * self.u[0] + d[1] * self.u[1] + d[2] * self.u[2],
                d[0] * self.f[0] + d[1] * self.f[1] + d[2] * self.f[2])


LIGHT = (-0.45, -0.55, 0.70)
_L = math.sqrt(sum(c * c for c in LIGHT))
LIGHT = tuple(c / _L for c in LIGHT)


class Raster:
    def __init__(self, W, H, K=9):
        self.W, self.H, self.K = W, H, K
        self.idx = bytearray(W * H)
        self.w = [0.0] * (W * H)

    def clear(self, bg=0):
        self.idx = bytearray([bg]) * (self.W * self.H)
        self.w = [0.0] * (self.W * self.H)

    def draw(self, tris, cam):
        W, H, K = self.W, self.H, self.K
        fpx = (H / 2) / math.tan(math.radians(cam.fov) / 2)
        cx, cy = W / 2, H / 2
        idx, zb = self.idx, self.w
        for a, b, c, mat in tris:
            # shading from the world-space normal
            ux, uy, uz = b[0] - a[0], b[1] - a[1], b[2] - a[2]
            vx, vy, vz = c[0] - a[0], c[1] - a[1], c[2] - a[2]
            nx, ny, nz = uy * vz - uz * vy, uz * vx - ux * vz, ux * vy - uy * vx
            Ln = math.sqrt(nx * nx + ny * ny + nz * nz)
            if Ln < 1e-12:
                continue
            d = abs(nx * LIGHT[0] + ny * LIGHT[1] + nz * LIGHT[2]) / Ln
            lvl = min(K - 1, int((0.30 + 0.70 * d) * K))
            col = 1 + mat * K + lvl
            pts = []
            ok = True
            for p in (a, b, c):
                x, y, z = cam.to_cam(p)
                if z < 20:
                    ok = False
                    break
                pts.append((cx + fpx * x / z, cy - fpx * y / z, 1.0 / z))
            if not ok:
                continue
            ymin = min(p[1] for p in pts)
            ymax = max(p[1] for p in pts)
            if ymax < 0 or ymin >= H:
                continue
            for yi in range(max(0, int(ymin)), min(H - 1, int(ymax)) + 1):
                yy = yi + 0.5
                xs = []
                for i in range(3):
                    p, q = pts[i], pts[(i + 1) % 3]
                    if (p[1] <= yy < q[1]) or (q[1] <= yy < p[1]):
                        t = (yy - p[1]) / (q[1] - p[1])
                        xs.append((p[0] + t * (q[0] - p[0]), p[2] + t * (q[2] - p[2])))
                if len(xs) < 2:
                    continue
                xs.sort()
                (xl, wl), (xr, wr) = xs[0], xs[-1]
                x0, x1 = max(0, int(xl + 0.5)), min(W - 1, int(xr - 0.5 + 1e-9))
                if x1 < x0:
                    continue
                span = xr - xl
                row = yi * W
                if span < 1e-9:
                    continue
                dw = (wr - wl) / span
                wv = wl + dw * (x0 + 0.5 - xl)
                for xi in range(x0, x1 + 1):
                    if wv > zb[row + xi]:
                        zb[row + xi] = wv
                        idx[row + xi] = col
                    wv += dw

    def palette(self, materials, bg):
        pal = [bg]
        K = self.K
        for mid in sorted(materials):
            name, (r, g, b) = materials[mid]
            for l in range(K):
                s = (0.30 + 0.70 * (l + 0.5) / K)
                pal.append((min(255, int(r * s * 1.12)), min(255, int(g * s * 1.12)), min(255, int(b * s * 1.12))))
        return pal


def indices_to_png(path, idx, W, H, pal):
    raw = bytearray()
    for y in range(H):
        raw.append(0)
        row = idx[y * W:(y + 1) * W]
        for v in row:
            raw += bytes(pal[v])

    def chunk(t, d):
        c = struct.pack(">I", len(d)) + t + d
        return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
    png += chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
    open(path, "wb").write(png)


# ------------------------------------------------------------------ GIF
def _lzw(data, min_code=8):
    clear, eoi = 1 << min_code, (1 << min_code) + 1
    out = bytearray()
    bitbuf, nbits = 0, 0

    def emit(code, size):
        nonlocal bitbuf, nbits
        bitbuf |= code << nbits
        nbits += size
        while nbits >= 8:
            out.append(bitbuf & 255)
            bitbuf >>= 8
            nbits -= 8

    size = min_code + 1
    table = {}
    nxt = eoi + 1
    emit(clear, size)
    prefix = data[0]
    for byte in data[1:]:
        key = (prefix, byte)
        if key in table:
            prefix = table[key]
            continue
        emit(prefix, size)
        if nxt < 4096:
            table[key] = nxt
            nxt += 1
            if nxt > (1 << size) and size < 12:
                size += 1
        else:
            emit(clear, size)
            table = {}
            nxt = eoi + 1
            size = min_code + 1
        prefix = byte
    emit(prefix, size)
    emit(eoi, size)
    if nbits:
        out.append(bitbuf & 255)
    return bytes(out)


def write_gif(path, frames, W, H, pal, delay_cs=12):
    pal = list(pal) + [(0, 0, 0)] * (256 - len(pal))
    out = bytearray(b"GIF89a")
    out += struct.pack("<HHBBB", W, H, 0xF7, 0, 0)
    for r, g, b in pal:
        out += bytes((r, g, b))
    out += b"\x21\xFF\x0BNETSCAPE2.0\x03\x01\x00\x00\x00"
    for fr in frames:
        out += b"\x21\xF9\x04\x00" + struct.pack("<H", delay_cs) + b"\x00\x00"
        out += b"\x2C" + struct.pack("<HHHHB", 0, 0, W, H, 0)
        out += b"\x08"
        data = _lzw(bytes(fr))
        for i in range(0, len(data), 255):
            blk = data[i:i + 255]
            out += bytes((len(blk),)) + blk
        out += b"\x00"
    out += b"\x3B"
    open(path, "wb").write(bytes(out))
