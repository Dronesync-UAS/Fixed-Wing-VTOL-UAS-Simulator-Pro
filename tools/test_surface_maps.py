"""Check the surface maps are real maps, not placeholders.

    python3 tools/test_surface_maps.py

THE BUG THIS EXISTS FOR, found 12 Oct 2026: every heightmap world
declared a normal map and the file was 128,128,255 with zero variation -
the "no relief at all" value of a tangent-space normal map. It had been
there for weeks doing nothing, and nothing checked it. A placeholder
that looks like a feature is worse than a missing feature.

So: a normal map must have relief, must have unit-length normals, must
tile without a seam, and no world may point at a flat one.
"""
import glob
import math
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")
WORLDS = os.path.join(REPO, "sim", "worlds")

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


def load(name):
    return np.asarray(Image.open(os.path.join(MEDIA, name)).convert("RGB"),
                      dtype=np.float64)


def per_channel_spread(rgb):
    """The biggest within-channel range.

    MEASURED PER CHANNEL on purpose. Taking max minus min across all
    three channels of a normal map gives 127 for a perfectly FLAT
    128,128,255 map, because blue sits 127 above red and green by
    definition - which is the difference between the channels, not
    variation within them. The first version of this check did that and
    called the flat placeholder textured.
    """
    return float(max(rgb[:, :, c].max() - rgb[:, :, c].min()
                     for c in range(3)))


print("1. the normal maps have relief")

for name in ("ground_normal.png", "grass_normal.png"):
    path = os.path.join(MEDIA, name)
    if not os.path.isfile(path):
        check("%s exists (run tools/make_surface_maps.py)" % name, False)
        continue
    rgb = load(name)
    spread = per_channel_spread(rgb)
    check("%s has relief, not 128,128,255 flat (spread %.0f)" % (name, spread),
          spread > 40)

    # Every pixel must be a UNIT vector once decoded, or lighting is wrong
    # in a way that is hard to see and impossible to debug by eye.
    v = rgb / 127.5 - 1.0
    lengths = np.sqrt((v * v).sum(axis=2))
    worst = float(max(abs(lengths.min() - 1.0), abs(lengths.max() - 1.0)))
    check("%s decodes to unit normals (worst error %.3f)" % (name, worst),
          worst < 0.02)

    # Z must point OUT of the surface everywhere. A negative blue channel
    # means an inside-out normal, which lights as a hole.
    check("%s points out of the surface everywhere (min Z %.2f)"
          % (name, float(v[:, :, 2].min())), v[:, :, 2].min() > 0.3)

    # Seamless: the first and last row/column must nearly match, or the
    # tile edge shows as a hard line of shading every 16 metres.
    top_bottom = float(np.abs(rgb[0] - rgb[-1]).mean())
    left_right = float(np.abs(rgb[:, 0] - rgb[:, -1]).mean())
    check("%s tiles without a seam (edges differ by %.1f, %.1f of 255)"
          % (name, top_bottom, left_right),
          top_bottom < 12 and left_right < 12)

    image = Image.open(path)
    check("%s is at least 1024 px (%d)" % (name, image.width),
          image.width >= 1024)

print("\n2. the old flat normal map is still recognisably flat")

flat = os.path.join(MEDIA, "flat_normal.png")
if os.path.isfile(flat):
    rgb = load("flat_normal.png")
    check("flat_normal.png is indeed flat, which is why it was replaced "
          "(spread %.0f)" % per_channel_spread(rgb),
          per_channel_spread(rgb) < 2)

print("\n3. no world points at a flat normal map")

pointing_flat = []
for path in sorted(glob.glob(os.path.join(WORLDS, "*.sdf"))):
    with open(path) as handle:
        text = handle.read()
    if "flat_normal.png" in text:
        pointing_flat.append(os.path.basename(path))
check("no world uses flat_normal.png (%s)"
      % (", ".join(pointing_flat) or "none do"), not pointing_flat)

using_real = []
for path in sorted(glob.glob(os.path.join(WORLDS, "*.sdf"))):
    with open(path) as handle:
        text = handle.read()
    if "<heightmap>" in text:
        using_real.append((os.path.basename(path),
                           "ground_normal.png" in text))
check("every heightmap world has a real normal map (%d of %d)"
      % (sum(1 for _, ok in using_real if ok), len(using_real)),
      using_real and all(ok for _, ok in using_real))

print("\n4. the diffuse and roughness maps")

for name, lo, hi in (("grass_fine.png", 60, 255),
                     ("ground_fine.png", 60, 255)):
    if not os.path.isfile(os.path.join(MEDIA, name)):
        check("%s exists" % name, False)
        continue
    rgb = load(name)
    spread = per_channel_spread(rgb)
    # grass_diffuse.png, the one this replaces, had a spread of 19.
    check("%s has real variation, not a flat swatch (spread %.0f)"
          % (name, spread), spread > 60)

for name in ("ground_rough.png", "grass_rough.png"):
    path = os.path.join(MEDIA, name)
    if not os.path.isfile(path):
        check("%s exists" % name, False)
        continue
    grey = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    # Ground is rough everywhere. A roughness map that reaches the smooth
    # end puts wet-looking patches on dry earth.
    check("%s stays in the rough half of the range (%.0f to %.0f)"
          % (name, grey.min(), grey.max()),
          grey.min() > 150 and grey.max() <= 255)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
