"""Adds a chase camera to the aircraft, so the external view can live inside
the instructor console instead of only in the Gazebo window:

    python3 tools/chase_camera_apply.py            # add it
    python3 tools/chase_camera_apply.py --dry-run  # show the change
    python3 tools/chase_camera_apply.py --revert   # put the backup back

WHAT IT ADDS, AND WHERE
-----------------------
A camera sensor on the aircraft's base_link, nine metres behind and two
above, pitched down to put the aircraft in the middle of the frame. Because
it is part of the model it moves and banks with the aircraft, which is what
makes it a chase view rather than a fixed camera the aircraft flies out of.

The link and sensor names are not free choices: sim_target.CHASE_CAMERA
holds the same pair, and the station builds its subscription topic from
them. Rename one without the other and the panel silently shows nothing.

WHY IT EDITS PX4'S MODEL AND NOT A WORLD
----------------------------------------
A camera that follows the aircraft has to be attached to the aircraft, and
the aircraft model lives in PX4's tree. That file is already locally
modified on this machine - the nose camera was added to it the same way -
so this is the established route rather than a new one.

Nothing here is tracked by git, so editing it cannot dirty the working tree.
The file is backed up to model.sdf.prechase first, the result is parsed as
XML, and anything that fails to parse is restored automatically.

THE COST, STATED PLAINLY
------------------------
This is a second rendered camera on a machine whose graphics performance is
already noted as marginal (12 July entry). It is 640x360 at 15 Hz against
the nose camera's 1280x960, which is the smallest useful situational view.
If the simulator slows noticeably, --revert removes it entirely.
"""
import os
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

MODEL = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SUFFIX = ".prechase"

LINK, SENSOR = sim_target.CHASE_CAMERA

# 9 m back and 2.2 m up. The pitch is atan(2.2/9) = 0.24 rad, which is what
# puts the aircraft in the centre of the frame rather than near the top:
# the camera looks along its own +X, so it has to be tilted down by the
# angle it is raised by.
SENSOR_BLOCK = """\
{i}<!-- Chase camera: the external view, streamed into the instructor station
{i}     rather than only visible in the Gazebo window. Added by
{i}     tools/chase_camera_apply.py; sim_target.CHASE_CAMERA holds the same
{i}     link and sensor names, and the station's topic is built from them.
{i}     Deliberately small and slow - this is a second rendered camera. -->
{i}<sensor name="{sensor}" type="camera">
{i}  <gz_frame_id>{link}</gz_frame_id>
{i}  <pose>-9 0 2.2 0 0.24 0</pose>
{i}  <always_on>1</always_on>
{i}  <update_rate>15</update_rate>
{i}  <camera>
{i}    <horizontal_fov>1.05</horizontal_fov>
{i}    <image>
{i}      <width>640</width>
{i}      <height>360</height>
{i}      <format>R8G8B8</format>
{i}    </image>
{i}    <!-- Far plane well past the 500 m operating limit, so the terrain
{i}         behind the aircraft does not end in mid-air. -->
{i}    <clip>
{i}      <near>0.1</near>
{i}      <far>8000</far>
{i}    </clip>
{i}  </camera>
{i}</sensor>
"""


def find_link_end(lines):
    """The line index of the </link> that closes the aircraft's base_link.

    Done on the text rather than by rewriting the parsed XML because
    ElementTree would discard this file's comments and formatting, and the
    result is a file a person has to be able to read and diff afterwards.
    """
    opening = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("<link") and (
                'name="%s"' % LINK in stripped or "name='%s'" % LINK in stripped):
            opening = number
            break
    if opening is None:
        return None, "no <link name=\"%s\"> found" % LINK
    for number in range(opening + 1, len(lines)):
        if lines[number].strip() == "</link>":
            return number, None
    return None, "the %s link is never closed" % LINK


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
    joined = "".join(lines)

    if 'name="%s"' % SENSOR in joined or "name='%s'" % SENSOR in joined:
        print("SKIP  the aircraft already has a %s sensor." % SENSOR)
        return 0

    close, problem = find_link_end(lines)
    if close is None:
        print("Cannot add the camera - %s in %s" % (problem, MODEL),
              file=sys.stderr)
        return 1

    indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())]
    block = SENSOR_BLOCK.format(i=indent + "  ", sensor=SENSOR, link=LINK)

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        print("  insert %d lines before line %d (the end of <link name=\"%s\">)"
              % (block.count("\n"), close + 1, LINK))
        print("  topic it would publish on:\n    %s"
              % sim_target.chase_camera_topic())
        print("\nDry run - nothing written.")
        return 0

    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(MODEL, backup)
    with open(MODEL, "w") as handle:
        handle.writelines(lines[:close] + [block] + lines[close:])

    # A model that no longer parses stops the aircraft spawning at all, so
    # undo rather than leave it broken.
    try:
        ET.parse(MODEL)
    except ET.ParseError as exc:
        shutil.copy2(backup, MODEL)
        print("FAILED: the edit broke the XML (%s) - restored from backup."
              % exc, file=sys.stderr)
        return 1

    print("OK    chase camera added to %s" % MODEL)
    print("      backup at %s" % os.path.basename(backup))
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. Check the camera is publishing (a terminal, while it runs):
     gz topic -l | grep chase
   Expect:
     %s
   Nothing listed means the sensor did not load - say so before going on.

3. The console's "Chase Camera" panel shows it.

If the simulator feels slower, this is the thing to blame first:
     python3 tools/chase_camera_apply.py --revert""" %
          sim_target.chase_camera_topic())
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except BrokenPipeError:
        try:
            sys.stdout.close()
        except BrokenPipeError:
            pass
        sys.exit(0)
