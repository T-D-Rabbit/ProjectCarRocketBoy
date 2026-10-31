#!/usr/bin/env python3
"""Generate the completed RocketBoy PCB (KiCad 9 .kicad_pcb) from the original user design.

* keeps the user's 9 x TB6612FNG module footprints, ESP32 socket and terminal pads (same symbol
  links / UUIDs) but re-places them into a 3 x 3 grid on a 158 x 208 mm board that uses the
  chassis hole pattern (+-75, +-100) taken from "Chassis file.step"
* adds board outline, mounting holes, group-enable switches, bulk caps, buck-module and IR-array
  headers
* routes every net (2-layer, bus lanes on B.Cu, stubs/trunks on F.Cu, GND pour on B.Cu)
* writes tools/out/pcb_preview.png and runs an independent clearance / connectivity check

Run:  python3 tools/build_pcb.py
"""
import os, re, sys, math, random, uuid, collections

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from pcbmodel import Board, Pad, Track, Via, rot_pt, check_clearance, check_connectivity
from sexpr import parse, find, first, val
import parts as P
from pngcanvas import Canvas, rgb

ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "originals", "RocketBoy.kicad_pcb.orig")
OUT = os.path.join(ROOT, "RocketBoy", "RocketBoy.kicad_pcb")

rng = random.Random(20261031)


def new_uuid():
    return str(uuid.UUID(int=rng.getrandbits(128), version=4))


# ------------------------------------------------------------------ board frame
CX, CY = 210.0, 148.5          # board centre on the A3 sheet (chassis centre)
BW, BH = 155.0, 208.0          # board size (155 wide: stays clear of the motor rear bosses at |x| = 77.7)
CORNER_R = 4.0
CLR = 0.25                      # clearance used while routing (rule in .kicad_pro = 0.2)


def A(x, y):
    return (round(CX + x, 4), round(CY + y, 4))


# ------------------------------------------------------------------ nets
class Nets:
    def __init__(self):
        self.names = [""]

    def id(self, name):
        if name is None:
            return 0
        if name not in self.names:
            self.names.append(name)
        return self.names.index(name)


N = Nets()

# ------------------------------------------------------------------ helpers for text blocks

def balanced(text, start):
    """Return end index (exclusive) of the s-expression starting at text[start] == '('."""
    depth, i, instr = 0, start, False
    while i < len(text):
        c = text[i]
        if instr:
            if c == "\\":
                i += 1
            elif c == '"':
                instr = False
        else:
            if c == '"':
                instr = True
            elif c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    return i + 1
        i += 1
    raise ValueError("unbalanced")


def blocks(text, head):
    out, pos = [], 0
    while True:
        i = text.find("(" + head, pos)
        if i < 0:
            return out
        # make sure it is a real token start (followed by space/newline/quote)
        j = balanced(text, i)
        out.append((i, j, text[i:j]))
        pos = j


orig = open(SRC).read()
fp_blocks = {}
for i, j, b in blocks(orig, "footprint "):
    ref = re.search(r'\(property "Reference" "([^"]+)"', b).group(1)
    fp_blocks[ref] = b

# ------------------------------------------------------------------ module pin tables
LEFT = [("1", 2.54, "VM"), ("2", 5.08, "VCC"), ("3", 7.62, "GND"), ("4", 10.16, "AO1"),
        ("5", 12.70, "AO2"), ("6", 15.24, "BO1"), ("7", 17.78, "BO2"), ("8", 20.32, "GND")]
RIGHT = [("9", 2.54, "PWMA"), ("10", 5.08, "AIN2"), ("11", 7.62, "AIN1"), ("12", 10.16, "STBY"),
         ("13", 12.70, "BIN1"), ("14", 15.24, "BIN2"), ("15", 17.78, "PWMB"), ("16", 20.32, "GND")]
PIN_NET = {"VM": "VBAT", "VCC": "VCCQ", "GND": "GND", "AO1": "/LmA", "AO2": "/LmB", "BO1": "/RmA",
           "BO2": "/RmB", "PWMA": "/PWMA", "AIN1": "/AIN1", "AIN2": "/AIN2", "PWMB": "/PWMB",
           "BIN1": "/BIN1", "BIN2": "/BIN2"}
LOGIC_ORDER = ["/PWMA", "/AIN1", "/AIN2", "/PWMB", "/BIN2", "/BIN1"]     # west -> east lane order
PAD_D = 1.905

# ------------------------------------------------------------------ layout numbers (board frame)
PITCH_X = 46.5
XS = [-51.34, -51.34 + PITCH_X, -51.34 + 2 * PITCH_X]
YS = [-90.0, -63.0, -36.0]
POWER_LANES = [("VBAT", 3.0, 1.5), ("GND", 3.0, 1.2), ("/LmA", 2.0, 1.2), ("/LmB", 2.0, 1.2),
               ("/RmA", 2.0, 1.2), ("/RmB", 2.0, 1.2), ("VCCQ", 0.6, 0.4)]   # (net, lane width, stub width)

# channel (trunk) stack, y centres and widths
TR = {
    "/BIN1": (-9.6, 0.3), "/BIN2": (-8.4, 0.3), "/PWMB": (-7.2, 0.3), "/AIN2": (-6.0, 0.3),
    "/AIN1": (-4.8, 0.3), "/PWMA": (-3.6, 0.3),
    "VCCQ": (-2.0, 0.8),
    "/LmA": (0.95, 3.5), "/LmB": (6.03, 3.5), "/RmA": (10.35, 3.5), "/RmB": (15.43, 3.5),
    "VBAT": (20.5, 5.0),
}
TERM_X = 72.5            # x of the terminal blocks (mirrored for the west side)
SW_Y = -97.0
ESP_XP = 40.0            # x of the ESP west pin column (control pins)
ESP_YE = 98.0            # ESP origin y (rot 180 -> pads at y = ESP_YE - py)

board = Board()
board.outline = (-BW / 2, -BH / 2, BW / 2, BH / 2, CORNER_R)

emit_fp = []       # text blocks of footprints
emit_trk = []      # text of segments / vias
fp_libs = {}       # name -> kicad_mod text (for RocketBoy.pretty)


def seg_text(layer, net, width, p, q):
    a, b = A(*p), A(*q)
    return ("\t(segment\n\t\t(start %.4f %.4f)\n\t\t(end %.4f %.4f)\n\t\t(width %.3f)\n\t\t(layer \"%s\")\n"
            "\t\t(net %d)\n\t\t(uuid \"%s\")\n\t)\n" % (a[0], a[1], b[0], b[1], width, layer, N.id(net), new_uuid()))


def via_text(x, y, net, dia, drill):
    a = A(x, y)
    return ("\t(via\n\t\t(at %.4f %.4f)\n\t\t(size %.3f)\n\t\t(drill %.3f)\n\t\t(layers \"F.Cu\" \"B.Cu\")\n"
            "\t\t(net %d)\n\t\t(uuid \"%s\")\n\t)\n" % (a[0], a[1], dia, drill, N.id(net), new_uuid()))


def trk(layer, net, width, *pts):
    pts = [tuple(p) for p in pts]
    # drop zero-length / duplicate points
    clean = [pts[0]]
    for p in pts[1:]:
        if abs(p[0] - clean[-1][0]) > 1e-6 or abs(p[1] - clean[-1][1]) > 1e-6:
            clean.append(p)
    if len(clean) < 2:
        return
    board.track(layer, net, width, *clean)
    for p, q in zip(clean, clean[1:]):
        emit_trk.append(seg_text(layer, net, width, p, q))


def via(x, y, net, dia=0.8, drill=0.4):
    board.via(x, y, net, dia, drill)
    emit_trk.append(via_text(x, y, net, dia, drill))


# ------------------------------------------------------------------ existing footprints (re-placed)

def retarget_block(b, x, y, rot, padnet):
    """Move a footprint block, optionally rotate it, and re-assign pad nets.
    padnet: {padnumber: netname or None} (missing numbers keep their original net name)."""
    ax, ay = A(x, y)
    at = "(at %.4f %.4f%s)" % (ax, ay, (" %g" % rot) if rot else "")
    # footprint-level (at ...) is the first one on its own line at depth 2 tabs
    b = re.sub(r"\n\t\t\(at [^)]*\)", "\n\t\t" + at, b, count=1)
    out, pos = [], 0
    for i, j, pb in blocks(b, "pad "):
        num = re.match(r'\(pad "([^"]*)"', pb).group(1)
        m = re.search(r'\n\t\t\t\(net (\d+) "([^"]*)"\)', pb)
        oldname = m.group(2) if m else None
        if num in padnet:
            name = padnet[num]
        else:
            name = oldname
        if name is None:
            pb2 = re.sub(r'\n\t\t\t\(net \d+ "[^"]*"\)', "", pb)
        else:
            nid = N.id(name)
            if m:
                pb2 = re.sub(r'\(net \d+ "[^"]*"\)', '(net %d "%s")' % (nid, name), pb, count=1)
            else:
                pb2 = pb.replace("\n\t\t\t(pinfunction", '\n\t\t\t(net %d "%s")\n\t\t\t(pinfunction' % (nid, name), 1)
        if rot and ' circle' not in pb2.split("\n")[0]:
            pass
        out.append((i, j, pb2))
    res, last = [], 0
    for i, j, pb2 in out:
        res.append(b[last:i])
        res.append(pb2)
        last = j
    res.append(b[last:])
    return "".join(res)


def pads_from_block(b, ref, x, y, rot):
    """Parse pad geometry of an original block -> pcbmodel Pads (absolute board-frame coords)."""
    t = parse(b)
    pads = []
    for pd in find(t, "pad"):
        num = val(pd[1])
        at = first(pd, "at")
        px, py = float(at[1]), float(at[2])
        rx, ry = rot_pt(px, py, rot)
        size = first(pd, "size")
        net = first(pd, "net")
        pads.append(Pad("%s.%s" % (ref, num), num, val(net[2]) if net else None, x + rx, y + ry, "circle",
                        float(size[1]), float(size[2]), float(first(pd, "drill")[1])))
    return pads


module_pos = {}
for k in range(1, 10):
    c, r = (k - 1) // 3, (k - 1) % 3
    module_pos["U%d" % k] = (XS[c], YS[r], c, r)

lane_x = {}          # lane_x[c][net] -> centre x of the lane in the west (power) region of column c
for c in range(3):
    lane_x[c] = {}
    edge = XS[c] + 1.59 - 1.6
    for net, w, sw in POWER_LANES:
        lane_x[c][net] = edge - w / 2
        edge -= w + 0.5


def east_x(c, net):
    base = XS[c] + 17.46 + 1.6
    if net in LOGIC_ORDER:
        return base + LOGIC_ORDER.index(net) * 1.0
    if net.startswith("/STBY"):
        return base + 6.0
    if net == "GND":
        return base + 7.6
    raise KeyError(net)


for ref, (mx, my, c, r) in module_pos.items():
    group = c + 1
    padnet = {}
    for num, off, pin in LEFT + RIGHT:
        padnet[num] = ("/STBY%d" % group) if pin == "STBY" else PIN_NET[pin]
    emit_fp.append(retarget_block(fp_blocks[ref], mx, my, 0, padnet))
    for p in pads_from_block(emit_fp[-1], ref, mx, my, 0):
        # pads_from_block parsed absolute coords already shifted twice -> rebuild from original geometry
        pass
    # rebuild pads directly (relative geometry is known)
    for num, off, pin in LEFT:
        board.pads.append(Pad("%s.%s" % (ref, num), num, padnet[num], mx + 2.54, my + off, "circle", PAD_D, PAD_D, 1.0))
    for num, off, pin in RIGHT:
        board.pads.append(Pad("%s.%s" % (ref, num), num, padnet[num], mx + 16.51, my + off, "circle", PAD_D, PAD_D, 1.0))

# ------------------------------------------------------------------ routing: module stubs, lanes
first_y = {}     # (c, net) -> first (top-most) via y for the lane
last_y = {}
for ref, (mx, my, c, r) in module_pos.items():
    group = c + 1
    # left row: stub west on F.Cu -> via -> B.Cu lane
    for num, off, pin in LEFT:
        net = PIN_NET[pin]
        lx = lane_x[c][net]
        sw = {n: s for n, w, s in POWER_LANES}[net]
        px, py = mx + 2.54, my + off
        if net == "VBAT":
            trk("F.Cu", net, sw, (px, py), (lx, py), (lx, py - 1.45))
            via(lx, py, net, 1.2, 0.6)
            via(lx, py - 1.45, net, 1.2, 0.6)
            first_y[(c, net)] = min(first_y.get((c, net), 1e9), py - 1.45)
        else:
            trk("F.Cu", net, sw, (px, py), (lx, py))
            if net == "VCCQ":
                via(lx, py, net, 0.8, 0.4)
            else:
                via(lx, py, net, 1.2, 0.6)
            first_y[(c, net)] = min(first_y.get((c, net), 1e9), py)
    # right row
    for num, off, pin in RIGHT:
        net = "/STBY%d" % group if pin == "STBY" else PIN_NET[pin]
        px, py = mx + 16.51, my + off
        if pin == "GND":
            lx = east_x(c, "GND")
            trk("F.Cu", net, 0.8, (px, py), (lx, py))
            via(lx, py, net, 1.2, 0.6)
        else:
            lx = east_x(c, net)
            trk("F.Cu", net, 0.3, (px, py), (lx, py))
            via(lx, py, net, 0.8, 0.4)
        first_y[(c, ("E", net))] = min(first_y.get((c, ("E", net)), 1e9), py)
        last_y[(c, ("E", net))] = max(last_y.get((c, ("E", net)), -1e9), py)

GND_END = -11.5     # west/east GND lanes stop here and merge into the B.Cu pour

# west (power) lanes
for c in range(3):
    for net, w, sw in POWER_LANES:
        x = lane_x[c][net]
        y0 = first_y[(c, net)]
        if net == "GND":
            trk("B.Cu", net, w, (x, y0), (x, GND_END))
        elif net == "VCCQ":
            # tops of the VCCQ lanes also feed the group switches -> go up to the switch row
            trk("B.Cu", net, w, (x, SW_Y), (x, y0))
            trk("B.Cu", net, w, (x, y0), (x, TR[net][0]))
            via(x, SW_Y, net, 0.8, 0.4)
            via(x, TR[net][0], net, 0.8, 0.4)
        else:
            ytr = TR[net][0]
            trk("B.Cu", net, w, (x, y0), (x, ytr))
            via(x, ytr, net, 1.2, 0.6)
            if net == "VBAT":
                via(x, ytr + 1.4, net, 1.2, 0.6)
                via(x, ytr - 1.4, net, 1.2, 0.6)

# east (logic) lanes
ESP_PADY = {}
for pad_num, py_ in [("24", 12.70), ("26", 17.78), ("27", 20.32), ("28", 22.86), ("29", 25.40), ("30", 27.94)]:
    ESP_PADY[pad_num] = ESP_YE - py_
ESP_CTRL = {"/PWMA": "24", "/AIN1": "26", "/AIN2": "27", "/PWMB": "28", "/BIN2": "29", "/BIN1": "30"}

for c in range(3):
    for net in LOGIC_ORDER:
        x = east_x(c, net)
        y0 = first_y[(c, ("E", net))]
        ytr = TR[net][0]
        if c == 1:
            yend = ESP_PADY[ESP_CTRL[net]]
            trk("B.Cu", net, 0.3, (x, y0), (x, yend))
        else:
            trk("B.Cu", net, 0.3, (x, y0), (x, ytr))
        via(x, ytr, net, 0.8, 0.4)
    # GND east lane
    x = east_x(c, "GND")
    trk("B.Cu", "GND", 1.5, (x, first_y[(c, ("E", "GND"))]), (x, GND_END))
    # STBY lane up to the switch
    sn = "/STBY%d" % (c + 1)
    x = east_x(c, sn)
    trk("B.Cu", sn, 0.3, (x, SW_Y), (x, last_y[(c, ("E", sn))]))

# trunks (F.Cu) for logic nets: gap1 .. gap3 lanes
for net in LOGIC_ORDER:
    ytr, w = TR[net]
    xs = [east_x(c, net) for c in range(3)]
    trk("F.Cu", net, w, (xs[0], ytr), (xs[2], ytr))

# VCCQ trunk: from col1 VCCQ lane to ESP corridor x
VCC_CORR_X = 42.5
ytr, w = TR["VCCQ"]
trk("F.Cu", "VCCQ", w, (lane_x[0]["VCCQ"], ytr), (VCC_CORR_X, ytr))
for c in range(3):
    pass
via(VCC_CORR_X, ytr, "VCCQ", 0.8, 0.4)

# power trunks (F.Cu)
for net in ["/LmA", "/LmB"]:
    ytr, w = TR[net]
    xs = [lane_x[c][net] for c in range(3)]
    trk("F.Cu", net, w, (-TERM_X, ytr), (xs[2], ytr))
for net in ["/RmA", "/RmB"]:
    ytr, w = TR[net]
    xs = [lane_x[c][net] for c in range(3)]
    trk("F.Cu", net, w, (xs[0], ytr), (TERM_X, ytr))
ytr, w = TR["VBAT"]
trk("F.Cu", "VBAT", w, (-TERM_X, ytr), (lane_x[2]["VBAT"], ytr))

# ------------------------------------------------------------------ new footprint generators
FPW = []   # (ref, libname, kicad_mod) for the .pretty folder


def fmt_pad(num, shape, x, y, w, h, drill, net, pinfunc, rotation=0, ptype="passive"):
    ang = (" %g" % rotation) if (rotation and shape != "circle") else ""
    nets = ('\n\t\t\t(net %d "%s")' % (N.id(net), net)) if net else ""
    d = "\n\t\t\t(drill %g)" % drill if drill else ""
    t = "thru_hole" if drill else "smd"
    layers = '"*.Cu" "*.Mask"' if drill else '"F.Cu" "F.Mask" "F.Paste"'
    return ('\t\t(pad "%s" %s %s\n\t\t\t(at %.4f %.4f%s)\n\t\t\t(size %.3f %.3f)%s\n\t\t\t(layers %s)\n'
            '\t\t\t(remove_unused_layers no)%s\n\t\t\t(pinfunction "%s")\n\t\t\t(pintype "%s")\n\t\t\t(uuid "%s")\n\t\t)\n'
            % (num, t, shape, x, y, ang, w, h, d, layers, nets, pinfunc, ptype, new_uuid()))


def fmt_line(x1, y1, x2, y2, layer="F.SilkS", w=0.12):
    return ('\t\t(fp_line\n\t\t\t(start %.3f %.3f)\n\t\t\t(end %.3f %.3f)\n\t\t\t(stroke\n\t\t\t\t(width %g)\n\t\t\t\t(type default)\n\t\t\t)\n'
            '\t\t\t(layer "%s")\n\t\t\t(uuid "%s")\n\t\t)\n' % (x1, y1, x2, y2, w, layer, new_uuid()))


def fmt_rect(x1, y1, x2, y2, layer="F.SilkS", w=0.12):
    return ('\t\t(fp_rect\n\t\t\t(start %.3f %.3f)\n\t\t\t(end %.3f %.3f)\n\t\t\t(stroke\n\t\t\t\t(width %g)\n\t\t\t\t(type default)\n\t\t\t)\n'
            '\t\t\t(fill no)\n\t\t\t(layer "%s")\n\t\t\t(uuid "%s")\n\t\t)\n' % (x1, y1, x2, y2, w, layer, new_uuid()))


def fmt_circle(cx, cy, r, layer="F.SilkS", w=0.12):
    return ('\t\t(fp_circle\n\t\t\t(center %.3f %.3f)\n\t\t\t(end %.3f %.3f)\n\t\t\t(stroke\n\t\t\t\t(width %g)\n\t\t\t\t(type default)\n\t\t\t)\n'
            '\t\t\t(fill no)\n\t\t\t(layer "%s")\n\t\t\t(uuid "%s")\n\t\t)\n' % (cx, cy, cx + r, cy, w, layer, new_uuid()))


def prop(name, value, x, y, layer, hide=False, size=1.0):
    return ('\t\t(property "%s" "%s"\n\t\t\t(at %.3f %.3f 0)\n\t\t\t(unlocked yes)\n\t\t\t(layer "%s")\n%s'
            '\t\t\t(uuid "%s")\n\t\t\t(effects\n\t\t\t\t(font\n\t\t\t\t\t(size %g %g)\n\t\t\t\t\t(thickness 0.15)\n\t\t\t\t)\n\t\t\t)\n\t\t)\n'
            % (name, value, x, y, layer, "\t\t\t(hide yes)\n" if hide else "", new_uuid(), size, size))


class FPDef:
    """Geometry of a custom footprint in footprint-local coordinates."""
    def __init__(self, lib, pads, gfx, ref_at=(0, -3), val_at=(0, 3), smd=False, descr=""):
        self.lib, self.pads, self.gfx, self.ref_at, self.val_at, self.smd, self.descr = lib, pads, gfx, ref_at, val_at, smd, descr


def hdr_def(lib, n, pitch=2.54):
    pads = []
    for i in range(n):
        pads.append((str(i + 1), "rect" if i == 0 else "circle", 0.0, i * pitch, 1.7, 1.7, 1.0))
    gfx = [("rect", -1.33, -1.33, 1.33, (n - 1) * pitch + 1.33)]
    return FPDef(lib, pads, gfx, ref_at=(-3.2, (n - 1) * pitch / 2), val_at=(3.4, (n - 1) * pitch / 2),
                 descr="Pin header 1x%d, 2.54 mm pitch" % n)


FPDEFS = {
    P.FP_TERM: FPDef(P.FP_TERM,
                     [("1", "rect", 0.0, 0.0, 3.2, 3.2, 1.6), ("2", "circle", 0.0, 5.08, 3.2, 3.2, 1.6)],
                     [("rect", -4.0, -3.2, 4.0, 8.28)], ref_at=(-6.2, 2.54), val_at=(6.0, 2.54),
                     descr="2-pole 5.08 mm screw terminal (KF301-5.0-2P style), pin 1 at origin, pin 2 +5.08 mm in Y"),
    P.FP_SW: FPDef(P.FP_SW,
                   [("1", "rect", -2.54, 0.0, 1.8, 1.8, 1.0), ("2", "circle", 0.0, 0.0, 1.8, 1.8, 1.0),
                    ("3", "circle", 2.54, 0.0, 1.8, 1.8, 1.0)],
                   [("rect", -4.5, -2.2, 4.5, 2.2)], ref_at=(0, -3.8), val_at=(0, 3.8),
                   descr="SPDT slide switch (SS12D00 / SS-12D / 3-pin toggle), 3 x 2.54 mm in line"),
    P.FP_CAP: FPDef(P.FP_CAP,
                    [("1", "rect", -2.5, 0.0, 2.0, 2.0, 1.0), ("2", "circle", 2.5, 0.0, 2.0, 2.0, 1.0)],
                    [("circle", 0.0, 0.0, 5.25)], ref_at=(0, -6.8), val_at=(0, 6.8),
                    descr="Radial electrolytic D10 mm, 5.0 mm pitch, pin 1 = +"),
    P.FP_HDR2: hdr_def(P.FP_HDR2, 2),
    P.FP_HDR10: hdr_def(P.FP_HDR10, 10),
    P.FP_HOLE: FPDef(P.FP_HOLE, [("", "np", 0.0, 0.0, 3.2, 3.2, 3.2)], [("circle", 0.0, 0.0, 3.6)], ref_at=(0, -5.2), val_at=(0, 5.2),
                     descr="M3 mounting hole, 3.2 mm drill"),
}

PLACE = {}   # ref -> (x, y, rot)


def place_part(ref, x, y, rot=0):
    PLACE[ref] = (x, y, rot)


def emit_custom(ref):
    part = P.PARTS[ref]
    d = FPDEFS[part["fp"]]
    x, y, rot = PLACE[ref]
    ax, ay = A(x, y)
    pin_net = {n: net for n, nm, net in part["pins"]}
    pin_name = {n: nm for n, nm, net in part["pins"]}
    body = ""
    for num, shape, px, py, w, h, drill in d.pads:
        rx, ry = rot_pt(px, py, rot)
        net = pin_net.get(num)
        if shape == "np":
            body += ('\t\t(pad "" np_thru_hole circle\n\t\t\t(at %.4f %.4f)\n\t\t\t(size %.3f %.3f)\n\t\t\t(drill %.3f)\n'
                     '\t\t\t(layers "*.Cu" "*.Mask")\n\t\t\t(uuid "%s")\n\t\t)\n' % (px, py, w, h, drill, new_uuid()))
            board.holes.append((x + rx, y + ry, drill))
        else:
            body += fmt_pad(num, shape, px, py, w, h, drill, net, pin_name.get(num, num), rotation=rot)
            ww, hh = (h, w) if int(round(rot)) % 180 == 90 else (w, h)
            kind = "circle" if shape == "circle" else "rect"
            board.pads.append(Pad("%s.%s" % (ref, num), num, net, x + rx, y + ry, kind, ww, hh, drill))
            board.holes.append((x + rx, y + ry, drill))
    gfx = ""
    for g in d.gfx:
        if g[0] == "rect":
            gfx += fmt_rect(*g[1:])
        elif g[0] == "circle":
            gfx += fmt_circle(*g[1:])
    path = "/" + part["uuid"]
    text = ('\t(footprint "%s"\n\t\t(layer "F.Cu")\n\t\t(uuid "%s")\n\t\t(at %.4f %.4f%s)\n' %
            (d.lib, new_uuid(), ax, ay, (" %g" % rot) if rot else ""))
    text += prop("Reference", ref, d.ref_at[0], d.ref_at[1], "F.SilkS")
    text += prop("Value", part["value"], d.val_at[0], d.val_at[1], "F.Fab")
    text += prop("Datasheet", "", 0, 0, "F.Fab", hide=True)
    text += prop("Description", part["desc"], 0, 0, "F.Fab", hide=True)
    text += '\t\t(path "%s")\n\t\t(sheetname "/")\n\t\t(sheetfile "RocketBoy.kicad_sch")\n' % path
    text += "\t\t(attr through_hole)\n" + gfx + body + "\t\t(embedded_fonts no)\n\t)\n"
    emit_fp.append(text)


# ------------------------------------------------------------------ placement of new parts
# mounting holes
for i, (hx, hy) in enumerate(P.HOLES):
    place_part("H%d" % (i + 1), hx, hy)

# group switches at the front edge, STBY lane enters at the common pin (pin 2)
for g in (1, 2, 3):
    place_part("SW%d" % g, east_x(g - 1, "/STBY%d" % g), SW_Y)

# terminals: battery (west, below the VM trunk) uses the user's BT1 symbol; motors use U11/U12
# (re-targeted to the terminal-block footprint)
TERM = {"BT1": (-TERM_X, TR["VBAT"][0]), "U11": (-TERM_X, TR["/LmA"][0]), "U12": (TERM_X, TR["/RmA"][0])}

# bulk capacitors under the VM trunk
CAP_X = [-58.0, -28.0, 2.0]
CAP_Y = 33.0
for i, cx_ in enumerate(CAP_X):
    place_part("C%d" % (i + 1), cx_, CAP_Y)

# buck module headers
place_part("J1", -66.0, 31.0)       # BUCK_IN  (VBAT, GND)
place_part("J2", 28.0, 95.46)       # BUCK_OUT (+5V, GND)
# expansion header for a second PCB: pin rows are aligned with the ESP32 control-pad rows
EXP_X = 6.0
EXP_Y0 = ESP_YE - 35.56            # pin 1 at 62.44; pins 4..10 land on the BIN1..PWMA rows of the ESP32
place_part("J3", EXP_X, EXP_Y0)

for ref in sorted(PLACE):
    emit_custom(ref)

# ------------------------------------------------------------------ user's terminal footprints (BT1/U11/U12)
term_pins = {"BT1": [("1", "VBAT"), ("2", "GND")], "U11": [("1", "/LmA"), ("2", "/LmB")], "U12": [("1", "/RmA"), ("2", "/RmB")]}
for ref, (tx, ty) in TERM.items():
    b = fp_blocks[ref]
    # swap library reference to the new terminal-block footprint and rebuild its pads
    ax, ay = A(tx, ty)
    # keep the original header/properties, replace pads + footprint name
    head = b[:b.index("\t\t(pad ")]
    head = re.sub(r'\(footprint "[^"]*"', '(footprint "%s"' % P.FP_TERM, head, count=1)
    head = re.sub(r"\n\t\t\(at [^)]*\)", "\n\t\t(at %.4f %.4f)" % (ax, ay), head, count=1)
    head = head.replace("(attr smd)", "(attr through_hole)")
    pin_names = {"BT1": ("+", "-"), "U11": ("IN1", "IN2"), "U12": ("IN1", "IN2")}[ref]
    pads_txt = ""
    for (num, net), nm in zip(term_pins[ref], pin_names):
        shape = "rect" if num == "1" else "circle"
        py = 0.0 if num == "1" else 5.08
        pads_txt += fmt_pad(num, shape, 0.0, py, 3.2, 3.2, 1.6, net, nm)
        board.pads.append(Pad("%s.%s" % (ref, num), num, net, tx, ty + py, "circle" if shape == "circle" else "rect", 3.2, 3.2, 1.6))
        board.holes.append((tx, ty + py, 1.6))
    gfx = fmt_rect(-4.0, -3.2, 4.0, 8.28)
    emit_fp.append(head + gfx + pads_txt + "\t\t(embedded_fonts no)\n\t)\n")
    # fix value text for readability
# terminal VBAT/GND/motor connections
# BT1: pad1 VBAT at the VM trunk end (x=-72.5,y=20.5); pad2 GND directly below -> pour
# motor terminals: pad1/pad2 sit on the 5.08 mm pitched trunks
# BT1 pad2 GND: stub to a via into the B.Cu pour
bx, by = TERM["BT1"]
via(bx + 3.0, by + 5.08, "GND", 1.2, 0.6)
trk("F.Cu", "GND", 1.5, (bx, by + 5.08), (bx + 3.0, by + 5.08))
# motor terminal pad 2 connects to the second trunk: trunks end exactly at pad centres
trk("F.Cu", "/LmB", 3.5, (-TERM_X, TR["/LmB"][0]), (-TERM_X, TR["/LmB"][0]))
trk("F.Cu", "/RmB", 3.5, (TERM_X, TR["/RmB"][0]), (TERM_X, TR["/RmB"][0]))
# motor terminals: U12 (right motor) pads at y(RmA)=10.35 and 15.43 -> matches trunks

# ------------------------------------------------------------------ ESP32 (rot 180)
esp = fp_blocks["U10"]
espnet = {}
for num, name in P.ESP_NETS.items():
    espnet[num] = name
ex, ey = ESP_XP + 20.32, ESP_YE      # origin such that west column (orig x=20.32) is at ESP_XP
emit_fp.append(retarget_block(esp, ex, ey, 180, espnet))
espt = parse(emit_fp[-1])
for pd in find(espt, "pad"):
    num = val(pd[1]); at = first(pd, "at"); net = first(pd, "net")
    px, py = float(at[1]), float(at[2])
    rx, ry = rot_pt(px, py, 180)
    nm = val(net[2]) if net else None
    board.pads.append(Pad("U10.%s" % num, num, nm, ex + rx, ey + ry, "circle", PAD_D, PAD_D, 1.0))
    board.holes.append((ex + rx, ey + ry, 1.0))

def esp_pad(num):
    for p in board.pads:
        if p.ref == "U10.%s" % num:
            return p
    raise KeyError(num)

# control stubs (B.Cu) from the west column to the lanes of column 2's logic region
for net, pn in ESP_CTRL.items():
    p = esp_pad(pn)
    trk("B.Cu", net, 0.3, (p.x, p.y), (east_x(1, net), p.y))

# 3V3 -> VCCQ: B.Cu corridor to the VCCQ trunk, F.Cu stub to the IR header
p3 = esp_pad("38")
trk("B.Cu", "VCCQ", 0.5, (p3.x, p3.y), (VCC_CORR_X, p3.y - 2.5), (VCC_CORR_X, TR["VCCQ"][0]))

# ESP GND pad 25 (west column, between PWMA / AIN1 stubs): F.Cu stub into the interior + via -> B.Cu pour
p25 = esp_pad("25")
trk("F.Cu", "GND", 0.5, (p25.x, p25.y), (p25.x + 5.0, p25.y))
via(p25.x + 5.0, p25.y, "GND", 0.8, 0.4)

# ------------------------------------------------------------------ expansion header wiring
j3 = {q.num: q for q in board.pads if q.ref.startswith("J3.")}
# control pins: F.Cu from the header pin east to a via on the (B.Cu) logic lane of column 2 at the same y
for pin, net in (("4", "/BIN1"), ("5", "/BIN2"), ("6", "/PWMB"), ("7", "/AIN2"), ("8", "/AIN1"), ("10", "/PWMA")):
    hp = j3[pin]
    lx = east_x(1, net)
    assert abs(hp.y - esp_pad(ESP_CTRL[net]).y) < 1e-6, (pin, hp.y)
    trk("F.Cu", net, 0.3, (hp.x, hp.y), (lx, hp.y))
    via(lx, hp.y, net, 0.8, 0.4)
# 3V3 from the ESP32 3V3 pad to header pin 2
trk("F.Cu", "VCCQ", 0.4, (p3.x, p3.y), (p3.x - 4.0, p3.y), (p3.x - 4.0, j3["2"].y), (j3["2"].x, j3["2"].y))

# ------------------------------------------------------------------ 5 V
j2 = {q.num: q for q in board.pads if q.ref.startswith("J2.")}
p20 = esp_pad("20")
trk("F.Cu", "+5V", 1.0, (j2["1"].x, j2["1"].y), (p20.x, p20.y))
j3p1 = [q for q in board.pads if q.ref == "J3.1"][0]
trk("F.Cu", "+5V", 1.0, (j2["1"].x, j2["1"].y), (EXP_X - 3.5, j2["1"].y), (EXP_X - 3.5, j3p1.y), (j3p1.x, j3p1.y))

# ------------------------------------------------------------------ buck-in feed from the VBAT trunk
j1 = {q.num: q for q in board.pads if q.ref.startswith("J1.")}
trk("F.Cu", "VBAT", 1.5, (j1["1"].x, TR["VBAT"][0]), (j1["1"].x, j1["1"].y))

# ------------------------------------------------------------------ bulk caps on VBAT trunk
for i in range(3):
    cp = {q.num: q for q in board.pads if q.ref == "C%d.%s" % (i + 1, "1")}
    p1 = [q for q in board.pads if q.ref == "C%d.1" % (i + 1)][0]
    trk("F.Cu", "VBAT", 2.0, (p1.x, p1.y), (p1.x, TR["VBAT"][0]))

# ------------------------------------------------------------------ switch wiring (VCCQ to pin 1)
for g, srcc in ((1, 0), (2, 1), (3, 2)):
    p1 = [q for q in board.pads if q.ref == "SW%d.1" % g][0]
    xl = lane_x[srcc]["VCCQ"]
    trk("F.Cu", "VCCQ", 0.4, (xl, SW_Y), (p1.x, p1.y))
    # the lane feeding pin 1 of switch g also exists as B.Cu lane of column srcc

# ------------------------------------------------------------------ done placing -> preview + checks



# ------------------------------------------------------------------ footprint library (.pretty) + board file

def mod_text(lib):
    d = FPDEFS[lib]
    name = lib.split(":")[1]
    t = ('(footprint "%s"\n\t(version 20241229)\n\t(generator "pcbnew")\n\t(generator_version "9.0")\n\t(layer "F.Cu")\n'
         '\t(descr "%s")\n' % (name, d.descr))
    def p2(nm, v, x, y, lay, hide=False):
        return ('\t(property "%s" "%s"\n\t\t(at %.3f %.3f 0)\n\t\t(layer "%s")\n%s\t\t(uuid "%s")\n\t\t(effects\n\t\t\t(font\n'
                '\t\t\t\t(size 1 1)\n\t\t\t\t(thickness 0.15)\n\t\t\t)\n\t\t)\n\t)\n' % (nm, v, x, y, lay, "\t\t(hide yes)\n" if hide else "", new_uuid()))
    t += p2("Reference", "REF**", d.ref_at[0], d.ref_at[1], "F.SilkS")
    t += p2("Value", name, d.val_at[0], d.val_at[1], "F.Fab")
    t += p2("Datasheet", "", 0, 0, "F.Fab", True)
    t += p2("Description", d.descr, 0, 0, "F.Fab", True)
    t += "\t(attr through_hole)\n"
    body = ""
    for num, shape, px, py, w, h, drill in d.pads:
        if shape == "np":
            body += ('\t(pad "" np_thru_hole circle\n\t\t(at %.3f %.3f)\n\t\t(size %.3f %.3f)\n\t\t(drill %.3f)\n'
                     '\t\t(layers "*.Cu" "*.Mask")\n\t\t(uuid "%s")\n\t)\n' % (px, py, w, h, drill, new_uuid()))
        else:
            body += ('\t(pad "%s" thru_hole %s\n\t\t(at %.3f %.3f)\n\t\t(size %.3f %.3f)\n\t\t(drill %g)\n\t\t(layers "*.Cu" "*.Mask")\n'
                     '\t\t(remove_unused_layers no)\n\t\t(uuid "%s")\n\t)\n' % (num, shape, px, py, w, h, drill, new_uuid()))
    gfx = ""
    for g in d.gfx:
        if g[0] == "rect":
            gfx += ('\t(fp_rect\n\t\t(start %.3f %.3f)\n\t\t(end %.3f %.3f)\n\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type default)\n\t\t)\n'
                    '\t\t(fill no)\n\t\t(layer "F.SilkS")\n\t\t(uuid "%s")\n\t)\n' % (g[1], g[2], g[3], g[4], new_uuid()))
        else:
            gfx += ('\t(fp_circle\n\t\t(center %.3f %.3f)\n\t\t(end %.3f %.3f)\n\t\t(stroke\n\t\t\t(width 0.12)\n\t\t\t(type default)\n\t\t)\n'
                    '\t\t(fill no)\n\t\t(layer "F.SilkS")\n\t\t(uuid "%s")\n\t)\n' % (g[1], g[2], g[1] + g[3], g[2], new_uuid()))
    return t + gfx + body + "\t(embedded_fonts no)\n)\n"


def gr_line(p, q, layer="Edge.Cuts", w=0.05):
    a, b = A(*p), A(*q)
    return ('\t(gr_line\n\t\t(start %.4f %.4f)\n\t\t(end %.4f %.4f)\n\t\t(stroke\n\t\t\t(width %g)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(layer "%s")\n\t\t(uuid "%s")\n\t)\n' % (a[0], a[1], b[0], b[1], w, layer, new_uuid()))


def gr_arc(p, m, q, layer="Edge.Cuts", w=0.05):
    a, b, c = A(*p), A(*m), A(*q)
    return ('\t(gr_arc\n\t\t(start %.4f %.4f)\n\t\t(mid %.4f %.4f)\n\t\t(end %.4f %.4f)\n\t\t(stroke\n\t\t\t(width %g)\n\t\t\t(type default)\n\t\t)\n'
            '\t\t(layer "%s")\n\t\t(uuid "%s")\n\t)\n' % (a[0], a[1], b[0], b[1], c[0], c[1], w, layer, new_uuid()))


def gr_text(txt, x, y, size=1.5, layer="F.SilkS", rotation=0, justify="left bottom"):
    a = A(x, y)
    return ('\t(gr_text "%s"\n\t\t(at %.4f %.4f %g)\n\t\t(layer "%s")\n\t\t(uuid "%s")\n\t\t(effects\n\t\t\t(font\n\t\t\t\t(size %g %g)\n'
            '\t\t\t\t(thickness %g)\n\t\t\t)\n\t\t\t(justify %s)\n\t\t)\n\t)\n' % (txt, a[0], a[1], rotation, layer, new_uuid(), size, size, size * 0.15, justify))


def board_graphics():
    x0, y0, x1, y1, r = board.outline
    g = ""
    g += gr_line((x0 + r, y0), (x1 - r, y0)) + gr_line((x1, y0 + r), (x1, y1 - r))
    g += gr_line((x1 - r, y1), (x0 + r, y1)) + gr_line((x0, y1 - r), (x0, y0 + r))
    k = r * (1 - math.sqrt(0.5))
    g += gr_arc((x0, y0 + r), (x0 + k, y0 + k), (x0 + r, y0))
    g += gr_arc((x1 - r, y0), (x1 - k, y0 + k), (x1, y0 + r))
    g += gr_arc((x1, y1 - r), (x1 - k, y1 - k), (x1 - r, y1))
    g += gr_arc((x0 + r, y1), (x0 + k, y1 - k), (x0, y1 - r))
    # silkscreen annotations
    g += gr_text("ROCKETBOY 9x TB6612FNG PARALLEL DRIVER", -38, -99.5, 1.2)
    g += gr_text("FRONT", -5, -102.5, 1.6)
    for gi in (1, 2, 3):
        g += gr_text("GRP%d EN" % gi, east_x(gi - 1, "/STBY%d" % gi) - 4.3, SW_Y - 3.2, 0.9)
    g += gr_text("LEFT MOTOR (OUT A)", -76, -1.5, 0.9)
    g += gr_text("RIGHT MOTOR (OUT B)", 46, 8.5, 0.9)
    g += gr_text("BATTERY 3S (9-12.6V) + / -", -76, 17.2, 0.9)
    g += gr_text("5V BUCK IN", -70, 29.8, 0.8)
    g += gr_text("5V BUCK OUT", 20, 93.5, 0.8)
    g += gr_text("EXPANSION HDR J3 (2ND PCB): 1=5V 2=3V3 3=GND 4=BIN1 5=BIN2 6=PWMB 7=AIN2 8=AIN1 9=GND 10=PWMA", -73, 60.0, 0.8)
    g += gr_text("USB", 49, 102.5, 1.0)
    g += gr_text("2 OZ COPPER RECOMMENDED - FILL ZONES (B) BEFORE PLOT", -60, 102.5, 0.8)
    return g


def zone_text():
    x0, y0, x1, y1, r = board.outline
    inset = 0.3
    pts = [(x0 + inset + 2, y0 + inset), (x1 - inset - 2, y0 + inset), (x1 - inset, y0 + inset + 2), (x1 - inset, y1 - inset - 2),
           (x1 - inset - 2, y1 - inset), (x0 + inset + 2, y1 - inset), (x0 + inset, y1 - inset - 2), (x0 + inset, y0 + inset + 2)]
    xy = "".join("\t\t\t\t(xy %.4f %.4f)\n" % A(*p) for p in pts)
    return ('\t(zone\n\t\t(net %d)\n\t\t(net_name "GND")\n\t\t(layer "B.Cu")\n\t\t(uuid "%s")\n\t\t(hatch edge 0.5)\n'
            '\t\t(connect_pads\n\t\t\t(clearance 0.4)\n\t\t)\n\t\t(min_thickness 0.25)\n\t\t(filled_areas_thickness no)\n'
            '\t\t(fill yes\n\t\t\t(thermal_gap 0.5)\n\t\t\t(thermal_bridge_width 0.6)\n\t\t)\n\t\t(polygon\n\t\t\t(pts\n%s\t\t\t)\n\t\t)\n\t)\n'
            % (N.id("GND"), new_uuid(), xy))


def write_pcb():
    head = orig[:orig.index('\t(net 0 "")')]
    head = head.replace('(paper "A4")', '(paper "A3")')
    body = "".join(emit_fp) + "".join(emit_trk) + zone_text() + board_graphics()
    nets = "".join('\t(net %d "%s")\n' % (i, n) for i, n in enumerate(N.names))
    text = head + nets + body + "\t(embedded_fonts no)\n)\n"
    open(OUT, "w").write(text)
    pretty = os.path.join(ROOT, "RocketBoy", "RocketBoy.pretty")
    os.makedirs(pretty, exist_ok=True)
    for lib in FPDEFS:
        open(os.path.join(pretty, lib.split(":")[1] + ".kicad_mod"), "w").write(mod_text(lib))
    return text


def render(path, scale=6.0, crop=None, show_labels=True):
    x0, y0, x1, y1 = crop if crop else (-BW / 2 - 2, -BH / 2 - 2, BW / 2 + 2, BH / 2 + 2)
    W, H = int((x1 - x0) * scale), int((y1 - y0) * scale)
    cv = Canvas(W, H, (22, 28, 26))
    tx = lambda x: (x - x0) * scale
    ty = lambda y: (y - y0) * scale
    ox0, oy0, ox1, oy1, r = board.outline
    cv.rect(tx(ox0), ty(oy0), tx(ox1), ty(oy1), (34, 48, 40))
    # B.Cu (blue) first, then F.Cu (red)
    for layer, col, a in (("B.Cu", (60, 110, 255), 0.85), ("F.Cu", (235, 70, 60), 0.80)):
        for t in board.tracks:
            if t.layer != layer:
                continue
            for p, q in zip(t.pts, t.pts[1:]):
                cv.line(tx(p[0]), ty(p[1]), tx(q[0]), ty(q[1]), col, t.width * scale, a)
    for v in board.vias:
        cv.circle(tx(v.x), ty(v.y), v.dia / 2 * scale, (230, 230, 120))
        cv.circle(tx(v.x), ty(v.y), v.drill / 2 * scale, (20, 20, 20))
    for p in board.pads:
        if p.kind == "circle":
            cv.circle(tx(p.x), ty(p.y), p.w / 2 * scale, (215, 190, 90))
        else:
            cv.rect(tx(p.x - p.w / 2), ty(p.y - p.h / 2), tx(p.x + p.w / 2), ty(p.y + p.h / 2), (215, 190, 90))
        if p.drill:
            cv.circle(tx(p.x), ty(p.y), p.drill / 2 * scale, (20, 20, 20))
    for (hx, hy) in P.HOLES:
        cv.circle(tx(hx), ty(hy), 1.6 * scale, (10, 10, 10))
        cv.circle(tx(hx), ty(hy), 1.9 * scale, (200, 200, 200), ring=1.2)
    cv.line(tx(ox0 + r), ty(oy0), tx(ox1 - r), ty(oy0), (255, 255, 0), 2)
    cv.line(tx(ox0 + r), ty(oy1), tx(ox1 - r), ty(oy1), (255, 255, 0), 2)
    cv.line(tx(ox0), ty(oy0 + r), tx(ox0), ty(oy1 - r), (255, 255, 0), 2)
    cv.line(tx(ox1), ty(oy0 + r), tx(ox1), ty(oy1 - r), (255, 255, 0), 2)
    if show_labels:
        for ref, (mx, my, c, r_) in module_pos.items():
            cv.text(tx(mx + 4), ty(my + 8.5), ref, (255, 255, 255), 2)
        for ref, (x, y, rot) in PLACE.items():
            cv.text(tx(x) + 4, ty(y) - 14, ref, (255, 255, 255), 1)
        cv.text(tx(-10), ty(-101), "FRONT", (255, 255, 0), 2)
    cv.save(path)


def extra_checks():
    from pcbmodel import pt_seg_dist
    import math as _m
    ox0, oy0, ox1, oy1, r = board.outline
    bad = []
    for s_ in board.all_shapes():
        b = s_.bbox
        if b[0] < ox0 + 0.5 or b[1] < oy0 + 0.5 or b[2] > ox1 - 0.5 or b[3] > oy1 - 0.5:
            bad.append(("edge", s_.ref or s_.tag, b))
    # drills: (x, y, d, net, owner)
    drills = [(p.x, p.y, p.drill, p.net, p.ref) for p in board.pads if p.drill] + [(v.x, v.y, v.drill, v.net, "via") for v in board.vias]
    for (hx, hy, d) in board.holes:
        if d >= 3.0:
            drills.append((hx, hy, d, "NPTH", "hole"))
    for i in range(len(drills)):
        for j in range(i + 1, len(drills)):
            a, b_ = drills[i], drills[j]
            gap = _m.hypot(a[0] - b_[0], a[1] - b_[1]) - a[2] / 2 - b_[2] / 2
            if gap < 0.25 - 1e-6 and not (a[4] == b_[4] and a[4] != "via"):
                bad.append(("hole-hole", a[4], b_[4], round(gap, 3)))
    shapes = board.all_shapes()
    for (hx, hy, d, net, owner) in drills:
        for s_ in shapes:
            if s_.net == net and net not in ("NPTH", None):
                continue
            if s_.ref.startswith(owner + ".") or (s_.ref == owner and owner != "via"):
                continue
            b = s_.bbox
            if hx < b[0] - 1 or hx > b[2] + 1 or hy < b[1] - 1 or hy > b[3] + 1:
                continue
            if s_.kind == "cap":
                dist = pt_seg_dist((hx, hy), s_.g[:2], s_.g[2:4]) - s_.g[4]
            else:
                cx, cy, hw, hh = s_.g
                dist = _m.hypot(max(0.0, abs(hx - cx) - hw), max(0.0, abs(hy - cy) - hh))
            if dist - d / 2 < 0.25 - 1e-6 and not (s_.ref == "via" and owner == "via" and (hx, hy) == tuple(s_.g[:2])):
                bad.append(("hole-copper", owner, s_.ref or s_.tag, s_.net, round(dist - d / 2, 3)))
    return bad

def main():
    errs = check_clearance(board, 0.2)
    print("clearance violations (0.20 mm):", len(errs))
    for e in errs[:60]:
        print("  ", e)
    ex = extra_checks()
    print("edge / drill checks:", len(ex))
    for e in ex[:30]:
        print("  ", e)
    from pcbmodel import pour_check
    sizes, res, unreach = pour_check(board, board.outline)
    main_c = max(sizes, key=lambda k: sizes[k])
    print("pour regions:", len(sizes), "main region cells:", sizes[main_c])
    for c_, items in res.items():
        if c_ != main_c:
            print("  GND items NOT in the main pour region:", items[:12])
    if unreach:
        print("  GND items with no pour contact:", unreach[:12])
    cons = check_connectivity(board, N.names)
    print("nets split into islands (pour-completed nets listed too):", len(cons))
    for n, g in sorted(cons.items()):
        if n == "GND":
            print("   GND islands (completed by B.Cu pour):", len(g))
        else:
            print("  ", n, [x if len(x) < 8 else x[:8] + ["..."] for x in g])


if __name__ == "__main__":
    main()
    text = write_pcb()
    t = parse(text)
    print("wrote", OUT, len(text), "bytes;", len(find(t, "footprint")), "footprints,", len(find(t, "segment")), "segments,", len(find(t, "via")), "vias,", len(find(t, "net")), "nets")
    os.makedirs(os.path.join(HERE, "out"), exist_ok=True)
    render(os.path.join(HERE, "out", "pcb_preview.png"), 5.0)
