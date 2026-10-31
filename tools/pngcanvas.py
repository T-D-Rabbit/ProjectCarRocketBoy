"""Tiny dependency-free raster canvas -> PNG (used for PCB previews and simulation plots).

Only the Python standard library is used (zlib/struct) because numpy/matplotlib/PIL
are not available in every environment this project is built in.
"""
import zlib, struct, math

_F = {
 '0': "01110 10001 10011 10101 11001 10001 01110", '1': "00100 01100 00100 00100 00100 00100 01110",
 '2': "01110 10001 00001 00010 00100 01000 11111", '3': "11110 00001 00001 01110 00001 00001 11110",
 '4': "00010 00110 01010 10010 11111 00010 00010", '5': "11111 10000 11110 00001 00001 10001 01110",
 '6': "00110 01000 10000 11110 10001 10001 01110", '7': "11111 00001 00010 00100 01000 01000 01000",
 '8': "01110 10001 10001 01110 10001 10001 01110", '9': "01110 10001 10001 01111 00001 00010 01100",
 'A': "01110 10001 10001 11111 10001 10001 10001", 'B': "11110 10001 10001 11110 10001 10001 11110",
 'C': "01110 10001 10000 10000 10000 10001 01110", 'D': "11110 10001 10001 10001 10001 10001 11110",
 'E': "11111 10000 10000 11110 10000 10000 11111", 'F': "11111 10000 10000 11110 10000 10000 10000",
 'G': "01110 10001 10000 10111 10001 10001 01111", 'H': "10001 10001 10001 11111 10001 10001 10001",
 'I': "01110 00100 00100 00100 00100 00100 01110", 'J': "00111 00010 00010 00010 00010 10010 01100",
 'K': "10001 10010 10100 11000 10100 10010 10001", 'L': "10000 10000 10000 10000 10000 10000 11111",
 'M': "10001 11011 10101 10101 10001 10001 10001", 'N': "10001 11001 10101 10011 10001 10001 10001",
 'O': "01110 10001 10001 10001 10001 10001 01110", 'P': "11110 10001 10001 11110 10000 10000 10000",
 'Q': "01110 10001 10001 10001 10101 10010 01101", 'R': "11110 10001 10001 11110 10100 10010 10001",
 'S': "01111 10000 10000 01110 00001 00001 11110", 'T': "11111 00100 00100 00100 00100 00100 00100",
 'U': "10001 10001 10001 10001 10001 10001 01110", 'V': "10001 10001 10001 10001 10001 01010 00100",
 'W': "10001 10001 10001 10101 10101 11011 10001", 'X': "10001 10001 01010 00100 01010 10001 10001",
 'Y': "10001 10001 01010 00100 00100 00100 00100", 'Z': "11111 00001 00010 00100 01000 10000 11111",
 '.': "00000 00000 00000 00000 00000 01100 01100", '-': "00000 00000 00000 11111 00000 00000 00000",
 '+': "00000 00100 00100 11111 00100 00100 00000", '/': "00001 00010 00010 00100 01000 01000 10000",
 ':': "00000 01100 01100 00000 01100 01100 00000", ' ': "00000 00000 00000 00000 00000 00000 00000",
 '(': "00010 00100 01000 01000 01000 00100 00010", ')': "01000 00100 00010 00010 00010 00100 01000",
 '%': "11001 11010 00010 00100 01000 01011 10011", '_': "00000 00000 00000 00000 00000 00000 11111",
 '=': "00000 00000 11111 00000 11111 00000 00000", ',': "00000 00000 00000 00000 01100 00100 01000",
 '<': "00010 00100 01000 10000 01000 00100 00010", '>': "01000 00100 00010 00001 00010 00100 01000",
 '[': "01110 01000 01000 01000 01000 01000 01110", ']': "01110 00010 00010 00010 00010 00010 01110",
}
FONT = {k: [row for row in v.split()] for k, v in _F.items()}


def rgb(h):
    h = h.lstrip('#')
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


class Canvas:
    def __init__(self, w, h, bg=(255, 255, 255)):
        self.w, self.h = int(w), int(h)
        self.px = bytearray(bytes(bg) * (self.w * self.h))

    def set(self, x, y, c, a=1.0):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            if a >= 1.0:
                self.px[i:i + 3] = bytes(c)
            else:
                p = self.px
                p[i] = int(p[i] * (1 - a) + c[0] * a)
                p[i + 1] = int(p[i + 1] * (1 - a) + c[1] * a)
                p[i + 2] = int(p[i + 2] * (1 - a) + c[2] * a)

    def rect(self, x0, y0, x1, y1, c, a=1.0):
        x0, x1 = sorted((int(round(x0)), int(round(x1))))
        y0, y1 = sorted((int(round(y0)), int(round(y1))))
        for y in range(max(0, y0), min(self.h, y1 + 1)):
            for x in range(max(0, x0), min(self.w, x1 + 1)):
                self.set(x, y, c, a)

    def circle(self, cx, cy, r, c, a=1.0, ring=None):
        r0 = int(math.floor(r))
        for y in range(int(cy) - r0 - 1, int(cy) + r0 + 2):
            for x in range(int(cx) - r0 - 1, int(cx) + r0 + 2):
                d = math.hypot(x + .5 - cx, y + .5 - cy)
                if d <= r and (ring is None or d >= r - ring):
                    self.set(x, y, c, a)

    def line(self, x0, y0, x1, y1, c, width=1.0, a=1.0):
        # capsule rasterisation
        hw = max(width / 2.0, 0.5)
        minx, maxx = int(min(x0, x1) - hw - 1), int(max(x0, x1) + hw + 1)
        miny, maxy = int(min(y0, y1) - hw - 1), int(max(y0, y1) + hw + 1)
        dx, dy = x1 - x0, y1 - y0
        L2 = dx * dx + dy * dy
        for y in range(max(0, miny), min(self.h, maxy + 1)):
            for x in range(max(0, minx), min(self.w, maxx + 1)):
                px, py = x + .5, y + .5
                t = 0 if L2 == 0 else max(0, min(1, ((px - x0) * dx + (py - y0) * dy) / L2))
                if math.hypot(px - (x0 + t * dx), py - (y0 + t * dy)) <= hw:
                    self.set(x, y, c, a)

    def poly(self, pts, c, a=1.0):
        ys = [p[1] for p in pts]
        for y in range(max(0, int(min(ys))), min(self.h, int(max(ys)) + 1)):
            yy = y + .5
            xs = []
            n = len(pts)
            for i in range(n):
                (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
                if (ya <= yy < yb) or (yb <= yy < ya):
                    xs.append(xa + (yy - ya) * (xb - xa) / (yb - ya))
            xs.sort()
            for i in range(0, len(xs) - 1, 2):
                for x in range(int(xs[i]), int(xs[i + 1]) + 1):
                    self.set(x, y, c, a)

    def text(self, x, y, s, c=(0, 0, 0), scale=1, vertical=False):
        cx, cy = x, y
        for ch in str(s).upper():
            g = FONT.get(ch, FONT[' '])
            for ry, row in enumerate(g):
                for rx, bit in enumerate(row):
                    if bit == '1':
                        for sy in range(scale):
                            for sx in range(scale):
                                if vertical:
                                    self.set(int(cx + ry * scale + sy), int(cy - rx * scale - sx), c)
                                else:
                                    self.set(int(cx + rx * scale + sx), int(cy + ry * scale + sy), c)
            if vertical:
                cy -= 6 * scale
            else:
                cx += 6 * scale

    def save(self, path):
        raw = bytearray()
        stride = self.w * 3
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y * stride:(y + 1) * stride]

        def chunk(t, d):
            c = struct.pack(">I", len(d)) + t + d
            return c + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)

        png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 2, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b"")
        open(path, "wb").write(png)
