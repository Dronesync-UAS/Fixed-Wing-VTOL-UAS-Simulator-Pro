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
sl.status_log = []
sl.home_amsl = lambda: 1200.0
sl.failure_injection_blocked = lambda: None
sl.read_param = lambda *a, **k: 1.0
sl.FAILURE_UNIT_SYSTEM_MOTOR = 101
sl.FAILURE_UNIT_SYSTEM_SERVO = 102
sl.FAILURE_UNIT_SYSTEM_RC_SIGNAL = 104
sl.FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 105
sl.FAILURE_TYPE_OK = 0
sl.FAILURE_TYPE_OFF = 1
sl.MAV_CMD_INJECT_FAILURE = 420
sl.offset_latlon = lambda lat, lon, bearing, dist: (lat, lon)
sl.say_step = lambda *a, **k: None
sl.cancel_sequence = lambda: None
sl.sequence_running = lambda: False
sl.start_sequence = lambda *a, **k: True
sl.wait_until = lambda *a, **k: True
sl.VTOL_STATES = {3: "Hover", 4: "Fixed wing"}
sl.status_since = lambda *a, **k: []
sl.wait_for_armed = lambda *a, **k: True
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
    def fov_rad(self): return 1.5708
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
        gyro = page.locator("#gyro").bounding_box()
        check("gyro is instrument-sized (%s px)" % round(gyro["width"]),
              gyro["width"] >= 180)
        band = page.evaluate(
            "() => document.getElementById('bottom').getBoundingClientRect().top")
        check("gyro straddles the band's top edge (centre %s vs edge %s)"
              % (round(gyro["y"] + gyro["height"] / 2), round(band)),
              abs((gyro["y"] + gyro["height"] / 2) - band) <= 3)
        clash = page.evaluate(
            "() => { const g = document.getElementById('gyro').getBoundingClientRect();"
            " let worst = 0;"
            " document.querySelectorAll('#cap .val, #cap .lim, #cap .pill').forEach(e => {"
            "   const r = e.getBoundingClientRect();"
            "   if (r.bottom > g.top && r.top < g.bottom)"
            "     worst = Math.max(worst, Math.min(r.right, g.right) - Math.max(r.left, g.left));"
            " }); return Math.round(worst); }")
        check("gyro does not sit on the CAP722B row (%s px of overlap)" % clash,
              clash <= 0)
        check("gyro paints pixels, not an empty canvas",
              page.evaluate(
                  "() => { const c = document.getElementById('gyro');"
                  " const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                  " let n = 0; for (let i = 3; i < d.length; i += 4) { if (d[i]) n++; }"
                  " return n > c.width * c.height * 0.5; }"))

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

        print("4b1. the map zooms, and never shows a bare patch of ground")
        # A parked aircraft has a two-metre track. Fitting to that gave a 50m
        # square of empty playa with home and the aircraft on top of each
        # other - "aircraft icon and home point too far", as it was reported.
        span = page.inner_text("#fp-range")
        check("fitted view is at least 300 m across (%s)" % span,
              ("m" in span and float(span.split()[0]) >= 300) or "km" in span)
        page.click('#hero [data-mapzoom="in"]')
        page.wait_for_timeout(300)
        closer = page.inner_text("#fp-range")
        check("zoom in shows less ground (%s -> %s)" % (span, closer),
              float(closer.split()[0]) < float(span.split()[0]))
        page.click('#hero [data-mapzoom="fit"]')
        page.wait_for_timeout(300)
        check("Fit goes back (%s)" % page.inner_text("#fp-range"),
              page.inner_text("#fp-range") == span)
        check("the map drew home and the aircraft",
              page.evaluate(
                  "() => { const c = document.getElementById('flightpath');"
                  " const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                  " let n = 0; for (let i = 3; i < d.length; i += 4) { if (d[i] > 40) n++; }"
                  " return n > 500; }"))

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

        print("4b3. the attitude overlay sits over the nose camera, not under it")
        # The overlay was drawn every frame and never seen: the camera image
        # is z-index 1 and the canvas had none of its own, so it painted
        # underneath. "Where is the gyroscope in nose view" was this.
        page.click('#viewtabs button[data-view="nose"]')
        page.wait_for_timeout(300)
        order = page.evaluate(
            "() => { const v = document.querySelector('#hero #view-nose');"
            " const z = e => parseInt(getComputedStyle(e).zIndex, 10) || 0;"
            " return {hud: z(v.querySelector('canvas.hud')), img: z(v.querySelector('img'))}; }")
        check("overlay stacks above the picture (%s)" % order, order["hud"] > order["img"])
        check("overlay has drawn something",
              page.evaluate(
                  "() => { const c = document.getElementById('hud');"
                  " const d = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;"
                  " let n = 0; for (let i = 3; i < d.length; i += 4) { if (d[i] > 40) n++; }"
                  " return n > 2000; }"))
        print("4b4. the gauge keeps clear of the controls and the top bar")
        # Pilot floats the two control columns over the picture, and the
        # main screen runs behind the top bar. The tapes and the corner
        # figures were printing underneath both. The horizon and the pitch
        # ladder still run the full width - they have to line up with the
        # real horizon - so what is checked is the margin the gauge works
        # out for everything else.
        page.click('#layouttabs button[data-layout="pilot"]')
        page.wait_for_timeout(500)
        safe = page.evaluate("() => window.gcsHudSafe('#hero canvas.hud')")
        for sel, side in (("#rail-left", "left"), ("#rail-right", "right"),
                          ("#topbar", "top")):
            r = page.locator(sel).bounding_box()
            if side == "left":
                ok, got, want = safe["left"] >= r["x"] + r["width"], safe["left"], r["x"] + r["width"]
            elif side == "right":
                ok, got, want = safe["right"] <= r["x"], safe["right"], r["x"]
            else:
                ok, got, want = safe["top"] >= r["y"] + r["height"], safe["top"], r["y"] + r["height"]
            check("gauge %s margin clears %s (%s vs %s)"
                  % (side, sel, round(got), round(want)), ok)

        page.click('#viewtabs button[data-view="map"]')
        page.wait_for_timeout(250)

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

        print("7b. a rail undocks, moves, resizes and turns on its side")
        rail = page.locator("#rail-right")
        before = rail.bounding_box()
        check("docked to start", "floating" not in (rail.get_attribute("class") or ""))
        # The handle is on screen while docked - that is the whole point of
        # it. A docked rail with no visible handle reads as fixed furniture,
        # which is exactly how this looked before.
        handle = page.locator("#rail-right .railbar")
        check("handle visible while docked", handle.is_visible())
        hb = handle.bounding_box()
        check("handle inside the rail (%s wide in %s)"
              % (round(hb["width"]), round(before["width"])),
              hb["width"] > 40 and hb["y"] >= before["y"] - 1)
        # Grab the handle, which is how a docked rail comes off the wall.
        page.mouse.move(hb["x"] + hb["width"] / 2 - 14, hb["y"] + hb["height"] / 2)
        page.mouse.down()
        page.mouse.move(before["x"] - 300, before["y"] + 220, steps=10)
        page.mouse.up()
        page.wait_for_timeout(250)
        after = rail.bounding_box()
        check("now floating", "floating" in (rail.get_attribute("class") or ""))
        check("and moved (%s -> %s)" % (round(before["x"]), round(after["x"])),
              abs(after["x"] - before["x"]) > 100)

        grip = page.locator("#rail-right .railgrip")
        box = grip.bounding_box()
        page.mouse.move(box["x"] + 8, box["y"] + 8)
        page.mouse.down()
        page.mouse.move(box["x"] + 130, box["y"] + 40, steps=8)
        page.mouse.up()
        page.wait_for_timeout(250)
        wider = rail.bounding_box()
        check("and resized (%s -> %s wide)"
              % (round(after["width"]), round(wider["width"])),
              wider["width"] > after["width"] + 50)

        page.click("#rail-right .turn")
        page.wait_for_timeout(250)
        check("turned on its side",
              "horizontal" in (page.get_attribute("#rail-right", "class") or ""))
        turned = rail.bounding_box()
        check("long side swapped (%sx%s -> %sx%s)"
              % (round(wider["width"]), round(wider["height"]),
                 round(turned["width"]), round(turned["height"])),
              turned["width"] > turned["height"])
        check("its buttons still reachable",
              page.locator("#rail-right #btn-gps_failure").count() == 1)

        print("7c. the picture is not inset for a panel that left the edge")
        page.click('#layouttabs button[data-layout="station"]')
        page.wait_for_timeout(250)
        hero = page.locator("#hero").bounding_box()
        check("no dead strip on the right (%s + %s vs %s)"
              % (round(hero["x"]), round(hero["width"]), 1600),
              hero["x"] + hero["width"] > 1590)

        page.click("#resettiles")
        page.wait_for_timeout(250)
        check("Reset panels re-docks it",
              "floating" not in (page.get_attribute("#rail-right", "class") or ""))

        print("8. telemetry reached the readouts")
        check("altitude shown", "12.5" in page.inner_text("#p-alt"))
        check("arming state shown", "Ready" in page.inner_text("#t-armcheck"))
        check("a lit failure shows its light",
              "on" in (page.get_attribute("#dot-gps_failure", "class") or ""))

        if "--shot" in sys.argv:
            out = sys.argv[sys.argv.index("--shot") + 1]
            # --nose puts the attitude overlay on screen over a stand-in for
            # bright desert, which is the only way to judge whether it reads.
            if "--layout" in sys.argv:
                page.click('#layouttabs button[data-layout="%s"]'
                           % sys.argv[sys.argv.index("--layout") + 1])
                page.wait_for_timeout(400)
            if "--view" in sys.argv:
                page.click('#viewtabs button[data-view="%s"]'
                           % sys.argv[sys.argv.index("--view") + 1])
                page.wait_for_timeout(1400)
            if "--nose" in sys.argv:
                page.click('#viewtabs button[data-view="nose"]')
                page.evaluate(
                    "() => { const v = document.querySelector('#hero #view-nose');"
                    " v.style.background = 'linear-gradient(#9ec9ea 0 45%, #cdab77 45% 100%)';"
                    " v.querySelector('.nosignal').style.display = 'none'; }")
                page.wait_for_timeout(400)
            page.screenshot(path=out)
            print("\n  screenshot: " + out)
        browser.close()

    server.shutdown()
    print()
    print("FAILED: %s" % fails if fails else "all checks passed")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
