#!/usr/bin/env python3
"""
Give the worlds a ground that light can catch.

    python3 tools/ground_texture_apply.py --list
    python3 tools/ground_texture_apply.py --all --dry-run
    python3 tools/ground_texture_apply.py --all

WHAT IT CHANGES. The heightmap worlds declare a normal map and the file
they point at - flat_normal.png - is 128,128,255 with zero variation,
which is the "no relief at all" value. So every one of them has been
rendering ground that is geometrically flat AND optically flat: one
colour however low the sun. This points them at ground_normal.png
instead, which is a real tangent-space normal map built from the same
height field as the diffuse beside it.

WHAT THAT LOOKS LIKE. At dusk, with the sun a few degrees up, a surface
with normals catches light on one side of every undulation and shades
the other. That is the difference between ground and painted card, and
it is most of why night and dusk looked flat.

WHAT IT DOES NOT DO - and this is the honest half. The seven worlds
whose ground is a PLANE rather than a heightmap still have no texture at
all. SDF gives a heightmap a <texture><size> to tile with; a plane
visual has no equivalent, so one texture would be stretched across the
whole 220 km rather than repeated, which is worse than a flat colour.
Fixing those properly means giving them a flat heightmap so the tiling
machinery applies, and that needs watching in Gazebo before it is done
to seven worlds. See docs/image-quality-options.md.

NOT SEEN IN GAZEBO.
"""

import argparse
import glob
import os
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDS = os.path.join(REPO, "sim", "worlds")
MEDIA = os.path.join(WORLDS, "media")

BACKUP_SUFFIX = ".prenormal"

OLD_NORMAL = "file://media/flat_normal.png"
NEW_NORMAL = "file://media/ground_normal.png"


def worlds():
    return sorted(glob.glob(os.path.join(WORLDS, "*.sdf")))


def state(text):
    """What this world's ground is, and whether it still has the flat
    normal map.

    The FLAT NORMAL MAP is looked for first, and the plane check comes
    after. Since 12 Oct 2026 the plane worlds also carry a flat
    heightmap, added as a visual so a texture could tile, so "has a
    heightmap" no longer means "is a heightmap world" - and what this
    script actually cares about is whether flat_normal.png is still
    being pointed at anywhere.
    """
    if OLD_NORMAL in text:
        return "flat-normal"
    if "<heightmap>" not in text:
        return "plane" if "<plane>" in text else "neither"
    if NEW_NORMAL in text or "grass_normal.png" in text:
        return "done"
    return "other-normal"


def apply_to(path, dry_run):
    name = os.path.basename(path)
    with open(path) as handle:
        text = handle.read()
    how = state(text)

    if how == "done":
        print("  %-34s already has a real normal map" % name)
        return "same"
    if how == "plane":
        print("  %-34s SKIPPED - ground is a plane, which cannot tile a "
              "texture" % name)
        return "skipped"
    if how == "neither":
        print("  %-34s SKIPPED - no ground to texture" % name)
        return "skipped"
    if how == "other-normal":
        print("  %-34s SKIPPED - points at a normal map this script did "
              "not put there" % name)
        return "skipped"

    count = text.count(OLD_NORMAL)
    if dry_run:
        print("  %-34s would point %d normal map(s) at ground_normal.png"
              % (name, count))
        return "would"

    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(text.replace(OLD_NORMAL, NEW_NORMAL))

    try:
        ET.parse(path)
    except ET.ParseError as exc:
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse (%s) - put back" % (name, exc))
        return "failed"

    print("  %-34s %d normal map(s) now ground_normal.png" % (name, count))
    return "done"


def revert(path):
    name = os.path.basename(path)
    backup = path + BACKUP_SUFFIX
    if not os.path.isfile(backup):
        print("  %-34s nothing to put back" % name)
        return
    shutil.copyfile(backup, path)
    os.remove(backup)
    print("  %-34s put back" % name)


def do_list():
    print("Ground in each world\n")
    print("  %-34s %-14s %s" % ("FILE", "GROUND", "NORMAL MAP"))
    for path in worlds():
        with open(path) as handle:
            how = state(handle.read())
        ground = "plane" if how == "plane" else (
            "none" if how == "neither" else "heightmap")
        note = {"flat-normal": "FLAT - no relief at all",
                "done": "ground_normal.png",
                "other-normal": "something else",
                "plane": "- (a plane cannot tile one)",
                "neither": "-"}[how]
        print("  %-34s %-14s %s" % (os.path.basename(path), ground, note))

    print("\nRequired media:")
    for name in ("ground_normal.png", "ground_rough.png", "grass_fine.png",
                 "grass_normal.png", "grass_rough.png"):
        there = os.path.isfile(os.path.join(MEDIA, name))
        print("  %-22s %s" % (name, "present" if there else
                              "MISSING - run tools/make_surface_maps.py"))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("world", nargs="?", help="one world file name")
    parser.add_argument("--all", action="store_true", help="every world")
    parser.add_argument("--list", action="store_true",
                        help="what each world's ground is")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would change, write nothing")
    parser.add_argument("--revert", action="store_true",
                        help="put back this script's backups")
    args = parser.parse_args()

    if args.list:
        return do_list()

    if not os.path.isfile(os.path.join(MEDIA, "ground_normal.png")):
        print("ground_normal.png is not there. Make it first:\n")
        print("    python3 tools/make_surface_maps.py")
        return 1

    if args.all:
        chosen = worlds()
    elif args.world:
        path = os.path.join(WORLDS, os.path.basename(args.world))
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

    print("%s the ground normal map:\n"
          % ("Would point" if args.dry_run else "Pointing"))
    results = [apply_to(path, args.dry_run) for path in chosen]
    print()
    if "failed" in results:
        print("At least one world did not parse and was put back.")
        return 1
    print("%d changed, %d left alone."
          % (sum(1 for r in results if r in ("done", "would")),
             sum(1 for r in results if r in ("same", "skipped"))))
    if not args.dry_run and "done" in results:
        print("\nRun tools/install_worlds.py, then restart PX4 and Gazebo.")
        print("Set the lighting to Dusk to see the difference - a normal "
              "map\nshows most when the sun is low.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
