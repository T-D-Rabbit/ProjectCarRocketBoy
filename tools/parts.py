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
FP_HDR16 = "RocketBoy:PinHeader_1x16_P2.54mm_Vertical"
FP_HDR8 = "RocketBoy:PinHeader_1x08_P2.54mm_Vertical"
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
add("J3", "EXPANSION", FP_HDR10, "RocketBoy:Conn_01x10",
    [("1", "5V", "+5V"), ("2", "3V3", "VCCQ"), ("3", "GND", "GND"), ("4", "BIN1", "/BIN1"), ("5", "BIN2", "/BIN2"),
     ("6", "PWMB", "/PWMB"), ("7", "AIN2", "/AIN2"), ("8", "AIN1", "/AIN1"), ("9", "GND", "GND"), ("10", "PWMA", "/PWMA")],
    "Expansion header for a second PCB / controller: 1=5V 2=3V3 3=GND 4=BIN1 5=BIN2 6=PWMB 7=AIN2 8=AIN1 9=GND 10=PWMA "
    "(same nets as the ESP32 control pins, remove the ESP32 when the other board drives them)")
# ---- break-out of every usable, still-unused ESP32 pin for a top PCB
# east column of the ESP32 socket (DevKit pads 19..4, listed top -> bottom on the board)
ESP_EAST = [("19", "GND", "GND"), ("18", "GPIO23", "/GPIO23"), ("17", "GPIO22", "/GPIO22"), ("16", "TX0_GPIO1", "/GPIO1_TX"),
            ("15", "RX0_GPIO3", "/GPIO3_RX"), ("14", "GPIO21", "/GPIO21"), ("13", "GND", "GND"), ("12", "GPIO19", "/GPIO19"),
            ("11", "GPIO18", "/GPIO18"), ("10", "GPIO5", "/GPIO5"), ("9", "GPIO17", "/GPIO17"), ("8", "GPIO16", "/GPIO16"),
            ("7", "GPIO4", "/GPIO4"), ("6", "GPIO0", "/GPIO0"), ("5", "GPIO2", "/GPIO2"), ("4", "GPIO15", "/GPIO15")]
# west column (DevKit pads 38..31)
ESP_WEST = [("38", "3V3", "VCCQ"), ("37", "EN", "/EN"), ("36", "GPIO36_SVP", "/GPIO36"), ("35", "GPIO39_SVN", "/GPIO39"),
            ("34", "GPIO34", "/GPIO34"), ("33", "GPIO35", "/GPIO35"), ("32", "GPIO32", "/GPIO32"), ("31", "GPIO33", "/GPIO33")]
add("J4", "ESP_GPIO_EAST", FP_HDR16, "RocketBoy:Conn_01x16",
    [(str(k + 1), nm, net) for k, (pad, nm, net) in enumerate(ESP_EAST)],
    "Break-out of the east ESP32 pin row (DevKit pads 19..4): GND, GPIO23/22/1/3/21, GND, GPIO19/18/5/17/16/4/0/2/15. "
    "Flash pins GPIO6-11 are NOT broken out.")
add("J5", "ESP_GPIO_WEST", FP_HDR8, "RocketBoy:Conn_01x08",
    [(str(k + 1), nm, net) for k, (pad, nm, net) in enumerate(ESP_WEST)],
    "Break-out of the west ESP32 pin row (DevKit pads 38..31): 3V3, EN, GPIO36/39/34/35 (input only), GPIO32/33")
for i in range(1, 5):
    add("H%d" % i, "M3", FP_HOLE, "RocketBoy:MountingHole", [], "M3 mounting hole (chassis pattern)")

# ESP32 pad -> net map (the original design only wired the 6 motor-control pads, 5V, 3V3, GND)
ESP_NETS = {   # filled below with the break-out pins too
    "20": "+5V",            # was VBAT (12 V) -> FIXED: now 5 V from the buck module
    "38": "VCCQ",           # 3V3
    "21": None,             # was GND but this DevKit pin is CMD (flash) -> now left open
    "24": "/PWMA", "26": "/AIN1", "27": "/AIN2", "28": "/PWMB", "29": "/BIN2", "30": "/BIN1",
}
# hole pattern of the chassis STEP: (+-75, +-100)
HOLES = [(-75.0, -100.0), (75.0, -100.0), (-75.0, 100.0), (75.0, 100.0)]

for _pad, _nm, _net in ESP_EAST + ESP_WEST:
    if _net not in ("GND", "VCCQ"):
        ESP_NETS[_pad] = _net
