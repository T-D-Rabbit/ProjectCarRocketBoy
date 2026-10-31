"""Electro-mechanical model of the RocketBoy robot (pure Python, no third-party packages).

  battery (3S Li-ion)  ->  9 x TB6612FNG modules in parallel (enable groups of 3)  ->  2 DC gearmotors
  -> 100 mm wheels with a tanh tyre-force model -> differential-drive chassis (+ optional slope)

States: x, y, heading, v, yaw rate, left/right wheel speed, battery SOC.
The two motor channels (A = left, B = right) are driven by the same ESP32 signals on all modules,
so the current of one motor splits over the enabled modules by the inverse of their on-resistance.
"""
import math, random
import params as P


# ------------------------------------------------------------------ motor
class Motor:
    """Permanent magnet DC motor + gearbox, parameters derived from the datasheet rated point."""

    def __init__(self):
        m = P.MOTOR
        self.V = m["V_RATED"]
        self.w0 = m["RPM_NOLOAD"] * 2 * math.pi / 60
        self.wr = m["RPM_RATED"] * 2 * math.pi / 60
        self.Tr = m["TORQUE_RATED_KGFCM"] * 0.0980665          # N m
        self.I0 = m["I_NOLOAD"]
        # w0 - wr = R * Tr / ke^2 and  ke = (V - I0 R)/w0   -> fixed point on R
        R = 2.0
        for _ in range(200):
            ke = (self.V - self.I0 * R) / self.w0
            R = ke * ke * (self.w0 - self.wr) / self.Tr
        self.R, self.ke = R, ke
        self.Kt = ke
        self.Tf = self.Kt * self.I0                           # friction torque at the output shaft
        self.I_stall = self.V / R
        self.T_stall = self.Kt * (self.I_stall - self.I0)
        self.I_rated = self.Tr / self.Kt + self.I0
        N = m["GEAR_RATIO"]
        self.J_out = m["J_ROTOR"] * N * N                     # rotor inertia reflected to the output shaft

    def summary(self):
        return dict(R_ohm=self.R, ke_Vs_per_rad=self.ke, I_stall_A=self.I_stall,
                    T_stall_Nm=self.T_stall, T_stall_kgfcm=self.T_stall / 0.0980665,
                    I_rated_A=self.I_rated, J_out=self.J_out)


# ------------------------------------------------------------------ battery
class Battery:
    def __init__(self, soc=None):
        b = P.BATTERY
        self.soc = b["SOC_START"] if soc is None else soc
        self.cap = b["CAPACITY_AH"]
        self.R = b["CELLS"] * b["R_CELL"] + b["R_PACK_EXTRA"]
        self.cells = b["CELLS"]
        self.v = self.ocv()

    def ocv(self):
        s = min(1.0, max(0.0, self.soc))
        t = P.OCV
        for (s0, v0), (s1, v1) in zip(t, t[1:]):
            if s0 <= s <= s1:
                return self.cells * (v0 + (v1 - v0) * (s - s0) / (s1 - s0))
        return self.cells * t[-1][1]

    def step(self, i_load, dt):
        self.v = self.ocv() - i_load * self.R
        self.soc -= i_load * dt / (3600.0 * self.cap)
        return self.v


# ------------------------------------------------------------------ driver bank
class DriverBank:
    """N parallel TB6612 channels per motor, randomly spread on-resistance (decides current sharing)."""

    def __init__(self, groups_on=(True, True, True), seed=1):
        d = P.DRIVER
        rnd = random.Random(seed)
        self.ron = {"A": [], "B": []}
        for ch in "AB":
            for g in range(d["GROUPS"]):
                for k in range(d["MODULES_PER_GROUP"]):
                    self.ron[ch].append(d["RON_TYP"] * (1 + d["RON_SPREAD"] * rnd.uniform(-1, 1)))
        self.groups = list(groups_on)
        self.i_cont, self.i_peak = d["I_CONT"], d["I_PEAK"]
        self.rw = d["R_WIRING"]
        self.stat = {"A": [0.0] * 9, "B": [0.0] * 9}                  # per-module peak |I|
        self.over_cont = {"A": [0.0] * 9, "B": [0.0] * 9}              # time above 1.2 A
        self.over_peak = {"A": [0.0] * 9, "B": [0.0] * 9}              # time above 3.2 A

    def active(self, ch):
        return [i for i in range(9) if self.groups[i // 3]]

    def r_eq(self, ch):
        act = self.active(ch)
        if not act:
            return None
        g = sum(1.0 / self.ron[ch][i] for i in act)
        return 1.0 / g + self.rw

    def split(self, ch, i_motor, dt=0.0):
        act = self.active(ch)
        g = [1.0 / self.ron[ch][i] for i in act]
        tot = sum(g)
        out = [0.0] * 9
        for i, gi in zip(act, g):
            ii = i_motor * gi / tot
            out[i] = ii
            a = abs(ii)
            if a > self.stat[ch][i]:
                self.stat[ch][i] = a
            if a > self.i_cont:
                self.over_cont[ch][i] += dt
            if a > self.i_peak:
                self.over_peak[ch][i] += dt
        return out


# ------------------------------------------------------------------ robot
class Robot:
    def __init__(self, groups_on=(True, True, True), slope_deg=0.0, seed=1, blocked=False):
        self.motor = Motor()
        self.batt = Battery()
        self.bank = DriverBank(groups_on, seed)
        self.m = P.total_mass()
        self.r = P.wheel_radius()
        self.b = P.track_width()
        self.Iz = P.yaw_inertia()
        self.slope = math.radians(slope_deg)
        self.blocked = blocked
        # wheel + reflected rotor inertia per side
        self.Jw = 0.5 * P.MECH["WHEEL_MASS"] * self.r ** 2 + self.motor.J_out
        self.N = self.m * P.G * P.MECH["DRIVE_LOAD_FRACTION"] / 2 * math.cos(self.slope)
        self.mu = P.MECH["MU_TYRE"]
        # state
        self.x = self.y = self.th = 0.0
        self.v = 0.0
        self.wz = 0.0
        self.wl = self.wr = 0.0            # wheel angular speeds (rad/s)
        self.phil = self.phir = 0.0        # accumulated wheel rotation (rad), used by the 3D animation
        self.t = 0.0
        self.il = self.ir = 0.0            # signed motor currents
        self.log = []
        self.slip_time = 0.0

    # tyre force: tanh saturation with a small slip-velocity scale
    def _force(self, slip):
        return self.mu * self.N * math.tanh(slip / 0.02)

    def step(self, ul, ur, dt):
        mo, bank = self.motor, self.bank
        vbat = self.batt.v
        out = []
        for u, w, ch in ((ul, self.wl, "A"), (ur, self.wr, "B")):
            req = bank.r_eq(ch)
            if req is None or abs(u) < 1e-6:
                i = 0.0                      # coast (STBY low or 0 duty)
            else:
                i = (u * vbat - mo.ke * w) / (mo.R + req)
            out.append(i)
        il, ir = out
        self.il, self.ir = il, ir
        # shaft torque (friction acts against motion)
        Tl = mo.Kt * il - mo.Tf * math.tanh(self.wl / 0.5)
        Tr = mo.Kt * ir - mo.Tf * math.tanh(self.wr / 0.5)
        if self.blocked:
            self.wl = self.wr = 0.0
            self.v = self.wz = 0.0               # jammed: neither wheels nor robot can move
            Tl = Tr = 0.0
            fl = fr = 0.0
        # contact slip speeds
        vl = self.v - self.wz * self.b / 2
        vr = self.v + self.wz * self.b / 2
        if not self.blocked:
            fl = self._force(self.wl * self.r - vl)
            fr = self._force(self.wr * self.r - vr)
            if abs(fl) > 0.95 * self.mu * self.N or abs(fr) > 0.95 * self.mu * self.N:
                self.slip_time += dt
        res = P.MECH["C_RR"] * self.m * P.G * math.cos(self.slope) * math.tanh(self.v / 0.02)
        res += self.m * P.G * math.sin(self.slope)
        a_v = (fl + fr - res) / self.m
        a_w = ((fr - fl) * self.b / 2 - P.MECH["YAW_VISCOUS"] * self.wz) / self.Iz
        if not self.blocked:
            self.wl += dt * (Tl - fl * self.r) / self.Jw
            self.wr += dt * (Tr - fr * self.r) / self.Jw
            self.v += dt * a_v
            self.wz += dt * a_w
        self.phil += self.wl * dt
        self.phir += self.wr * dt
        # pose
        self.th += self.wz * dt
        self.x += self.v * math.cos(self.th) * dt
        self.y += self.v * math.sin(self.th) * dt
        # electrical bookkeeping
        mo_i = {"A": il, "B": ir}
        for ch in "AB":
            bank.split(ch, mo_i[ch], dt)
        i_bat = abs(il) + abs(ir) + P.BATTERY["I_LOGIC"]
        self.batt.step(i_bat, dt)
        self.t += dt
        return i_bat

    def record(self, extra=None):
        row = dict(t=self.t, x=self.x, y=self.y, th=self.th, v=self.v, wz=self.wz,
                   il=self.il, ir=self.ir, vbat=self.batt.v, soc=self.batt.soc,
                   ibat=abs(self.il) + abs(self.ir) + P.BATTERY["I_LOGIC"])
        if extra:
            row.update(extra)
        self.log.append(row)


# ------------------------------------------------------------------ helpers
def run(robot, duty_fn, t_end, dt=None, rec_every=0.01):
    dt = dt or P.SIM["DT"]
    n = int(t_end / dt)
    next_rec = 0.0
    for k in range(n):
        ul, ur = duty_fn(robot.t, robot)
        robot.step(ul, ur, dt)
        if robot.t >= next_rec:
            robot.record()
            next_rec += rec_every
    return robot
