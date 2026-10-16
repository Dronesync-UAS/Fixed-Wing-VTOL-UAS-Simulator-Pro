#!/usr/bin/env python3
"""
Builds the flat ground mesh the plane worlds stand on.

    python3 tools/make_ground_mesh.py
    python3 tools/make_ground_mesh.py --extent 8000 --tile 16

WHY A MESH AND NOT A HEIGHTMAP
------------------------------
The seven plane worlds needed a ground that TILES a texture - one image
repeated every few metres - because a <plane> visual stretches a single
image across its whole size and 1024 px over 220 km is 215 m per pixel.

The first answer, on 12 Oct 2026, was a dead-flat HEIGHTMAP, because
<heightmap><texture><size> is SDF's only built-in way to say "repeat this
every N metres". It did not work. Measured in Gazebo on 13 Oct 2026, with
the coast world loaded:

    camera    ground came back as
    chase     rgb(22,38,49), pixel variation 0.0
    payload   rgb(255,255,255), pixel variation 0.0
    nose      rgb(173,150,143), pixel variation 6.4

Three colours for one surface and no texture detail at all. The same
scene's valley world, whose terrain is also a heightmap with the same
<texture> block, came back with pixel variation 22.2 - properly textured.
The two differ in one thing: the valley's heightmap has 240 m of relief
and this one has none. Two attempts to keep the heightmap failed: giving
the image a real 0..255 range, and adding an explicit <material> with
roughness 1.0 and metalness 0. Neither changed any of the figures above.

So the heightmap goes. A mesh carries its own UV coordinates, and a UV
that runs 0..500 across the quad repeats the texture 500 times with no
terrain code involved at all. It is also EXACTLY flat, which a heightmap
with enough relief to render could never be - and flat matters, because
the collision these worlds land on is a separate 220 km box at z=0, and
any relief in the visual would show the aircraft sinking into the ground
or hovering above it.

WHAT IT WRITES
--------------
sim/worlds/media/ground_tile.obj - a flat square in the XY plane, centred
on the origin, with every normal straight up and UVs that repeat the
texture every <tile> metres.

It is subdivided rather than being two big triangles. A single quad that
size puts its vertices 8 km apart, and anything the renderer interpolates
between them - including the tangent basis a normal map needs - is then
being interpolated across the whole world.

NOT SEEN IN GAZEBO at the time of writing. The arithmetic is checked by
tools/test_surface_maps.py.
"""

import argparse
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")

# Matches plane_ground_texture.NEAR_EXTENT_M and TILE_M. They are repeated
# rather than imported so this tool stands alone, and the test checks the
# two agree.
EXTENT_M = 8000
TILE_M = 16
# How many cells across. 64 keeps the vertices 125 m apart, which is close
# enough for a tangent basis and still only 4225 vertices.
CELLS = 64


def build(extent, tile, cells):
    """An OBJ for a flat square, centred, tiling its texture every `tile` m."""
    half = extent / 2.0
    repeats = extent / float(tile)

    lines = [
        "# Flat ground for the plane worlds, written by",
        "# tools/make_ground_mesh.py. %g m square, texture repeating every"
        % extent,
        "# %g m (%g times across). Flat: every Z is 0 and every normal is up."
        % (tile, repeats),
        "",
    ]

    for row in range(cells + 1):
        for col in range(cells + 1):
            x = -half + extent * col / cells
            y = -half + extent * row / cells
            lines.append("v %.4f %.4f 0.0" % (x, y))

    for row in range(cells + 1):
        for col in range(cells + 1):
            lines.append("vt %.6f %.6f" % (repeats * col / cells,
                                           repeats * row / cells))

    lines.append("vn 0.0 0.0 1.0")

    def index(row, col):
        return row * (cells + 1) + col + 1          # OBJ counts from 1

    for row in range(cells):
        for col in range(cells):
            a, b = index(row, col), index(row, col + 1)
            c, d = index(row + 1, col + 1), index(row + 1, col)
            # Anticlockwise seen from above, so the face points up.
            lines.append("f %d/%d/1 %d/%d/1 %d/%d/1" % (a, a, b, b, c, c))
            lines.append("f %d/%d/1 %d/%d/1 %d/%d/1" % (a, a, c, c, d, d))

    return "\n".join(lines) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--extent", type=float, default=EXTENT_M,
                        help="metres across (default %g)" % EXTENT_M)
    parser.add_argument("--tile", type=float, default=TILE_M,
                        help="metres per texture repeat (default %g)" % TILE_M)
    parser.add_argument("--cells", type=int, default=CELLS,
                        help="subdivisions across (default %d)" % CELLS)
    args = parser.parse_args(argv)

    os.makedirs(MEDIA, exist_ok=True)
    path = os.path.join(MEDIA, "ground_tile.obj")
    with open(path, "w") as handle:
        handle.write(build(args.extent, args.tile, args.cells))

    print("Wrote %s" % path)
    print("  %g m square, %d x %d cells, texture every %g m (%g repeats)"
          % (args.extent, args.cells, args.cells, args.tile,
             args.extent / args.tile))
    print("  %.0f kB" % (os.path.getsize(path) / 1024))
    print("\nNow: python3 tools/plane_ground_texture.py --all")
    print("then: python3 tools/install_worlds.py, and restart PX4 and Gazebo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
