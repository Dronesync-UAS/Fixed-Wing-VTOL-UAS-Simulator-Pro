"""Downloads real elevation data and turns it into a Gazebo heightmap:

    python3 tools/fetch_terrain.py --list
    python3 tools/fetch_terrain.py coast
    python3 tools/fetch_terrain.py valley --key YOUR_OPENTOPOGRAPHY_KEY
    python3 tools/fetch_terrain.py coast --dry-run

WHAT IT IS FOR
--------------
Nine of the training areas are a flat plane with scenery on it, and one
(the valley) has a heightmap that was made up. That is the right trade
for most of them - the Fens, the Levels and an airfield genuinely are
flat, and a heightmap of flat ground is several megabytes of nothing.

But if a particular area needs to be the REAL ground - a site survey
rehearsal, or a brief for an actual job - this fetches the real
elevation for that world's own coordinates and writes a heightmap
beside the others. The world file then has to be pointed at it, which
this tool prints the exact change for rather than making it silently.

WHY IT IS NOT RUN AUTOMATICALLY
-------------------------------
Two reasons, both worth knowing:

  * it needs the internet, and the whole point of this station is that
    it works without it. Everything else in this project is offline
    after installation;
  * the only global source that is free, keyless and open is limited,
    and the good one needs a (free) API key. Downloading several
    hundred megabytes of elevation on somebody's behalf without asking
    is not acceptable.

WHERE THE DATA COMES FROM
-------------------------
  opentopography (default, needs a free key)
        Copernicus GLO-30 global DEM, 30 m postings, via OpenTopography's
        global DEM API. Free for non-commercial use; register at
        opentopography.org for a key, which takes a minute. Global.

  terrarium (no key)
        The AWS Terrain Tiles open dataset, as Terrarium-encoded PNG
        tiles. Open data, no key, no registration. Elevation is encoded
        in the pixel: height = (red * 256 + green + blue / 256) - 32768
        metres. Global, and the resolution varies with the source
        beneath it - typically 30 m over land.

Both are stated in the output so it is always clear what was used and
under what terms.

WHAT IT WRITES
--------------
    sim/worlds/media/<key>_real_heightmap.png     the terrain
    sim/worlds/media/<key>_real_heightmap.json    where it came from

and prints the exact <heightmap> block to paste into the world file,
with the <size> already worked out from the data.

THE THING THAT WILL BITE
------------------------
Real ground is not flat. The station enforces a 120 m ceiling above the
launch point and a 500 m range limit, so if the real relief within
500 m of the spawn point is more than about 100 m, there is no airspace
a student can legally fly in. This tool MEASURES that and says so before
you commit to it - which is the check that was missing when the Hoggar
world was first built and had to be flattened afterwards by
tools/widen_clearing.py.

NOT YET RUN. Neither provider is reachable from the machine this was
written on, so the download path has never executed. The arithmetic -
tile numbering, Terrarium decoding, the relief measurement - is checked
by tools/test_terrain_fetch.py against known values.
"""
import argparse
import io
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim_target                                           # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(REPO, "sim", "worlds", "media")

# How big a square to fetch, centred on the world's own coordinates. 8 km
# matches the valley heightmap and is four times the station's 2 km
# operating circle, so the horizon is never a visible edge.
HALF_EXTENT_M = 4000.0

# Gazebo wants 2^n + 1. 513 is what every other heightmap in this
# project uses; anything larger is collision geometry nobody flies near.
OUT_PX = 513

# Terrarium tiles at this zoom are about 30 m a pixel at 50 degrees
# latitude, which matches the source data rather than over-sampling it.
TERRARIUM_ZOOM = 12
TERRARIUM_URL = ("https://s3.amazonaws.com/elevation-tiles-prod/terrarium/"
                 "{z}/{x}/{y}.png")

OPENTOPO_URL = "https://portal.opentopography.org/API/globaldem"
OPENTOPO_DEM = "COP30"

TIMEOUT = 60

# The station's own limits, so the warning below is the real one.
CEILING_M = 120.0
RANGE_M = 500.0


# ------------------------------------------------------------------
# ARITHMETIC - no network, so tools/test_terrain_fetch.py can check it
# ------------------------------------------------------------------

def metres_per_degree(latitude_deg):
    """(north, east) metres in one degree, near enough for a few km."""
    return 111320.0, 111320.0 * math.cos(math.radians(latitude_deg))


def bounds(latitude_deg, longitude_deg, half_extent_m=HALF_EXTENT_M):
    """The south, north, west, east edges of the square to fetch."""
    per_north, per_east = metres_per_degree(latitude_deg)
    dlat = half_extent_m / per_north
    dlon = half_extent_m / per_east
    return (latitude_deg - dlat, latitude_deg + dlat,
            longitude_deg - dlon, longitude_deg + dlon)


def tile_xy(latitude_deg, longitude_deg, zoom):
    """Slippy-map tile numbers. The standard Web Mercator scheme every
    XYZ tile server uses, including the Terrain Tiles bucket."""
    lat = math.radians(latitude_deg)
    n = 2.0 ** zoom
    x = int((longitude_deg + 180.0) / 360.0 * n)
    y = int((1.0 - math.asinh(math.tan(lat)) / math.pi) / 2.0 * n)
    return x, y


def terrarium_height(red, green, blue):
    """Metres above sea level from one Terrarium pixel.

    The encoding is published by the Terrain Tiles dataset:
    height = (R * 256 + G + B / 256) - 32768.
    """
    return (red * 256.0 + green + blue / 256.0) - 32768.0


def relief_within(samples, metres_per_sample, radius_m):
    """The height range within radius_m of the centre of a square grid.

    This is the number that decides whether a world is usable: the
    station caps the ceiling at 120 m above the launch point, so a world
    whose ground already moves by more than that inside the range limit
    has no airspace left.
    """
    size = len(samples)
    middle = (size - 1) / 2.0
    lowest, highest = None, None
    reach = radius_m / metres_per_sample
    for row in range(size):
        for col in range(size):
            if math.hypot(row - middle, col - middle) > reach:
                continue
            value = samples[row][col]
            lowest = value if lowest is None else min(lowest, value)
            highest = value if highest is None else max(highest, value)
    if lowest is None:
        return 0.0, 0.0, 0.0
    return highest - lowest, lowest, highest


def to_greyscale(samples, floor, ceiling):
    """Map a grid of metres onto 0-255, as Gazebo reads a heightmap."""
    span = max(1e-6, ceiling - floor)
    out = []
    for row in samples:
        out.append([max(0, min(255, int(round((v - floor) / span * 255.0))))
                    for v in row])
    return out


# ------------------------------------------------------------------
# THE DOWNLOAD
# ------------------------------------------------------------------

def _get(url, headers=None, attempts=3):
    request = urllib.request.Request(url, headers=headers or {
        "User-Agent": "UAV-Academy-Simulator/1.0 (training use)"})
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except (urllib.error.URLError, OSError) as exc:
            last = exc
    raise RuntimeError("%s\n    %s" % (url, last))


def fetch_opentopography(south, north, west, east, key):
    """A single GeoTIFF covering the square, from OpenTopography."""
    query = urllib.parse.urlencode({
        "demtype": OPENTOPO_DEM, "south": south, "north": north,
        "west": west, "east": east, "outputFormat": "GTiff",
        "API_Key": key})
    data = _get(OPENTOPO_URL + "?" + query)
    try:
        import rasterio                                     # noqa: F401
    except ImportError:
        raise RuntimeError(
            "The OpenTopography download arrived but reading a GeoTIFF "
            "needs rasterio, which is not installed. Either\n"
            "    pip3 install rasterio\n"
            "or use the keyless provider instead:\n"
            "    python3 tools/fetch_terrain.py <world> --provider terrarium")
    import rasterio
    with rasterio.open(io.BytesIO(data)) as source:
        band = source.read(1)
    return [[float(v) for v in row] for row in band]


def fetch_terrarium(south, north, west, east):
    """Stitch Terrarium tiles covering the square and decode them."""
    from PIL import Image
    x0, y0 = tile_xy(north, west, TERRARIUM_ZOOM)
    x1, y1 = tile_xy(south, east, TERRARIUM_ZOOM)
    across, down = x1 - x0 + 1, y1 - y0 + 1
    canvas = Image.new("RGB", (across * 256, down * 256))
    for row in range(down):
        for col in range(across):
            url = TERRARIUM_URL.format(z=TERRARIUM_ZOOM, x=x0 + col, y=y0 + row)
            tile = Image.open(io.BytesIO(_get(url))).convert("RGB")
            canvas.paste(tile, (col * 256, row * 256))
    pixels = canvas.load()
    width, height = canvas.size
    return [[terrarium_height(*pixels[c, r]) for c in range(width)]
            for r in range(height)]


def resample(samples, size=OUT_PX):
    """Nearest-neighbour down to the output grid.

    Nearest rather than averaged on purpose: averaging a DEM rounds off
    exactly the ridge lines and gully bottoms that make terrain legible
    from the air, and at 30 m postings there is nothing to gain.
    """
    rows, cols = len(samples), len(samples[0])
    out = []
    for r in range(size):
        sr = min(rows - 1, int(r * rows / size))
        out.append([samples[sr][min(cols - 1, int(c * cols / size))]
                    for c in range(size)])
    return out


# ------------------------------------------------------------------

def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("world", nargs="?", help="a world key, e.g. coast")
    parser.add_argument("--list", action="store_true",
                        help="show the world keys and their coordinates")
    parser.add_argument("--provider", default="opentopography",
                        choices=("opentopography", "terrarium"))
    parser.add_argument("--key", default=os.environ.get("OPENTOPOGRAPHY_KEY"),
                        help="OpenTopography API key (or set "
                             "OPENTOPOGRAPHY_KEY in the environment)")
    parser.add_argument("--dry-run", action="store_true",
                        help="work out the square and the URLs, download "
                             "nothing")
    args = parser.parse_args(argv)

    if args.list or not args.world:
        print("World keys, and the coordinates their world file declares:\n")
        for env in sim_target.ENVIRONMENTS:
            lat, lon = _coords(env["world"])
            print("  %-10s %-30s %s"
                  % (env["key"], env["world"],
                     "%.4f, %.4f" % (lat, lon) if lat is not None
                     else "(no coordinates found)"))
        print("\n  python3 tools/fetch_terrain.py coast")
        return 0

    env = sim_target.BY_KEY.get(args.world)
    if env is None:
        print("Unknown world '%s'. Try --list." % args.world, file=sys.stderr)
        return 1
    latitude, longitude = _coords(env["world"])
    if latitude is None:
        print("No <spherical_coordinates> in %s.sdf - cannot work out where "
              "to fetch." % env["world"], file=sys.stderr)
        return 1

    south, north, west, east = bounds(latitude, longitude)
    print("%s (%s)" % (env["label"], env["world"]))
    print("  centre   %.4f, %.4f" % (latitude, longitude))
    print("  square   %.4f..%.4f N, %.4f..%.4f E  (%g km across)"
          % (south, north, west, east, HALF_EXTENT_M * 2 / 1000.0))
    print("  provider %s" % args.provider)

    if args.provider == "opentopography" and not args.key:
        print("\nOpenTopography needs a free API key. Register at "
              "https://portal.opentopography.org/ and then either pass\n"
              "    --key YOUR_KEY\n"
              "or set OPENTOPOGRAPHY_KEY in your environment. Or use the "
              "keyless provider:\n"
              "    python3 tools/fetch_terrain.py %s --provider terrarium"
              % args.world, file=sys.stderr)
        return 1

    if args.dry_run:
        if args.provider == "terrarium":
            x0, y0 = tile_xy(north, west, TERRARIUM_ZOOM)
            x1, y1 = tile_xy(south, east, TERRARIUM_ZOOM)
            print("  tiles    %d x %d at zoom %d, starting %s"
                  % (x1 - x0 + 1, y1 - y0 + 1, TERRARIUM_ZOOM,
                     TERRARIUM_URL.format(z=TERRARIUM_ZOOM, x=x0, y=y0)))
        else:
            print("  request  %s?demtype=%s&south=...&north=...&..."
                  % (OPENTOPO_URL, OPENTOPO_DEM))
        print("\nDry run - nothing downloaded.")
        return 0

    try:
        if args.provider == "terrarium":
            samples = fetch_terrarium(south, north, west, east)
        else:
            samples = fetch_opentopography(south, north, west, east, args.key)
    except RuntimeError as exc:
        print("\nDownload failed:\n  %s" % exc, file=sys.stderr)
        return 1

    grid = resample(samples)
    per_sample = HALF_EXTENT_M * 2 / (OUT_PX - 1)
    spread, floor, ceiling = relief_within(grid, per_sample, RANGE_M)
    total, lowest, highest = relief_within(grid, per_sample, HALF_EXTENT_M)

    print("\n  relief within %g m of the launch point: %.1f m (%.0f to %.0f)"
          % (RANGE_M, spread, floor, ceiling))
    print("  relief across the whole square:          %.1f m" % total)
    if spread > CEILING_M * 0.8:
        print("\n  WARNING. The station caps the ceiling at %g m above the\n"
              "  launch point. With %.0f m of relief inside the %g m range\n"
              "  limit there is little or no airspace a student can legally\n"
              "  fly in. Either pick a flatter centre, or flatten the middle\n"
              "  the way tools/widen_clearing.py did for the Hoggar world."
              % (CEILING_M, spread, RANGE_M))

    from PIL import Image
    grey = to_greyscale(grid, lowest, highest)
    image = Image.new("L", (OUT_PX, OUT_PX))
    pixels = image.load()
    for r in range(OUT_PX):
        for c in range(OUT_PX):
            pixels[c, r] = grey[r][c]
    os.makedirs(MEDIA, exist_ok=True)
    name = "%s_real_heightmap" % args.world
    path = os.path.join(MEDIA, name + ".png")
    image.save(path)
    with open(os.path.join(MEDIA, name + ".json"), "w") as handle:
        json.dump({"world": env["world"], "provider": args.provider,
                   "dem": OPENTOPO_DEM if args.provider == "opentopography"
                          else "AWS Terrain Tiles (Terrarium)",
                   "centre": [latitude, longitude],
                   "span_m": HALF_EXTENT_M * 2,
                   "lowest_m": lowest, "highest_m": highest,
                   "relief_within_%gm" % RANGE_M: spread},
                  handle, indent=2, sort_keys=True)

    print("\nWrote %s" % path)
    print("\nNow point the world at it. Open")
    print("    sim/worlds/%s.sdf" % env["world"])
    print("in a text editor, and replace the whole <model "
          "name=\"ground_plane\"> block with:\n")
    print(_heightmap_block(name, highest - lowest))
    print("Then restart the simulator.")
    return 0


def _heightmap_block(name, height_m):
    return """    <model name="real_terrain">
      <static>true</static>
      <pose>0 0 0 0 0 0</pose>
      <link name="terrain_link">
        <collision name="terrain_collision">
          <geometry>
            <heightmap>
              <uri>file://media/%s.png</uri>
              <size>%g %g %.2f</size>
            </heightmap>
          </geometry>
          <surface>
            <friction><ode/></friction>
            <bounce/>
            <contact/>
          </surface>
        </collision>
        <visual name="terrain_visual">
          <geometry>
            <heightmap>
              <uri>file://media/%s.png</uri>
              <size>%g %g %.2f</size>
              <texture>
                <diffuse>file://media/grass_diffuse.png</diffuse>
                <normal>file://media/flat_normal.png</normal>
                <size>24</size>
              </texture>
            </heightmap>
          </geometry>
        </visual>
      </link>
    </model>
""" % (name, HALF_EXTENT_M * 2, HALF_EXTENT_M * 2, max(1.0, height_m),
       name, HALF_EXTENT_M * 2, HALF_EXTENT_M * 2, max(1.0, height_m))


def _coords(world):
    """The latitude and longitude the world file itself declares."""
    import xml.etree.ElementTree as ET
    path = os.path.join(REPO, "sim", "worlds", world + ".sdf")
    try:
        root = ET.parse(path).getroot()
    except (OSError, ET.ParseError):
        return None, None
    block = root.find("world/spherical_coordinates")
    if block is None:
        return None, None
    try:
        return (float(block.find("latitude_deg").text),
                float(block.find("longitude_deg").text))
    except (AttributeError, TypeError, ValueError):
        return None, None


if __name__ == "__main__":
    sys.exit(main())
