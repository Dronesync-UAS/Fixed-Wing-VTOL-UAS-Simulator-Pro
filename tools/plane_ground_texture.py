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

THE FIX. Add an 8 km MESH over the training area, purely as a visual,
from tools/make_ground_mesh.py. It carries UV coordinates that repeat
the texture every 16 m, so the tiling comes from the mesh itself and no
terrain code is involved. So:

    ground_near   8 km mesh, exactly flat, tiled grass every 16 m, with
                  a normal and roughness map. Visual only - no collision.
    ground_far    the existing 220 km plane, flat colour, left alone,
                  sunk 0.05 m so the two cannot z-fight.

Eight kilometres covers the 500 m student envelope four hundred times
over and most of a 100 km leg's interesting part. Beyond it the far
plane takes over, and at that distance a flat tone is what haze does
anyway.

THE COLLISION IS NOT TOUCHED. The 220 km box underneath still carries
every landing. A second collision here would be two surfaces fighting
over the same contact.

IT WAS A FLAT HEIGHTMAP FIRST, AND THAT DID NOT WORK. <heightmap> is
SDF's only built-in way to tile, so 12 Oct 2026 used a dead-flat one.
Loaded in Gazebo on 13 Oct, the coast world rendered it with no texture
at all and a different colour from every camera:

    chase    rgb(22,38,49)      pixel variation 0.0
    payload  rgb(255,255,255)   pixel variation 0.0
    nose     rgb(173,150,143)   pixel variation 6.4

The valley world's terrain, a heightmap with the same <texture> block
but 240 m of relief, measured 22.2 in the same scene. Two fixes were
tried and neither moved any of those figures: giving the heightmap image
a real 0..255 range instead of a single value, and adding an explicit
<material> with roughness 1.0 and metalness 0. A flat heightmap appears
not to texture at all, and relief is not an option here - the collision
is a flat box at z=0, so any relief in the visual shows the aircraft
sunk into the ground or hovering above it.

None of that was catchable offline: re-parsing and tools/test_surface_maps.py
only read the XML, and the XML was valid every time.
"""

import argparse
import glob
import os
import re
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
{i}     A MESH, from tools/make_ground_mesh.py, carrying UV coordinates
{i}     that repeat the texture every {tile} m. A <plane> visual cannot tile -
{i}     it stretches one image across its whole size - which is why this
{i}     world used to stand on one flat colour.
{i}
{i}     IT WAS A FLAT HEIGHTMAP FIRST, AND THAT DID NOT WORK. SDF's only
{i}     built-in way to tile is <heightmap><texture><size>, so a dead-flat
{i}     heightmap was tried on 12 Oct 2026. Loaded in Gazebo on 13 Oct it
{i}     rendered with no texture at all and a different colour from every
{i}     camera - white from the payload, near-black from the chase - while
{i}     the valley world's heightmap, same <texture> block but 240 m of
{i}     relief, rendered correctly. Giving the image a real height range
{i}     and adding an explicit material both changed nothing. A mesh needs
{i}     no terrain code and is exactly flat, which matters: the collision
{i}     is a separate box at z=0, and relief in the visual would show the
{i}     aircraft sunk into the ground or hovering over it.
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
{i}        <mesh>
{i}          <uri>file://media/ground_tile.obj</uri>
{i}        </mesh>
{i}      </geometry>
{i}      <!-- PLAIN COLOUR, NO TEXTURE MAPS. Measured in Gazebo on 13 Oct
{i}           2026, by spawning boxes side by side into the running world -
{i}           same light, same texture file, one variable each:
{i}
{i}             plain <diffuse> colour        lit and shaded, correct
{i}             <albedo_map>                  near-black
{i}             <albedo_map> + normal + rough near-black
{i}             <albedo_map>, absolute path   near-black
{i}             <emissive_map>, same file     renders the texture
{i}
{i}           PBR albedo_map does not render in this Gazebo Harmonic /
{i}           ogre2 build. That is why the flat heightmap, the height
{i}           range, the mesh and the material were each blamed in turn and
{i}           no change made any difference: every one of them ended on the
{i}           same broken path.
{i}
{i}           This is the one configuration proven to render, and it is
{i}           what the 220 km far plane has always used. The cost is no
{i}           surface detail. The alternative is a ground that is black. -->
{i}      <material>
{i}        <ambient>0.30 0.34 0.24 1</ambient>
{i}        <diffuse>0.42 0.50 0.30 1</diffuse>
{i}        <specular>0.04 0.04 0.04 1</specular>
{i}      </material>
{i}    </visual>
{i}  </link>
{i}</model>
"""

# Which textures suit which world. The British worlds get grass; the
# bare ones get the dry ground the playa worlds already use.
# Diffuse, normal and roughness. The roughness maps have existed since
# tools/make_surface_maps.py was written and were pointed at by nothing
# until 13 Oct 2026 - tools/ground_texture_apply.py checked they were
# present and no world ever referenced one.
GRASS = ("grass_fine.png", "grass_normal.png", "grass_rough.png")
DRY = ("ground_fine.png", "ground_normal.png", "ground_rough.png")
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


def block_for(base):
    """The block this world should have, or None if it is not one of ours."""
    if base not in SURFACE:
        return None
    diffuse, normal, rough = SURFACE[base]
    for texture in (diffuse, normal, rough, "ground_tile.obj"):
        if not os.path.isfile(os.path.join(MEDIA, texture)):
            return None
    return BLOCK.format(i="    ", marker=MARKER, z=NEAR_Z,
                        diffuse=diffuse, normal=normal, rough=rough,
                        tile=TILE_M)


def rebuild(path, name, base, text, dry_run):
    """Swap a world's existing ground_near for the current one.

    Idempotent: a world already carrying exactly this block is left alone
    and reported as such, so running the tool twice is a no-op."""
    block = block_for(base)
    if block is None:
        print("  %-34s SKIPPED - no surface chosen, or media missing" % name)
        return "skipped"

    found = OLD_BLOCK.search(text)
    if not found:
        print("  %-34s SKIPPED - has ground_near but not one this tool "
              "wrote; left alone" % name)
        return "skipped"
    if found.group(0) == block:
        print("  %-34s already up to date" % name)
        return "same"
    if dry_run:
        print("  %-34s would be REBUILT (%.0f mm relief, paging off)"
              % (name, NEAR_RELIEF_M * 1000.0))
        return "would"

    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(text[:found.start()] + block + text[found.end():])
    try:
        ET.parse(path)
    except ET.ParseError as problem:
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse (%s) - world restored" % (name, problem))
        return "failed"
    print("  %-34s rebuilt" % name)
    return "done"


def insert_before_close(text, block):
    """Put the model just before </world>, which every one of these ends
    with. Inserting at the top of the world would work too; the end is
    where a reader looks for "what was added"."""
    close = text.rindex("</world>")
    return text[:close] + block + text[close:]


# The whole added block, comment and all, so a world that already has one
# can have it REBUILT rather than skipped. Without this the tool could only
# ever add ground to a world that had none, and the seven worlds that got a
# faulty block on 12 Oct 2026 could not be corrected except by --revert -
# which restores a snapshot predating the other four world tools and
# silently undoes them. See the note in CLAUDE.md.
OLD_BLOCK = re.compile(
    r"[ \t]*<!--\s*GROUND WITHIN THE TRAINING AREA.*?"
    r"<model name=\"" + MARKER + r"\">.*?</model>\n",
    re.S)


def apply_to(path, dry_run):
    name = os.path.basename(path)
    base = name[:-4]
    with open(path) as handle:
        text = handle.read()
    how = kind(text)

    if how == "done":
        return rebuild(path, name, base, text, dry_run)
    if how != "plane":
        print("  %-34s SKIPPED - ground is a %s" % (name, how))
        return "skipped"
    if base not in SURFACE:
        print("  %-34s SKIPPED - no surface chosen for it" % name)
        return "skipped"

    diffuse, normal, rough = SURFACE[base]
    for texture in (diffuse, normal, rough, "ground_tile.obj"):
        if not os.path.isfile(os.path.join(MEDIA, texture)):
            print("  %-34s SKIPPED - %s is missing" % (name, texture))
            return "skipped"

    if dry_run:
        print("  %-34s would get %d km of %s, tiled every %d m"
              % (name, NEAR_EXTENT_M // 1000, diffuse, TILE_M))
        return "would"

    block = BLOCK.format(i="    ", marker=MARKER, z=NEAR_Z,
                         diffuse=diffuse, normal=normal, rough=rough,
                         tile=TILE_M)
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
