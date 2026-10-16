"""Check the motor sound, the two new switches, and the landing gear.

    python3 tools/test_sound_and_gear.py

Needs neither PX4 nor Gazebo. Three things are worth proving here:

  * the motor sound runs the RIGHT MOTORS. Hover rotors in hover and
    through both transitions, pusher in fixed wing and on the way into
    it, nothing at all while disarmed. Getting this backwards would teach
    a student that a VTOL keeps its lift rotors turning in cruise;
  * the two switches are on the page and do what they say - the lights
    switch in particular, because it now tells the station which way to
    go rather than asking it to toggle, and a sign error there leaves the
    console showing the opposite of the truth;
  * the landing gear stands on the ground. Four legs that lean have to
    have their TOPS on the rails and their BOTTOMS at one height, and
    that is arithmetic that will not announce it has gone wrong - the
    aircraft will just be sunk into the runway.

What this does NOT prove is that the motors SOUND right. Nobody has
listened to them yet with the simulator running.

Needs playwright for the browser half (pip install playwright). Chromium
is already on this machine; do not run "playwright install".
"""
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


# The console browser check already builds the whole station against
# stubs. Importing it borrows all of that rather than keeping a second
# copy of it here to drift out of step.
import test_console_browser as console_test     # noqa: E402

PAGE = console_test.PAGE


print("1. the switches are on the page")
check("motor sound switch", 'id="motor-sound-on"' in PAGE)
check("motor volume slider", 'id="motor-volume"' in PAGE)
check("navigation lights switch", 'id="lights-on"' in PAGE)
check("the motor sound script is served", "gcsMotorDemand" in PAGE)


print("2. the lights plugin takes a direction, not just a nudge")
import importlib.util                                           # noqa: E402

spec = importlib.util.spec_from_file_location(
    "plugin_aircraft_lights", os.path.join(REPO, "plugins", "aircraft_lights.py"))
lights_plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(lights_plugin)

lights_plugin.toggle_lights("1")
check("on=1 switches them on", lights_plugin.state["active"] is True)
lights_plugin.toggle_lights("1")
check("on=1 again leaves them on", lights_plugin.state["active"] is True)
lights_plugin.toggle_lights("0")
check("on=0 switches them off", lights_plugin.state["active"] is False)
lights_plugin.toggle_lights()
check("no argument still toggles", lights_plugin.state["active"] is True)
lights_plugin.toggle_lights()
check("and toggles back", lights_plugin.state["active"] is False)


print("3. the landing gear reaches the ground")
import aircraft_legs_apply as gear                              # noqa: E402
import math                                                     # noqa: E402

made = gear.parts()
kinds = [k for k, _, _, _ in made]
names = [n for _, n, _, _ in made]
check("two mounting rails", kinds.count("box") == 2)
check("four leg tubes", len([n for n in names if n.endswith("_tube")]) == 4)
# The gimbal moved out of this tool on 12 Oct 2026 and into
# tools/gimbal_apply.py, which builds it as a real two-axis mount.
# tools/test_payload.py checks it. What matters here is that this tool
# leaves the space under the belly clear for it.
check("no gimbal here any more", not [n for n in names if "gimbal" in n])


def ends(fields):
    """A leaning cylinder's two ends, from its centre and its rotation."""
    roll, pitch = fields["roll"], fields["pitch"]
    axis = (math.cos(roll) * math.sin(pitch),
            -math.sin(roll),
            math.cos(roll) * math.cos(pitch))
    half = fields["length"] / 2
    centre = (fields["x"], fields["y"], fields["z"])
    top = tuple(centre[i] + axis[i] * half for i in range(3))
    bottom = tuple(centre[i] - axis[i] * half for i in range(3))
    return top, bottom


legs = [(n, f) for k, n, f, _ in made if n.endswith("_tube")]
for name, fields in legs:
    top, bottom = ends(fields)
    check("%s stands on the ground plane" % name,
          abs(bottom[2] - gear.FOOT_Z) < 1e-3)
    check("%s hangs off a rail" % name,
          abs(top[2] - gear.LEG_TOP_Z) < 1e-3
          and abs(abs(top[1]) - gear.RAIL_Y) < 1e-3)
    check("%s splays outboard" % name, abs(bottom[1]) > abs(top[1]) + 0.01)
    leans_right_way = ((bottom[0] > top[0] + 0.01) if "front" in name
                       else (bottom[0] < top[0] - 0.01))
    check("%s leans away from the middle" % name, leans_right_way)



print("4. the edit it makes to the aircraft model")
# A fragment shaped like PX4's standard_vtol: the same base_link, the same
# named collision with a pose, closed the same way.
MODEL = """<?xml version="1.0" ?>
<sdf version='1.9'>
  <model name='standard_vtol'>
    <link name='base_link'>
      <pose>0 0 0 0 0 0</pose>
      <collision name='base_link_collision'>
        <pose>0 0 -0.07 0 0 0</pose>
        <geometry>
          <box>
            <size>0.55 2.144 0.05</size>
          </box>
        </geometry>
      </collision>
      <visual name='base_link_visual'>
        <geometry>
          <box><size>1 1 1</size></box>
        </geometry>
      </visual>
    </link>
  </model>
</sdf>
"""

work = tempfile.mkdtemp()
path = os.path.join(work, "model.sdf")
with open(path, "w") as handle:
    handle.write(MODEL)
original = open(path).read()
gear.MODEL = path

check("dry run writes nothing", gear.apply(True, True) == 0
      and open(path).read() == original)

check("it applies cleanly", gear.apply(False, True) == 0)
written = open(path).read()
try:
    ET.parse(path)
    parsed = True
except ET.ParseError:
    parsed = False
check("the result is valid XML", parsed)
check("the legs are in the model", "leg_front_left_tube" in written)
check("the stance was lowered to the feet",
      "<pose>0 0 -0.295 0 0 0</pose>" in written)
check("the backup was kept", os.path.exists(path + gear.SUFFIX))

check("running it twice changes nothing", gear.apply(False, True) == 0
      and open(path).read() == written)

check("--revert puts the original back",
      gear.revert() == 0 and open(path).read() == original)

# --no-stance is the escape hatch for anyone who does not want the drop
# at spawn. It must add the legs and leave the physics alone.
with open(path, "w") as handle:
    handle.write(MODEL)
os.remove(path + gear.SUFFIX)
gear.apply(False, False)
plain = open(path).read()
check("--no-stance still adds the legs", "leg_front_left_tube" in plain)
check("--no-stance leaves the collision alone",
      "<pose>0 0 -0.07 0 0 0</pose>" in plain)
shutil.rmtree(work, ignore_errors=True)


print("5. which motors run, in a real browser")


def browser_checks():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP  playwright is not installed")
        print("        pip install playwright  (Chromium is already here)")
        return

    import glob
    import socketserver
    import threading

    chrome = None
    for base in sorted(glob.glob("/opt/pw-browsers/chromium-*"), reverse=True):
        candidate = os.path.join(base, "chrome-linux", "chrome")
        if os.path.isfile(candidate):
            chrome = candidate
            break

    asked = []

    class Recording(console_test.Stub):
        """The console's stub server, plus a record of the lights calls."""

        def do_GET(self):
            if self.path.startswith("/action/aircraft_lights"):
                asked.append(self.path)
                body = b"Lights on."
                self.send_response(200)
                self.send_header("Content-type", "text/plain; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            console_test.Stub.do_GET(self)

    server = socketserver.TCPServer(("127.0.0.1", 0), Recording)
    server.daemon_threads = True
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    with sync_playwright() as pw:
        browser = (pw.chromium.launch(executable_path=chrome) if chrome
                   else pw.chromium.launch())
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        errors = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:%d/" % port)
        page.wait_for_timeout(700)
        check("the page runs without errors", not errors)
        if errors:
            for line in errors[:4]:
                print("        " + line)

        # The rotors now spool up over a second and a half rather than
        # switching on, so a demand taken at the instant of arming is
        # correctly zero. These helpers drive the clock forward past the
        # spool so the steady state can be checked; the spool itself is
        # checked on its own below.
        clock = [1000000.0]

        # STOP THE PAGE'S OWN 80 ms LOOP FIRST. It calls the same
        # gcsMotorDemand with Date.now(), and the spool it updates is the
        # one these helpers drive with the virtual clock above. A tick
        # landing between two calls here restarts the ramp from zero, so
        # both the quiet and the loud reading come back at idle and "the
        # pitch follows the throttle" fails. Intermittent, about one run in
        # three, and only inside verify_install where the machine is busy -
        # which is the worst kind, because the check the instructor is told
        # to trust before committing was the one crying wolf.
        stopped = page.evaluate(
            "() => { if (window.gcsMotorTick) { clearInterval(window.gcsMotorTick);"
            " window.gcsMotorTick = null; return true; } return false; }")
        check("the page's own sound loop can be stopped for this test", stopped)

        def raw(ms, **telem):
            """One reading, ms after the previous one."""
            clock[0] += ms
            return page.evaluate(
                "a => window.gcsMotorDemand(a[0], a[1])", [telem, clock[0]])

        def demand(**telem):
            """A reading once the spool has settled.

            Two calls, not one: the first is what tells the spool the
            armed state changed, and it is correctly still at the old
            level on that call. Asking once and expecting the new steady
            state was this test's own mistake, not the code's.
            """
            raw(10, **telem)
            return raw(6000, **telem)

        off = demand(armed=False, vtol_state="Hover", throttle_pct=0)
        check("disarmed: nothing turns", off["hover"] == 0 and off["pusher"] == 0)

        hover = demand(armed=True, vtol_state="Hover", throttle_pct=55)
        check("hover: the four rotors, not the pusher",
              hover["hover"] == 1 and hover["pusher"] == 0)

        going = demand(armed=True, vtol_state="Transitioning to fixed wing",
                       throttle_pct=90)
        check("into fixed wing: both, which is what a transition is",
              going["hover"] == 1 and going["pusher"] == 1)

        cruise = demand(armed=True, vtol_state="Fixed wing", throttle_pct=60)
        check("fixed wing: the pusher only - PX4 stops the lift rotors",
              cruise["hover"] == 0 and cruise["pusher"] == 1)

        back = demand(armed=True, vtol_state="Transitioning to hover",
                      throttle_pct=40)
        check("back to hover: the rotors only, the pusher is stopped",
              back["hover"] == 1 and back["pusher"] == 0)

        print("   the rotors spool up rather than switching on")
        # Start from a settled, disarmed aircraft.
        raw(6000, armed=False, vtol_state="Hover", throttle_pct=0)
        hover = dict(armed=True, vtol_state="Hover", throttle_pct=0)
        start = raw(10, **hover)
        check("nothing is turning in the first hundredth of a second (%.2f)"
              % start["spool"], start["spool"] < 0.05)
        part = raw(700, **hover)
        check("part way up after seven tenths of a second (%.2f)"
              % part["spool"], 0.2 < part["spool"] < 0.9)
        up = raw(2000, **hover)
        check("fully up after a couple of seconds (%.2f)" % up["spool"],
              up["spool"] > 0.99)
        stopping = dict(armed=False, vtol_state="Hover", throttle_pct=0)
        raw(10, **stopping)
        # At 700 ms the spin-up was 41% of the way there; the run-down is
        # slower, so at the same 700 ms it must still be well above 59%.
        winding = raw(690, **stopping)
        check("and winds down slower than it wound up (%.2f left)"
              % winding["spool"], 0.6 < winding["spool"] < 1.0)
        settled = raw(6000, **stopping)
        check("then stops (%.2f)" % settled["spool"], settled["spool"] == 0)

        quiet = demand(armed=True, vtol_state="Hover", throttle_pct=5)
        loud = demand(armed=True, vtol_state="Hover", throttle_pct=100)
        check("the pitch follows the throttle",
              loud["hoverHz"] > quiet["hoverHz"] + 40)
        check("an armed aircraft is never silent (%.2f)" % quiet["effort"],
              quiet["effort"] >= 0.17)
        check("the pusher is pitched apart from the rotors",
              abs(loud["pusherHz"] - loud["hoverHz"]) > 20)

        state = page.evaluate("() => window.gcsMotorSound()")
        check("the sound is on by default", state["on"] is True)
        page.evaluate(
            "() => { var b = document.getElementById('motor-sound-on');"
            " b.checked = false; b.dispatchEvent(new Event('change')); }")
        page.wait_for_timeout(200)
        check("the switch turns it off",
              page.evaluate("() => window.gcsMotorSound().on") is False)

        # The lights switch, both ways round.
        page.evaluate(
            "() => { var b = document.getElementById('lights-on');"
            " b.checked = true; b.dispatchEvent(new Event('change')); }")
        page.wait_for_timeout(300)
        page.evaluate(
            "() => { var b = document.getElementById('lights-on');"
            " b.checked = false; b.dispatchEvent(new Event('change')); }")
        page.wait_for_timeout(300)
        check("switching the lights on says so", "on=1" in " ".join(asked))
        check("switching them off says so", "on=0" in " ".join(asked))

        browser.close()
    server.shutdown()


browser_checks()

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
