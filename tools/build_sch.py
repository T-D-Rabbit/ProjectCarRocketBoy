#!/usr/bin/env python3
"""Patch the original RocketBoy schematic (KiCad 9) with the design corrections + new parts.

Fixes applied to the user's schematic
  1. ESP32 5Vin was tied to the raw battery net (VCC, 9-12.6 V) -> now a dedicated +5V net fed by an
     external buck module (header J2); battery net renamed VBAT.
  2. STBY of all 9 TB6612 modules was hard-wired to VCCQ (always enabled) -> three group nets
     STBY1..3 driven by the SPDT enable switches SW1..SW3 (ON = VCCQ, OFF = GND).
  3. ESP32 pin 21 (DevKit "CMD" = flash line) was tied to GND -> pin now left open (no-connect).
  4. Added bulk caps C1..C3 on VBAT, 5 V buck headers J1/J2, expansion header J3 (control lines +
     5 V/3V3/GND for a second PCB), chassis mounting holes H1..H4.
  5. BT1 / U11 / U12 footprints -> 5.08 mm screw terminals (the old 1.9 mm pads cannot carry the
     motor current).
"""
import os, re, sys, uuid
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from sexpr import parse, find, first, val, blocks, balanced
import parts as P

ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "originals", "RocketBoy.kicad_sch.orig")
OUT = os.path.join(ROOT, "RocketBoy", "RocketBoy.kicad_sch")
SYMOUT = os.path.join(ROOT, "RocketBoy", "RocketBoy.kicad_sym")
SHEET_UUID = "e4b79852-5c3e-4422-b46f-8380f33e21df"
NS = uuid.UUID("0a1b2c3d-4e5f-4a6b-8c7d-9e0f1a2b3c4d")


def U(name):
    return str(uuid.uuid5(NS, name))


class Q(str):
    """quoted string"""


def ser(node, ind=0):
    pad = "\t" * ind
    if isinstance(node, Q):
        return '"' + node.replace('"', '\\"') + '"'
    if not isinstance(node, list):
        return str(node)
    if all(not isinstance(x, list) for x in node):
        return "(" + " ".join(ser(x) for x in node) + ")"
    # head atoms on first line, lists on following lines
    head = []
    i = 0
    while i < len(node) and not isinstance(node[i], list):
        head.append(ser(node[i]))
        i += 1
    s = "(" + " ".join(head)
    for ch in node[i:]:
        s += "\n" + "\t" * (ind + 1) + ser(ch, ind + 1)
    s += "\n" + pad + ")"
    return s


def eff(size=1.27, hide=False, justify=None):
    e = ["effects", ["font", ["size", size, size]]]
    if justify:
        e.append(["justify"] + justify.split())
    if hide:
        e.append(["hide", "yes"])
    return e


def prop(name, value, x, y, ang=0, hide=False, size=1.27):
    return ["property", Q(name), Q(value), ["at", x, y, ang], eff(size, hide)]


# ------------------------------------------------------------------ symbol library (new, project local)
def box_symbol(name, ref, desc, pins, body_h=None, shape="rect"):
    """pins: list of (num, name, etype) placed on the left, 2.54 mm pitch."""
    n = len(pins)
    h = (n - 1) * 2.54 + 2.54 if n else 5.08
    sub = [
        "symbol", Q(name.split(":")[-1] + "_1_1"),
    ]
    if shape == "rect":
        sub.append(["rectangle", ["start", -1.27, 1.27], ["end", 5.08, round(-h + 1.27, 3)],
                    ["stroke", ["width", 0.254], ["type", "default"]], ["fill", ["type", "background"]]])
    elif shape == "hole":
        sub.append(["circle", ["center", 0, 0], ["radius", 2.54], ["stroke", ["width", 0.254], ["type", "default"]],
                    ["fill", ["type", "none"]]])
    for k, (num, pname, et) in enumerate(pins):
        y = round(-k * 2.54, 3)
        sub.append(["pin", et, "line", ["at", -5.08, y, 0], ["length", 3.81],
                    ["name", Q(pname), eff()], ["number", Q(num), eff()]])
    top = 3.0 if shape == "rect" else 4.5
    s = ["symbol", Q(name), ["pin_names", ["offset", 1.016]] if n else ["pin_names", ["offset", 0], ["hide", "yes"]],
         ["exclude_from_sim", "no"], ["in_bom", "yes" if shape == "rect" else "no"], ["on_board", "yes"],
         prop("Reference", ref, 0, top), prop("Value", name.split(":")[-1], 2.54, top + 2.54),
         prop("Footprint", "", 0, 0, 0, True), prop("Datasheet", "~", 0, 0, 0, True), prop("Description", desc, 0, 0, 0, True),
         sub, ["embedded_fonts", "no"]]
    return s


def lib_symbols(prefix):
    ET = "passive"
    syms = [
        box_symbol(prefix + "SW_SPDT_Slide", "SW", "SPDT slide switch: pin1 ON, pin2 common, pin3 OFF",
                   [("1", "ON", ET), ("2", "COM", ET), ("3", "OFF", ET)]),
        box_symbol(prefix + "CP_Polarized", "C", "Polarized capacitor", [("1", "+", ET), ("2", "-", ET)]),
        box_symbol(prefix + "Conn_01x02", "J", "Generic 1x02 connector", [("1", "Pin_1", ET), ("2", "Pin_2", ET)]),
        box_symbol(prefix + "Conn_01x10", "J", "Generic 1x10 connector", [(str(i), "Pin_%d" % i, ET) for i in range(1, 11)]),
        box_symbol(prefix + "Conn_01x16", "J", "Generic 1x16 connector", [(str(i), "Pin_%d" % i, ET) for i in range(1, 17)]),
        box_symbol(prefix + "Conn_01x08", "J", "Generic 1x08 connector", [(str(i), "Pin_%d" % i, ET) for i in range(1, 9)]),
        box_symbol(prefix + "MountingHole", "H", "Mounting hole", [], shape="hole"),
    ]
    return syms


# ------------------------------------------------------------------ patching the original text
orig = open(SRC).read()
text = orig
removed = []


def cut(text, spans):
    for i, j in sorted(spans, reverse=True):
        # also eat the preceding newline+tab so the file stays tidy
        k = i
        while k > 0 and text[k - 1] in "\t":
            k -= 1
        if k > 0 and text[k - 1] == "\n":
            k -= 1
        text = text[:k] + text[j:]
    return text


# --- 1. wires / junctions to delete
STBY_X = {120.65: 123.19, 162.56: 165.10, 203.20: 205.74}
STBY_Y = [48.26, 80.01, 111.76]
kill_wire = set()
for xv, xs in STBY_X.items():
    for y in STBY_Y:
        kill_wire.add(((xv, y), (xs, y)))
kill_wire.add(((39.37, 137.16), (41.91, 137.16)))         # ESP pin 21 -> GND
kill_junc = {(xv, y) for xv in STBY_X for y in STBY_Y} | {(41.91, 137.16)}

spans = []
for i, j, b in blocks(text, "wire"):
    t = parse(b)
    pts = [(float(p[1]), float(p[2])) for p in find(first(t, "pts"), "xy")]
    key = (pts[0], pts[1])
    key2 = (pts[1], pts[0])
    if key in kill_wire or key2 in kill_wire:
        spans.append((i, j))
found_w = len(spans)
for i, j, b in blocks(text, "junction"):
    t = parse(b)
    a = first(t, "at")
    if (float(a[1]), float(a[2])) in kill_junc:
        spans.append((i, j))
print("removed wires:", found_w, " junctions:", len(spans) - found_w)
text = cut(text, spans)

# --- 2. symbol instances: rename battery net, +5V, footprints
def patch_symbols(text):
    out, last = [], 0
    for i, j, b in blocks(text, "symbol\n\t\t(lib_id"):
        lib = re.search(r'\(lib_id "([^"]+)"', b).group(1)
        ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
        nb = b
        if lib == "power:VCC":
            newv = "+5V" if ref == "#PWR031" else "VBAT"
            nb = nb.replace('(property "Value" "VCC"', '(property "Value" "%s"' % newv, 1)
            nb = nb.replace('with name \\"VCC\\"', 'with name \\"%s\\"' % newv)
        if ref in ("BT1", "U11", "U12"):
            nb = nb.replace('"Control_Modules:SwitchPads_1"', '"%s"' % P.FP_TERM)
        out.append(text[last:i])
        out.append(nb)
        last = j
    out.append(text[last:])
    return "".join(out)


text = patch_symbols(text)

# --- 3. ESP lib symbol, pin 21 : GND(power_in) -> CMD(passive, left open)
old = '(pin power_in line\n\t\t\t\t\t(at -1.27 -54.61 90)\n\t\t\t\t\t(length 2.54)\n\t\t\t\t\t(name "GND"'
assert old in text
text = text.replace(old, '(pin passive line\n\t\t\t\t\t(at -1.27 -54.61 90)\n\t\t\t\t\t(length 2.54)\n\t\t\t\t\t(name "CMD"', 1)

# --- 4. paper size
text = text.replace('(paper "A4")', '(paper "A3")', 1)

# --- 5. new library symbols
prefix = "RocketBoy:"
libs = lib_symbols(prefix)
lib_text = "".join("\t\t" + ser(s, 2) + "\n" for s in libs)
i, j, lb = blocks(text, "lib_symbols")[0]
text = text[:j - 1].rstrip("\n\t") + "\n" + lib_text + "\t" + text[j - 1:]

# --- 6. new elements (labels, symbols, power symbols, flags, no-connect)
new_items = []
pwr_n = [32]
flg_n = [3]


def label(name, x, y, side):
    ang, just = (180, "right bottom") if side == "L" else (0, "left bottom")
    return ["label", Q(name), ["at", x, y, ang], eff(1.27, False, just), ["uuid", Q(U("label-%s-%s-%s" % (name, x, y)))]]


def power_sym(net, x, y):
    pwr_n[0] += 1
    ref = "#PWR%03d" % pwr_n[0]
    lib = {"GND": "power:GND", "VCCQ": "power:VCCQ"}.get(net, "power:VCC")
    if net == "GND":
        vy, ry = y + 3.81, y + 6.35
    else:
        vy, ry = y - 3.81, y - 6.35
    return ["symbol", ["lib_id", Q(lib)], ["at", x, y, 0], ["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "yes"],
            ["on_board", "yes"], ["dnp", "no"], ["uuid", Q(U("pwr-%s-%s-%s" % (net, x, y)))],
            prop("Reference", ref, x, ry, 0, True), prop("Value", net, x - 7.0, vy, 0),
            prop("Footprint", "", x, y, 0, True), prop("Datasheet", "", x, y, 0, True),
            prop("Description", 'Power symbol creates a global label with name "%s"' % net, x, y, 0, True),
            ["pin", Q("1"), ["uuid", Q(U("pwrpin-%s-%s-%s" % (net, x, y)))]],
            ["instances", ["project", Q("RocketBoy"), ["path", Q("/" + SHEET_UUID), ["reference", Q(ref)], ["unit", 1]]]]]


def flag(x, y):
    flg_n[0] += 1
    ref = "#FLG%02d" % flg_n[0]
    return ["symbol", ["lib_id", Q("power:PWR_FLAG")], ["at", x, y, 0], ["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "yes"],
            ["on_board", "yes"], ["dnp", "no"], ["uuid", Q(U("flag-%s-%s" % (x, y)))],
            prop("Reference", ref, x, y - 3.81, 0, True), prop("Value", "PWR_FLAG", x, y - 3.81, 0, True),
            prop("Footprint", "", x, y, 0, True), prop("Datasheet", "~", x, y, 0, True),
            prop("Description", "Special symbol for telling ERC where power comes from", x, y, 0, True),
            ["pin", Q("1"), ["uuid", Q(U("flagpin-%s-%s" % (x, y)))]],
            ["instances", ["project", Q("RocketBoy"), ["path", Q("/" + SHEET_UUID), ["reference", Q(ref)], ["unit", 1]]]]]


POWER_NETS = {"GND", "VCCQ", "VBAT", "+5V"}
SYM_POS = {
    "SW1": (50.8, 175.26), "SW2": (111.76, 175.26), "SW3": (172.72, 175.26),
    "C1": (50.8, 215.9), "C2": (111.76, 215.9), "C3": (172.72, 215.9),
    "J1": (233.68, 175.26), "J2": (233.68, 200.66), "J3": (294.64, 175.26), "J4": (294.64, 215.9), "J5": (355.6, 175.26),
    "H1": (240.0, 275.0), "H2": (260.0, 275.0), "H3": (280.0, 275.0), "H4": (300.0, 275.0),
}
for ref, part in P.PARTS.items():
    x, y = SYM_POS[ref]
    lib = part["sym"]
    nm = lib.split(":")[1]
    n = len(part["pins"])
    props = [prop("Reference", ref, x, y + 4.0, 0), prop("Value", part["value"], x + 2.54, y + 6.5, 0),
             prop("Footprint", part["fp"], x, y, 0, True), prop("Datasheet", "~", x, y, 0, True),
             prop("Description", part["desc"], x, y, 0, True)]
    pins = [["pin", Q(num), ["uuid", Q(U("pin-%s-%s" % (ref, num)))]] for num, pn, net in part["pins"]]
    inst = ["symbol", ["lib_id", Q(lib)], ["at", x, y, 0], ["unit", 1], ["exclude_from_sim", "no"], ["in_bom", "no" if ref.startswith("H") else "yes"],
            ["on_board", "yes"], ["dnp", "no"], ["uuid", Q(part["uuid"])]] + props + pins + [
        ["instances", ["project", Q("RocketBoy"), ["path", Q("/" + SHEET_UUID), ["reference", Q(ref)], ["unit", 1]]]]]
    new_items.append(inst)
    for k, (num, pn, net) in enumerate(part["pins"]):
        px, py = round(x - 5.08, 2), round(y + k * 2.54, 2)       # sheet y grows downwards
        if net in POWER_NETS:
            new_items.append(power_sym(net, px, py))
        else:
            new_items.append(label(net.lstrip("/"), px, py, "L"))

# PWR_FLAG on the +5V net (J2 pin 1 end)
jx, jy = SYM_POS["J2"]
new_items.append(flag(round(jx - 5.08, 2), round(jy, 2)))

# STBY group labels at the STBY pins of the 9 modules (pin end = x_vcc + 2.54)
for xv, xs in STBY_X.items():
    g = {120.65: 1, 162.56: 2, 203.20: 3}[xv]
    for y in STBY_Y:
        new_items.append(["label", Q("STBY%d" % g), ["at", xs, y, 90], eff(1.27, False, "left bottom"),
                          ["uuid", Q(U("stby-%d-%s" % (g, y)))]])

# labels for the break-out pins on the ESP32 symbol (pin-end coordinates of the symbol, see sch_netlist extraction)
ESP_PIN_POS = {  # pad -> (x, y, side)
    "4": (26.67, 85.09, "L"), "5": (26.67, 87.63, "L"), "6": (26.67, 90.17, "L"), "7": (26.67, 92.71, "L"), "8": (26.67, 95.25, "L"),
    "9": (26.67, 97.79, "L"), "10": (26.67, 100.33, "L"), "18": (26.67, 120.65, "L"), "12": (26.67, 123.19, "L"), "11": (26.67, 125.73, "L"),
    "32": (26.67, 129.54, "L"), "31": (26.67, 132.08, "L"),
    "33": (60.96, 85.09, "R"), "34": (60.96, 87.63, "R"), "35": (60.96, 90.17, "R"), "36": (60.96, 92.71, "R"), "37": (60.96, 95.25, "R"),
    "17": (60.96, 102.87, "R"), "14": (60.96, 105.41, "R"), "16": (60.96, 107.95, "R"), "15": (60.96, 110.49, "R"),
}
for pad, net in P.ESP_NETS.items():
    if pad in ESP_PIN_POS and net and net.startswith("/GPIO") or pad in ("37",):
        x, y, side = ESP_PIN_POS[pad]
        new_items.append(label(net.lstrip("/"), x, y, side))
n_lbl = sum(1 for pad, net in P.ESP_NETS.items() if pad in ESP_PIN_POS and net)
assert n_lbl == 21, n_lbl

# no-connect on ESP32 pin 21 (CMD)
new_items.append(["no_connect", ["at", 39.37, 137.16], ["uuid", Q(U("nc-esp-21"))]])

# note text
new_items.append(["text", Q("FIXES vs original: (1) ESP32 5Vin now +5V from buck module (was raw battery); (2) STBY per group via SW1..SW3 (was always on); "
                            "(3) ESP32 pin 21 (CMD) no longer tied to GND; (4) VM bulk caps, expansion header J3 + ESP32 GPIO break-out headers J4/J5 for a top PCB, mounting holes, screw terminals added."),
                  ["exclude_from_sim", "no"], ["at", 30.0, 160.0, 0], eff(1.5, False, "left bottom"), ["uuid", Q(U("note-fixes"))]])

add_text = "".join("\t" + ser(it, 1) + "\n" for it in new_items)
k = text.index("\t(sheet_instances")
text = text[:k] + add_text + text[k:]
open(OUT, "w").write(text)

# project-local symbol library so "Update symbols from library" and the lib table resolve
lib_file = ["kicad_symbol_lib", ["version", 20241209], ["generator", Q("kicad_symbol_editor")], ["generator_version", Q("9.0")]]
lib_file += lib_symbols("")
open(SYMOUT, "w").write(ser(lib_file, 0) + "\n")

open(os.path.join(ROOT, "RocketBoy", "sym-lib-table"), "w").write(
    '(sym_lib_table\n\t(version 7)\n\t(lib (name "RocketBoy")(type "KiCad")(uri "${KIPRJMOD}/RocketBoy.kicad_sym")(options "")(descr "RocketBoy project symbols"))\n)\n')
open(os.path.join(ROOT, "RocketBoy", "fp-lib-table"), "w").write(
    '(fp_lib_table\n\t(version 7)\n\t(lib (name "RocketBoy")(type "KiCad")(uri "${KIPRJMOD}/RocketBoy.pretty")(options "")(descr "RocketBoy project footprints"))\n)\n')
print("wrote", OUT, len(text), "bytes")
