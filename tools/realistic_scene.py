"""Makes the training worlds look less like a flat diagram:

    python3 tools/realistic_scene.py            # apply
    python3 tools/realistic_scene.py --dry-run  # show the change
    python3 tools/realistic_scene.py --revert   # put the backups back

THE THREE THINGS, AND WHY EACH ONE FLATTENS THE PICTURE
--------------------------------------------------------
1. THERE WAS NO SKY. Every world set <background>0.6 0.75 0.9 1</background>
   and nothing else, which paints a single flat blue behind everything -
   no horizon, no cloud, no change with viewing angle.

   gz-sim8 reads <scene><sky/></scene>: RenderUtil.cc line 1185, "if
   (scene.Sky()) scene->SetSkyEnabled(true)". Ogre2Scene::SetSkyEnabled
   (line 1529) loads skybox.dds as an environment map and - this is the part
   that matters here - applies it to EVERY sensor camera as well, not just
   the Gazebo window. So the chase and nose feeds get it too.

   What <sky/> does NOT do: sdformat lets you write <time>, <sunrise>,
   <clouds> and so on inside it, and gz-rendering8 ignores all of them. It
   is a fixed cubemap, on or off. Writing those sub-elements would look like
   configuration that does nothing.

2. THE SUN WAS NEARLY OVERHEAD. direction "-0.4 0.2 -0.9" is about 63
   degrees of elevation. Light from overhead casts almost no shadow, so
   terrain relief, the airframe's own shape and the ground all read as flat
   regardless of resolution. Lowered to about 32 degrees, which is where
   landscape reads as landscape.

3. AMBIENT WAS 0.6. That is a very bright fill, and fill light is exactly
   what removes contrast: every surface gets most of its brightness
   regardless of which way it faces. Reduced to 0.4, with the sun's diffuse
   warmed slightly, so a surface turned away from the sun is visibly darker
   than one facing it.

Shadows were already on in every world, and were doing nothing visible
because of 2 and 3.

TASTE, AND HOW TO UNDO IT
-------------------------
Unlike the terrain resolution, this is a judgement about how it should look
rather than a defect being fixed. --revert puts every world back exactly as
it was; the backups are <name>.sdf.prescene.
"""
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
REPO_WORLDS = os.path.join(REPO, "sim", "worlds")
SUFFIX = ".prescene"

# About 32 degrees of elevation, from the north-west. Not a guess at a time
# of day - just low enough that slopes facing the sun are clearly brighter
# than slopes facing away, which is what makes ground read as ground.
SUN_DIRECTION = "-0.55 0.35 -0.62"
SUN_DIFFUSE = "1.0 0.97 0.90 1"
SUN_SPECULAR = "0.35 0.35 0.33 1"
AMBIENT = "0.40 0.41 0.44 1"


def world_paths():
    found = []
    for env in sim_target.ENVIRONMENTS:
        name = env["world"] + ".sdf"
        px4 = os.path.join(PX4_WORLDS, name)
        repo = os.path.join(REPO_WORLDS, name)
        if os.path.isfile(px4):
            found.append(px4)
        elif os.path.isfile(repo):
            found.append(repo)
    return found


def restyle(text):
    """Returns (new_text, changed)."""
    if "<sky" in text:
        return text, False

    out = text

    # The sun: lower it and warm it. Only the light named "sun" is touched -
    # a world that grows a second light later should not be rewritten by a
    # blanket substitution.
    def sun_block(match):
        block = match.group(0)
        block = re.sub(r"<direction>[^<]*</direction>",
                       "<direction>%s</direction>" % SUN_DIRECTION, block)
        block = re.sub(r"<diffuse>[^<]*</diffuse>",
                       "<diffuse>%s</diffuse>" % SUN_DIFFUSE, block)
        block = re.sub(r"<specular>[^<]*</specular>",
                       "<specular>%s</specular>" % SUN_SPECULAR, block)
        return block

    out, suns = re.subn(r'<light type="directional" name="sun">.*?</light>',
                        sun_block, out, flags=re.S)

    # The scene: a real sky, and ambient low enough for the sun to matter.
    def scene_block(match):
        block = match.group(0)
        block = re.sub(r"<ambient>[^<]*</ambient>",
                       "<ambient>%s</ambient>" % AMBIENT, block)
        # <sky/> goes last, after <shadows>, which is where sdformat expects
        # it; a sky element out of order is dropped without complaint.
        return block.replace(
            "</scene>",
            "  <!-- A real skybox instead of one flat colour. gz-rendering8\n"
            "           applies it to every sensor camera too, so the chase and\n"
            "           nose feeds get it, not only the Gazebo window. Its\n"
            "           sdformat sub-elements (time, clouds, humidity) are\n"
            "           ignored by this renderer - it is on or off. -->\n"
            "      <sky></sky>\n    </scene>")

    out, scenes = re.subn(r"<scene>.*?</scene>", scene_block, out, flags=re.S)
    return out, bool(suns and scenes)


def revert():
    restored = 0
    for path in world_paths():
        backup = path + SUFFIX
        if os.path.exists(backup):
            shutil.copy2(backup, path)
            print("restored %s" % os.path.basename(path))
            restored += 1
    print("\n%d file(s) restored." % restored if restored else
          "\nNo %s backups found - nothing to restore." % SUFFIX)
    return 0


def apply(dry_run):
    paths = world_paths()
    if not paths:
        print("No training worlds found.", file=sys.stderr)
        return 1

    edited = skipped = failed = 0
    for path in paths:
        name = os.path.basename(path)
        with open(path) as handle:
            text = handle.read()
        new_text, changed = restyle(text)
        if not changed:
            print("SKIP  %s: already has a sky, or no sun and scene to change"
                  % name)
            skipped += 1
            continue
        if dry_run:
            print("WOULD EDIT %s: sky on, sun to %s, ambient to %s"
                  % (name, SUN_DIRECTION, AMBIENT.split()[0]))
            edited += 1
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
            print("FAIL  %s: XML broke (%s) - reverted" % (name, exc),
                  file=sys.stderr)
            failed += 1
            continue
        print("OK    %s" % name)
        edited += 1

    print()
    print("edited=%d skipped=%d failed=%d" % (edited, skipped, failed))
    if dry_run:
        print("\nDry run - nothing written.")
    elif edited and not failed:
        print("""
Restart the simulator to see it.

This one is taste rather than a defect. If it is too dark, or the shadows
are too long for teaching:
     python3 tools/realistic_scene.py --revert""")
    return 1 if failed else 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except BrokenPipeError:
            pass
        sys.exit(0)
