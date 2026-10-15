"""Check the two operating envelopes, offline.

    python3 tools/test_range_profile.py

Nothing here talks to PX4 or Gazebo. What is checked is what can be got
wrong without them:

  * the CAA envelope is what a station that has never been set gets, and
    a corrupt saved file does not turn into the 100 km one;
  * only the range differs between the two, so nobody raises the height
    limit by accident;
  * the switch is written down - the flight log carries the envelope's
    NAME, not just its numbers;
  * the plugin actually updates the station's own LIMITS dict, which is
    what every warning on the page reads;
  * the imagery fetcher drops zoom as the extent grows instead of asking
    for twenty thousand tiles;
  * every world that can have its visible ground widened has been, and
    the widened files still parse.
"""
import glob
import json
import os
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

# --- stub event_logger so this check never writes to the real compliance CSV ---
# Added 16 Oct 2026: range_profile logs its envelope changes through the real
# event_logger, so every run of this test wrote three range_profile rows into
# ~/uas_sim_logs/instructor_events.csv, the CAP722B assessment record - 38
# such sessions from 12 Oct 2026 onwards, most of them via verify_install.py.
import types                                                # noqa: E402
el = types.ModuleType("event_logger")
el.log_event = lambda *a, **k: None
el.read_events = lambda: []
el.SESSION_ID = "TEST"
sys.modules["event_logger"] = el

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


import range_profile as rp                                  # noqa: E402

print("The two envelopes")

# A station that has never been set, and one whose saved file is rubbish,
# must both come up on the envelope a student is allowed to fly.
holder = tempfile.mkdtemp()
rp.STATE_FILE = os.path.join(holder, "range_profile.json")
check("a station never set comes up on the CAA envelope",
      rp.restore() is rp.PROFILES["caa"])
with open(rp.STATE_FILE, "w") as handle:
    handle.write("{ not json")
check("a corrupt saved file falls back to CAA", rp.restore_limits()["range_m"] == 500.0)
with open(rp.STATE_FILE, "w") as handle:
    json.dump({"profile": "something_else"}, handle)
check("an unknown saved name falls back to CAA", rp.restore()["range_m"] == 500.0)

check("CAA is 500 m", rp.PROFILES["caa"]["range_m"] == 500.0)
check("extended is 100 km", rp.PROFILES["extended"]["range_m"] == 100000.0)
check("only the range differs between them",
      rp.PROFILES["caa"]["ceiling_m"] == rp.PROFILES["extended"]["ceiling_m"]
      and (rp.PROFILES["caa"]["groundspeed_ms"]
           == rp.PROFILES["extended"]["groundspeed_ms"]))
check("the ceiling stays at 120 m on both",
      rp.PROFILES["caa"]["ceiling_m"] == 120.0)
check("CAA is marked as the one a student may fly",
      rp.PROFILES["caa"]["student_safe"] is True
      and rp.PROFILES["extended"]["student_safe"] is False)

ok, message = rp.choose("extended")
check("switching works", ok and rp.active_key() == "extended")
check("and reports which envelope, by name", "100 km" in message)
check("and says it is instructor-only", "nstructor" in message)
check("the limits follow", rp.limits()["range_m"] == 100000.0)
check("it is remembered", json.load(open(rp.STATE_FILE))["profile"] == "extended")
ok, message = rp.choose("nonsense")
check("a bad name changes nothing",
      not ok and rp.active_key() == "extended")

# The flight log has to be able to say, later, which envelope a flight
# was flown against. Numbers alone cannot.
described = rp.describe()
check("the record carries the envelope's name",
      described["profile"] == "extended" and "100 km" in described["label"])
check("and whether it was inside the student limit",
      described["student_safe"] is False)

print("\nThe control on the page")

# The plugin updates the station's LIMITS dict in place - that one dict
# is what every warning, the altitude tape and the flight log read. A
# stand-in station is enough to prove it reaches the right object.
import types                                                # noqa: E402

station = types.ModuleType("instructor_station")
station.LIMITS = {"ceiling_m": 120.0, "range_m": 500.0, "groundspeed_ms": 30.0,
                  "battery_warn_pct": 20}
sys.modules["instructor_station"] = station

# Loaded by path, the way plugin_loader does it, so the test exercises
# the same thing the station will.
import importlib.util                                       # noqa: E402

spec = importlib.util.spec_from_file_location(
    "operating_envelope",
    os.path.join(REPO, "plugins", "operating_envelope.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

check("the plugin is not called range_profile as well",
      not os.path.exists(os.path.join(REPO, "plugins", "range_profile.py")))
check("its id matches its filename",
      plugin.PLUGIN["id"] == "operating_envelope")

check("the control is in Simulation Control, not on a flying rail",
      plugin.PLUGIN["category"] == "Simulation Control")
check("it offers exactly the two envelopes",
      [o["value"] for o in plugin.PLUGIN["inputs"][0]["options"]]
      == ["caa", "extended"])

said = plugin.set_profile("extended")
check("choosing extended updates the station's own limits",
      station.LIMITS["range_m"] == 100000.0)
check("and leaves the ceiling alone", station.LIMITS["ceiling_m"] == 120.0)
check("and leaves other limits untouched",
      station.LIMITS["battery_warn_pct"] == 20)
check("and says what changed", "100 km" in said)
plugin.set_profile("caa")
check("choosing CAA puts it back", station.LIMITS["range_m"] == 500.0)
check("a bad name is refused without touching the limits",
      "not one of" in plugin.set_profile("nope")
      and station.LIMITS["range_m"] == 500.0)

print("\nImagery wide enough to fly across")

import math                                                 # noqa: E402
import fetch_satellite as fs                                # noqa: E402


def plan(extent_km, provider_name, lat=52.97, lon=0.81):
    """The same zoom-and-tile arithmetic fetch_one does, with nothing
    downloaded. Kept in step with it by the checks below."""
    provider = fs.PROVIDERS[provider_name]
    tile_px = provider.get("tile_px", 256)
    zoom = fs.ZOOM + provider.get("zoom_offset", 0)
    half = extent_km * 1000.0 / 2.0
    d_lat = half / 110540.0
    d_lon = half / (111320.0 * math.cos(math.radians(lat)))
    while True:
        x0, y0 = fs.lonlat_to_tile(lon - d_lon, lat + d_lat, zoom)
        x1, y1 = fs.lonlat_to_tile(lon + d_lon, lat - d_lat, zoom)
        columns = math.floor(x1) - math.floor(x0) + 1
        rows = math.floor(y1) - math.floor(y0) + 1
        if columns * rows <= fs.MAX_TILES or zoom <= fs.ZOOM_FLOOR:
            break
        zoom -= 1
    mpp = (156543.03392 * math.cos(math.radians(lat))
           / (2.0 ** zoom) * (256.0 / tile_px))
    return zoom, columns * rows, mpp


check("the default extent is still the 4 km one that was fetched before",
      fs.DEFAULT_EXTENT_KM == 4.0)
zoom4, tiles4, _ = plan(4, "mapbox")
check("4 km on Mapbox is unchanged at zoom 15, 36 tiles (%d, %d)"
      % (zoom4, tiles4), (zoom4, tiles4) == (15, 36))
zoom100, tiles100, mpp100 = plan(100, "mapbox")
check("100 km drops to zoom %d rather than asking for thousands of tiles"
      % zoom100, zoom100 < zoom4)
check("and %d tiles is inside the budget of %d" % (tiles100, fs.MAX_TILES),
      tiles100 <= fs.MAX_TILES)
check("at about %.0f m per pixel, which is coarse and says so" % mpp100,
      10 < mpp100 < 60)
for km in (4, 10, 25, 50, 100, 200):
    for provider in ("mapbox", "usgs", "esri"):
        _, tiles, _ = plan(km, provider)
        if tiles > fs.MAX_TILES:
            check("%d km on %s stays inside the tile budget" % (km, provider),
                  False)
check("every extent and provider stays inside the tile budget", True)

print("\nGround you can see at 100 km")

import far_ground_apply as fg                               # noqa: E402

planes, heightmaps, narrow = [], [], []
for path in fg.worlds():
    text = open(path).read()
    kind = fg.ground_kind(text)
    if kind == "heightmap":
        heightmaps.append(os.path.basename(path))
        continue
    planes.append(os.path.basename(path))
    size = fg.current_size(text)
    if not size or size[0] < 200000:
        narrow.append((os.path.basename(path), size))
    # Exactly one plane may match, or the pattern is hitting something
    # that is not the ground.
    # Counts the solid box too: --solid turns the ground plane into one,
    # and this check is here to catch the pattern matching something that
    # is not the ground - not to insist on a particular primitive.
    if fg.ground_visual_count(text) != 1:
        check("%s has exactly one ground plane" % os.path.basename(path), False)

check("%d worlds stand on a plane and %d on a heightmap"
      % (len(planes), len(heightmaps)), len(planes) > 0 and len(heightmaps) > 0)
check("every plane world has been widened past 200 km (%s)"
      % (", ".join(n for n, _ in narrow) or "all done"), not narrow)
check("the pattern matches one plane per world, not several", True)

# The collision used to stop 50 km from home. If it still does, a long
# flight lands on nothing.
import re                                                   # noqa: E402

for name in planes:
    text = open(os.path.join(REPO, "sim", "worlds", name)).read()
    found = fg.GROUND_COLLISION.search(text)
    if not found or float(found.group(2)) < 200000:
        check("%s collision reaches past 100 km from home" % name, False)
check("every plane world's collision reaches past 100 km from home", True)

for path in fg.worlds():
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        check("%s still parses (%s)" % (os.path.basename(path), exc), False)
check("every world still parses after the widening", True)

# The heightmap worlds were deliberately left alone. Saying so here is
# what stops someone "fixing" them later without reading why.
check("heightmap worlds were left alone on purpose (%s)"
      % ", ".join(sorted(heightmaps)), len(heightmaps) == 5)

import shutil                                               # noqa: E402

shutil.rmtree(holder, ignore_errors=True)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
