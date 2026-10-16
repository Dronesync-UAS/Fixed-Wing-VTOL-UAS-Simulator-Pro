# UAS Academy — Where Things Live

One pointer file instead of guessing. Nothing in this project is duplicated
across locations — each item below has exactly one home.

## Code (not moved — active, path-coupled, already on GitHub)

- **PX4 + simulator + UAV Academy GCS Pro:** `~/PX4-Autopilot/` (23GB source/build
  tree; git repo). The actual instructor console app is nested at
  `~/PX4-Autopilot/gcs_app/` — its own git repo, remote:
  `https://github.com/Dronesync-UAS/Fixed-Wing-VTOL-UAS-Simulator-Pro`
  (renamed from `uas-instructor-station` ~5 Sep 2026).
- **Starting a session:** the **UAV Academy Simulator** desktop icon, or
  `python3 gcs_app/tools/uas_launcher.py`. It starts Gazebo, PX4 and the
  station together in one chosen training area, so the simulator and the
  console can no longer be pointed at different worlds. Install the icons
  with `gcs_app/tools/install_launcher.sh`. Logs land in
  `~/uas_sim_logs/sim_launch.log` and `~/uas_sim_logs/gcs.log`.
- **Live flight-event log (CSV):** `~/uas_sim_logs/instructor_events.csv` —
  path is hardcoded into `gcs_app/event_logger.py`; don't move without
  updating that code. Backed up daily to `Flight-Logs/instructor-events/`
  (cron, 20:30).
- **ArduPilot SITL** (added 6 Sep 2026, built without sudo):
  `~/ardupilot/` (source + `build/sitl/bin/arduplane`), plugin at
  `~/ardupilot_gazebo/build/`, rapidjson vendored to `~/.local/include/`.
  Setup notes: `gcs_app/sim/README.md`. Verified: the ArduPilot Gazebo
  plugin loads in Gazebo Harmonic on this machine; SITL binary runs.
  Not yet flown; instructor station still speaks PX4 not ArduPilot.
- **Superseded prototype**, kept for history only, not used by the live
  app: `~/UAS-Academy/Archive/instructor_panel/`.

## Reference material — now `~/UAS-Academy/UAV-Academy/UAV Academy GCS Pro/`

Moved here from `Reference/` on 5 Sep 2026 (done directly in the OneDrive
web UI, then synced down) so the OneDrive view shows a tidy
`UAV-Academy > UAV Academy GCS Pro` structure instead of loose folders at
the account root. The old `Reference/` folder is gone (was left empty by
the move, then removed). This did **not** touch `Archive/` — the
instructor_panel path below is unaffected.

- `Herelink/` — raw photos/screenshots of the physical Herelink hardware.
  For the *written* Herelink documentation (specs, setup guides, FAQ
  scraped from docs.cubepilot.org), see `gcs_app/docs/herelink-docs.md`
  instead — that one lives with the code since it's specifically referenced
  from there.
- `3DXR/` — **the single, complete home for MFE Fighter material.** Manuals,
  specs docs, CAD pictures, and now also the CAD/RealFlight files and the
  ArduPilot param set, consolidated here from `~/Downloads/MFE Fighter/`
  on 5 Sep 2026 (that source folder is gone - fully emptied and removed,
  no copy left behind).
  - **Current param file:** `3DXR/SITL_Models_RealFlight/Fighter_VTOL_V4.6.3.param`
    - ArduPlane V4.6.3, VTOL fixed-wing variant ("Plane: Fighter VTOL 奋斗者",
      250 params). Confirmed 5 Sep 2026 as the correct one for this
      aircraft - a same-named-but-different file (`Fighter_V4.6.3.param`,
      82 params, no "VTOL" in its own header) is a *different, non-VTOL*
      airframe config, not a version of this one. That file was left in
      Trash, not brought in.
    - **Open question, not yet checked:** whether the RealFlight/CAD
      files sitting alongside (`fighterVTOL_EA.RFX`, `.kex`, `.rfvehicle`)
      were built against this V4.6.3 param set or the older V4.4.4 -
      actuator/servo mappings can drift out of sync across firmware
      revisions if they don't match.
  - `SITL_Models_RealFlight/superseded/Fighter_VTOL_V4.4.4.param` — the
    previous param set, kept for history, not for use.
- `GCS/` — reference photos/screenshots for ground control station
  hardware/setup (QGC screenshots, Striekair, Dock Stream).
- `ARDUPILOT/` — "Mission Planner & ArduPilot" overview/training material.
  Note: this is reference *documentation*, not an ArduPilot SITL
  installation — there is no ArduPilot source/build on this machine yet.

## Inbox — drop new material here anytime

`~/UAS-Academy/Inbox/` — nothing in it yet. Whenever you add something,
ask me to check it and I'll say, for each item: keep it (and where),
flag as a duplicate of something that already exists, or ask you if it's
unclear. Nothing gets moved or deleted from here without you confirming.

## Moved from Documents (5 Sep 2026, checked for zero disruption first)

- **Decision Log** → `gcs_app/docs/decision-log/` (git-tracked, not here) —
  moved out of `~/Documents/Decision Log/`, confirmed first that no code
  referenced that path. Documents this repo's own decision history, so
  it lives with the code rather than in this OneDrive-backed folder.
- **QGroundControl flight logs** → `Flight-Logs/QGroundControl-Telemetry/`
  (28 `.tlog` files) — **copied**, not moved. The originals are still at
  `~/Documents/QGroundControl/Telemetry/`, since that folder is
  QGroundControl's own live application data directory (Parameters,
  Missions, Settings, CrashLogs, etc.) - moving it would disrupt the app
  itself. This is a backup copy only, for the "machine dies" scenario.
- **Instructor event log** → `Flight-Logs/instructor-events/instructor_events.csv`
  — **copied**, not moved, same reasoning: the real file stays at
  `~/uas_sim_logs/instructor_events.csv`, hardcoded into
  `gcs_app/event_logger.py`. This is the actual CAP722B assessment/event
  record (failure timestamps, instructor actions, student response
  times) - arguably the single most important thing to have an
  off-machine copy of. **Caveat: this copy is a one-time snapshot, not a
  live sync** - `~/uas_sim_logs` sits outside OneDrive's `sync_dir`, so
  new events logged after 5 Sep 2026 won't appear here automatically.
  Re-copy periodically, or set up a scheduled refresh, to keep it current.

## Brand assets — `~/UAS-Academy/Brand/`

- `UAV Academy Logo.png` — the flat generic company logo.
- `UAV Academy GCS Pro Icon.png` — the app icon: the logo on a rounded
  square with "GCS Pro" added beneath "ACADEMY". **This is now live** —
  a 512px copy is at `~/.local/share/icons/uav-academy-gcs-pro.png` and
  both desktop launchers point at it. The old `uas-instructor-station.png`
  icon has been deleted.
- The GCS Pro UI design mockup lives with the code at
  `gcs_app/docs/design-mockup-gcs-pro.png` (git-tracked), not here.

## Instructor event log — automatic backup

A cron job (`crontab -l` to see it) copies
`~/uas_sim_logs/instructor_events.csv` into
`Flight-Logs/instructor-events/` every day at 20:30, so the OneDrive
backup stays current instead of being a one-off snapshot. Runs only when
the machine is on at that time - if it's usually off then, adjust the
cron time or run the copy manually.

## Note: this OneDrive account had pre-existing content

Once `sync_dir` was pointed at `~/UAS-Academy`, three items appeared here
that nobody created for this project — Microsoft's own defaults from
before this account was used for this backup: `Folders/`, `Pictures/`,
and `Getting started with OneDrive.pdf` (all dated 2024). Harmless, but
they're not part of this project - the OneDrive client mirrors the
*entire* account root both ways, so anything already up there merges in
locally. Left in place; say the word if you want them cleared out.

## Explicitly left alone (not part of this project)

- Desktop, Documents, Downloads, Music, Public, snap, Templates, Videos —
  per instruction, none of these were touched or moved.
- Inside the "Fixed Wing VTOL UAS Simulator Pro" drive: CAA Sources,
  Training Manual, NPCC, PWC, SKYGATE, STRIEKAIR, TEKEVER, PPL Course,
  ELECTROMAGNETIC SPECTRUM, Pictures, System Volume Information, and the
  loose images/PDFs at its root — these look like separate ventures/topics,
  not this project, so left in place. Say the word if any of these should
  actually move in.
