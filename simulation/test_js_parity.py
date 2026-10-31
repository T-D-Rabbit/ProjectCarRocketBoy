#!/usr/bin/env python3
"""Checks that the JavaScript model used by RocketBoy_Simulator.html gives the same numbers as the Python model.
    python3 simulation/test_js_parity.py      (needs `node`)"""
import os, sys, json, subprocess, math
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import params as P
import rocketbot as rb
import web_params

route = json.load(open(os.path.join(HERE, "results", "route_30hz.json")))["route"]
params = web_params.build()
SLEW, DTC, DT = 3.0, P.SIM["DT_CTRL"], P.SIM["DT"]


def py_cases():
    out = {}
    r = rb.Robot(groups_on=(True, False, False))
    rb.run(r, lambda t, rob: (1.0, 1.0), 3.0)
    out["launch"] = dict(v=r.v, il=r.il, vbat=r.batt.v, peak=max(x["il"] for x in r.log), worst=max(r.bank.stat["A"]), soc=r.batt.soc)
    r = rb.Robot(groups_on=(True, True, True), blocked=True)
    rb.run(r, lambda t, rob: (1.0, 1.0), 0.3)
    out["stall"] = dict(il=r.il, vbat=r.batt.v, worst=max(r.bank.stat["A"]))
    r = rb.Robot(groups_on=(True, False, False))
    ul = ur = 0.0
    sub = int(round(DTC / DT))
    for name, T, tl, tr_ in route:
        for _ in range(int(round(T / DTC))):
            ul += max(-SLEW * DTC, min(SLEW * DTC, tl - ul)); ur += max(-SLEW * DTC, min(SLEW * DTC, tr_ - ur))
            for _ in range(sub):
                r.step(ul, ur, DT)
    out["route"] = dict(x=r.x, y=r.y, th=r.th, soc=r.batt.soc, worst=max(r.bank.stat["A"]), phil=r.phil)
    return out


JS = r'''
const {RocketSim} = require('./web/sim_core.js');
const P = JSON.parse(process.argv[2]), route = JSON.parse(process.argv[3]);
const DT = %(DT)r, DTC = %(DTC)r, SLEW = %(SLEW)r, sub = Math.round(DTC / DT);
const out = {};
let s = new RocketSim(P, [true, false, false]); let peak = 0;
for (let i = 0; i < Math.floor(3.0 / DT); i++) { s.step(1.0, 1.0, DT); peak = Math.max(peak, s.il); }
out.launch = {v: s.v, il: s.il, vbat: s.batt.v, peak, worst: Math.max(...s.bank.stat.A), soc: s.batt.soc};
s = new RocketSim(P, [true, true, true], {blocked: true});
for (let i = 0; i < Math.floor(0.3 / DT); i++) s.step(1.0, 1.0, DT);
out.stall = {il: s.il, vbat: s.batt.v, worst: Math.max(...s.bank.stat.A)};
s = new RocketSim(P, [true, false, false]); let ul = 0, ur = 0;
for (const [name, T, tl, tr] of route) {
  for (let k = 0; k < Math.round(T / DTC); k++) {
    ul += Math.max(-SLEW * DTC, Math.min(SLEW * DTC, tl - ul)); ur += Math.max(-SLEW * DTC, Math.min(SLEW * DTC, tr - ur));
    for (let j = 0; j < sub; j++) s.step(ul, ur, DT);
  }
}
out.route = {x: s.x, y: s.y, th: s.th, soc: s.batt.soc, worst: Math.max(...s.bank.stat.A), phil: s.phil};
console.log(JSON.stringify(out));
''' % dict(DT=DT, DTC=DTC, SLEW=SLEW)

if __name__ == "__main__":
    # python's Robot.log-based peak uses 10 ms sampling; use the same definition as JS (every step) for a fair comparison
    py = py_cases()
    r = rb.Robot(groups_on=(True, False, False))
    peak = 0.0
    for _ in range(int(3.0 / DT)):
        r.step(1.0, 1.0, DT); peak = max(peak, r.il)
    py["launch"]["peak"] = peak
    open(os.path.join(HERE, "_parity.js"), "w").write(JS)
    try:
        res = subprocess.run(["node", os.path.join(HERE, "_parity.js"), json.dumps(params), json.dumps(route)], capture_output=True, text=True, cwd=HERE)
    finally:
        os.remove(os.path.join(HERE, "_parity.js"))
    if res.returncode:
        print(res.stderr); sys.exit(1)
    js = json.loads(res.stdout)
    worst = 0.0
    for case in py:
        for k, v in py[case].items():
            d = abs(v - js[case][k]) / max(1e-9, abs(v))
            worst = max(worst, d)
            print("%-7s %-6s python %.9g  js %.9g  rel.diff %.2e" % (case, k, v, js[case][k], d))
    print("max relative difference: %.2e  ->  %s" % (worst, "PASS" if worst < 1e-6 else "FAIL"))
    sys.exit(0 if worst < 1e-6 else 1)
