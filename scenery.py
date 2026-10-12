"""
What is on the ground in each training area, and why.

Added 12 Oct 2026. Until now every world was bare: a heightmap, a ground
plane and four distance markers. That was fine when the only pictures
were a nose camera pointed at the horizon and a chase camera pointed at
the aircraft. It is not fine now there is a gimbal: a sensor operator
cannot be taught to find, identify and hold a target in a world with
nothing in it, and "fly out to 400 m and look at the ground" is not a
lesson.

THIS FILE IS THE CONTENT. tools/scenery_apply.py is the tool that writes
it into a world file. They are separate so the layout can be checked by
tools/test_scenery.py without touching any world.

WHAT IS IN EACH PLACE
---------------------
Chosen to be what a remote pilot would actually see there, because a
student who learns to recognise a shape in the wrong landscape has
learned nothing:

  desert (Hoggar, Algeria)   boulder fields, a dry wadi, a graded track,
                             a mud-brick compound, a palm cluster, a
                             pair of pickups
  playa (Black Rock, Nevada) a dead-flat lake bed, scattered sage, a
                             straight dirt road, a line of marker drums,
                             a hangar and a windsock
  dryland (Nullarbor, AUS)   saltbush, a red dirt road, a station shed
                             and water tank, a telegraph line, a stock
                             fence
  saltflat (Uyuni, Bolivia)  salt-harvest mounds, a rail line, a small
                             block building, parked vehicles
  lowland (northern Europe)  hedged fields, woodland blocks, a farm with
                             a barn, a metalled road, a church with a
                             spire, a wind turbine, pylons

EVERYTHING IS A PRIMITIVE. Boxes, cylinders, spheres and cones. No
meshes, because a mesh is a file that has to be installed on the
teaching machine and found by Gazebo's resource path, and the whole
point of this project's world files is that they drop into any PX4
install. A box with a pitched roof is obviously a building from 120 m up,
which is the only range anyone sees it from.

PLACEMENT IS DETERMINISTIC. The same world comes out identical every
time, because a lesson that says "the target is the orange container
north-east of the farm" must still be true tomorrow. It is a seeded
pseudo-random layout, not a random one, and the seed is the world's own
name.

NOTHING WITHIN THE CLEAR RADIUS. The first 90 m around the origin stays
empty: that is where the aircraft spawns, arms, hovers and lands, and an
obstacle there would turn every lesson into a crash. Beyond that,
buildings and masts DO have collision, deliberately - an obstacle an
aircraft can fly through teaches a student that obstacles do not matter.
Vegetation does not, because a tree with collision at 25 m/s is a crash
with no lesson in it and a lot of contact solving.

TARGETS. Every area carries three high-contrast marked panels at known
bearings and ranges from the origin, numbered 1 to 3. They are there so
an instructor can say "find target 2" and mean something, and so the
payload lesson has a pass/fail. Their positions are printed by the tool
and listed in docs/scenery-targets.md.
"""
import math

# The ground around the launch point that stays clear, in metres.
CLEAR_RADIUS_M = 90.0

# How far out scenery is placed. Beyond 1500 m nothing is identifiable
# from a training height anyway, and the station's own range limit is
# 500 m, so most of it is there to be looked AT rather than flown over.
NEAR_M, FAR_M = 110.0, 1500.0


class Rng:
    """A small deterministic generator.

    Python's random module would do, but its stream is not guaranteed
    stable across versions, and the whole point here is that a world laid
    out today is laid out identically in two years. This is a plain
    32-bit linear congruential generator with the constants from Numerical
    Recipes - unremarkable, and completely reproducible.
    """

    def __init__(self, seed):
        self.state = seed & 0xFFFFFFFF

    def next(self):
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state

    def unit(self):
        return self.next() / 4294967296.0

    def between(self, low, high):
        return low + (high - low) * self.unit()

    def pick(self, items):
        return items[self.next() % len(items)]


def seed_for(name):
    """A stable seed from a world name - not hash(), which is salted."""
    value = 0
    for ch in name:
        value = (value * 131 + ord(ch)) & 0xFFFFFFFF
    return value or 1


# --------------------------------------------------------------------
# THE SHAPES
#
# Each returns a list of (kind, args) parts in LOCAL coordinates, which
# the writer turns into SDF. Keeping them as data rather than as strings
# is what lets the test check a tree is taller than it is wide without
# parsing XML.
# --------------------------------------------------------------------

def box(x, y, z, sx, sy, sz, colour, yaw=0.0, collide=False):
    return ("box", {"x": x, "y": y, "z": z, "sx": sx, "sy": sy, "sz": sz,
                    "colour": colour, "yaw": yaw, "collide": collide})


def cyl(x, y, z, r, h, colour, pitch=0.0, yaw=0.0, collide=False):
    return ("cylinder", {"x": x, "y": y, "z": z, "r": r, "h": h,
                         "colour": colour, "pitch": pitch, "yaw": yaw,
                         "collide": collide})


def sphere(x, y, z, r, colour, squash=1.0):
    return ("sphere", {"x": x, "y": y, "z": z, "r": r, "colour": colour,
                       "squash": squash})


def cone(x, y, z, r, h, colour):
    # Gazebo 8 has no cone primitive everywhere, so a cone is a cylinder
    # with a tiny top - which at these sizes is indistinguishable and
    # needs no capability check.
    return ("cone", {"x": x, "y": y, "z": z, "r": r, "h": h, "colour": colour})


WALL = (0.78, 0.74, 0.66)
MUD = (0.62, 0.50, 0.36)
ROOF_RED = (0.42, 0.18, 0.13)
ROOF_GREY = (0.30, 0.31, 0.33)
METAL = (0.62, 0.64, 0.66)
TARMAC = (0.17, 0.17, 0.18)
DIRT = (0.56, 0.44, 0.30)
RED_DIRT = (0.56, 0.28, 0.16)
LEAF = (0.17, 0.33, 0.15)
LEAF_DRY = (0.38, 0.40, 0.24)
TRUNK = (0.26, 0.20, 0.14)
SCRUB = (0.42, 0.44, 0.30)
ROCK = (0.45, 0.43, 0.40)
SALT = (0.92, 0.92, 0.94)
GRASS = (0.26, 0.40, 0.19)
CROP = (0.56, 0.54, 0.26)
HEDGE = (0.16, 0.26, 0.13)
WATER = (0.16, 0.28, 0.36)
HI_VIS = (0.95, 0.42, 0.05)


def building(w, d, h, wall, roof, pitched=True):
    """A box with a roof. Collides - it is an obstacle."""
    parts = [box(0, 0, h / 2, w, d, h, wall, collide=True)]
    if pitched:
        # Two slabs leaning against each other reads as a pitched roof
        # from above and from the side, which is the only angle it is
        # seen from.
        slope = math.radians(22)
        half = w / 2
        parts.append(box(-half / 2, 0, h + half * math.tan(slope) / 2,
                         half / math.cos(slope), d, 0.12, roof, yaw=0.0))
        parts.append(box(half / 2, 0, h + half * math.tan(slope) / 2,
                         half / math.cos(slope), d, 0.12, roof, yaw=0.0))
    else:
        parts.append(box(0, 0, h + 0.1, w * 1.06, d * 1.06, 0.2, roof))
    return parts


def tree(height, leaf=LEAF):
    r = height * 0.26
    return [cyl(0, 0, height * 0.28, height * 0.05, height * 0.56, TRUNK),
            sphere(0, 0, height * 0.72, r, leaf, squash=0.82),
            sphere(r * 0.4, 0, height * 0.58, r * 0.72, leaf, squash=0.8)]


def palm(height):
    return [cyl(0, 0, height / 2, height * 0.035, height, (0.40, 0.33, 0.22)),
            sphere(0, 0, height, height * 0.22, (0.22, 0.36, 0.16), squash=0.35)]


def bush(size, colour=SCRUB):
    return [sphere(0, 0, size * 0.35, size, colour, squash=0.45)]


def boulder(size):
    return [sphere(0, 0, size * 0.3, size, ROCK, squash=0.62)]


def vehicle(colour=(0.85, 0.85, 0.85)):
    return [box(0, 0, 0.75, 5.2, 2.0, 1.0, colour, collide=True),
            box(-0.4, 0, 1.5, 2.4, 1.9, 0.9, (0.2, 0.22, 0.25)),
            cyl(1.7, 1.0, 0.38, 0.38, 0.25, (0.1, 0.1, 0.1), pitch=1.5708),
            cyl(1.7, -1.0, 0.38, 0.38, 0.25, (0.1, 0.1, 0.1), pitch=1.5708),
            cyl(-1.7, 1.0, 0.38, 0.38, 0.25, (0.1, 0.1, 0.1), pitch=1.5708),
            cyl(-1.7, -1.0, 0.38, 0.38, 0.25, (0.1, 0.1, 0.1), pitch=1.5708)]


def container(colour=HI_VIS):
    return [box(0, 0, 1.3, 12.2, 2.44, 2.6, colour, collide=True)]


def hangar(w=28.0, d=18.0, h=6.0):
    parts = [box(0, 0, h / 2, w, d, h, METAL, collide=True)]
    for i in range(7):
        a = math.pi * i / 6.0
        parts.append(box(math.cos(a) * w * 0.44, 0,
                         h + math.sin(a) * 2.6, w * 0.16, d * 1.02, 0.4, METAL))
    return parts


def mast(height, colour=METAL):
    return [cyl(0, 0, height / 2, 0.22, height, colour, collide=True),
            box(0, 0, height * 0.92, 0.3, height * 0.22, 0.2, colour)]


def windsock():
    return [cyl(0, 0, 3.0, 0.08, 6.0, (0.85, 0.85, 0.85), collide=True),
            cone(0, 1.4, 5.6, 0.45, 2.4, (0.95, 0.45, 0.05))]


def turbine(height=70.0):
    parts = [cyl(0, 0, height / 2, 1.6, height, (0.92, 0.92, 0.92), collide=True),
             box(0, 0, height + 1.2, 6.0, 2.2, 2.2, (0.92, 0.92, 0.92))]
    for i in range(3):
        a = 2 * math.pi * i / 3
        parts.append(box(0, math.cos(a) * 18.0, height + 1.2 + math.sin(a) * 18.0,
                         0.5, 36.0 * abs(math.cos(a)) + 1.0,
                         36.0 * abs(math.sin(a)) + 1.0, (0.95, 0.95, 0.95)))
    return parts


def church():
    parts = building(10.0, 24.0, 7.0, WALL, ROOF_GREY)
    parts.append(box(0, -13.0, 9.0, 5.0, 5.0, 18.0, WALL, collide=True))
    parts.append(cone(0, -13.0, 18.0, 3.4, 11.0, ROOF_GREY))
    return parts


def pylon(height=26.0):
    parts = [cyl(0, 0, height / 2, 0.5, height, (0.55, 0.56, 0.58), collide=True)]
    for z in (height * 0.7, height * 0.86, height):
        parts.append(box(0, 0, z, 0.3, height * 0.42, 0.3, (0.55, 0.56, 0.58)))
    return parts


def water_tank():
    return [cyl(0, 0, 4.5, 3.2, 3.0, (0.60, 0.58, 0.50), collide=True),
            cyl(-2.4, 0, 3.0, 0.12, 6.0, METAL),
            cyl(2.4, 0, 3.0, 0.12, 6.0, METAL)]


def salt_mound(size):
    return [cone(0, 0, 0, size, size * 0.8, SALT)]


def strip(length, width, colour, thickness=0.06):
    """A road, a track, a runway or a rail - a thin slab on the ground."""
    return [box(0, 0, thickness / 2, length, width, thickness, colour)]


def field(size, colour):
    return [box(0, 0, 0.04, size, size, 0.04, colour)]


def hedge(length):
    return [box(0, 0, 1.1, length, 1.8, 2.2, HEDGE)]


def fence(length):
    return [box(0, 0, 0.6, length, 0.08, 0.1, (0.45, 0.42, 0.38)),
            box(0, 0, 1.1, length, 0.08, 0.1, (0.45, 0.42, 0.38))]


def target_panel(number):
    """A high-contrast marked panel for a payload lesson.

    Chequered, because a plain panel against a plain desert is invisible
    at 400 m and a chequer is exactly what a real calibration target is.
    The number is readable only close in, which is the point: the
    operator has to zoom.
    """
    parts = [box(0, 0, 1.6, 0.3, 6.0, 3.2, (0.95, 0.95, 0.95), collide=True)]
    for i in range(3):
        for j in range(2):
            if (i + j) % 2:
                continue
            parts.append(box(0.2, -2.0 + i * 2.0, 0.8 + j * 1.6,
                             0.05, 2.0, 1.6, (0.05, 0.05, 0.05)))
    parts.append(cyl(0, 0, 0.3, 0.3, 0.6, HI_VIS))
    for i in range(number):
        parts.append(box(0.25, -1.0 + i * 1.0, 3.5, 0.1, 0.5, 0.5, HI_VIS))
    return parts


# --------------------------------------------------------------------
# THE PLACES
#
# Each theme is a list of (name, builder, how many, how to place). The
# placement is done below so that every theme gets the same clear radius
# and the same deterministic layout.
# --------------------------------------------------------------------

def _scatter(rng, count, near, far, builder):
    out = []
    for i in range(count):
        angle = rng.between(0, 2 * math.pi)
        radius = math.sqrt(rng.between((near / far) ** 2, 1.0)) * far
        out.append((rng.between(0, 2 * math.pi), radius * math.cos(angle),
                    radius * math.sin(angle), builder(rng, i)))
    return out


def _line(rng, count, start, bearing_deg, spacing, builder, jitter=0.0):
    """Things in a row - a fence, a telegraph line, a line of drums."""
    out = []
    bearing = math.radians(bearing_deg)
    for i in range(count):
        along = start + i * spacing
        x = along * math.cos(bearing) + rng.between(-jitter, jitter)
        y = along * math.sin(bearing) + rng.between(-jitter, jitter)
        out.append((bearing, x, y, builder(rng, i)))
    return out


# The three payload targets, as (bearing from the launch point, range).
# Spread round the compass and at three different ranges, so finding one
# is not the same exercise as finding the next.
TARGETS = [(35.0, 260.0), (160.0, 430.0), (285.0, 700.0)]


def _targets():
    out = []
    for number, (bearing_deg, distance) in enumerate(TARGETS, start=1):
        bearing = math.radians(bearing_deg)
        # Bearing is from north, clockwise; the world is x-north, y-east.
        x = distance * math.cos(bearing)
        y = distance * math.sin(bearing)
        out.append((bearing + math.pi / 2, x, y, target_panel(number)))
    return out


def desert(rng):
    """Hoggar: rock, sand, a track and a small compound."""
    out = []
    out += _scatter(rng, 26, 120, 1200, lambda r, i: boulder(r.between(1.2, 4.5)))
    out += _scatter(rng, 34, 110, 900, lambda r, i: bush(r.between(0.5, 1.4), (0.40, 0.38, 0.25)))
    out += [(math.radians(28), 0, 0, strip(2600, 7.0, DIRT))]
    out += [(0.0, 300, -180, building(9, 14, 3.4, MUD, MUD, pitched=False))]
    out += [(0.6, 318, -164, building(6, 8, 2.8, MUD, MUD, pitched=False))]
    out += [(0.0, 292, -200, fence(40))]
    out += _scatter(rng, 7, 280, 420, lambda r, i: palm(r.between(5.0, 9.0)))
    out += [(1.2, 285, -150, vehicle((0.80, 0.78, 0.70))),
            (2.4, 310, -205, vehicle((0.35, 0.40, 0.33)))]
    # A dry wadi: a dark winding strip, in four straight pieces.
    for i, (x, y, yaw, length) in enumerate(
            ((-250, 400, 0.4, 420), (-120, 600, 0.9, 380),
             (30, 760, 0.3, 340), (210, 840, -0.2, 300))):
        out.append((yaw, x, y, strip(length, 22.0, (0.50, 0.45, 0.36), 0.05)))
    return out


def playa(rng):
    """Black Rock: dead flat, almost nothing, and that is the lesson."""
    out = []
    out += _scatter(rng, 20, 160, 1400, lambda r, i: bush(r.between(0.4, 0.9), (0.46, 0.46, 0.35)))
    out += [(0.0, 0, 0, strip(3000, 9.0, (0.70, 0.68, 0.62)))]
    out += [(math.radians(90), 0, 0, strip(2400, 6.0, (0.70, 0.68, 0.62)))]
    out += [(0.0, 180, 120, hangar()), (0.0, 150, 150, windsock())]
    out += [(0.0, 205, 150, container()), (0.3, 165, 176, vehicle())]
    # A line of marker drums down the "runway", which is how a playa
    # strip is actually marked out.
    out += _line(rng, 14, 140, 0.0, 70, lambda r, i: [
        cyl(0, 0, 0.45, 0.3, 0.9, HI_VIS if i % 2 else (0.95, 0.95, 0.95))])
    return out


def dryland(rng):
    """Nullarbor: saltbush, red dirt, a station and a telegraph line."""
    out = []
    out += _scatter(rng, 70, 110, 1300, lambda r, i: bush(r.between(0.5, 1.3), (0.40, 0.46, 0.33)))
    out += [(math.radians(75), 0, 0, strip(3000, 8.0, RED_DIRT))]
    out += [(0.0, -240, 300, building(14, 9, 3.2, METAL, ROOF_GREY)),
            (0.0, -262, 318, building(8, 6, 2.6, WALL, ROOF_RED)),
            (0.0, -228, 322, water_tank()),
            (0.4, -250, 280, vehicle((0.75, 0.30, 0.18)))]
    out += [(0.0, -270, 290, fence(260)), (math.radians(90), -270, 290, fence(220))]
    out += _line(rng, 16, 150, 75.0, 90, lambda r, i: [
        cyl(0, 0, 4.0, 0.14, 8.0, (0.35, 0.28, 0.20), collide=True),
        box(0, 0, 7.4, 0.2, 1.6, 0.12, (0.35, 0.28, 0.20))])
    out += _scatter(rng, 9, 400, 1200, lambda r, i: tree(r.between(4.0, 7.0), LEAF_DRY))
    return out


def saltflat(rng):
    """Uyuni: salt, harvest mounds, a rail line and a block hut."""
    out = []
    out += _scatter(rng, 44, 120, 1100, lambda r, i: salt_mound(r.between(1.0, 2.6)))
    # The rail line across the flat, as two rails and the sleepers.
    for offset in (-0.72, 0.72):
        out.append((math.radians(118), offset * math.sin(math.radians(118)),
                    -offset * math.cos(math.radians(118)),
                    strip(2800, 0.12, (0.35, 0.30, 0.26), 0.12)))
    out += _line(rng, 40, -1000, 118.0, 50,
                 lambda r, i: [box(0, 0, 0.05, 0.25, 2.5, 0.1, (0.30, 0.26, 0.22))])
    out += [(0.0, 420, 240, building(7, 5, 2.8, (0.72, 0.70, 0.66), ROOF_GREY, pitched=False)),
            (0.0, 440, 250, container((0.15, 0.35, 0.55))),
            (1.1, 405, 262, vehicle((0.9, 0.9, 0.9)))]
    out += _scatter(rng, 6, 300, 800, lambda r, i: [
        box(0, 0, 0.9, 3.0, 3.0, 1.8, SALT)])
    return out


def lowland(rng):
    """Northern Europe: hedged fields, woods, a farm, a church, a turbine."""
    out = []
    # The fields first, so everything else sits on top of them.
    for i in range(16):
        angle = rng.between(0, 2 * math.pi)
        radius = rng.between(200, 1300)
        size = rng.between(180, 320)
        colour = rng.pick([GRASS, CROP, (0.33, 0.44, 0.22), (0.48, 0.46, 0.28)])
        out.append((rng.between(0, 1.5), radius * math.cos(angle),
                    radius * math.sin(angle), field(size, colour)))
        out.append((rng.between(0, 1.5), radius * math.cos(angle),
                    radius * math.sin(angle) + size / 2, hedge(size)))
    out += _scatter(rng, 26, 150, 1200, lambda r, i: tree(r.between(9.0, 17.0)))
    # Two woodland blocks, which read as solid dark green from height.
    for x, y in ((-520, -340), (640, 420)):
        for i in range(22):
            out.append((0.0, x + rng.between(-60, 60), y + rng.between(-60, 60),
                        tree(rng.between(11.0, 18.0))))
    out += [(math.radians(18), 0, 0, strip(3000, 6.5, TARMAC))]
    out += [(math.radians(108), 0, 0, strip(2200, 4.5, TARMAC))]
    # The farm.
    out += [(0.0, -260, 200, building(12, 24, 6.5, (0.55, 0.42, 0.34), ROOF_RED)),
            (0.0, -236, 214, building(9, 12, 4.0, WALL, ROOF_RED)),
            (0.0, -280, 226, hangar(20, 12, 5.0)),
            (0.5, -252, 180, vehicle((0.20, 0.45, 0.22)))]
    out += [(0.0, 380, -300, church())]
    out += [(0.0, -800, 560, turbine(72.0))]
    out += _line(rng, 9, 260, 200.0, 140, lambda r, i: pylon(24.0))
    # A pond, because water is the one thing an infrared view makes
    # obvious and a daylight view does not.
    out += [(0.0, 180, -420, [sphere(0, 0, 0.02, 34.0, WATER, squash=0.004)])]
    return out


THEMES = {
    "desert": desert,
    "playa": playa,
    "dryland": dryland,
    "saltflat": saltflat,
    "lowland": lowland,
}

# Which theme each world gets. flat_test is deliberately absent: it
# exists to isolate faults, and putting scenery in it would defeat it.
WORLD_THEMES = {
    "training_area": "desert",
    "training_area_blackrock": "playa",
    "training_area_nullarbor": "dryland",
    "training_area_uyuni": "saltflat",
    "training_area_lowlands": "lowland",
}


def layout(world):
    """Everything to place in this world, as (yaw, x, y, parts).

    The payload targets are appended to every theme, and anything inside
    the clear radius is dropped rather than moved - moving it would make
    the layout depend on the order things were generated in, and the
    whole point is that it does not.
    """
    theme = WORLD_THEMES.get(world)
    if theme is None:
        return []
    rng = Rng(seed_for(world))
    placed = THEMES[theme](rng) + _targets()
    out = []
    for yaw, x, y, parts in placed:
        # A road or a field is centred on the origin on purpose and is
        # flat, so it is not an obstacle and is not dropped.
        flat = all(p[0] == "box" and p[1]["sz"] <= 0.2 for p in parts)
        if not flat and math.hypot(x, y) < CLEAR_RADIUS_M:
            continue
        out.append((yaw, x, y, parts))
    return out


def target_positions():
    """Where the three payload targets are, for the instructor's notes."""
    out = []
    for number, (bearing_deg, distance) in enumerate(TARGETS, start=1):
        bearing = math.radians(bearing_deg)
        out.append({"number": number, "bearing_deg": bearing_deg,
                    "range_m": distance,
                    "north_m": round(distance * math.cos(bearing), 1),
                    "east_m": round(distance * math.sin(bearing), 1)})
    return out
