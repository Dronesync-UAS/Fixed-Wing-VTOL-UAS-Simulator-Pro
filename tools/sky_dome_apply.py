#!/usr/bin/env python3
"""
Put a painted sky over every world, and stop washing the ground out.

    python3 tools/sky_dome_apply.py --list
    python3 tools/sky_dome_apply.py --all --dry-run
    python3 tools/sky_dome_apply.py --all
    python3 tools/sky_dome_apply.py --all --revert

THREE CHANGES, and each one is here because of something measured in a
screenshot on 12 Oct 2026.

1. THE SKY. <sky></sky> is Gazebo Harmonic's built-in sky, and it is one
   bit - on or off. gz-sim8's RenderUtil.cc reads scene.Ambient(),
   scene.Background() and SetSkyEnabled(true), and that is all it reads:
   there is no sky material, no gradient, no cloud, and the word "fog"
   does not appear in the file. On screen it is a flat near-white
   ceiling filling the top half of every camera view.

   So the built-in sky comes OUT and a painted dome goes in: an
   inside-out mesh at 7 km radius, inside the cameras' 8 km clip plane,
   carrying the image from tools/make_sky_dome.py.

2. THE AMBIENT. Every world had <ambient>0.40 0.41 0.44</ambient>. That
   is a lot of flat light from nowhere, and it is why the PBR materials
   added earlier the same day made no visible difference: a surface lit
   40% from every direction at once cannot show relief, and roughness
   has nothing to be rough against. Down to 0.26 0.28 0.32, which keeps
   shadowed sides readable rather than black.

3. THE HORIZON. The dome's painted haze band sits where the ground stops
   at the clip plane. It does not make real fog - this renderer has
   none - but it replaces a hard line between ground and white with a
   soft one between ground and haze.

THE DOME IS STATIC, AT THE WORLD ORIGIN. Beyond about 7 km from launch
the aircraft flies out of it and the sky falls back to <background>.
That covers the 500 m student envelope entirely and the first few
minutes of a 100 km leg. Said plainly because it is a real limit: on an
extended-range flight the sky will go flat.

NIGHT. The dome is emissive, so the sun does not touch it, so it would
stay bright blue at night. plugins/time_of_day.py dims it over
/world/NAME/material_color, which gz-sim8's UserCommands.cc does support
on a named visual - that is what makes a night sky possible without
restarting the world.

NOT SEEN IN GAZEBO. Checked by re-parsing and by tools/test_sky.py.
Nobody has watched a dome load.
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

BACKUP_SUFFIX = ".presky"
MARKER = "sky_dome"

MESH = "sky_dome.obj"
TEXTURE = "sky_day.png"

# Inside the cameras' far clip, which tools/chase_camera_apply.py and
# tools/gimbal_apply.py both set to 8000 m. A dome outside it would be
# clipped away and the sky would be the background colour again.
DOME_RADIUS_M = 7000
CAMERA_FAR_CLIP_M = 8000

NEW_AMBIENT = "0.26 0.28 0.32 1"
NEW_BACKGROUND = "0.52 0.66 0.84 1"

BLOCK = """\
{i}<!-- THE SKY, added 12 Oct 2026 by tools/sky_dome_apply.py.
{i}
{i}     An inside-out dome at {radius} m - inside the cameras' {clip} m clip
{i}     plane - carrying the sky image from tools/make_sky_dome.py. It
{i}     replaces <sky></sky>, which in this renderer is a flat near-white
{i}     ceiling with no gradient and no cloud.
{i}
{i}     EMISSIVE, ALBEDO BLACK. A sky is not a surface the sun falls on.
{i}     The image is the emissive map and nothing else lights the dome, so
{i}     it shows exactly what was painted. plugins/time_of_day.py dims it
{i}     for dusk and night over /world/NAME/material_color.
{i}
{i}     NO SHADOWS, NO COLLISION. It is 7 km of geometry around everything;
{i}     either one would be a disaster. -->
{i}<model name="{marker}">
{i}  <static>true</static>
{i}  <pose>0 0 0 0 0 0</pose>
{i}  <link name="{marker}_link">
{i}    <visual name="{marker}_visual">
{i}      <cast_shadows>false</cast_shadows>
{i}      <geometry>
{i}        <mesh>
{i}          <uri>file://media/{mesh}</uri>
{i}          <scale>{radius} {radius} {radius}</scale>
{i}        </mesh>
{i}      </geometry>
{i}      <material>
{i}        <ambient>0 0 0 1</ambient>
{i}        <diffuse>0 0 0 1</diffuse>
{i}        <specular>0 0 0 1</specular>
{i}        <emissive>1 1 1 1</emissive>
{i}        <pbr>
{i}          <metal>
{i}            <roughness>1.0</roughness>
{i}            <metalness>0.0</metalness>
{i}            <emissive_map>file://media/{texture}</emissive_map>
{i}          </metal>
{i}        </pbr>
{i}      </material>
{i}    </visual>
{i}  </link>
{i}</model>
"""

SKY_REPLACEMENT = """<!-- The built-in sky was removed 12 Oct 2026: it is one
           bit in this renderer, with no gradient and no cloud. The
           sky_dome model at the end of this file replaces it. -->"""

SCENE = re.compile(r"<scene>.*?</scene>", re.DOTALL)
SKY_TAG = re.compile(r"<sky\s*/>|<sky>.*?</sky>", re.DOTALL)
AMBIENT = re.compile(r"<ambient>[^<]*</ambient>")
BACKGROUND = re.compile(r"<background>[^<]*</background>")


def worlds():
    return sorted(glob.glob(os.path.join(WORLDS, "*.sdf")))


def scene_of(text):
    found = SCENE.search(text)
    return found.group(0) if found else None


def ambient_of(text):
    scene = scene_of(text) or ""
    found = AMBIENT.search(scene)
    return found.group(0)[9:-10].strip() if found else None


def has_dome(text):
    return 'name="%s"' % MARKER in text


def has_builtin_sky(text):
    scene = scene_of(text) or ""
    return bool(SKY_TAG.search(scene))


def rewrite_scene(text):
    """Take the built-in sky out, and bring the flat ambient down."""
    scene = scene_of(text)
    if scene is None:
        return text, "no <scene>"
    fixed = SKY_TAG.sub(SKY_REPLACEMENT, scene)
    fixed = AMBIENT.sub("<ambient>%s</ambient>" % NEW_AMBIENT, fixed, count=1)
    fixed = BACKGROUND.sub("<background>%s</background>" % NEW_BACKGROUND,
                           fixed, count=1)
    return text[:text.index(scene)] + fixed + text[text.index(scene) + len(scene):], None


def apply_to(path, dry_run):
    name = os.path.basename(path)
    with open(path) as handle:
        text = handle.read()

    if has_dome(text):
        print("  %-34s already has a sky dome" % name)
        return "same"

    for asset in (MESH, TEXTURE):
        if not os.path.isfile(os.path.join(MEDIA, asset)):
            print("  %-34s SKIPPED - media/%s is missing. Run "
                  "tools/make_sky_dome.py first." % (name, asset))
            return "skipped"

    if dry_run:
        print("  %-34s would get a %d km dome; ambient %s -> %s"
              % (name, DOME_RADIUS_M // 1000, ambient_of(text),
                 NEW_AMBIENT.rsplit(" ", 1)[0]))
        return "would"

    fixed, problem = rewrite_scene(text)
    if problem:
        print("  %-34s SKIPPED - %s" % (name, problem))
        return "skipped"

    block = BLOCK.format(i="    ", marker=MARKER, mesh=MESH, texture=TEXTURE,
                         radius=DOME_RADIUS_M, clip=CAMERA_FAR_CLIP_M)
    close = fixed.rindex("</world>")
    fixed = fixed[:close] + block + fixed[close:]

    shutil.copyfile(path, path + BACKUP_SUFFIX)
    with open(path, "w") as handle:
        handle.write(fixed)

    try:
        ET.parse(path)
    except ET.ParseError as exc:
        shutil.copyfile(path + BACKUP_SUFFIX, path)
        print("  %-34s FAILED to parse (%s) - put back" % (name, exc))
        return "failed"

    print("  %-34s %d km dome, built-in sky out, ambient %s"
          % (name, DOME_RADIUS_M // 1000, NEW_AMBIENT.rsplit(" ", 1)[0]))
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
    print("The sky in each world\n")
    print("  %-34s %-10s %-12s %s"
          % ("FILE", "DOME?", "BUILT-IN SKY", "SCENE AMBIENT"))
    for path in worlds():
        with open(path) as handle:
            text = handle.read()
        print("  %-34s %-10s %-12s %s"
              % (os.path.basename(path),
                 "yes" if has_dome(text) else "NO",
                 "still on" if has_builtin_sky(text) else "removed",
                 ambient_of(text) or "-"))
    print("\nAnything showing NO is still on the flat built-in sky.")
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
        print("\nOne tool's --revert undoes the others. Check with:"
              "\n    python3 tools/worlds_state.py")
        return 0

    print("%s the painted sky:\n" % ("Would add" if args.dry_run else "Adding"))
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
