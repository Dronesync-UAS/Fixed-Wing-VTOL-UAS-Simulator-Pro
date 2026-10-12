#!/usr/bin/env python3
"""
Give the plane worlds a ground texture, which they have never had.

    python3 tools/plane_ground_texture.py --list
    python3 tools/plane_ground_texture.py --all --dry-run
    python3 tools/plane_ground_texture.py --all
    python3 tools/plane_ground_texture.py --all --revert

THE PROBLEM. Seven worlds - coast, airfield, estate, flood, forest,
lowlands and flat_test - stand on a <plane> visual with a flat colour
and no texture at all. Measured 12 Oct 2026. From the chase camera at
nine metres that is one unbroken sheet of green, and at dusk it is one
unbroken sheet of darker green. It is the single largest surface in
every camera view and it carries no detail whatsoever.

WHY NOT JUST PUT A TEXTURE ON THE PLANE. Because SDF gives no way to
tile one. A heightmap has <texture><size> - "repeat this every N metres"
- and a plane visual has no equivalent, so one texture would be
stretched across the whole 220 km. A 1024 px image over 220 km is 215
metres per pixel. Worse than a flat colour.

THE FIX. Add a flat HEIGHTMAP over the training area, purely as a
visual, which can tile. Gazebo builds terrain from an image; a uniform
image gives perfectly level ground. So:

    ground_near   8 km heightmap, dead flat, tiled grass every 16 m,
                  with a real normal map. Visual only - no collision.
    ground_far    the existing 220 km plane, flat colour, left alone,
                  sunk 0.05 m so the two cannot z-fight.

Eight kilometres covers the 500 m student envelope four hundred times
over and most of a 100 km leg's interesting part. Beyond it the far
plane takes over, and at that distance a flat tone is what haze does
anyway.

THE COLLISION IS NOT TOUCHED. The 220 km box underneath still carries
every landing. A heightmap collision as well would be two surfaces
fighting over the same contact.

NOT SEEN IN GAZEBO. The edit is checked by re-parsing and by
tools/test_surface_maps.py; nobody has watched one of these worlds load.
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

BACKUP_SUFFIX = ".preground"
MARKER = "ground_near"

NEAR_EXTENT_M = 8000
# How often the grass repeats. 16 m matches what tools/sharpen_terrain.py
# chose for the heightmap worlds, so the two kinds of world look alike.
TILE_M = 16
# Sunk below zero by a hair so the far plane at z=0 cannot z-fight with
# it. Five centimetres is invisible from the air and decisive to the
# depth buffer.
NEAR_Z = 0.02

BLOCK = """\
{i}<!-- GROUND WITHIN THE TRAINING AREA, added 12 Oct 2026 by
{i}     tools/plane_ground_texture.py.
{i}
{i}     This is a HEIGHTMAP and it is dead flat on purpose. The reason is
{i}     not the shape - it is that a heightmap can TILE a texture, with
{i}     <texture><size>, and a plane visual cannot. This world used to
{i}     stand on an untextured plane: one flat colour across the largest
{i}     surface in every camera view.
{i}
{i}     VISUAL ONLY. The 220 km collision box in ground_plane still
{i}     carries every landing; a second collision here would be two
{i}     surfaces arguing over the same contact.
{i}
{i}     Eight kilometres covers the 500 m student envelope many times
{i}     over. Beyond it the far plane takes over, which at that distance
{i}     is what haze does anyway. -->
{i}<model name="{marker}">
{i}  <static>true</static>
{i}  <pose>0 0 {z} 0 0 0</pose>
{i}  <link name="{marker}_link">
{i}    <visual name="{marker}_visual">
{i}      <geometry>
{i}        <heightmap>
{i}          <texture>
{i}            <diffuse>file://media/{diffuse}</diffuse>
{i}            <normal>file://media/{normal}</normal>
{i}            <size>{tile}</size>
{i}          </texture>
{i}          <uri>file://media/flat_ground_heightmap.png</uri>
{i}          <size>{extent} {extent} 0.001</size>
{i}          <pos>0 0 0</pos>
{i}        </heightmap>
{i}      </geometry>
{i}    </visual>
{i}  </link>
{i}</model>
"""

# Which textures suit which world. The British worlds get grass; the
# bare ones get the dry ground the playa worlds already use.
GRASS = ("grass_fine.png", "grass_normal.png")
DRY = ("ground_fine.png", "ground_normal.png")
SURFACE = {
    "training_area_coast": GRASS,
    "training_area_lowlands": GRASS,
    "training_area_estate": GRASS,
    "training_area_forest": GRASS,
    "training_area_airfield": GRASS,
    "training_area_flood": GRASS,
    "flat_test": DRY,          # the bare calibration world, deliberately plain
}


def worlds():
    return sorted(glob.glob(os.path.join(WORLDS, "*.sdf")))


def kind(text):
    if MARKER in text:
        return "done"
    if "<heightmap>" in text:
        return "heightmap"
    if "<plane>" in text:
        return "plane"
    return "neither"


def insert_before_close(text, block):
    """Put the model just before </world>, which every one of these ends
    with. Inserting at the top of the world would work too; the end is
    where a reader looks for "what was added"."""
    close = text.rindex("</world>")
    return text[:close] + block + text[close:]


def apply_to(path, dry_run):
    name = os.path.basename(path)
    base = name[:-4]
    with open(path) as handle:
        text = handle.read()
    how = kind(text)

    if how == "done":
        print("  %-34s already has textured ground" % name)
        return "same"
    if how != "plane":
        print("  %-34s SKIPPED - ground is a %s" % (name, how))
        return "skipped"
    if base not in SURFACE:
        print("  %-34s SKIPPED - no surface chosen for it" % name)
        return "skipped"

    diffuse, normal = SURFACE[base]
    for texture in (diffuse, normal, "flat_ground_heightmap.png"):
        if not os.path.isfile(os.path.join(MEDIA, texture)):
            print("  %-34s SKIPPED - %s is missing" % (name, texture))
            return "skipped"

    if dry_run:
        print("  %-34s would get %d km of %s, tiled every %d m"
              % (name, NEAR_EXTENT_M // 1000, diffuse, TILE_M))
        return "would"

    block = BLOCK.format(i="    ", marker=MARKER, z=NEAR_Z,
                         diffuse=diffuse, normal=normal,
                         tile=TILE_M, extent=NEAR_EXTENT_M)
    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(insert_before_close(text, block))

    try:
        ET.parse(path)
    except ET.ParseError as exc:
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse (%s) - put back" % (name, exc))
        return "failed"

    print("  %-34s %d km of %s, tiled every %d m"
          % (name, NEAR_EXTENT_M // 1000, diffuse, TILE_M))
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
    print("  %-34s %-12s %s" % ("FILE", "GROUND", "TEXTURED?"))
    for path in worlds():
        with open(path) as handle:
            how = kind(handle.read())
        base = os.path.basename(path)[:-4]
        note = {"done": "yes - %s" % SURFACE.get(base, ("?",))[0],
                "heightmap": "yes - it is a heightmap already",
                "plane": "NO - one flat colour",
                "neither": "-"}[how]
        ground = "heightmap" if how in ("heightmap", "done") else how
        print("  %-34s %-12s %s" % (os.path.basename(path), ground, note))
    return 0


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("world", nargs="?", help="one world file name")
    parser.add_argument("--all", action="store_true", help="every world")
    parser.add_argument("--list", action="store_true", help="what each has")
    parser.add_argument("--dry-run", action="store_true",
                        help="say what would change, write nothing")
    parser.add_argument("--revert", action="store_true",
                        help="put back this script's backups")
    args = parser.parse_args()

    if args.list:
        return do_list()

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

    print("%s textured ground inside the training area:\n"
          % ("Would add" if args.dry_run else "Adding"))
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
