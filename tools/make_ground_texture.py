"""Generates the ground texture the training worlds use.

    python3 tools/make_ground_texture.py

Writes sim/worlds/media/ground_fine.png.

WHY
---
Every world was painting its terrain with grass_diffuse.png: 256x256 pixels
stretched over 40 metres. That is 6.4 pixels per metre, so at the 9 m the
chase camera sits from the aircraft the ground is being magnified about
fifteen times. No camera resolution fixes that - it was why the picture
stayed soft after the chase camera went to 1600x900.

This writes 1024x1024. With the 16 m tile tools/sharpen_terrain.py sets,
that is 64 pixels per metre: ten times the detail that was there.

SEAMLESS, BECAUSE IT TILES A THOUSAND TIMES
-------------------------------------------
A 16 m tile repeats about a thousand times across a 16 km terrain, so a
visible seam would read as a grid from the air. The noise is made seamless
by blurring it wrapped around on itself - tile 3x3, blur, take the middle -
rather than blurring the square and leaving its edges mismatched.

The grain is deliberately fine and low in contrast. These worlds are dry
lake beds and playa; what they look like close up is sand with cracks, not
pattern. Fine uniform grain also hides the repeat, where anything with a
large feature in it would announce it.
"""
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")
SIZE = 1024

# Sampled from the playa these worlds render as, kept low-contrast: real dry
# lake bed is close to flat in tone, and contrast here would read as tiling.
BASE = np.array([183, 164, 128], dtype=np.float64)


def wrapped_blur(field, radius):
    """Blur that wraps at the edges, so the result tiles without a seam."""
    tiled = np.tile(field, (3, 3))
    image = Image.fromarray(np.uint8(np.clip(tiled, 0, 255)))
    image = image.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"])
                         .GaussianBlur(radius))
    out = np.asarray(image, dtype=np.float64)
    n = field.shape[0]
    return out[n:2 * n, n:2 * n]


def main():
    rng = np.random.default_rng(20261011)

    # Several octaves: fine grain for the close-up, a little broad variation
    # so a large flat area does not look painted.
    field = np.zeros((SIZE, SIZE), dtype=np.float64)
    # Weights tuned by looking at the result, not by taste: the first pass
    # came out at a standard deviation of 5 grey levels, which at 64 pixels
    # per metre reads as clean flat paint rather than ground. These land
    # near 14, which is grain you can see from nine metres without it
    # turning into visible noise.
    for radius, weight in ((0.6, 26.0), (2.0, 18.0), (6.0, 13.0), (18.0, 10.0)):
        noise = rng.normal(128, 40, (SIZE, SIZE))
        field += (wrapped_blur(noise, radius) - 128) * weight / 40.0

    # Dry ground cracks: faint darker veins, which is what reads as "surface"
    # rather than "texture" when the camera is a few metres away.
    veins = rng.normal(128, 60, (SIZE, SIZE))
    veins = wrapped_blur(veins, 1.2)
    cracks = np.clip((veins - 146) / 14.0, 0, 1) * -24.0

    # A touch of independent per-channel variation: ground is never one hue,
    # and a purely grey-scale grain over a flat colour looks printed.
    rgb = np.zeros((SIZE, SIZE, 3), dtype=np.float64)
    for channel in range(3):
        tint = wrapped_blur(rng.normal(128, 40, (SIZE, SIZE)), 3.0) - 128
        rgb[:, :, channel] = BASE[channel] + field + cracks + tint * 0.09

    image = Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), "RGB")
    os.makedirs(MEDIA, exist_ok=True)
    path = os.path.join(MEDIA, "ground_fine.png")
    image.save(path, optimize=True)
    print("wrote %s (%dx%d, %.0f kB)"
          % (path, image.width, image.height, os.path.getsize(path) / 1024))

    # A seam would show as a grid from the air, so check rather than hope:
    # the wrap-around difference should be no worse than the inside.
    pixels = np.asarray(image, dtype=np.float64)
    seam = np.abs(pixels[0, :, :] - pixels[-1, :, :]).mean()
    inside = np.abs(pixels[10, :, :] - pixels[11, :, :]).mean()
    print("  vertical seam %.2f vs %.2f between neighbouring rows inside"
          % (seam, inside))
    seam_h = np.abs(pixels[:, 0, :] - pixels[:, -1, :]).mean()
    inside_h = np.abs(pixels[:, 10, :] - pixels[:, 11, :]).mean()
    print("  horizontal seam %.2f vs %.2f" % (seam_h, inside_h))
    if seam > inside * 2.5 or seam_h > inside_h * 2.5:
        print("  SEAM VISIBLE - this would tile as a grid", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
