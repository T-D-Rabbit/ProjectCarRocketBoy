"""All numbers used by the RocketBoy simulation, each tagged with where it comes from.

[PDF]     read from "Johnson Motor.pdf" / "L Clamp.pdf"
[STEP]    measured on "Chassis file.step"
[KICAD]   taken from RocketBoy.kicad_pcb / .kicad_sch
[DS]      published TB6612FNG / Molicel datasheet typical values
[ASSUMED] not given anywhere in the repository -> edit here, everything else follows
"""
import math

G = 9.81

# ---------------------------------------------------------------- motor  (SGMADA SG-3851218000-60K, 12 V)
MOTOR = dict(
    V_RATED=12.0,                 # [PDF] 12 V DC
    RPM_NOLOAD=300.0,             # [PDF] No-load speed 300 +-30 rpm (output shaft)
    RPM_RATED=220.0,              # [PDF] rated-load speed 220 +-22 rpm
    TORQUE_RATED_KGFCM=6.0,       # [PDF] rated load torque 6 kgf.cm
    I_NOLOAD=0.50,                # [PDF] no-load current <= 600 mA  -> 0.5 A used
    I_RATED_MAX=4.5,              # [PDF] rated current <= 4500 mA (upper bound, used only as a sanity check)
    GEAR_RATIO=60.0,              # [ASSUMED] "60K" in the model code = 1:60
    J_ROTOR=2.5e-6,               # [ASSUMED] rotor inertia kg m^2 (29 mm brushed can)
    I_STALL=7.5,                  # [USER] stall current 7.5 A (the stall rows of the PDF are blank). With I_STALL, R = V / I_STALL and
                                  # Ke follows from the no-load point; the datasheet rated point (220 rpm @ 6 kgf.cm) is then only a check.
)

# ---------------------------------------------------------------- mechanical
MECH = dict(
    WHEEL_DIAMETER=0.110,         # [ASSUMED] 110 mm rubber wheel, 6 mm bore (fits the 34.8 mm of free shaft; gives 25.3 mm under-chassis clearance)
    WHEEL_WIDTH=0.025,            # [ASSUMED]
    WHEEL_MASS=0.200,             # [ASSUMED] each
    AXLE_ABOVE_TOP=0.0267,        # [PDF] L-clamp: motor axis 26.7 mm above the flange face; clamps are bolted to the TOP face of the chassis
    CHASSIS_THICKNESS=0.003,      # [STEP]
    CHASSIS_RADIUS=0.150,         # [STEP]  (300 mm disc)
    CASTER_Y=0.125,               # [STEP]  caster slots at y = +-125 mm
    CLAMP_PLATE_X=0.1479,         # [STEP]+[PDF] vertical clamp plate at x = 130.8+... 147.9 mm
    SHAFT_BEYOND_PLATE=0.0348,    # [PDF] 4.8 mm boss + 30 mm shaft beyond the 1.5 mm plate
    MU_TYRE=0.80,                 # [ASSUMED] rubber on laminate / matt board
    C_RR=0.02,                    # [ASSUMED] rolling resistance coefficient
    DRIVE_LOAD_FRACTION=0.85,     # [ASSUMED] share of weight on the two drive wheels (rest on the casters)
    YAW_VISCOUS=0.02,             # [ASSUMED] N m s, caster scrub etc.
)
MASSES = {                        # kg, [ASSUMED] (3 mm acrylic chassis)
    "chassis 300 mm x 3 mm acrylic": 0.25,
    "2 x SG-3851218000-60K motor": 0.60,
    "2 x L clamp (1.5 mm steel)": 0.06,
    "2 x wheel 110 mm": 0.40,
    "2 x ball caster": 0.10,
    "3S1P Molicel pack + holder": 0.20,
    "PCB 155x208 + 9 TB6612 + ESP32 + terminals + standoffs": 0.45,
    "buck module + voltage indicator + wiring + fasteners": 0.13,
}

# ---------------------------------------------------------------- driver (Toshiba TB6612FNG)
DRIVER = dict(
    I_CONT=1.2,                   # [DS] A per channel, continuous
    I_PEAK=3.2,                   # [DS] A per channel, pulsed (10 ms single pulse)
    RON_TYP=0.50,                 # [DS] ohm, high+low side typical
    RON_SPREAD=0.25,              # [ASSUMED] +-25 % unit-to-unit spread (decides current sharing)
    R_WIRING=0.03,                # [ASSUMED] ohm per motor, connector + wire
    N_MODULES=9,                  # [KICAD]
    GROUPS=3,                     # [KICAD] (fixed in this repo: STBY1..3 enable switches)
    MODULES_PER_GROUP=3,
)

# ---------------------------------------------------------------- battery (3S Molicel INR18650-P28A class)
BATTERY = dict(
    CELLS=3,
    CAPACITY_AH=2.8,              # [DS] P28A 2.8 Ah
    R_CELL=0.022,                 # [DS] ~22 mohm DCIR per cell
    R_PACK_EXTRA=0.035,           # [ASSUMED] holder, fuse, switch, wires
    I_LOGIC=0.35,                 # [ASSUMED] ESP32 + 9 logic rails + IR array, A (from VBAT through the buck)
    SOC_START=0.9,
)
# open-circuit voltage per cell vs state of charge (typical NMC 18650)
OCV = [(0.0, 3.00), (0.05, 3.30), (0.10, 3.45), (0.20, 3.58), (0.30, 3.65), (0.40, 3.70), (0.50, 3.76),
       (0.60, 3.84), (0.70, 3.93), (0.80, 4.02), (0.90, 4.10), (1.0, 4.20)]

# ---------------------------------------------------------------- time steps
SIM = dict(DT=0.0005, DT_CTRL=0.005)


def total_mass():
    return sum(MASSES.values())


def wheel_radius():
    return MECH["WHEEL_DIAMETER"] / 2


def chassis_top_height():
    """Top face of the chassis above the ground (wheel axle height minus the clamp axis height)."""
    return wheel_radius() - MECH["AXLE_ABOVE_TOP"]


def ground_clearance():
    """Underside of the chassis above ground = room for the battery pack / caster height."""
    return chassis_top_height() - MECH["CHASSIS_THICKNESS"]


def track_width():
    """Wheel-centre to wheel-centre distance (wheels outboard of the clamp plates)."""
    inner = MECH["CLAMP_PLATE_X"] + 0.005
    return 2 * (inner + MECH["WHEEL_WIDTH"] / 2)


def yaw_inertia():
    """kg m^2 about the vertical axis through the axle centre."""
    m_motor, m_wheel, m_clamp = 0.60, 0.40, 0.06                       # totals for both sides (see MASSES)
    m_body = total_mass() - m_motor - m_wheel - m_clamp
    i_body = 0.5 * m_body * (0.85 * MECH["CHASSIS_RADIUS"]) ** 2         # PCB/battery/chassis spread over the disc
    i_side = m_motor * 0.11 ** 2 + m_wheel * (track_width() / 2) ** 2 + m_clamp * MECH["CLAMP_PLATE_X"] ** 2
    return i_body + i_side
