"""Parameters handed to the JavaScript model (simulation/web/sim_core.js): one source of truth = params.py."""
import params as P
import rocketbot as rb


def build():
    m = P.MOTOR
    bank = rb.DriverBank(seed=1)
    return dict(
        motor={k: m[k] for k in ("V_RATED", "RPM_NOLOAD", "RPM_RATED", "TORQUE_RATED_KGFCM", "I_NOLOAD", "J_ROTOR", "GEAR_RATIO")},
        mech=dict(R_W=P.wheel_radius(), TRACK=P.track_width(), MASS=P.total_mass(), IZ=P.yaw_inertia(), MU=P.MECH["MU_TYRE"],
                  C_RR=P.MECH["C_RR"], DRIVE_FRACTION=P.MECH["DRIVE_LOAD_FRACTION"], YAW_VISCOUS=P.MECH["YAW_VISCOUS"],
                  WHEEL_MASS=P.MECH["WHEEL_MASS"]),
        battery={k: P.BATTERY[k] for k in ("CELLS", "CAPACITY_AH", "R_CELL", "R_PACK_EXTRA", "SOC_START")},
        ocv=[list(x) for x in P.OCV],
        driver=dict(I_CONT=P.DRIVER["I_CONT"], I_PEAK=P.DRIVER["I_PEAK"], R_WIRING=P.DRIVER["R_WIRING"],
                    RON_A=bank.ron["A"], RON_B=bank.ron["B"]),
        logic=dict(I_LOGIC=P.BATTERY["I_LOGIC"]),
    )
