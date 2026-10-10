# ArduPilot SITL + Gazebo simulation

Set up 6 Sep 2026. This machine now has, alongside the existing PX4 setup:

## What's installed

| Thing | Location | Built how |
|---|---|---|
| ArduPilot source + ArduPlane SITL binary | `~/ardupilot/` , binary at `~/ardupilot/build/sitl/bin/arduplane` | `./waf configure --board sitl && ./waf plane` — no sudo needed |
| `ardupilot_gazebo` plugins | `~/ardupilot_gazebo/build/` (`libArduPilotPlugin.so` + camera/parachute) | cmake/make — no sudo |
| Python deps (`empy==3.3.4`, `MAVProxy`, `pymavlink`) | `~/.local/` | `pip3 install --user` |
| RapidJSON headers (dependency of the plugin) | `~/.local/include/rapidjson/` | vendored from source — `rapidjson-dev` isn't installable without sudo |

**Nothing needed `sudo`** — the Gazebo dev headers (`libgz-sim8-dev`,
`libopencv-dev`) were already installed for the PX4 side, and everything
else went into `~/.local` or a userspace build.

## Running it (not yet done / not yet tested)

```bash
# terminal 1 - Gazebo with the plugin + resource paths
export GZ_SIM_SYSTEM_PLUGIN_PATH=$HOME/ardupilot_gazebo/build:$GZ_SIM_SYSTEM_PLUGIN_PATH
export GZ_SIM_RESOURCE_PATH=$HOME/ardupilot_gazebo/models:$HOME/ardupilot_gazebo/worlds:$HOME/PX4-Autopilot/gcs_app/sim/models:$GZ_SIM_RESOURCE_PATH
gz sim -v4 -r <world>.sdf

# terminal 2 - ArduPlane SITL talking to Gazebo
export PATH=$HOME/.local/bin:$PATH
cd ~/ardupilot
./Tools/autotest/sim_vehicle.py -v ArduPlane -f gazebo-<frame> --model JSON --console --map
```

A first sanity check should use a stock model (`zephyr_with_ardupilot`
or `iris_with_ardupilot`) to prove the SITL↔Gazebo JSON bridge works on
this machine before touching the Fighter model.

## The Fighter model

`sim/models/mfe_fighter/` — **first draft only**, adapted from ArduPilot's
`alti_transition_quad`. So far only the mass and the ArduPilotPlugin
channel map have been changed to match the real aircraft's
`Fighter_VTOL_V4.6.3.param`. Geometry, aero, thrust and inertia are still
the Alti's and need the CAD data + sim tuning. See the model's own
`model.config` and `docs/mfe-fighter-sim-model-plan.md`.

## Instructor station note

`gcs_app/instructor_station.py` and its `simulator_link.py` speak PX4
MAVLink (PX4 custom-mode numbers, PX4 command semantics). Pointed at an
ArduPilot SITL instead, the mode buttons (HOLD / Manual / Position /
FORWARD FLIGHT etc.) will not work correctly — ArduPilot's mode
enumeration is completely different. Adapting the station for ArduPilot
is its own task, tracked separately.
