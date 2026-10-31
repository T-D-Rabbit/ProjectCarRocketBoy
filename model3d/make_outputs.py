#!/usr/bin/env python3
"""Build every 3D deliverable:  python3 model3d/make_outputs.py   (run simulation/run_all.py first)

  out/rocketboy_assembly.stl        whole robot, wheels at phi = 0 (mm, binary STL)
  out/rocketboy_body.stl, out/rocketboy_wheel_right.stl, out/rocketboy_wheel_left.stl   separate bodies
  out/rocketboy.obj + .mtl          coloured OBJ with 3 objects (body / wheel_right / wheel_left)
  out/preview_*.png                 still renders
  out/rocketboy_route.gif           animation of the hard-coded route
"""
import os, sys, json, math, time
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import build_model as BM
from mesh import Mesh, write_obj
from render import Camera, Raster, indices_to_png, write_gif

OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
groups = BM.build_all()

# ------------------------------------------------------------------ CAD files
asm = BM.assembled(groups)
asm.write_stl(os.path.join(OUT, "rocketboy_assembly.stl"), "RocketBoy assembly mm")
for k, v in groups.items():
    v.write_stl(os.path.join(OUT, "rocketboy_%s.stl" % k), k)
write_obj(groups, BM.MATERIALS, os.path.join(OUT, "rocketboy.obj"))
lo, hi = asm.bbox()
print("assembly: %d triangles, bbox %s .. %s mm" % (len(asm.tris), [round(v) for v in lo], [round(v) for v in hi]))

# ------------------------------------------------------------------ stills
BG = (240, 244, 248)


def still(name, eye, target, fov=34, size=(1000, 640), floor=True):
    W, H = size
    R = Raster(W, H)
    R.clear(0)
    tris = (floor_tris(3000) if floor else []) + asm.tris
    R.draw(tris, Camera(eye, target, fov))
    indices_to_png(os.path.join(OUT, name), R.idx, W, H, R.palette(BM.MATERIALS, BG))


def quad_flat(x0, y0, x1, y1, z, mat):
    m = Mesh()
    m.quad((x0, y0, z), (x1, y0, z), (x1, y1, z), (x0, y1, z), mat)
    return m.tris


def floor_tris(half, step=500, z=0.0, line=6.0):
    """Floor as 500 mm tiles + short grid-line segments (so nothing is dropped by the near-plane test)."""
    t = []
    g = -half
    while g < half:
        h = -half
        while h < half:
            t += quad_flat(g, h, g + step, h + step, z - 0.5, BM.MID["floor"])
            t += quad_flat(g - line / 2, h, g + line / 2, h + step, z, BM.MID["grid"])
            t += quad_flat(g, h - line / 2, g + step, h + line / 2, z, BM.MID["grid"])
            h += step
        g += step
    return t


still("preview_iso.png", (620, -820, 480), (0, 0, 45))
still("preview_iso_rear.png", (-640, 800, 470), (0, 0, 45))
still("preview_front.png", (0, -1050, 150), (0, 0, 55), 30)
still("preview_side.png", (1150, 0, 120), (0, 0, 55), 30)
still("preview_top.png", (0, 1, 1250), (0, 0, 0), 34)
still("preview_under.png", (420, -520, -380), (0, 0, 30), 36, floor=False)
print("stills written")

# ------------------------------------------------------------------ animation (GIF)
route = json.load(open(os.path.join(ROOT, "simulation", "results", "route_30hz.json")))
frames_data = route["frames"]
xs = [f[1] * 1000 for f in frames_data]
ys = [f[2] * 1000 for f in frames_data]
cxm, cym = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
span = max(max(xs) - min(xs), max(ys) - min(ys)) + 700


def posed(tris, th, x, y):
    a = th - math.pi / 2
    ca, sa = math.cos(a), math.sin(a)
    tx, ty = x * 1000, y * 1000
    f = lambda p: (p[0] * ca - p[1] * sa + tx, p[0] * sa + p[1] * ca + ty, p[2])
    return [(f(a_), f(b_), f(c_), m) for a_, b_, c_, m in tris]


def trail_tris(upto, width=9.0):
    t = []
    for i in range(1, upto + 1, 2):
        a, b = frames_data[i - 1], frames_data[min(i + 1, upto)]
        x0, y0, x1, y1 = a[1] * 1000, a[2] * 1000, b[1] * 1000, b[2] * 1000
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1.0:
            continue
        nx, ny = -(y1 - y0) / L * width / 2, (x1 - x0) / L * width / 2
        m = Mesh()
        m.quad((x0 - nx, y0 - ny, 0.6), (x1 - nx, y1 - ny, 0.6), (x1 + nx, y1 + ny, 0.6), (x0 + nx, y0 + ny, 0.6), BM.MID["trail"])
        t += m.tris
    return t


W, H = 720, 470
cam = Camera((cxm + span * 0.30, cym - span * 0.80, span * 1.25), (cxm, cym, 0), 36)
floor = floor_tris(3500, 500)
gif_frames = []
t0 = time.time()
STEP = 5                      # every 5th 30 Hz sample -> 6 fps at 2x playback = real-time x1.67 ; keep file small
for i in range(0, len(frames_data), STEP):
    f = frames_data[i]
    m = BM.assembled(groups, f[4], f[5])
    R = Raster(W, H)
    R.clear(0)
    R.draw(floor + trail_tris(i) + posed(m.tris, f[3], f[1], f[2]), cam)
    gif_frames.append(R.idx)
pal = Raster(W, H).palette(BM.MATERIALS, BG)
dt_real = STEP / route["rec_hz"]
write_gif(os.path.join(OUT, "rocketboy_route.gif"), gif_frames, W, H, pal, delay_cs=max(2, int(round(dt_real * 100 / 1.0))))
print("gif: %d frames in %.0f s, real-time playback" % (len(gif_frames), time.time() - t0))

