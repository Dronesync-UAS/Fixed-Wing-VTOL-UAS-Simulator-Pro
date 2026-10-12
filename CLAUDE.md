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

## Checking a machine is set up

These two are for a machine, not for a commit. Neither changes anything.

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
