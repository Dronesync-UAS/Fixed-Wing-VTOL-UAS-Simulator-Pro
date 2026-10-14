"""Check the QGC-shaped console at /pro.

    python3 tools/test_pro_console.py

Needs neither PX4 nor Gazebo. Needs playwright for the browser half; the
rest runs without it.

WHY THIS EXISTS
---------------
/pro is meant to be QGroundControl's layout with this project's forty-two
instructor controls inside it. Two things can go wrong silently:

  * a control stops being reachable. The page is assembled from the same
    plugin list as the other console, so a plugin that moves between
    groups can vanish from the page with nothing to say so.
  * the layout drifts from QGC's. Its sizes are not decoration - they are
    QGC's own numbers, taken from its source at v5.1.5 and from measuring
    the running application, so that an instructor glancing between the
    student's QGC and this console is reading the same shapes in the same
    places. A stray CSS change can undo that and still look fine.

THE FIGURES, and where each came from
-------------------------------------
    toolbar height      66 px   measured: rows 0-65 of QGC maximised at
                                1854x1011 are flat window-colour, the map
                                below jumps in variance. ScreenTools.qml:
                                toolbarHeight = defaultFontPixelHeight * 3
    tool strip width    56 px   measured x=6..61. ToolStrip.qml:
                                width = defaultFontPixelWidth * 7
    margin               6 px   measured left edge. FlyViewWidgetLayer.qml:
                                _toolsMargin = defaultFontPixelWidth * 0.75

Those give defaultFontPixelHeight = 22 and defaultFontPixelWidth = 8 on
this screen, and they cross-check: 8 * 0.75 is the 6 that was measured.
"""

import contextlib
import io
import json
import os
import re
import sys
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


# The station, with its hardware-facing imports stubbed - the same harness
# tools/offline_render_check.py sets up, reused rather than repeated.
_src = open(os.path.join(REPO, "tools", "offline_render_check.py")).read()
_cut = _src.index("console = mod.render_console()")
_g = {"__name__": "__main__",
      "__file__": os.path.join(REPO, "tools", "offline_render_check.py")}
with contextlib.redirect_stdout(io.StringIO()):
    exec(compile(_src[:_cut], "offline_render_check.py", "exec"), _g)
station = _g["mod"]
PAGE = station.render_pro()


print("0. the station actually SERVES this page by default")
# This is the check that was missing, and the reason the redesign sat
# unseen for a day. The QGC-shaped console was served only at /pro while
# it was "being judged", but the desktop icon opens http://localhost:PORT
# with no path - so every ordinary start showed the OLD console and the
# report came back as "the GCS still looks the same". A page nothing opens
# is not a redesign.
#
# Driven through the station's REAL Handler rather than a stub server,
# because it was the routing that was wrong, not the page.
def _serve(path):
    """GET path through the station's own Handler. Returns the body."""
    class Fake(station.Handler):
        def __init__(self, request_path):
            self.rfile = io.BytesIO(b"")
            self.wfile = io.BytesIO()
            self.path = request_path
            self.requestline = "GET %s HTTP/1.1" % request_path
            self.client_address = ("127.0.0.1", 0)
            self.request_version = "HTTP/1.1"
            self.command = "GET"
            self.headers = {}

        def log_message(self, *a):
            pass

        def send_response(self, *a, **k):
            pass

        def send_header(self, *a, **k):
            pass

        def end_headers(self):
            pass

    handler = Fake(path)
    handler.do_GET()
    return handler.wfile.getvalue().decode("utf-8", "replace")


# The station only serves a console once it believes PX4 is there; without
# this every path returns the "Connecting to the simulator" holding page.
station.connection_status["connected"] = True
default_page = _serve("/")
check("/ serves the QGC-shaped console, not the old one",
      'id="tools"' in default_page and "--toolbar: 66px" in default_page)
check("/pro still works, so older links and notes do not break",
      'id="tools"' in _serve("/pro"))
check("the previous console is still reachable at /console",
      'id="tools"' not in _serve("/console") and len(_serve("/console")) > 1000)
check("the original panel grid is still reachable at /classic",
      len(_serve("/classic")) > 1000)


print("0b. the instructor's own controls are IN THE DRAWER, not in Settings")
# "Reachable" is the word that let the last fault through: all 42 controls
# were on the page and the test passed, while the failure injections sat in
# a settings pane headed "Not yet placed" and the drawer held eight
# recover buttons. An instructor console whose failures take three clicks
# through a settings window is not an instructor console.
#
# The drawer markup comes before <div id="setback"> in the page, so a
# control's position relative to that marker says which it is in.
_setback = PAGE.index('<div id="setback">')


def _in_drawer(plugin_id):
    at = PAGE.find('id="btn-%s"' % plugin_id)
    return 0 <= at < _setback


# The things an instructor reaches for WHILE a student is flying.
for group, ids in [
        ("failure injection", ["gps_failure", "data_link_loss",
                               "rc_signal_loss", "engine_failure",
                               "motor_failure", "cuas_encounter"]),
        ("conditions", ["conditions", "weather", "time_of_day", "wind_gust"]),
        ("scenario", ["freeze", "reset_scenario", "reset_spawn",
                      "new_session"]),
]:
    adrift = [i for i in ids if not _in_drawer(i)]
    check("every %s control is in the drawer (%s)"
          % (group, adrift or "all of them"), not adrift)

check("nothing is left in a pane headed \"Not yet placed\"",
      "Not yet placed" not in PAGE)


print("1. every instructor control is on the page")
# Reachable means a button with its id, OR a tool-strip entry that sends it.
ids = set(re.findall(r'id="btn-([a-z0-9_]+)"', PAGE))
sends = set(re.findall(r'data-send="([a-z0-9_]+)"', PAGE))
reachable = ids | sends
missing = [p["id"] for p in station.plugins if p["id"] not in reachable]
check("all %d controls are reachable (%s)"
      % (len(station.plugins), missing or "none missing"), not missing)

# Duplicate ids are not cosmetic: getElementById returns the first, so a
# failure light on the second copy never lights.
dupes = [i for i in set(re.findall(r'id="([^"]+)"', PAGE))
         if PAGE.count('id="%s"' % i) > 1]
check("no element id appears twice (%s)" % (dupes or "none"), not dupes)

check("the page carries no unfilled placeholders",
      "__" not in re.sub(r"__[A-Z_]+__", lambda m: "", PAGE) or
      not re.search(r"__[A-Z_]+__", PAGE))


print("2. the layout constants are QGC's own")
for token, what in (("--fw: 8px", "defaultFontPixelWidth"),
                    ("--fh: 22px", "defaultFontPixelHeight"),
                    ("--toolbar: 66px", "toolbarHeight, fh * 3"),
                    ("--strip: 56px", "ToolStrip width, fw * 7"),
                    ("--margin: 6px", "_toolsMargin, fw * 0.75")):
    check("%s is declared (%s)" % (token, what), token in PAGE)

# QGC's dark palette, from QGCPalette.cc's fourth column.
for colour, what in (("#222222", "window"), ("#00e04b", "colorGreen"),
                     ("#f32836", "colorRed"), ("#de8500", "colorOrange")):
    check("the %s colour %s is QGC's" % (what, colour), colour in PAGE)


print("3. the map reads QGroundControl's tile cache")
import map_tiles                                             # noqa: E402

check("the tile hash is QGC's format, provider+x+y+zoom",
      map_tiles.tile_hash(4, 21117, 50828, 17)
      == "00000000040002111700050828017")
# Web Mercator both ways, or the tiles land somewhere other than the track.
lon, lat = map_tiles.tile_to_lonlat(21117, 50828, 17)
check("tile 21117/50828 at zoom 17 is Mountain View (%.3f, %.3f)" % (lat, lon),
      abs(lat - 37.41) < 0.05 and abs(lon + 122.00) < 0.05)
check("and the inverse agrees",
      map_tiles.lonlat_to_tile(lon + 1e-9, lat - 1e-9, 17) == (21117, 50828))
check("Google Hybrid is provider 4, as QGC's provider list orders them",
      map_tiles.PROVIDERS[4] == "Google Hybrid"
      and map_tiles.DEFAULT_PROVIDER == 4)

cache = map_tiles.available()
if cache["present"]:
    print("      cache: %d provider(s), %d tiles"
          % (len(cache["providers"]),
             sum(p["tiles"] for p in cache["providers"])))
else:
    print("      cache: none on this machine - the browser section will "
          "check the fallback instead")


print("4. the console in a real browser")


def browser_checks():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP  playwright is not installed")
        return

    import http.server
    import socketserver
    import preflight

    home = {"lat": -31.49561, "lon": 129.04713}
    posted = []

    class Stub(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _json(self, obj):
            body = json.dumps(obj).encode()
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?")[0]
            query = dict(kv.split("=", 1)
                         for kv in self.path.split("?", 1)[-1].split("&")
                         if "=" in kv) if "?" in self.path else {}
            if path.startswith("/tile/"):
                z, x, y = (int(v) for v in path.strip("/").split("/")[1:4])
                blob = map_tiles.best_tile(z, x, y)
                if blob is None:
                    self.send_response(404)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-type", "image/jpeg")
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)
                return
            if path == "/preflight":
                return self._json(preflight.state())
            if path == "/preflight_tick":
                preflight.tick(query.get("item", ""), query.get("on") == "1")
                return self._json(preflight.state())
            if path == "/preflight_complete":
                return self._json(preflight.complete())
            if path == "/flight_log":
                return self._json({"now": {"recording": False},
                                   "flights": [{"started_utc": "2026-10-14T01:10:00+00:00",
                                                "world": "training_area_nullarbor"}],
                                   "folder": "/tmp/flights"})
            if path == "/flight_path":
                return self._json({"home": home,
                                   "points": [[home["lat"], home["lon"], 50.0]]})
            if path == "/terrain_info":
                return self._json({"available": False,
                                   "world": "training_area_nullarbor"})
            if path == "/livery":
                return self._json({"scheme": "sar", "label": "SAR", "locked": None,
                                   "schemes": [{"id": "sar", "label": "Search and Rescue", "why": ""},
                                               {"id": "grey", "label": "Dark grey", "why": ""}]})
            if path in ("/telemetry", "/health", "/limit_status",
                        "/failure_status", "/chase_view"):
                return self._json({})
            body = PAGE.encode()
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            posted.append(self.path)
            self.rfile.read(int(self.headers.get("Content-Length") or 0))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ok")

    server = socketserver.TCPServer(("127.0.0.1", 0), Stub)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        # QGC's own maximised size on this machine, so the measurements
        # below compare like with like.
        page = browser.new_page(viewport={"width": 1854, "height": 1011})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:%d/" % port)
        page.wait_for_timeout(2500)
        check("the page runs with no script errors (%s)" % (errors or "none"),
              not errors)

        box = page.evaluate("""() => {
            const r = id => { const e = document.getElementById(id);
                if (!e) return null; const b = e.getBoundingClientRect();
                return {x: Math.round(b.left), y: Math.round(b.top),
                        w: Math.round(b.width), h: Math.round(b.height)}; };
            return {top: r('top'), tools: r('tools'), cams: r('cams'),
                    bottomright: r('bottomright'), pip: r('pip')};
        }""")
        check("the toolbar is QGC's 66 px, full width (%s)" % (box["top"],),
              box["top"]["h"] == 66 and box["top"]["w"] == 1854
              and box["top"]["y"] == 0)
        check("the tool strip is 56 px wide at a 6 px margin (%s)"
              % (box["tools"],),
              box["tools"]["w"] == 56 and box["tools"]["x"] == 6)
        check("it starts below the toolbar (%d)" % box["tools"]["y"],
              box["tools"]["y"] == 72)
        check("the camera strip is the same width, against the right edge",
              box["cams"]["w"] == 56
              and box["cams"]["x"] + box["cams"]["w"] == 1854 - 6)
        # FlyViewBottomRightRowLayout.qml puts the telemetry bar and the
        # instrument panel in ONE row anchored bottom-right.
        check("telemetry and the compass share one bottom-right row (%s)"
              % (box["bottomright"],),
              box["bottomright"]["x"] + box["bottomright"]["w"] == 1854 - 6
              and box["bottomright"]["y"] + box["bottomright"]["h"] == 1011 - 6)

        page.click("#open-checklist")
        page.wait_for_timeout(900)
        check("the checklist opens", page.locator("#sheet-checklist").is_visible())
        items = page.locator("#pf-items .pf-item").count()
        check("it lists the station's real checklist (%d items)" % items, items > 0)
        manual = page.locator("#pf-items .pf-item.manual").first
        was = "ok" in (manual.get_attribute("class") or "")
        manual.click()
        page.wait_for_timeout(500)
        now = "ok" in (page.locator("#pf-items .pf-item.manual")
                       .first.get_attribute("class") or "")
        check("a manual item ticks (%s -> %s)" % (was, now), was != now)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Escape closes it", not page.locator("#sheet-checklist").is_visible())

        page.click("#open-log")
        page.wait_for_timeout(900)
        check("the flight log opens and lists a flight",
              page.locator("#sheet-log").is_visible()
              and page.locator("#log-body .logrow").count() == 1)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        posted.clear()
        page.click("#exit-open")
        page.wait_for_timeout(400)
        check("the X asks before exiting", page.locator("#exit-ask").is_visible())
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Escape means no, and sends nothing",
              not page.locator("#exit-ask").is_visible()
              and "/exit" not in posted)
        page.click("#exit-open")
        page.click("#exit-yes")
        page.wait_for_timeout(600)
        check("only Yes sends the shutdown", "/exit" in posted)

        stats = page.evaluate("() => window.gcsTileStats ? window.gcsTileStats() : null")
        check("the map drew tiles (%s)" % (stats,), stats and stats["have"] > 0)
        # NOTHING UPSCALED. fromParent counts tiles drawn by blowing up an
        # ancestor because the zoom asked for was not available. On
        # 14 Oct 2026, reading only QGroundControl's cache, 34 of 54 tiles
        # came that way and the map was reported as poor quality. Tiles are
        # now fetched for the zoom actually wanted, so this must be zero -
        # a non-zero value means the fetch is failing and the map has
        # quietly gone back to looking blurry.
        check("no tile is an upscaled ancestor (fromParent=%s)"
              % stats.get("fromParent", 0), not stats.get("fromParent"))
        check("no tile is missing (missing=%s)" % stats.get("missing"),
              not stats.get("missing"))
        browser.close()
    server.shutdown()


browser_checks()

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
sys.stdout.flush()
# os._exit, not sys.exit: this file imports the station, which loads the
# Gazebo python bindings, and those sometimes abort the process on
# interpreter shutdown AFTER every check has passed. See the same note in
# tools/test_payload.py.
if not fails:
    print("All checks passed.")
    sys.stdout.flush()
os._exit(1 if fails else 0)
