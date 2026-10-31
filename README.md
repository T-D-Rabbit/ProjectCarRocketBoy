# RocketBoy – 9 × TB6612FNG parallel motor-driver board, 3D model and simulation

A circular (Ø300 mm) differential-drive robot: two SG-3851218000-60K 12 V gear-motors on L-clamps, two ball casters,
a 3S Molicel pack underneath and this PCB on top with **9 TB6612FNG modules wired in parallel**
(3 × 3 grid, three enable switches), an ESP32 DevKit socket and an **expansion header for a second PCB**.

![robot](model3d/out/preview_iso.png)

```
RocketBoy/            KiCad 9 project (schematic, PCB, project footprint + symbol libraries)
model3d/              3D model generator + outputs (STL, OBJ, interactive HTML viewer, GIF, renders)
simulation/           pure-Python robot + electronics simulation (python3 simulation/run_all.py)
firmware/             Arduino sketch that runs the same hard-coded route on the ESP32
tools/                generators / checkers that produced the KiCad files (see "Reproducing")
docs/                 PCB renders
Chassis file.step, Johnson Motor.pdf, L Clamp.pdf     (inputs, unchanged)
```

## 1. How much current? (the "9 modules – how many amps" question)

| situation (simulated) | current per motor | modules needed |
|---|---|---|
| steady driving, flat, 1.73 m/s | **0.5 A** (just the motor's no-load current) | 1 |
| hard-coded route (square with spins) | mean 0.8 A while moving, peak 2.5 A | 1 group (3 modules = 3.6 A rated) |
| 25° ramp at duty 0.7 | 1.2 A | 1 |
| tyres at the traction limit (≈ 34° slope / wheel spin) | ≈ 1.4 A | 1 |
| **full-duty step from standstill (inrush)** | **6.2 A for ~50 ms** | soft-start the PWM (the route uses 3 duty/s) |
| **motor stalled / pushing a wall** | **5.6 – 5.9 A per motor, ≈ 12 A from the battery for both** | ≥ 2 groups (or stall-detect in firmware) |

For *these* motors one group (3 modules per motor channel, 3.6 A continuous / 9.6 A pulse) is enough for all normal driving;
the 2nd/3rd group (6/9 modules per motor, 7.2/10.8 A continuous) is insurance against stalls and for heavier motors later –
that is what the three STBY switches are for. Details: `simulation/results/summary.md`.

> Stall current/torque are **blank in `Johnson Motor.pdf`** (only 300 rpm no-load, 220 rpm @ 6 kgf·cm, ≤ 600 mA no-load are printed).
> The simulation derives them from that rated point: R = 1.78 Ω, Ke = 0.354 V·s/rad → stall ≈ 6.7 A / 22.5 kgf·cm.
> If you measure the real stall current, edit `simulation/params.py`.

## 2. Mistakes found in the original design and what was changed

| # | original | problem | fix |
|---|---|---|---|
| 1 | ESP32 `5Vin` connected to net `VCC` = battery (9 – 12.6 V) | over-voltages the DevKit regulator / USB 5 V rail | new `+5V` net from an external buck module (`J2` BUCK_OUT, `J1` BUCK_IN); battery net renamed `VBAT` |
| 2 | `STBY` of all modules tied to `VCCQ` | the requested enable switches did not exist – modules were always on | `STBY1…3` per group (= per PCB column: U1-3, U4-6, U7-9); SPDT slide switches `SW1…3` (ON → 3V3, OFF → GND, so STBY is never floating) |
| 3 | ESP32 pad 21 tied to GND | on the 38-pin DevKit that position is `CMD` (GPIO11, flash line) – grounding it can stop the board booting | pad left open (no-connect). The other GND pins (13, 19, 25) remain connected |
| 4 | no board outline, no mounting holes, only a few 0.2 mm tracks | board not finished | outline 155 × 208 mm, 4 × Ø3.2 mm holes at the STEP hole pattern (±75 mm, ±100 mm), everything routed |
| 5 | battery/motor connections on 1.9 mm pads, 0.2 mm routing | cannot carry 6 A+ | 5.08 mm screw terminals, 3 – 5 mm trunks, B.Cu GND pour, 2 oz copper recommended |
| 6 | no bulk capacitance on VM | motor-supply spikes | `C1–C3` 470 µF/25 V on VBAT |
| 7 | no way to attach another controller | – | expansion header `J3` (below) |
| 8 | *(my own earlier mistake)* README/params said the L-clamps sit under the chassis and gave 23.3 mm clearance | the 26.7 mm clamp axis height is measured from the flange face, so with the flange **under** the plate the chassis would be 76 mm off the floor | clamps are on the **top** face (flange on the plate, matches the chassis slot pattern); wheel Ø110 → top face 28.3 mm, underside 25.3 mm above floor (see §4) |

Things I could **not** verify and you should check against your parts:

* **TB6612 module pin order.** The footprint (`pad 6 = BO1, pad 7 = BO2`) was kept. Many breakouts print `AO1 AO2 BO2 BO1` on that row;
  if yours does, only the *right motor polarity* flips (swap the motor wires or `DIR_RIGHT` in the firmware) – all nine modules are identical so nothing shorts.
* **ESP32 DevKit pinout** (pad 21 = CMD above).
* `GPIO12` (AIN1) is the ESP32 flash-voltage strapping pin; it is fine because the TB6612 inputs pull it low, but do not add a pull-up.

### Expansion header `J3` (for the second PCB, replaces the IR header – no IR array on this board any more)

1×10, 2.54 mm: `1 5V · 2 3V3 · 3 GND · 4 BIN1 · 5 BIN2 · 6 PWMB · 7 AIN2 · 8 AIN1 · 9 GND · 10 PWMA`.
The control pins are the same nets as the ESP32 pads (BIN1 = GPIO25, BIN2 = GPIO26, PWMB = GPIO27, AIN2 = GPIO14, AIN1 = GPIO12, PWMA = GPIO13).
Use it either to drive the motors from another board (then **remove the ESP32** so two outputs never fight) or to read the rails.
The 3D model shows it as a tall male header (11.5 mm pins) so a second board can sit on the 40 mm standoff stack.
`STBY` stays on the three slide switches.

## 3. PCB (RocketBoy/RocketBoy.kicad_pcb)

![board](docs/pcb_full.png)

* 2 layers, A3 sheet, **155 × 208 mm** (155 keeps the board clear of the motors' rear bosses at |x| = 77.1 mm), board centre = chassis centre, **front = top edge** (switches at the front edge, USB of the ESP32 at the rear edge).
* **Architecture** – one column of three modules = one enable group:
  * each module pin goes by a short `F.Cu` stub to a via; vertical `B.Cu` "bus lanes" run along the column (VBAT 3 mm, GND 3 mm, four motor-output lanes 2 mm, logic lanes 0.3 mm);
  * at the bottom of the grid the lanes of the three columns are joined by horizontal `F.Cu` trunks (VBAT 5 mm, motor outputs 3.5 mm, logic 0.3 mm) that end at the
    battery / left-motor / right-motor screw terminals (`BT1`, `U11`, `U12`);
  * the six control lines continue down the middle logic lanes to the ESP32 control pins and to `J3`; `B.Cu` carries a GND pour (fill zones with **B** before plotting).
* Current capacity of every power path is checked in `simulation/results/summary.md` (S6, IPC-2221, +10 °C): stall of both motors is only covered with **2 oz copper**.
* Parts added: `SW1–3` (STBY enable), `C1–3`, `J1/J2` (5 V buck module in/out), `J3` (expansion), `H1–H4` (M3).
  Footprints/symbols of these live in `RocketBoy/RocketBoy.pretty` and `RocketBoy.kicad_sym` (registered through `fp-lib-table` / `sym-lib-table`).
  The original `Control_Modules:` and `MCU:` footprints are the ones you already had; the board file is self-contained.
* Buck module and cables are not on the board (`J1` → module IN, module OUT → `J2`). A ≥ 2 A 12→5 V module is plenty.
  Recommended: 15 A inline fuse and a main switch in the battery lead.

Checks that were run (KiCad itself is not available in the build environment, so **please run KiCad's own ERC/DRC once**):

| check | result |
|---|---|
| independent clearance check, all copper, 0.20 mm rule (project rule) | 0 violations |
| every non-GND net electrically connected (pads/tracks/vias) | all connected |
| flood-fill of the B.Cu pour with 0.4 mm clearance | every GND pad/via/lane reaches the main pour region |
| edge clearance ≥ 0.5 mm, drill-to-drill/-copper ≥ 0.25 mm | 0 violations |
| schematic netlist vs PCB netlist (`tools/compare_netlists.py`) | identical (17 nets) |

## 4. Mechanics (what the 3D model is built from)

* `Chassis file.step`: 300 mm × 3 mm disc, PCB holes (±75, ±100), 12 clamp holes at x = ±(130.8 / 136.8 / 142.8), y = ±14.9, caster slots 50 × 3.2 mm at y = ±125.
* `L Clamp.pdf`: 1.5 mm steel, 40 mm wide, flange 22 mm (6 holes, matches the chassis slots, plate at x ≈ 147 mm), plate Ø22 bore + 12 holes on PCD 30.5, **motor axis 26.7 mm above the flange face**.
* `Johnson Motor.pdf`: gearbox Ø37 × 25, can Ø29 × 37.8, rear boss 6.5, front boss 6.3, Ø6 shaft 30 mm.
* Clamps are bolted on the **top** face of the chassis, motors point inwards, wheels outside: the wheel axle is at wheel radius, so the chassis top face is at r − 26.7 mm.
  **Wheel Ø110 × 25 mm (assumed, 6 mm bore)** → top face 28.3 mm, underside **25.3 mm** above the floor: room for the 3 × 18650 pack (≈ 21 mm), buck module and voltage indicator, which hang under the chassis; casters must be 25.3 mm tall (ball caster + spacer).
  Track width 331 mm; the wheel hub sits 4.7 mm inside the 34.8 mm of shaft that protrudes past the clamp plate.
* PCB on four **M3 × 40 mm** standoffs (board underside 68.3 mm above the floor): the motor rear boss (z up to 61 mm, x ≥ 77.1) then passes under/beside the board edge (|x| ≤ 77.5) with no contact.
* Assumed (not in the repo): 110 mm wheel, battery pack/holder, buck module, voltage-indicator board, casters, total mass 2.2 kg – all in `simulation/params.py` / `model3d/build_model.py`.

## 5. 3D model and animation (`model3d/out/`)

| file | what |
|---|---|
| `rocketboy_viewer.html` | **open in any browser** – self-contained interactive 3D model + the simulated route (orbit/zoom, play/pause, speed, follow-cam, iso/top/side/front/underside buttons, live speed / motor-current / battery HUD) |
| `rocketboy_route.gif` | the same animation as a GIF (real time, 15 s) |
| `rocketboy_assembly.stl`, `rocketboy_body.stl`, `rocketboy_wheel_right.stl`, `rocketboy_wheel_left.stl` | binary STL, mm, x = wheel axis, y = forward, z = up, floor at z = 0 |
| `rocketboy.obj` + `.mtl` | coloured OBJ with 3 objects (body / wheel_right / wheel_left) |
| `preview_*.png` | iso, rear, front, side, top and underside renders |

![route](model3d/out/rocketboy_route.gif)

The model is parametric (`model3d/build_model.py`): chassis with its real hole/slot pattern, L-clamps with bore and hole ring, motors, wheels with spokes, casters,
battery + holder, buck module, indicator board, standoffs, the PCB with all populated parts at their **PCB-file positions** (modules, ESP32, terminals, switches, caps, headers).
It is a visual/fit model – not a STEP file – and the chassis outline is rebuilt from the STEP's dimensions, not converted from it.
Rebuild with `python3 model3d/make_outputs.py` (needs `simulation/results/route_30hz.json` from `run_all.py`).

## 6. Simulation (`python3 simulation/run_all.py`, ≈ 5 s, no dependencies)

Electro-mechanical model: 3S Li-ion (OCV curve + 101 mΩ) → TB6612 bank (random ±25 % R_on spread decides how the current shares over the modules) →
DC motors fitted to the datasheet rated point → tanh tyre force model → differential-drive body with slope, rolling resistance, yaw inertia.

| file in `simulation/results/` | content |
|---|---|
| `S1_launch.png` | full-duty launch: speed, motor current, battery voltage (1 vs 3 groups) |
| `S5_route_topview.png`, `S5_route.png`, `S5_route_30hz.csv`, `route_30hz.json` | **hard-coded route** (no sensors): 4 × [drive 2 s at duty 0.6, pause, spin left 0.377 s at ±0.45 (calibrated to 90°), settle], duty slew-limited to 3/s |
| `summary.md` | all tables: launch, stall, hill sweep, spin, route, PCB copper check |

Key outputs: top speed 1.73 m/s, 0 → 1 m/s in 0.20 s, spin 269 °/s. Route: 15.2 s, 7.9 m, ends 69 mm / −3° from where it started (open loop – it drifts; with all 3 groups
enabled the different driver resistance changes the turn rate and the end error is 128 mm), peak 2.5 A, 6.8 mAh, battery ≥ 11.76 V, worst module 1.06 A (≤ 1.2 A rating).
The one real hazard is a **hard PWM step**: ≈ 6 A for ~50 ms (worst module 2.6 A with one group) → keep the slew limit in firmware.

Assumed (all in `simulation/params.py`): mass 2.2 kg, 1:60 gearbox / rotor inertia, wheel, tyre μ 0.8, battery 2.8 Ah/22 mΩ per cell, R_on 0.5 Ω ± 25 %.
The model has no lateral tyre slip, no motor inductance (PWM-averaged) and no thermal model.

## 7. Firmware (`firmware/rocketboy_hardcoded/`)

`rocketboy_hardcoded.ino` runs the same route on the ESP32 (LEDC 20 kHz PWM, same pins as the schematic, same 5 ms control loop and slew limit).
`route.h` is generated by `run_all.py` from the simulated route, so they cannot drift apart. **Not tested on hardware** – lift the wheels off the floor first.

## 8. Reproducing / editing

```
python3 tools/build_pcb.py        # re-routes and rewrites RocketBoy.kicad_pcb (+ .pretty), prints the checks
python3 tools/build_sch.py        # rewrites RocketBoy.kicad_sch from tools/originals/*.orig
python3 tools/compare_netlists.py
python3 simulation/run_all.py     # results + firmware/route.h + route_30hz.json
python3 model3d/make_outputs.py   # STL / OBJ / GIF / HTML viewer
```
`tools/originals/` keeps your untouched files; the generators always start from them. Hand edits made in KiCad afterwards will be overwritten if you re-run the generators,
so treat the generators as the one-time "design completion" step and edit in KiCad from here on.
