# MFE Fighter geometry — extracted from the manufacturer's RealFlight model

Source: `fighterVTOL_EA.RFX` → `fighterVTOL.rfvehicle` (RealFlight 8 vehicle
definition, dated June 2026). Parsed 6 Sep 2026. This replaces the
"geometry approximated, needs CAD" open item — these are the manufacturer's
own numbers.

**Frame conversion applied:** RealFlight (X-right, Y-nose, Z-up) →
Gazebo aircraft (X-forward, Y-left, Z-up): `Xg = Yrf, Yg = -Xrf, Zg = Zrf`.
Positions below are in the Gazebo frame, relative to the RealFlight model
origin (NOT yet shifted to CG).

## Mass

| Component | Gazebo pos (m) | Mass (kg) | Notes |
|---|---|---|---|
| Fuselage (structure) | (0.421, 0.000, -0.030) | 3.719 | |
| Forward tractor motor "Engine" | (0.442, 0.000, -0.044) | 0.323 | **MFE X5120S, KV190** (RFX pick — real aircraft uses ~KV200) |
| Lift motor ENGINE_FL | (0.397, 0.503, 0.016) | 0.221 | **MFE M5015S, KV220** ×4 (real aircraft ~KV160) |
| Lift motor ENGINE_FR | (0.425, -0.503, 0.016) | 0.221 | |
| Lift motor ENGINE_RL | (-0.445, 0.503, 0.016) | 0.221 | |
| Lift motor ENGINE_RR | (-0.445, -0.503, 0.016) | 0.221 | |
| boom_L / boom_R (tubes) | (0.405, ±0.501, -0.001) | 0.072 each | |
| Main Battery | (0.151, 0.000, -0.055) | 1.089 | modelled as 6S of the RFX cell weight; real aircraft flies 2×6S 16000mAh |
| Main Wing | (0.077, -0.134, 0.016) | 0.340 | |
| Horizontal Tail | (-0.759, -0.050, -0.041) | 0.085 | |
| Vertical Tail | (-0.655, 0.000, 0.000) | 0.091 | |
| Avionics/ballast lump "Mass" | (-0.168, 0.000, -0.061) | 0.595 | |

**Total: 7.27 kg** — the RealFlight model is deliberately lighter than the
real aircraft's **11.5 kg MTOW**. Open question stands: was
`Fighter_VTOL_V4.6.3.param` (`Q_M_THST_HOVER=0.381`) tuned against this
RealFlight model (7.3 kg) or the real aircraft (11.5 kg)? That decides
which mass the Gazebo model should use.

## Derived (point-mass approximation)

- **CG:** (0.236, -0.007, -0.028) m from the RFX origin — i.e. well forward.
- **Inertia about CG:** Ixx ≈ 0.27, Iyy ≈ 0.64, Izz ≈ 0.90 kg·m²
  (point masses under-estimate — expect the real tensor ~1.5–2× larger;
  tune against a flight log).

## ⚠ Forward-CG / rotor asymmetry

Front lift rotors sit at X ≈ +0.41, rear rotors at X ≈ -0.445, so the
rotor rectangle centre is at X ≈ -0.02 — but the CG is at X ≈ +0.24,
about **0.26 m forward of the rotor centroid**. With ArduPilot's default
`Q_FRAME_TYPE=1` (X) mixing this needs significant hover pitch trim
(front motors work harder). Either the real aircraft's CG is further aft
than the RFX, or they rely on `Q_M_HOVER_LEARN` + the attitude
controller. Flag for the tuning pass.

## Lifting surfaces (RealFlight `.rfvehicle`)

| Surface | Root chord | Tip chord | Span/side | Airfoil |
|---|---|---|---|---|
| Main Wing | 0.3048 m | 0.27686 m | 1.14046 m (→ 2.28 m full) | NACA 5411 → NACA 2412 |
| Horizontal Tail | 0.218695 m | 0.174028 m | 0.51054 m | NACA 0010 → 0009 |
| Vertical Tail | 0.2667 m | 0.1778 m | 0.56896 m | NACA 0009 |

Main-wing area ≈ 0.66 m² (spec sheet says 0.725 m² — RealFlight model is
slightly smaller). Fuselage drag areas: frontal 0.1645 m², side 0.2258 m².

## Motor spec files (from the RFX)

- **MFE M5015S KV220** (lift ×4): 221 g, KV 190… wait — the `.electricTorque`
  says KV 220, R 0.028 Ω, no-load current 2 A. 7.8 oz.
- **MFE X5120S KV190** (forward): 323 g, KV 190, R 0.028 Ω, Io 2 A. 11.4 oz.
- Battery cell: 6.4 oz, 0.009 Ω internal, 10000 mAh nominal per the file
  (named "20000 mah"), LiPo voltage curve 4.2→3.6 V.
