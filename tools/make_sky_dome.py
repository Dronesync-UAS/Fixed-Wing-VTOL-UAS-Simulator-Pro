#!/usr/bin/env python3
"""
Make the sky: an inside-out dome mesh and the sky texture painted on it.

    python3 tools/make_sky_dome.py
    python3 tools/make_sky_dome.py --preview

WHY THERE IS A DOME AT ALL. Gazebo Harmonic's own sky is one bit: on or
off. gz-sim8's RenderUtil.cc does scene.Ambient(), scene.Background() and
SetSkyEnabled(true) and nothing else - there is no sky material, no
gradient, no cloud, and no fog anywhere in that file. So <sky></sky> gives
a flat near-white ceiling, which is the largest area in every camera view
and the single worst thing about how this simulator looks.

A painted dome inside the camera's far clip plane replaces it. It costs
two triangles' worth of thought and it is the whole sky.

WHY A MESH AND NOT AN SDF <sphere>. Looking at a sphere from the inside
means seeing its back faces, which are culled. SDF can ask for
double-sided, but in gz-sim8 that flag only reaches Ogre through
SetAlphaFromTexture, i.e. only when an albedo map is present, and it is
not worth depending on. An inside-out mesh has no back faces to cull:
every triangle is wound and normalled to face the middle, which is where
the aircraft is.

WHICH WAY UP. gz-common's mesh importer sets aiProcess_FlipUVs
(graphics/src/AssimpLoader.cc line 877), so the v coordinate in this file
is flipped before anything samples the image. The zenith therefore gets
v=1 here. Getting this backwards does not fail, it renders the painted
ground-haze tone across the entire sky, which is what happened the first
time.

WHY EMISSIVE AND NOT LIT. A sky is not a surface that the sun falls on.
The dome's albedo is black and the sky image is its emissive map, so it
shows exactly what was painted, whatever the sun is doing. plugins/
time_of_day.py then dims it over /world/NAME/material_color, which is how
night gets a night sky without restarting the world.

WHAT IS PAINTED, AND WHAT IS A COMPROMISE

  * A real zenith-to-horizon gradient, deep blue to pale.
  * Cloud, as periodic value noise. It FADES OUT above about 65 degrees
    of elevation, because an equirectangular image pinches at the pole
    and stretched cloud there looks worse than no cloud.
  * A haze band at the horizon, which is what softens the hard line where
    the ground stops at the camera's clip plane. There is no fog in this
    renderer; this is the substitute.
  * A broad, weak glow where the worlds put the sun. Deliberately not a
    disc: plugins/time_of_day.py moves the sun and a painted disc would
    then be in the wrong place.
  * Below the horizon the image fades to a dull haze tone. It is normally
    hidden by the ground; it is painted so that a glimpse of it is not a
    hole.

NOT SEEN IN GAZEBO. The mesh and the image are checked by
tools/test_sky.py - geometry, winding, UV coverage, gradient, seam - and
nobody has watched a dome load.
"""
import argparse
import math
import os
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")

MESH_NAME = "sky_dome.obj"
TEXTURE_NAME = "sky_day.png"

# The mesh is a UNIT sphere. The world file scales it, so one mesh serves
# any dome radius and the radius is a number a reader can see in the SDF.
AZIMUTH_STEPS = 72          # every 5 degrees
POLAR_STEPS = 36            # every 5 degrees

TEX_W, TEX_H = 2048, 1024

# Where the worlds put the sun: direction of travel (-0.55, 0.35, -0.62)
# in ENU, so the sun itself is at (+0.55, -0.35, +0.62).
SUN_VECTOR = (0.55, -0.35, 0.62)

ZENITH = (46, 96, 166)
MID_SKY = (105, 150, 202)
HORIZON = (206, 216, 226)
BELOW = (78, 82, 72)

CLOUD_LIT = (252, 253, 255)
CLOUD_SHADE = (206, 212, 224)


# --- the mesh ----------------------------------------------------------

def dome_obj():
    """An inside-out unit sphere, as OBJ text.

    Vertex ring j runs from the zenith (j=0) to the nadir. The seam at
    azimuth 0 is DUPLICATED with u=1 so the texture does not wrap a
    whole image across the last column.
    """
    verts, uvs, norms, faces = [], [], [], []

    for j in range(POLAR_STEPS + 1):
        polar = math.pi * j / POLAR_STEPS          # 0 at zenith
        z = math.cos(polar)
        r = math.sin(polar)
        for i in range(AZIMUTH_STEPS + 1):
            # Azimuth measured from north, turning east, to match the
            # bearing an instructor reads off the compass tape.
            az = 2.0 * math.pi * i / AZIMUTH_STEPS
            x = r * math.sin(az)      # east
            y = r * math.cos(az)      # north
            verts.append((x, y, z))
            # v is 1 AT THE ZENITH, not 0. gz-common imports meshes with
            # aiProcess_FlipUVs set - graphics/src/AssimpLoader.cc line
            # 877 - so whatever v is in this file arrives flipped. The
            # first dome written here had v=0 at the zenith and rendered
            # the painted below-horizon tone across the whole sky.
            uvs.append((i / AZIMUTH_STEPS, 1.0 - j / POLAR_STEPS))
            # Inward: the surface faces the middle of the dome.
            norms.append((-x, -y, -z))

    def index(j, i):
        return j * (AZIMUTH_STEPS + 1) + i + 1    # OBJ is 1-based

    for j in range(POLAR_STEPS):
        for i in range(AZIMUTH_STEPS):
            a, b = index(j, i), index(j, i + 1)
            c, d = index(j + 1, i + 1), index(j + 1, i)
            # Wound so that the front face is the one seen from inside.
            faces.append((a, d, c))
            faces.append((a, c, b))

    out = ["# Inside-out sky dome, unit radius.",
           "# Written by tools/make_sky_dome.py - do not hand-edit.",
           "# Normals and winding both point INWARD: there are no back",
           "# faces to cull, which is the whole reason this is a mesh and",
           "# not an SDF <sphere>.",
           "o sky_dome"]
    out += ["v %.6f %.6f %.6f" % v for v in verts]
    out += ["vt %.6f %.6f" % uv for uv in uvs]
    out += ["vn %.6f %.6f %.6f" % n for n in norms]
    out += ["f %d/%d/%d %d/%d/%d %d/%d/%d"
            % (f[0], f[0], f[0], f[1], f[1], f[1], f[2], f[2], f[2])
            for f in faces]
    return "\n".join(out) + "\n"


# --- the texture -------------------------------------------------------

def periodic_noise(rng, cells_x, cells_y, height, width):
    """Value noise that WRAPS in x, so the seam at azimuth 0 is invisible."""
    lattice = rng.random((cells_y + 1, cells_x))

    xs = np.linspace(0.0, cells_x, width, endpoint=False)
    ys = np.linspace(0.0, cells_y, height, endpoint=False)
    x0 = np.floor(xs).astype(int)
    y0 = np.floor(ys).astype(int)
    fx, fy = xs - x0, ys - y0
    sx = (fx * fx * (3.0 - 2.0 * fx))[None, :]
    sy = (fy * fy * (3.0 - 2.0 * fy))[:, None]

    xa, xb = x0 % cells_x, (x0 + 1) % cells_x
    ya, yb = y0, np.minimum(y0 + 1, cells_y)

    top = (lattice[ya[:, None], xa[None, :]] * (1.0 - sx)
           + lattice[ya[:, None], xb[None, :]] * sx)
    bottom = (lattice[yb[:, None], xa[None, :]] * (1.0 - sx)
              + lattice[yb[:, None], xb[None, :]] * sx)
    return top * (1.0 - sy) + bottom * sy


def mix(a, b, t):
    """Blend two RGB triples. t is an array; the result is H x W x 3."""
    t = t[..., None]
    return np.array(a)[None, None, :] * (1.0 - t) + np.array(b)[None, None, :] * t


def sky_image(seed=11):
    rng = np.random.default_rng(seed)

    # v runs 0 at the zenith to 1 at the nadir; u is the bearing.
    v = (np.arange(TEX_H) + 0.5) / TEX_H
    u = (np.arange(TEX_W) + 0.5) / TEX_W
    polar = v * math.pi
    elevation = (math.pi / 2.0) - polar               # + up, 0 at horizon
    el_grid = np.repeat(elevation[:, None], TEX_W, axis=1)

    # The gradient. Two stops rather than one, because a single linear
    # ramp from zenith to horizon reads as a flat wash.
    up = np.clip(np.sin(np.clip(el_grid, 0.0, None)), 0.0, 1.0)
    low = mix(HORIZON, MID_SKY, np.clip(up / 0.45, 0.0, 1.0))
    high = mix(MID_SKY, ZENITH, np.clip((up - 0.45) / 0.55, 0.0, 1.0))
    sky = np.where((up > 0.45)[..., None], high, low)

    # The haze band. Strongest in the few degrees either side of the
    # horizon, which is where the ground stops at the clip plane.
    haze = np.exp(-(np.clip(el_grid, 0.0, None) / math.radians(7.0)) ** 2)
    sky = sky * (1.0 - haze[..., None]) + np.array(HORIZON)[None, None, :] * haze[..., None]

    # Cloud. Four octaves, each wrapping in azimuth.
    cloud = np.zeros((TEX_H, TEX_W))
    for cells_x, cells_y, weight in ((11, 5, 0.50), (23, 11, 0.27),
                                     (47, 23, 0.15), (95, 47, 0.08)):
        cloud += weight * periodic_noise(rng, cells_x, cells_y, TEX_H, TEX_W)
    cloud = (cloud - cloud.min()) / max(float(np.ptp(cloud)), 1e-6)

    # Coverage: soft-threshold so edges are not cut out with scissors.
    cover = np.clip((cloud - 0.47) / 0.22, 0.0, 1.0) ** 1.3
    # Fade out at the pole, where equirectangular UVs pinch, and below
    # about 6 degrees, where cloud would sit in the haze band.
    cover *= np.clip((math.radians(74.0) - el_grid) / math.radians(16.0), 0.0, 1.0)
    cover *= np.clip((el_grid - math.radians(4.0)) / math.radians(7.0), 0.0, 1.0)

    shade = np.clip((cloud - 0.47) / 0.36, 0.0, 1.0)
    cloud_rgb = mix(CLOUD_SHADE, CLOUD_LIT, shade)
    sky = sky * (1.0 - cover[..., None]) + cloud_rgb * cover[..., None]

    # The sun's glow. Broad and weak on purpose - see the header.
    sun = np.array(SUN_VECTOR, dtype=float)
    sun /= np.linalg.norm(sun)
    az = 2.0 * math.pi * u
    dir_x = np.sin(polar)[:, None] * np.sin(az)[None, :]
    dir_y = np.sin(polar)[:, None] * np.cos(az)[None, :]
    dir_z = np.repeat(np.cos(polar)[:, None], TEX_W, axis=1)
    angle = np.arccos(np.clip(dir_x * sun[0] + dir_y * sun[1]
                              + dir_z * sun[2], -1.0, 1.0))
    glow = 0.22 * np.exp(-(angle / math.radians(30.0)) ** 2)
    sky = sky * (1.0 - glow[..., None]) + np.array([255, 250, 238])[None, None, :] * glow[..., None]

    # Below the horizon: fade to a dull haze tone. Normally hidden by the
    # ground; painted so a glimpse of it is not a hole.
    down = np.clip(-el_grid / math.radians(12.0), 0.0, 1.0)
    sky = sky * (1.0 - down[..., None]) + np.array(BELOW)[None, None, :] * down[..., None]

    return Image.fromarray(np.clip(sky, 0, 255).astype(np.uint8), "RGB")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--preview", action="store_true",
                        help="also write the image to /tmp to look at")
    args = parser.parse_args()

    if not os.path.isdir(MEDIA):
        print("No media directory: %s" % MEDIA)
        return 1

    mesh_path = os.path.join(MEDIA, MESH_NAME)
    with open(mesh_path, "w") as handle:
        handle.write(dome_obj())
    faces = 2 * AZIMUTH_STEPS * POLAR_STEPS
    print("%-22s %d triangles, unit radius, normals inward"
          % (MESH_NAME, faces))

    image = sky_image()
    texture_path = os.path.join(MEDIA, TEXTURE_NAME)
    image.save(texture_path)
    pixels = np.asarray(image).reshape(-1, 3)
    print("%-22s %dx%d, mean RGB %s"
          % (TEXTURE_NAME, image.width, image.height,
             pixels.mean(0).round(0).astype(int).tolist()))

    if args.preview:
        out = "/tmp/sky_day_preview.png"
        image.save(out)
        print("\nPreview written to %s" % out)

    print("\nNext: python3 tools/sky_dome_apply.py --all")
    return 0


if __name__ == "__main__":
    sys.exit(main())
