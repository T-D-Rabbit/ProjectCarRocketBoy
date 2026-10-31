# RocketBoy simulation results

## Model summary
| item | value | source |
|---|---|---|
| total mass | 2.19 kg | assumed part list (params.py) |
| wheel | 110 mm dia, track width 331 mm | assumed wheel, STEP/PDF geometry |
| chassis top face / underside above ground | 28.3 / 25.3 mm (wheel radius - 26.7 mm clamp axis height; clamps on the top face) | PDF |
| motor no-load speed / rated point | 300 rpm / 220 rpm @ 6 kgf.cm, I0 = 0.5 A | Johnson Motor.pdf |
| motor winding resistance | 1.60 ohm (= 12 V / stall current) | derived |
| motor Ke = Kt | 0.3565 V s/rad | derived |
| **stall current / torque** | **7.50 A** (given by user) / 25.4 kgf.cm (derived) | PDF stall rows are blank |
| rated-point check | model gives 229 rpm at 6 kgf.cm (datasheet 220 +-22 rpm) | consistent |
| current at rated load | 2.15 A (PDF upper bound 4.5 A) | derived |
| battery | 3S1P, 2.8 Ah, 101 mohm pack incl. wiring | Molicel P28A class |

## S1 - full-duty launch on flat ground
| groups on | 0-1 m/s [s] | top speed [m/s] | inrush peak per motor [A] | steady current per motor [A] | min battery V | worst module peak [A] (limit 1.2 A cont / 3.2 A pulse) |
|---|---|---|---|---|---|---|
| 1 (3 modules/motor) | 0.18 | 1.73 | 6.84 | 0.53 | 10.88 | 2.83 |
| 2 | 0.17 | 1.73 | 7.19 | 0.53 | 10.81 | 1.49 |
| 3 (9 modules) | 0.17 | 1.74 | 7.30 | 0.53 | 10.79 | 1.04 |

Per-module current peaks during the launch (channel A / left motor), 1 group enabled: 2.83, 1.97, 2.04 A
A hard 100 % duty step makes the motor draw its inrush (6.8 A) before back-EMF builds up -> **ramp the PWM (>= 100 ms) in firmware**; the 3 modules of one group then stay inside the 1.2 A continuous rating.

## S2 - blocked wheels (jammed gearbox / wheel held still), full duty
| groups on | modules per motor | stall current per motor [A] | rated (cont.) capacity [A] | pulse capacity [A] | verdict | battery V | battery current [A] |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 6.13 | 3.6 | 9.6 | pulse only (<=3.2 A/module) (worst module 2.83 A) | 11.02 | 12.6 |
| 2 | 6 | 6.41 | 7.2 | 19.2 | pulse only (<=3.2 A/module) (worst module 1.49 A) | 10.97 | 13.2 |
| 3 | 9 | 6.50 | 10.8 | 28.8 | OK (worst module 1.04 A) | 10.95 | 13.4 |

Note: with free tyres on a floor the wheels slip before the motor stalls (traction limit, see S3, about 1.4 A per motor), so this case needs a jammed gearbox or a wheel held by an obstacle.

Stall is the only case that needs more than one group; with 2-3 groups enabled a stalled motor is inside the pulse rating. The TB6612FNG has thermal shutdown but **no current limit**, so stall detection in firmware is recommended.

## S3 - hill climb (duty 0.7 for 6 s, 1 group)
| slope [deg] | speed [m/s] | motor current [A] | wheel slip |
|---|---|---|---|
| 0 | 1.16 | 0.53 | no |
| 5 | 1.12 | 0.68 | no |
| 10 | 1.07 | 0.82 | no |
| 15 | 1.03 | 0.96 | no |
| 20 | 0.98 | 1.10 | no |
| 25 | 0.94 | 1.23 | no |
| 30 | 0.89 | 1.36 | yes |
| 35 | -0.06 | 1.42 | yes |

Tyre limit: the drive wheels (85 % of weight, mu = 0.80) hold up to about 34 deg before slipping.

## S4 - spin on the spot (duty -0.5 / +0.5)
Yaw rate 272 deg/s, current 0.54 A per motor, battery 12.15 V.

## S5 - hard-coded demo route (open loop, no sensors)
Route: 4 x [drive straight 2.0 s at duty 0.60, pause, spin left 0.368 s at +-0.45 (calibrated so one side+spin cycle turns the robot 90 deg), settle]; duty is slew-limited to 3 /s.

| enabled | duration [s] | path length [m] | end position error [mm] | end heading error [deg] | peak motor A | mean motor A (moving) | min battery V | charge used [mAh] | worst module A (1.2 cont / 3.2 pulse) |
|---|---|---|---|---|---|---|---|---|---|
| 1 group | 15.2 | 7.94 | 91 | 3.7 | 2.63 | 0.79 | 11.73 | 6.9 | 1.11 |
| 3 groups | 15.2 | 8.02 | 273 | 11.3 | 2.71 | 0.80 | 11.71 | 7.0 | 0.40 |

## S6 - PCB copper current check (widths read from RocketBoy.kicad_pcb)
| path | width [mm] | demand [A] | capacity 1 oz / 2 oz @ +10 C [A] | verdict (2 oz) |
|---|---|---|---|---|
| VBAT main trunk (both motors stalled, 3 groups) | 5.0 | 13.4 | 7.7 / 12.7 | marginal - fault condition only |
| motor out trunk /LmA (one motor stalled) | 3.5 | 7.5 | 5.9 / 9.8 | OK |
| motor out trunk /RmA (one motor stalled) | 3.5 | 7.5 | 5.9 / 9.8 | OK |
| VBAT lane per column (3.0 mm) (3 modules x 2 ch x 1.2 A rated) | 3.0 | 7.2 | 5.3 / 8.8 | OK |
| motor lane per column (2.0 mm) (3 modules x 1.2 A rated) | 2.0 | 3.6 | 4.0 / 6.5 | OK |
| module stub VBAT (1.5 mm) (one module, both channels rated) | 1.5 | 2.4 | 3.2 / 5.3 | OK |
| module stub motor (1.2 mm) (one module channel rated) | 1.2 | 1.2 | 2.7 / 4.5 | OK |
| logic nets (0.3 mm) (GPIO current) | 0.3 | 0.0 | 1.0 / 1.7 | OK |

Order the board with **2 oz copper**; with 1 oz the trunks are still adequate for normal running (<2 A per motor) but not for stall.

