#!/usr/bin/env python3
"""
Widen a world's visible ground so a long flight is not flown over a void.

Added 12 Oct 2026 alongside the 100 km instructor envelope in
range_profile.py.

THE PROBLEM. Every world's ground has two parts. The COLLISION is already
a 100 km box, so the aircraft never falls through. The VISUAL is a plane
8 km square, which is plenty for a 500 m exercise and runs out 4 km from
home - so on a long leg the ground simply ends, and past that edge the
chase and nose views show sky and nothing else.

WHAT THIS DOES. Changes one number: the visual plane's <size>. A plane
carries flat colour, not a tiled texture, so making it wider costs
nothing to render and cannot tile visibly. Nothing else in the world
moves.

WHAT IT WILL NOT DO. A world whose ground is a HEIGHTMAP cannot be
widened this way - stretching a heightmap stretches the relief with it,
and dropping a flat apron around it leaves a step at the join as tall as
whatever the terrain happens to be at its own edge (Hoggar's heightmap
spans 1151 m of height in 4 km, so that step could be hundreds of
metres). Those worlds are reported and left alone. For long flights use
one of the plane worlds; the script says which they are.

NOT TESTED AGAINST A RUNNING GAZEBO. The edit is checked by re-parsing
the file and by tools/test_range_profile.py; nobody has yet watched a
widened world load.

Usage, one command at a time, at the $ shell:

    python3 tools/far_ground_apply.py --list
    python3 tools/far_ground_apply.py --all --dry-run
    python3 tools/far_ground_apply.py --all
    python3 tools/far_ground_apply.py --all --revert
"""

import argparse
import glob
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

WORLD_DIR = os.path.join(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))), "sim", "worlds")

# 220 km square: 110 km from home in every direction, which covers the
# 100 km envelope with room to turn round at the far end.
DEFAULT_SIZE_M = 220000

BACKUP_SUFFIX = ".prefarground"

# <plane><size>W H</size></plane> - two numbers, unlike a box's three,
# which is what tells the two apart without walking the whole tree.
PLANE_SIZE = re.compile(
    r"(<plane>\s*(?:<normal>[^<]*</normal>\s*)?<size>)\s*"
    r"([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*(</size>)")

# The ground's COLLISION is a sunken box 100 km square - so the aircraft
# stops falling at 50 km from home, which is half of the 100 km envelope.
# Widened to match the visual, keeping its thickness.
GROUND_COLLISION = re.compile(
    r'(<collision name="ground_collision">.*?<box>\s*<size>)\s*'
    r'([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*(</size>)',
    re.DOTALL)


def worlds():
    return sorted(glob.glob(os.path.join(WORLD_DIR, "*.sdf")))


def ground_kind(text):
    """"plane", "heightmap", or "neither" - what the world STANDS on.

    THE PLANE IS CHECKED FIRST, and the order matters. On 12 Oct 2026
    tools/plane_ground_texture.py added a flat heightmap over the plane
    worlds as a VISUAL, so that a texture could tile. After that every
    world contained a <heightmap> somewhere, and this function - which
    tested for that first - reported all twelve as heightmap worlds. The
    widening then refused to touch any of them and the range-profile
    check failed on both counts.

    What a world stands on is its ground PLANE if it has one. The
    heightmap over the top is decoration.
    """
    if PLANE_SIZE.search(text):
        return "plane"
    if "<heightmap>" in text:
        return "heightmap"
    return "neither"


def current_size(text):
    found = PLANE_SIZE.search(text)
    return (float(found.group(2)), float(found.group(3))) if found else None


def widen(text, size_m):
    """Set the first plane's size, and the ground collision box with it.
    First plane, not all: a world could use a plane for something that is
    not the ground - a road, a lake surface - and the ground plane comes
    first in every world here. The only other <plane> in these files is
    inside a comment, which the pattern cannot match; --list prints the
    count so that stays true."""
    text = PLANE_SIZE.sub(
        lambda m: "%s%d %d%s" % (m.group(1), size_m, size_m, m.group(4)),
        text, count=1)
    return GROUND_COLLISION.sub(
        lambda m: "%s%d %d %s%s" % (m.group(1), size_m, size_m,
                                    m.group(4), m.group(5)),
        text, count=1)


def parses(path):
    try:
        ET.parse(path)
        return True
    except ET.ParseError:
        return False


def apply_to(path, size_m, dry_run):
    name = os.path.basename(path)
    with open(path) as handle:
        text = handle.read()

    kind = ground_kind(text)
    if kind != "plane":
        print("  %-34s SKIPPED - ground is a %s" % (name, kind))
        return "skipped"

    was = current_size(text)
    if was and int(was[0]) == size_m:
        print("  %-34s already %d m" % (name, size_m))
        return "unchanged"

    if dry_run:
        print("  %-34s %d -> %d m" % (name, was[0], size_m))
        return "would"

    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(widen(text, size_m))

    # A world file that does not parse will not load, and finding that
    # out when Gazebo refuses to start is a bad way to find it out.
    if not parses(path):
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse - put back as it was" % name)
        return "failed"

    print("  %-34s %d -> %d m" % (name, was[0], size_m))
    return "done"


def revert(path):
    name = os.path.basename(path)
    backup = path + BACKUP_SUFFIX
    if not os.path.isfile(backup):
        print("  %-34s nothing to put back" % name)
        return "none"
    shutil.copyfile(backup, path)
    os.remove(backup)
    print("  %-34s put back" % name)
    return "reverted"


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("world", nargs="?",
                        help="one world file name, e.g. training_area_coast.sdf")
    parser.add_argument("--all", action="store_true", help="every world")
    parser.add_argument("--list", action="store_true",
                        help="what each world stands on, and how wide it is")
    parser.add_argument("--size-m", type=int, default=DEFAULT_SIZE_M,
                        help="width of the square, in metres (default %d)"
                             % DEFAULT_SIZE_M)
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would change, write nothing")
    parser.add_argument("--revert", action="store_true",
                        help="put back the backup this script made")
    args = parser.parse_args()

    if args.list:
        print("Ground in each world:\n")
        plane_worlds = []
        for path in worlds():
            with open(path) as handle:
                text = handle.read()
            kind = ground_kind(text)
            size = current_size(text)
            extent = ("%d m square" % size[0]) if size else "-"
            print("  %-34s %-10s %s" % (os.path.basename(path), kind, extent))
            if kind == "plane":
                plane_worlds.append(os.path.basename(path))
        print("\n%d of %d worlds can be widened; the rest stand on a "
              "heightmap." % (len(plane_worlds), len(worlds())))
        print("For flights past 4 km from home, use one of these:")
        for name in plane_worlds:
            print("    " + name)
        return 0

    if args.all:
        chosen = worlds()
    elif args.world:
        path = os.path.join(WORLD_DIR, os.path.basename(args.world))
        if not os.path.isfile(path):
            print("No such world: %s" % path)
            return 1
        chosen = [path]
    else:
        parser.print_help()
        return 1

    if args.revert:
        print("Putting worlds back:\n")
        for path in chosen:
            revert(path)
        return 0

    print("%s the visible ground to %d m square:\n"
          % ("Would widen" if args.dry_run else "Widening", args.size_m))
    results = [apply_to(path, args.size_m, args.dry_run) for path in chosen]
    print()
    if "failed" in results:
        print("At least one world did not parse afterwards and was put "
              "back. Nothing else was touched.")
        return 1
    print("%d changed, %d skipped (heightmap or already done)."
          % (sum(1 for r in results if r in ("done", "would")),
             sum(1 for r in results if r in ("skipped", "unchanged"))))
    if not args.dry_run:
        print("Restart Gazebo for this to take effect.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
