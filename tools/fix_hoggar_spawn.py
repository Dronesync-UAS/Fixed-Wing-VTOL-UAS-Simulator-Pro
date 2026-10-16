"""Removes the invisible safety-floor slab from the Hoggar world and puts the
spawn back on the real ground:

    python3 tools/fix_hoggar_spawn.py --dry-run
    python3 tools/fix_hoggar_spawn.py
    python3 tools/fix_hoggar_spawn.py --revert

What is wrong. training_area.sdf contains `spawn_area_safety_floor`: a
900 m x 900 m collision-only box whose top face is at Z=615.5, added 23 Aug
2026 as a backup surface while the resting-drift problem was being chased. The
spawn is 615.5 m, so the aircraft rests on that slab - confirmed in the sim,
which reported it at Z=615.595, the same 0.095 m offset it shows when sitting
on ordinary ground.

The carved clearing underneath is at 604.8 m. So the aircraft sits on an
invisible platform **10.7 m above the visible terrain**, takes off from
nothing, and looks wrong from every camera angle - the ground is not where the
aircraft is.

The fix: delete the slab and spawn at 605.1 m, which is ground + 0.3 m, the
same convention every other world uses. The terrain now has a 600 m carved
clearing and the <surface> block copied from Gazebo's known-good ground_plane,
so the backup surface has nothing left to back up.

If the aircraft then sinks or ends up under the visible ground, that is a
genuine rendering-versus-physics mismatch in the heightmap (gazebosim/gz-sim#1295,
which the 23 Aug entry already flags for this world) and this world should be
parked in favour of the three flat ones that work. --revert puts the slab back.
"""
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
REPO_WORLDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "sim", "worlds")
WORLD_FILE = "training_area.sdf"
SUFFIX = ".prespawn"

MODEL_NAME = "spawn_area_safety_floor"
NEW_SPAWN_Z = 605.1     # clearing floor 604.8 + 0.3, as the other worlds do


def targets():
    return [os.path.join(base, WORLD_FILE) for base in (PX4_WORLDS, REPO_WORLDS)
            if os.path.isfile(os.path.join(base, WORLD_FILE))]


def revert():
    restored = 0
    for path in targets():
        backup = path + SUFFIX
        if os.path.isfile(backup):
            shutil.copy2(backup, path)
            print(f"restored {path}")
            restored += 1
    print(f"\n{restored} file(s) restored." if restored else
          f"\nNo {SUFFIX} backups found - nothing to restore.")
    print("Remember to put the spawn height back to 615.5 in tools/start_world.sh\n"
          "and sim_target.py if you reverted after applying.")
    return 0


def strip_model(text):
    """Remove the safety-floor model and the comment block introducing it.

    Done on the text rather than the parse tree so every other line keeps its
    exact formatting and comments - a world file is read by people.
    """
    pattern = re.compile(
        r"[ \t]*<!--[^<]*?SAFETY FLOOR.*?-->\s*"            # its comment block
        r"[ \t]*<model name=\"" + re.escape(MODEL_NAME) + r"\">.*?</model>\s*",
        re.S)
    new, count = pattern.subn("", text)
    if count:
        return new, count
    # Comment block absent or reworded: take just the model.
    pattern = re.compile(
        r"[ \t]*<model name=\"" + re.escape(MODEL_NAME) + r"\">.*?</model>\s*", re.S)
    return pattern.subn("", text)


def main(dry_run):
    paths = targets()
    if not paths:
        print(f"{WORLD_FILE} not found in {PX4_WORLDS} or {REPO_WORLDS}")
        return 1

    failed = 0
    for path in paths:
        with open(path) as handle:
            text = handle.read()
        if MODEL_NAME not in text:
            print(f"SKIP  {path}: no {MODEL_NAME} - already done")
            continue

        new_text, count = strip_model(text)
        if not count:
            print(f"SKIP  {path}: could not isolate the model - left alone")
            continue

        if dry_run:
            removed = len(text.splitlines()) - len(new_text.splitlines())
            print(f"WOULD EDIT {path}: remove {MODEL_NAME} ({removed} lines)")
            continue

        backup = path + SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as handle:
            handle.write(new_text)

        try:
            ET.parse(path)
        except ET.ParseError as exc:
            shutil.copy2(backup, path)
            print(f"FAIL  {path}: XML broke ({exc}) - reverted")
            failed += 1
            continue
        print(f"OK    {path}: {MODEL_NAME} removed")

    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
        return 0
    if failed:
        return 1

    print(f"""
Spawn height must change too - it is {NEW_SPAWN_Z} m now, not 615.5:
  tools/start_world.sh  and  sim_target.py  are already set to {NEW_SPAWN_Z}
  in this version, so just relaunch:

    bash tools/start_world.sh hoggar

Then check where it ends up:

    gz model -m standard_vtol_0 -p

  Z around {NEW_SPAWN_Z:.0f}       -> sitting on the real ground. Fixed.
  Z far below, or still falling    -> the heightmap's physics and rendering
                                      disagree (gz-sim#1295). Park this world
                                      and use Black Rock; the three flat
                                      worlds do not have this problem.

To undo:  python3 tools/fix_hoggar_spawn.py --revert""")
    return 0


if __name__ == "__main__":
    if "--revert" in sys.argv:
        sys.exit(revert())
    sys.exit(main("--dry-run" in sys.argv))
