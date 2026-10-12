"""Check the flight display's wording, colours and low-altitude warning.

    python3 tools/test_flight_display.py

The gauge itself is pixels, and asserting pixels proves very little. What is
worth proving is the decisions behind them: which message the instructor is
shown for a given aircraft state, which of the three colours it is drawn in,
and - the part that could do real harm if it were wrong - exactly when the
low-altitude warning sounds and when it stays quiet.

It drives the real page in Chromium, feeding it aircraft states through the
same window.gcsTelemetry the live telemetry poll writes to, and reads the
answers back through window.gcsHudState().

Needs playwright. Chromium is already on this machine; do not run
"playwright install".
"""
import glob
import json
import os
import sys
import threading

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "tools"))

import test_console_browser as harness  # noqa: E402  (its stubs and server)

RED, AMBER, GREEN = "#ff4b4b", "#ffc400", "#4ade80"


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright is not installed - skipping the flight display check.")
        return 0

    import socketserver
    server = socketserver.TCPServer(("127.0.0.1", 0), harness.Stub)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    fails = []

    def check(tag, cond):
        print(("  PASS  " if cond else "  FAIL  ") + tag)
        if not cond:
            fails.append(tag)

    chrome = None
    for base in sorted(glob.glob("/opt/pw-browsers/chromium-*"), reverse=True):
        candidate = os.path.join(base, "chrome-linux", "chrome")
        if os.path.isfile(candidate):
            chrome = candidate
            break

    with sync_playwright() as pw:
        browser = pw.chromium.launch(executable_path=chrome) if chrome else pw.chromium.launch()
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:%d/" % port)
        page.wait_for_timeout(1200)

        # The telemetry poll overwrites window.gcsTelemetry twice a second,
        # so it is stopped before any state is fed in by hand.
        page.evaluate("() => { for (let i = 1; i < 9999; i++) clearInterval(i); }")

        def state(**fields):
            base = {"armed": False, "mode": "Hold", "altitude_m": 0.0,
                    "arm_ready": True, "airspeed_ms": 0.0, "groundspeed_ms": 0.0,
                    "heading_deg": 0, "roll_deg": 0, "pitch_deg": 0,
                    "battery_pct": 90, "satellites": 11}
            base.update(fields)
            page.evaluate("s => { window.gcsTelemetry = s; }", base)
            return page.evaluate("() => window.gcsHudState()")

        print("1. the page exposes the display")
        check("no JavaScript errors: %s" % (errors[:2] or "none"), not errors)
        check("gcsHudState is there", page.evaluate("() => typeof window.gcsHudState") == "function")
        check("the gauge is on both camera views",
              page.locator("#view-nose canvas.hud").count() == 1
              and page.locator("#view-chase canvas.hud").count() == 1)

        print("2. the message, and its colour")
        s = state(armed=False, arm_ready=True)
        check("disarmed reads DISARMED in red (%s / %s)" % (s["text"], s["colour"]),
              s["text"] == "DISARMED" and s["colour"] == RED)
        s = state(armed=False, arm_ready=False)
        check("blocked from arming reads amber (%s / %s)" % (s["text"], s["colour"]),
              "NOT READY" in s["text"] and s["colour"] == AMBER)
        # Armed is announced for a few seconds on the transition, so the
        # steady-state message is read after that announcement expires.
        state(armed=True, mode="Hold", altitude_m=60)
        page.wait_for_timeout(4300)
        s = state(armed=True, mode="Hold", altitude_m=60)
        check("armed and flying reads green (%s / %s)" % (s["text"], s["colour"]),
              s["colour"] == GREEN)
        s = state(armed=True, mode="Takeoff", altitude_m=5)
        check("takeoff reads amber (%s / %s)" % (s["text"], s["colour"]),
              s["text"] == "TAKE-OFF" and s["colour"] == AMBER)
        s = state(armed=True, mode="Land", altitude_m=5)
        check("landing reads amber (%s / %s)" % (s["text"], s["colour"]),
              s["text"] == "LANDING" and s["colour"] == AMBER)
        s = state(armed=True, mode="Return to Launch", altitude_m=60)
        check("return to launch reads amber (%s / %s)" % (s["text"], s["colour"]),
              "RETURN" in s["text"] and s["colour"] == AMBER)

        print("3. the low-altitude warning")
        # Disarmed on the pad at zero feet must not warn - this is the case
        # that would otherwise have the alarm sounding all lesson.
        s = state(armed=False, altitude_m=0.0)
        check("quiet while disarmed on the ground", not s["lowActive"])
        s = state(armed=True, mode="Takeoff", altitude_m=2.0)
        check("quiet through the takeoff climb", not s["lowActive"] and not s["lowArmed"])
        s = state(armed=True, mode="Hold", altitude_m=60.0)
        check("arms once well clear of the threshold", s["lowArmed"] and not s["lowActive"])
        s = state(armed=True, mode="Hold", altitude_m=8.0)
        check("sounds below the threshold (%s)" % s["text"],
              s["lowActive"] and s["text"] == "LOW ALTITUDE" and s["colour"] == RED)
        s = state(armed=True, mode="Land", altitude_m=3.0)
        check("quiet in LAND, where descending is the point", not s["lowActive"])
        s = state(armed=False, mode="Hold", altitude_m=0.2)
        check("forgotten again on disarm", not s["lowActive"] and not s["lowArmed"])
        s = state(armed=True, mode="Hold", altitude_m=2.0)
        check("stays quiet after disarm until it has climbed again",
              not s["lowActive"])

        print("4. the home point, seen through the camera")
        # 500 m due north of home, flying north, 100 m up, wings level: home
        # is behind and below. Flown north-ish so the arithmetic is checkable
        # by hand rather than only by running it.
        HOME_LAT, HOME_LON = 40.8750, -119.0849

        def at(north_m, east_m, alt, yaw, roll=0, pitch=0, fov=1.5708):
            page.evaluate(
                "s => { window.gcsTelemetry = s; }",
                {"armed": True, "mode": "Hold", "altitude_m": alt,
                 "home_lat": HOME_LAT, "home_lon": HOME_LON,
                 "latitude": HOME_LAT + north_m / 110540.0,
                 "longitude": HOME_LON + east_m / (111320.0 * 0.7566),
                 "yaw_deg": yaw, "heading_deg": yaw, "roll_deg": roll,
                 "pitch_deg": pitch, "airspeed_ms": 18, "groundspeed_ms": 18,
                 "camera_fov": {"nose": fov, "chase": fov}})
            return page.evaluate("() => window.gcsHomePoint('#hero canvas.hud')")

        page.click('#viewtabs button[data-view="nose"]')
        page.wait_for_timeout(400)
        box = page.locator("#hero canvas.hud").bounding_box()
        mid = box["width"] / 2

        h = at(-400, 0, 100, 0)       # home 400 m straight ahead, 100 m below
        check("straight ahead: drawn in the picture, not as an arrow (%s)"
              % (h and h["arrow"]), h and not h["arrow"])
        check("straight ahead: centred left to right (%s vs %s)"
              % (h and round(h["x"]), round(mid)), h and abs(h["x"] - mid) < 12)
        check("straight ahead: below the horizon (%s vs %s)"
              % (h and round(h["y"]), round(box["height"] / 2)),
              h and h["y"] > box["height"] / 2)
        check("straight ahead: reports the slant distance (%s m)" % (h and h["dist"]),
              h and 400 < h["dist"] < 440)

        h = at(-400, 0, 100, 90)      # same place, but flying east
        check("home off the left wing when flying east (%s vs %s)"
              % (h and round(h["x"]), round(mid)), h and h["x"] < mid)

        h = at(400, 0, 100, 0)        # home behind: an arrow, not a marker
        check("behind the aircraft: an arrow instead (%s)" % (h and h["arrow"]),
              h and h["arrow"])
        check("the arrow points backwards (%s rad)"
              % (h and round(h["bearing"], 2)),
              h and abs(abs(h["bearing"]) - 3.1416) < 0.2)

        # Bank right and the ground below swings to the right of the
        # windscreen, which is what the horizon tilting away from you means.
        h = at(-400, 0, 100, 0, roll=30)
        check("banked right: the ground below swings right (%s vs %s)"
              % (h and round(h["x"]), round(mid)), h and h["x"] > mid + 20)
        h = at(-400, 0, 100, 0, roll=-30)
        check("banked left: and left the other way (%s vs %s)"
              % (h and round(h["x"]), round(mid)), h and h["x"] < mid - 20)

        # A narrower lens magnifies: the same point sits further from the
        # middle. Both angles have to keep it inside the picture, or the
        # comparison is between a marker and an edge arrow.
        wide = at(-400, 60, 100, 0, fov=1.5708)
        narrow = at(-400, 60, 100, 0, fov=1.1)
        check("both lenses still show the marker itself",
              wide and narrow and not wide["arrow"] and not narrow["arrow"])
        check("a narrower lens pushes the same point further out (%s -> %s)"
              % (wide and round(wide["x"]), narrow and round(narrow["x"])),
              wide and narrow and abs(narrow["x"] - mid) > abs(wide["x"] - mid))

        # The whole point of reading the angle from Gazebo: no angle, no marker.
        page.evaluate("() => { window.gcsTelemetry.camera_fov = {}; }")
        check("no marker when the camera's field of view is unknown",
              page.evaluate("() => window.gcsHomePoint('#hero canvas.hud')") is None)

        print("5. the sound can be silenced")
        # The alarm switch lives in the settings panel now, under the
        # "Warnings & sound" category, so the panel has to be opened and
        # that category chosen before it can be clicked.
        check("there is an alarm switch", page.locator("#alarm-on").count() == 1)
        page.click("#settings-open")
        page.wait_for_timeout(300)
        page.click('#set-tabs button[data-tab="sound"]')
        page.wait_for_timeout(250)
        page.uncheck("#alarm-on")
        state(armed=True, mode="Hold", altitude_m=60.0)
        s = state(armed=True, mode="Hold", altitude_m=5.0)
        check("the warning still shows with the sound off", s["lowActive"])
        page.check("#alarm-on")
        page.keyboard.press("Escape")
        page.wait_for_timeout(250)

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
