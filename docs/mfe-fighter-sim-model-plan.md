# MFE Fighter — Simulator Model Build Plan (ArduPilot + Gazebo Harmonic)

Status: **planning only — nothing built.** This scopes the work so that
once ArduPilot SITL is installed the model-building is a defined task, not
a blank page. Written 6 Sep 2026 from `Fighter_VTOL_V4.6.3.param`, the
manufacturer specs, and the `ardupilot_gazebo` docs.

## Decision recap

The real aircraft runs **ArduPlane 4.6.3** on a Cube Orange (confirmed
from photos + the param file). So the simulator targets **ArduPilot SITL
+ `ardupilot_gazebo`** on the Gazebo Harmonic install that's already here
for PX4 — not PX4's `standard_vtol`. See
`docs/decision-log/22.08.2026 ...` and `MFE-Fighter-Specifications.md`
(in `~/UAS-Academy/UAV-Academy/UAV Academy GCS Pro/3DXR/`).

## Prerequisites (all need `sudo`, so they're the user's to run)

1. **Build deps + ArduPilot source**
   ```
   git clone --recurse-submodules https://github.com/ArduPilot/ardupilot.git
   cd ardupilot && Tools/environment_install/install-prereqs-ubuntu.sh -y
   . ~/.profile
   ./waf configure --board sitl && ./waf plane
   ```
   Note the 24.04 caveat — same class of "script predates this Ubuntu" issue
   the PX4 build hit (see `docs/decision-log/12.07.2026 ...`). If
   `install-prereqs-ubuntu.sh` chokes, the deps are just: `python3-pip`,
   `gcc/g++`, `git`, `libtool`, `libxml2-dev`, `libxslt1-dev`,
   `python3-pexpect`, plus the pip packages `future`, `MAVProxy`,
   `pymavlink`, `empy==3.3.4`.

2. **`ardupilot_gazebo` plugin** (Gazebo Harmonic is already installed)
   ```
   sudo apt install libgz-sim8-dev rapidjson-dev libopencv-dev
   git clone https://github.com/ArduPilot/ardupilot_gazebo
   cd ardupilot_gazebo && mkdir build && cd build
   cmake .. -DCMAKE_BUILD_TYPE=RelWithDebInfo && make -j4
   ```
   Then export `GZ_SIM_SYSTEM_PLUGIN_PATH` and `GZ_SIM_RESOURCE_PATH` per
   its README.

3. Sanity check with a stock model first (`iris_with_ardupilot` or
   `zephyr`) before touching the Fighter model — proves the SITL↔Gazebo
   bridge works on this machine.

## The Fighter model — what it needs to contain

A **QuadPlane**: fixed wing + 4 non-tilting vertical lift rotors in an X.
From the param file: `Q_FRAME_CLASS=1` (Quad), `Q_FRAME_TYPE=1` (X),
`Q_TILT_ENABLE=0`.

### Geometry / mass (from the manufacturer spec sheet)

| Property | Value |
|---|---|
| Wingspan | 2.43 m |
| Fuselage length | 1.45 m |
| Wing area | 0.725 m² |
| MTOW | 11.5 kg (use ~10.5 kg as a typical loaded sim mass) |
| Stall speed | 10 m/s → sets the wing's lift-curve / area·Cl |
| Cruise | 17–20 m/s |
| Hover throttle | `Q_M_THST_HOVER=0.381` → 4 rotors must produce ~1.05× weight at ~38% throttle |

**Inertia:** no measured figures. Start from a box+wing approximation
(Ixx dominated by wingspan, Iyy by fuselage length) and tune against
real flight-log rates later. **Open item: get a CG measurement** — the
manual only says "under the fuselage hook / wing-root plastic".

### Actuator → Gazebo joint mapping

`ardupilot_gazebo`'s `<control>` channels are 0-indexed and map to
ArduPilot SERVOn outputs. From `Fighter_VTOL_V4.6.3.param`:

| SERVOn | FUNCTION | Meaning | Gazebo element |
|---|---|---|---|
| 1 | 4 | Aileron (left) | left aileron revolute joint |
| 2 | 19 | Elevator | elevator joint (or elevons if tailless — confirm from CAD) |
| 3 | 70 | Throttle | forward pusher/tractor rotor (`M5020 200KV`, APC prop) |
| 4 | 21 | Rudder | rudder joint |
| 5 | 4 | Aileron (right) | right aileron revolute joint |
| 6 | 19 | Elevator (2nd) | second elevator servo — same joint or mirrored |
| 9 | 33 | Motor1 | VTOL lift rotor, front-right (X layout) |
| 10 | 34 | Motor2 | VTOL lift rotor, rear-left |
| 11 | 35 | Motor3 | VTOL lift rotor, front-left |
| 12 | 36 | Motor4 | VTOL lift rotor, rear-right |

Lift rotors: `MFE 160KV`, CF 20×6.8 props. Motor1–4 spin directions
follow ArduCopter's Quad-X convention (M1 CCW front-right, M2 CCW
rear-left, M3 CW front-left, M4 CW rear-right) — the Gazebo
`MulticopterMotorModel` `turningDirection` must match or attitude
control inverts.

### Plugins per link/joint

- `LiftDragPlugin` on wing, horizontal tail, vertical tail (3+ instances),
  seeded from wing area 0.725 m² and stall at 10 m/s.
- `MulticopterMotorModel` ×5 (4 lift + 1 forward), or the lighter
  `LiftDragPlugin`-based prop model the ardupilot_gazebo examples use.
- `JointPositionController` (or `JointController`) ×4 for aileron ×2,
  elevator, rudder.
- One `ArduPilotPlugin` block with the `<control>` channel list above,
  `fdm_port_in`/`fdm_port_out` on the SITL default (9002/9003), and the
  IMU/nav sensors wired to `<imuName>`.

### Reuse from what's already here

- The **FPV camera** sensor block from PX4's `standard_vtol/model.sdf`
  (`docs/decision-log/12.07.2026 ...` documents how it was added) — the
  same camera on `base_link` feeds `video_feed.py`. Keep the topic name
  matching `CAMERA_TOPIC` in `video_feed.py` or update that constant.
- The **training-area worlds** (Hoggar / Black Rock / Uyuni / Nullarbor)
  and their `<spherical_coordinates>` + magnetic-field blocks — reusable
  as-is; only the vehicle model spawned into them changes.

## Geometry — RESOLVED from the RealFlight model (6 Sep 2026)

Item 4 below turned out to be the answer to items 1, 3 and 5: the
manufacturer's `fighterVTOL_EA.RFX` contains a full mass/geometry model.
Extracted and documented in
`sim/models/mfe_fighter/GEOMETRY-from-realflight.md` and applied (mass +
inertia so far) to `model.sdf`.

Confirmed from the RFX:
- Conventional layout — separate main wing, horizontal tail, vertical
  tail; ailerons + elevator + rudder (item 2). Not elevons.
- 4 lift rotors at X ≈ +0.41 (front) / -0.445 (rear), Y ≈ ±0.50; forward
  **tractor** at the nose (+0.44 m), not a pusher (item 3).
- RealFlight total mass 7.27 kg, CG at X ≈ +0.24 m, point-mass inertia
  Ixx/Iyy/Izz ≈ 0.27 / 0.64 / 0.90 kg·m² (items 1, 5).

## Still open

1. Which mass the param file was tuned to — RealFlight's 7.27 kg or the
   real aircraft's 11.5 kg MTOW.
2. The forward-CG vs rotor-centroid asymmetry (CG ~0.26 m ahead of the
   rotor rectangle centre) — real, or an RFX artefact?
3. Real flight log to tune `Q_A_RAT_*` gains, motor thrust constants and
   the lift/drag coefficients against.
