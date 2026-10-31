"""Dependency-free line plots (PNG) built on tools/pngcanvas.py."""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
from pngcanvas import Canvas

COLORS = [(31, 119, 180), (214, 39, 40), (44, 160, 44), (255, 127, 14), (148, 103, 189), (140, 86, 75), (227, 119, 194), (23, 190, 207)]


def nice_ticks(lo, hi, n=5):
    if hi - lo < 1e-12:
        hi = lo + 1.0
    raw = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(raw))
    for m in (1, 2, 2.5, 5, 10):
        if raw <= m * mag:
            step = m * mag
            break
    t0 = math.floor(lo / step) * step
    ticks = []
    t = t0
    while t <= hi + step * 0.5:
        ticks.append(round(t, 10))
        t += step
    return ticks


def fmt(v):
    if abs(v) >= 100 or v == int(v):
        return "%d" % round(v)
    if abs(v) >= 10:
        return "%.1f" % v
    return ("%.2f" % v).rstrip("0").rstrip(".")


def panel(cv, x0, y0, w, h, series, title, ylabel, xlabel=None, xlim=None, ylim=None, hlines=()):
    """series: list of (label, xs, ys)."""
    ml, mr, mt, mb = 62, 14, 22, 30
    px0, py0, px1, py1 = x0 + ml, y0 + mt, x0 + w - mr, y0 + h - mb
    allx = [x for _, xs, _ in series for x in xs]
    ally = [y for _, _, ys in series for y in ys] + [v for v, *_ in hlines]
    xl = xlim or (min(allx), max(allx))
    yl = ylim or (min(ally), max(ally))
    if yl[1] - yl[0] < 1e-9:
        yl = (yl[0] - 1, yl[1] + 1)
    if not ylim:
        pad = 0.06 * (yl[1] - yl[0])
        yl = (yl[0] - pad if yl[0] < 0 else max(0, yl[0] - pad) if yl[0] > 0 else 0, yl[1] + pad)
    xt, yt = nice_ticks(*xl), nice_ticks(*yl)
    sx = lambda x: px0 + (x - xl[0]) / (xl[1] - xl[0]) * (px1 - px0)
    sy = lambda y: py1 - (y - yl[0]) / (yl[1] - yl[0]) * (py1 - py0)
    cv.rect(px0, py0, px1, py1, (250, 250, 250))
    for t in yt:
        if yl[0] <= t <= yl[1]:
            cv.line(px0, sy(t), px1, sy(t), (225, 225, 225), 1)
            cv.text(x0 + 4, sy(t) - 3, fmt(t), (60, 60, 60), 1)
    for t in xt:
        if xl[0] <= t <= xl[1]:
            cv.line(sx(t), py0, sx(t), py1, (235, 235, 235), 1)
            cv.text(sx(t) - 6, py1 + 5, fmt(t), (60, 60, 60), 1)
    for v, col, lab in hlines:
        if yl[0] <= v <= yl[1]:
            cv.line(px0, sy(v), px1, sy(v), col, 1.5)
            cv.text(px1 - 6 * len(lab) - 2, sy(v) - 9, lab, col, 1)
    for k, (label, xs, ys) in enumerate(series):
        col = COLORS[k % len(COLORS)]
        pts = [(sx(x), sy(y)) for x, y in zip(xs, ys)]
        # decimate to ~2 points per pixel
        step = max(1, len(pts) // int(2 * (px1 - px0)))
        pts = pts[::step]
        for a, b in zip(pts, pts[1:]):
            cv.line(a[0], a[1], b[0], b[1], col, 1.6)
        cv.line(px0 + 8 + 130 * k, py0 + 9, px0 + 26 + 130 * k, py0 + 9, col, 2)
        cv.text(px0 + 30 + 130 * k, py0 + 6, label, (30, 30, 30), 1)
    cv.line(px0, py0, px0, py1, (0, 0, 0), 1)
    cv.line(px0, py1, px1, py1, (0, 0, 0), 1)
    cv.text(x0 + 4, y0 + 4, title, (0, 0, 0), 1)
    cv.text(x0 + 4, y0 + 13, ylabel, (90, 90, 90), 1)
    if xlabel:
        cv.text((px0 + px1) // 2 - 20, y0 + h - 10, xlabel, (90, 90, 90), 1)


def stacked(path, panels, w=960, ph=230, title=None):
    h = ph * len(panels) + (20 if title else 0)
    cv = Canvas(w, h, (255, 255, 255))
    top = 0
    if title:
        cv.text(8, 6, title, (0, 0, 0), 2)
        top = 20
    for k, p in enumerate(panels):
        panel(cv, 0, top + k * ph, w, ph, **p)
    cv.save(path)
