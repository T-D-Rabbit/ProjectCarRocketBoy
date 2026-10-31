#!/usr/bin/env python3
"""Run the full RocketBoy simulation suite and write results to simulation/results/.

    python3 simulation/run_all.py

Scenarios
  S1  full-duty launch, straight line            (current inrush, battery sag, module sharing)
  S2  blocked-wheel stall for 1 / 2 / 3 enabled groups   (is the driver bank big enough?)
  S3  hill climb sweep
  S4  spin on the spot
  S5  hard-coded demo route (square with 90 degree spins), 1 group vs 3 groups enabled; exports the 30 Hz pose
      log that drives the 3D animation
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
md("| chassis top face / underside above ground | %.1f / %.1f mm (wheel radius - 26.7 mm clamp axis height; clamps on the top face) | PDF |" % (P.chassis_top_height() * 1000, P.ground_clearance() * 1000))
md("| motor no-load speed / rated point | 300 rpm / 220 rpm @ 6 kgf.cm, I0 = 0.5 A | Johnson Motor.pdf |")
md("| motor winding resistance | %.2f ohm (= 12 V / stall current) | derived |" % ms["R_ohm"])
md("| motor Ke = Kt | %.4f V s/rad | derived |" % ms["ke_Vs_per_rad"])
md("| **stall current / torque** | **%.2f A** (given by user) / %.1f kgf.cm (derived) | PDF stall rows are blank |" % (ms["I_stall_A"], ms["T_stall_kgfcm"]))
md("| rated-point check | model gives %.0f rpm at 6 kgf.cm (datasheet 220 +-22 rpm) | consistent |" % ms["rated_speed_rpm"])
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
md("## S2 - blocked wheels (jammed gearbox / wheel held still), full duty")
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
md("Note: with free tyres on a floor the wheels slip before the motor stalls (traction limit, see S3, about 1.4 A per motor), so this case needs a jammed gearbox or a wheel held by an obstacle.")
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

# ------------------------------------------------------------------ S5 hard-coded demo route
SLEW = 3.0            # duty per second  (soft start: keeps the motor inrush inside the driver rating)
CTRL_DT = P.SIM["DT_CTRL"]


def route_run(groups, route, rec_hz=30.0):
    """Open-loop execution of [(name, seconds, duty_left, duty_right), ...] with a duty slew-rate limit."""
    rob = rb.Robot(groups_on=groups)
    dt = P.SIM["DT"]
    sub = int(round(CTRL_DT / dt))
    ul = ur = 0.0
    log, next_rec, step_i = [], 0.0, 0
    marks = []
    for name, T, tl, tr_ in route:
        marks.append((rob.t, name))
        for _ in range(int(round(T / CTRL_DT))):
            ul += max(-SLEW * CTRL_DT, min(SLEW * CTRL_DT, tl - ul))
            ur += max(-SLEW * CTRL_DT, min(SLEW * CTRL_DT, tr_ - ur))
            for _ in range(sub):
                rob.step(ul, ur, dt)
            if rob.t >= next_rec:
                log.append(dict(t=rob.t, x=rob.x, y=rob.y, th=rob.th, phil=rob.phil, phir=rob.phir, v=rob.v, wz=rob.wz,
                                il=rob.il, ir=rob.ir, vbat=rob.batt.v, ul=ul, ur=ur, seg=name))
                next_rec += 1.0 / rec_hz
    return rob, log, marks


def calibrate_spin(duty, t_side, duty_side, angle=math.pi / 2):
    """Seconds of +-duty spin that make one full cycle (side, pause, spin, settle) end 90 degrees to the left."""
    lo, hi = 0.2, 3.0
    for _ in range(14):
        mid = (lo + hi) / 2
        rob, _, _ = route_run(G1, [("side", t_side, duty_side, duty_side), ("pause", 0.5, 0.0, 0.0),
                                   ("spin", mid, -duty, duty), ("settle", 0.8, 0.0, 0.0)], rec_hz=1)
        if rob.th < angle:
            lo = mid
        else:
            hi = mid
    return round((lo + hi) / 2, 3)


SPIN_DUTY = 0.45
T_SIDE = 2.0
DUTY_SIDE = 0.60
T_SPIN = calibrate_spin(SPIN_DUTY, T_SIDE, DUTY_SIDE)
ROUTE = []
for k in range(4):
    ROUTE += [("side %d" % (k + 1), T_SIDE, DUTY_SIDE, DUTY_SIDE), ("pause", 0.5, 0.0, 0.0),
              ("spin left 90", T_SPIN, -SPIN_DUTY, SPIN_DUTY), ("settle", 0.8, 0.0, 0.0)]
ROUTE += [("stop", 0.5, 0.0, 0.0)]
md("## S5 - hard-coded demo route (open loop, no sensors)")
md("Route: 4 x [drive straight %.1f s at duty %.2f, pause, spin left %.3f s at +-%.2f (calibrated so one side+spin cycle turns the robot 90 deg), settle]; duty is slew-limited to %.0f /s."
   % (T_SIDE, DUTY_SIDE, T_SPIN, SPIN_DUTY, SLEW))
md()
md("| enabled | duration [s] | path length [m] | end position error [mm] | end heading error [deg] | peak motor A | mean motor A (moving) | min battery V | charge used [mAh] | worst module A (1.2 cont / 3.2 pulse) |")
md("|---|---|---|---|---|---|---|---|---|---|")
res5 = {}
for name, g in (("1 group", G1), ("3 groups", G3)):
    rob, log, marks = route_run(g, ROUTE)
    res5[name] = (rob, log, marks)
    path = sum(math.hypot(b["x"] - a["x"], b["y"] - a["y"]) for a, b in zip(log, log[1:]))
    moving = [x for x in log if abs(x["v"]) > 0.05]
    mean_i = sum(abs(x["il"]) + abs(x["ir"]) for x in moving) / (2 * max(1, len(moving)))
    used = (P.BATTERY["SOC_START"] - rob.batt.soc) * P.BATTERY["CAPACITY_AH"] * 1000
    worst = max(max(rob.bank.stat["A"]), max(rob.bank.stat["B"]))
    herr = math.degrees(((rob.th + math.pi) % (2 * math.pi)) - math.pi)
    md("| %s | %.1f | %.2f | %.0f | %.1f | %.2f | %.2f | %.2f | %.1f | %.2f |" % (
        name, rob.t, path, math.hypot(rob.x, rob.y) * 1000, herr, max(max(x["il"], x["ir"]) for x in log), mean_i,
        min(x["vbat"] for x in log), used, worst))
md()
rob, log, marks = res5["1 group"]
ts = [x["t"] for x in log]
# top-down trajectory plot with robot outline snapshots
W, H = 760, 620
cv = Canvas(W, H, (255, 255, 255))
xs_ = [x["x"] for x in log]; ys_ = [x["y"] for x in log]
pad = 0.45
x0_, x1_ = min(xs_) - pad, max(xs_) + pad
y0_, y1_ = min(ys_) - pad, max(ys_) + pad
sc = min((W - 40) / (x1_ - x0_), (H - 70) / (y1_ - y0_))
tp = lambda x, y: (20 + (x - x0_) * sc, H - 20 - (y - y0_) * sc)
cv.text(10, 8, "S5 HARD-CODED ROUTE - TOP VIEW (GRID 0.5 M, ROBOT OUTLINE EVERY 1.5 S)", (0, 0, 0), 1)
g_ = math.floor(x0_ * 2) / 2
while g_ <= x1_:
    a_, b_ = tp(g_, y0_), tp(g_, y1_); cv.line(a_[0], a_[1], b_[0], b_[1], (232, 232, 232), 1); g_ += 0.5
g_ = math.floor(y0_ * 2) / 2
while g_ <= y1_:
    a_, b_ = tp(x0_, g_), tp(x1_, g_); cv.line(a_[0], a_[1], b_[0], b_[1], (232, 232, 232), 1); g_ += 0.5
vmax_ = max(x["v"] for x in log) or 1
for a, b in zip(log, log[1:]):
    pa, pb = tp(a["x"], a["y"]), tp(b["x"], b["y"])
    f = max(0.0, min(1.0, a["v"] / vmax_))
    cv.line(pa[0], pa[1], pb[0], pb[1], (int(230 * (1 - f)), int(150 * f), 60), 2.5)
R_ = P.MECH["CHASSIS_RADIUS"]
nxt = 0.0
for x in log:
    if x["t"] >= nxt:
        nxt += 1.5
        c = tp(x["x"], x["y"])
        cv.circle(c[0], c[1], R_ * sc, (60, 90, 200), 0.10)
        cv.circle(c[0], c[1], R_ * sc, (60, 90, 200), 0.9, ring=1.2)
        hx, hy = tp(x["x"] + math.cos(x["th"]) * R_, x["y"] + math.sin(x["th"]) * R_)
        cv.line(c[0], c[1], hx, hy, (200, 30, 30), 2)
cv.save(os.path.join(RES, "S5_route_topview.png"))
stacked(os.path.join(RES, "S5_route.png"), [
    dict(series=[("speed m/s", ts, [x["v"] for x in log]), ("yaw rate rad/s", ts, [x["wz"] for x in log])], title="S5 hard-coded route, 1 group enabled", ylabel="m/s, rad/s"),
    dict(series=[("left motor", ts, [x["il"] for x in log]), ("right motor", ts, [x["ir"] for x in log])], title="motor currents", ylabel="A",
         hlines=[(3.6, (200, 0, 0), "1 group rated 3.6A")]),
    dict(series=[("battery V", ts, [x["vbat"] for x in log])], title="battery terminal voltage", ylabel="V", xlabel="time [s]"),
], title="RocketBoy S5")
write_csv("S5_route_30hz.csv", log)
import json as _json
_json.dump(dict(route=ROUTE, rec_hz=30.0, wheel_radius=P.wheel_radius(), track=P.track_width(),
                frames=[[round(x["t"], 4), round(x["x"], 5), round(x["y"], 5), round(x["th"], 5), round(x["phil"], 4), round(x["phir"], 4),
                         round(x["v"], 4), round(x["il"], 3), round(x["ir"], 3), round(x["vbat"], 3), x["seg"]] for x in log]),
           open(os.path.join(RES, "route_30hz.json"), "w"))

# firmware constants generated from the same route
fw_dir = os.path.join(os.path.dirname(HERE), "firmware", "rocketboy_hardcoded")
os.makedirs(fw_dir, exist_ok=True)
rows = ",\n".join('  {"%s", %d, %.2ff, %.2ff}' % (n, int(round(T * 1000)), tl, trr) for n, T, tl, trr in ROUTE)
open(os.path.join(fw_dir, "route.h"), "w").write(
    "// GENERATED by simulation/run_all.py - same route, durations and duty slew as the simulation\n"
    "#pragma once\nstruct Step { const char* name; unsigned long ms; float left; float right; };\n"
    "static const float SLEW_PER_S = %.1ff;   // duty units per second (soft start)\n"
    "static const Step ROUTE[] = {\n%s\n};\n" % (SLEW, rows))

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
