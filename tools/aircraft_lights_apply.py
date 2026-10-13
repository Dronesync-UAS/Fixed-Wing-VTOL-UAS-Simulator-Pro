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

WHICH ONES FLASH
----------------
The navigation lights are STEADY - that is what a position light is for,
and flashing them would teach a student the wrong thing. The white
strobes double-flash about once a second, and the red beacon flashes on
its own slower rhythm while the aircraft is armed. aircraft_lights.py
drives all of that.

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

The strobes DO flash. Gazebo has no flashing light of its own, so the
flashing is done by aircraft_lights.py switching them on and off on the
world's light_config topic from one thread - one publisher for all of
them, which is why it is affordable. (An earlier version of this file
said they were steady. That was true when it was written and has not been
true since the flash driver was added on 12 Oct 2026.)

WHY IT EDITS PX4'S MODEL
------------------------
A light that moves with the aircraft has to be attached to the aircraft,
and that model lives in PX4's tree - the same route the nose camera and
the chase camera already took. The file is backed up first, the result is
parsed as XML, and anything that fails to parse is restored automatically.
"""
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
SUFFIX = ".prelights"
LINK = "base_link"

# name, colour, where it sits on the airframe, and what it is for.
# The wing half-span is taken from the standard_vtol model's own wing
# geometry (the wing runs to about 1.07 m either side of the centreline).
# NO WING LIGHTS. There were red and green wingtip navigation lights here
# until 13 Oct 2026. They were removed on instruction, and the reference
# photographs of the DeltaQuad show none. They were also doing visible
# harm: with a 40 m range and almost no attenuation they threw large red
# and green pools onto the ground in broad daylight, which is not what a
# navigation light does.
LIGHTS = [
    # THE TAIL LIGHT IS THE GPS INDICATOR, not a position light. Green
    # flashing means the aircraft is on and has GPS; red flashing means
    # GPS has been lost. The colour is changed while it runs - see
    # aircraft_lights.set_gps - so the figure here is only what it starts
    # at. Green, because an aircraft that has just started and has a fix
    # is the normal case.
    ("nav_tail", (0.05, 0.9, 0.15), (-0.55, 0.0, 0.10),
     "tail, facing aft - GPS status, GREEN with a fix / RED without"),
    ("strobe_top", (1.0, 1.0, 1.0), (0.0, 0.0, 0.22),
     "spine anti-collision - WHITE"),
    ("strobe_belly", (1.0, 1.0, 1.0), (0.0, 0.0, -0.14),
     "belly anti-collision - WHITE"),
    # A real beacon is red and means the engines are running or about to
    # be. Here it follows the armed state, which is the same statement.
    ("beacon_top", (0.95, 0.08, 0.05), (0.12, 0.0, 0.24),
     "beacon, flashes while armed - RED"),
]

# Lights this tool used to write and no longer does. Named explicitly
# rather than "anything not in LIGHTS", so a light another tool added can
# never be deleted by this one.
OBSOLETE = ("nav_port", "nav_starboard")

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


def write_out(text, what):
    """Back up, write, and put the backup back if the result will not parse.
    Shared by the add path and the removal-only path."""
    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(MODEL, backup)
    with open(MODEL, "w") as handle:
        handle.write(text)
    try:
        ET.parse(MODEL)
    except ET.ParseError as exc:
        shutil.copy2(backup, MODEL)
        print("FAILED: the edit broke the XML (%s) - restored from backup."
              % exc, file=sys.stderr)
        return 1
    print("OK    %s in %s" % (what, MODEL))
    print("      backup at %s" % os.path.basename(backup))
    return 0


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

    # WHICH lights are missing, not whether the FIRST one is there.
    #
    # THE BUG THIS FIXES, found 12 Oct 2026 by verify_install.py on the
    # instructor's machine: this used to test for LIGHTS[0] - nav_port -
    # and skip if it was present. The beacon was added to the list after
    # that machine had already run the tool, so every later run said
    # "already has its lights" and the beacon could never arrive. A tool
    # that gains a part must be able to add that part to a model it has
    # already edited.
    # Take out the lights this tool no longer writes, before working out
    # what is missing. Without this a model edited by an older version
    # keeps them for ever: the tool only ever added.
    removed = []
    for name in OBSOLETE:
        pattern = re.compile(
            r'[ \t]*<light name="%s"[^>]*>.*?</light>\n' % re.escape(name),
            re.S)
        joined, count = pattern.subn("", joined)
        if count:
            removed.append(name)
    if removed:
        lines = joined.splitlines(keepends=True)
        print("Removing %s - no longer part of the aircraft.\n"
              % ", ".join(removed))

    # Bring lights that ARE there into line with the table. The tool only
    # ever added, so a light whose job changed kept its old colour: when
    # the tail light became the GPS indicator on 13 Oct 2026 the table
    # said green and the model still said white.
    recoloured = []
    for name, (r, g, b), _, _ in LIGHTS:
        want = "<diffuse>%s %s %s 1</diffuse>" % (r, g, b)
        block = re.search(
            r'<light name="%s"[^>]*>.*?</light>' % re.escape(name), joined, re.S)
        if not block or want in block.group(0):
            continue
        fixed = re.sub(r"<(diffuse|specular)>[^<]*</\1>",
                       lambda m: "<%s>%s %s %s 1</%s>" % (m.group(1), r, g, b,
                                                          m.group(1)),
                       block.group(0))
        joined = joined.replace(block.group(0), fixed, 1)
        recoloured.append(name)
    if recoloured:
        lines = joined.splitlines(keepends=True)
        print("Recolouring %s to match the table.\n" % ", ".join(recoloured))

    missing = [light for light in LIGHTS
               if 'name="%s"' % light[0] not in joined]
    if not missing and not removed and not recoloured:
        print("SKIP  the aircraft already has all %d lights." % len(LIGHTS))
        return 0
    if missing and len(missing) < len(LIGHTS):
        print("The aircraft has %d of %d lights. Adding the rest: %s\n"
              % (len(LIGHTS) - len(missing), len(LIGHTS),
                 ", ".join(light[0] for light in missing)))

    # Nothing to ADD, but something was taken out: write the removal and
    # stop. Falling through would try to insert an empty block, which the
    # first version of this did - it offered to "insert 4 lines" of
    # nothing.
    if not missing:
        did = ([("removed " + ", ".join(removed))] if removed else []) \
            + ([("recoloured " + ", ".join(recoloured))] if recoloured else [])
        if dry_run:
            print("WOULD EDIT %s" % MODEL)
            for line in did:
                print("  %s" % line)
            print("\nDry run - nothing written.")
            return 0
        return write_out(joined, "; ".join(did))

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
    for name, (r, g, b), (x, y, z), _ in missing:
        block += LIGHT_BLOCK.format(i=indent, name=name, r=r, g=g, b=b,
                                    x=x, y=y, z=z)

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        print("  insert %d lines before line %d (the end of <link name=\"%s\">)"
              % (block.count("\n"), close + 1, LINK))
        for name, _, where, what in missing:
            print("    %-16s %-22s %s" % (name, str(where), what))
        print("\nDry run - nothing written.")
        return 0

    if write_out("".join(lines[:close] + [block] + lines[close:]),
                 "lights added") != 0:
        return 1
    # write_out already reports what it did and where the backup is.
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. Set the lighting to Night in the console's Simulation Control section,
   so there is something for them to show up against.

3. Switch them on with the console's "Aircraft lights" control.

The strobes double-flash and the beacon flashes while armed. The tail
light is the GPS indicator - flashing green with a fix, flashing red
without - so injecting a GPS failure shows on the airframe itself. There
are no wingtip navigation lights: the reference aircraft has none. All of
them are easiest to see against a dark scene, so set the lighting to
Night first.

To take them off again:
     python3 tools/aircraft_lights_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
