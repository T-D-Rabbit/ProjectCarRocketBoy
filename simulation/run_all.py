#!/usr/bin/env python3
"""Run the full RocketBoy simulation suite and write results to simulation/results/.

    python3 simulation/run_all.py

Scenarios
  S1  full-duty launch, straight line            (current inrush, battery sag, module sharing)
  S2  blocked-wheel stall for 1 / 2 / 3 enabled groups   (is the driver bank big enough?)
  S3  hill climb sweep
  S4  spin on the spot
  S5  line-following lap with an 8-channel IR array (PID), 1 group vs 3 groups enabled
  S6  PCB copper current check (trace widths read from RocketBoy.kicad_pcb)
"""
import os, sys, math, csv, re, json, random
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tools"))
import params as P
import rocketbot as rb
from plotting import stacked, panel
from pngcanvas import Canvas
from sexpr import parse, find, first, val

RES = os.path.join(HERE, "results")
os.makedirs(RES, exist_ok=True)
lines = []          # markdown report


def md(s=""):
    lines.append(s)
    print(s)


def write_csv(name, rows):
    with open(os.path.join(RES, name), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow({k: ("%.6g" % v if isinstance(v, float) else v) for k, v in r.items()})


G3 = (True, True, True)
G1 = (True, False, False)
G2 = (True, True, False)

mo = rb.Motor()
ms = mo.summary()
md("# RocketBoy simulation results")
md()
md("## Model summary")
md("| item | value | source |")
md("|---|---|---|")
md("| total mass | %.2f kg | assumed part list (params.py) |" % P.total_mass())
md("| wheel | %.0f mm dia, track width %.0f mm | assumed wheel, STEP/PDF geometry |" % (P.MECH["WHEEL_DIAMETER"] * 1000, P.track_width() * 1000))
md("| ground clearance under chassis | %.1f mm (wheel radius - 26.7 mm L-clamp axis height) | PDF |" % (P.ground_clearance() * 1000))
md("| motor no-load speed / rated point | 300 rpm / 220 rpm @ 6 kgf.cm, I0 = 0.5 A | Johnson Motor.pdf |")
md("| motor winding resistance (fitted) | %.2f ohm | derived from rated point |" % ms["R_ohm"])
md("| motor Ke = Kt | %.4f V s/rad | derived |" % ms["ke_Vs_per_rad"])
md("| **stall current / torque (derived)** | **%.2f A / %.1f kgf.cm** | PDF stall rows are blank -> derived |" % (ms["I_stall_A"], ms["T_stall_kgfcm"]))
md("| current at rated load | %.2f A (PDF upper bound 4.5 A) | derived |" % ms["I_rated_A"])
md("| battery | 3S1P, 2.8 Ah, %.0f mohm pack incl. wiring | Molicel P28A class |" % ((rb.Battery().R) * 1000))
md()

# ------------------------------------------------------------------ S1 launch
md("## S1 - full-duty launch on flat ground")
md("| groups on | 0-1 m/s [s] | top speed [m/s] | inrush peak per motor [A] | steady current per motor [A] | min battery V | worst module peak [A] (limit 1.2 A cont / 3.2 A pulse) |")
md("|---|---|---|---|---|---|---|")
s1 = {}
for name, g in (("1 (3 modules/motor)", G1), ("2", G2), ("3 (9 modules)", G3)):
    r = rb.Robot(groups_on=g)
    rb.run(r, lambda t, rob: (1.0, 1.0), 3.0)
    t1 = next(row["t"] for row in r.log if row["v"] >= 1.0)
    peak = max(row["il"] for row in r.log)
    worst = max(max(r.bank.stat["A"]), max(r.bank.stat["B"]))
    md("| %s | %.2f | %.2f | %.2f | %.2f | %.2f | %.2f |" % (name, t1, r.log[-1]["v"], peak, r.log[-1]["il"], min(row["vbat"] for row in r.log), worst))
    s1[name] = r
r = s1["1 (3 modules/motor)"]
r3 = s1["3 (9 modules)"]
stacked(os.path.join(RES, "S1_launch.png"), [
    dict(series=[("speed m/s", [x["t"] for x in r.log], [x["v"] for x in r.log])], title="S1 full-duty launch, 1 group enabled", ylabel="speed [m/s]"),
    dict(series=[("1 group", [x["t"] for x in r.log], [x["il"] for x in r.log]), ("3 groups", [x["t"] for x in r3.log], [x["il"] for x in r3.log])],
         title="motor current (one motor)", ylabel="A", hlines=[(3.6, (200, 0, 0), "1 grp rated 3.6A")]),
    dict(series=[("1 group", [x["t"] for x in r.log], [x["vbat"] for x in r.log]), ("3 groups", [x["t"] for x in r3.log], [x["vbat"] for x in r3.log])],
         title="battery terminal voltage", ylabel="V", xlabel="time [s]"),
], title="RocketBoy S1: launch")
write_csv("S1_launch_1group.csv", r.log)
md()
md("Per-module current peaks during the launch (channel A / left motor), 1 group enabled: %s A" % ", ".join("%.2f" % x for x in r.bank.stat["A"][:3]))
md("A hard 100 %% duty step makes the motor draw its inrush (%.1f A) before back-EMF builds up -> **ramp the PWM (>= 100 ms) in firmware**; the 3 modules of one group then stay inside the 1.2 A continuous rating." % max(row["il"] for row in r.log))
md()

# ------------------------------------------------------------------ S2 stall
md("## S2 - blocked wheels (motors stalled), full duty")
md("| groups on | modules per motor | stall current per motor [A] | rated (cont.) capacity [A] | pulse capacity [A] | verdict | battery V | battery current [A] |")
md("|---|---|---|---|---|---|---|---|")
for name, g, n in (("1", G1, 3), ("2", G2, 6), ("3", G3, 9)):
    r = rb.Robot(groups_on=g, blocked=True)
    rb.run(r, lambda t, rob: (1.0, 1.0), 0.3)
    ist = r.log[-1]["il"]
    cont, pk = n * P.DRIVER["I_CONT"], n * P.DRIVER["I_PEAK"]
    worst = max(max(r.bank.stat["A"]), max(r.bank.stat["B"]))
    verdict = "OK" if worst <= P.DRIVER["I_CONT"] else ("pulse only (<=3.2 A/module)" if worst <= P.DRIVER["I_PEAK"] else "OVERLOAD")
    md("| %s | %d | %.2f | %.1f | %.1f | %s (worst module %.2f A) | %.2f | %.1f |" % (name, n, ist, cont, pk, verdict, worst, r.log[-1]["vbat"], r.log[-1]["ibat"]))
md()
md("Stall is the only case that needs more than one group; with 2-3 groups enabled a stalled motor is inside the pulse rating. "
   "The TB6612FNG has thermal shutdown but **no current limit**, so stall detection in firmware is recommended.")
md()

# ------------------------------------------------------------------ S3 hill
md("## S3 - hill climb (duty 0.7 for 6 s, 1 group)")
md("| slope [deg] | speed [m/s] | motor current [A] | wheel slip |")
md("|---|---|---|---|")
hill = []
for sl in (0, 5, 10, 15, 20, 25, 30, 35):
    r = rb.Robot(groups_on=G1, slope_deg=sl)
    rb.run(r, lambda t, rob: (0.7, 0.7), 6.0)
    tail = r.log[-100:]
    v = sum(x["v"] for x in tail) / len(tail)
    i = sum(x["il"] for x in tail) / len(tail)
    md("| %d | %.2f | %.2f | %s |" % (sl, v, i, "yes" if r.slip_time > 0.5 else "no"))
    hill.append((sl, v, i))
md()
md("Tyre limit: the drive wheels (%.0f %% of weight, mu = %.2f) hold up to about %.0f deg before slipping." %
   (P.MECH["DRIVE_LOAD_FRACTION"] * 100, P.MECH["MU_TYRE"], math.degrees(math.atan(P.MECH["MU_TYRE"] * P.MECH["DRIVE_LOAD_FRACTION"]))))
md()

# ------------------------------------------------------------------ S4 spin
r = rb.Robot(groups_on=G1)
rb.run(r, lambda t, rob: (-0.5, 0.5), 3.0)
md("## S4 - spin on the spot (duty -0.5 / +0.5)")
md("Yaw rate %.0f deg/s, current %.2f A per motor, battery %.2f V." % (math.degrees(r.log[-1]["wz"]), abs(r.log[-1]["il"]), r.log[-1]["vbat"]))
md()

# ------------------------------------------------------------------ S5 line follower
class Track:
    """Closed stadium track: two 1.6 m straights (the lower one has a gentle bulge / chicane) joined by R = 0.6 m turns."""

    def __init__(self, L=1.6, R=0.6, A=0.18, spacing=0.0035):
        pts = []
        n = int(L / spacing)
        for k in range(n):                                   # bottom straight, left -> right
            u = k / n
            pts.append((-L / 2 + u * L, -R + A * (1 - math.cos(2 * math.pi * u)) / 2))
        m = int(math.pi * R / spacing)
        for k in range(m):                                   # right half circle (counter-clockwise)
            a = -math.pi / 2 + math.pi * k / m
            pts.append((L / 2 + R * math.cos(a), R * math.sin(a)))
        for k in range(n):                                   # top straight, right -> left
            u = k / n
            pts.append((L / 2 - u * L, R))
        for k in range(m):                                   # left half circle
            a = math.pi / 2 + math.pi * k / m
            pts.append((-L / 2 + R * math.cos(a), R * math.sin(a)))
        pts.append(pts[0])
        self.pts = pts
        self.s = [0.0]
        for a, b in zip(pts, pts[1:]):
            self.s.append(self.s[-1] + math.hypot(b[0] - a[0], b[1] - a[1]))
        self.length = self.s[-1]
        rmin = 1e9
        for k in range(2, len(pts) - 2, 3):
            a, b, c = pts[k - 2], pts[k], pts[k + 2]
            ab = math.hypot(b[0] - a[0], b[1] - a[1]); bc = math.hypot(c[0] - b[0], c[1] - b[1]); ca = math.hypot(a[0] - c[0], a[1] - c[1])
            area2 = abs((b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0]))
            if area2 > 1e-12:
                rmin = min(rmin, ab * bc * ca / (2 * area2))
        self.rmin = rmin

    def dist(self, p, hint):
        n = len(self.pts) - 1
        best, bi = 1e9, hint
        for d in range(-30, 31):
            i = (hint + d) % n
            a, b = self.pts[i], self.pts[i + 1]
            dx, dy = b[0] - a[0], b[1] - a[1]
            L2 = dx * dx + dy * dy
            t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / L2))
            dd = math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))
            if dd < best:
                best, bi = dd, i
        return best, bi


def line_follow(groups, base=0.55, kp=0.085, kd=0.010, slew=8.0, t_max=60.0, tag=""):
    trk = Track()
    sen = P.SENSOR
    r = rb.Robot(groups_on=groups)
    a, b = trk.pts[0], trk.pts[1]
    rnd = random.Random(5)
    # start 30 mm beside the line with a 6 degree heading error (the controller must find and follow the line)
    th0 = math.atan2(b[1] - a[1], b[0] - a[0])
    r.x, r.y, r.th = a[0] - 0.030 * math.sin(th0), a[1] + 0.030 * math.cos(th0), th0 + math.radians(6)
    hint = [0] * sen["N"]
    chint = 0
    prev_e = 0.0
    corr = 0.0
    ul = ur = 0.0
    dt, dtc = P.SIM["DT"], P.SIM["DT_CTRL"]
    sub = int(round(dtc / dt))
    progress = 0
    laps_done = False
    max_err = 0.0
    err_log = []
    lost_t = 0.0
    last_idx = 0
    unwrapped = 0
    n = len(trk.pts) - 1
    while r.t < t_max and not laps_done:
        # --- sensors
        vals = []
        for i in range(sen["N"]):
            yl = ((sen["N"] - 1) / 2 - i) * sen["PITCH"]            # +left, index 0 = leftmost
            wx = r.x + math.cos(r.th) * sen["AHEAD"] - math.sin(r.th) * yl
            wy = r.y + math.sin(r.th) * sen["AHEAD"] + math.cos(r.th) * yl
            d, hint[i] = trk.dist((wx, wy), hint[i])
            ex = max(0.0, d - sen["LINE_WIDTH"] / 2)
            vals.append(max(0.0, math.exp(-(ex / sen["SPOT"]) ** 2) * (1 + 0.03 * rnd.gauss(0, 1))))   # 3 % sensor noise
        tot = sum(vals)
        if tot > 0.05:
            pos = sum(v * (((sen["N"] - 1) / 2 - i)) for i, v in enumerate(vals)) / tot       # in pitches, +left
            de = (pos - prev_e) / dtc
            prev_e = pos
            corr = kp * pos + kd * de
        else:
            lost_t += dtc
        tl = max(-1.0, min(1.0, base - corr))
        tr_ = max(-1.0, min(1.0, base + corr))
        ul += max(-slew * dtc, min(slew * dtc, tl - ul))          # duty slew-rate limit (soft start / soft steering)
        ur += max(-slew * dtc, min(slew * dtc, tr_ - ur))
        for _ in range(sub):
            r.step(ul, ur, dt)
        # --- bookkeeping
        d, chint = trk.dist((r.x, r.y), chint)
        max_err = max(max_err, d)
        err_log.append(d)
        if chint < last_idx - n // 2:
            unwrapped += n
        elif chint > last_idx + n // 2:
            unwrapped -= n
        last_idx = chint
        progress = unwrapped + chint
        if int(r.t / dtc) % 4 == 0:
            r.record(dict(err=d, ul=ul, ur=ur, pos=pos if tot > 0.05 else 0.0))
        if progress >= n - 5 and r.t > 3:
            laps_done = True
    return r, trk, max_err, err_log, lost_t, laps_done


md("## S5 - line following lap (8-channel IR array, PID)")
res5 = {}
for name, g in (("1 group", G1), ("3 groups", G3)):
    r, trk, max_err, err_log, lost_t, done = line_follow(g)
    res5[name] = (r, trk, max_err, err_log, lost_t, done)
tr = res5["1 group"][1]
md("Track: closed loop %.2f m long, minimum radius %.0f mm, 19 mm tape. Sensor array 130 mm ahead of the axle, 9.525 mm pitch." % (tr.length, tr.rmin * 1000))
md()
md("| enabled | finished lap | lap time [s] | avg speed [m/s] | max off-line [mm] | rms off-line [mm] | line lost [s] | peak motor A | mean motor A | min battery V | charge used [mAh] | worst module [A] |")
md("|---|---|---|---|---|---|---|---|---|---|---|---|")
for name, (r, trk, max_err, err_log, lost_t, done) in res5.items():
    rms = math.sqrt(sum(e * e for e in err_log) / len(err_log))
    ib = [x["ibat"] for x in r.log]
    mean_m = sum(abs(x["il"]) + abs(x["ir"]) for x in r.log) / len(r.log) / 2
    used = (P.BATTERY["SOC_START"] - r.batt.soc) * P.BATTERY["CAPACITY_AH"] * 1000
    worst = max(max(r.bank.stat["A"]), max(r.bank.stat["B"]))
    md("| %s | %s | %.1f | %.2f | %.1f | %.1f | %.2f | %.2f | %.2f | %.2f | %.1f | %.2f |" % (
        name, "yes" if done else "NO", r.t, trk.length / r.t, max_err * 1000, rms * 1000, lost_t,
        max(max(x["il"], x["ir"]) for x in r.log), mean_m, min(x["vbat"] for x in r.log), used, worst))
md()
# plots: track + trajectory, speed/current/error
r, trk, max_err, err_log, lost_t, done = res5["1 group"]
W, H, sc = 960, 560, 300.0
cv = Canvas(W, H, (255, 255, 255))
cx, cy = W / 2, H / 2
tp = lambda p: (cx + p[0] * sc * 0.95 * 1.0, cy - p[1] * sc * 0.95)
for a, b in zip(trk.pts, trk.pts[1:]):
    pa, pb = tp(a), tp(b)
    cv.line(pa[0], pa[1], pb[0], pb[1], (30, 30, 30), P.SENSOR["LINE_WIDTH"] * sc * 0.95)
vmax = max(x["v"] for x in r.log) or 1
for a, b in zip(r.log, r.log[1:]):
    pa, pb = tp((a["x"], a["y"])), tp((b["x"], b["y"]))
    f = max(0.0, min(1.0, a["v"] / vmax))
    cv.line(pa[0], pa[1], pb[0], pb[1], (int(255 * (1 - f)), int(180 * f), 255 * 0 + 60), 2)
cv.text(10, 10, "S5 LINE FOLLOWER LAP - TRAJECTORY COLOURED BY SPEED (RED SLOW, GREEN FAST)", (0, 0, 0), 1)
cv.text(10, 24, "BLACK = 19 MM LINE, LAP %.1f S" % r.t, (0, 0, 0), 1)
cv.save(os.path.join(RES, "S5_track.png"))
ts = [x["t"] for x in r.log]
r3_ = res5["3 groups"][0]
stacked(os.path.join(RES, "S5_line_follow.png"), [
    dict(series=[("speed m/s", ts, [x["v"] for x in r.log])], title="S5 line follower, 1 group enabled", ylabel="speed [m/s]"),
    dict(series=[("left motor", ts, [x["il"] for x in r.log]), ("right motor", ts, [x["ir"] for x in r.log])], title="motor currents", ylabel="A",
         hlines=[(3.6, (200, 0, 0), "1 group rated 3.6A")]),
    dict(series=[("off-line mm", ts, [x["err"] * 1000 for x in r.log])], title="distance of axle centre from line", ylabel="mm"),
    dict(series=[("1 group", ts, [x["vbat"] for x in r.log]), ("3 groups", [x["t"] for x in r3_.log], [x["vbat"] for x in r3_.log])],
         title="battery voltage", ylabel="V", xlabel="time [s]"),
], title="RocketBoy S5")
write_csv("S5_line_follow_1group.csv", r.log)

# ------------------------------------------------------------------ S6 PCB copper check
md("## S6 - PCB copper current check (widths read from RocketBoy.kicad_pcb)")
pcb = parse(open(os.path.join(os.path.dirname(HERE), "RocketBoy", "RocketBoy.kicad_pcb")).read())
netname = {}
for n in find(pcb, "net"):
    netname[int(n[1])] = val(n[2])
wmax, wmin_trunk = {}, {}
for sgm in find(pcb, "segment"):
    nid = int(first(sgm, "net")[1])
    w = float(first(sgm, "width")[1])
    wmax[netname[nid]] = max(wmax.get(netname[nid], 0), w)


def ipc2221(width_mm, oz, dT=10.0):
    area = (width_mm / 0.0254) * (1.378 * oz)       # mil^2
    return 0.048 * dT ** 0.44 * area ** 0.725


stall = mo.I_stall
r2 = rb.Robot(groups_on=G3, blocked=True)
rb.run(r2, lambda t, rob: (1.0, 1.0), 0.3)
ibat_stall = r2.log[-1]["ibat"]
checks = [
    ("VBAT main trunk", wmax["VBAT"], ibat_stall, "both motors stalled, 3 groups"),
    ("motor out trunk /LmA", wmax["/LmA"], stall, "one motor stalled"),
    ("motor out trunk /RmA", wmax["/RmA"], stall, "one motor stalled"),
    ("VBAT lane per column (3.0 mm)", 3.0, 3 * 2 * P.DRIVER["I_CONT"], "3 modules x 2 ch x 1.2 A rated"),
    ("motor lane per column (2.0 mm)", 2.0, 3 * P.DRIVER["I_CONT"], "3 modules x 1.2 A rated"),
    ("module stub VBAT (1.5 mm)", 1.5, 2 * P.DRIVER["I_CONT"], "one module, both channels rated"),
    ("module stub motor (1.2 mm)", 1.2, P.DRIVER["I_CONT"], "one module channel rated"),
    ("logic nets (0.3 mm)", 0.3, 0.02, "GPIO current"),
]
md("| path | width [mm] | demand [A] | capacity 1 oz / 2 oz @ +10 C [A] | verdict (2 oz) |")
md("|---|---|---|---|---|")
for nm, w, i, why in checks:
    c1, c2 = ipc2221(w, 1), ipc2221(w, 2)
    md("| %s (%s) | %.1f | %.1f | %.1f / %.1f | %s |" % (nm, why, w, i, c1, c2, "OK" if c2 >= i else "marginal - fault condition only" if c2 >= 0.6 * i else "UNDERSIZED"))
md()
md("Order the board with **2 oz copper**; with 1 oz the trunks are still adequate for normal running (<2 A per motor) but not for stall.")
md()
open(os.path.join(RES, "summary.md"), "w").write("\n".join(lines) + "\n")
print("results written to", RES)
