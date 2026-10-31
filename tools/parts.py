"""Single source of truth for the NEW parts that are added to the RocketBoy design.

Both build_pcb.py (footprints, placement, routing) and build_sch.py (symbols, labels) import
this file, so the schematic and the PCB can never disagree about reference designators,
pin numbers or net names.
"""
import uuid as _uuid


def _u(name):
    return str(_uuid.uuid5(_uuid.UUID("6f0c9d3e-2b7a-4c11-9a55-0d2c3e4f5a60"), name))


# ---------------------------------------------------------------- footprint families
FP_TERM = "RocketBoy:TerminalBlock_5.08mm_2P_Vertical"
FP_SW = "RocketBoy:SPDT_Slide_1x03_P2.54mm"
FP_CAP = "RocketBoy:CP_Radial_D10.0mm_P5.00mm"
FP_HDR2 = "RocketBoy:PinHeader_1x02_P2.54mm_Vertical"
FP_HDR10 = "RocketBoy:PinHeader_1x10_P2.54mm_Vertical"
FP_HOLE = "RocketBoy:MountingHole_3.2mm_M3"

# ---------------------------------------------------------------- new parts
# ref: dict(value, fp, sym, pins=[(num, name, net)], uuid)
PARTS = {}


def add(ref, value, fp, sym, pins, desc=""):
    PARTS[ref] = dict(ref=ref, value=value, fp=fp, sym=sym, pins=pins, uuid=_u(ref), desc=desc)


for g in (1, 2, 3):
    add("SW%d" % g, "STBY_GROUP%d" % g, FP_SW, "RocketBoy:SW_SPDT_Slide",
        [("1", "ON", "VCCQ"), ("2", "COM", "/STBY%d" % g), ("3", "OFF", "GND")],
        "Group %d enable: ON = STBY high (3 TB6612 modules active), OFF = STBY low (outputs Hi-Z)" % g)

for i in (1, 2, 3):
    add("C%d" % i, "470uF 25V", FP_CAP, "RocketBoy:CP_Polarized",
        [("1", "+", "VBAT"), ("2", "-", "GND")], "VM bulk capacitor %d" % i)

add("J1", "BUCK_IN", FP_HDR2, "RocketBoy:Conn_01x02",
    [("1", "Pin_1", "VBAT"), ("2", "Pin_2", "GND")], "Input to external 5 V buck module (VBAT, GND)")
add("J2", "BUCK_OUT", FP_HDR2, "RocketBoy:Conn_01x02",
    [("1", "Pin_1", "+5V"), ("2", "Pin_2", "GND")], "Output of external 5 V buck module (+5V, GND)")
add("J3", "IR_ARRAY", FP_HDR10, "RocketBoy:Conn_01x10",
    [("1", "GND", "GND"), ("2", "VCC", "VCCQ")] + [(str(i + 2), "OUT%d" % i, "/IR%d" % i) for i in range(1, 9)],
    "8-channel IR line array header: 1=GND 2=3V3 3..10=OUT1..OUT8 (verify against your sensor)")
for i in range(1, 5):
    add("H%d" % i, "M3", FP_HOLE, "RocketBoy:MountingHole", [], "M3 mounting hole (chassis pattern)")

# ESP32 pad -> net map (the original design only wired the 6 motor-control pads, 5V, 3V3, GND)
ESP_NETS = {
    "20": "+5V",            # was VBAT (12 V) -> FIXED: now 5 V from the buck module
    "38": "VCCQ",           # 3V3
    "21": None,             # was GND but this DevKit pin is CMD (flash) -> now left open
    "24": "/PWMA", "26": "/AIN1", "27": "/AIN2", "28": "/PWMB", "29": "/BIN2", "30": "/BIN1",
    "36": "/IR1", "35": "/IR2", "34": "/IR3", "33": "/IR4", "32": "/IR5", "31": "/IR6",
    "12": "/IR8", "11": "/IR7",
}
# hole pattern of the chassis STEP: (+-75, +-100)
HOLES = [(-75.0, -100.0), (75.0, -100.0), (-75.0, 100.0), (75.0, 100.0)]
