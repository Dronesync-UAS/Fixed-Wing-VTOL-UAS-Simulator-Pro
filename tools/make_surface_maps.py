#!/usr/bin/env python3
"""
Generates the surface maps the worlds need: real normal maps, a grass and
farmland diffuse for the northern European worlds, and roughness maps.

    python3 tools/make_surface_maps.py

WHY THIS EXISTS. Measured on 12 Oct 2026, the three textures every world
was using:

    flat_normal.png    256px   mean 128,128,255   spread 0,0,0
    grass_diffuse.png  256px   mean 193,164,119   spread 19
    ground_fine.png   1024px   mean 180,161,125   spread 136

flat_normal.png has ZERO spread. 128,128,255 with no variation is the
"no bump at all" value of a tangent-space normal map, so every heightmap
world was declaring a normal map that did nothing - there was no surface
relief anywhere in any world. grass_diffuse.png is a near-flat colour
swatch at 256 pixels. And the seven worlds whose ground is a plane
rather than a heightmap had no texture at all.

WHAT A NORMAL MAP IS, since the point is easy to miss. It does not change
the shape of anything. It tells the renderer which way the surface is
FACING at each pixel, so light catches it. Without one, a flat plane lit
by a low sun is one flat colour however good its diffuse texture is -
which is exactly what dusk looked like.

HOW THESE ARE MADE. From a height field, not by guessing: build seamless
multi-octave noise, treat it as a height, and take its gradient. The
normal at a pixel is the unit vector perpendicular to that slope. That
is the actual definition, so the result is consistent with the diffuse
made from the same field rather than merely plausible beside it.

THESE ARE GENERATED, NOT PHOTOGRAPHED. Said plainly: procedural noise
with cracks and tonal variation reads as ground from ten metres and as
noise from one. Photographic CC0 material sets - Poly Haven, ambientCG -
would be better and are the next step. This is what can be made here,
now, with no download and no licence to check.

NOT SEEN IN GAZEBO. The arithmetic is checked in
tools/test_surface_maps.py; nobody has watched these light.
"""

import os
import sys

import numpy as np
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")
SIZE = 1024

# How strongly the height field bends the normals. 1.0 would be a
# near-vertical cliff at every grain; this is ground, so the slopes are
# gentle and the figure is small. Raising it makes the surface look
# rough and, past about 4, crumpled.
NORMAL_STRENGTH = 2.2

# Northern European grass and farmland, which is what coast, lowlands,
# estate, forest, airfield and flood are. Greener and darker than playa.
GRASS = np.array([96, 112, 62], dtype=np.float64)
# Dry playa and desert, matching the existing ground_fine.png.
DRY = np.array([183, 164, 128], dtype=np.float64)


def wrapped_blur(field, radius):
    """Blur that wraps at the edges, so the result tiles without a seam.
    Tile 3x3, blur, take the middle - blurring the square on its own
    leaves its edges mismatched and the repeat shows as a grid."""
    tiled = np.tile(field, (3, 3))
    image = Image.fromarray(np.uint8(np.clip(tiled, 0, 255)))
    image = image.filter(ImageFilter.GaussianBlur(radius))
    out = np.asarray(image, dtype=np.float64)
    n = field.shape[0]
    return out[n:2 * n, n:2 * n]


def height_field(rng, octaves):
    """Seamless multi-octave noise, as a height in grey levels."""
    field = np.zeros((SIZE, SIZE), dtype=np.float64)
    for radius, weight in octaves:
        noise = rng.normal(128, 40, (SIZE, SIZE))
        field += (wrapped_blur(noise, radius) - 128) * weight / 40.0
    return field


def normal_map(height, strength=NORMAL_STRENGTH):
    """A tangent-space normal map from a height field.

    The gradient is taken with np.roll rather than np.gradient so that it
    wraps: a normal map whose edges do not match shows the tile boundary
    as a hard line of shading, which is worse than no normal map at all.

    Tangent space convention: +X is right in the texture, +Y is up, +Z
    out of the surface, each mapped from -1..1 onto 0..255. A flat
    surface is therefore 128,128,255 - which is what the old file was,
    all over.
    """
    dx = (np.roll(height, -1, axis=1) - np.roll(height, 1, axis=1)) * 0.5
    dy = (np.roll(height, -1, axis=0) - np.roll(height, 1, axis=0)) * 0.5
    # Scale the slopes into something the unit vector can use. The /255
    # puts the height in 0..1 before the strength is applied.
    nx = -dx * strength / 255.0
    ny = -dy * strength / 255.0
    nz = np.ones_like(nx)
    length = np.sqrt(nx * nx + ny * ny + nz * nz)
    nx, ny, nz = nx / length, ny / length, nz / length
    rgb = np.stack([(nx + 1.0) * 127.5,
                    (ny + 1.0) * 127.5,
                    (nz + 1.0) * 127.5], axis=2)
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), "RGB")


def roughness_map(height):
    """Rougher where the surface is disturbed, smoother where it is not.
    Grey-scale; ogre2's metal/roughness workflow reads it as one channel.
    Ground is rough everywhere, so this is a narrow band high up the
    range rather than the full sweep - a roughness map that reaches the
    smooth end puts wet-looking patches on dry earth."""
    normalised = (height - height.min()) / max(1.0, float(np.ptp(height)))
    rough = 185 + normalised * 50          # 185..235 of 255
    return Image.fromarray(np.uint8(np.clip(rough, 0, 255)), "L")


def grass_diffuse(rng, height, base):
    """A diffuse the same height field shaped, so the normal map's
    bumps land where the colour changes rather than beside them."""
    veins = wrapped_blur(rng.normal(128, 60, (SIZE, SIZE)), 1.1)
    # Darker where grass is longer or shaded, lighter where it is worn.
    shade = np.clip((veins - 140) / 18.0, -1, 1) * 14.0
    # Patchiness at field scale: real grass is not one green.
    patch = wrapped_blur(rng.normal(128, 40, (SIZE, SIZE)), 26.0) - 128
    rgb = np.zeros((SIZE, SIZE, 3), dtype=np.float64)
    for channel in range(3):
        tint = wrapped_blur(rng.normal(128, 40, (SIZE, SIZE)), 4.0) - 128
        # Green varies most, which is what makes it read as vegetation
        # rather than painted card.
        spread = (0.26, 0.42, 0.18)[channel]
        rgb[:, :, channel] = (base[channel] + height * 0.75 + shade
                              + patch * spread + tint * 0.11)
    return Image.fromarray(np.uint8(np.clip(rgb, 0, 255)), "RGB")


OCTAVES_FINE = ((0.6, 26.0), (2.0, 18.0), (6.0, 13.0), (18.0, 10.0))


def main():
    os.makedirs(MEDIA, exist_ok=True)
    written = []

    # One height field for the dry worlds, matching the octaves that made
    # the existing ground_fine.png, so its new normal map agrees with it.
    rng = np.random.default_rng(20261012)
    dry_height = height_field(rng, OCTAVES_FINE)

    for name, image in (
            ("ground_normal.png", normal_map(dry_height)),
            ("ground_rough.png", roughness_map(dry_height))):
        path = os.path.join(MEDIA, name)
        image.save(path, optimize=True)
        written.append(path)

    # And one for the green worlds.
    rng = np.random.default_rng(20261013)
    grass_height = height_field(rng, OCTAVES_FINE)
    for name, image in (
            ("grass_fine.png", grass_diffuse(rng, grass_height, GRASS)),
            ("grass_normal.png", normal_map(grass_height)),
            ("grass_rough.png", roughness_map(grass_height))):
        path = os.path.join(MEDIA, name)
        image.save(path, optimize=True)
        written.append(path)

    print("Wrote:\n")
    for path in written:
        image = Image.open(path)
        band = np.asarray(image.convert("RGB"), dtype=np.int16)
        spread = int(band.max() - band.min())
        print("  %-22s %dx%d  spread %-4d %6.0f kB"
              % (os.path.basename(path), image.width, image.height,
                 spread, os.path.getsize(path) / 1024))
    print("\nA normal map with spread 0 is the bug this replaces - "
          "128,128,255\nflat everywhere means no relief at all.")
    print("\nThese are GENERATED, not photographed. Photographic CC0 "
          "material\nsets would be better; see docs/image-quality-options.md.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
