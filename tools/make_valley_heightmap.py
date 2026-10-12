"""Generates the valley training area's terrain:

    python3 tools/make_valley_heightmap.py
    python3 tools/make_valley_heightmap.py --preview valley.png

Writes sim/worlds/media/valley_heightmap.png, which
sim/worlds/training_area_valley.sdf loads as its ground.

THIS TERRAIN IS SYNTHETIC. It is not a survey of anywhere. The world's
coordinates and magnetic field are real - the north Wales foothills -
because PX4's EKF needs a field that matches the latitude it is told it
is at, but the SHAPE of the ground is made up here. Nothing in this file
should be described to a student as a real place.

WHY MAKE ONE UP. The other training areas are real terrain, fetched from
elevation data. Doing that needs a download, and the point of this one
is a flight environment the others do not cover - a flat floor between
two ridges, where the aircraft is below the surrounding ground and the
horizon is 200 m above it. That shape is what matters, not which valley
it is.

THE SHAPE, AND WHY THESE NUMBERS
--------------------------------
The station enforces a 120 m ceiling above the launch point and a 500 m
range limit. A world with more relief than that inside the range limit
has no airspace a student can legally fly in - the same reasoning that
had tools/widen_clearing.py flatten 600 m of the Hoggar world.

So: the floor is DEAD FLAT out to 520 m either side of the valley axis,
which comfortably contains the whole legal operating area. Beyond that
the ground rises, reaching the full 240 m by about 1400 m out. The
valley runs north-south, so the ridges are to the east and west and a
student flying the length of the floor stays in level ground.

The ridges are not a smooth ramp: three sine terms of different
wavelengths give them spurs and gullies, so the ridge line is something
an operator can navigate by rather than a wall. The terms are
deterministic - the same file comes out every time this is run.

HOW GAZEBO READS IT. A heightmap PNG is greyscale: pixel 0 is the
model's own z, pixel 255 is z plus the height in <size>. The world
declares <size>8000 8000 240</size>, so one grey level is 0.94 m and
the floor sits at exactly 0.

513x513 to match the other heightmaps in this project - Gazebo wants
2^n+1, and anything larger is collision geometry nobody flies near.

NOT YET LOADED IN GAZEBO.
"""
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "sim", "worlds", "media", "valley_heightmap.png")

SIZE_PX = 513
SPAN_M = 8000.0          # what the world's <size> says the image covers
HEIGHT_M = 240.0         # and how tall pixel 255 is

FLOOR_HALF_WIDTH_M = 520.0    # dead flat out to here either side of the axis
RIDGE_TOP_M = 1400.0          # full height by here

# The three roughness terms below sum to at most this. Used to normalise
# them so the tallest point is exactly HEIGHT_M - see height_at().
ROUGHNESS_SUM = 0.16 + 0.09 + 0.05


def height_at(east_m, north_m):
    """Metres above the valley floor at a point, floor at 0."""
    across = abs(east_m)
    if across <= FLOOR_HALF_WIDTH_M:
        return 0.0
    # A smoothstep from the edge of the floor to the ridge top: it
    # leaves the floor horizontally rather than as a kink, which a
    # linear ramp would, and a kink is visible from the air.
    t = min(1.0, (across - FLOOR_HALF_WIDTH_M)
            / (RIDGE_TOP_M - FLOOR_HALF_WIDTH_M))
    base = t * t * (3.0 - 2.0 * t)
    # Spurs and gullies, so the ridge is something to navigate by.
    along = north_m
    rough = (0.16 * math.sin(along / 180.0) +
             0.09 * math.sin(along / 70.0 + 1.3) +
             0.05 * math.sin(along / 33.0 + 2.7))
    # Divided by the largest the three terms can sum to, so the tallest
    # possible point is exactly HEIGHT_M and nothing clips at pixel 255.
    # A clipped ridge comes out as a flat table top, which is the one
    # shape a real ridge never has. The ridge line therefore varies
    # between about 77% and 100% of full height along its length, which
    # is what gives it spurs and cols.
    shape = base * (1.0 + rough * base) / (1.0 + ROUGHNESS_SUM)
    # The roughness fades out at the floor edge, so it cannot put a bump
    # on the flat part.
    return max(0.0, shape) * HEIGHT_M


def build():
    from PIL import Image
    image = Image.new("L", (SIZE_PX, SIZE_PX))
    pixels = image.load()
    step = SPAN_M / (SIZE_PX - 1)
    half = SPAN_M / 2.0
    for row in range(SIZE_PX):
        north = half - row * step
        for col in range(SIZE_PX):
            east = -half + col * step
            value = height_at(east, north) / HEIGHT_M * 255.0
            pixels[col, row] = int(max(0, min(255, round(value))))
    return image


def main(argv):
    image = build()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    image.save(OUT)
    print("Wrote %s (%dx%d, %g m span, %g m of relief)"
          % (OUT, SIZE_PX, SIZE_PX, SPAN_M, HEIGHT_M))
    print("  floor is flat to +-%g m either side of the axis;"
          % FLOOR_HALF_WIDTH_M)
    print("  the ridges reach full height by %g m out." % RIDGE_TOP_M)
    if "--preview" in argv:
        where = argv[argv.index("--preview") + 1]
        image.resize((512, 512)).save(where)
        print("  preview written to %s" % where)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
