"""Open the rebuilt console in a real browser and check it works.

    python3 tools/test_console_browser.py            # pass/fail
    python3 tools/test_console_browser.py --shot out.png

The offline render check proves the page ASSEMBLES. This proves it RUNS: the
console is mostly JavaScript now, and a single syntax error in it shows up
as a black screen with every control gone - the one failure that cannot be
caught by looking at the HTML.

Serves the real page with stubbed JSON endpoints, loads it in Chromium, and
fails on any console error, any failed request, a hero that laid out with no
size, a view tab that does not swap the main screen, or a tile that cannot
be dragged.

Needs playwright (pip install playwright). Chromium is already on this
machine; do not run "playwright install".
"""
import glob
import http.server
import importlib.util
import json
import os
import socketserver
import sys
import threading
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- the same stubs the offline render check uses, for the same reason -----
sl = types.ModuleType("simulator_link")
sl.telemetry = {
    "armed": False, "mode": "Hold", "altitude_m": 12.5, "altitude_amsl_m": 1200.0,
    "groundspeed_ms": 3.4, "battery_pct": 87, "heading_deg": 93, "satellites": 10,
    "roll_deg": 6.0, "pitch_deg": -2.0, "yaw_deg": 93.0, "airspeed_ms": 4.1,
    "range_from_home_m": 164.0, "arm_ready": True, "arm_state": "Ready to arm",
    "arm_blocker": None,
}
sl.connection_status = {"connected": True, "message": "Connected."}


class _M:
    class mav:
        @staticmethod
        def command_long_send(*a, **k): pass
    target_system = 1
    target_component = 1


sl.master = _M()
for name in ("reset_flight_state", "log_instructor_action", "mark_failure_injected",
             "mark_failure_cleared", "start_background_script", "stop_background_script"):
    setattr(sl, name, lambda *a, **k: None)
sl.running_processes = {}
sl.RESPONSE_TIMEOUT_S = 45
sl.flight_path = [(23.5, 6.5, 100.0, 1.0), (23.5012, 6.5009, 120.0, 2.0)]
sl.home_latlon = {"lat": 23.5, "lon": 6.5}
sl.link_health = {"last_msg_t": None}
sl.command_acks = {}
sl.MAV_RESULT_NAMES = {0: "accepted"}
sl.send_command_and_wait = lambda *a, **k: (0, "accepted")
sl.set_mode = lambda m, s=0, name=None: "ok"
sys.modules["simulator_link"] = sl

el = types.ModuleType("event_logger")
el.log_event = lambda *a, **k: None
el.read_events = lambda: []
sys.modules["event_logger"] = el

vf = types.ModuleType("video_feed")
vf.start_video_capture = lambda: None
vf.mjpeg_generator = lambda: iter(())
vf.camera_fps = lambda: 15.0


class _Feed:
    def mjpeg_generator(self): return iter(())
    def fps(self): return 15.0
    def current_topic(self): return None
    def resubscribe(self): return None
    def start(self): return None


vf.FEEDS = {"nose": _Feed(), "chase": _Feed()}
vf.nose = vf.FEEDS["nose"]
vf.chase = vf.FEEDS["chase"]
sys.modules["video_feed"] = vf

sys.path.insert(0, REPO)
spec = importlib.util.spec_from_file_location(
    "instructor_station", os.path.join(REPO, "instructor_station.py"))
station = importlib.util.module_from_spec(spec)
spec.loader.exec_module(station)

# Render against a throwaway layout file. Reading the real one would make
# this test depend on however the last person arranged their console, and
# would let the test's own saves overwrite it - exactly what happened the
# first time it was run.
import tempfile
station.LAYOUT_FILE = os.path.join(tempfile.mkdtemp(), "gcs_layout.json")

PAGE = station.render_console()

# A 1x1 PNG, so the <img> tags resolve instead of reporting a failed request.
PNG = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db4" "0000000049454e44ae426082")

STUBS = {
    "/telemetry": sl.telemetry,
    "/limit_status": {"level": "ok", "items": []},
    "/health": {"telemetry_age_s": 0.4, "camera_fps": 15.0},
    "/failure_status": {"gps_failure": True, "motor_failure": False},
    "/flight_path": {"home": sl.home_latlon,
                     "points": [[23.5, 6.5, 100.0], [23.5012, 6.5009, 120.0]]},
    "/terrain_info": {"available": False},
    "/connection_status": sl.connection_status,
}


class Stub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
        elif path in STUBS:
            body, ctype = json.dumps(STUBS[path]).encode(), "application/json"
        elif path in ("/video_feed", "/chase_feed", "/terrain.png", "/favicon.ico"):
            body, ctype = PNG, "image/png"
        else:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *a):
        pass


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed - skipping the browser check.")
        print("  pip install playwright     (Chromium is already on this machine)")
        return 0

    server = socketserver.TCPServer(("127.0.0.1", 0), Stub)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    fails = []

    def check(tag, cond):
        print(("  PASS  " if cond else "  FAIL  ") + tag)
        if not cond:
            fails.append(tag)

    # This machine ships Chromium under /opt/pw-browsers, and pip's
    # playwright may be a newer release expecting a build number that is not
    # there. Point it at what exists rather than downloading another copy.
    chrome = None
    for base in sorted(glob.glob("/opt/pw-browsers/chromium-*"), reverse=True):
        candidate = os.path.join(base, "chrome-linux", "chrome")
        if os.path.isfile(candidate):
            chrome = candidate
            break

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome) if chrome else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors, failed = [], []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("requestfailed", lambda r: failed.append(r.url))
        page.goto("http://127.0.0.1:%d/" % port)
        page.wait_for_timeout(1800)

        print("1. the page runs at all")
        check("no JavaScript errors: %s" % (errors[:2] or "none"), not errors)
        check("no failed requests: %s" % (failed[:2] or "none"), not failed)

        print("2. it laid out")
        hero = page.locator("#hero").bounding_box()
        check("hero has real size (%s)" % hero, hero and hero["width"] > 600 and hero["height"] > 300)
        for side in ("left", "right"):
            box = page.locator("#tile-" + side).bounding_box()
            check("%s tile placed on screen (%s)" % (side, box),
                  box and box["width"] > 100 and 0 <= box["x"] < 1600)
        check("gyro is drawn", page.locator("#gyro").is_visible())

        print("3. the three views are each in exactly one place")
        for view in ("chase", "nose", "map"):
            check("#view-%s present once" % view, page.locator("#view-" + view).count() == 1)
        check("the hero holds the saved view",
              page.locator("#hero #view-chase").count() == 1)

        print("4. the main screen swaps")
        page.click('#viewtabs button[data-view="map"]')
        page.wait_for_timeout(300)
        check("map moved into the hero", page.locator("#hero #view-map").count() == 1)
        check("chase moved out to a tile", page.locator(".tile #view-chase").count() == 1)
        check("the tab shows which view is live",
              "on" in (page.get_attribute('#viewtabs button[data-view="map"]', "class") or ""))

        print("4b. the map fills the hero")
        # Guards the 420px bug: the classic stylesheet pins #flightpath to a
        # fixed height with an id selector, which left the map drawing a
        # quarter of the hero and black everywhere else.
        box = page.locator("#hero #flightpath").bounding_box()
        hero = page.locator("#hero").bounding_box()
        check("canvas is as tall as the hero (%s vs %s)"
              % (round(box["height"]), round(hero["height"])),
              box["height"] > hero["height"] - 8)
        check("and as wide (%s vs %s)" % (round(box["width"]), round(hero["width"])),
              box["width"] > hero["width"] - 8)

        print("4b2. the canvases are sized for the display, not just CSS")
        # Guards the soft map and overlay: a canvas sized in CSS pixels is
        # drawn one device pixel per CSS pixel and scaled up by the screen.
        sizing = page.evaluate(
            "() => { const c = document.getElementById('flightpath');"
            " return {css: c.cssW, client: c.clientWidth, backing: c.width,"
            " dpr: Math.min(window.devicePixelRatio || 1, 2)}; }")
        check("fit() recorded the CSS size (%s)" % sizing,
              sizing["css"] == sizing["client"] and sizing["css"] > 0)
        check("backing store matches CSS x devicePixelRatio",
              abs(sizing["backing"] - sizing["css"] * sizing["dpr"]) <= 1)

        print("4c. rail sections collapse")
        head = page.locator("#rail-right .group .head").first
        group = page.locator("#rail-right .group").first
        check("open to start", "shut" not in (group.get_attribute("class") or ""))
        head.click()
        page.wait_for_timeout(200)
        check("shut after a click", "shut" in (group.get_attribute("class") or ""))
        check("its controls are hidden", not group.locator(".items").is_visible())
        head.click()
        page.wait_for_timeout(200)
        check("open again", "shut" not in (group.get_attribute("class") or ""))

        print("4d. rail labels fit the rail")
        rail = page.locator("#rail-left").bounding_box()
        widest = page.evaluate(
            "() => Math.max(...[...document.querySelectorAll('#rail-left button')]"
            ".map(b => b.scrollWidth))")
        check("no button text overflows (%s px in a %s px rail)"
              % (widest, round(rail["width"])), widest <= rail["width"])

        print("5. clicking a tile swaps it in")
        page.click("#tile-left .body")
        page.wait_for_timeout(300)
        check("a different view is now the hero",
              page.locator("#hero #view-map").count() == 0)

        print("6. the layout switch changes the chrome")
        before = page.locator("#hero").bounding_box()
        page.click('#layouttabs button[data-layout="station"]')
        page.wait_for_timeout(300)
        after = page.locator("#hero").bounding_box()
        check("Station insets the picture (%s -> %s)" % (before["x"], after["x"]),
              after["x"] > before["x"])

        print("7. a tile can be dragged")
        bar = page.locator("#tile-right .bar")
        start = page.locator("#tile-right").bounding_box()
        box = bar.bounding_box()
        page.mouse.move(box["x"] + 40, box["y"] + 10)
        page.mouse.down()
        page.mouse.move(box["x"] - 160, box["y"] - 90, steps=8)
        page.mouse.up()
        page.wait_for_timeout(200)
        moved = page.locator("#tile-right").bounding_box()
        check("it moved (%s -> %s)" % (round(start["x"]), round(moved["x"])),
              abs(moved["x"] - start["x"]) > 80)

        print("8. telemetry reached the readouts")
        check("altitude shown", "12.5" in page.inner_text("#p-alt"))
        check("arming state shown", "Ready" in page.inner_text("#t-armcheck"))
        check("a lit failure shows its light",
              "on" in (page.get_attribute("#dot-gps_failure", "class") or ""))

        if "--shot" in sys.argv:
            out = sys.argv[sys.argv.index("--shot") + 1]
            page.screenshot(path=out)
            print("\n  screenshot: " + out)
        browser.close()

    server.shutdown()
    print()
    print("FAILED: %s" % fails if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
