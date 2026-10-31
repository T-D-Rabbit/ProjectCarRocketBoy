#!/usr/bin/env python3
"""Render docs/SPECS.md as docs/RocketBoy_Specs.pdf  (pure Python, no libraries; Helvetica built-in fonts).

    python3 docs/make_specs_pdf.py
"""
import os, re, sys, zlib, struct, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PW, PH = 595.28, 841.89
MX, MT, MB = 42.0, 46.0, 46.0

HELV = {' ': 278, '!': 278, '"': 355, '#': 556, '$': 556, '%': 889, '&': 667, "'": 191, '(': 333, ')': 333, '*': 389, '+': 584, ',': 278,
        '-': 333, '.': 278, '/': 278, ':': 278, ';': 278, '<': 584, '=': 584, '>': 584, '?': 556, '@': 1015, '[': 278, '\\': 278, ']': 278,
        '^': 469, '_': 556, '`': 333, '{': 334, '|': 260, '}': 334, '~': 584}
for c in "0123456789":
    HELV[c] = 556
for c, w in zip("ABCDEFGHIJKLMNOPQRSTUVWXYZ", [667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556, 833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611]):
    HELV[c] = w
for c, w in zip("abcdefghijklmnopqrstuvwxyz", [556, 556, 500, 556, 556, 278, 556, 556, 222, 222, 500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500, 500]):
    HELV[c] = w
HELV.update({'\u00d7': 584, '\u00b0': 400, '\u00b5': 556, '\u00b7': 278, '\u00b1': 584, '\u2013': 556, '\u2014': 1000})


def tw(s, size, bold=False):
    return sum(HELV.get(ch, 556) for ch in s) * size / 1000.0 * (1.07 if bold else 1.0)


def clean(s):
    s = s.replace("**", "").replace("`", "")
    rep = {"\u2248": "~", "\u2192": "->", "\u03a9": "ohm", "\u2265": ">=", "\u2264": "<=", "\u03bc": "mu", "\u00b5": "\u00b5", "\u2192": "->",
           "\u2022": "-", "\u00b7": "\u00b7", "\u2212": "-", "\u2011": "-"}
    for a, b in rep.items():
        s = s.replace(a, b)
    return s


def wrap(text, width, size, bold=False):
    words = text.split(" ")
    lines, cur = [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(t, size, bold) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    lines.append(cur)
    return lines


# ------------------------------------------------------------------ parse markdown
def parse_md(path):
    items = []
    lines = open(path, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(lines):
        ln = lines[i].rstrip()
        if ln.startswith("# "):
            items.append(("h1", clean(ln[2:])))
        elif ln.startswith("## "):
            items.append(("h2", clean(ln[3:])))
        elif ln.startswith("### "):
            items.append(("h3", clean(ln[4:])))
        elif ln.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                cells = [clean(c.strip()) for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells):
                    rows.append(cells)
                i += 1
            items.append(("table", rows))
            continue
        elif ln.strip():
            items.append(("p", clean(ln.strip())))
        i += 1
    return items


# ------------------------------------------------------------------ layout -> drawing ops
class Doc:
    def __init__(self):
        self.pages = []
        self.new_page()

    def new_page(self):
        self.pages.append([])
        self.y = PH - MT

    @property
    def ops(self):
        return self.pages[-1]

    def need(self, h):
        if self.y - h < MB:
            self.new_page()
            return True
        return False

    def text(self, x, y, s, size=9, bold=False, color=(0, 0, 0)):
        self.ops.append(("text", x, y, s, size, bold, color))

    def rect(self, x, y, w, h, fill=None, stroke=None, lw=0.5):
        self.ops.append(("rect", x, y, w, h, fill, stroke, lw))

    def image(self, x, y, w, h):
        self.ops.append(("img", x, y, w, h))


def layout(items, img_size):
    d = Doc()
    W = PW - 2 * MX
    first_table_in_section = True
    for kind, val in items:
        if kind == "h1":
            d.text(MX, d.y - 20, val, 22, True, (0.10, 0.18, 0.30))
            d.y -= 30
            d.rect(MX, d.y, W, 1.5, fill=(1.0, 0.55, 0.1))
            d.y -= 8
            if img_size:                                 # picture under the title
                iw, ih = img_size
                h = 160.0
                w = h * iw / ih
                d.need(h)
                d.image(MX + (W - w) / 2, d.y - h, w, h)
                d.y -= h + 8
        elif kind == "h2":
            d.need(60)
            d.y -= 8
            d.rect(MX, d.y - 20, W, 20, fill=(0.10, 0.18, 0.30))
            d.text(MX + 8, d.y - 14.5, val, 12.5, True, (1, 1, 1))
            d.y -= 28
        elif kind == "h3":
            d.need(50)
            d.y -= 4
            d.text(MX, d.y - 11, val, 10.5, True, (0.10, 0.18, 0.30))
            d.y -= 17
        elif kind == "p":
            size = 8.3
            lines = wrap(val, W, size)
            d.need(len(lines) * 11 + 6)
            for l in lines:
                d.text(MX, d.y - 9, l, size, False, (0.25, 0.25, 0.25))
                d.y -= 11
            d.y -= 4
        elif kind == "table":
            rows = val
            ncol = len(rows[0])
            size = 8.2
            pad = 3.4
            nat = [max(tw(r[c], size, r is rows[0]) for r in rows if c < len(r)) + 2 * pad for c in range(ncol)]
            mn = [min(nat[c], max(34.0, tw(max(rows[0][c].split(" "), key=len), size, True) + 2 * pad)) for c in range(ncol)]
            cw = nat[:]
            if sum(cw) > W:                               # shrink the widest columns first
                avail = W - sum(mn)
                extra = [max(0.0, nat[c] - mn[c]) for c in range(ncol)]
                tot = sum(extra) or 1.0
                cw = [mn[c] + avail * extra[c] / tot for c in range(ncol)]
            else:
                spare = (W - sum(cw))
                cw = [cw[c] + spare * (nat[c] / sum(nat)) for c in range(ncol)]
            for ri, row in enumerate(rows):
                bold = ri == 0
                cells = [wrap(row[c] if c < len(row) else "", cw[c] - 2 * pad, size, bold) for c in range(ncol)]
                h = max(len(c) for c in cells) * 10.4 + 2 * pad - 1
                if d.need(h + 2) and ri > 0:             # repeat the header after a page break
                    hdr = [wrap(rows[0][c], cw[c] - 2 * pad, size, True) for c in range(ncol)]
                    hh = max(len(c) for c in hdr) * 10.4 + 2 * pad - 1
                    x = MX
                    for c in range(ncol):
                        d.rect(x, d.y - hh, cw[c], hh, fill=(0.88, 0.90, 0.94), stroke=(0.6, 0.65, 0.72))
                        for k, l in enumerate(hdr[c]):
                            d.text(x + pad, d.y - pad - 8 - k * 10.4, l, size, True)
                        x += cw[c]
                    d.y -= hh
                x = MX
                for c in range(ncol):
                    fill = (0.88, 0.90, 0.94) if bold else ((0.97, 0.98, 0.99) if ri % 2 == 0 else None)
                    d.rect(x, d.y - h, cw[c], h, fill=fill, stroke=(0.6, 0.65, 0.72))
                    for k, l in enumerate(cells[c]):
                        col = (0, 0, 0)
                        d.text(x + pad, d.y - pad - 8 - k * 10.4, l, size, bold, col)
                    x += cw[c]
                d.y -= h
            d.y -= 8
    return d


# ------------------------------------------------------------------ PDF writer
def pdf_esc(b):
    return b.replace(b"\\", b"\\\\").replace(b"(", b"\\(").replace(b")", b"\\)")


def write_pdf(doc, path, png_path):
    objs = []

    def add(data):
        objs.append(data)
        return len(objs)

    img_obj = None
    if png_path and os.path.exists(png_path):
        raw = open(png_path, "rb").read()
        pos, idat, iw, ih = 8, b"", 0, 0
        while pos < len(raw):
            ln = struct.unpack(">I", raw[pos:pos + 4])[0]
            typ = raw[pos + 4:pos + 8]
            body = raw[pos + 8:pos + 8 + ln]
            if typ == b"IHDR":
                iw, ih = struct.unpack(">II", body[:8])
            elif typ == b"IDAT":
                idat += body
            pos += 12 + ln
        img_obj = add(b"<< /Type /XObject /Subtype /Image /Width %d /Height %d /ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode "
                      b"/DecodeParms << /Predictor 15 /Colors 3 /BitsPerComponent 8 /Columns %d >> /Length %d >>\nstream\n" % (iw, ih, iw, len(idat)) + idat + b"\nendstream")
    f1 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>")
    f2 = add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>")
    page_ids, content_ids = [], []
    pages_id_placeholder = len(objs) + 1 + 2 * len(doc.pages)      # filled in below
    n = len(doc.pages)
    for pi, ops in enumerate(doc.pages):
        s = []
        for op in ops:
            if op[0] == "rect":
                _, x, y, w, h, fill, stroke, lw = op
                if fill:
                    s.append("%.3f %.3f %.3f rg %.2f %.2f %.2f %.2f re f" % (*fill, x, y, w, h))
                if stroke:
                    s.append("%.3f %.3f %.3f RG %.2f w %.2f %.2f %.2f %.2f re S" % (*stroke, lw, x, y, w, h))
            elif op[0] == "text":
                _, x, y, t, size, bold, color = op
                s.append("BT /F%d %.2f Tf %.3f %.3f %.3f rg %.2f %.2f Td (%s) Tj ET" % (2 if bold else 1, size, *color, x, y, pdf_esc(t.encode("cp1252", "replace")).decode("latin-1")))
            elif op[0] == "img":
                _, x, y, w, h = op
                s.append("q %.2f 0 0 %.2f %.2f %.2f cm /Im1 Do Q" % (w, h, x, y))
        foot = "RocketBoy specification sheet   |   page %d of %d" % (pi + 1, n)
        s.append("BT /F1 7.5 Tf 0.45 0.45 0.45 rg %.2f 26 Td (%s) Tj ET" % (MX, foot))
        stream = "\n".join(s).encode("latin-1")
        cid = add(b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream")
        content_ids.append(cid)
    pages_id = len(objs) + n + 1
    for cid in content_ids:
        res = "/Font << /F1 %d 0 R /F2 %d 0 R >>" % (f1, f2) + (" /XObject << /Im1 %d 0 R >>" % img_obj if img_obj else "")
        pid = add(("<< /Type /Page /Parent %d 0 R /MediaBox [0 0 %.2f %.2f] /Contents %d 0 R /Resources << %s >> >>" % (pages_id, PW, PH, cid, res)).encode())
        page_ids.append(pid)
    assert len(objs) + 1 == pages_id
    add(("<< /Type /Pages /Kids [%s] /Count %d >>" % (" ".join("%d 0 R" % p for p in page_ids), n)).encode())
    cat = add(("<< /Type /Catalog /Pages %d 0 R >>" % pages_id).encode())
    info = add(("<< /Title (RocketBoy specification sheet) /Producer (RocketBoy tools/docs/make_specs_pdf.py) /CreationDate (D:%s) >>" % datetime.datetime.utcnow().strftime("%Y%m%d%H%M%S")).encode())
    out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offs = []
    for i, o in enumerate(objs, 1):
        offs.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    for o in offs:
        out += b"%010d 00000 n \n" % o
    out += b"trailer\n<< /Size %d /Root %d 0 R /Info %d 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, cat, info, xref)
    open(path, "wb").write(bytes(out))
    return len(out)


if __name__ == "__main__":
    png = os.path.join(ROOT, "model3d", "out", "preview_iso.png")
    size = None
    if os.path.exists(png):
        raw = open(png, "rb").read()
        size = struct.unpack(">II", raw[16:24])
    items = parse_md(os.path.join(HERE, "SPECS.md"))
    doc = layout(items, size)
    out = os.path.join(HERE, "RocketBoy_Specs.pdf")
    n = write_pdf(doc, out, png)
    print("wrote", out, n, "bytes,", len(doc.pages), "pages")
    if "--debug-png" in sys.argv:                                  # quick visual check of the layout (bitmap font)
        sys.path.insert(0, os.path.join(ROOT, "tools"))
        from pngcanvas import Canvas
        for pi, ops in enumerate(doc.pages):
            S = 1.3
            cv = Canvas(int(PW * S), int(PH * S), (255, 255, 255))
            for op in ops:
                if op[0] == "rect":
                    _, x, y, w, h, fill, stroke, lw = op
                    X0, Y0, X1, Y1 = x * S, (PH - y - h) * S, (x + w) * S, (PH - y) * S
                    if fill:
                        cv.rect(X0, Y0, X1, Y1, tuple(int(c * 255) for c in fill))
                    if stroke:
                        sc = tuple(int(c * 255) for c in stroke)
                        for a, b, c_, d_ in ((X0, Y0, X1, Y0), (X0, Y1, X1, Y1), (X0, Y0, X0, Y1), (X1, Y0, X1, Y1)):
                            cv.line(a, b, c_, d_, sc, 1)
                elif op[0] == "text":
                    _, x, y, t, size, bold, color = op
                    cv.text(int(x * S), int((PH - y - size * 0.8) * S), t, tuple(int(c * 255) for c in color), 1)
                elif op[0] == "img":
                    _, x, y, w, h = op
                    cv.rect(x * S, (PH - y - h) * S, (x + w) * S, (PH - y) * S, (200, 215, 235))
            cv.save(os.path.join(HERE, "_page%d.png" % (pi + 1)))
