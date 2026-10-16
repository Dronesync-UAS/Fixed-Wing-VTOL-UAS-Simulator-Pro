"""Adds wind support to the training world files, then checks the result:

    python3 tools/wind_apply.py            # edit all four training_area worlds
    python3 tools/wind_apply.py --dry-run  # show the change, write nothing
    python3 tools/wind_apply.py --revert    # put the backups back

Two things get inserted before </world>:

  <wind><linear_velocity>0 0 0</linear_velocity></wind>
      A world property, not a sensor. Zero, so nothing changes until an
      instructor commands wind - adding this must not alter how the sim
      flies today.

  the WindEffects system plugin
      Safe to add here only because these worlds already declare their own
      systems (8 of them). gz-sim8 skips its default system set entirely
      once a world declares any, so adding a plugin to a world that had
      none would have silently removed physics, IMU, NavSat and the camera.
      Checked by tools/wind_survey.py before this script was written.

Plugin tuning values are copied from gz-sim8's own examples/worlds/wind.sdf
rather than guessed. They shape how wind ramps and gusts; the instructor
sets the actual speed and direction at runtime over
/world/training_area/wind.

Every file is backed up to <name>.sdf.prewind before being touched, the
result is parsed as XML, and any file that fails to parse is restored
automatically. Re-running is harmless - worlds that already have wind are
skipped.
"""
import os, sys, glob, shutil
import xml.etree.ElementTree as ET

WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
PATTERN = os.path.join(WORLDS, "training_area*.sdf")
SUFFIX = ".prewind"

WIND_BLOCK = """\
{i}<!-- Wind: speed/direction are set at runtime by the instructor station over
{i}     /world/NAME/wind (gz.msgs.Wind). Zero here so an untouched sim
{i}     flies exactly as it did before wind was added. -->
{i}<wind>
{i}  <linear_velocity>0 0 0</linear_velocity>
{i}</wind>
{i}<plugin filename="gz-sim-wind-effects-system" name="gz::sim::systems::WindEffects">
{i}  <force_approximation_scaling_factor>1</force_approximation_scaling_factor>
{i}  <horizontal>
{i}    <magnitude>
{i}      <time_for_rise>10</time_for_rise>
{i}      <sin>
{i}        <amplitude_percent>0.05</amplitude_percent>
{i}        <period>60</period>
{i}      </sin>
{i}      <noise type="gaussian">
{i}        <mean>0</mean>
{i}        <stddev>0.0002</stddev>
{i}      </noise>
{i}    </magnitude>
{i}    <direction>
{i}      <time_for_rise>30</time_for_rise>
{i}      <sin>
{i}        <amplitude>5</amplitude>
{i}        <period>20</period>
{i}      </sin>
{i}      <noise type="gaussian">
{i}        <mean>0</mean>
{i}        <stddev>0.03</stddev>
{i}      </noise>
{i}    </direction>
{i}  </horizontal>
{i}  <vertical>
{i}    <noise type="gaussian">
{i}      <mean>0</mean>
{i}      <stddev>0.03</stddev>
{i}    </noise>
{i}  </vertical>
{i}</plugin>
"""


def revert():
    restored = 0
    for backup in sorted(glob.glob(PATTERN + SUFFIX)):
        target = backup[: -len(SUFFIX)]
        shutil.copy2(backup, target)
        print(f"restored {os.path.basename(target)} from backup")
        restored += 1
    print(f"\n{restored} file(s) restored." if restored else
          "\nNo .prewind backups found - nothing to restore.")
    return 0


def apply(dry_run):
    paths = sorted(glob.glob(PATTERN))
    if not paths:
        print(f"No training_area*.sdf found in {WORLDS}")
        return 1

    edited = skipped = failed = 0
    for path in paths:
        name = os.path.basename(path)
        with open(path) as fh:
            lines = fh.read().splitlines(keepends=True)

        joined = "".join(lines)
        if "<wind>" in joined or "WindEffects" in joined:
            print(f"SKIP  {name}: already has wind")
            skipped += 1
            continue

        # Find the world's closing tag and copy its indentation, so the
        # inserted block lines up with whatever style the file already uses.
        close = next((n for n, l in enumerate(lines) if l.strip() == "</world>"), None)
        if close is None:
            print(f"SKIP  {name}: no </world> line found - left alone")
            skipped += 1
            continue
        outer = lines[close][: len(lines[close]) - len(lines[close].lstrip())]
        block = WIND_BLOCK.format(i=outer + "  ")

        if dry_run:
            print(f"WOULD EDIT {name}: insert {block.count(chr(10))} lines "
                  f"before line {close + 1}")
            edited += 1
            continue

        backup = path + SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as fh:
            fh.writelines(lines[:close] + [block] + lines[close:])

        # A world file that no longer parses would stop the sim launching at
        # all, so undo rather than leave it broken.
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            shutil.copy2(backup, path)
            print(f"FAIL  {name}: XML broke ({exc}) - reverted from backup")
            failed += 1
            continue

        print(f"OK    {name}: wind added (backup at {os.path.basename(backup)})")
        edited += 1

    print()
    print(f"edited={edited} skipped={skipped} failed={failed}")
    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    elif edited and not failed:
        print("""
Next, in this order:

1. Restart the sim:
     ~/PX4-Autopilot/start_training_area.sh

2. Check the wind endpoint appeared (new terminal):
     gz topic -l | grep wind
   Expect: /world/training_area/wind
   Nothing listed means the plugin did not load - say so before going on.

3. Take off, get into forward flight, then command wind:
     gz topic -t "/world/training_area/wind" -m gz.msgs.Wind -p "linear_velocity: {x: 8, y: 0, z: 0}, enable_wind: true"
   8 m/s from the south. Watch for drift and a groundspeed/airspeed split.

4. Back to calm:
     gz topic -t "/world/training_area/wind" -m gz.msgs.Wind -p "linear_velocity: {x: 0, y: 0, z: 0}, enable_wind: true"

If step 3 does nothing visible, stop - no instructor control gets wired to
an effect that has not been seen working. To undo everything:
     python3 tools/wind_apply.py --revert""")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--revert" in sys.argv:
        sys.exit(revert())
    sys.exit(apply("--dry-run" in sys.argv))
