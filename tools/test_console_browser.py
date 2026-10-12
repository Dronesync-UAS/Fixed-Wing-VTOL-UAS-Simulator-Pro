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
sl.on_armed_change = lambda cb: None
sl.on_failure = lambda cb: None
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
al = types.ModuleType("aircraft_lights")
al.set_armed = lambda *a, **k: None
al.set_on = lambda on: None
al.status = lambda: {"on": False, "armed": False, "problem": None}
al.NAVIGATION = ["nav_port", "nav_starboard", "nav_tail"]
al.STROBES = ["strobe_top", "strobe_belly"]
al.BEACON = ["beacon_top"]
al.ALL = al.NAVIGATION + al.STROBES + al.BEACON
sys.modules["aircraft_lights"] = al

el = types.ModuleType("event_logger")
el.log_event = lambda *a, **k: None
el.read_events = lambda: []
el.SESSION_ID = "TEST"
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
    "/payload_status": {"pan_deg": 0.0, "tilt_deg": 30.0, "zoom": 1.0,
                        "mode": "manual", "target": None, "range_m": None,
                        "range_source": None, "range_age_s": None,
                        "range_stale": False, "fov_deg": 60.2,
                        "pan_limit_deg": 180.0, "tilt_up_deg": -30.0,
                        "tilt_down_deg": 90.0, "zoom_max": 12.0,
                        "problem": None, "stabilised": False, "fps": 0.0,
                        "view_mode": "normal", "camera_live": False,
                        "recording": {"on": False, "frames": 0, "seconds": 0}},
    "/chase_view": {"az_deg": 0.0, "el_deg": 13.8, "preset": "behind"},
    "/flight_log": {"now": {"recording": False, "last": None},
                    "flights": [], "folder": "/tmp/flights"},
    "/connection_status": sl.connection_status,
}

# The checklist is served by the real module, not a canned answer: its job
# is to read the aircraft honestly, and a stub would test the panel against
# a fiction.
import preflight  # noqa: E402


class Stub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/":
            body, ctype = PAGE.encode("utf-8"), "text/html; charset=utf-8"
        elif path == "/preflight":
            body, ctype = json.dumps(preflight.state()).encode(), "application/json"
        elif path == "/preflight_tick":
            query = dict(p.split("=", 1) for p in
                         self.path.split("?", 1)[-1].split("&") if "=" in p)
            preflight.tick(query.get("item", ""), query.get("on") == "1")
            body, ctype = json.dumps(preflight.state()).encode(), "application/json"
        elif path == "/preflight_complete":
            body, ctype = json.dumps(preflight.complete()).encode(), "application/json"
        elif path in STUBS:
            body, ctype = json.dumps(STUBS[path]).encode(), "application/json"
        elif path in ("/video_feed", "/chase_feed", "/payload_feed",
                      "/terrain.png", "/favicon.ico"):
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

    def set_layout(name):
        """Switch layout without caring whether the settings panel is open."""
        page.evaluate(
            "n => document.querySelector('#layouttabs button[data-layout=\"'"
            " + n + '\"]').click()", name)
        page.wait_for_timeout(420)

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

        print("1b. the top bar fits on one line")
        # It grew a window button at a time until it wrapped, and the part
        # that fell off was the aircraft's own state at the right-hand end.
        bar = page.evaluate(
            "() => { const b = document.getElementById('topbar');"
            " return {scroll: b.scrollWidth, client: b.clientWidth,"
            "  height: b.getBoundingClientRect().height}; }")
        check("nothing is clipped off the ends (%s wide in %s)"
              % (bar["scroll"], bar["client"]), bar["scroll"] <= bar["client"] + 1)
        # scrollWidth alone is not enough, and this is how the last one got
        # through: the middle group can shrink below its own content while
        # the bar clips rather than scrolls, so the controls inside spill
        # sideways over the aircraft's state without the bar ever growing.
        SPILL_PROBE = """() => {
              const tools = document.querySelector('#topbar .tools');
              const icons = document.querySelector('#topbar .icons');
              if (!tools || !icons) { return 'missing'; }
              const i = icons.getBoundingClientRect();
              const over = [...tools.children].map(e => e.getBoundingClientRect())
                .filter(r => r.right > i.left + 1);
              return over.length ? Math.round(over[0].right - i.left) : 0;
            }"""
        spill = page.evaluate(SPILL_PROBE)
        check("and nothing spills over the aircraft's state (%s)"
              % (("%s px" % spill) if spill else "clear"), spill == 0)
        # Squeezed to a narrow laptop, where it has to give somewhere.
        page.set_viewport_size({"width": 1100, "height": 800})
        page.wait_for_timeout(400)
        tight = page.evaluate(SPILL_PROBE)
        check("still clear at 1100 wide (%s)"
              % (("%s px" % tight) if tight else "clear"), tight == 0)
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(400)
        check("and it is still one row high (%s px)" % round(bar["height"]),
              bar["height"] <= 56)
        sizes = page.evaluate(
            "() => [...document.querySelectorAll('#topbar button, #topbar"
            " .badge, #topbar #t-mode')]"
            " .map(e => getComputedStyle(e).fontSize)")
        check("every label is the same size (%s)" % sorted(set(sizes)),
              len(set(sizes)) == 1)
        icons = page.evaluate(
            "() => [...document.querySelectorAll('#topbar .icons svg')]"
            " .map(e => Math.round(e.getBoundingClientRect().width))")
        check("every icon is the same size (%s)" % sorted(set(icons)),
              len(set(icons)) == 1 and icons[0] >= 18)

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
        set_layout("pilot")
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

        print("4b5. the tapes clear the corner views")
        # The corner views are 400px wide now, and at that size the left
        # one reached straight across the speed tape.
        page.click('#viewtabs button[data-view="nose"]')
        page.wait_for_timeout(500)
        tapes = page.evaluate("() => window.gcsTapes('#hero canvas.hud')")
        boxes = page.evaluate(
            """() => { const c = document.querySelector('#hero canvas.hud');
               const b = c.getBoundingClientRect();
               return [...document.querySelectorAll('.tile')].map(t => {
                 const r = t.getBoundingClientRect();
                 return {left: r.left - b.left, right: r.right - b.left,
                         top: r.top - b.top, bottom: r.bottom - b.top}; }); }""")
        check("the gauge reported where it put them", tapes is not None)
        if tapes:
            for name in ("speed", "alt"):
                tape = tapes[name]
                clash = [t for t in boxes
                         if tape["right"] > t["left"] and tape["left"] < t["right"]
                         and tape["bottom"] > t["top"] and tape["top"] < t["bottom"]]
                check("the %s tape clears both corner views (%s)"
                      % (name, "clear" if not clash else clash), not clash)
            check("and they are still either side of the middle (%s | %s)"
                  % (round(tapes["speed"]["right"]), round(tapes["alt"]["left"])),
                  tapes["speed"]["right"] < tapes["alt"]["left"])
        page.click('#viewtabs button[data-view="map"]')
        page.wait_for_timeout(300)

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

        print("4e. no control sits on top of another")
        # Reported as "some buttons overlap others". Found by measuring
        # rather than by looking, because it only shows at some widths.
        OVERLAP_PROBE = """() => {
              const out = [];
              for (const scope of ['#rail-left', '#rail-right', '#topbar']) {
                const root = document.querySelector(scope);
                if (!root) continue;
                const items = [...root.querySelectorAll('button, label, input, select')]
                  .filter(e => e.offsetParent !== null)
                  .filter(e => !e.closest('label'))
                  .map(e => ({ e, r: e.getBoundingClientRect() }))
                  .filter(o => o.r.width > 2 && o.r.height > 2);
                for (let i = 0; i < items.length; i++) {
                  for (let j = i + 1; j < items.length; j++) {
                    const a = items[i], b = items[j];
                    if (a.e.contains(b.e) || b.e.contains(a.e)) continue;
                    const dx = Math.min(a.r.right, b.r.right) - Math.max(a.r.left, b.r.left);
                    const dy = Math.min(a.r.bottom, b.r.bottom) - Math.max(a.r.top, b.r.top);
                    if (dx > 1 && dy > 1) {
                      out.push(scope + ': ' +
                        (a.e.id || a.e.innerText || a.e.type).trim().slice(0, 18) +
                        ' / ' +
                        (b.e.id || b.e.innerText || b.e.type).trim().slice(0, 18) +
                        ' (' + Math.round(dx) + 'x' + Math.round(dy) + ')');
                    }
                  }
                }
              }
              return out;
            }"""
        def measure_overlaps():
            return page.evaluate(OVERLAP_PROBE)

        # Both layouts, because Pilot's columns are narrower and that is
        # where a label is most likely to be pushed onto its neighbour.
        for layout in ("station", "pilot"):
            set_layout(layout)
            found = measure_overlaps()
            check("%s: nothing overlaps (%s)" % (layout, found[:3] or "clear"),
                  not found)
        # And at a laptop width, where everything is tightest.
        page.set_viewport_size({"width": 1280, "height": 800})
        page.wait_for_timeout(500)
        found = measure_overlaps()
        check("1280 wide: nothing overlaps (%s)" % (found[:3] or "clear"),
              not found)
        page.set_viewport_size({"width": 1600, "height": 900})
        page.wait_for_timeout(450)

        print("5. clicking a tile swaps it in")
        page.click("#tile-left .body")
        page.wait_for_timeout(300)
        check("a different view is now the hero",
              page.locator("#hero #view-map").count() == 0)

        print("6. the layout switch changes the chrome")
        before = page.locator("#hero").bounding_box()
        set_layout("station")
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
        # GPS failure used to live in this rail, then New session did;
        # both have moved (a window and the settings panel), so the check
        # follows whatever the rail still holds - Set home here.
        check("its buttons still reachable",
              page.locator("#rail-right #btn-set_home").count() == 1)

        print("7c. the picture is not inset for a panel that left the edge")
        set_layout("station")
        hero = page.locator("#hero").bounding_box()
        check("no dead strip on the right (%s + %s vs %s)"
              % (round(hero["x"]), round(hero["width"]), 1600),
              hero["x"] + hero["width"] > 1590)

        # Reset lives in the settings panel now, like the layout tabs.
        page.evaluate("() => document.getElementById('resettiles').click()")
        page.wait_for_timeout(300)
        check("Reset panels re-docks it",
              "floating" not in (page.get_attribute("#rail-right", "class") or ""))

        print("7c2. the two windows, off the columns and into the middle")
        # Motor tests and failure injections used to be two more sections
        # in the right-hand column. They are things an instructor stops to
        # do, not things reached for while watching a student fly.
        for cat, text in (("Function Test", "Motor"),
                          ("Failure Injection", "GPS")):
            check("%s is no longer in a rail" % cat,
                  page.locator("#rail-right .items button:has-text('%s')" % text).count() == 0)
        page.click('[data-open-win="motors"]')
        page.wait_for_timeout(400)
        check("the motor window opens", page.locator("#win-motors.open").count() == 1)
        rotors = page.locator("#win-motors .airframe .rotor").count()
        check("it draws the aircraft from above with its rotors (%s)" % rotors,
              rotors == 5)
        spins = page.locator("#win-motors .airframe .spin").all_text_contents()
        check("each hover rotor says which way it turns (%s)" % spins,
              sorted(spins) == ["CCW", "CCW", "CW", "CW"])
        # The aircraft is the control: no list of buttons beside it.
        check("there is no button list beside it",
              page.locator("#win-motors .win-controls button").count() == 0)
        check("the propellers themselves are the controls",
              page.locator("#win-motors .airframe .rotor[data-motor]").count() == 5)
        page.click('#win-motors .airframe .rotor[data-motor="motor_test_3"]')
        page.wait_for_timeout(400)
        check("clicking one runs that motor's test (%s)"
              % page.inner_text("#status")[:40],
              page.locator('#win-motors .airframe .rotor.lit').count() >= 1)
        # Opened clear of everything an instructor reads, and draggable.
        box = page.locator("#win-motors").bounding_box()
        rail = page.locator("#rail-left").bounding_box()
        tapes = page.evaluate("() => window.gcsTapes('#hero canvas.hud')")
        check("it opens clear of the left-hand controls (%s vs %s)"
              % (round(box["x"]), round(rail["x"] + rail["width"])),
              box["x"] >= rail["x"] + rail["width"])
        check("it is see-through, not a solid block (%s)"
              % page.evaluate(
                  "() => getComputedStyle(document.getElementById('win-motors'))"
                  ".backgroundColor"),
              "0.7" in page.evaluate(
                  "() => getComputedStyle(document.getElementById('win-motors'))"
                  ".backgroundColor")
              or "0.78" in page.evaluate(
                  "() => getComputedStyle(document.getElementById('win-motors'))"
                  ".backgroundColor"))
        head = page.locator("#win-motors .win-head").bounding_box()
        page.mouse.move(head["x"] + 90, head["y"] + 12)
        page.mouse.down()
        page.mouse.move(head["x"] + 320, head["y"] + 190, steps=10)
        page.mouse.up()
        page.wait_for_timeout(400)
        moved = page.locator("#win-motors").bounding_box()
        check("and it can be dragged anywhere (%s -> %s)"
              % (round(box["x"]), round(moved["x"])),
              abs(moved["x"] - box["x"]) > 150)

        page.click("#win-motors .win-close")
        page.wait_for_timeout(300)
        check("the X closes it", page.locator("#win-motors.open").count() == 0)

        page.click('[data-open-win="failures"]')
        page.wait_for_timeout(400)
        check("the failures window opens",
              page.locator("#win-failures.open").count() == 1)
        check("a failure still shows its light",
              page.locator("#win-failures #dot-gps_failure").count() == 1)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        check("Escape closes it", page.locator("#win-failures.open").count() == 0)

        print("7c3. the settings panel")
        # The bar had grown until the camera-view select printed over the
        # aircraft's state. What is set once and left now lives behind the
        # gear instead.
        for gone in ("hud-on", "alarm-on", "voice-on", "viewmode",
                     "resettiles", "layouttabs"):
            check("%s is off the bar" % gone,
                  page.locator("#topbar #%s" % gone).count() == 0)
        page.click("#settings-open")
        page.wait_for_timeout(400)
        check("the gear opens it", page.locator("#win-settings.open").count() == 1)
        for here in ("hud-on", "alarm-on", "voice-on", "viewmode",
                     "resettiles", "layouttabs"):
            check("%s is in settings" % here,
                  page.locator("#win-settings #%s" % here).count() == 1)
        # And they still work from in there.
        page.click('#win-settings #layouttabs button[data-layout="station"]')
        page.wait_for_timeout(400)
        check("the layout switch still switches",
              "on" in (page.get_attribute(
                  '#layouttabs button[data-layout="station"]', "class") or ""))
        check("and the panel stays open while you use it",
              page.locator("#win-settings.open").count() == 1)
        page.evaluate("() => { document.querySelector('#layouttabs"
                      " button[data-layout=\"pilot\"]').click(); }")
        page.wait_for_timeout(300)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)

        print("7d. the pre-flight checklist")
        page.click("#pf-open")
        page.wait_for_timeout(600)
        check("it opens", page.locator("#preflight.open").count() == 1)
        auto = page.locator("#preflight .pf-item.auto").count()
        manual = page.locator("#preflight .pf-item.manual").count()
        check("it lists automatic and manual items (%s auto, %s by hand)"
              % (auto, manual), auto >= 4 and manual >= 4)
        # The stub aircraft is disarmed, ready to arm, 10 satellites, 87%
        # battery, so the automatic items should already be green.
        green_auto = page.locator("#preflight .pf-item.auto.ok").count()
        check("the aircraft's own items read from telemetry (%s green)"
              % green_auto, green_auto >= 3)
        check("nothing ticked by hand yet",
              page.locator("#preflight .pf-item.manual.ok").count() == 0)

        row = page.locator("#preflight .pf-item.manual").first
        key = row.get_attribute("data-item")
        row.click()
        page.wait_for_timeout(400)
        check("a manual item ticks (%s)" % key,
              page.locator('#preflight .pf-item.manual.ok[data-item="%s"]' % key).count() == 1)
        row = page.locator('#preflight .pf-item.manual[data-item="%s"]' % key)
        row.click()
        page.wait_for_timeout(400)
        check("and unticks again",
              page.locator('#preflight .pf-item.manual.ok[data-item="%s"]' % key).count() == 0)

        check("it says how many are outstanding (%s)"
              % page.inner_text("#pf-state"),
              "outstanding" in page.inner_text("#pf-state"))

        # An exercise started with red items is allowed, and recorded.
        page.click("#pf-complete")
        page.wait_for_timeout(500)
        check("starting the exercise puts the list away",
              page.locator("#preflight.open").count() == 0)
        check("and says what was not green (%s)" % page.inner_text("#status")[:60],
              "not green" in page.inner_text("#status"))

        print("8. telemetry reached the readouts")
        check("altitude shown", "12.5" in page.inner_text("#p-alt"))
        check("arming state shown", "Ready" in page.inner_text("#t-armcheck"))
        page.click('[data-open-win="failures"]')
        page.wait_for_timeout(400)
        check("a lit failure shows its light",
              "on" in (page.get_attribute("#dot-gps_failure", "class") or ""))

        if "--shot" in sys.argv:
            out = sys.argv[sys.argv.index("--shot") + 1]
            # --nose puts the attitude overlay on screen over a stand-in for
            # bright desert, which is the only way to judge whether it reads.
            if "--window" in sys.argv:
                which = sys.argv[sys.argv.index("--window") + 1]
                if which == "settings":
                    page.click("#settings-open")
                else:
                    page.click('[data-open-win="%s"]' % which)
                page.wait_for_timeout(600)
            if "--checklist" in sys.argv:
                page.click("#pf-open")
                page.wait_for_timeout(700)
            if "--layout" in sys.argv:
                set_layout(sys.argv[sys.argv.index("--layout") + 1])
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
