'use strict';
/* RocketBoy electro-mechanical model - JavaScript port of simulation/rocketbot.py (kept line-for-line comparable).
   Verified against the Python model by simulation/test_js_parity.py.

   battery (3S) -> 9 x TB6612FNG (3 enable groups) -> 2 DC gear-motors -> tyres -> differential-drive chassis */
const G = 9.81;

class Motor {
  constructor(m) {
    this.V = m.V_RATED;
    this.w0 = m.RPM_NOLOAD * 2 * Math.PI / 60;
    this.wr = m.RPM_RATED * 2 * Math.PI / 60;
    this.Tr = m.TORQUE_RATED_KGFCM * 0.0980665;
    this.I0 = m.I_NOLOAD;
    let R = 2.0, ke = 0;
    for (let i = 0; i < 200; i++) {                       // w0 - wr = R Tr / ke^2 and ke = (V - I0 R) / w0
      ke = (this.V - this.I0 * R) / this.w0;
      R = ke * ke * (this.w0 - this.wr) / this.Tr;
    }
    this.R = R; this.ke = ke; this.Kt = ke;
    this.Tf = this.Kt * this.I0;                          // friction torque at the output shaft
    this.I_stall = this.V / R;
    this.T_stall = this.Kt * (this.I_stall - this.I0);
    this.J_out = m.J_ROTOR * m.GEAR_RATIO * m.GEAR_RATIO;  // rotor inertia reflected to the output
  }
}

class Battery {
  constructor(b, ocv) {
    this.b = b; this.ocvTab = ocv;
    this.soc = b.SOC_START; this.cap = b.CAPACITY_AH; this.cells = b.CELLS;
    this.R = b.CELLS * b.R_CELL + b.R_PACK_EXTRA;
    this.v = this.ocv();
  }
  ocv() {
    const s = Math.min(1, Math.max(0, this.soc)), t = this.ocvTab;
    for (let i = 0; i < t.length - 1; i++) {
      const [s0, v0] = t[i], [s1, v1] = t[i + 1];
      if (s >= s0 && s <= s1) return this.cells * (v0 + (v1 - v0) * (s - s0) / (s1 - s0));
    }
    return this.cells * t[t.length - 1][1];
  }
  step(iLoad, dt) {
    this.v = this.ocv() - iLoad * this.R;
    this.soc -= iLoad * dt / (3600 * this.cap);
    return this.v;
  }
}

class DriverBank {
  constructor(d, groups) {
    this.ron = { A: d.RON_A.slice(), B: d.RON_B.slice() };   // 9 values per channel (same seed as the Python model)
    this.groups = groups.slice();
    this.iCont = d.I_CONT; this.iPeak = d.I_PEAK; this.rw = d.R_WIRING;
    this.reset();
  }
  reset() {
    const z = () => new Array(9).fill(0);
    this.stat = { A: z(), B: z() };           // peak |I| per module
    this.overCont = { A: z(), B: z() };       // seconds above the continuous rating
    this.overPeak = { A: z(), B: z() };
    this.now = { A: z(), B: z() };            // present current per module
  }
  active() { const a = []; for (let i = 0; i < 9; i++) if (this.groups[Math.floor(i / 3)]) a.push(i); return a; }
  nActive() { return this.active().length; }
  rEq(ch) {
    const act = this.active();
    if (!act.length) return null;
    let g = 0;
    for (const i of act) g += 1 / this.ron[ch][i];
    return 1 / g + this.rw;
  }
  split(ch, iMotor, dt) {
    const act = this.active();
    const out = this.now[ch];
    out.fill(0);
    let tot = 0;
    for (const i of act) tot += 1 / this.ron[ch][i];
    for (const i of act) {
      const ii = iMotor * (1 / this.ron[ch][i]) / tot;
      out[i] = ii;
      const a = Math.abs(ii);
      if (a > this.stat[ch][i]) this.stat[ch][i] = a;
      if (a > this.iCont) this.overCont[ch][i] += dt;
      if (a > this.iPeak) this.overPeak[ch][i] += dt;
    }
  }
}

class RocketSim {
  /* P = {motor, mech:{R_W,TRACK,MASS,IZ,MU,C_RR,DRIVE_FRACTION,YAW_VISCOUS,WHEEL_MASS}, battery, ocv, driver, logic} */
  constructor(P, groups, opts) {
    opts = opts || {};
    this.P = P;
    this.motor = new Motor(P.motor);
    this.batt = new Battery(P.battery, P.ocv);
    this.bank = new DriverBank(P.driver, groups || [true, true, true]);
    const M = P.mech;
    this.m = M.MASS; this.r = M.R_W; this.b = M.TRACK; this.Iz = M.IZ;
    this.slope = (opts.slopeDeg || 0) * Math.PI / 180;
    this.blocked = !!opts.blocked;
    this.Jw = 0.5 * M.WHEEL_MASS * this.r * this.r + this.motor.J_out;
    this.N = this.m * G * M.DRIVE_FRACTION / 2 * Math.cos(this.slope);
    this.mu = M.MU;
    this.reset();
  }
  reset() {
    this.x = this.y = this.th = 0; this.v = 0; this.wz = 0; this.wl = this.wr = 0;
    this.phil = this.phir = 0; this.t = 0; this.il = this.ir = 0; this.slipTime = 0;
    this.batt = new Battery(this.P.battery, this.P.ocv);
    this.bank.reset();
  }
  force(slip) { return this.mu * this.N * Math.tanh(slip / 0.02); }
  step(ul, ur, dt) {
    const mo = this.motor, bank = this.bank, M = this.P.mech;
    const vbat = this.batt.v;
    const cur = [];
    for (const [u, w, ch] of [[ul, this.wl, 'A'], [ur, this.wr, 'B']]) {
      const req = bank.rEq(ch);
      cur.push((req === null || Math.abs(u) < 1e-6) ? 0.0 : (u * vbat - mo.ke * w) / (mo.R + req));   // coast when STBY low / duty 0
    }
    const il = cur[0], ir = cur[1];
    this.il = il; this.ir = ir;
    let Tl = mo.Kt * il - mo.Tf * Math.tanh(this.wl / 0.5);
    let Tr = mo.Kt * ir - mo.Tf * Math.tanh(this.wr / 0.5);
    let fl = 0, fr = 0;
    if (this.blocked) {                                   // jammed gearbox: wheels cannot turn, robot cannot move
      this.wl = this.wr = 0; this.v = 0; this.wz = 0; Tl = Tr = 0;
    }
    const vl = this.v - this.wz * this.b / 2, vr = this.v + this.wz * this.b / 2;
    if (!this.blocked) {
      fl = this.force(this.wl * this.r - vl);
      fr = this.force(this.wr * this.r - vr);
      if (Math.abs(fl) > 0.95 * this.mu * this.N || Math.abs(fr) > 0.95 * this.mu * this.N) this.slipTime += dt;
    }
    let res = M.C_RR * this.m * G * Math.cos(this.slope) * Math.tanh(this.v / 0.02);
    res += this.m * G * Math.sin(this.slope);
    const aV = (fl + fr - res) / this.m;
    const aW = ((fr - fl) * this.b / 2 - M.YAW_VISCOUS * this.wz) / this.Iz;
    if (!this.blocked) {
      this.wl += dt * (Tl - fl * this.r) / this.Jw;
      this.wr += dt * (Tr - fr * this.r) / this.Jw;
      this.v += dt * aV;
      this.wz += dt * aW;
    }
    this.phil += this.wl * dt;
    this.phir += this.wr * dt;
    this.th += this.wz * dt;
    this.x += this.v * Math.cos(this.th) * dt;
    this.y += this.v * Math.sin(this.th) * dt;
    bank.split('A', il, dt);
    bank.split('B', ir, dt);
    const iBat = Math.abs(il) + Math.abs(ir) + this.P.logic.I_LOGIC;
    this.ibat = iBat;
    this.batt.step(iBat, dt);
    this.t += dt;
    return iBat;
  }
}

if (typeof module !== 'undefined') module.exports = { Motor, Battery, DriverBank, RocketSim };
