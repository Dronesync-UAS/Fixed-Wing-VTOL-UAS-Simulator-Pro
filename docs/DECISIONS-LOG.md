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
- Student/instructor identification scheme: SETTLED — first name + session code. Engages UK GDPR/DPA 2018 (CAP722B **2.1(f)**, corrected 14 Oct 2026 - 2.2(f) was cited here for a year and is about nominated persons, not data) from the first logged entry. Records are kept five years under 2.1(g).
- Record retention/storage: SETTLED — each record stored as a file in the student/instructor's dedicated **Google Drive** folder (corrected 07/10/2026 — previously wrongly logged as OneDrive), access restricted to UAV Academy personnel only (no external/public sharing links). Lock/tamper-protection mechanism for the file itself is still TBC.
- VTOL-specific competency/procedure knowledge: SETTLED (approach) — delivered via a dedicated UAV Academy simulator-training session, not built as a simulator feature.

## Still Open / TBC
- Sim flying hours / assessment log format
- Definition of a "correct" student response to an injected failure
- ~~Whether the GPS-failure proxy workaround is an acceptable substitute for CAP722B 5.5(l) sign-off~~ SETTLED 14 Oct 2026, twice over: the proxy is gone (the control now sets PX4's own SIM_GPS_USED, so the loss is real inside PX4's sensor pipeline), and 5.5(l)'s guidance in the document reads "A SOC is sufficient for this requirement" — so what it needs is a written Statement of Compliance, not a sign-off
- CSV/record lock mechanism (options: OneDrive-style version history + scheduled lock, checksum/hash file, restricted edit permissions)

## Corrections Log
- **[07/10/2026]** Correction: record storage location is **Google Drive**, not OneDrive as previously logged. Per-person folders, UAV Academy personnel access only. Other terms of the 03/09/2026 sign-off (session-code ID scheme, CSV lock mechanism still TBC) unchanged.

## MFE Fighter — MTOW/Payload Conflict Resolved
- **[07/10/2026]** Two prior dated logs disagreed on MFE Fighter MTOW/payload: one (25/08/2026) cited 13.5kg/2.5kg from MFE's official product page; a later one (06/10/2026) reverted to 11.5kg/1.5kg from the manual + 3dxr.co.uk, without addressing why the manufacturer-page source was set aside. **Tony confirmed 11.5kg / 1.5kg is correct.** This is now the settled figure for all simulator mass/payload configuration.
