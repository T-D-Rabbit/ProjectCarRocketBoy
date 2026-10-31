# RocketBoy simulation results

## Model summary
| item | value | source |
|---|---|---|
| total mass | 2.12 kg | assumed part list (params.py) |
| wheel | 100 mm dia, track width 331 mm | assumed wheel, STEP/PDF geometry |
| ground clearance under chassis | 23.3 mm (wheel radius - 26.7 mm L-clamp axis height) | PDF |
| motor no-load speed / rated point | 300 rpm / 220 rpm @ 6 kgf.cm, I0 = 0.5 A | Johnson Motor.pdf |
| motor winding resistance (fitted) | 1.78 ohm | derived from rated point |
| motor Ke = Kt | 0.3536 V s/rad | derived |
| **stall current / torque (derived)** | **6.74 A / 22.5 kgf.cm** | PDF stall rows are blank -> derived |
| current at rated load | 2.16 A (PDF upper bound 4.5 A) | derived |
| battery | 3S1P, 2.8 Ah, 101 mohm pack incl. wiring | Molicel P28A class |

## S1 - full-duty launch on flat ground
| groups on | 0-1 m/s [s] | top speed [m/s] | inrush peak per motor [A] | steady current per motor [A] | min battery V | worst module peak [A] (limit 1.2 A cont / 3.2 A pulse) |
|---|---|---|---|---|---|---|
| 1 (3 modules/motor) | 0.22 | 1.57 | 6.21 | 0.53 | 11.01 | 2.57 |
| 2 | 0.21 | 1.58 | 6.50 | 0.53 | 10.95 | 1.35 |
| 3 (9 modules) | 0.21 | 1.58 | 6.60 | 0.53 | 10.93 | 0.94 |

Per-module current peaks during the launch (channel A / left motor), 1 group enabled: 2.57, 1.79, 1.86 A
A hard 100 % duty step makes the motor draw its inrush (6.2 A) before back-EMF builds up -> **ramp the PWM (>= 100 ms) in firmware**; the 3 modules of one group then stay inside the 1.2 A continuous rating.

## S2 - blocked wheels (motors stalled), full duty
| groups on | modules per motor | stall current per motor [A] | rated (cont.) capacity [A] | pulse capacity [A] | verdict | battery V | battery current [A] |
|---|---|---|---|---|---|---|---|
| 1 | 3 | 5.62 | 3.6 | 9.6 | pulse only (<=3.2 A/module) (worst module 2.57 A) | 11.12 | 11.6 |
| 2 | 6 | 5.86 | 7.2 | 19.2 | pulse only (<=3.2 A/module) (worst module 1.35 A) | 11.08 | 12.1 |
| 3 | 9 | 5.93 | 10.8 | 28.8 | OK (worst module 0.94 A) | 11.07 | 12.2 |

Stall is the only case that needs more than one group; with 2-3 groups enabled a stalled motor is inside the pulse rating. The TB6612FNG has thermal shutdown but **no current limit**, so stall detection in firmware is recommended.

## S3 - hill climb (duty 0.7 for 6 s, 1 group)
| slope [deg] | speed [m/s] | motor current [A] | wheel slip |
|---|---|---|---|
| 0 | 1.05 | 0.53 | no |
| 5 | 1.01 | 0.66 | no |
| 10 | 0.97 | 0.78 | no |
| 15 | 0.93 | 0.91 | no |
| 20 | 0.89 | 1.03 | no |
| 25 | 0.85 | 1.15 | no |
| 30 | 0.81 | 1.26 | yes |
| 35 | -0.06 | 1.32 | yes |

Tyre limit: the drive wheels (85 % of weight, mu = 0.80) hold up to about 34 deg before slipping.

## S4 - spin on the spot (duty -0.5 / +0.5)
Yaw rate 246 deg/s, current 0.54 A per motor, battery 12.16 V.

## S5 - line following lap (8-channel IR array, PID)
Track: closed loop 7.02 m long, minimum radius 600 mm, 19 mm tape. Sensor array 130 mm ahead of the axle, 9.525 mm pitch.

| enabled | finished lap | lap time [s] | avg speed [m/s] | max off-line [mm] | rms off-line [mm] | line lost [s] | peak motor A | mean motor A | min battery V | charge used [mAh] | worst module [A] |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 group | yes | 9.0 | 0.78 | 31.6 | 6.2 | 0.01 | 3.29 | 0.59 | 11.77 | 3.8 | 1.41 |
| 3 groups | yes | 8.9 | 0.79 | 31.6 | 6.2 | 0.01 | 3.39 | 0.59 | 11.75 | 3.8 | 0.49 |

## S6 - PCB copper current check (widths read from RocketBoy.kicad_pcb)
| path | width [mm] | demand [A] | capacity 1 oz / 2 oz @ +10 C [A] | verdict (2 oz) |
|---|---|---|---|---|
| VBAT main trunk (both motors stalled, 3 groups) | 5.0 | 12.2 | 7.7 / 12.7 | OK |
| motor out trunk /LmA (one motor stalled) | 3.5 | 6.7 | 5.9 / 9.8 | OK |
| motor out trunk /RmA (one motor stalled) | 3.5 | 6.7 | 5.9 / 9.8 | OK |
| VBAT lane per column (3.0 mm) (3 modules x 2 ch x 1.2 A rated) | 3.0 | 7.2 | 5.3 / 8.8 | OK |
| motor lane per column (2.0 mm) (3 modules x 1.2 A rated) | 2.0 | 3.6 | 4.0 / 6.5 | OK |
| module stub VBAT (1.5 mm) (one module, both channels rated) | 1.5 | 2.4 | 3.2 / 5.3 | OK |
| module stub motor (1.2 mm) (one module channel rated) | 1.2 | 1.2 | 2.7 / 4.5 | OK |
| logic nets (0.3 mm) (GPIO current) | 0.3 | 0.0 | 1.0 / 1.7 | OK |

Order the board with **2 oz copper**; with 1 oz the trunks are still adequate for normal running (<2 A per motor) but not for stall.

