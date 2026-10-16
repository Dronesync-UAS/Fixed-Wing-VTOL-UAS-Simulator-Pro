#!/usr/bin/env python3
"""
Check the painted sky: the dome mesh, the sky image, and every world.

    python3 tools/test_sky.py

Nothing here needs PX4 or Gazebo. What it CANNOT check is the only thing
that finally matters - whether the dome renders. It checks the things
that would make it fail to render, or render inside out, or render black.
"""
import math
import os
import re
import sys

import numpy as np
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDS = os.path.join(REPO, "sim", "worlds")
MEDIA = os.path.join(WORLDS, "media")

MESH = os.path.join(MEDIA, "sky_dome.obj")
TEXTURE = os.path.join(MEDIA, "sky_day.png")

failures = []
checks = [0]


def check(name, ok, detail=""):
    checks[0] += 1
    print("  %-58s %s" % (name, "ok" if ok else "FAILED"))
    if not ok:
        failures.append("%s%s" % (name, (" - " + detail) if detail else ""))


def read_obj(path):
    verts, uvs, norms, faces = [], [], [], []
    with open(path) as handle:
        for line in handle:
            bits = line.split()
            if not bits:
                continue
            if bits[0] == "v":
                verts.append(tuple(float(x) for x in bits[1:4]))
            elif bits[0] == "vt":
                uvs.append(tuple(float(x) for x in bits[1:3]))
            elif bits[0] == "vn":
                norms.append(tuple(float(x) for x in bits[1:4]))
            elif bits[0] == "f":
                faces.append(tuple(int(p.split("/")[0]) for p in bits[1:4]))
    return (np.array(verts), np.array(uvs), np.array(norms),
            np.array(faces, dtype=int))


def test_mesh():
    print("\nThe dome mesh")
    if not os.path.isfile(MESH):
        check("sky_dome.obj exists", False, "run tools/make_sky_dome.py")
        return
    check("sky_dome.obj exists", True)

    verts, uvs, norms, faces = read_obj(MESH)
    check("it has vertices, UVs, normals and faces",
          len(verts) > 100 and len(uvs) == len(verts)
          and len(norms) == len(verts) and len(faces) > 100,
          "%d v, %d vt, %d vn, %d f" % (len(verts), len(uvs),
                                        len(norms), len(faces)))

    radii = np.linalg.norm(verts, axis=1)
    check("every vertex sits on the unit sphere",
          bool(np.all(np.abs(radii - 1.0) < 1e-4)),
          "radius %.5f to %.5f" % (radii.min(), radii.max()))

    # The whole point of a custom mesh: nothing to back-face cull.
    unit = verts / np.clip(radii, 1e-9, None)[:, None]
    inward = np.sum(unit * norms, axis=1)
    check("every normal points INWARD, at the aircraft",
          bool(np.all(inward < -0.999)),
          "worst dot %.4f (should be -1)" % inward.max())

    check("face indices are all in range",
          bool(faces.min() >= 1 and faces.max() <= len(verts)),
          "%d to %d of %d" % (faces.min(), faces.max(), len(verts)))

    a = verts[faces[:, 0] - 1]
    b = verts[faces[:, 1] - 1]
    c = verts[faces[:, 2] - 1]
    cross = np.cross(b - a, c - a)
    centroid = (a + b + c) / 3.0
    facing = np.sum(cross * centroid, axis=1)
    # Degenerate triangles happen at the two poles, where a quad collapses.
    real = np.abs(facing) > 1e-9
    check("every triangle is WOUND to be seen from inside",
          bool(np.all(facing[real] < 0)),
          "%d of %d wound outwards" % (int(np.sum(facing[real] >= 0)),
                                       int(real.sum())))

    check("UVs cover the whole image",
          bool(uvs[:, 0].min() < 1e-6 and uvs[:, 0].max() > 1 - 1e-6
               and uvs[:, 1].min() < 1e-6 and uvs[:, 1].max() > 1 - 1e-6),
          "u %.3f..%.3f  v %.3f..%.3f" % (uvs[:, 0].min(), uvs[:, 0].max(),
                                          uvs[:, 1].min(), uvs[:, 1].max()))

    # The seam is duplicated rather than wrapped, or the last column of
    # faces would stretch the entire image across five degrees.
    seam_zero = np.sum(np.abs(uvs[:, 0]) < 1e-9)
    seam_one = np.sum(np.abs(uvs[:, 0] - 1.0) < 1e-9)
    check("the azimuth seam is duplicated, not wrapped",
          seam_zero > 1 and seam_zero == seam_one,
          "%d vertices at u=0, %d at u=1" % (seam_zero, seam_one))

    # v=1 must be the zenith. gz-common imports meshes with
    # aiProcess_FlipUVs set - graphics/src/AssimpLoader.cc line 877 - so
    # v in the file arrives flipped. With this the wrong way round the
    # dome still renders, in the painted ground-haze tone, all over the
    # sky. That is exactly what happened on the first flight of it.
    top = verts[np.abs(uvs[:, 1] - 1.0) < 1e-9]
    bottom = verts[np.abs(uvs[:, 1]) < 1e-9]
    check("v=1 is the zenith (gz flips UVs on import)",
          bool(len(top) and np.all(top[:, 2] > 0.999)),
          "z %.3f" % (top[:, 2].min() if len(top) else float("nan")))
    check("v=0 is the nadir",
          bool(len(bottom) and np.all(bottom[:, 2] < -0.999)),
          "z %.3f" % (bottom[:, 2].max() if len(bottom) else float("nan")))


def test_texture():
    print("\nThe sky image")
    if not os.path.isfile(TEXTURE):
        check("sky_day.png exists", False, "run tools/make_sky_dome.py")
        return
    check("sky_day.png exists", True)

    image = Image.open(TEXTURE)
    pixels = np.asarray(image.convert("RGB")).astype(float)
    height, width = pixels.shape[:2]
    check("it is equirectangular - twice as wide as high",
          width == 2 * height, "%dx%d" % (width, height))

    zenith = pixels[2].mean(0)
    horizon = pixels[int(height * 0.5) - 3].mean(0)
    below = pixels[int(height * 0.75)].mean(0)

    check("the zenith is darker than the horizon",
          zenith.mean() < horizon.mean() - 40,
          "zenith %s, horizon %s" % (zenith.round(0), horizon.round(0)))
    check("the zenith is blue, not grey",
          zenith[2] > zenith[0] + 60,
          "RGB %s" % zenith.round(0))
    check("there is a pale haze band at the horizon",
          horizon.mean() > 180, "RGB %s" % horizon.round(0))
    check("below the horizon is a dull tone, not sky",
          below[2] < below[1] + 10, "RGB %s" % below.round(0))

    # Flat sky was the complaint. Cloud has to actually vary.
    band = pixels[int(height * 0.18):int(height * 0.42)].mean(2)
    check("the sky band is not one flat wash",
          float(band.std()) > 12.0, "standard deviation %.1f" % band.std())

    # The seam runs down the middle of a camera view sooner or later.
    seam = np.abs(pixels[:, 0] - pixels[:, -1]).mean()
    check("the left and right edges meet without a seam",
          float(seam) < 6.0, "mean difference %.2f" % seam)


def test_worlds():
    print("\nEvery world")
    paths = sorted(p for p in os.listdir(WORLDS) if p.endswith(".sdf"))
    check("there are worlds to check", bool(paths))

    missing_dome, still_sky, bright, bad_scale = [], [], [], []
    for name in paths:
        with open(os.path.join(WORLDS, name)) as handle:
            text = handle.read()
        if 'name="sky_dome"' not in text:
            missing_dome.append(name)
        scene = re.search(r"<scene>.*?</scene>", text, re.DOTALL)
        scene_text = scene.group(0) if scene else ""
        if re.search(r"<sky\s*/>|<sky>.*?</sky>", scene_text, re.DOTALL):
            still_sky.append(name)
        found = re.search(r"<ambient>([^<]*)</ambient>", scene_text)
        if found:
            first = float(found.group(1).split()[0])
            if first > 0.30:
                bright.append("%s (%.2f)" % (name, first))
        scale = re.search(r"<scale>(\d+) \d+ \d+</scale>", text)
        if scale and int(scale.group(1)) >= 8000:
            bad_scale.append("%s (%s m)" % (name, scale.group(1)))

    check("every world has the sky dome", not missing_dome,
          ", ".join(missing_dome))
    check("no world still has the flat built-in sky", not still_sky,
          ", ".join(still_sky))
    check("no world still has the washed-out 0.40 ambient", not bright,
          ", ".join(bright))
    check("the dome is inside the cameras' 8 km clip plane", not bad_scale,
          ", ".join(bad_scale))

    # install_worlds.py copies what the worlds ask for by name; a typo
    # here would be a dome that loads with no sky on it.
    sample = os.path.join(WORLDS, paths[0]) if paths else None
    if sample:
        with open(sample) as handle:
            text = handle.read()
        wanted = re.findall(r"file://media/(sky_[A-Za-z0-9_.-]+)", text)
        gone = [w for w in wanted if not os.path.isfile(os.path.join(MEDIA, w))]
        check("the sky files the worlds ask for exist", not gone,
              ", ".join(gone))


def test_time_of_day():
    print("\nThe day/night control")
    path = os.path.join(REPO, "plugins", "time_of_day.py")
    with open(path) as handle:
        source = handle.read()
    sys.path.insert(0, REPO)
    try:
        import importlib
        module = importlib.import_module("plugins.time_of_day")
        importlib.reload(module)
    except Exception as exc:                      # noqa: BLE001
        check("the plugin imports", False, str(exc))
        return
    check("the plugin imports", True)

    times = module.TIMES
    check("every time of day has a sky tint",
          all("sky" in t for t in times.values()),
          ", ".join(k for k, t in times.items() if "sky" not in t))
    check("midday leaves the sky as painted",
          times["day"]["sky"] == (1.0, 1.0, 1.0),
          str(times["day"]["sky"]))
    check("night is a dark sky, not a blue one",
          max(times["night"]["sky"]) < 0.2, str(times["night"]["sky"]))
    check("dusk is between the two",
          max(times["night"]["sky"]) < max(times["dusk"]["sky"])
          < max(times["day"]["sky"]),
          "dusk %s" % (times["dusk"]["sky"],))
    check("it dims the dome by its scoped visual name",
          module.SKY_VISUAL.count("::") == 2, module.SKY_VISUAL)
    check("it publishes on material_color, the topic Gazebo listens on",
          "material_color" in source and "gz.msgs.MaterialColor" in source)


def main():
    print("Checking the painted sky")
    test_mesh()
    test_texture()
    test_worlds()
    test_time_of_day()

    print("\n%d checks." % checks[0])
    if failures:
        print("\n%d FAILED:" % len(failures))
        for line in failures:
            print("  - %s" % line)
        print("\nMost of these are fixed by, in order:")
        print("    python3 tools/make_sky_dome.py")
        print("    python3 tools/sky_dome_apply.py --all")
        print("    python3 tools/install_worlds.py")
        return 1
    print("\nAll good. Not checked: whether any of it renders.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
