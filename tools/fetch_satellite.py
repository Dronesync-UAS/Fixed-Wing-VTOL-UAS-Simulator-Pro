"""Downloads satellite imagery for a world, once, and caches it for offline use:

    python3 tools/fetch_satellite.py blackrock
    python3 tools/fetch_satellite.py blackrock --provider esri
    python3 tools/fetch_satellite.py --list

Why a one-off download rather than live tiles: the station has to work with no
internet. This fetches once, stitches the tiles into a single image, and writes
it next to the worlds. From then on the plan view draws it offline, exactly
like the terrain relief.

Why satellite at all, when the relief backdrop already exists: it does not help
on a flat world. Black Rock has 0.6 m of relief across the whole operating
area, so a hillshade of it is a blank grey square. Imagery is the only backdrop
that tells an instructor anything there.

PROVIDERS

  usgs (default)  The USGS National Map's imagery service. US federal imagery,
                  public domain, no API key, no usage limit worth worrying
                  about. Covers the United States only - so this is the right
                  choice for Black Rock and no use for the other three worlds.

  esri            Esri's World Imagery basemap. Global coverage. Widely used
                  this way, but it is Esri's service under Esri's terms, not
                  public domain - check those terms before relying on it for
                  anything beyond local training use. Offered because the three
                  non-US worlds have no public-domain alternative at this
                  resolution.

Nothing is downloaded until you ask for a specific world, and the provider is
always named in the output so it is clear what was used and under what terms.
"""

import argparse
import io
import json
import math
import os
import sys
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import sim_target  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
CACHE_DIR = os.path.join(REPO, "sim", "worlds", "satellite")

HALF_EXTENT_M = 2000.0     # a 4 km square centred on home
ZOOM = 16                  # about 1.8 m per pixel at 40 degrees latitude
TIMEOUT = 30

PROVIDERS = {
    "usgs": {
        "url": ("https://basemap.nationalmap.gov/arcgis/rest/services/"
                "USGSImageryOnly/MapServer/tile/{z}/{y}/{x}"),
        "credit": "USGS National Map imagery (public domain)",
    },
    "esri": {
        "url": ("https://server.arcgisonline.com/ArcGIS/rest/services/"
                "World_Imagery/MapServer/tile/{z}/{y}/{x}"),
        "credit": "Esri World Imagery - check Esri's terms of use",
    },
}


def lonlat_to_tile(lon, lat, zoom):
    """Web Mercator tile coordinates, as floats so a crop can be sub-tile."""
    n = 2.0 ** zoom
    x = (lon + 180.0) / 360.0 * n
    radians = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(radians)) / math.pi) / 2.0 * n
    return x, y


def world_latlon(world_file):
    path = os.path.join(PX4_WORLDS, world_file + ".sdf")
    if not os.path.isfile(path):
        path = os.path.join(REPO, "sim", "worlds", world_file + ".sdf")
    if not os.path.isfile(path):
        return None
    try:
        sc = ET.parse(path).getroot().find("world").find("spherical_coordinates")
        return float(sc.findtext("latitude_deg")), float(sc.findtext("longitude_deg"))
    except (ET.ParseError, AttributeError, TypeError, ValueError):
        return None


def fetch_tile(url, attempts=3):
    request = urllib.request.Request(url, headers={
        # Tile services reject the default Python agent.
        "User-Agent": "UAV-Academy-GCS-Pro/1.0 (training simulator; local use)"})
    last = None
    for _ in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return Image.open(io.BytesIO(response.read())).convert("RGB")
        except (urllib.error.URLError, OSError) as exc:
            last = exc
    raise RuntimeError(f"{url}\n    {last}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("world", nargs="?", help="environment key, e.g. blackrock")
    parser.add_argument("--provider", default="usgs", choices=sorted(PROVIDERS))
    parser.add_argument("--list", action="store_true", help="list the environments")
    args = parser.parse_args()

    if args.list or not args.world:
        print("Environments:")
        for env in sim_target.ENVIRONMENTS:
            coords = world_latlon(env["world"])
            where = f"{coords[0]:.4f}, {coords[1]:.4f}" if coords else "no coordinates"
            cached = os.path.isfile(os.path.join(CACHE_DIR, env["world"] + ".png"))
            print(f"  {env['key']:11} {where:22} {'cached' if cached else ''}")
        print("\nProviders:")
        for name, provider in sorted(PROVIDERS.items()):
            print(f"  {name:6} {provider['credit']}")
        return 0

    env = sim_target.BY_KEY.get(args.world)
    if env is None:
        print(f"Unknown environment: {args.world}")
        return 1
    coords = world_latlon(env["world"])
    if coords is None:
        print(f"Could not read coordinates for {env['world']}")
        return 1
    lat, lon = coords
    provider = PROVIDERS[args.provider]

    if args.provider == "usgs" and not (-170 < lon < -60 and 18 < lat < 72):
        print(f"{env['label']} is at {lat:.4f}, {lon:.4f} - outside USGS coverage.")
        print("Use --provider esri for this world, and check Esri's terms first.")
        return 1

    # Bounding box in degrees, from the same flat-earth conversion the plan
    # view uses, so the image lines up with the track.
    d_lat = HALF_EXTENT_M / 110540.0
    d_lon = HALF_EXTENT_M / (111320.0 * math.cos(math.radians(lat)))
    west, east = lon - d_lon, lon + d_lon
    south, north = lat - d_lat, lat + d_lat

    x0, y0 = lonlat_to_tile(west, north, ZOOM)     # top-left
    x1, y1 = lonlat_to_tile(east, south, ZOOM)     # bottom-right
    tx0, ty0, tx1, ty1 = (math.floor(x0), math.floor(y0),
                          math.floor(x1), math.floor(y1))
    columns, rows = tx1 - tx0 + 1, ty1 - ty0 + 1

    print(f"{env['label']}")
    print(f"  centre {lat:.5f}, {lon:.5f}   {HALF_EXTENT_M * 2:.0f} m square")
    print(f"  source {provider['credit']}")
    print(f"  {columns}x{rows} tiles at zoom {ZOOM} ({columns * rows} downloads)\n")

    stitched = Image.new("RGB", (columns * 256, rows * 256))
    for row in range(rows):
        for column in range(columns):
            url = provider["url"].format(z=ZOOM, x=tx0 + column, y=ty0 + row)
            try:
                tile = fetch_tile(url)
            except RuntimeError as exc:
                print(f"  FAILED: {exc}")
                print("\nNothing written. Check this machine has internet access,")
                print("and that the provider is reachable from it.")
                return 1
            stitched.paste(tile, (column * 256, row * 256))
            print(f"\r  downloaded {row * columns + column + 1}/{columns * rows}",
                  end="", flush=True)
    print()

    # Crop to the exact bounding box so the image registers with the track.
    left = int(round((x0 - tx0) * 256))
    top = int(round((y0 - ty0) * 256))
    right = int(round((x1 - tx0) * 256))
    bottom = int(round((y1 - ty0) * 256))
    cropped = stitched.crop((left, top, right, bottom))

    os.makedirs(CACHE_DIR, exist_ok=True)
    image_path = os.path.join(CACHE_DIR, env["world"] + ".png")
    cropped.save(image_path)
    with open(os.path.join(CACHE_DIR, env["world"] + ".json"), "w") as handle:
        json.dump({
            "world": env["world"],
            "provider": args.provider,
            "credit": provider["credit"],
            "zoom": ZOOM,
            "centre_lat": lat,
            "centre_lon": lon,
            "east_min": -HALF_EXTENT_M, "east_max": HALF_EXTENT_M,
            "north_min": -HALF_EXTENT_M, "north_max": HALF_EXTENT_M,
        }, handle, indent=2)

    size_kb = os.path.getsize(image_path) / 1024
    print(f"\n  saved {cropped.size[0]}x{cropped.size[1]}, {size_kb:.0f} KB")
    print(f"  {image_path}")
    print(f"\nRestart the station and the plan view will use it for this world.")
    print(f"Credit to show if this is ever published: {provider['credit']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
