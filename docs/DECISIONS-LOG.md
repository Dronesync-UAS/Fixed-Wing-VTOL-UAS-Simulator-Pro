# Decisions Log — Fixed-Wing VTOL UAS Simulator-Pro

This is the live, current decisions log for this project. Superseded by nothing except a later entry below. The PDF in Google Drive 99_Archive is historical only — it predates most of this log and is not authoritative.

## Settled Architecture
- PX4 pinned to v1.15.4, standard_vtol airframe (MFE Fighter is the real target aircraft)
- Gazebo Harmonic
- VirtualBox OVA distribution
- Telemetry bridge on WebSocket port 8765 / PX4 offboard UDP 14540
- QGC on UDP 14550
- Flight-stack fidelity (PX4 vs ArduPilot): RESOLVED 03/09/2026 — Accountable Manager confirmed no issue with simulator running PX4 while real MFE Fighter runs ArduPilot on its Cube Orange autopilot. No flight-stack rebuild required.

## Sign-off Decisions (Accountable Manager / Head of Training)
Confirmed 03/09/2026:
- GPS/environmental failure behaviour: both instant-total-loss and gradual-degradation GPS failure modes to be built as selectable scenarios (not one or the other). Weather condition changes added as new scope, separate from existing GPS/motor/engine failure injection.
- 45-second no-response timeout (failure-response logging): SETTLED as final, not provisional.
- Student/instructor identification scheme: SETTLED — first name + session code. Engages UK GDPR/DPA 2018 (CAP722B 2.2(f)) from the first logged entry.
- Record retention/storage: SETTLED — each record stored as a file in the student/instructor's dedicated **Google Drive** folder (corrected 07/10/2026 — previously wrongly logged as OneDrive), access restricted to UAV Academy personnel only (no external/public sharing links). Lock/tamper-protection mechanism for the file itself is still TBC.
- VTOL-specific competency/procedure knowledge: SETTLED (approach) — delivered via a dedicated UAV Academy simulator-training session, not built as a simulator feature.

## Still Open / TBC
- Sim flying hours / assessment log format
- Definition of a "correct" student response to an injected failure
- Whether the GPS-failure proxy workaround (used because PX4's native GPS failure injection is broken — PX4 issue 22296) is an acceptable substitute for CAP722B 5.5(l) sign-off, or needs its own written Statement of Compliance
- CSV/record lock mechanism (options: OneDrive-style version history + scheduled lock, checksum/hash file, restricted edit permissions)

## Corrections Log
- **[07/10/2026]** Correction: record storage location is **Google Drive**, not OneDrive as previously logged. Per-person folders, UAV Academy personnel access only. Other terms of the 03/09/2026 sign-off (session-code ID scheme, CSV lock mechanism still TBC) unchanged.

## MFE Fighter — MTOW/Payload Conflict Resolved
- **[07/10/2026]** Two prior dated logs disagreed on MFE Fighter MTOW/payload: one (25/08/2026) cited 13.5kg/2.5kg from MFE's official product page; a later one (06/10/2026) reverted to 11.5kg/1.5kg from the manual + 3dxr.co.uk, without addressing why the manufacturer-page source was set aside. **Tony confirmed 11.5kg / 1.5kg is correct.** This is now the settled figure for all simulator mass/payload configuration.

## Failure Injection Non-Functional Under Gazebo Harmonic — Confirmed by Test (15/10/2026)

Tested on the live build: Getac X600, native Ubuntu, PX4 v1.15.4, `gz_standard_vtol`,
world `training_area`, `SYS_AUTOSTART=4004`. Run via Claude Code with console output logged.

Build is not pure v1.15.4. One local modification found in GZBridge.cpp: lockstep startup timeout raised from 10000 to 60000. It does not touch failure handling. Recorded because “PX4 pinned to v1.15.4” is settled architecture and this is a deviation from it.

With `SYS_FAILURE_EN` confirmed set to 1, `failure gps off` produced:

    WARN  [failure] inject failure unit: gps (4), type: off (1), instance: 0
    ERROR [failure] Timeout waiting for ack
    Command 'failure' failed, returned 1.

The command dispatched (GPS = unit 4, `off` = type 1) and no acknowledgement returned.
Three independent sources now agree: the v1.15 failure-injection docs name only Gazebo
Classic as supported; PX4 issue 23602 reports that GZBridge does not handle
VEHICLE_CMD_INJECT_FAILURE; and this test reproduces it on our own build.

**Relationship to PX4 issue 22296 — OPEN, not resolved.** The "Still Open" section of this
log attributes broken native GPS failure injection to issue 22296. Our failure mode matches
the mechanism described in issue 23602 instead. Whether 22296 and 23602 describe the same
fault, two different faults, or whether 22296 is a stale attribution has NOT been
determined — issue 22296 has not been read. Do not treat either issue number as the
confirmed cause until that is checked.

**Compliance effect:** the GPS proxy is a response to a known upstream simulator
limitation, not a local workaround. This strengthens the CAP722B 5.5(l) Statement of
Compliance case. Acceptability still requires Accountable Manager / Head of Training
sign-off.

**Full v1.15.4 failure command inventory captured for the first time** (not published in
PX4 docs). Components (15): gyro, accel, mag, baro, gps, optical_flow, vio,
distance_sensor, airspeed, battery, motor, servo, avoidance, rc_signal, mavlink_signal.
Types (8): ok, off, stuck, garbage, wrong, slow, delayed, intermittent. Syntax:
`failure <component> <type> [-i <instance>]`, instance 0 = all. The types slow, delayed,
intermittent and garbage are the gradual-degradation behaviours the 03/09/2026 sign-off
requested. NONE are verified to work.

Scope of what this test proved, per a source check of our own tree: in v1.15.4 the GZ bridge does not handle sensor failure injection — GPS and the other sensors are handled only in SimulatorMavlink, the Gazebo Classic path. That is consistent with issue 23602. Motor failures are handled in the commander’s FailureDetector and battery failures in BatterySimulator, so the GPS result says nothing about motor or battery injection — separate code paths, both untested. Every component on the list must be tested individually. Whether FailureDetector (whose role is failure detection) is also the path that services an injected motor failure has not been established; treat the motor path as unverified in both directions.

Open question retained: how our existing motor/engine failure injection (23.08.2026) actually works has not been established. The GPS result does not bear on it either way.

Airspeed — RESOLVED, concern withdrawn. Settled from the ULog. The sensor is present and works; it simply starts late. airspeed_validated begins at t=2.09 s with valid=0, index −1, no value; “No airspeed sensor detected. Switch to non-airspeed mode.” is logged at t=2.088 s. First valid sample at t=8.29 s, index 1 selected from then on, and from t=8.29 s to the end of the run (t=2922.9 s) there were zero invalid samples and no missing values — last invalid sample t=8.09 s. Logged topics: airspeed, airspeed_validated, airspeed_wind (two instances), differential_pressure. Device ID 1377548, error count 0 throughout. On the ground, indicated airspeed ranged −2.6 to +2.4 m/s (median 0.08), differential pressure −3.35 to +3.1 Pa — noise around zero, as expected when stationary. Estimated wind 0 throughout; airspeed-based wind estimate scale factor 1.0.

The startup message came from the airspeed selector checking for a sensor about 6 s before any sensor data arrived. The vehicle was in non-airspeed mode for roughly the first 6 seconds only. The earlier concern about a fixed-wing VTOL trainer running without airspeed does not hold.

Residual questions, none investigated: why the sensor data starts late — a sensor absent for the first ~6 s could still matter in a fast-start scenario where takeoff is commanded immediately after boot; airspeed.confidence reads 0 in every sample; differential_pressure temperature reads 275.1 in a field PX4 treats as °C, which looks like a Kelvin value (≈2 °C). The last two may be quirks of how the Gazebo bridge fills these fields rather than faults.

Residual link to earlier work, retained deliberately: if the 23.08.2026 takeoff/transition bugs occurred shortly after boot, the ~6 s window with no valid airspeed could still be relevant — the steady-state concern is withdrawn, this one is not. Worth checking the timestamps on those earlier logs before closing it. Bears on CAP722B 5.5(h), failure and sensor modelling fidelity, only if that link holds.

GPS drift warnings — RESOLVED, no effect from the injection. Settled from the ULog, not the console. The command appears in vehicle_command at t=19.232 s (command 420, param1=4 GPS, param2=1 off) with no matching ack; “Timeout waiting for ack” at t=20.24 s. GPS data did not change: sensor_gps showed fix 3, 10 satellites, eph 0.900, epv 1.780 identically before and after — but its 1 Hz rate in the log is the logger’s sampling limit for that topic (src/modules/logger/logged_topics.cpp:216), not the GPS output rate, so a dropout shorter than about a second would not appear there. The conclusion rests on vehicle_gps_position, logged at 8.0 Hz with the same values throughout and a largest gap of 0.128 s. estimator_status.gps_check_fail_flags stayed 0 until ~480 s, then showed 64 (horizontal drift) and 128 (vertical drift) intermittently. First drift warning t=497.8 s — 478 s after the command — vertical at 855.9 s, yaw estimate error at 1061.8 s. EKF horizontal drift-rate peaked at 0.097 m/s before 480 s versus 0.113 m/s around the warning: noise on a stationary vehicle crossing a threshold. Within everything examined — the GPS topics and the EKF GPS check flags — the injection produced no change, and the warnings are unrelated to it. No other subsystem was checked. The drift-rate reading (“noise crossing a threshold”) is an interpretation of the data, not a verified explanation; the threshold parameters were not examined. Threshold parameter values not checked.

Timebase note, applies to every timestamp in this entry. All ULog times are simulation time. In this run simulation time ran slower than the clock — about 2280 s of sim time over roughly 90 minutes of wall clock. Any figure here converted to minutes is sim-time minutes.

Method note: the console made the warnings look immediate because console lines carry no timestamps. A screen reading suggested a partial effect; the log showed none.

Side observation, from this one run only — this world, this airframe, not established as general behaviour: with the aircraft stationary, the GPS horizontal drift check first tripped at t=497.8 s, vertical at t=855.9 s, yaw estimate error at t=1061.8 s. All of those are simulation time, not clock time. This run covered roughly 2280 s of simulation time across about 90 minutes of wall clock, so by a wristwatch they appear considerably later. Flagged because an instructor seeing these during a briefing pause might reasonably report them as a fault.

**Incidental observations — not investigated:** Preflight Fail: Attitude failure (roll) first appears just after param set SYS_FAILURE_EN 1 (log line 56), not at boot — probably unrelated to the parameter, but this log does not show it as pre-existing, and it was not investigated; four `gz_frame_id` SDF warnings, each emitted twice — the first four reference our own standard_vtol/model.sdf (lines 385, 469, 481, 537) for chase_camera, payload_camera, payload_lrf and fpv_camera; the second four reference `<data-string>` (lines 416, 536, 565, 640), the copy made when the model spawns; logger starts at boot rather than at arming, which bears on the
open assessment-log-format question.

Open question raised — which clock does the 45-second timeout use? The 45-second no-response timeout for failure-response logging was signed off 03/09/2026 as final. Simulation time and wall clock differ, and by a variable amount. If the instructor station measures sim time, a student’s real thinking time changes with how fast the simulation happens to run. If it measures wall clock, the figure is stable but will not line up with ULog timestamps an auditor cross-checks against. Either may be acceptable — but the question has not been asked, and a record that cannot say which clock it used is weak evidence. Needs checking against the instructor station’s implementation, and may need Head of Training sign-off if the answer changes what a student experiences.
