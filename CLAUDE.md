# Working on this project

## Who this is for

The person maintaining this project is an instructor, not a developer.
Instructions have to be literal: which window to click, what to type, what
to expect back. Assume nothing about terminals, branches, editors or shell
syntax.

## Giving commands

**One command per code block. Always.** A block holding several lines gets
pasted as one lump, and when something fails there is no way to tell which
line did it. Four commands means four blocks, in order, with a note to wait
for each to finish.

Never put a placeholder in a command. `<world>.sdf` and
`/path/from/step2.sdf` have both been pasted literally and both failed -
work out the real path and write it out.

Never ask for XML or multi-line text to be pasted into a shell. Bash reads
`<` and `>` as redirections. Use an editor, or write the file from here.

Say which window a command belongs in. PX4's own commands (`param`,
`commander check`) only work at its `pxh>` prompt, not at the `$` shell -
that has caught people out more than once.

## Writing code and comments

Comments say WHY, not what. The decision log in `docs/decision-log/` is the
long form: one file per decision, named `DD.MM.YYYY decisions-log-<topic>.md`.

State plainly what has and has not been tested. "Confirmed in flight" and
"never run against Gazebo" are both useful; "should work" is not. If a
feature only does half of what was asked, say which half.

## Before committing

Run the offline checks - they need neither PX4 nor Gazebo:

```
python3 tools/offline_render_check.py
```

After changing the console's page or its JavaScript, also run the browser
check - the console is mostly JavaScript, and a syntax error in it shows as
a black screen that the offline check cannot see:

```
python3 tools/test_console_browser.py
```

The console the station opens by default is the QGC-shaped one
(`console_qgc.py`, served at `/`). After changing it - or changing which
page `/` serves - run:

```
python3 tools/test_pro_console.py
```

The three consoles are all still served: `/` the QGC-shaped one,
`/console` the one before it, `/classic` the original panel grid.

After changing the flight display (`flight_display.py`), run its own check
too - it covers which message is shown in which colour, and exactly when
the low-altitude warning sounds:

```
python3 tools/test_flight_display.py
```

After changing the night-operations pieces - the infrared views, the
lighting control or the aircraft's own lights - run:

```
python3 tools/test_night_ops.py
```

After changing the motor sound, the motor-sound or navigation-light
switches, or the landing gear and gimbal, run:

```
python3 tools/test_sound_and_gear.py
```

After changing the payload gimbal, the chase angles or the console
layout, run:

```
python3 tools/test_payload.py
```

After changing the flight log, run:

```
python3 tools/test_flight_log.py
```

After changing what is in the training areas, run:

```
python3 tools/test_scenery.py
```

After changing the real-terrain fetcher or the satellite imagery
fetcher, run:

```
python3 tools/test_terrain_fetch.py
```

After changing the operating envelope (the CAA 500 m / 100 km choice),
the world files' ground extent, or the satellite fetcher's extent, run:

```
python3 tools/test_range_profile.py
```

After changing mission planning - the patterns, the photogrammetry
figures or the upload - run:

```
python3 tools/test_mission.py
```

After changing the surface maps - the normal, diffuse or roughness
textures, or which world points at which - run:

```
python3 tools/test_surface_maps.py
```

After changing the sky - the dome mesh, the sky image, the scene's
ambient light or the day/night control - run:

```
python3 tools/test_sky.py
```

After changing a world file, or the launcher, run the install check -
there are two copies of every world and only one of them flies:

```
python3 tools/test_install_worlds.py
```

After changing ARM or NEW SESSION, run the recovery check - these two
controls are the ones that bite hardest when they are wrong:

```
python3 tools/test_recovery.py
```

Other tools under `tools/` are self-describing; `--dry-run` and `--revert`
exist on anything that edits world files, and world edits are always backed
up and auto-restored if the result does not parse.

## Five tools edit the worlds, and one tool's --revert undoes the others

`far_ground_apply`, `ground_texture_apply`, `plane_ground_texture`,
`scenery_apply` and `sky_dome_apply` each keep a backup of the world file
**as they found it**. So one tool's `--revert` restores a snapshot that
predates the others and silently undoes them. That happened on 12 Oct
2026: reverting the scenery to re-apply it took the 220 km ground
widening and the real normal maps with it, and everything still parsed.

So after any `--revert`, check what is actually in the worlds:

```
python3 tools/worlds_state.py
```

It prints a table and, if anything is missing, the commands to put it
back in the right order. All five tools are idempotent, so re-running
the lot is always safe. `tools/test_install_worlds.py` runs this check
too.

## Two copies of every world

The worlds in `sim/worlds/` are tracked by git and are what every tool
here edits. The ones in `~/PX4-Autopilot/Tools/simulation/gz/worlds/` are
what PX4 hands to Gazebo, and are the only ones that affect what flies.

So after a `git pull`, and after anything that edits a world file:

```
python3 tools/install_worlds.py
```

`tools/start_world.sh` runs it before launching, and refuses to launch if
it could not install everything. A running Gazebo holds the world file as
it was when it started, so a change needs PX4 and Gazebo restarting.

## Showing it to somebody

A scripted demonstration, recorded to a file. Prints the running order
first so it can be rehearsed:

```
python3 tools/demo_record.py --list short
```

Then, with PX4, Gazebo, the station and the browser all up:

```
python3 tools/demo_record.py short
```

It drives the flying over the station's own interface and PRINTS cues
for the few things that need a click, because the station cannot reach
into the browser. `short` is 60 s and expects the aircraft already
hovering; `full` is 150 s from disarmed.

## Checking a machine is set up

These three are for a machine, not for a commit. None changes anything.

What the machine IS - model, serial number, CPU, memory, graphics, disk,
and the Gazebo and PX4 versions. The graphics line is the one that sets
the simulator's frame rate, and it says plainly whether a discrete card
is fitted:

```
python3 tools/machine_report.py
```

The model and serial number live in DMI, which only root can read, so
those two lines need `sudo python3 tools/machine_report.py`. Everything
else does not.

Nothing running needed - checks the files, the worlds, the aircraft model,
the imagery, and runs all the offline checks:

```
python3 tools/verify_install.py
```

With PX4, Gazebo and the station all up - checks the cameras, the
rangefinder, the gimbal and boom controllers, and the station's own
endpoints:

```
python3 tools/verify_live.py
```

Both print the one command that fixes anything they find, and both end by
listing what they could NOT check - the things that need eyes. A row of
OKs from either is not a statement that the simulator looks right.
