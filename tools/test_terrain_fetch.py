"""Check the terrain fetcher's arithmetic, with nothing downloaded.

    python3 tools/test_terrain_fetch.py

The download path cannot be tested here - neither elevation host is
reachable from the machine this was written on - so what is checked is
everything that happens either side of it, which is where the mistakes
would be anyway:

  * the slippy-map tile numbers, against values anyone can verify;
  * the Terrarium height encoding, against its published formula;
  * the relief measurement, which is the check that decides whether a
    world is flyable at all;
  * that every world's coordinates can be read back out of its own file.
"""
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


import fetch_terrain as ft                                  # noqa: E402
import sim_target                                           # noqa: E402

print("1. slippy-map tile numbers")
# At zoom 0 the whole world is one tile.
check("zoom 0 is a single tile", ft.tile_xy(0.0, 0.0, 0) == (0, 0))
# At zoom 1 the world is 2x2 and the prime meridian / equator is the
# corner between them: just east and north of it is tile (1, 0).
check("zoom 1, just NE of the origin, is tile (1, 0)",
      ft.tile_xy(1.0, 1.0, 1) == (1, 0))
check("zoom 1, just SW of the origin, is tile (0, 1)",
      ft.tile_xy(-1.0, -1.0, 1) == (0, 1))
# Greenwich at zoom 12: x is exactly half of 2^12.
check("the prime meridian at zoom 12 is x = 2048",
      ft.tile_xy(51.4778, 0.0, 12)[0] == 2048)
check("longitude increases the tile number",
      ft.tile_xy(52.0, 1.0, 12)[0] > ft.tile_xy(52.0, 0.0, 12)[0])
check("latitude increasing DECREASES it, because y runs south",
      ft.tile_xy(53.0, 0.0, 12)[1] < ft.tile_xy(52.0, 0.0, 12)[1])

print("2. the Terrarium height encoding")
# The published formula is (R * 256 + G + B / 256) - 32768.
check("sea level is R=128, G=0, B=0", ft.terrarium_height(128, 0, 0) == 0.0)
check("one metre up is G=1", ft.terrarium_height(128, 1, 0) == 1.0)
check("a quarter metre is B=64", ft.terrarium_height(128, 0, 64) == 0.25)
check("below sea level comes out negative",
      ft.terrarium_height(127, 255, 0) == -1.0)
check("Ben Nevis-ish: 1345 m", abs(ft.terrarium_height(133, 65, 0) - 1345.0) < 0.01)

print("3. the square it asks for")
south, north, west, east = ft.bounds(52.0, 0.0, 4000.0)
per_north, per_east = ft.metres_per_degree(52.0)
check("north and south are 4 km either side",
      abs((north - 52.0) * per_north - 4000.0) < 1.0)
check("east and west are too, allowing for the latitude",
      abs((east - 0.0) * per_east - 4000.0) < 1.0)
check("a degree of longitude is shorter at 52 N than at the equator",
      ft.metres_per_degree(52.0)[1] < ft.metres_per_degree(0.0)[1] * 0.7)

print("4. the relief measurement - the one that decides if a world is usable")
# A flat grid: no relief anywhere.
flat = [[100.0] * 51 for _ in range(51)]
check("flat ground has no relief", ft.relief_within(flat, 20.0, 500.0)[0] == 0.0)

# A grid that is flat in the middle and rises steeply outside it. The
# middle is 51x51 at 20 m a sample, so 500 m from the centre is 25
# samples - the whole grid. Use a bigger one so the radius bites.
size = 101
per = 20.0            # 20 m a sample, so the grid is 2 km across
grid = []
middle = (size - 1) / 2.0
for r in range(size):
    row = []
    for c in range(size):
        out_m = math.hypot(r - middle, c - middle) * per
        row.append(0.0 if out_m <= 400.0 else (out_m - 400.0) * 0.5)
    grid.append(row)
spread, low, high = ft.relief_within(grid, per, 300.0)
check("flat inside the flat part (%.1f m)" % spread, spread == 0.0)
spread, low, high = ft.relief_within(grid, per, 500.0)
check("and not flat once the radius reaches the slope (%.1f m)" % spread,
      40.0 < spread < 60.0)
spread, low, high = ft.relief_within(grid, per, 1000.0)
check("more relief over a wider circle (%.1f m)" % spread, spread > 250.0)

print("5. greyscale conversion")
grey = ft.to_greyscale([[0.0, 50.0, 100.0]], 0.0, 100.0)
check("the lowest point is 0", grey[0][0] == 0)
check("the highest is 255", grey[0][2] == 255)
check("halfway is halfway", 126 <= grey[0][1] <= 129)
# A flat world must not divide by zero.
grey = ft.to_greyscale([[7.0, 7.0]], 7.0, 7.0)
check("flat ground does not divide by zero", grey == [[0, 0]])

print("6. every world's coordinates can be read out of its own file")
for env in sim_target.ENVIRONMENTS:
    lat, lon = ft._coords(env["world"])
    check("%s: %s" % (env["key"],
                      "%.4f, %.4f" % (lat, lon) if lat is not None else "MISSING"),
          lat is not None and -90 <= lat <= 90 and -180 <= lon <= 180)

print("7. it refuses the keyed provider without a key, and says what to do")
import io                                                   # noqa: E402
import contextlib                                           # noqa: E402

captured = io.StringIO()
with contextlib.redirect_stderr(captured):
    code = ft.main(["coast", "--provider", "opentopography", "--key", ""])
check("it fails rather than downloading nothing", code == 1)
message = captured.getvalue()
check("it names the keyless alternative", "--provider terrarium" in message)
check("and where to get a key", "opentopography.org" in message)

print("8. a dry run downloads nothing and prints the square")
captured = io.StringIO()
with contextlib.redirect_stdout(captured):
    code = ft.main(["valley", "--provider", "terrarium", "--dry-run"])
out = captured.getvalue()
check("it succeeds", code == 0)
check("it says where", "52.9000, -3.8000" in out)
check("and how many tiles", "tiles" in out)
check("and that nothing was downloaded", "nothing downloaded" in out.lower())

print("9. the satellite imagery providers, including Mapbox")
import contextlib                                           # noqa: E402,F811
import io                                                    # noqa: E402,F811

import fetch_satellite as fs                                 # noqa: E402

check("there are keyless providers", "usgs" in fs.PROVIDERS and "esri" in fs.PROVIDERS)
check("and Mapbox", "mapbox" in fs.PROVIDERS)
check("Mapbox is marked as needing a token",
      fs.PROVIDERS["mapbox"].get("needs_token") is True)
check("the keyless ones are not",
      not fs.PROVIDERS["usgs"].get("needs_token")
      and not fs.PROVIDERS["esri"].get("needs_token"))
check("the default provider needs no token",
      not fs.PROVIDERS["usgs"].get("needs_token"))
# A 512 px tile covers four 256 px ones, so a provider serving them must
# drop a zoom level or the image comes out four times the ground.
check("Mapbox asks for 512 px tiles a zoom level lower",
      fs.PROVIDERS["mapbox"].get("tile_px") == 512
      and fs.PROVIDERS["mapbox"].get("zoom_offset") == -1)
check("its URL has somewhere to put the token",
      "{token}" in fs.PROVIDERS["mapbox"]["url"])

# main() reads sys.argv, so drive it that way.
saved_argv = sys.argv
sys.argv = ["fetch_satellite.py", "coast", "--provider", "mapbox"]
captured = io.StringIO()
try:
    with contextlib.redirect_stdout(captured):
        code = fs.main()
finally:
    sys.argv = saved_argv
message = captured.getvalue()
check("without a token it refuses rather than failing mid-download", code == 1)
check("and says where to get one", "account.mapbox.com" in message)
check("and offers the keyless alternative", "--provider esri" in message)

# The token must not end up on screen either. Found by testing the
# failure path with a fake token: a download that failed printed the
# whole URL, and the whole URL carries ?access_token=pk... - so the one
# place the token was certain to appear was the one place somebody would
# copy and paste to ask for help.
check("a printed URL has the token taken out of it",
      "pk.SECRET" not in fs.safe_url(
          "https://api.mapbox.com/v4/mapbox.satellite/15/1/1@2x.jpg90"
          "?access_token=pk.SECRET123"))
check("and says that it did",
      "<token hidden>" in fs.safe_url("https://x/?access_token=pk.SECRET123"))
check("a URL with no token is left alone",
      fs.safe_url("https://basemap.nationalmap.gov/a/b/c")
      == "https://basemap.nationalmap.gov/a/b/c")

# A token in a file, which is the way it is meant to be kept.
import tempfile                                             # noqa: E402

holder = tempfile.mkdtemp()
fs.TOKEN_FILE = os.path.join(holder, ".mapbox_token")
check("no file means no token", fs.read_token_file() is None)
with open(fs.TOKEN_FILE, "w") as handle:
    handle.write("pk.FROM_A_FILE\n")
os.chmod(fs.TOKEN_FILE, 0o644)
check("a file is read, and stripped", fs.read_token_file() == "pk.FROM_A_FILE")
check("and tightened to owner-only (%s)"
      % oct(os.stat(fs.TOKEN_FILE).st_mode & 0o777),
      (os.stat(fs.TOKEN_FILE).st_mode & 0o077) == 0)
with open(fs.TOKEN_FILE, "w") as handle:
    handle.write("\n")
check("an empty file is not a token", fs.read_token_file() is None)
check("the token file is outside the repository, so it cannot be committed",
      not os.path.abspath(
          os.path.expanduser("~/.mapbox_token")).startswith(REPO + os.sep))
import shutil as _sh                                        # noqa: E402
_sh.rmtree(holder, ignore_errors=True)

# The token must not end up in the file that gets copied between machines.
source = open(os.path.join(REPO, "tools", "fetch_satellite.py")).read()
sidecar = source[source.index('"provider": args.provider'):]
sidecar = sidecar[:sidecar.index("}, handle")]
check("the token is never written into the cached image's sidecar",
      "token" not in sidecar)

# --all once fetched twelve worlds, two of which were the same picture:
# flat_test carries hoggar's coordinates as a placeholder.
check("flat_test is left out of --all", "flat_test" in fs.SKIP_IN_ALL)
all_worlds = [env["key"] for env in sim_target.ENVIRONMENTS
              if fs.world_latlon(env["world"])
              and env["world"] not in fs.SKIP_IN_ALL]
check("so --all covers 11 worlds, not 12 (%d)" % len(all_worlds),
      len(all_worlds) == 11 and "flat" not in all_worlds)
check("but the bare world can still be asked for by name",
      sim_target.BY_KEY.get("flat") is not None)

# The credit line is attribution on its own; the token note belongs
# with the provider list, not in the line printed over the imagery.
for name in ("mapbox", "mapbox-outdoors"):
    check("%s credit is attribution only" % name,
          "token" not in fs.PROVIDERS[name]["credit"].lower())

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
