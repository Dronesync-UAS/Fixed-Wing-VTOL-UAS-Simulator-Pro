"""Adds four landing legs and their mounting rails to the aircraft:

    python3 tools/aircraft_legs_apply.py            # add them
    python3 tools/aircraft_legs_apply.py --dry-run  # show the change
    python3 tools/aircraft_legs_apply.py --no-stance  # legs only, see below
    python3 tools/aircraft_legs_apply.py --revert   # put the backup back

WHY
---
Requested 12 Oct 2026 with photographs of the real airframe: four tubular
legs under the aircraft and a ball gimbal under the nose. PX4's
standard_vtol has neither - it has a flat belly and sits on it.

WHAT IS ADDED, AND WHY IT LOOKS LIKE THIS
-----------------------------------------
Copied off the photographs that came with the request - a belly view and
a three-quarter view of the real airframe - rather than invented:

  * TWO FORE-AFT RAILS under the fuselage, one each side, close in to the
    centreline. The legs hang off these, not off the motor booms. This is
    the thing that is easiest to get wrong from the words alone: "four
    legs under the aircraft" sounds like one under each rotor, and the
    photographs show nothing of the kind;
  * FOUR TUBULAR LEGS, one at each end of each rail, SPLAYED - outboard
    going down, and the front pair leaning forward while the rear pair
    lean aft. Plain open tubes, with no feet on them, which is what the
    photographs show.

The ball gimbal that hangs between the legs is NOT added here. It used to
be, as three static shapes; it is now a real two-axis mount with its own
camera and laser rangefinder, built by tools/gimbal_apply.py. Run that
tool as well. This one will not add a second one, and gimbal_apply.py
removes the old static shapes if it finds them.

Everything is carbon black, as in the photographs, against the fuselage
grey that tools/aircraft_colours_apply.py already sets.

WHERE THE POSITIONS COME FROM
-----------------------------
The airframe figures are read out of the aircraft's own model
(PX4-gazebo-models models/standard_vtol/model.sdf), not guessed:

  * +X is forward. The pusher, rotor_puller, is at x = -0.22, so -X is aft.
  * Y is the span. The belly collision box is 2.144 m in Y (+-1.07 m), the
    same half-span the wingtip lights use.
  * the four hover rotors are at x = +-0.35, y = +-0.35.
  * the belly sits at z = -0.095: the collision box's pose is z = -0.07 and
    it is 0.05 thick.

So the rails sit at y = +-0.16, just outboard of the fuselage and well
inboard of the rotors, and the legs stand at x = +-0.24 on those rails.
(tools/gimbal_apply.py hangs the gimbal at x = 0.06 between them, which
is why nothing else is put there.) The splay angles and the
0.32 m stance height are proportions off the photographs; everything else
is arithmetic from the figures above.

VISUAL ONLY - AND WHAT THAT MEANS FOR THE STANCE
------------------------------------------------
The legs and the rails are <visual> elements with NO <collision>. Four
thin cylinders touching the ground is exactly the contact case ODE is
worst at, and a landing gear that makes the aircraft jitter or tip on the
runway would be a worse lesson than no landing gear at all.

That leaves the question of height. With nothing else changed the aircraft
would still rest on its belly, and the new legs would disappear into the
ground. So by default this tool also LOWERS the existing belly collision
box, from z = -0.07 to z = -0.295, which puts its underside at z = -0.32:
the height of the feet. The aircraft then stands at the right height on
one simple box, which is the same single contact ODE has always had - no
new contact behaviour, no jitter, just a lower one.

The honest cost: a world that spawns the model at a fixed height will now
drop it about 0.22 m further before it settles. That is a small drop on
the ground before arming, and it has NOT been watched happen - see below.
Pass --no-stance to leave the collision box alone; the legs then clip
through the ground, which looks wrong but changes no physics at all.

NOT YET SEEN. Nobody has watched this in Gazebo. The geometry is arithmetic
off the model's own numbers and the file is parsed as XML before it is
accepted, which catches a broken edit but not an ugly one.
"""
import math
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

MODEL = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SUFFIX = ".prelegs"
LINK = "base_link"
MARKER = "leg_front_left_tube"

# Where the feet are. Everything else is measured from here.
FOOT_Z = -0.32
BELLY_Z = -0.095            # the model's own belly, from its collision box

# The two fore-aft rails the legs hang from.
RAIL_Y = 0.16
RAIL_LEN_X = 0.56
RAIL_W = 0.030
RAIL_H = 0.018
RAIL_Z = -0.104             # tucked just under the belly

LEG_TOP_Z = -0.108          # where a leg meets the underside of a rail
LEG_X = 0.24                # one at each end of each rail
LEG_RADIUS = 0.014

# How far the legs lean, in degrees: outboard going down, and fore and aft
# away from the middle. Proportions off the photographs.
SPLAY_OUT_DEG = 12.0
SPLAY_FORE_DEG = 10.0

# Carbon tube black, as in the photographs.
TUBE = (0.06, 0.06, 0.065)

# Where the belly collision box ends up, so the aircraft stands on the
# height the legs imply. 0.05 is the box's own thickness.
STANCE_POSE_Z = round(FOOT_Z + 0.05 / 2, 4)
STANCE_WAS_Z = -0.07

CYL = """\
{i}<visual name="{name}">
{i}  <pose>{x} {y} {z} {roll} {pitch} 0</pose>
{i}  <geometry>
{i}    <cylinder>
{i}      <radius>{radius}</radius>
{i}      <length>{length}</length>
{i}    </cylinder>
{i}  </geometry>
{i}  <material>
{i}    <ambient>{r} {g} {b} 1</ambient>
{i}    <diffuse>{r} {g} {b} 1</diffuse>
{i}  </material>
{i}</visual>
"""

SPHERE = """\
{i}<visual name="{name}">
{i}  <pose>{x} {y} {z} 0 0 0</pose>
{i}  <geometry>
{i}    <sphere>
{i}      <radius>{radius}</radius>
{i}    </sphere>
{i}  </geometry>
{i}  <material>
{i}    <ambient>{r} {g} {b} 1</ambient>
{i}    <diffuse>{r} {g} {b} 1</diffuse>
{i}  </material>
{i}</visual>
"""


BOX = """\
{i}<visual name="{name}">
{i}  <pose>{x} {y} {z} 0 0 0</pose>
{i}  <geometry>
{i}    <box>
{i}      <size>{sx} {sy} {sz}</size>
{i}    </box>
{i}  </geometry>
{i}  <material>
{i}    <ambient>{r} {g} {b} 1</ambient>
{i}    <diffuse>{r} {g} {b} 1</diffuse>
{i}  </material>
{i}</visual>
"""


def parts():
    """Every visual to add, as (kind, name, fields, what it is).

    The legs are worked out rather than written down, because a leaning
    cylinder has to have its centre moved to keep its TOP on the rail and
    its BOTTOM on the ground, and doing that four times by hand is four
    chances to get a sign wrong.

    A cylinder's axis is its local Z. Gazebo applies a pose's rotation as
    Rz(yaw) . Ry(pitch) . Rx(roll), so with yaw 0 the axis ends up at

        (cos(roll) sin(pitch), -sin(roll), cos(roll) cos(pitch))

    A positive roll therefore puts the BOTTOM of the leg at +Y, and a
    negative pitch puts it at +X - which is how the signs below come out.
    """
    out = []

    for side, sy in (("left", 1), ("right", -1)):
        out.append(("box", "gear_rail_%s" % side,
                    dict(x=0.0, y=round(RAIL_Y * sy, 4), z=RAIL_Z,
                         sx=RAIL_LEN_X, sy=RAIL_W, sz=RAIL_H,
                         r=TUBE[0], g=TUBE[1], b=TUBE[2]),
                    "mounting rail, %s" % side))

    roll_out = math.radians(SPLAY_OUT_DEG)
    pitch_fore = math.radians(SPLAY_FORE_DEG)
    # The straight-down drop is shortened by both leans, so the tube has
    # to be longer than the drop to still reach the ground.
    drop = LEG_TOP_Z - FOOT_Z
    length = drop / (math.cos(roll_out) * math.cos(pitch_fore))

    for tag, sx, sy in (("front_left", 1, 1), ("front_right", 1, -1),
                        ("rear_left", -1, 1), ("rear_right", -1, -1)):
        roll = roll_out * sy
        pitch = -pitch_fore * sx
        axis = (math.cos(roll) * math.sin(pitch),
                -math.sin(roll),
                math.cos(roll) * math.cos(pitch))
        top = (LEG_X * sx, RAIL_Y * sy, LEG_TOP_Z)
        centre = tuple(top[i] - axis[i] * length / 2 for i in range(3))
        out.append(("cyl", "leg_%s_tube" % tag,
                    dict(x=round(centre[0], 4), y=round(centre[1], 4),
                         z=round(centre[2], 4),
                         roll=round(roll, 5), pitch=round(pitch, 5),
                         radius=LEG_RADIUS, length=round(length, 4),
                         r=TUBE[0], g=TUBE[1], b=TUBE[2]),
                    "leg tube, %s" % tag.replace("_", " ")))

    return out


def block(indent):
    text = (indent + "<!-- Landing legs and their rails, added by\n"
            + indent + "     tools/aircraft_legs_apply.py. Visual only: four thin\n"
            + indent + "     cylinders on the ground is the contact case ODE handles\n"
            + indent + "     worst, so the aircraft still stands on its one belly box,\n"
            + indent + "     lowered to the height of the feet. -->\n")
    for kind, name, fields, _ in parts():
        template = {"cyl": CYL, "sphere": SPHERE, "box": BOX}[kind]
        text += template.format(i=indent, name=name, **fields)
    return text


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


def lower_stance(lines):
    """Move the belly collision box down to the height of the feet.

    Returns (changed, note). Finds the collision by name and rewrites the
    first <pose> after it - the only pose that box has.
    """
    opening = None
    for number, line in enumerate(lines):
        if re.search(r"<collision\s+name=['\"]base_link_collision['\"]", line):
            opening = number
            break
    if opening is None:
        return False, "no <collision name='base_link_collision'> to lower"
    for number in range(opening + 1, min(opening + 8, len(lines))):
        match = re.match(r"(\s*)<pose>([^<]*)</pose>\s*$", lines[number])
        if not match:
            continue
        fields = match.group(2).split()
        if len(fields) != 6:
            return False, "the collision pose is not six numbers: %r" % match.group(2)
        try:
            already = float(fields[2])
        except ValueError:
            return False, "the collision pose z is not a number: %r" % fields[2]
        if abs(already - STANCE_POSE_Z) < 1e-6:
            return False, "the stance is already lowered"
        fields[2] = repr(STANCE_POSE_Z)
        lines[number] = "%s<pose>%s</pose>\n" % (match.group(1), " ".join(fields))
        return True, ("belly collision box z %s -> %s, so its underside sits "
                      "at the feet (%s)" % (already, STANCE_POSE_Z, FOOT_Z))
    return False, "the collision has no <pose> to lower"


def revert():
    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        print("No %s backup found - nothing to restore." % SUFFIX)
        return 0
    shutil.copy2(backup, MODEL)
    print("Restored %s from its backup." % MODEL)
    print("Restart the simulator for it to take effect.")
    return 0


def apply(dry_run, stance):
    if not os.path.isfile(MODEL):
        print("Aircraft model not found: %s" % MODEL, file=sys.stderr)
        return 1

    with open(MODEL) as handle:
        lines = handle.read().splitlines(keepends=True)

    if MARKER in "".join(lines):
        print("SKIP  the aircraft already has its legs.")
        return 0

    close, problem = find_link_end(lines)
    if close is None:
        print("Cannot add the legs - %s in %s" % (problem, MODEL),
              file=sys.stderr)
        return 1

    indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())] + "  "
    added = block(indent)
    lines = lines[:close] + [added] + lines[close:]

    stance_note = "left alone (--no-stance)"
    if stance:
        changed, stance_note = lower_stance(lines)
        if not changed and "already" not in stance_note:
            print("Cannot set the stance - %s" % stance_note, file=sys.stderr)
            return 1

    if dry_run:
        print("WOULD EDIT %s" % MODEL)
        print("  insert %d lines before the end of <link name=\"%s\">"
              % (added.count("\n"), LINK))
        for _, name, fields, what in parts():
            print("    %-20s (%s, %s, %s)  %s"
                  % (name, fields["x"], fields["y"], fields["z"], what))
        print("  stance: %s" % stance_note)
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

    print("OK    four legs and their rails added to %s" % MODEL)
    print("      stance: %s" % stance_note)
    print("      backup at %s" % os.path.basename(backup))
    print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. Look at the aircraft on the ground in the chase view. The legs should
   be standing on it, not sunk into it.

The legs are decoration: they have no collision. The gimbal is added
separately, by tools/gimbal_apply.py.

To take them off again:
     python3 tools/aircraft_legs_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv, "--no-stance" not in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
