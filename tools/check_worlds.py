"""Parses every world file in sim/worlds/ and reports anything malformed:

    python3 tools/check_worlds.py

Exists because a world file was committed with a broken comment - an XML
comment cannot contain a double hyphen, and "gz model --list" was written
inside one. The file still looked right to read, and Gazebo would have refused
to load it at the worst possible moment. A parse is cheap; do it before
committing a world.

Also reports what each world declares, so an accidental change to the
magnetic field, the system list or the ground stands out.
"""
import glob
import os
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDS = os.path.join(REPO, "sim", "worlds")


def main():
    paths = sorted(glob.glob(os.path.join(WORLDS, "*.sdf")))
    if not paths:
        print(f"No .sdf files in {WORLDS}")
        return 1

    bad = 0
    for path in paths:
        name = os.path.basename(path)
        try:
            world = ET.parse(path).getroot().find("world")
        except ET.ParseError as exc:
            print(f"BROKEN  {name}: {exc}")
            bad += 1
            continue
        if world is None:
            print(f"BROKEN  {name}: no <world> element")
            bad += 1
            continue

        sc = world.find("spherical_coordinates")
        coords = (f"{sc.findtext('latitude_deg')}, {sc.findtext('longitude_deg')}"
                  if sc is not None else "none")
        systems = len(world.findall("plugin"))
        wind = world.find("wind")
        print(f"OK      {name}")
        print(f"          world name   {world.get('name')}")
        print(f"          coordinates  {coords}")
        print(f"          mag field    {world.findtext('magnetic_field')}")
        print(f"          plugins      {systems}")
        print(f"          wind         {wind.findtext('linear_velocity') if wind is not None else 'none'}")

        # Every file:// reference should resolve next to the world.
        for ref in {t.strip()[len("file://"):] for t in
                    (e.text or "" for e in world.iter())
                    if t.strip().startswith("file://")}:
            target = os.path.join(WORLDS, ref)
            if not os.path.isfile(target):
                print(f"          MISSING FILE {ref}")
                bad += 1

    print(f"\n{len(paths)} world(s), {bad} problem(s).")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
