"""Adds a real two-axis gimbal, with its camera and laser rangefinder:

    python3 tools/gimbal_apply.py            # add it
    python3 tools/gimbal_apply.py --dry-run  # show the change
    python3 tools/gimbal_apply.py --revert   # put the backup back

WHAT THIS REPLACES
------------------
An earlier version of tools/aircraft_legs_apply.py hung three static
shapes under the belly - a yoke, a ball and a lens - so the aircraft
LOOKED like the photographs. They did not move and no picture came out of
them. This tool builds the real thing in their place, and removes those
three shapes if it finds them, so it does not matter which order the two
tools are run in.

WHAT IT BUILDS
--------------
    base_link
      +-- gimbal_yaw_joint    revolute about Z    -> gimbal_yaw_link
            +-- gimbal_pitch_joint  revolute about Y -> gimbal_pitch_link
                  +-- payload_camera   a camera sensor
                  +-- payload_lrf      a single-ray lidar, as the rangefinder

Both joints carry a gz-sim JointPositionController, which listens on
/model/<model>/joint/<joint>/0/cmd_pos for a gz.msgs.Double - the topic
pattern and message type are the ones in the gz-sim 8 (Harmonic)
JointPositionController documentation. gimbal.py in the station publishes
to exactly those two topics; the joint names here are the contract
between the two files, the same way sim_target.CHASE_CAMERA is for the
chase camera.

SIGN CONVENTIONS, WHICH ARE EASY TO GET BACKWARDS
--------------------------------------------------
A camera looks along its own +X.

  * yaw joint, about +Z: rotating by +a turns +X towards +Y, which is
    PORT (left). An operator means right when they say "pan right", so
    the station sends joint = -pan.
  * pitch joint, about +Y: rotating by +b turns +X towards -Z, which is
    DOWN. The station works in a depression angle - 0 at the horizon,
    +90 straight down - so joint = +tilt.

These two sentences are the whole reason the view is not mirrored.

TRAVEL
------
Pan is continuous, +-180 degrees. Tilt runs from 30 degrees above the
horizon to straight down, which is the travel quoted for real UAS EO/IR
balls of this size (-90 to +30 elevation).

WHY THE STATION DRIVES THE JOINTS AND NOT PX4
----------------------------------------------
PX4 does have a gimbal protocol - MNT_MODE_IN / MNT_MODE_OUT and the
MAVLink gimbal manager, per the PX4 v1.15 gimbal control page. Going that
way would mean giving PX4 a gimbal device to manage, configuring the
mount parameters, and having every payload command travel
console -> MAVLink -> PX4 -> gimbal. The station already talks to Gazebo
directly for the lights and the camera feeds, and a joint command on a
topic is one hop with nothing to misconfigure.

The cost, stated plainly: the gimbal is therefore NOT in PX4's view of
the world. It does not appear in a PX4 log, it is not stabilised by PX4,
and a student practising on a real aircraft whose gimbal is driven
through the autopilot will see slightly different behaviour. For teaching
a sensor operator to find, hold and measure a target, that difference
does not change the lesson.

STABILISATION
-------------
There is none in the model. A real ball holds its line while the aircraft
rolls; this one is bolted to the airframe, so the picture moves with the
aircraft. The station compensates instead: in TARGET LOCK it recomputes
the pointing angles from the aircraft's own attitude ten times a second,
which holds the picture on the ground point. In manual pointing it does
not, and the view will move with the aircraft - which is honest about
what an unstabilised mount does, and is called out on screen.

MASS
----
The two links together weigh 40 g against the aircraft's 5 kg - 0.8%.
PX4's controllers are tuned for this airframe's mass, so this is kept
deliberately small. It has not been measured in flight.

NOT YET SEEN RUNNING. Written against the gz-sim 8 documentation and the
aircraft's own model file. Nobody has watched this gimbal move.
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
SUFFIX = ".pregimbal"
LINK = "base_link"

YAW_LINK, PITCH_LINK = sim_target.GIMBAL_LINKS
YAW_JOINT, PITCH_JOINT = sim_target.GIMBAL_JOINTS
CAMERA = sim_target.GIMBAL_CAMERA[1]
LRF_TOPIC = sim_target.LRF_TOPIC

# Where it hangs: amidships between the four landing legs, from the
# photographs. The belly is at z = -0.095 (the model's collision box is at
# -0.07 and 0.05 thick), and the legs' feet are at -0.32, so the ball has
# to live between those two.
MOUNT_X = 0.06
YAW_Z = -0.125           # the top of the mount, just under the belly
BALL_Z = -0.180          # the centre of the ball, and of both camera axes
BALL_R = 0.055

# Travel. Continuous pan; tilt from 30 degrees up to straight down.
PAN_LIMIT = math.pi
TILT_UP = -math.radians(30.0)
TILT_DOWN = math.radians(90.0)

# The picture. Smaller and slower than the nose camera on purpose - this is
# a THIRD rendered camera on a machine whose graphics were already called
# marginal, and the payload view is watched zoomed in, where resolution
# matters less than not dropping frames. 1.05 rad is 60 degrees, a normal
# wide end for an EO ball.
IMAGE_W, IMAGE_H = 1024, 576
IMAGE_HZ = 15
FOV_RAD = 1.05

# The rangefinder. One ray, straight out of the lens. 5 km is beyond
# anything a student will be asked to range in these worlds.
LRF_MIN_M = 1.0
LRF_MAX_M = 5000.0
LRF_HZ = 5

BODY = (0.10, 0.10, 0.11)
LENS = (0.02, 0.02, 0.03)

# The three static shapes the old legs tool used to add. Removed if found.
OLD_VISUALS = ["gimbal_yoke", "gimbal_ball", "gimbal_lens"]


BLOCK = """\
{i}<!-- PAYLOAD GIMBAL, added by tools/gimbal_apply.py.
{i}     Two revolute joints, a camera and a one-ray lidar used as a laser
{i}     rangefinder. Driven from the station over the JointPositionController
{i}     topics below; sim_target holds the same names. A camera looks along
{i}     its own +X, so +yaw points it to PORT and +pitch points it DOWN -
{i}     gimbal.py sends -pan and +tilt accordingly. -->
{i}<link name="{yaw_link}">
{i}  <pose>{mx} 0 {yaw_z} 0 0 0</pose>
{i}  <inertial>
{i}    <mass>0.015</mass>
{i}    <!-- A solid cylinder r=0.018 h=0.05 at 15 g: Izz = mr^2/2 = 2.4e-06,
{i}         Ixx = Iyy = m(3r^2 + h^2)/12 = 4.3e-06. Written out because the
{i}         controller gains below are worked out from these numbers. -->
{i}    <inertia>
{i}      <ixx>4.3e-06</ixx><ixy>0</ixy><ixz>0</ixz>
{i}      <iyy>4.3e-06</iyy><iyz>0</iyz><izz>2.4e-06</izz>
{i}    </inertia>
{i}  </inertial>
{i}  <visual name="gimbal_mount">
{i}    <pose>0 0 0 0 0 0</pose>
{i}    <geometry><cylinder><radius>0.018</radius><length>0.05</length></cylinder></geometry>
{i}    <material>
{i}      <ambient>{br} {bg} {bb} 1</ambient><diffuse>{br} {bg} {bb} 1</diffuse>
{i}    </material>
{i}  </visual>
{i}</link>
{i}<joint name="{yaw_joint}" type="revolute">
{i}  <parent>{parent}</parent>
{i}  <child>{yaw_link}</child>
{i}  <axis>
{i}    <xyz>0 0 1</xyz>
{i}    <limit><lower>{pan_lo}</lower><upper>{pan_hi}</upper>
{i}      <effort>0.2</effort><velocity>2.1</velocity></limit>
{i}    <dynamics><damping>0.0002</damping></dynamics>
{i}  </axis>
{i}</joint>
{i}<link name="{pitch_link}">
{i}  <pose>{mx} 0 {ball_z} 0 0 0</pose>
{i}  <inertial>
{i}    <mass>0.025</mass>
{i}    <!-- A solid sphere r=0.055 at 25 g: I = 2mr^2/5 = 3.0e-05 about every
{i}         axis. Its centre of mass is ON both joint axes, so neither axis
{i}         has to hold the ball up against gravity. -->
{i}    <inertia>
{i}      <ixx>3.0e-05</ixx><ixy>0</ixy><ixz>0</ixz>
{i}      <iyy>3.0e-05</iyy><iyz>0</iyz><izz>3.0e-05</izz>
{i}    </inertia>
{i}  </inertial>
{i}  <visual name="gimbal_ball_body">
{i}    <pose>0 0 0 0 0 0</pose>
{i}    <geometry><sphere><radius>{ball_r}</radius></sphere></geometry>
{i}    <material>
{i}      <ambient>{br} {bg} {bb} 1</ambient><diffuse>{br} {bg} {bb} 1</diffuse>
{i}    </material>
{i}  </visual>
{i}  <visual name="gimbal_ball_lens">
{i}    <pose>{lens_x} 0 0 0 1.5707963 0</pose>
{i}    <geometry><cylinder><radius>0.022</radius><length>0.02</length></cylinder></geometry>
{i}    <material>
{i}      <ambient>{lr} {lg} {lb} 1</ambient><diffuse>{lr} {lg} {lb} 1</diffuse>
{i}    </material>
{i}  </visual>
{i}  <sensor name="{camera}" type="camera">
{i}    <gz_frame_id>{pitch_link}</gz_frame_id>
{i}    <pose>0 0 0 0 0 0</pose>
{i}    <camera>
{i}      <horizontal_fov>{fov}</horizontal_fov>
{i}      <image><width>{iw}</width><height>{ih}</height></image>
{i}      <clip><near>0.1</near><far>8000</far></clip>
{i}    </camera>
{i}    <always_on>1</always_on>
{i}    <update_rate>{ihz}</update_rate>
{i}    <visualize>false</visualize>
{i}  </sensor>
{i}  <sensor name="payload_lrf" type="gpu_lidar">
{i}    <gz_frame_id>{pitch_link}</gz_frame_id>
{i}    <pose>0 0 0 0 0 0</pose>
{i}    <topic>{lrf_topic}</topic>
{i}    <lidar>
{i}      <scan>
{i}        <horizontal><samples>1</samples><resolution>1</resolution>
{i}          <min_angle>0</min_angle><max_angle>0</max_angle></horizontal>
{i}        <vertical><samples>1</samples><resolution>1</resolution>
{i}          <min_angle>0</min_angle><max_angle>0</max_angle></vertical>
{i}      </scan>
{i}      <range><min>{lrf_min}</min><max>{lrf_max}</max><resolution>0.1</resolution></range>
{i}    </lidar>
{i}    <always_on>1</always_on>
{i}    <update_rate>{lrf_hz}</update_rate>
{i}    <visualize>false</visualize>
{i}  </sensor>
{i}</link>
{i}<joint name="{pitch_joint}" type="revolute">
{i}  <parent>{yaw_link}</parent>
{i}  <child>{pitch_link}</child>
{i}  <axis>
{i}    <xyz>0 1 0</xyz>
{i}    <limit><lower>{tilt_lo}</lower><upper>{tilt_hi}</upper>
{i}      <effort>0.2</effort><velocity>2.1</velocity></limit>
{i}    <dynamics><damping>0.0002</damping></dynamics>
{i}  </axis>
{i}</joint>
"""

# The two controllers, which go at MODEL level rather than inside the link.
PLUGINS = """\
{i}<!-- One position controller per gimbal axis. Each listens on
{i}     /model/<model>/joint/<joint>/0/cmd_pos for a gz.msgs.Double, which is
{i}     the gz-sim 8 default for this system - gimbal.py publishes there.
{i}     Note these carry NO <sub_topic>: the servo controllers further down
{i}     this file do, which is what moves them off the default topic, and
{i}     copying that here would have made the gimbal unreachable.
{i}
{i}     THE GAINS ARE WORKED OUT, NOT GUESSED. Both axes carry about
{i}     I = 3e-05 kg m^2 (see the inertia blocks above). For a critically
{i}     damped response at wn = 12 rad/s - a gimbal that settles in about a
{i}     third of a second, which is what a slew feels like -
{i}         P = I wn^2    = 3e-05 * 144 = 0.0043
{i}         D = 2 I wn    = 2 * 3e-05 * 12 = 0.0007
{i}     and the joint damping above adds the rest. The first draft of this
{i}     file used P = 2.2, which against an inertia of 3e-05 is an angular
{i}     acceleration of a hundred thousand radians a second squared: the
{i}     gimbal would have slammed between its stops every timestep. -->
{i}<plugin filename="gz-sim-joint-position-controller-system"
{i}        name="gz::sim::systems::JointPositionController">
{i}  <joint_name>{yaw_joint}</joint_name>
{i}  <p_gain>0.0045</p_gain><i_gain>0.0002</i_gain><d_gain>0.0007</d_gain>
{i}  <cmd_max>0.08</cmd_max><cmd_min>-0.08</cmd_min>
{i}</plugin>
{i}<plugin filename="gz-sim-joint-position-controller-system"
{i}        name="gz::sim::systems::JointPositionController">
{i}  <joint_name>{pitch_joint}</joint_name>
{i}  <p_gain>0.0045</p_gain><i_gain>0.0002</i_gain><d_gain>0.0007</d_gain>
{i}  <cmd_max>0.08</cmd_max><cmd_min>-0.08</cmd_min>
{i}</plugin>
"""


def _link_bounds(lines, name):
    """(first, last) line indices of <link name="..."> ... </link>."""
    opening = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("<link") and (
                'name="%s"' % name in stripped or "name='%s'" % name in stripped):
            opening = number
            break
    if opening is None:
        return None, None
    for number in range(opening + 1, len(lines)):
        if lines[number].strip() == "</link>":
            return opening, number
    return opening, None


def find_link_end(lines):
    opening, close = _link_bounds(lines, LINK)
    if opening is None:
        return None, 'no <link name="%s"> found' % LINK
    if close is None:
        return None, "the %s link is never closed" % LINK
    return close, None


def find_model_end(lines):
    """The line index of the </model> that closes the aircraft."""
    for number in range(len(lines) - 1, -1, -1):
        if lines[number].strip() == "</model>":
            return number, None
    return None, "no </model> found"


def strip_old_visuals(lines):
    """Remove the three static shapes the old legs tool added.

    They are plain <visual name="..."> ... </visual> blocks with no nested
    visuals, so matching the closing tag by indentation is not needed - the
    first </visual> after the opening is the right one.
    """
    removed = []
    for name in OLD_VISUALS:
        while True:
            opening = None
            for number, line in enumerate(lines):
                stripped = line.strip()
                if stripped.startswith("<visual") and (
                        'name="%s"' % name in stripped
                        or "name='%s'" % name in stripped):
                    opening = number
                    break
            if opening is None:
                break
            close = None
            for number in range(opening + 1, len(lines)):
                if lines[number].strip() == "</visual>":
                    close = number
                    break
            if close is None:
                break
            del lines[opening:close + 1]
            removed.append(name)
    return removed


def block(indent):
    return BLOCK.format(
        i=indent, parent=LINK,
        yaw_link=YAW_LINK, pitch_link=PITCH_LINK,
        yaw_joint=YAW_JOINT, pitch_joint=PITCH_JOINT,
        camera=CAMERA, lrf_topic=LRF_TOPIC,
        mx=MOUNT_X, yaw_z=YAW_Z, ball_z=BALL_Z, ball_r=BALL_R,
        lens_x=round(BALL_R - 0.004, 4),
        pan_lo=round(-PAN_LIMIT, 5), pan_hi=round(PAN_LIMIT, 5),
        tilt_lo=round(TILT_UP, 5), tilt_hi=round(TILT_DOWN, 5),
        fov=FOV_RAD, iw=IMAGE_W, ih=IMAGE_H, ihz=IMAGE_HZ,
        lrf_min=LRF_MIN_M, lrf_max=LRF_MAX_M, lrf_hz=LRF_HZ,
        br=BODY[0], bg=BODY[1], bb=BODY[2],
        lr=LENS[0], lg=LENS[1], lb=LENS[2])


def plugins(indent):
    return PLUGINS.format(i=indent, yaw_joint=YAW_JOINT, pitch_joint=PITCH_JOINT)


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

    if 'name="%s"' % PITCH_LINK in "".join(lines):
        print("SKIP  the aircraft already has its gimbal.")
        return 0

    removed = strip_old_visuals(lines)

    close, problem = find_link_end(lines)
    if close is None:
        print("Cannot add the gimbal - %s in %s" % (problem, MODEL),
              file=sys.stderr)
        return 1
    link_indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())]
    # The gimbal's own links and joints are SIBLINGS of base_link, so they
    # go after its </link>, not inside it.
    added = block(link_indent)
    lines = lines[:close + 1] + [added] + lines[close + 1:]

    end, problem = find_model_end(lines)
    if end is None:
        print("Cannot add the controllers - %s in %s" % (problem, MODEL),
              file=sys.stderr)
        return 1
    plugin_indent = lines[end][: len(lines[end]) - len(lines[end].lstrip())] + "  "
    lines = lines[:end] + [plugins(plugin_indent)] + lines[end:]

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        if removed:
            print("  remove the old static shapes: %s" % ", ".join(sorted(set(removed))))
        print("  add links  %s, %s" % (YAW_LINK, PITCH_LINK))
        print("  add joints %s (Z, +-180 deg), %s (Y, %+d to %+d deg)"
              % (YAW_JOINT, PITCH_JOINT,
                 round(math.degrees(TILT_UP)), round(math.degrees(TILT_DOWN))))
        print("  add sensors %s (%dx%d at %d Hz), payload_lrf on %s"
              % (CAMERA, IMAGE_W, IMAGE_H, IMAGE_HZ, LRF_TOPIC))
        print("  add two JointPositionController plugins")
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

    print("OK    payload gimbal added to %s" % MODEL)
    if removed:
        print("      removed the old static shapes: %s"
              % ", ".join(sorted(set(removed))))
    print("      backup at %s" % os.path.basename(backup))
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. In the console, choose the Payload view.

3. Drag in the picture to slew the gimbal, and roll the mouse wheel to
   zoom.

If the picture never appears, check that Gazebo is publishing it:
     gz topic -l | grep payload

To take the gimbal off again:
     python3 tools/gimbal_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
