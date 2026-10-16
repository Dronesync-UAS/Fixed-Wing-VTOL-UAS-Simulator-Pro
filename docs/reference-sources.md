# Where the answers come from

Two upstream projects decide almost everything this station does. When a
question is about how QGroundControl behaves, or what PX4 will accept,
**read the source rather than guess** — both are public, and both have
already settled arguments in this project that guesswork had got wrong.

## QGroundControl

| | |
|---|---|
| Site and user guide | <https://qgroundcontrol.com/> → <https://docs.qgroundcontrol.com/master/en/qgc-user-guide/index.html> |
| Source | <https://github.com/mavlink/qgroundcontrol> |
| Version installed here | **v5.1.5**, commit `3a67d31` — `~/Downloads/QGroundControl-v5.1.5-x86_64.AppImage` |
| Its settings on this machine | `~/.config/QGroundControl/QGroundControl.ini` |

Read a file at the exact installed version:

```bash
curl -s https://raw.githubusercontent.com/mavlink/qgroundcontrol/v5.1.5/src/Toolbar/FlyViewToolBar.qml
```

List the whole tree at that version:

```bash
curl -s "https://api.github.com/repos/mavlink/qgroundcontrol/git/trees/v5.1.5?recursive=1"
```

**What it has already settled here.** Every layout number in
`console_qgc.py` came from this source, not from measuring a screenshot:
the 66 px toolbar and 44 px logo from `QGCToolBarButton.qml`, the 56 px
tool strip from `ToolStrip.qml`, the 6 px margin from
`FlyViewWidgetLayer.qml`, the dark palette from `QGCPalette.cc`, the
telemetry bar and instrument panel sharing one row from
`FlyViewBottomRightRowLayout.qml`, the view menu from
`SelectViewDropdown.qml`, and the heartbeat filter from
`MultiVehicleManager::_vehicleHeartbeatInfo`. The settings page names
came from the user guide.

The useful directories: `src/Toolbar` (29 indicators), `src/FlyView`
(59 files), `src/PlanView` (44), `src/AnalyzeView` (17),
`src/AppSettings` (29), `src/AutoPilotPlugins` (vehicle setup).

**Licence:** dual Apache-2.0 / GPLv3. Copying *layout and numbers* is
fine; copying code is a licence decision nobody has taken here.

## PX4

| | |
|---|---|
| Source | <https://github.com/px4/px4-autopilot/> |
| Version here | **v1.15.4**, cloned at `~/PX4-Autopilot` — so it can be read locally, no network needed |

```bash
grep -rn "SIM_GPS_USED" ~/PX4-Autopilot/src/modules/simulation/
```

**What it has already settled here.** `SensorGpsSim.cpp` gives a 3D fix at
4 satellites or more, which is why the GPS-failure control sets
`SIM_GPS_USED` to 0 rather than running a proxy. `gz_bridge` in v1.15.4
has no failure-injection handling at all, which is why
`MAV_CMD_INJECT_FAILURE` silently did nothing. `streams/STATUSTEXT.hpp`
guards its whole send on `is_gcs_connected()`, and `mavlink_receiver.cpp`
sets that only on a `MAV_TYPE_GCS` heartbeat — which is why this station
received no messages at all until it started sending one.
`mavlink_main.cpp` shows which streams each `-m` mode carries, and
`px4-rc.mavlink` shows which port runs in which mode.

The local clone matters: these are the questions that get answered wrongly
when guessed, and `grep` over `~/PX4-Autopilot` answers them in seconds.

## The habit

The decision log has several entries that exist because something was
assumed instead of read — the ground that ignored its material, the
heartbeat that was decoded as the aircraft, the clause numbers nobody had
checked, the messages PX4 was never asked for. In every case the answer
was sitting in one of these two repositories, or in the CAA's own PDF.

Measure, or read the source. Do not reason about what it probably does.
