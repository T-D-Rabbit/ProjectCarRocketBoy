"""Parametric 3D model of the RocketBoy robot (units mm; x = right/wheel axis, y = forward, z = up, z = 0 is the floor).

Dimensions come from the repository inputs:
  * Chassis file.step : 300 mm disc, 3 mm thick, 4 PCB holes (+-75, +-100), 12 clamp holes, 2 caster slots
  * L Clamp.pdf       : 1.5 mm plate, 40 mm wide, flange 22 mm with 3 x 2 holes, bore + 12 holes PCD 30.5, axis 26.7 mm
  * Johnson Motor.pdf : gearbox D37 x 25, can D29 x 37.8, rear boss 6.5, front boss 6.3, shaft D6 x 30
  * RocketBoy.kicad_pcb : board outline, module / ESP32 / connector positions (read from tools/build_pcb.py)
Assumed: 110 mm wheels, 40 mm standoffs, battery pack, casters, buck module (see simulation/params.py).
"""
import os, sys, math
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "tools"))
sys.path.insert(0, os.path.join(ROOT, "simulation"))
from mesh import Mesh, circle_pts, rect_pts, rrect_pts
import params as SP

# ------------------------------------------------------------------ materials  (id: (name, rgb))
MAT_LIST = [
    ("chassis", (150, 185, 205)), ("steel", (176, 180, 186)), ("clamp", (122, 130, 140)), ("motor_can", (190, 192, 196)),
    ("gearbox", (201, 162, 75)), ("tire", (28, 28, 30)), ("rim", (235, 120, 40)), ("rim_dark", (70, 72, 78)),
    ("pcb", (20, 110, 62)), ("module_pcb", (200, 40, 45)), ("black", (35, 35, 38)), ("esp_pcb", (30, 30, 36)),
    ("usb", (200, 200, 205)), ("terminal", (40, 90, 200)), ("cap", (35, 60, 140)), ("switch", (235, 235, 235)),
    ("gold", (230, 190, 70)), ("standoff", (205, 160, 70)), ("caster", (150, 152, 158)), ("cell", (40, 120, 200)),
    ("holder", (60, 60, 66)), ("buck", (40, 100, 190)), ("indicator", (30, 150, 80)), ("marker", (220, 30, 30)),
    ("floor", (232, 234, 238)), ("grid", (205, 208, 214)), ("trail", (255, 140, 0)), ("sky", (255, 255, 255)),
]
MID = {n: i for i, (n, c) in enumerate(MAT_LIST)}
MATERIALS = {i: (n, c) for i, (n, c) in enumerate(MAT_LIST)}

# ------------------------------------------------------------------ key dimensions
R_W = SP.MECH["WHEEL_DIAMETER"] * 500.0           # wheel radius mm
ZT = R_W - SP.MECH["AXLE_ABOVE_TOP"] * 1000.0     # chassis top face above floor
T_CH = SP.MECH["CHASSIS_THICKNESS"] * 1000.0
ZU = ZT - T_CH                                    # chassis underside
STANDOFF = 40.0
Z_PCB = ZT + STANDOFF
Z_TOP = Z_PCB + 1.6
PLATE_IN, PLATE_OUT = 146.4, 147.9
WHEEL_X0, WHEEL_W = 153.0, 25.0


def build_chassis():
    m = Mesh()
    outer = circle_pts(0, 0, 150, 120)
    holes = [circle_pts(x, y, 1.6, 14) for x in (-75, 75) for y in (-100, 100)]
    for sx in (-1, 1):
        for x in (130.8, 136.8, 142.8):
            for y in (-14.9, 14.9):
                holes.append(circle_pts(sx * x, y, 1.6, 14))
    holes.append(rect_pts(-25, 123.4, 25, 126.6))
    holes.append(rect_pts(-25, -126.6, 25, -123.4))
    m.extrude(outer, holes, ZU, ZT, MID["chassis"])
    # front marker (red wedge)
    m.extrude([(-12, 131), (12, 131), (0, 146)], [], ZT, ZT + 0.8, MID["marker"])
    return m


def build_clamp_and_motor():
    """Right-hand side (x > 0); mirrored for the left."""
    m = Mesh()
    c = MID["clamp"]
    # flange (22 x 40 x 1.5) with 6 holes, lying on the chassis top face
    fh = [circle_pts(x, y, 1.65, 12) for x in (130.8, 136.8, 142.8) for y in (-14.9, 14.9)]
    m.extrude(rect_pts(126.0, -20, PLATE_OUT, 20), fh, ZT, ZT + 1.5, c)
    # vertical plate (YZ plane): 40 wide, 40 tall, rounded top corners, D22 bore, 12 holes on PCD 30.5
    za = ZT + SP.MECH["AXLE_ABOVE_TOP"] * 1000.0          # axis height = wheel radius
    plate = rrect_pts(-20, ZT, 20, ZT + 40, 8.0, 8, top_only=True)
    ph = [circle_pts(0, za, 11.0, 28)] + [circle_pts(15.25 * math.cos(math.radians(30 * k + 15)), za + 15.25 * math.sin(math.radians(30 * k + 15)), 1.65, 10) for k in range(12)]
    m.extrude(plate, ph, PLATE_IN, PLATE_OUT, c, plane="yz")
    # motor (gearbox on the inside of the plate, shaft through the bore)
    m.cyl("x", ((PLATE_IN + PLATE_IN - 25) / 2, 0, za), 18.5, 25.0, MID["gearbox"], 40)
    m.cyl("x", (PLATE_IN - 25 - 37.8 / 2, 0, za), 14.5, 37.8, MID["motor_can"], 36)
    m.cyl("x", (PLATE_IN - 25 - 37.8 - 3.25, 0, za), 6.0, 6.5, MID["steel"], 20)
    m.cyl("x", (PLATE_IN + 6.3 / 2, 0, za), 10.9, 6.3, MID["gearbox"], 28)               # pilot boss through the bore
    m.cyl("x", (PLATE_IN + 6.3 + 15.0, 0, za), 3.0, 30.0, MID["steel"], 16)               # D6 output shaft
    # motor terminals (two lugs on the can end)
    return m


def build_wheel():
    """Right wheel, built with phi = 0 about the axle (x axis through y = 0, z = R_W)."""
    m = Mesh()
    x0, x1 = WHEEL_X0, WHEEL_X0 + WHEEL_W
    za = R_W
    ring_o = circle_pts(0, za, R_W, 56)
    ring_i = circle_pts(0, za, R_W * 0.76, 56)
    m.extrude(ring_o, [ring_i], x0, x1, MID["tire"], plane="yz")
    for (a, b) in ((x0, x0 + 3.0), (x1 - 3.0, x1)):
        holes = [circle_pts(27 * math.cos(math.radians(72 * k)), za + 27 * math.sin(math.radians(72 * k)), 9.0, 18) for k in range(5)]
        holes.append(circle_pts(0, za, 8.5, 16))
        m.extrude(circle_pts(0, za, R_W * 0.76, 56), holes, a, b, MID["rim"], plane="yz")
    m.cyl("x", ((x0 + x1) / 2, 0, za), 8.5, WHEEL_W, MID["rim_dark"], 24)
    m.cyl("x", (x1 + 0.5, 0, za), 4.0, 1.0, MID["steel"], 12)
    return m


def build_caster(y):
    m = Mesh()
    m.box(0, y, ZU - 1.0, 34, 34, 2.0, MID["caster"])
    h0, h1 = 9.0 + 4.0, ZU - 2.0
    m.cyl("z", (0, y, (h0 + h1) / 2), 11.0, h1 - h0, MID["caster"], 24)
    m.sphere((0, y, 9.0), 9.0, MID["steel"], 18)
    return m


def build_underside():
    m = Mesh()
    # 3 x 18650 (3S1P Molicel) lying along y, in a holder
    zc = 13.8
    for k in (-1, 0, 1):
        m.cyl("y", (k * 19.0, -5.0, zc), 9.3, 65.0, MID["cell"], 24)
        m.cyl("y", (k * 19.0, -5.0 + 33.2, zc), 3.5, 1.4, MID["gold"], 12)
    m.box(0, -5.0, 4.6, 59.0, 69.0, 2.4, MID["holder"])
    m.box(0, -5.0 - 33.5, zc, 59.0, 2.0, 21.0, MID["holder"])
    m.box(0, -5.0 + 33.5, zc, 59.0, 2.0, 21.0, MID["holder"])
    m.box(0, -5.0, ZU - 1.2, 59.0, 69.0, 2.4, MID["holder"])
    # buck module (12 V -> 5 V) and LiPo voltage indicator
    m.box(-12, 58, ZU - 6.5, 43.0, 21.0, 1.6, MID["buck"])
    m.cyl("z", (-4, 58, ZU - 11.5), 7.0, 9.0, MID["black"], 18)
    m.box(-20, 58, ZU - 11.0, 10.0, 8.0, 10.0, MID["cap"])
    m.box(0, 96, ZU - 4.5, 36.0, 10.0, 1.6, MID["indicator"])
    m.cyl("z", (10, 96, ZU - 8.5), 6.0, 8.0, MID["black"], 18)
    # standoffs for the two small boards
    for (x, y) in ((-28, 52), (4, 64), (-14, 96), (14, 96)):
        m.cyl("z", (x, y, ZU - 3.0), 1.8, 6.0, MID["standoff"], 8)
    return m


def build_pcb_stack():
    """Standoffs + PCB + all populated parts, positions taken from tools/build_pcb.py."""
    import build_pcb as B
    m = Mesh()
    W = lambda px, py: (px, -py)                       # PCB frame (y down) -> world (y forward)
    # standoffs, screws
    for (hx, hy) in B.P.HOLES:
        wx, wy = W(hx, hy)
        m.cyl("z", (wx, wy, ZT + STANDOFF / 2), 3.0, STANDOFF, MID["standoff"], 6)
        m.cyl("z", (wx, wy, ZT + STANDOFF + 1.6 + 1.2), 2.8, 2.4, MID["steel"], 16)
        m.cyl("z", (wx, wy, ZU - 1.2), 2.8, 2.4, MID["steel"], 16)
    # board
    ox0, oy0, ox1, oy1, r = B.board.outline
    outline = rrect_pts(ox0, oy0, ox1, oy1, r, 8)
    holes = [circle_pts(*W(hx, hy), 1.6, 14) for (hx, hy) in B.P.HOLES]
    m.extrude(outline, holes, Z_PCB, Z_PCB + 1.6, MID["pcb"])
    z0 = Z_PCB + 1.6

    def female(cx, cy, sx, sy, h=8.5):
        m.box(cx, cy, z0 + h / 2, sx, sy, h, MID["black"])

    # 9 TB6612FNG modules on female sockets
    for ref, (mx, my, c, rr) in B.module_pos.items():
        for px in (mx + 2.54, mx + 16.51):
            female(*W(px, my + 11.43), 2.54, 20.32)
        cx, cy = W(mx + 9.525, my + 11.43)
        m.box(cx, cy, z0 + 8.5 + 0.8, 16.51, 20.32, 1.6, MID["module_pcb"])
        m.box(cx, cy, z0 + 8.5 + 1.6 + 0.8, 7.0, 10.0, 1.6, MID["black"])
        m.box(cx + 4.5, cy - 7.5, z0 + 8.5 + 1.6 + 1.5, 4.0, 3.0, 3.0, MID["cap"])
    # ESP32 DevKit (rotated 180 deg: USB at the rear edge)
    ex, ey = B.ex, B.ey
    for px in (ex - 20.32, ex + 2.54):
        female(*W(px, ey - 25.4), 2.54, 48.26)
    cx, cy = W(ex - 8.89, ey - 23.6)
    m.box(cx, cy, z0 + 8.5 + 0.8, 27.94, 54.4, 1.6, MID["esp_pcb"])
    cx2, cy2 = W(ex - 8.89, ey - 40.0)
    m.box(cx2, cy2, z0 + 8.5 + 1.6 + 1.6, 18.0, 25.5, 3.2, MID["steel"])
    m.box(*W(ex - 8.89, ey + 0.5), z0 + 8.5 + 1.6 + 1.5, 8.0, 5.5, 3.0, MID["usb"]) if False else None
    ux, uy = W(ex - 8.89, ey + 0.5)
    m.box(ux, uy, z0 + 8.5 + 1.6 + 1.5, 8.0, 5.5, 3.0, MID["usb"])
    # screw terminals (battery, left motor, right motor)
    for ref, (tx, ty) in B.TERM.items():
        cx, cy = W(tx, ty + 2.54)
        m.box(cx, cy, z0 + 5.0, 8.0, 10.2, 10.0, MID["terminal"])
        m.box(cx, cy, z0 + 10.2, 5.0, 8.0, 0.4, MID["black"])
    # switches, caps, headers
    for ref, (x, y, rot) in B.PLACE.items():
        wx, wy = W(x, y)
        if ref.startswith("SW"):
            m.box(wx, wy, z0 + 1.8, 9.0, 3.6, 3.6, MID["switch"])
            m.box(wx + 1.0, wy, z0 + 3.6 + 2.2, 3.6, 1.4, 4.4, MID["black"])
        elif ref.startswith("C"):
            m.cyl("z", (wx, wy, z0 + 8.0), 5.0, 16.0, MID["cap"], 28)
            m.cyl("z", (wx, wy, z0 + 16.05), 4.2, 0.2, MID["steel"], 20)
        elif ref in ("J1", "J2", "J3", "J4", "J5"):
            n = {"J1": 2, "J2": 2, "J3": 10, "J4": 16, "J5": 8}[ref]
            hy = y + (n - 1) * 1.27
            cx, cy = W(x, hy)
            m.box(cx, cy, z0 + 1.25, 2.54, n * 2.54, 2.5, MID["black"])
            for k in range(n):
                px_, py_ = W(x, y + k * 2.54)
                m.box(px_, py_, z0 + 2.5 + 4.0, 0.64, 0.64, 11.5 if ref in ("J3", "J4", "J5") else 8.0, MID["gold"])
    return m


def build_all():
    body = Mesh()
    body.extend(build_chassis())
    cm = build_clamp_and_motor()
    body.extend(cm)
    body.extend(cm.mirrored_x())
    body.extend(build_caster(125.0))
    body.extend(build_caster(-125.0))
    body.extend(build_underside())
    body.extend(build_pcb_stack())
    wheel_r = build_wheel()
    wheel_l = wheel_r.mirrored_x()
    return {"body": body, "wheel_right": wheel_r, "wheel_left": wheel_l}


def assembled(groups, phi_l=0.0, phi_r=0.0):
    """Static mesh (all groups) with the wheels rotated by phi (rad, positive = rolling forward)."""
    m = Mesh()
    m.extend(groups["body"])
    m.extend(groups["wheel_right"].rotated_x(-phi_r, 0.0, R_W))
    m.extend(groups["wheel_left"].rotated_x(-phi_l, 0.0, R_W))
    return m


if __name__ == "__main__":
    g = build_all()
    for k, v in g.items():
        lo, hi = v.bbox()
        print(k, len(v.tris), "tris  bbox", [round(a, 1) for a in lo], [round(a, 1) for a in hi])
    print("chassis top %.1f underside %.1f  PCB top %.1f  axle %.1f" % (ZT, ZU, Z_TOP, R_W))
