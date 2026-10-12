"""Adds navigation and anti-collision lights to the aircraft:

    python3 tools/aircraft_lights_apply.py            # add them
    python3 tools/aircraft_lights_apply.py --dry-run  # show the change
    python3 tools/aircraft_lights_apply.py --revert   # put the backup back

WHAT IT ADDS, AND WHY THESE COLOURS
-----------------------------------
The real convention, which is worth teaching correctly because a student
will be asked it:

  * RED on the PORT (left) wingtip
  * GREEN on the STARBOARD (right) wingtip
  * WHITE at the tail, facing aft
  * WHITE anti-collision strobes, one on the spine and one on the belly

Those are the lights by which another pilot reads which way an aircraft is
pointing at night: red on your left and green on your right means it is
coming towards you.

THE REQUEST ASKED FOR SOMETHING SLIGHTLY DIFFERENT - a white strobe on top
(which is right), a green strobe on the belly, and "white and red on the
wing tips". Green on the belly is not a light a real aircraft carries, and
the wingtips are red and green rather than red and white. The real
convention is what has been built, because the simulator is for training
and a student taught the wrong colours will be marked wrong. The belly
strobe is here, in white; changing its colour is one line below if that is
genuinely wanted.

HOW THEY ARE SWITCHED
---------------------
They are Gazebo lights attached to the aircraft's base_link, so they move
with it. The console switches them through Gazebo's own light_config
service - see plugins/aircraft_lights.py - rather than by restarting.

The strobes do not flash. Gazebo has no flashing light; a flash would have
to be a plugin toggling the light on and off, and that is a running
process per light. They are steady, and the console says so.

WHY IT EDITS PX4'S MODEL
------------------------
A light that moves with the aircraft has to be attached to the aircraft,
and that model lives in PX4's tree - the same route the nose camera and
the chase camera already took. The file is backed up first, the result is
parsed as XML, and anything that fails to parse is restored automatically.
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
SUFFIX = ".prelights"
LINK = "base_link"

# name, colour, where it sits on the airframe, and what it is for.
# The wing half-span is taken from the standard_vtol model's own wing
# geometry (the wing runs to about 1.07 m either side of the centreline).
LIGHTS = [
    ("nav_port", (0.9, 0.05, 0.05), (0.0, 1.05, 0.05),
     "port (left) wingtip - RED"),
    ("nav_starboard", (0.05, 0.9, 0.15), (0.0, -1.05, 0.05),
     "starboard (right) wingtip - GREEN"),
    ("nav_tail", (0.9, 0.9, 0.85), (-0.55, 0.0, 0.10),
     "tail, facing aft - WHITE"),
    ("strobe_top", (1.0, 1.0, 1.0), (0.0, 0.0, 0.22),
     "spine anti-collision - WHITE"),
    ("strobe_belly", (1.0, 1.0, 1.0), (0.0, 0.0, -0.14),
     "belly anti-collision - WHITE"),
]

LIGHT_BLOCK = """\
{i}<light name="{name}" type="point">
{i}  <pose>{x} {y} {z} 0 0 0</pose>
{i}  <diffuse>{r} {g} {b} 1</diffuse>
{i}  <specular>{r} {g} {b} 1</specular>
{i}  <attenuation>
{i}    <range>40</range>
{i}    <constant>0.2</constant>
{i}    <linear>0.08</linear>
{i}    <quadratic>0.01</quadratic>
{i}  </attenuation>
{i}  <cast_shadows>false</cast_shadows>
{i}</light>
"""


def find_link_end(lines):
    """The line index of the </link> that closes the aircraft's base_link."""
    opening = None
    for number, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("<link") and (
                'name="%s"' % LINK in stripped or "name='%s'" % LINK in stripped):
            opening = number
            break
    if opening is None:
        return None, 'no <link name="%s"> found' % LINK
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

    if 'name="%s"' % LIGHTS[0][0] in joined:
        print("SKIP  the aircraft already has its lights.")
        return 0

    close, problem = find_link_end(lines)
    if close is None:
        print("Cannot add the lights - %s in %s" % (problem, MODEL),
              file=sys.stderr)
        return 1

    indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())] + "  "
    block = (indent + "<!-- Navigation and anti-collision lights, added by\n"
             + indent + "     tools/aircraft_lights_apply.py. Red to port, green to\n"
             + indent + "     starboard, white at the tail, white strobes above and\n"
             + indent + "     below. Switched from the console. -->\n")
    for name, (r, g, b), (x, y, z), _ in LIGHTS:
        block += LIGHT_BLOCK.format(i=indent, name=name, r=r, g=g, b=b,
                                    x=x, y=y, z=z)

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        print("  insert %d lines before line %d (the end of <link name=\"%s\">)"
              % (block.count("\n"), close + 1, LINK))
        for name, _, where, what in LIGHTS:
            print("    %-16s %-22s %s" % (name, str(where), what))
        print("\nDry run - nothing written.")
        return 0

    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(MODEL, backup)
    with open(MODEL, "w") as handle:
        handle.writelines(lines[:close] + [block] + lines[close:])

    try:
        ET.parse(MODEL)
    except ET.ParseError as exc:
        shutil.copy2(backup, MODEL)
        print("FAILED: the edit broke the XML (%s) - restored from backup."
              % exc, file=sys.stderr)
        return 1

    print("OK    aircraft lights added to %s" % MODEL)
    print("      backup at %s" % os.path.basename(backup))
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. Set the lighting to Night in the console's Simulation Control section,
   so there is something for them to show up against.

3. Switch them on with the console's "Aircraft lights" control.

They are steady, not flashing: Gazebo has no flashing light, and making
one flash would mean a process per light toggling it. They are also only
visible against a dark scene.

To take them off again:
     python3 tools/aircraft_lights_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
