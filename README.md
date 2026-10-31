# RocketBoy – 9 × TB6612FNG parallel motor-driver board, chassis fit-check and simulation

A circular (Ø300 mm) differential-drive robot: two SG-3851218000-60K 12 V gear-motors on L-clamps, two ball casters,
3S Molicel pack and IR line array underneath, and this PCB on top with **9 TB6612FNG modules wired in parallel**
(3 × 3 grid, three enable switches) plus an ESP32 DevKit socket.

```
RocketBoy/            KiCad 9 project (schematic, PCB, project footprint + symbol libraries)
simulation/           pure-Python robot + electronics simulation (python3 simulation/run_all.py)
tools/                generators / checkers that produced the files above (see "Reproducing")
docs/                 PCB renders
Chassis file.step, Johnson Motor.pdf, L Clamp.pdf     (inputs, unchanged)
```

## 1. How much current? (the "9 modules – how many amps" question)

| situation (simulated) | current per motor | modules needed |
|---|---|---|
| steady driving, flat, 1.57 m/s | **0.5 A** (just the motor's no-load current) | 1 |
| line-following lap, 0.8 m/s | mean 0.6 A, peaks ≈ 3.3 A (steering/start) | 1 group (3 modules = 3.6 A rated) |
| 25° ramp at duty 0.7 | 1.15 A | 1 |
| tyres at the traction limit (≈ 34° slope / wheel spin) | ≈ 1.3 A | 1 |
| **full-duty step from standstill (inrush)** | **6.2 A for ~50 ms** | soft-start the PWM |
| **motor stalled / pushing a wall** | **5.6 – 5.9 A per motor, 12 A from the battery for both** | ≥ 2 groups (or stall-detect in firmware) |

So for *these* motors one group (3 modules per motor channel, 3.6 A continuous / 9.6 A pulse) is enough for all normal driving;
the 2nd/3rd group (6/9 modules per motor, 7.2/10.8 A continuous) is insurance against stall, and for heavier motors later.
That is exactly what the three STBY switches are for. Details: `simulation/results/summary.md`.

> Stall current/torque are **blank in `Johnson Motor.pdf`** (only 300 rpm no-load, 220 rpm @ 6 kgf·cm, ≤ 600 mA no-load are printed).
> The simulation derives them from that rated point: R = 1.78 Ω, Ke = 0.354 V·s/rad → stall ≈ 6.7 A / 22.5 kgf·cm.
> If you measure the real stall current, edit `simulation/params.py`.

## 2. Mistakes found in the original design and what was changed

| # | original | problem | fix |
|---|---|---|---|
| 1 | ESP32 `5Vin` connected to net `VCC` = battery (9 – 12.6 V) | over-voltages the DevKit regulator / USB 5 V rail | new `+5V` net from an external buck module (`J2` BUCK_OUT, `J1` BUCK_IN); battery net renamed `VBAT` |
| 2 | `STBY` of all modules tied to `VCCQ` | the requested enable switches did not exist – modules were always on | `STBY1…3` per group (= per PCB column: U1-3, U4-6, U7-9); SPDT slide switches `SW1…3` (ON → 3V3, OFF → GND, so STBY is never floating) |
| 3 | ESP32 pad 21 tied to GND | on the 38-pin DevKit that position is `CMD` (GPIO11, flash line) – grounding it can stop the board booting | pad left open (no-connect). The other GND pins (13, 19, 25) remain connected |
| 4 | no board outline, no mounting holes, only a few 0.2 mm tracks | board not finished | outline 158 × 208 mm, 4 × Ø3.2 mm holes at the STEP hole pattern (±75 mm, ±100 mm), everything routed |
| 5 | battery/motor connections on 1.9 mm pads, 0.2 mm routing | cannot carry 6 A+ | 5.08 mm screw terminals, 3 – 5 mm trunks, B.Cu GND pour, 2 oz copper recommended |
| 6 | no bulk capacitance on VM, no IR sensor header | motor-supply spikes; line array unconnected | `C1–C3` 470 µF/25 V on VBAT, `J3` 1×10 IR header wired to ESP32 |

Things I could **not** verify and you should check against your parts:

* **TB6612 module pin order.** The footprint (`pad 6 = BO1, pad 7 = BO2`) was kept. Many breakouts print `AO1 AO2 BO2 BO1` on that row;
  if yours does, only the *right motor polarity* flips (swap the motor wires or invert in firmware) – all nine modules are identical so nothing shorts.
* **ESP32 DevKit pinout** (pad 21 = CMD above) and the **IR array pinout** (`J3`: 1 GND, 2 3V3, 3–10 OUT1–OUT8 – the shop page returned HTTP 403). Outputs are fed from 3V3 so they cannot exceed the ESP32 limit.
  IR1…IR6 → GPIO36, 39, 34, 35, 32, 33 (all ADC1, usable with Wi-Fi on); IR7 → GPIO18, IR8 → GPIO19 (digital only – if your array is analogue remap them or use a mux).
* `GPIO12` (AIN1) is the ESP32 flash-voltage strapping pin; it is fine because the TB6612 inputs pull it low, but do not add a pull-up.

## 3. PCB (RocketBoy/RocketBoy.kicad_pcb)

![board](docs/pcb_full.png)

* 2 layers, A3 sheet, board centre = chassis centre, **front = top edge** (switches at the front edge, USB of the ESP32 at the rear edge).
* **Architecture** – one column of three modules = one enable group:
  * each module pin goes by a short `F.Cu` stub to a via; vertical `B.Cu` "bus lanes" run along the column (VBAT 3 mm, GND 3 mm, four motor-output lanes 2 mm, logic lanes 0.3 mm);
  * at the bottom of the grid the lanes of the three columns are joined by horizontal `F.Cu` trunks (VBAT 5 mm, motor outputs 3.5 mm, logic 0.3 mm) that end at the
    battery / left-motor / right-motor screw terminals (`BT1`, `U11`, `U12`);
  * the six control lines continue down the middle logic lanes to the ESP32 control pins; `B.Cu` carries a GND pour (fill zones with **B** before plotting).
* Current capacity of every power path is checked in `simulation/results/summary.md` (S6, IPC-2221, +10 °C): stall of both motors is only covered with **2 oz copper**.
* Parts added: `SW1–3` (STBY enable), `C1–3`, `J1/J2` (5 V buck module in/out), `J3` (IR array), `H1–H4` (M3).
  Footprints/symbols of these live in `RocketBoy/RocketBoy.pretty` and `RocketBoy.kicad_sym` (registered through `fp-lib-table` / `sym-lib-table`).
  The original `Control_Modules:` and `MCU:` footprints are the ones you already had; the board file is self-contained.
* Buck module and cables are not on the board (`J1` → module IN, module OUT → `J2`). A ≥ 2 A 12→5 V module (e.g. Pololu D24V22F5 / LM2596 type) is plenty.
  Recommended: 15 A inline fuse and a main switch in the battery lead.

Checks that were run (KiCad itself is not available in the build environment, so **please run KiCad's own ERC/DRC once**):

| check | result |
|---|---|
| independent clearance check, all copper, 0.20 mm rule (project rule) | 0 violations |
| every non-GND net electrically connected (pads/tracks/vias) | all connected |
| flood-fill of the B.Cu pour with 0.4 mm clearance | all 19 GND pads/vias/lanes reach the main pour region |
| edge clearance ≥ 0.5 mm, drill-to-drill/-copper ≥ 0.25 mm | 0 violations |
| schematic netlist vs PCB netlist (`tools/compare_netlists.py`) | identical (25 nets) |

## 4. Mechanics used for the simulation

From `Chassis file.step`: 300 mm × 3 mm disc, mounting holes (±75, ±100), motor clamp slots at x = ±(130.8…142.8) y = ±14.9, caster slots at y = ±125.
From `L Clamp.pdf`: flange 22 × 40 mm with 6 holes (matches the chassis slots, plate at x ≈ 147 mm), motor axis **26.7 mm** from the flange face.
Clamps on the underside → axle 26.7 mm below the chassis. Wheel chosen: **Ø100 × 25 mm rubber, 6 mm bore** → 23.3 mm clearance for the battery,
331 mm track, wheel hub sits 4.7 mm inside the 34.8 mm of shaft that protrudes past the clamp plate. Casters must be 23.3 mm high (ball caster + spacer).

## 5. Simulation (`python3 simulation/run_all.py`, ≈ 5 s, no dependencies)

Electro-mechanical model: 3S Li-ion (OCV curve + 100 mΩ) → TB6612 bank (random ±25 % R_on spread decides how the current shares over the modules) →
DC motors fitted to the datasheet rated point → tanh tyre force model → differential-drive body with slope, rolling resistance, yaw inertia.
Results (plots + CSV) are in `simulation/results/`:

| file | content |
|---|---|
| `S1_launch.png` | full-duty launch: speed, motor current, battery voltage (1 vs 3 groups) |
| `S5_track.png`, `S5_line_follow.png` | PID line-following lap with the 8-channel array (7 m stadium track with chicane, 3 % sensor noise, 30 mm start offset): finishes in 9.0 s, rms error 6 mm |
| `summary.md` | all tables: launch, stall, hill sweep, spin, lap, PCB copper check |

Key outputs: top speed 1.57 m/s, 0 → 1 m/s in 0.22 s, spin 246 °/s, lap 9.0 s at 0.78 m/s, 3.8 mAh per lap, battery ≥ 11.2 V in all runs.
The simulation shows the one real hazard: **hard PWM steps** make the motor draw ≈ 6 A for ~50 ms (module peaks 2.6 A with one group > 1.2 A rating) →
slew-limit duty in firmware (the lap simulation uses 8 duty/s; its worst module is 1.4 A).

Assumed (not in the repo, all in `simulation/params.py`): total mass 2.1 kg, 1:60 gearbox / rotor inertia, wheel, tyre μ 0.8, battery 2.8 Ah/22 mΩ per cell, R_on 0.5 Ω ± 25 %.
The model has no lateral tyre slip, no motor inductance (PWM-averaged) and no thermal model.

## 6. Reproducing / editing

```
python3 tools/build_pcb.py      # re-routes and rewrites RocketBoy.kicad_pcb (+ .pretty), prints the checks, writes tools/out/pcb_preview.png
python3 tools/build_sch.py      # rewrites RocketBoy.kicad_sch from tools/originals/*.orig
python3 tools/compare_netlists.py
python3 simulation/run_all.py
```
`tools/originals/` keeps your untouched files; the generators always start from them. Hand edits made in KiCad afterwards will be overwritten if you re-run the generators,
so treat the generators as the one-time "design completion" step and edit in KiCad from here on.
