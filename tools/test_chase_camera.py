"""Check the chase camera end to end, short of Gazebo rendering it.

    python3 tools/test_chase_camera.py

Covers the two halves that can be wrong independently: the model edit
(tools/chase_camera_apply.py, run against a copy of a real standard_vtol
model.sdf) and the topic the station subscribes to. Those are joined only by
sim_target.CHASE_CAMERA holding the link and sensor names, so a rename on
one side fails silently - the panel just shows nothing - which is exactly
the kind of fault worth a test.

What it cannot prove: that Gazebo renders the camera, or what it costs in
frame rate. That needs the simulator.
"""
import importlib.util
import os
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

spec = importlib.util.spec_from_file_location(
    "chase_camera_apply", os.path.join(REPO, "tools", "chase_camera_apply.py"))
CC = importlib.util.module_from_spec(spec)
spec.loader.exec_module(CC)

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


# A stand-in for PX4's model: the parts this tool actually navigates, with
# the awkward bits real files have - single quotes on the link, a nested
# sensor, and a </link> that is not the first one in the file.
MODEL_XML = """<?xml version="1.0"?>
<sdf version='1.9'>
  <model name='standard_vtol'>
    <link name='base_link'>
      <inertial><mass>5.4</mass></inertial>
      <sensor name="imu_sensor" type="imu">
        <gz_frame_id>base_link</gz_frame_id>
      </sensor>
    </link>
    <link name='rotor_0'>
      <inertial><mass>0.01</mass></inertial>
    </link>
  </model>
</sdf>
"""

with tempfile.TemporaryDirectory() as tmp:
    model = os.path.join(tmp, "model.sdf")
    with open(model, "w") as handle:
        handle.write(MODEL_XML)
    CC.MODEL = model

    print("1. a dry run writes nothing")
    before = open(model).read()
    CC.apply(dry_run=True)
    check("file untouched", open(model).read() == before)
    check("no backup made", not os.path.exists(model + CC.SUFFIX))

    print("2. the sensor lands inside base_link, not another link")
    check("applied", CC.apply(dry_run=False) == 0)
    tree = ET.parse(model)
    links = {link.get("name"): link for link in tree.iter("link")}
    sensors = {s.get("name"): s for s in links["base_link"].findall("sensor")}
    check("sensor is in base_link", sim_target.CHASE_CAMERA[1] in sensors)
    check("rotor_0 untouched", not links["rotor_0"].findall("sensor"))
    check("the existing imu sensor survived", "imu_sensor" in sensors)

    print("3. the camera is aimed at the aircraft, not at the sky")
    camera = sensors[sim_target.CHASE_CAMERA[1]]
    pose = [float(v) for v in camera.findtext("pose").split()]
    back, up, pitch = -pose[0], pose[2], pose[4]
    check("behind the aircraft (%.1f m)" % back, back > 0)
    check("above it (%.1f m)" % up, up > 0)
    # The camera looks along its own +X, so being raised means it has to be
    # pitched down by the same angle or the aircraft sits near the top edge.
    import math
    wanted = math.atan2(up, back)
    check("pitched down to match the height (%.3f vs %.3f rad)"
          % (pitch, wanted), abs(pitch - wanted) < 0.05)
    far = float(camera.findtext("./camera/clip/far"))
    check("sees past the 500 m operating limit (%.0f m)" % far, far > 500)

    print("4. it is the cheap camera it claims to be")
    width = int(camera.findtext("./camera/image/width"))
    rate = float(camera.findtext("update_rate"))
    # Cost, not pixels, is the thing to hold: megapixels a second against the
    # nose camera's 1280x960 at 30, which this machine already runs.
    height = int(camera.findtext("./camera/image/height"))
    load = width * height * rate
    check("cheaper than the nose camera (%.1f vs 36.9 Mpx/s)" % (load / 1e6),
          load < 1280 * 960 * 30)
    check("slow (%.0f Hz)" % rate, rate <= 20)

    print("5. the station would subscribe to exactly what this publishes")
    link_name = "base_link"
    expected = "/world/%s/model/%s/link/%s/sensor/%s/image" % (
        sim_target.WORLD, sim_target.MODEL, link_name, camera.get("name"))
    check("topic matches sim_target.chase_camera_topic()\n          %s"
          % expected, sim_target.chase_camera_topic() == expected)

    print("6. re-running is harmless")
    after_first = open(model).read()
    check("second run skips", CC.apply(dry_run=False) == 0)
    check("file unchanged by the second run", open(model).read() == after_first)

    print("7. revert puts the aircraft back exactly as it was")
    check("reverted", CC.revert() == 0)
    check("byte-identical to the original", open(model).read() == MODEL_XML)

    print("8. a model with no base_link is refused, not half-edited")
    broken = os.path.join(tmp, "nolink.sdf")
    with open(broken, "w") as handle:
        handle.write("<sdf version='1.9'><model name='x'>"
                     "<link name='other'/></model></sdf>\n")
    CC.MODEL = broken
    original = open(broken).read()
    check("refused", CC.apply(dry_run=False) == 1)
    check("left alone", open(broken).read() == original)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
