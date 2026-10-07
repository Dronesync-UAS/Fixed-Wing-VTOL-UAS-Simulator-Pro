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
