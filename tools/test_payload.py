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
# THE BOOM STARTS WHERE THE CONSOLE SAYS. The console shows Behind
# highlighted from the first frame, so if the opening angle is not the
# Behind angle, the view is wrong and no instructor would think to press
# an already-lit button. That is exactly what happened on 12 Oct 2026:
# the state said 7.0 while the preset said 17.0.
check("the boom starts at the Behind preset, not some other angle",
      (gimbal.chase["az_deg"], gimbal.chase["el_deg"])
      == gimbal.CHASE_PRESETS["behind"])
check("and the console is told whether the command went out",
      "sent" in gimbal.chase_status())

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

print("8b. the external view's angle, and that it survives a restart")
# Added 13 Oct 2026. Settings > Aircraft sets the chase view's elevation in
# degrees and LOCKS it, which has to mean the next session opens at it. The
# failure that matters is silent: a locked angle that is written but never
# read back leaves an instructor setting it again every morning and
# assuming they forgot.
import contextlib                                           # noqa: E402
import io                                                   # noqa: E402
import json as _json                                        # noqa: E402

_was = gimbal.CHASE_PRESETS["behind"]
check("the boom's travel is one pair of figures, not two",
      (gimbal.CHASE_EL_MIN, gimbal.CHASE_EL_MAX) == (-28.0, 83.0))
check("setting the angle moves only the Behind view",
      gimbal.set_behind_elevation(40) == 40.0
      and gimbal.CHASE_PRESETS["behind"] == (0.0, 40.0)
      and gimbal.CHASE_PRESETS["top"] == (0.0, 60.0))
check("an angle past the joint's reach is clamped, not refused",
      gimbal.set_behind_elevation(900) == gimbal.CHASE_EL_MAX
      and gimbal.set_behind_elevation(-900) == gimbal.CHASE_EL_MIN)
gimbal.CHASE_PRESETS["behind"] = _was

with contextlib.redirect_stdout(io.StringIO()):
    import instructor_station as _st                         # noqa: E402
_real_layout = _st.LAYOUT_FILE
_tmp = tempfile.mkdtemp()
_st.LAYOUT_FILE = os.path.join(_tmp, "gcs_layout.json")
try:
    check("with nothing saved, no angle is locked",
          _st.read_prefs()["view_angle_deg"] is None
          and _st.apply_saved_prefs() is None)

    _st.write_prefs({"view_angle_deg": 35.0})
    check("a locked angle is read back as it was written",
          _st.read_prefs()["view_angle_deg"] == 35.0)

    # Clamped on the way IN as well as out: the file is on disk and can be
    # edited by hand, and a boom told to go to 500 degrees would sit at its
    # stop with the console claiming otherwise.
    _st.write_prefs({"view_angle_deg": 500.0})
    check("an impossible angle in the file is clamped on the way back in",
          _st.read_prefs()["view_angle_deg"] == gimbal.CHASE_EL_MAX)

    _st.write_prefs({"view_angle_deg": 41.0})
    check("start-up applies the locked angle to the Behind view",
          _st.apply_saved_prefs() == 41.0
          and gimbal.CHASE_PRESETS["behind"] == (0.0, 41.0))
    check("and leaves the other views alone",
          gimbal.CHASE_PRESETS["top"] == (0.0, 60.0)
          and gimbal.CHASE_PRESETS["low"] == (0.0, -14.0))

    # The layout and the preferences share one file. Saving either must not
    # wipe the other, which is the obvious way this breaks later.
    _st.write_console_layout({"hero": "nose",
                              "windows": {"chasebar": {"x": 300, "y": 200}}})
    _saved = _json.load(open(_st.LAYOUT_FILE))
    check("saving a layout does not wipe the locked angle",
          _saved["prefs"]["view_angle_deg"] == 41.0)
    check("and the external view strip's position is saved with it",
          _saved["console"]["windows"].get("chasebar") == {"x": 300, "y": 200})
    _st.write_prefs({"view_angle_deg": 12.0})
    check("and saving the angle does not wipe the layout",
          _json.load(open(_st.LAYOUT_FILE))["console"]["hero"] == "nose")

    # A corrupt file must not stop the station starting. It is written on
    # every drag, so a power cut mid-write is not far-fetched.
    with open(_st.LAYOUT_FILE, "w") as _h:
        _h.write("{ not json")
    check("a corrupt file reads as no angle rather than throwing",
          _st.read_prefs()["view_angle_deg"] is None)
finally:
    _st.LAYOUT_FILE = _real_layout
    gimbal.CHASE_PRESETS["behind"] = _was
    shutil.rmtree(_tmp, ignore_errors=True)

print("8c. the fuselage colour, and that it survives a restart")
# Added 13 Oct 2026. Two schemes, chosen from the console while the
# aircraft flies - Gazebo recolours a visual at runtime, so this needs no
# restart - and LOCK means the next session starts in that colour.
import aircraft_livery                                      # noqa: E402

check("there are exactly the two schemes asked for (%s)"
      % ", ".join(sorted(aircraft_livery.SCHEMES)),
      set(aircraft_livery.SCHEMES) == {"sar", "grey"})
check("the orange one is the search-and-rescue scheme",
      "Search and Rescue" in aircraft_livery.SCHEMES["sar"]["label"])
# The visual has to be scoped model::link::visual or gz silently recolours
# nothing - there is no error for a name that matches no entity.
check("the fuselage visual is scoped the way gz needs (%s)"
      % aircraft_livery.AIRFRAME_VISUAL,
      aircraft_livery.AIRFRAME_VISUAL
      == "%s::base_link::base_link_visual" % sim_target.MODEL)

_sent = []
_real_publish = aircraft_livery._publish
aircraft_livery._publish = lambda rgb: _sent.append(rgb) or True
try:
    ok, _ = aircraft_livery.set_scheme("grey")
    check("choosing grey sends the grey colour",
          ok and _sent and _sent[-1] == aircraft_livery.SCHEMES["grey"]["rgb"])
    ok, message = aircraft_livery.set_scheme("tartan")
    check("an unknown scheme is refused, and says what is on offer",
          not ok and "sar" in message and "grey" in message)
    _sent.clear()
    aircraft_livery.reapply()
    check("and a world switch puts the chosen colour back on",
          _sent == [aircraft_livery.SCHEMES["grey"]["rgb"]])
finally:
    aircraft_livery._publish = _real_publish
    aircraft_livery.state["scheme"] = aircraft_livery.DEFAULT

_real_layout2 = _st.LAYOUT_FILE
_tmp2 = tempfile.mkdtemp()
_st.LAYOUT_FILE = os.path.join(_tmp2, "gcs_layout.json")
try:
    _st.write_prefs({"livery": "grey"})
    check("a locked livery is read back", _st.read_prefs()["livery"] == "grey")
    # Checked against the list, because the file can be hand-edited and an
    # unknown name would leave the console claiming a colour nobody has.
    _st.write_prefs({"livery": "tartan"})
    check("an unknown one in the file is ignored rather than trusted",
          _st.read_prefs()["livery"] is None)
    _st.write_prefs({"livery": "sar", "view_angle_deg": 30.0})
    check("the livery and the view angle do not overwrite each other",
          _st.read_prefs()["livery"] == "sar"
          and _st.read_prefs()["view_angle_deg"] == 30.0)
finally:
    _st.LAYOUT_FILE = _real_layout2
    shutil.rmtree(_tmp2, ignore_errors=True)

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
                body = json.dumps({"az_deg": 0.0, "el_deg": 17.0,
                                   "sent": True,
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
        # The categories go DOWN THE SIDE of the panes, not above them.
        # A leftover "flex-direction: column" from the single-column
        # version of this window came later in the stylesheet and won,
        # which stacked them and left 200 px of empty window above the
        # first setting.
        side = page.evaluate("""() => {
            const t = document.querySelector('.set-tabs').getBoundingClientRect();
            const p = document.querySelector('.set-panes').getBoundingClientRect();
            const first = document.querySelector('.set-pane.on .group, .set-pane.on .set-row');
            return { sideBySide: p.left >= t.right - 1,
                     sameTop: Math.abs(p.top - t.top) < 4,
                     gapAbove: Math.round(first.getBoundingClientRect().top - p.top) };
        }""")
        check("the categories are beside the panes, not above them",
              side["sideBySide"] and side["sameTop"])
        check("so the first setting is at the top of the pane (%s px down)"
              % side["gapAbove"], side["gapAbove"] < 30)

        # The settings icon has to be at the END of the bar - the decision
        # of 12 Oct 2026, where DJI puts it. From 13 Oct the close X sits
        # outside it, because that is where every application keeps close
        # and an instructor reaching for it should not have to look. So the
        # rule is now "last but one, and still hard against the edge"
        # rather than "last".
        right_edge = page.evaluate("""() => {
            const b = document.getElementById('settings-open');
            const x = document.getElementById('exit-open');
            const bar = document.getElementById('topbar');
            const r = b.getBoundingClientRect(), t = bar.getBoundingClientRect();
            const xr = x ? x.getBoundingClientRect() : null;
            const others = [...bar.querySelectorAll('button, .item, .badge')]
              .filter(e => e !== b && e !== x)
              .map(e => e.getBoundingClientRect().right);
            return { gap: Math.round(t.right - r.right),
                     lastButOne: r.right >= Math.max(...others) - 1,
                     xIsLast: !!xr && xr.right >= r.right,
                     xGap: xr ? Math.round(t.right - xr.right) : null };
        }""")
        check("the menu icon is the last thing on the bar bar the close X",
              right_edge["lastButOne"])
        check("the close X is the very last, as in any application",
              right_edge["xIsLast"])
        check("and both sit against the right edge (%s px, %s px)"
              % (right_edge["gap"], right_edge["xGap"]),
              right_edge["gap"] < 80 and right_edge["xGap"] < 30)

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

        print("12. the external view's angle, on the page")
        # Added 13 Oct 2026. The arrows and the lock live in Settings >
        # Aircraft; the figures they clamp to are the boom joint's own
        # travel, and a console that let an instructor wind past it would
        # show an angle the camera was never at.
        check("the angle control is in the Aircraft tab, not loose on the page",
              page.locator('.set-pane[data-pane="aircraft"] #angle-read').count() == 1)
        # And it is reached the way an instructor reaches it: the gear, then
        # the Aircraft tab. Hidden until then is correct, not a fault.
        check("it is not on screen until the Aircraft tab is chosen",
              not page.locator("#angle-up").is_visible())
        page.locator("#settings-open").click()
        page.locator('#set-tabs button[data-tab="aircraft"]').click()
        check("the gear and the Aircraft tab bring it up",
              page.locator("#angle-up").is_visible())

        def angle_now():
            return page.locator("#angle-read").inner_text().replace("°", "")

        start = angle_now()
        page.locator("#angle-up").click()
        page.locator("#angle-up").click()
        check("two presses of the up arrow raise it (%s -> %s)"
              % (start, angle_now()), float(angle_now()) == float(start) + 4)
        page.locator("#angle-down").click()
        check("and the down arrow lowers it again (%s)" % angle_now(),
              float(angle_now()) == float(start) + 2)

        def hold(which, limit=120):
            """Press an arrow until it goes dead, as holding it down would."""
            for _ in range(limit):
                if page.locator(which).is_disabled():
                    return True
                page.locator(which).click()
            return False

        check("the up arrow eventually goes dead rather than running on",
              hold("#angle-up"))
        check("it stops at the top of the boom's reach (%s)" % angle_now(),
              float(angle_now()) == gimbal.CHASE_EL_MAX)
        check("and the arrow goes dead there rather than doing nothing quietly",
              page.locator("#angle-up").is_disabled())
        check("the down arrow does the same the other way", hold("#angle-down"))
        check("and at the bottom of it (%s)" % angle_now(),
              float(angle_now()) == gimbal.CHASE_EL_MIN)
        check("with the other arrow dead",
              page.locator("#angle-down").is_disabled())

        print("13. the wheel over the height tape")
        # The tape is painted on a canvas, so the live area is a rectangle
        # rather than an element. It is hit-tested against the figures the
        # gauge actually drew with, which is the only way it can stay on
        # the tape after the instructor drags a corner tile over it.
        rects = page.evaluate("window.gcsTapes ? window.gcsTapes('canvas.hud') : null")
        check("the gauge publishes where it drew the tapes", bool(rects and rects.get("alt")))
        if rects and rects.get("alt"):
            probe = """(r) => {
              const cv = document.querySelector('canvas.hud');
              const box = cv.getBoundingClientRect();
              const sx = box.width / (cv.cssW || box.width);
              const sy = box.height / (cv.cssH || box.height);
              const mid = (a) => [box.left + ((a.left + a.right) / 2) * sx,
                                  box.top + ((a.top + a.bottom) / 2) * sy];
              const out = {};
              out.onAlt = window.gcsAltWheel('canvas.hud', ...mid(r.alt)).hit;
              out.onSpeed = window.gcsAltWheel('canvas.hud', ...mid(r.speed)).hit;
              out.offTape = window.gcsAltWheel('canvas.hud', box.left + 4,
                                               box.top + 4).hit;
              const [x, y] = mid(r.alt);
              const spin = (n, d) => { for (let i = 0; i < n; i++) {
                cv.dispatchEvent(new WheelEvent('wheel', {deltaY: d, clientX: x,
                  clientY: y, bubbles: true, cancelable: true})); } };
              // The wheel counts from where the aircraft actually IS, not
              // from zero - otherwise the first notch commands a dive to
              // 5 m from whatever height it is at.
              const step0 = window.gcsAltWheel('canvas.hud', x, y).step;
              const nowAlt = (window.gcsTelemetry || {}).altitude_m || 0;
              out.base = Math.round(nowAlt / step0) * step0;
              spin(3, -100);
              out.afterThreeUp = window.gcsAltWheel('canvas.hud', x, y).pending;
              spin(1, 100);
              out.afterOneDown = window.gcsAltWheel('canvas.hud', x, y).pending;
              spin(80, 100);
              out.floor = window.gcsAltWheel('canvas.hud', x, y).pending;
              spin(120, -100);
              out.ceiling = window.gcsAltWheel('canvas.hud', x, y).pending;
              const ev = new WheelEvent('wheel', {deltaY: -100, clientX: x,
                clientY: y, bubbles: true, cancelable: true});
              cv.dispatchEvent(ev);
              out.consumed = ev.defaultPrevented;
              const limits = window.gcsAltWheel('canvas.hud', x, y);
              out.step = limits.step; out.min = limits.min; out.max = limits.max;
              return out;
            }"""
            w = page.evaluate(probe, rects)
            check("the height tape takes the wheel", w["onAlt"])
            check("the speed tape does not", not w["onSpeed"])
            check("and neither does the rest of the picture", not w["offTape"])
            check("it counts from the height the aircraft is at (%s m)"
                  % w["base"], w["base"] is not None)
            check("three notches up is three steps above that (%s m)"
                  % w["afterThreeUp"],
                  w["afterThreeUp"] == w["base"] + 3 * w["step"])
            check("one back down is one step less (%s m)" % w["afterOneDown"],
                  w["afterOneDown"] == w["base"] + 2 * w["step"])
            check("it cannot be wound below the floor (%s m)" % w["floor"],
                  w["floor"] == w["min"])
            check("nor above the ceiling (%s m)" % w["ceiling"],
                  w["ceiling"] == w["max"])
            # Without this the console scrolls under the pointer while the
            # instructor is changing height, which moves the tape itself.
            check("and the page does not scroll underneath it", w["consumed"])

        print("14. every container can be dragged, and is remembered")
        # The rails, the corner tiles and the pop-up panels could all be
        # moved and remembered. The external view strip was the one left
        # nailed to the picture.
        moved = page.evaluate("""() => {
          const strip = document.getElementById('chasebar');
          if (!strip) { return {missing: true}; }
          const h = strip.querySelector('.striphandle');
          if (!h) { return {noHandle: true}; }
          const b0 = strip.getBoundingClientRect();
          h.dispatchEvent(new MouseEvent('mousedown', {clientX: b0.left + 5,
            clientY: b0.top + 5, bubbles: true, cancelable: true}));
          document.dispatchEvent(new MouseEvent('mousemove',
            {clientX: b0.left + 205, clientY: b0.top + 155, bubbles: true}));
          const b1 = strip.getBoundingClientRect();
          document.dispatchEvent(new MouseEvent('mouseup', {bubbles: true}));
          return { dx: Math.round(b1.left - b0.left),
                   dy: Math.round(b1.top - b0.top),
                   floating: strip.classList.contains('floating'),
                   stillDragging: strip.classList.contains('dragging'),
                   mask: getComputedStyle(
                     document.getElementById('dragmask')).display,
                   buttonsIntact: strip.querySelectorAll('button[data-chase]').length };
        }""")
        check("the external view strip has a grip to drag it by",
              not moved.get("missing") and not moved.get("noHandle"))
        # A strip that jumps on the first grab is the symptom of being
        # positioned against the view and then dragged against the window.
        check("it follows the mouse exactly rather than jumping (%s, %s)"
              % (moved.get("dx"), moved.get("dy")),
              moved.get("dx") == 200 and moved.get("dy") == 150)
        check("it is fixed to the window, not to a view that moves into a tile",
              moved.get("floating"))
        check("the drag ends cleanly", not moved.get("stillDragging"))
        # The mask sits at z-index 60 over everything; left up, the whole
        # console stops taking clicks.
        check("and the drag mask comes back down", moved.get("mask") == "none")
        check("and its view buttons survive the drag (%s)"
              % moved.get("buttonsIntact"), moved.get("buttonsIntact") == 6)

        browser.close()
    server.shutdown()


browser_checks()

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)

# os._exit, NOT sys.exit. This file imports gimbal, which loads the Gazebo
# python bindings, and those keep a background thread. On interpreter
# shutdown that thread sometimes releases an object without the GIL and
# pybind11 aborts the process - measured 13 Oct 2026, two runs in three,
# every one of them AFTER every check had passed and been printed. An exit
# code of 134 on a run with no failures reads as "the tests are broken",
# which is worse than the race it comes from. The result is already decided
# here, so leave without running the interpreter's teardown.
sys.stdout.flush()
if not fails:
    print("All checks passed.")
    sys.stdout.flush()
os._exit(1 if fails else 0)
