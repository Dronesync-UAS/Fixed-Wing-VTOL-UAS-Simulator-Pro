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
    if PLANE_SIZE.search(text) or SOLID_GROUND_BOX.search(text):
        return "plane"
    if "<heightmap>" in text:
        return "heightmap"
    return "neither"


def current_size(text):
    """How wide the visible ground is, whether it is a plane or a box."""
    found = PLANE_SIZE.search(text)
    if found:
        return (float(found.group(2)), float(found.group(3)))
    # After --solid the ground is a box, and its first two numbers are the
    # same width and depth the plane carried.
    found = SOLID_GROUND_BOX.search(text)
    return (float(found.group(1)), float(found.group(2))) if found else None


def ground_visual_count(text):
    """How many ground visuals the pattern can see - must be exactly one.

    Counts planes AND solid boxes, since --solid turns one into the other
    and the check behind this exists to catch the pattern matching
    something that is not the ground at all.
    """
    return len(PLANE_SIZE.findall(text)) + len(SOLID_GROUND_BOX.findall(text))


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


# A visual <plane> and the thin box that replaces it.
GROUND_VISUAL_PLANE = re.compile(
    r'(<visual name="ground_visual">)(\s*)(<geometry>\s*)<plane>\s*'
    r'(?:<normal>[^<]*</normal>\s*)?<size>\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)'
    r'\s*</size>\s*</plane>', re.DOTALL)
# Thick enough that nothing can see its edge from inside, sunk so its TOP
# face is exactly z=0 - where the plane's surface was, so nothing else in
# the world moves.
SOLID_THICKNESS_M = 2.0

# The same ground after --solid has turned it into a box. ground_kind has
# to go on calling these the PLANE worlds: it is what the world stands on
# that matters, not which primitive draws it, and the widening, the
# collision reach and the range-profile check are all keyed off that word.
SOLID_GROUND_BOX = re.compile(
    r'<visual name="ground_visual">.*?<box>\s*<size>\s*'
    r'([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*</size>', re.DOTALL)


def make_ground_solid(text):
    """Turn the ground VISUAL's plane into a thin box. Returns (text, done).

    WHY, and this is the answer to the "dark ground" that survived three
    attempts between 12 and 14 Oct 2026:

    **<geometry><plane> IGNORES ITS SDF MATERIAL in this Gazebo Harmonic /
    ogre2 build.** The ground renders a default grey-brown and nothing
    written in <material> changes it.

    Measured on 14 Oct 2026, on the coast world, with everything running:

        ground_plane material set to magenta, geometry left a <plane>
            -> camera sees (151.8, 137.5, 126.5). No change at all.
        same magenta material, geometry changed to a <box>
            -> camera sees (160.1, 2.1, 158.6). Magenta.

    That is why every earlier fix failed: the flat heightmap, the explicit
    material, the 8 km mesh and the normal maps were all downstream of a
    surface that was never going to show any of them. It is also why the
    five HEIGHTMAP worlds looked right all along - a heightmap is not a
    plane, so its material and texture were always honoured.

    The collision is untouched. It has always been a separate sunken box
    and still is; this changes what you SEE, not what you land on.
    """
    def swap(m):
        x, y = float(m.group(4)), float(m.group(5))
        return ('%s%s<pose>0 0 %.3f 0 0 0</pose>%s%s<box><size>%g %g %g</size></box>'
                % (m.group(1), m.group(2), -SOLID_THICKNESS_M / 2.0,
                   m.group(2), m.group(3), x, y, SOLID_THICKNESS_M))
    out, n = GROUND_VISUAL_PLANE.subn(swap, text, count=1)
    return out, n > 0


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


def solidify(path, dry_run):
    """Make one world's ground visual a box instead of a plane."""
    name = os.path.basename(path)
    with open(path) as handle:
        text = handle.read()
    if '<visual name="ground_visual">' not in text:
        print("  %-34s SKIPPED - no ground_visual" % name)
        return "skipped"
    if "<plane>" not in text.split('<visual name="ground_visual">', 1)[1][:600]:
        print("  %-34s already solid" % name)
        return "unchanged"
    out, done = make_ground_solid(text)
    if not done:
        print("  %-34s SKIPPED - could not read its plane" % name)
        return "skipped"
    if dry_run:
        print("  %-34s plane -> box" % name)
        return "would"
    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(out)
    if not parses(path):
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse - put back as it was" % name)
        return "failed"
    print("  %-34s plane -> box, so its material shows" % name)
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
    parser.add_argument("--solid", action="store_true",
                        help="make the ground visual a box rather than a "
                             "plane, so its material is actually rendered - "
                             "see make_ground_solid for the measurements")
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

    if args.solid:
        print("%s the ground visual from a plane to a box:\n"
              % ("Would change" if args.dry_run else "Changing"))
        results = [solidify(path, args.dry_run) for path in chosen]
        print()
        if "failed" in results:
            print("At least one world did not parse and was put back.")
            return 1
        if not args.dry_run and "done" in results:
            print("Run tools/install_worlds.py, then restart PX4 and Gazebo.")
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
