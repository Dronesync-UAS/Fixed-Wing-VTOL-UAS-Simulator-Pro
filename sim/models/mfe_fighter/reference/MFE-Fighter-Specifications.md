# MFE Fighter VTOL — Consolidated Specifications

One clean reference instead of three overlapping source documents. Sources
cross-checked against each other 5 Sep 2026:
- `Make Fly Easy - MFE Fighter 2430mm Wingspan - VTOL.docx` (3DXR retailer listing)
- `Manual fighter.pdf` (manufacturer's own user manual, Chinese + English, v1.0, 2020.04)
- `Fighter_VTOL_V4.6.3.param` (the actual ArduPilot parameter file for this aircraft)

The dimension/weight numbers below match exactly between the retailer
listing and the manufacturer's manual - treat them as confirmed, not
estimated.

## Airframe

| Spec | Value |
|---|---|
| Type | Fixed-wing VTOL ("QuadPlane" - fixed wing + 4 independent lift motors, not tilting) |
| Wingspan | 2430 mm |
| Fuselage length | 1450 mm |
| Fuselage height | 180 mm |
| Wing area | 72.5 dm² |
| Transport case size | 1.26 × 0.35 × 0.495 m |
| Material | EPO, EVA, carbon fibre, PC, engineering plastics |
| Waterproofing | IPX3 |
| Disassembly | Tool-free (quick-release wings, folding arms, quick-release tail) |

## Weight & performance

| Spec | Value |
|---|---|
| Max take-off weight | 11.5 kg |
| Maximum payload | 1.5 kg (manual says "suggested payload <2500g" - treat 1.5kg as the safe design limit) |
| Payload bay | 280 × 160 × 110 mm |
| Suggested flight speed | 17–20 m/s |
| Stalling speed | 10 m/s |
| Practical ceiling | 4000 m |
| Wind resistance rating | 5 (manufacturer's own scale, not further defined) |
| Longest range | >150 km (with a 600 g payload) |
| Max endurance | 90–110 min forward flight, on 2× 6S 16000mAh |
| Take-off/landing | VTOL or hand-launch/parachute |

## Propulsion

| Role | Spec |
|---|---|
| Forward (cruise) motor | 1× MFE custom 200KV, 12S 60A ESC, APC forward prop |
| Lift motors (VTOL) | 4× MFE custom 160KV, one 12S ESC each, mounted in the wings |
| VTOL props | 2 pairs, carbon fibre 20×6.8 |
| Battery | 2× 6S 16000mAh LiPo, max supported 12S@22000mAh |

## Avionics (as fitted)

- Flight controller: **Cube Orange**, mounted on an anti-vibration plate
- Carrier board: power/signal distribution (2 power inputs, POWER1/POWER2)
- GNSS: **Here3** (CAN-based, mounted external/rear for heading + position)
- RC/telemetry/video: **Herelink** (air unit + controller — see `../Herelink/` and `gcs_app/docs/herelink-docs.md`)
- Power management/monitoring: **Mauch 003**, **Power Cube 3**
- Companion computer: an onboard SBC (Jetson-class, actively cooled) forward of the Cube, for onboard processing (the "3DXR Specs.docx" source describes this from photos, not a datasheet — treat the exact model as unconfirmed)
- Payload options mentioned by the manufacturer: Sony A7R2 (42MP full-frame) camera, or a ~1.5kg lightweight LiDAR

## Confirmed ArduPilot configuration (from `Fighter_VTOL_V4.6.3.param`)

This is the actual flight-tested config, not a guess:

- `Q_ENABLE = 1` — QuadPlane mode active
- `Q_FRAME_CLASS = 1` (Quad), `Q_FRAME_TYPE = 1` (X) — **4 lift motors in an X layout**, matching the "4x lift motors" in the parts list above
- Servo output map:
  - Outputs 1, 5: Aileron (`SERVO_FUNCTION 4`) — two aileron servos
  - Output 2, 6: function 19
  - Output 3: function 70
  - Output 4: function 21
  - Outputs 9–12: `SERVO_FUNCTION 33/34/35/36` = **Motor1–Motor4** — the four VTOL lift motors, confirming the quad-X lift layout sits on outputs 9–12, separate from the fixed-wing surfaces on 1–6

## Firmware

- **ArduPlane V4.6.3** (per the param file's own header comment, dated 2026-01-30). This is the current/confirmed version — see `SITL_Models_RealFlight/superseded/` for the previous V4.4.4 set, kept for history only.

## Open items (not yet confirmed)

- Whether the RealFlight model files (`fighterVTOL_EA.RFX`, `.kex`, `.rfvehicle`) were built against V4.6.3 or the older V4.4.4 param set — servo/motor mapping could be out of sync if not.
- Exact companion computer model (Jetson-class SBC identified from photos only, not a datasheet).
- CG location is documented qualitatively ("under the raised position of the fuselage hook and wing root plastic") but not as a measured distance from a reference datum - worth getting an exact number before building a simulator model, since VTOL stability is sensitive to CG placement.
