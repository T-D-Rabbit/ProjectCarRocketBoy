# RocketBoy – specification sheet

Legend: **[given]** read from your files (STEP / PDFs / KiCad), **[derived]** calculated from them, **[assumed]** my choice – confirm or replace, **[sim]** simulated, not measured.

## Base robot

### Parts used
| # | Part | Qty | Notes |
|---|---|---|---|
| 1 | Main PCB with header pins (RocketBoy.kicad_pcb) | 1 | 155 × 208 × 1.6 mm, 2-layer, 2 oz copper recommended |
| 2 | ESP32 DevKit (38-pin) | 1 | plugs into socket U10 |
| 3 | Johnson gear-motor SG-3851218000-60K, 12 V | 2 | |
| 4 | Custom 3D-printed / CNC chassis | 1 | Ø300 × 3 mm disc |
| 5 | L-clamp for Johnson motor | 2 | 1.5 mm steel |
| 6 | TB6612FNG driver module | 9 | 3 enable groups of 3 |
| 7 | Wheel Ø110 × 25 mm, 6 mm bore **[assumed]** | 2 | |
| 8 | Ball caster, 25.3 mm tall **[assumed]** | 2 | front and rear |
| 9 | 3S Li-ion pack (Molicel 18650, 2.8 Ah class) **[assumed]** | 1 | under the chassis |
| 10 | 12 V → 5 V buck module, ≥ 2 A **[assumed]** | 1 | wired to J1 / J2 |
| 11 | SPDT slide switch | 3 | SW1–SW3, enable the 3 driver groups |
| 12 | 470 µF / 25 V electrolytic capacitor | 3 | C1–C3 on the motor supply |
| 13 | 5.08 mm screw terminal, 2-pole | 3 | battery, left motor, right motor |
| 14 | M3 × 40 mm standoff + M3 screws | 4 | PCB on the chassis holes (±75, ±100 mm) |
| 15 | Fuse 15 A + main switch **[recommended]** | 1 | in the battery lead |
| 16 | Header pins J3 (1×10), J4 (1×16), J5 (1×8), 2.54 mm | 3 | for a top PCB / add-ons |

### Sizes
| Item | Size |
|---|---|
| Overall (wheel to wheel × length × height) | ≈ 358 × 300 × 86 mm **[derived]** |
| Chassis | Ø300 mm × 3 mm **[given]** |
| Wheel | Ø110 × 25 mm **[assumed]**; track (wheel centre to centre) 331 mm |
| Chassis underside above floor | 25.3 mm (top face 28.3 mm) **[derived]** |
| Motor | gearbox Ø37 × 25, can Ø29 × 37.8, shaft Ø6 × 30 mm **[given]** |
| L-clamp | 40 mm wide, flange 22 mm, motor axis 26.7 mm above the flange **[given]** |
| PCB | 155 × 208 × 1.6 mm, 4 × Ø3.2 mm holes on a 150 × 200 mm pattern **[given]** |
| Mass | ≈ 2.2 kg **[assumed part list]** |

### Specification
| Item | Value |
|---|---|
| Supply | 3S Li-ion, 9 – 12.6 V (nominal 11.1 V) |
| Logic | ESP32 on 5 V from the buck module; 3.3 V for the driver modules' logic |
| Motor | 12 V DC, 300 rpm no-load, 220 rpm at 6 kgf·cm, no-load current ≤ 0.6 A **[given]** |
| Motor stall (not in the PDF) | ≈ 6.7 A / 22.5 kgf·cm **[derived]** |
| Driver | TB6612FNG ×9 in parallel: 1.2 A continuous / 3.2 A pulse per channel, R_on ≈ 0.5 Ω |
| Channels | A = left motor, B = right motor, same signals on all 9 modules |
| Driver capacity per motor | 1 group 3.6 A · 2 groups 7.2 A · 3 groups 10.8 A continuous |
| Enable | STBY1–3 via slide switches SW1–SW3 (ON = 3.3 V, OFF = GND) |
| Control pins | PWMA GPIO13, AIN1 GPIO12, AIN2 GPIO14, PWMB GPIO27, BIN1 GPIO25, BIN2 GPIO26 |
| Top speed | 1.73 m/s **[sim]** |
| Acceleration | 0 → 1 m/s in 0.20 s **[sim]** |
| Spin on the spot | ≈ 270 °/s at duty ±0.5 **[sim]** |
| Slope | tyres slip at ≈ 34° (μ 0.8 assumed) **[sim]** |
| Current | cruise ≈ 0.5 A per motor; start-up spike ≈ 6 A for ~50 ms (use soft start); jammed wheel ≈ 5.7 A **[sim]** |
| Runtime | ≈ 2 h at steady cruise on 2.8 Ah (≈ 1.4 A total) **[estimate]** |
| Expansion | J3: 5V, 3V3, GND, BIN1, BIN2, PWMB, AIN2, AIN1, GND, PWMA · J4/J5: all usable free ESP32 pins |

## Line follower add-on

### Parts used
| # | Part | Qty | Notes |
|---|---|---|---|
| 1 | Base robot (above) | 1 | unchanged |
| 2 | 8-channel IR reflectance array (Indian Hobby Center "Line Follower Sensor 8 Array") | 1 | pinout **not verified** (shop page blocked for me) |
| 3 | Sensor mounting bracket (3D-printed) | 1 | array 3–8 mm above the floor, at the front underside |
| 4 | Jumper wires / ribbon to J5 (and J4 if needed) | 1 set | |
| 5 | Optional: top add-on PCB on J3 / J4 / J5 | 0–1 | |

### Sizes
| Item | Size |
|---|---|
| Sensor array | width ≈ 70 mm for 8 sensors at 9.525 mm pitch **[assumed, QTR-8 style]** – check yours |
| Mounting | under the chassis front; chassis underside is 25.3 mm above the floor, so the bracket drops ≈ 17–22 mm |
| Line | 19 mm black tape on a light floor **[assumed]** |

### Specification
| Item | Value |
|---|---|
| Sensor supply | 3.3 V (J5 pin 1) so outputs never exceed the ESP32's 3.3 V limit |
| Analog inputs | J5: GPIO36, 39, 34, 35, 32, 33 (ADC1, work with Wi-Fi on) |
| Extra digital inputs | J4: e.g. GPIO18, GPIO19 for sensors 7 and 8 |
| Control | PID on the weighted line position → left/right duty (firmware not included) |
| Driver groups needed | 1 group is enough; keep the duty slew limit (3 per second) |
| Performance | not simulated in the current simulator **[open]** |
