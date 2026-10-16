"""Check the training areas' scenery.

    python3 tools/test_scenery.py

Needs neither PX4 nor Gazebo. The things worth proving:

  * the launch point stays clear. An obstacle where the aircraft spawns
    turns every lesson in that world into a crash, and nobody would see
    it coming from reading scenery.py;
  * the layout is the SAME every time. A lesson that says "the target is
    the container north-east of the hangar" is worthless if the hangar
    moves on the next run;
  * the three payload targets are where the instructor's notes say;
  * what is written into the world files is valid SDF, and the tool can
    take it out again.
"""
import math
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


import scenery                                              # noqa: E402
import scenery_apply                                        # noqa: E402
import sim_target                                           # noqa: E402

print("1. every world with a theme gets scenery")
for world, theme in scenery.WORLD_THEMES.items():
    items = scenery.layout(world)
    check("%s (%s): %d features" % (world, theme, len(items)), len(items) > 20)
check("the bare world stays bare", scenery.layout("flat_test") == [])
check("every themed world is one the station can load",
      all(w in sim_target.BY_WORLD for w in scenery.WORLD_THEMES))

print("2. the launch point is clear")
for world in scenery.WORLD_THEMES:
    too_close = []
    for yaw, x, y, parts in scenery.layout(world):
        if math.hypot(x, y) >= scenery.CLEAR_RADIUS_M:
            continue
        # Flat things - roads, fields, rail - are allowed through the
        # middle. They are not obstacles and a road that stops 90 m short
        # of the aircraft would look absurd.
        tall = [p for p in parts
                if not (p[0] == "box" and p[1]["sz"] <= 0.2)]
        if tall:
            too_close.append((round(x), round(y), parts[0][0]))
    check("%s has nothing solid within %g m (%s)"
          % (world, scenery.CLEAR_RADIUS_M, too_close or "clear"), not too_close)

print("3. the same layout every time")
for world in scenery.WORLD_THEMES:
    first = scenery.layout(world)
    second = scenery.layout(world)
    check("%s is reproducible" % world, first == second)
check("and two worlds are not the same layout",
      scenery.layout("training_area") != scenery.layout("training_area_uyuni"))

print("4. the payload targets")
targets = scenery.target_positions()
check("there are three", len(targets) == 3)
check("at three different ranges",
      len({t["range_m"] for t in targets}) == 3)
check("spread round the compass",
      max(t["bearing_deg"] for t in targets)
      - min(t["bearing_deg"] for t in targets) > 180)
for t in targets:
    bearing = math.radians(t["bearing_deg"])
    check("target %d is where the notes say (%+.0f N, %+.0f E)"
          % (t["number"], t["north_m"], t["east_m"]),
          abs(t["north_m"] - t["range_m"] * math.cos(bearing)) < 0.2
          and abs(t["east_m"] - t["range_m"] * math.sin(bearing)) < 0.2)
# And that each one is actually placed in every world.
for world in scenery.WORLD_THEMES:
    placed = scenery.layout(world)
    # The panel is 0.3 m thick, 6 m wide, 3.2 m tall and white. The
    # thickness matters: without it a 7x6x3.2 m outbuilding on the
    # coast counted as a fourth target.
    panels = [p for p in placed
              if any(k == "box" and abs(a["sx"] - 0.3) < 0.01
                     and abs(a["sy"] - 6.0) < 0.01
                     and abs(a["sz"] - 3.2) < 0.01 for k, a in p[3])]
    check("%s carries all three target panels (%d)" % (world, len(panels)),
          len(panels) == 3)

print("5. obstacles collide and vegetation does not")
lowland = scenery.layout("training_area_lowlands")
collides = [p for p in lowland
            if any(a.get("collide") for _, a in p[3])]
check("some things are obstacles (%d of %d)" % (len(collides), len(lowland)),
      10 < len(collides) < len(lowland))
# A tree is a trunk cylinder and two leaf spheres, and none of it should
# collide - this is the one that would be noticed only by crashing.
trees = [p for p in lowland
         if len(p[3]) == 3 and p[3][0][0] == "cylinder"
         and p[3][1][0] == "sphere"]
check("there are trees (%d)" % len(trees), len(trees) > 20)
check("and none of them collides",
      all(not a.get("collide") for p in trees for _, a in p[3]))

print("6. what it writes into a world file")
work = tempfile.mkdtemp()
world = "training_area_lowlands"
source = os.path.join(REPO, "sim", "worlds", world + ".sdf")
# Work on a copy, with the scenery stripped back out, so this test can
# run whether or not the real world files have been written yet.
text = open(source).read()
at = text.find("    " + scenery_apply.MARKER)
if at >= 0:
    text = text[:at] + "  </world>\n</sdf>\n"
path = os.path.join(work, world + ".sdf")
open(path, "w").write(text)
scenery_apply.WORLDS_DIR = work

check("it applies", scenery_apply._apply_one(world, False) == 0)
written = open(path).read()
try:
    tree = ET.parse(path)
    parsed = True
except ET.ParseError as exc:
    parsed, tree = False, None
    print("        " + str(exc))
check("the result is valid XML", parsed)
if parsed:
    models = [m.get("name") for m in tree.getroot().find("world").findall("model")]
    scenic = [m for m in models if m.startswith("scenery_")]
    check("every feature became a model (%d)" % len(scenic),
          len(scenic) == len(scenery.layout(world)))
    check("they are all static",
          all(m.find("static") is not None and m.find("static").text == "true"
              for m in tree.getroot().find("world").findall("model")
              if (m.get("name") or "").startswith("scenery_")))
    check("an ellipsoid was used for the squashed shapes, not a sunk sphere",
          "<ellipsoid>" in written)
check("running it twice changes nothing",
      scenery_apply._apply_one(world, False) == 0
      and open(path).read() == written)
check("the backup was kept", os.path.exists(path + scenery_apply.SUFFIX))
scenery_apply.revert()
check("--revert puts the world back", open(path).read() == text)
shutil.rmtree(work, ignore_errors=True)

print("7. the instructor's notes agree with the layout")
import scenery_targets_doc                                  # noqa: E402

generated = scenery_targets_doc.build()
on_disk = open(os.path.join(REPO, "docs", "scenery-targets.md")).read()
check("docs/scenery-targets.md is up to date "
      "(run tools/scenery_targets_doc.py if not)", generated == on_disk)


print("How surfaces behave in light")
# Added 12 Oct 2026. Until then every object in every world carried the
# same flat material, so water, a painted container, wet mud and a hedge
# all caught light identically - a large part of why the scenery read as
# coloured cardboard.
from collections import Counter                             # noqa: E402

counts = Counter()
unknown = set()
for name in scenery.THEMES:
    for item in scenery.THEMES[name](scenery.Rng(7)):
        for kind, a in item[3]:
            surface = a.get("surface", scenery.DEFAULT_SURFACE)
            counts[surface] += 1
            if surface not in scenery.SURFACES:
                unknown.add(surface)

check("every part names a surface this project knows (%s)"
      % (", ".join(sorted(unknown)) or "all known"), not unknown)
check("water is marked as water (%d parts)" % counts["water"],
      counts["water"] > 0)
check("vegetation is marked (%d parts)" % counts["vegetation"],
      counts["vegetation"] > 50)
check("metal is marked (%d parts)" % counts["metal"], counts["metal"] > 10)

# Water must be near-mirror, or the sea at Norfolk, the flooded Levels
# and the estuary stay matte plates - which is what they were.
rough_water, metal_water = scenery.SURFACES["water"]
check("water is near-mirror (roughness %.2f)" % rough_water,
      rough_water < 0.2)
rough_matte, _ = scenery.SURFACES["matte"]
check("and far smoother than earth (%.2f against %.2f)"
      % (rough_water, rough_matte), rough_water < rough_matte / 3)
_, metalness = scenery.SURFACES["metal"]
check("metal reads as metal (metalness %.2f)" % metalness, metalness > 0.5)
check("nothing else is metal",
      all(m < 0.1 for k, (r, m) in scenery.SURFACES.items() if k != "metal"))

# The writer has to put those numbers in the XML, or none of it reaches
# Gazebo.
sys.path.insert(0, os.path.join(REPO, "tools"))
import scenery_apply as _sa                                 # noqa: E402

xml = _sa._material((0.1, 0.22, 0.3), "water")
check("the writer emits a <pbr> block", "<pbr>" in xml and "<metal>" in xml)
check("with water's roughness in it (%s)" % rough_water,
      "<roughness>%g</roughness>" % rough_water in xml)
xml = _sa._material((0.8, 0.8, 0.8), "metal")
check("and metal's metalness", "<metalness>%g</metalness>" % metalness in xml)
xml = _sa._material((0.4, 0.5, 0.3))
check("an untagged object still gets a material",
      "<diffuse>" in xml and "<pbr>" in xml)
check("and no empty albedo_map, which reads as a missing texture",
      "albedo_map" not in xml)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
