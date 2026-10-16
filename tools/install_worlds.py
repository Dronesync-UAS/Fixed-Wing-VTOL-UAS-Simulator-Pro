#!/usr/bin/env python3
"""
Copy the training worlds from this repository into the place the
simulator actually loads them from.

    python3 tools/install_worlds.py --list
    python3 tools/install_worlds.py --dry-run
    python3 tools/install_worlds.py

WHY THIS EXISTS, and it is the most important note in this folder.

There are TWO copies of every world. The one in this repository's
sim/worlds/ is tracked by git and is what every tool here edits -
scenery_apply, far_ground_apply, weather_apply, fix_magnetic_field, all
of them. The one in ~/PX4-Autopilot/Tools/simulation/gz/worlds/ is the
one PX4 hands to Gazebo, and is the ONLY one that affects what flies.

Until 12 Oct 2026 nothing copied the first to the second. The
consequence, found by verify_live.py on the instructor's machine: the
six training areas added that day had never been installed, so they
could not be flown at all, and the ground widening had reached only
flat_test - the one world start_world.sh happened to copy on its way
past.

That is the whole reason for this file. Run it after a git pull, and
after any tool that edits a world.

WHAT IT COPIES
  * every sim/worlds/*.sdf
  * every file under sim/worlds/media/ that a world refers to, because a
    world whose heightmap is missing loads as an empty void with no
    error that says why.

WHAT IT WILL NOT DO
  * It will not quietly overwrite a world in PX4's tree that is NEWER
    than the repository's copy. That is somebody's local edit, and
    losing it silently is worse than refusing. --force overwrites it,
    and a backup is kept either way.
  * It does not touch the aircraft model. That is PX4's own file and
    gimbal_apply.py, aircraft_legs_apply.py and chase_angles_apply.py
    edit it in place.

NOT TESTED AGAINST A RUNNING GAZEBO. The copying and the comparison are
checked by tools/test_install_worlds.py; nobody has yet watched a
freshly installed world load.
"""

import argparse
import filecmp
import glob
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_WORLDS = os.path.join(REPO, "sim", "worlds")
REPO_MEDIA = os.path.join(REPO_WORLDS, "media")
PX4_WORLDS = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/worlds")
PX4_MEDIA = os.path.join(PX4_WORLDS, "media")

BACKUP_SUFFIX = ".preinstall"

# file://media/<name> inside a world file. Anything a world asks for has
# to travel with it.
MEDIA_REF = re.compile(r"file://media/([A-Za-z0-9_.-]+)")


def repo_worlds():
    return sorted(glob.glob(os.path.join(REPO_WORLDS, "*.sdf")))


def media_needed():
    """Every media file any world refers to, as a set of bare names."""
    wanted = set()
    for path in repo_worlds():
        with open(path) as handle:
            wanted.update(MEDIA_REF.findall(handle.read()))
    return sorted(wanted)


def state(repo_path, px4_path):
    """What copying this one would do: "new", "same", "older" (the repo's
    is newer, so copying is an update), or "newer" (PX4's is newer, so
    copying would throw away somebody's edit)."""
    if not os.path.exists(px4_path):
        return "new"
    if filecmp.cmp(repo_path, px4_path, shallow=False):
        return "same"
    if os.path.getmtime(px4_path) > os.path.getmtime(repo_path):
        return "newer"
    return "older"


def copy_one(repo_path, px4_path, force, dry_run):
    name = os.path.basename(repo_path)
    how = state(repo_path, px4_path)

    if how == "same":
        return "same", "%-30s already identical" % name
    if how == "newer" and not force:
        return "refused", ("%-30s REFUSED - the copy in PX4's tree is newer "
                           "than this one.\n%sSomething edited it there. "
                           "--force overwrites it (a backup is kept)."
                           % (name, " " * 38))

    if dry_run:
        return "would", "%-30s would %s" % (
            name, "be installed" if how == "new" else "be updated")

    os.makedirs(os.path.dirname(px4_path), exist_ok=True)
    if os.path.exists(px4_path):
        shutil.copyfile(px4_path, px4_path + BACKUP_SUFFIX)
    shutil.copyfile(repo_path, px4_path)
    return "done", "%-30s %s" % (name,
                                 "installed" if how == "new" else "updated")


def check_parses(path):
    try:
        ET.parse(path)
        return True
    except ET.ParseError:
        return False


def do_list():
    print("Worlds\n")
    print("  %-30s %-12s %s" % ("FILE", "IN PX4", "NOTE"))
    missing = 0
    for path in repo_worlds():
        how = state(path, os.path.join(PX4_WORLDS, os.path.basename(path)))
        note = {"new": "NOT INSTALLED - cannot be flown",
                "same": "",
                "older": "out of date in PX4's tree",
                "newer": "PX4's copy is newer - edited there"}[how]
        print("  %-30s %-12s %s" % (os.path.basename(path),
                                    "no" if how == "new" else "yes", note))
        if how != "same":
            missing += 1

    print("\nMedia the worlds refer to\n")
    for name in media_needed():
        here = os.path.isfile(os.path.join(REPO_MEDIA, name))
        there = os.path.isfile(os.path.join(PX4_MEDIA, name))
        print("  %-34s repo %-4s PX4 %s" % (name, "yes" if here else "NO",
                                            "yes" if there else "NO"))

    print()
    if missing:
        print("%d world file(s) differ. To put the repository's copies in "
              "place:" % missing)
        print("    python3 tools/install_worlds.py")
    else:
        print("Every world in this repository is installed and identical.")
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--list", action="store_true",
                        help="what is installed, what is not, what differs")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would be copied, copy nothing")
    parser.add_argument("--force", action="store_true",
                        help="overwrite a copy in PX4's tree that is newer "
                             "than this one (a backup is kept)")
    parser.add_argument("--revert", action="store_true",
                        help="put back the backups this script made")
    args = parser.parse_args()

    if not os.path.isdir(PX4_WORLDS):
        print("Not found: %s" % PX4_WORLDS)
        print()
        print("That is where PX4 keeps the worlds it hands to Gazebo. If")
        print("PX4-Autopilot is somewhere else on this machine, nothing")
        print("here can find it.")
        return 1

    if args.revert:
        print("Putting back the previous copies:\n")
        put_back = 0
        for path in glob.glob(os.path.join(PX4_WORLDS, "*" + BACKUP_SUFFIX)):
            target = path[:-len(BACKUP_SUFFIX)]
            shutil.copyfile(path, target)
            os.remove(path)
            print("  %-30s put back" % os.path.basename(target))
            put_back += 1
        print("\n%d file(s) put back." % put_back)
        return 0

    if args.list:
        return do_list()

    # Anything that does not parse must not be copied: a broken world
    # file in PX4's tree is a simulator that will not start, and the
    # error Gazebo gives for it does not say which file.
    broken = [os.path.basename(p) for p in repo_worlds()
              if not check_parses(p)]
    if broken:
        print("These world files do not parse, so nothing was copied:")
        for name in broken:
            print("  " + name)
        return 1

    print("%s %s\n  -> %s\n"
          % ("Would install" if args.dry_run else "Installing",
             REPO_WORLDS, PX4_WORLDS))

    results = []
    for path in repo_worlds():
        how, message = copy_one(
            path, os.path.join(PX4_WORLDS, os.path.basename(path)),
            args.force, args.dry_run)
        results.append(how)
        print("  " + message)

    print("\nMedia:\n")
    for name in media_needed():
        source = os.path.join(REPO_MEDIA, name)
        if not os.path.isfile(source):
            print("  %-30s NOT IN THIS REPOSITORY - a world refers to it"
                  % name)
            results.append("refused")
            continue
        how, message = copy_one(source, os.path.join(PX4_MEDIA, name),
                                args.force, args.dry_run)
        results.append(how)
        print("  " + message)

    print()
    changed = sum(1 for r in results if r in ("done", "would"))
    same = sum(1 for r in results if r == "same")
    refused = sum(1 for r in results if r == "refused")
    print("%d changed, %d already identical, %d refused."
          % (changed, same, refused))
    if refused:
        print("\nA refusal means PX4's copy is newer than this repository's,")
        print("or a file a world needs is not in this repository at all.")
        print("Nothing was lost - read the lines above.")
    if changed and not args.dry_run:
        print("\nRestart PX4 and Gazebo for this to take effect. A running")
        print("Gazebo holds the world file as it was when it started.")
    return 1 if refused else 0


if __name__ == "__main__":
    sys.exit(main())
