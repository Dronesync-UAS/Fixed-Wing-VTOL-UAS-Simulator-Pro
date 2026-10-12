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

  mapbox          Mapbox Satellite. Global, high resolution, and the one most
                  people have heard of. Needs a free access token - make an
                  account at account.mapbox.com, copy the default public token,
                  and pass it with --token or set MAPBOX_TOKEN in your
                  environment. Mapbox's terms apply. Added 12 Oct 2026.

  mapbox-outdoors Mapbox's street and outdoors style rather than imagery -
                  roads, paths and place names, which is what is wanted when
                  the point is briefing an area rather than looking at it.
                  Same token.

  esri            Esri's World Imagery basemap. Global coverage. Widely used
                  this way, but it is Esri's service under Esri's terms, not
                  public domain - check those terms before relying on it for
                  anything beyond local training use. Offered because the three
                  non-US worlds have no public-domain alternative at this
                  resolution.

Nothing is downloaded until you ask for a specific world, and the provider is
always named in the output so it is clear what was used and under what terms.

WHERE THE MAPBOX TOKEN COMES FROM, in this order:

  1. --token on the command line
  2. MAPBOX_TOKEN in the environment
  3. ~/.mapbox_token - a file holding nothing but the token

The file is the one to use. Put the token in it once and every command
after that is the same command with no token in it, which matters here:
a token pasted into a terminal ends up in the shell history, and a
command with a placeholder in it has been pasted literally more than
once on this project.

The file's permissions are tightened to owner-only when it is read, and
it is NOT inside this repository, so it cannot be committed by accident.

THE TOKEN IS NEVER WRITTEN DOWN BY THIS TOOL. It goes into the request
and nowhere else - not into the cached image's sidecar, not into the
console's logs. A token in a file that gets copied between machines is a
token that leaks.
"""

import argparse
import io
import json
import math
import os
import re
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

# Outside the repository on purpose: a token inside it is a token that
# gets committed. See the docstring.
TOKEN_FILE = os.path.expanduser("~/.mapbox_token")

# flat_test is the bare calibration world: no scenery, and its
# coordinates are a placeholder rather than a place anyone flies,
# so imagery over it is five megabytes of somewhere else. --all
# leaves it out; asking for it by name still fetches it.
SKIP_IN_ALL = {"flat_test"}

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
    # Added 12 Oct 2026 on request. Mapbox is global, high resolution,
    # and the one most people have heard of - but unlike the two above
    # it needs an access token, which is why it cannot be the default.
    # A free account gives a token in a couple of minutes:
    # account.mapbox.com. The token is read from the command line or
    # from MAPBOX_TOKEN in the environment and is NOT written into the
    # cached file's metadata - a token in a file that gets copied
    # between machines is a token that leaks.
    "mapbox": {
        "url": ("https://api.mapbox.com/v4/mapbox.satellite/"
                "{z}/{x}/{y}@2x.jpg90?access_token={token}"),
        "credit": "Mapbox Satellite (c) Mapbox (c) Maxar",
        "needs_token": True,
        # @2x asks for 512 px tiles rather than 256, which is why this
        # one goes in at a zoom lower: the same ground at the same
        # detail, in a quarter of the requests.
        "tile_px": 512,
        "zoom_offset": -1,
    },
    # Mapbox's own street/outdoors style, for when the point is roads
    # and place names rather than imagery - which is what an instructor
    # briefing an area actually wants half the time.
    "mapbox-outdoors": {
        "url": ("https://api.mapbox.com/styles/v1/mapbox/outdoors-v12/tiles/"
                "512/{z}/{x}/{y}@2x?access_token={token}"),
        "credit": "Mapbox Outdoors (c) Mapbox (c) OpenStreetMap",
        "needs_token": True,
        "tile_px": 512,
        "zoom_offset": -1,
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


def read_token_file():
    """The token from ~/.mapbox_token, or None.

    Tightens the file to owner-only while it is here, because a token
    readable by every account on a shared teaching machine is not a
    secret. Failing to chmod is not fatal - some filesystems cannot.
    """
    try:
        with open(TOKEN_FILE) as handle:
            token = handle.read().strip()
    except OSError:
        return None
    if not token:
        return None
    try:
        os.chmod(TOKEN_FILE, 0o600)
    except OSError:
        pass
    return token


def safe_url(url):
    """A URL with any access token taken out of it.

    Found on 12 Oct 2026 by testing the failure path with a fake token:
    a download that failed printed the whole URL, and the whole URL
    contains ?access_token=pk.... So the one place the token was certain
    to appear on screen was the one place somebody would copy and paste
    to ask for help. Every URL this tool prints goes through here.
    """
    return re.sub(r"(access_token=)[^&\s]+", r"\1<token hidden>", url)


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
    raise RuntimeError(f"{safe_url(url)}\n    {last}")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("world", nargs="?", help="environment key, e.g. blackrock")
    parser.add_argument("--provider", default="usgs", choices=sorted(PROVIDERS))
    parser.add_argument("--token", default=None,
                        help="Mapbox access token. Only needed for the mapbox "
                             "providers, and only if it is not already in "
                             "MAPBOX_TOKEN or ~/.mapbox_token.")
    parser.add_argument("--all", action="store_true",
                        help="every environment that has coordinates, one "
                             "after another - about 36 tiles each")
    parser.add_argument("--list", action="store_true", help="list the environments")
    args = parser.parse_args()

    # The token, from whichever of the three places has one. Resolved
    # once here rather than in three places later.
    args.token = (args.token or os.environ.get("MAPBOX_TOKEN")
                  or read_token_file())

    if args.all:
        worlds = [env["key"] for env in sim_target.ENVIRONMENTS
                  if world_latlon(env["world"])
                  and env["world"] not in SKIP_IN_ALL]
        print("Fetching %d environments from %s.\n" % (len(worlds), args.provider))
        failed = []
        for key in worlds:
            args.world = key
            if fetch_one(args) != 0:
                failed.append(key)
            print()
        if failed:
            print("Finished, but these did not work: %s" % ", ".join(failed))
            return 1
        print("All %d done." % len(worlds))
        return 0

    if args.list or not args.world:
        print("Environments:")
        for env in sim_target.ENVIRONMENTS:
            coords = world_latlon(env["world"])
            where = f"{coords[0]:.4f}, {coords[1]:.4f}" if coords else "no coordinates"
            cached = os.path.isfile(os.path.join(CACHE_DIR, env["world"] + ".png"))
            print(f"  {env['key']:11} {where:22} {'cached' if cached else ''}")
        print("\nProviders:")
        for name, provider in sorted(PROVIDERS.items()):
            mark = (" - needs a token in ~/.mapbox_token, and "
                    "Mapbox's terms apply"
                    if provider.get("needs_token") else "")
            print(f"  {name:16} {provider['credit']}{mark}")
        return 0

    return fetch_one(args)


def fetch_one(args):
    """Fetch one world. Split out of main() on 12 Oct 2026 so --all can
    call it in a loop rather than main() calling itself."""
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

    if provider.get("needs_token") and not args.token:
        print(f"{args.provider} needs an access token, and there is none in")
        print(f"{TOKEN_FILE}, in MAPBOX_TOKEN, or on the command line.")
        print()
        print("Make a free account at https://account.mapbox.com/, copy the")
        print("default public token from your account page, and put it in that")
        print("file - one line, nothing else in it. Then this command works")
        print("with no token in it, every time.")
        print()
        print("Or use a provider that needs no token at all:")
        print()
        print(f"    python3 tools/fetch_satellite.py {args.world} --provider esri")
        return 1

    # A 512 px tile covers the same ground as four 256 px ones, so a
    # provider serving them goes in a zoom level lower for the same
    # detail - and a quarter of the downloads.
    tile_px = provider.get("tile_px", 256)
    zoom = ZOOM + provider.get("zoom_offset", 0)

    # Bounding box in degrees, from the same flat-earth conversion the plan
    # view uses, so the image lines up with the track.
    d_lat = HALF_EXTENT_M / 110540.0
    d_lon = HALF_EXTENT_M / (111320.0 * math.cos(math.radians(lat)))
    west, east = lon - d_lon, lon + d_lon
    south, north = lat - d_lat, lat + d_lat

    x0, y0 = lonlat_to_tile(west, north, zoom)     # top-left
    x1, y1 = lonlat_to_tile(east, south, zoom)     # bottom-right
    tx0, ty0, tx1, ty1 = (math.floor(x0), math.floor(y0),
                          math.floor(x1), math.floor(y1))
    columns, rows = tx1 - tx0 + 1, ty1 - ty0 + 1

    print(f"{env['label']}")
    print(f"  centre {lat:.5f}, {lon:.5f}   {HALF_EXTENT_M * 2:.0f} m square")
    print(f"  source {provider['credit']}")
    print(f"  {columns}x{rows} tiles at zoom {zoom}, {tile_px} px each "
          f"({columns * rows} downloads)\n")

    stitched = Image.new("RGB", (columns * tile_px, rows * tile_px))
    for row in range(rows):
        for column in range(columns):
            url = provider["url"].format(z=zoom, x=tx0 + column, y=ty0 + row,
                                         token=args.token or "")
            try:
                tile = fetch_tile(url)
            except RuntimeError as exc:
                print(f"  FAILED: {exc}")
                print("\nNothing written. Check this machine has internet access,")
                print("and that the provider is reachable from it.")
                return 1
            # Trust the tile's own size over the provider table: a
            # service that quietly serves 256 when 512 was asked for
            # would otherwise be pasted into a grid with gaps in it.
            if tile.size != (tile_px, tile_px):
                tile = tile.resize((tile_px, tile_px), Image.BICUBIC)
            stitched.paste(tile, (column * tile_px, row * tile_px))
            print(f"\r  downloaded {row * columns + column + 1}/{columns * rows}",
                  end="", flush=True)
    print()

    # Crop to the exact bounding box so the image registers with the track.
    left = int(round((x0 - tx0) * tile_px))
    top = int(round((y0 - ty0) * tile_px))
    right = int(round((x1 - tx0) * tile_px))
    bottom = int(round((y1 - ty0) * tile_px))
    cropped = stitched.crop((left, top, right, bottom))

    os.makedirs(CACHE_DIR, exist_ok=True)
    image_path = os.path.join(CACHE_DIR, env["world"] + ".png")
    cropped.save(image_path)
    with open(os.path.join(CACHE_DIR, env["world"] + ".json"), "w") as handle:
        json.dump({
            "world": env["world"],
            "provider": args.provider,
            "credit": provider["credit"],
            "zoom": zoom,
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
