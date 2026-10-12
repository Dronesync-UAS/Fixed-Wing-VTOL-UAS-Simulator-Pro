"""Puts the chase camera on a boom so it can be swung round the aircraft:

    python3 tools/chase_angles_apply.py            # convert it
    python3 tools/chase_angles_apply.py --dry-run  # show the change
    python3 tools/chase_angles_apply.py --revert   # put the backup back

THE PROBLEM THIS SOLVES
-----------------------
tools/chase_camera_apply.py bolts one camera nine metres behind the
aircraft. That is the right default and the wrong only option: an
instructor wants to see a transition from the side, a landing from the
front, and a circuit from above. Four more cameras would be four more
things for this machine to render, and its graphics were already called
marginal in the 12 July entry.

So instead the ONE camera goes on a two-axis boom, and the view is
changed by moving the boom. Nothing extra is rendered.

WHAT IT BUILDS
--------------
    base_link
      +-- chase_az_joint   revolute about Z  -> chase_az_link
            +-- chase_el_joint  revolute about Y -> chase_el_link
                  +-- chase_camera   moved here from base_link

The camera sits at x = -9 on the elevation link and looks along its own
+X, which is straight back at the aircraft. Both links have their centre
of mass on the aircraft's own origin, so neither joint has to hold
anything up and the boom cannot swing under gravity.

HOW THE ANGLES COME OUT
-----------------------
Working in the model's FLU frame - x forward, y LEFT, z up:

  * azimuth 0 leaves the camera behind the aircraft;
  * azimuth +90 rotates (-9, 0, 0) to (0, -9, 0), which is off the
    STARBOARD wing, looking back at the aircraft. So +90 is the view from
    the right and -90 the view from the left. That is the one worth
    writing down, because the sign is the opposite of what "+ is left"
    suggests;
  * azimuth 180 puts it ahead of the aircraft, looking back at the nose;
  * elevation +theta lifts the camera to (-9cos, 0, +9sin) and tilts its
    look direction down by the same angle, so it keeps pointing at the
    aircraft. +0.24 rad reproduces the old fixed camera almost exactly
    (nine back, 2.2 up, pitched down 0.24), which is why that is the
    default.

The station's presets are in instructor_station.CHASE_ANGLES.

BOTH TOPICS STAY ALIVE
----------------------
Moving the sensor changes the topic it publishes on, because a Gazebo
camera topic has its link name in it. Rather than make this tool
compulsory, the station subscribes to BOTH the old base_link topic and
the new boom topic; whichever one has a publisher is the one that
delivers. So a machine that has not run this tool keeps the fixed chase
view and simply has no angle buttons that do anything.

NOT YET SEEN RUNNING.
"""
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

MODEL = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SUFFIX = ".prechaseboom"
LINK = "base_link"

AZ_LINK, EL_LINK = sim_target.CHASE_BOOM_LINKS
AZ_JOINT, EL_JOINT = sim_target.CHASE_BOOM_JOINTS
SENSOR = sim_target.CHASE_CAMERA[1]

BOOM_M = 9.0            # how far back the camera sits, as before

BLOCK = """\
{i}<!-- CHASE BOOM, added by tools/chase_angles_apply.py. The chase camera
{i}     moved onto a two-axis boom so the external view can be swung round
{i}     the aircraft without rendering a second camera. Azimuth +90 puts it
{i}     off the STARBOARD wing; elevation + lifts it and tilts it down.
{i}     Both links have their mass on the aircraft's own origin, so neither
{i}     joint carries a load. -->
{i}<link name="{az_link}">
{i}  <pose>0 0 0 0 0 0</pose>
{i}  <inertial>
{i}    <mass>0.001</mass>
{i}    <inertia><ixx>1e-06</ixx><ixy>0</ixy><ixz>0</ixz>
{i}      <iyy>1e-06</iyy><iyz>0</iyz><izz>1e-06</izz></inertia>
{i}  </inertial>
{i}</link>
{i}<joint name="{az_joint}" type="revolute">
{i}  <parent>{parent}</parent>
{i}  <child>{az_link}</child>
{i}  <axis><xyz>0 0 1</xyz>
{i}    <limit><lower>-3.14159</lower><upper>3.14159</upper>
{i}      <effort>0.2</effort><velocity>2.0</velocity></limit>
{i}    <dynamics><damping>0.0002</damping></dynamics>
{i}  </axis>
{i}</joint>
{i}<link name="{el_link}">
{i}  <pose>0 0 0 0 0 0</pose>
{i}  <inertial>
{i}    <mass>0.001</mass>
{i}    <inertia><ixx>1e-06</ixx><ixy>0</ixy><ixz>0</ixz>
{i}      <iyy>1e-06</iyy><iyz>0</iyz><izz>1e-06</izz></inertia>
{i}  </inertial>
{i}  <sensor name="{sensor}" type="camera">
{i}    <gz_frame_id>{el_link}</gz_frame_id>
{i}    <pose>{back} 0 0 0 0 0</pose>
{i}    <camera>
{i}      <horizontal_fov>1.2</horizontal_fov>
{i}      <image><width>1600</width><height>900</height></image>
{i}      <clip><near>0.1</near><far>8000</far></clip>
{i}    </camera>
{i}    <always_on>1</always_on>
{i}    <update_rate>15</update_rate>
{i}    <visualize>false</visualize>
{i}  </sensor>
{i}</link>
{i}<joint name="{el_joint}" type="revolute">
{i}  <parent>{az_link}</parent>
{i}  <child>{el_link}</child>
{i}  <axis><xyz>0 1 0</xyz>
{i}    <limit><lower>-0.5</lower><upper>1.45</upper>
{i}      <effort>0.2</effort><velocity>2.0</velocity></limit>
{i}    <dynamics><damping>0.0002</damping></dynamics>
{i}  </axis>
{i}</joint>
"""

PLUGINS = """\
{i}<!-- One position controller per boom axis, on the gz-sim 8 default
{i}     cmd_pos topic. No <sub_topic>: the servo controllers in this file
{i}     carry one, and copying it here would take the boom off the topic
{i}     the station publishes to. Gains sized to the 1e-06 inertia above:
{i}     P = I wn^2 and D = 2 I wn at wn = 8 rad/s, which is a swing that
{i}     takes about half a second and does not overshoot. -->
{i}<plugin filename="gz-sim-joint-position-controller-system"
{i}        name="gz::sim::systems::JointPositionController">
{i}  <joint_name>{az_joint}</joint_name>
{i}  <p_gain>6.4e-05</p_gain><i_gain>2e-06</i_gain><d_gain>1.6e-05</d_gain>
{i}  <cmd_max>0.01</cmd_max><cmd_min>-0.01</cmd_min>
{i}</plugin>
{i}<plugin filename="gz-sim-joint-position-controller-system"
{i}        name="gz::sim::systems::JointPositionController">
{i}  <joint_name>{el_joint}</joint_name>
{i}  <p_gain>6.4e-05</p_gain><i_gain>2e-06</i_gain><d_gain>1.6e-05</d_gain>
{i}  <cmd_max>0.01</cmd_max><cmd_min>-0.01</cmd_min>
{i}</plugin>
"""


def find_link_end(lines, name=LINK):
    opening = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("<link") and (
                'name="%s"' % name in stripped or "name='%s'" % name in stripped):
            opening = number
            break
    if opening is None:
        return None, 'no <link name="%s"> found' % name
    for number in range(opening + 1, len(lines)):
        if lines[number].strip() == "</link>":
            return number, None
    return None, "the %s link is never closed" % name


def find_model_end(lines):
    for number in range(len(lines) - 1, -1, -1):
        if lines[number].strip() == "</model>":
            return number, None
    return None, "no </model> found"


def strip_sensor(lines, name):
    """Remove a <sensor name="..."> block wherever it is. Returns True if
    one was found. Sensors do not nest, so the first </sensor> closes it."""
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("<sensor") and (
                'name="%s"' % name in stripped or "name='%s'" % name in stripped):
            for close in range(number + 1, len(lines)):
                if lines[close].strip() == "</sensor>":
                    del lines[number:close + 1]
                    return True
            return False
    return False


def block(indent):
    return BLOCK.format(i=indent, parent=LINK, az_link=AZ_LINK,
                        el_link=EL_LINK, az_joint=AZ_JOINT, el_joint=EL_JOINT,
                        sensor=SENSOR, back=-BOOM_M)


def plugins(indent):
    return PLUGINS.format(i=indent, az_joint=AZ_JOINT, el_joint=EL_JOINT)


def revert():
    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        print("No %s backup found - nothing to restore." % SUFFIX)
        return 0
    shutil.copy2(backup, MODEL)
    print("Restored %s from its backup." % MODEL)
    print("Restart the simulator for it to take effect.")
    return 0


def apply(dry_run):
    if not os.path.isfile(MODEL):
        print("Aircraft model not found: %s" % MODEL, file=sys.stderr)
        return 1
    with open(MODEL) as handle:
        lines = handle.read().splitlines(keepends=True)

    if 'name="%s"' % EL_LINK in "".join(lines):
        print("SKIP  the chase camera is already on a boom.")
        return 0

    moved = strip_sensor(lines, SENSOR)

    close, problem = find_link_end(lines)
    if close is None:
        print("Cannot add the boom - %s in %s" % (problem, MODEL), file=sys.stderr)
        return 1
    indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())]
    lines = lines[:close + 1] + [block(indent)] + lines[close + 1:]

    end, problem = find_model_end(lines)
    if end is None:
        print("Cannot add the controllers - %s" % problem, file=sys.stderr)
        return 1
    lines = lines[:end] + [plugins(indent)] + lines[end:]

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        print("  %s the existing %s sensor"
              % ("move" if moved else "add (none found to move):", SENSOR))
        print("  add links  %s, %s" % (AZ_LINK, EL_LINK))
        print("  add joints %s (Z), %s (Y)" % (AZ_JOINT, EL_JOINT))
        print("  camera %g m behind on the boom" % BOOM_M)
        print("\nDry run - nothing written.")
        return 0

    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(MODEL, backup)
    with open(MODEL, "w") as handle:
        handle.writelines(lines)
    try:
        ET.parse(MODEL)
    except ET.ParseError as exc:
        shutil.copy2(backup, MODEL)
        print("FAILED: the edit broke the XML (%s) - restored from backup."
              % exc, file=sys.stderr)
        return 1

    print("OK    the chase camera is now on a boom in %s" % MODEL)
    if not moved:
        print("      note: no existing %s sensor was found, so a new one was"
              % SENSOR)
        print("      created on the boom. That is fine - it is the same camera.")
    print("      backup at %s" % os.path.basename(backup))
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. In the console, choose the Chase view. The angle buttons appear
   across the bottom of the picture.

To put the camera back where it was:
     python3 tools/chase_angles_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
