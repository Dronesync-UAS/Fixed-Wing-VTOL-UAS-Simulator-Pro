"""Generates the two particle textures the weather cell uses.

    python3 tools/make_particle_textures.py

Writes sim/worlds/media/particle_soft.png and particle_streak.png.

WHY THESE EXIST
---------------
A particle emitter with only <diffuse>/<specular> and no texture renders
each particle as a flat, hard-edged coloured quad. On 11 Oct 2026 the first
fog test looked like pale rectangles stacked in the sky, which is exactly
what it was: 18 m square billboards with no alpha.

The shape of a particle comes from its texture's alpha channel, so fog needs
a soft radial falloff and rain needs a tapered streak. Both are generated
rather than downloaded: Gazebo's own fog generator lives on Fuel, and a
texture this project depends on should be reproducible from a script in the
repository rather than fetched from a server that may not be reachable.

HOW THE ALPHA IS USED
---------------------
SceneManager::LoadMaterial calls SetAlphaFromTexture(true, 0.5, ...) for any
albedo map, which on Ogre2Material sets an alpha test at 0.5 AND a
SBT_TRANSPARENT_ALPHA blendblock. Particles get only the blendblock -
Ogre2Material::FillUnlitDatablock copies samplerblock, macroblock and
blendblock, and does not copy the alpha test - so the full gradient renders
smoothly and nothing is clipped at 0.5.
"""
import math
import os
import sys

from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")


def soft_blob(size=128):
    """A round puff: opaque at the centre, fading to nothing at the rim.

    The exponent decides how a cloud of these reads. Linear falloff leaves a
    visible disc edge where particles overlap; squaring it spreads the fade
    out so overlapping puffs merge into one mass, which is the whole point
    of using particles as fog.
    """
    image = Image.new("RGBA", (size, size))
    pixels = image.load()
    centre = (size - 1) / 2.0
    for y in range(size):
        for x in range(size):
            radius = math.hypot(x - centre, y - centre) / centre
            alpha = 0.0 if radius >= 1.0 else (1.0 - radius) ** 2
            pixels[x, y] = (255, 255, 255, int(round(255 * alpha)))
    return image


def streak(width=32, height=128):
    """A falling raindrop: a soft vertical line, tapered at both ends.

    Tapered rather than a plain bar because a bar's square ends read as the
    thing they are - rectangles - as soon as two of them overlap.
    """
    image = Image.new("RGBA", (width, height))
    pixels = image.load()
    cx = (width - 1) / 2.0
    for y in range(height):
        along = y / (height - 1.0)
        # Smooth 0 -> 1 -> 0 along the drop's length.
        taper = math.sin(math.pi * along) ** 0.6
        for x in range(width):
            across = abs(x - cx) / cx
            alpha = 0.0 if across >= 1.0 else (1.0 - across) ** 2 * taper
            pixels[x, y] = (255, 255, 255, int(round(255 * alpha)))
    return image


def main():
    os.makedirs(MEDIA, exist_ok=True)
    for name, image in (("particle_soft.png", soft_blob()),
                        ("particle_streak.png", streak())):
        path = os.path.join(MEDIA, name)
        image.save(path)
        print("wrote %s (%dx%d)" % (path, image.width, image.height))
    return 0


if __name__ == "__main__":
    sys.exit(main())
