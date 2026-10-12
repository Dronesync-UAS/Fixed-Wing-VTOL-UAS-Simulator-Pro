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

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
