"""Adds the Gazebo systems PX4 ships by default but these worlds don't declare:

    python3 tools/add_world_systems.py --dry-run   # show the change
    python3 tools/add_world_systems.py             # apply it
    python3 tools/add_world_systems.py --revert    # put the backups back

Why: the four training_area*.sdf worlds declare 8 world systems. PX4's own
default list (PX4-gazebo-models/server.config) carries 13, and three of the
missing ones are:

    AirSpeed         - simulated airspeed sensor
    Magnetometer     - simulated magnetometer
    ApplyLinkWrench  - lets external forces/torques be applied to links

This matters because gz-sim8 loads its defaults ONLY when a world declares no
systems of its own ("No systems loaded from SDF, loading defaults" in
SimulationRunner.cc). These worlds do declare systems, so PX4's list is never
consulted and whatever the worlds leave out simply isn't loaded.

**This is an experiment, not a known fix.** The open issue from 22 August is a
VTOL that arms, climbs, holds briefly, then enters an uncommanded spiral with
"Attitude failure (roll/pitch)" and failsafes. A fixed-wing VTOL running without
a simulated airspeed sensor is worth ruling out, and the 22 August entry already
records that the same failure reproduced on the stock PX4 default world - which
at this submodule pin also declares its own systems, so it would have the same
gap. That is a hypothesis with a plausible mechanism, not a diagnosis. Fly it and
see; if nothing changes, revert and the question is closed cheaply.

Adding systems to a world that already declares some is additive and carries
none of the suppression risk that applied to the wind plugin - there are no
defaults left to suppress.

Each file is backed up to <name>.sdf.presystems, the result is re-parsed as XML,
and anything that fails to parse is restored automatically. Re-running skips
systems that are already there.
"""
import glob
import os
import shutil
import sys
import xml.etree.ElementTree as ET

WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
PATTERN = os.path.join(WORLDS, "training_area*.sdf")
SUFFIX = ".presystems"

# filename / name exactly as PX4's own server.config declares them.
SYSTEMS = [
    ("gz-sim-air-speed-system", "gz::sim::systems::AirSpeed",
     "simulated airspeed sensor - the one most likely to matter to a fixed wing"),
    ("gz-sim-magnetometer-system", "gz::sim::systems::Magnetometer",
     "simulated magnetometer, for heading"),
    ("gz-sim-apply-link-wrench-system", "gz::sim::systems::ApplyLinkWrench",
     "allows external forces and torques on links"),
]

PLUGIN_SO_DIRS = ("/usr/lib/x86_64-linux-gnu/gz-sim-8/plugins",
                  "/usr/lib/x86_64-linux-gnu/gz-sim8/plugins")


def plugin_installed(filename):
    """Is the shared library for this system actually on disk? A world that
    names a plugin Gazebo cannot load logs an error and carries on without it,
    which is easy to miss - better to say so up front."""
    for directory in PLUGIN_SO_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if filename.replace("gz-sim-", "gz-sim8-") in name or filename in name:
                return True
    return None if not any(os.path.isdir(d) for d in PLUGIN_SO_DIRS) else False


def revert():
    restored = 0
    for backup in sorted(glob.glob(PATTERN + SUFFIX)):
        target = backup[: -len(SUFFIX)]
        shutil.copy2(backup, target)
        print(f"restored {os.path.basename(target)}")
        restored += 1
    print(f"\n{restored} file(s) restored." if restored else
          f"\nNo {SUFFIX} backups found - nothing to restore.")
    return 0


def apply(dry_run):
    paths = sorted(glob.glob(PATTERN))
    if not paths:
        print(f"No training_area*.sdf found in {WORLDS}")
        return 1

    print("Systems to add:")
    for filename, name, why in SYSTEMS:
        state = plugin_installed(filename)
        mark = {True: "installed", False: "NOT INSTALLED", None: "could not check"}[state]
        print(f"  {name.split('::')[-1]:16} {mark:15} {why}")
    print()

    edited = skipped = failed = 0
    for path in paths:
        base = os.path.basename(path)
        with open(path) as fh:
            lines = fh.read().splitlines(keepends=True)

        joined = "".join(lines)
        wanted = [s for s in SYSTEMS if s[1] not in joined]
        if not wanted:
            print(f"SKIP  {base}: all three already declared")
            skipped += 1
            continue

        # Insert after the world's last existing </plugin>, so the systems stay
        # together, falling back to just before </world>.
        close_world = next((n for n, l in enumerate(lines) if l.strip() == "</world>"), None)
        if close_world is None:
            print(f"SKIP  {base}: no </world> line - left alone")
            skipped += 1
            continue
        insert_at = close_world
        for n in range(close_world - 1, -1, -1):
            if lines[n].strip().endswith("</plugin>"):
                insert_at = n + 1
                break
        indent = lines[insert_at - 1][: len(lines[insert_at - 1])
                                      - len(lines[insert_at - 1].lstrip())] \
            if insert_at > 0 else "    "

        block = "".join(
            f'{indent}<plugin filename="{filename}" name="{name}"></plugin>\n'
            for filename, name, _ in wanted)

        if dry_run:
            print(f"WOULD EDIT {base}: add {len(wanted)} system(s) at line {insert_at + 1}")
            edited += 1
            continue

        backup = path + SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as fh:
            fh.writelines(lines[:insert_at] + [block] + lines[insert_at:])

        try:
            ET.parse(path)
        except ET.ParseError as exc:
            shutil.copy2(backup, path)
            print(f"FAIL  {base}: XML broke ({exc}) - reverted")
            failed += 1
            continue

        names = ", ".join(n.split("::")[-1] for _, n, _ in wanted)
        print(f"OK    {base}: added {names}")
        edited += 1

    print(f"\nedited={edited} skipped={skipped} failed={failed}")
    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    elif edited and not failed:
        print("""
Now fly it and watch for the 22 August failure - arm, take off, and see whether
it still spirals after 3-10 seconds with "Attitude failure (roll/pitch)".

  Changed            -> the missing systems were involved; tell me what changed.
  Identical          -> they were not the cause. Revert and we look elsewhere:
                          python3 tools/add_world_systems.py --revert
  Worse, or it won't
  start              -> revert, and send me what the PX4 console printed.

Either answer is worth having. While you are flying, also check wind from 270
pushes the aircraft EAST, and how the rear-and-above view frames it.""")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--revert" in sys.argv:
        sys.exit(revert())
    sys.exit(apply("--dry-run" in sys.argv))
