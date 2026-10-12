"""Check the payload gimbal: the geometry, and the model edit.

    python3 tools/test_payload.py

Needs neither PX4 nor Gazebo.

WHY THIS EXISTS. The gimbal is pointing maths, and pointing maths fails
silently: a sign error does not crash, it just looks at the wrong half of
the world, and on a featureless training area nobody notices until a
student has been taught to distrust the instrument. Every case below is
one a person can check in their head:

  * tilt 90 looks straight down, whatever the aircraft is doing;
  * flying north, pan 90 looks east;
  * a target 500 m north of an aircraft flying north is dead ahead;
  * a lock held while the aircraft flies past swings the gimbal round;
  * the mount's travel actually stops it.
"""
import math
import os
import shutil
import sys
import tempfile
import types
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


def close(a, b, tol=1e-6):
    return a is not None and b is not None and abs(a - b) < tol


import gimbal                                               # noqa: E402

print("1. where the camera is looking")
check("tilt 90 is straight down",
      close(gimbal.boresight_body(0, 90)[2], 1.0, 1e-9))
check("tilt 0 pan 0 is dead ahead",
      close(gimbal.boresight_body(0, 0)[0], 1.0, 1e-9))
check("pan 90 is out of the right-hand side",
      close(gimbal.boresight_body(90, 0)[1], 1.0, 1e-9))

# Flying north (yaw 0), looking 90 right, should be looking east.
north, east, down = gimbal.boresight_ned(0, 0, 0, 90, 0)
check("flying north, pan 90 looks east", close(east, 1.0, 1e-9))

# Flying east (yaw 90), looking straight ahead, should be looking east.
north, east, down = gimbal.boresight_ned(0, 0, 90, 0, 0)
check("flying east, pan 0 looks east", close(east, 1.0, 1e-9))

# Straight down stays straight down however the aircraft is pointing,
# because the mount is bolted to the airframe only in bank and pitch -
# with the aircraft level, yaw cannot move a vertical line of sight.
for heading in (0, 45, 180, 300):
    _, _, down = gimbal.boresight_ned(0, 0, heading, 0, 90)
    check("heading %d: straight down is still down" % heading,
          close(down, 1.0, 1e-9))

# Banked right 30 degrees, looking straight down the mount. Because the
# mount does NOT stabilise, the line of sight banks with the aircraft -
# and it goes LEFT, not right, which is the opposite of most people's
# first guess and was wrong in the first draft of this test. Rolling
# right tilts the lift vector right, so it tilts the belly - and anything
# bolted to it looking down - to the left by the same angle.
north, east, down = gimbal.boresight_ned(30, 0, 0, 0, 90)
check("banked right 30, a down-looking unstabilised mount looks 30 left",
      close(east, -math.sin(math.radians(30)), 1e-9)
      and close(down, math.cos(math.radians(30)), 1e-9))

print("2. working out where a target is")
target = gimbal.project_target(23.5, 6.5, 1200.0,
                               gimbal.boresight_ned(0, 0, 0, 0, 90), 150.0)
check("straight down, 150 m, lands under the aircraft",
      close(target["lat"], 23.5, 1e-9) and close(target["lon"], 6.5, 1e-9))
check("and 150 m lower", close(target["alt_amsl"], 1050.0, 1e-6))

# 500 m north and 200 m below.
flat = {"lat": 23.5 + 500.0 / gimbal.EARTH_M_PER_DEG, "lon": 6.5,
        "alt_amsl": 1000.0}
answer = gimbal.aim_at_target(23.5, 6.5, 1200.0, 0, 0, 0, flat)
pan, tilt, distance = answer
check("a target due north, flying north, is dead ahead", close(pan, 0.0, 1e-6))
check("and 200 m below at 500 m out is 21.8 degrees down",
      close(tilt, math.degrees(math.atan2(200.0, 500.0)), 1e-6))
check("the slant range is the hypotenuse",
      close(distance, math.hypot(500.0, 200.0), 0.5))

# The same target, now flying east: it should be off the left wing.
pan, tilt, _ = gimbal.aim_at_target(23.5, 6.5, 1200.0, 0, 0, 90, flat)
check("flying east, a target to the north is 90 left", close(pan, -90.0, 1e-6))

print("3. a lock held while the aircraft flies past")
# Aircraft starts 500 m south of the target and flies north past it. The
# gimbal should start ahead, swing through the beam, and end up behind.
pans = []
for offset in (-500.0, -100.0, 100.0, 500.0):
    lat = flat["lat"] + offset / gimbal.EARTH_M_PER_DEG
    pan, tilt, _ = gimbal.aim_at_target(lat, 6.5, 1200.0, 0, 0, 0, flat)
    pans.append(round(pan, 1))
check("ahead before, behind after (%s)" % pans,
      close(pans[0], 0.0, 0.01) and abs(pans[-1]) > 179.0)
check("and the tilt steepens on the way in",
      gimbal.aim_at_target(flat["lat"] - 100.0 / gimbal.EARTH_M_PER_DEG, 6.5,
                           1200.0, 0, 0, 0, flat)[1]
      > gimbal.aim_at_target(flat["lat"] - 500.0 / gimbal.EARTH_M_PER_DEG, 6.5,
                             1200.0, 0, 0, 0, flat)[1])

print("3b. stabilisation holds the line of sight while the aircraft rolls")
# Aim 20 degrees right and 40 down with the aircraft level, then bank it
# 30 degrees right. A stabilised mount must end up looking at the same
# patch of ground, which means DIFFERENT joint angles.
level = gimbal.world_from_body(0, 0, 0, 20.0, 40.0)
banked_pan, banked_tilt = gimbal.body_from_world(30, 0, 0, level[0], level[1])
check("the joints have to move to hold it (%.1f, %.1f -> %.1f, %.1f)"
      % (20.0, 40.0, banked_pan, banked_tilt),
      abs(banked_pan - 20.0) > 2.0 or abs(banked_tilt - 40.0) > 2.0)
held = gimbal.world_from_body(30, 0, 0, banked_pan, banked_tilt)
check("and the line of sight comes out where it started (%.2f, %.2f)"
      % held, close(held[0], level[0], 1e-6) and close(held[1], level[1], 1e-6))
# The unstabilised case, for contrast: same joints, different ground.
drifted = gimbal.world_from_body(30, 0, 0, 20.0, 40.0)
# Shortest way round, or a 27 degree swing reads as 332.
moved = abs((drifted[0] - level[0] + 180.0) % 360.0 - 180.0)
check("while leaving the joints alone moves it (%.1f deg of bearing)" % moved,
      moved > 5.0)
# And a full turn: the bearing held must not depend on the heading.
for heading in (0, 90, 215, 330):
    pan, tilt = gimbal.body_from_world(0, 0, heading, level[0], level[1])
    back = gimbal.world_from_body(0, 0, heading, pan, tilt)
    check("heading %d: still pointing at bearing %.0f" % (heading, level[0]),
          close(back[0], level[0], 1e-6) and close(back[1], level[1], 1e-6))

print("4. the mount's travel")
pan, tilt = gimbal.clamp_angles(200.0, 120.0)
check("pan folds into +-180 (%.1f)" % pan, close(pan, -160.0, 1e-9))
check("tilt stops at straight down (%.1f)" % tilt,
      close(tilt, gimbal.TILT_DOWN, 1e-9))
pan, tilt = gimbal.clamp_angles(0.0, -80.0)
check("and cannot look further up than the mount allows (%.1f)" % tilt,
      close(tilt, gimbal.TILT_UP, 1e-9))

print("5. a click in the picture, and the zoom")
# A 60 degree lens: the right-hand edge is half of 60 off axis, but NOT
# exactly 30 - a pinhole camera is not linear in angle.
d_pan, d_tilt = gimbal.pixel_offset_deg(0.5, 0.0, math.radians(60.0), 0.5625)
check("the frame edge is about half the field of view (%.1f)" % d_pan,
      29.0 < d_pan < 31.0)
check("the centre of the frame is no offset at all",
      close(gimbal.pixel_offset_deg(0, 0, 1.05, 0.5625)[0], 0.0, 1e-12))
check("a click below the middle tilts down",
      gimbal.pixel_offset_deg(0.0, 0.25, 1.05, 0.5625)[1] > 0)

gimbal.set_zoom(4.0)
narrow = gimbal.effective_fov_rad()
gimbal.set_zoom(1.0)
wide = gimbal.effective_fov_rad()
check("zooming in narrows the field of view (%.1f -> %.1f deg)"
      % (math.degrees(wide), math.degrees(narrow)), narrow < wide / 3.0)
check("zoom is clamped", gimbal.set_zoom(999) == gimbal.ZOOM_MAX
      and gimbal.set_zoom(0.1) == gimbal.ZOOM_MIN)
gimbal.set_zoom(1.0)

print("6. a range nobody measured is reported as computed, not as fact")
down_ray = gimbal.boresight_ned(0, 0, 0, 0, 90)
check("straight down from 120 m is 120 m",
      close(gimbal.ground_range(down_ray, 120.0), 120.0, 1e-6))
level = gimbal.boresight_ned(0, 0, 0, 0, 0)
check("a level line of sight never meets flat ground",
      gimbal.ground_range(level, 120.0) is None)
shallow = gimbal.boresight_ned(0, 0, 0, 0, 30)
check("30 degrees down from 100 m is 200 m of slant",
      close(gimbal.ground_range(shallow, 100.0), 200.0, 1e-6))

print("7. the model edit")
import gimbal_apply as gm                                   # noqa: E402

MODEL = """<?xml version="1.0" ?>
<sdf version='1.9'>
  <model name='standard_vtol'>
    <link name='base_link'>
      <pose>0 0 0 0 0 0</pose>
      <visual name='gimbal_yoke'>
        <geometry><box><size>1 1 1</size></box></geometry>
      </visual>
      <visual name='gimbal_ball'>
        <geometry><sphere><radius>1</radius></sphere></geometry>
      </visual>
      <visual name='gimbal_lens'>
        <geometry><box><size>1 1 1</size></box></geometry>
      </visual>
    </link>
    <link name='rotor_0'>
      <pose>0.35 -0.35 0.07 0 0 0</pose>
    </link>
    <plugin filename='gz-sim-joint-position-controller-system'
            name='gz::sim::systems::JointPositionController'>
      <joint_name>servo_0</joint_name>
      <sub_topic>servo_0</sub_topic>
    </plugin>
  </model>
</sdf>
"""

work = tempfile.mkdtemp()
path = os.path.join(work, "model.sdf")
open(path, "w").write(MODEL)
original = open(path).read()
gm.MODEL = path

check("dry run writes nothing",
      gm.apply(True) == 0 and open(path).read() == original)
check("it applies cleanly", gm.apply(False) == 0)
written = open(path).read()
try:
    tree = ET.parse(path)
    parsed = True
except ET.ParseError:
    parsed = False
check("the result is valid XML", parsed)

model = tree.getroot().find("model")
links = [l.get("name") for l in model.findall("link")]
joints = {j.get("name"): j for j in model.findall("joint")}
check("the two gimbal links are there",
      "gimbal_yaw_link" in links and "gimbal_pitch_link" in links)
visuals = [v.get("name") for l in model.findall("link")
           for v in l.findall("visual")]
check("the old static shapes are gone (%s)" % visuals,
      not {"gimbal_ball", "gimbal_yoke", "gimbal_lens"} & set(visuals))
check("the ball body replaced them", "gimbal_ball_body" in written)
check("the yaw joint hangs off base_link",
      joints["gimbal_yaw_joint"].find("parent").text == "base_link")
check("the pitch joint hangs off the yaw link",
      joints["gimbal_pitch_joint"].find("parent").text == "gimbal_yaw_link")
check("the yaw axis is Z",
      joints["gimbal_yaw_joint"].find("axis/xyz").text.strip() == "0 0 1")
check("the pitch axis is Y",
      joints["gimbal_pitch_joint"].find("axis/xyz").text.strip() == "0 1 0")

tilt_lo = float(joints["gimbal_pitch_joint"].find("axis/limit/lower").text)
tilt_hi = float(joints["gimbal_pitch_joint"].find("axis/limit/upper").text)
check("the pitch travel matches what the station clamps to",
      close(math.degrees(tilt_lo), gimbal.TILT_UP, 1e-3)
      and close(math.degrees(tilt_hi), gimbal.TILT_DOWN, 1e-3))

sensors = [s.get("name")
           for l in model.findall("link") if l.get("name") == "gimbal_pitch_link"
           for s in l.findall("sensor")]
check("the camera is on the pitch link", "payload_camera" in sensors)
check("so is the rangefinder", "payload_lrf" in sensors)

controlled = [p.find("joint_name").text for p in model.findall("plugin")
              if p.find("joint_name") is not None]
check("both gimbal joints have a position controller",
      "gimbal_yaw_joint" in controlled and "gimbal_pitch_joint" in controlled)
# The servo controllers in this model carry <sub_topic>, which moves them
# off the default command topic. Copying that onto the gimbal would make
# it unreachable, so check it was not copied.
gimbal_plugins = [p for p in model.findall("plugin")
                  if p.find("joint_name") is not None
                  and p.find("joint_name").text.startswith("gimbal_")]
check("and no <sub_topic>, so they stay on the topic the station publishes to",
      all(p.find("sub_topic") is None for p in gimbal_plugins))

check("running it twice changes nothing",
      gm.apply(False) == 0 and open(path).read() == written)
check("--revert puts the original back",
      gm.revert() == 0 and open(path).read() == original)
shutil.rmtree(work, ignore_errors=True)

print("8. the station's half agrees with the model's half")
import sim_target                                           # noqa: E402

check("the joint names match",
      gm.YAW_JOINT == sim_target.GIMBAL_JOINTS[0]
      and gm.PITCH_JOINT == sim_target.GIMBAL_JOINTS[1])
check("the camera link and sensor match",
      (gm.PITCH_LINK, gm.CAMERA) == sim_target.GIMBAL_CAMERA)
check("the rangefinder topic matches", gm.LRF_TOPIC == sim_target.LRF_TOPIC)
check("the command topic is the model-scoped cmd_pos one",
      sim_target.gimbal_joint_topic("gimbal_yaw_joint")
      == "/model/%s/joint/gimbal_yaw_joint/0/cmd_pos" % sim_target.MODEL)

print("9. the payload screen, in a real browser")


def browser_checks():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("  SKIP  playwright is not installed")
        return

    import glob
    import json
    import socketserver
    import threading
    from urllib.parse import parse_qs, urlparse

    import test_console_browser as console_test

    chrome = None
    for base in sorted(glob.glob("/opt/pw-browsers/chromium-*"), reverse=True):
        candidate = os.path.join(base, "chrome-linux", "chrome")
        if os.path.isfile(candidate):
            chrome = candidate
            break

    asked = []
    # A stand-in gimbal: it records what it was told and answers with a
    # state that reflects it, so the screen can be checked end to end
    # without Gazebo. The real arithmetic is already checked above.
    fake = {"pan_deg": 0.0, "tilt_deg": 30.0, "zoom": 1.0, "mode": "manual",
            "target": None, "range_m": None, "range_source": None,
            "range_age_s": None, "range_stale": False, "fov_deg": 60.0,
            "pan_limit_deg": 180.0, "tilt_up_deg": -30.0, "tilt_down_deg": 90.0,
            "zoom_max": 12.0, "problem": None, "stabilised": True,
            "world_az_deg": 0.0, "world_el_deg": 30.0,
            "fps": 12.0, "view_mode": "normal", "camera_live": True,
            "recording": {"on": False, "frames": 0, "seconds": 0}}

    class Recording(console_test.Stub):
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/chase_view":
                query = parse_qs(parsed.query)
                body = json.dumps({"az_deg": 0.0, "el_deg": 13.8,
                                   "preset": query.get("preset", ["behind"])[0]
                                   }).encode()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if parsed.path.startswith("/payload_") and parsed.path != "/payload_feed":
                asked.append(self.path)
                query = parse_qs(parsed.query)
                what = parsed.path[len("/payload_"):]
                if what == "zoom":
                    fake["zoom"] = round(
                        fake["zoom"] * (1.25 ** float(query["steps"][0])), 2)
                elif what == "aim":
                    fake["pan_deg"] += float(query.get("dpan", [0])[0])
                    fake["tilt_deg"] += float(query.get("dtilt", [0])[0])
                elif what == "lock":
                    fake["mode"] = "lock"
                    fake["range_m"] = 412.0
                    fake["range_source"] = "laser"
                    fake["range_age_s"] = 0.2
                elif what == "unlock":
                    fake["mode"] = "manual"
                elif what == "stabilise":
                    fake["stabilised"] = query.get("on", ["1"])[0] == "1"
                elif what == "record":
                    fake["recording"] = {
                        "on": query.get("on", ["1"])[0] == "1",
                        "frames": 3, "seconds": 2}
                body = json.dumps(fake).encode()
                self.send_response(200)
                self.send_header("Content-type", "application/json")
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
        for line in errors[:4]:
            print("        " + line)

        page.click('#viewtabs button[data-view="payload"]')
        page.wait_for_timeout(700)
        check("the payload view becomes the main screen",
              page.evaluate("() => document.getElementById('hero')"
                            ".contains(document.getElementById('view-payload'))"))
        check("its control strip is on screen",
              page.locator("#paybar").is_visible())

        # Drag across a quarter of the picture: the gimbal should be told
        # to slew, and in the direction that makes the picture follow the
        # hand rather than fight it.
        box = page.locator("#view-payload").bounding_box()
        page.mouse.move(box["x"] + box["width"] * 0.5, box["y"] + box["height"] * 0.4)
        page.mouse.down()
        page.mouse.move(box["x"] + box["width"] * 0.25,
                        box["y"] + box["height"] * 0.4, steps=6)
        page.mouse.up()
        page.wait_for_timeout(400)
        aims = [a for a in asked if a.startswith("/payload_aim")]
        check("dragging slews the gimbal (%d commands)" % len(aims), aims)
        check("dragging the picture left looks right",
              fake["pan_deg"] > 1.0)

        before = fake["zoom"]
        page.mouse.move(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)
        page.mouse.wheel(0, -300)
        page.wait_for_timeout(400)
        check("the wheel zooms in (%s -> %s)" % (before, fake["zoom"]),
              fake["zoom"] > before)
        page.mouse.wheel(0, 600)
        page.wait_for_timeout(400)
        check("and back out again", fake["zoom"] < 1.6)

        # Target selection is two steps on purpose: arm it, then click.
        # A click that locked on by itself would fire every time an
        # operator touched the picture.
        page.click("#pay-track")
        page.wait_for_timeout(200)
        locks = [a for a in asked if a.startswith("/payload_lock")]
        check("arming TRACK does not by itself lock on", not locks)
        page.mouse.click(box["x"] + box["width"] * 0.6,
                         box["y"] + box["height"] * 0.55)
        page.wait_for_timeout(500)
        locks = [a for a in asked if a.startswith("/payload_lock")]
        check("then a click locks on (%s)" % (locks[:1] or "none"), locks)
        check("and it sends where in the frame was clicked",
              locks and "u=0.1" in locks[0] and "v=0.0" in locks[0])
        check("the strip now offers UNLOCK",
              page.inner_text("#pay-track").strip() == "UNLOCK")

        page.click("#pay-record")
        page.wait_for_timeout(400)
        check("record starts", any(a.startswith("/payload_record?on=1")
                                   for a in asked))
        check("and the button says so",
              "REC" in page.inner_text("#pay-record"))

        check("the strip says the picture is stabilised",
              "on" in (page.get_attribute("#pay-stab", "class") or ""))
        page.click("#pay-stab")
        page.wait_for_timeout(300)
        check("and stabilisation can be switched off",
              fake["stabilised"] is False
              and "on" not in (page.get_attribute("#pay-stab", "class") or ""))
        page.click("#pay-stab")
        page.wait_for_timeout(300)

        page.click('#paybar button[data-pay="lase"]')
        page.wait_for_timeout(300)
        check("the rangefinder can be fired",
              any(a.startswith("/payload_lase") for a in asked))
        check("the readout shows pan, tilt and range (%s)"
              % page.inner_text("#pay-read")[:60],
              "PAN" in page.inner_text("#pay-read")
              and "RNG" in page.inner_text("#pay-read"))

        print("10. the rest of the reorganised console")
        page.click('#viewtabs button[data-view="chase"]')
        page.wait_for_timeout(400)
        check("the chase view has its angle buttons",
              page.locator("#chasebar button").count() >= 4)
        page.click('#chasebar button[data-chase="starboard"]')
        page.wait_for_timeout(400)
        check("choosing one marks it",
              "on" in (page.get_attribute('#chasebar button[data-chase="starboard"]',
                                          "class") or ""))

        page.evaluate("() => document.getElementById('settings-open').click()")
        page.wait_for_timeout(300)
        check("settings opens", page.locator("#win-settings").is_visible())
        check("it has categories down the side",
              page.locator("#set-tabs button").count() >= 5)
        page.click('#set-tabs button[data-tab="environment"]')
        page.wait_for_timeout(200)
        check("choosing one shows that pane",
              page.locator('.set-pane[data-pane="environment"]').is_visible())
        check("and the environment controls are in it",
              page.locator('.set-pane[data-pane="environment"] #btn-environment')
              .count() == 1)
        check("the display pane is hidden while it is",
              not page.locator('.set-pane[data-pane="display"]').is_visible())

        # The settings icon has to be the last thing on the bar.
        right_edge = page.evaluate("""() => {
            const b = document.getElementById('settings-open');
            const bar = document.getElementById('topbar');
            const r = b.getBoundingClientRect(), t = bar.getBoundingClientRect();
            const others = [...bar.querySelectorAll('button, .item, .badge')]
              .filter(e => e !== b)
              .map(e => e.getBoundingClientRect().right);
            return { gap: Math.round(t.right - r.right),
                     last: r.right >= Math.max(...others) - 1 };
        }""")
        check("the menu icon is the last thing on the bar", right_edge["last"])
        check("and sits against the right edge (%s px)" % right_edge["gap"],
              right_edge["gap"] < 30)

        page.evaluate("() => document.querySelector('[data-open-win=\"flightlog\"]').click()")
        page.wait_for_timeout(600)
        check("the flight log opens", page.locator("#win-flightlog").is_visible())
        check("and says where the flights are written",
              "track.csv" in page.inner_text("#fl-foot"))

        print("11. nothing was lost in the reorganisation")
        # The point of this section: the rails were emptied into the
        # settings window, and a control that quietly stopped existing
        # would look exactly like a control that moved.
        import instructor_station as station
        spare = station.unplaced_controls()
        check("every control is placed somewhere (%s)" % (spare or "none"),
              not spare)

        def reachable(pid):
            # Most controls are a button. The motor tests are the
            # propellers on the aircraft diagram instead - clicking the
            # motor you want to test was the instruction - so they are
            # reachable through the diagram, not through a button.
            return (page.locator("#btn-" + pid).count() >= 1
                    or page.locator('[data-motor="%s"]' % pid).count() >= 1)

        missing = [p["id"] for p in station.plugins if not reachable(p["id"])]
        check("every control is reachable on the page (%s)"
              % (missing or "all present"), not missing)

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
