"""Recolours the aircraft so it looks less like a toy:

    python3 tools/aircraft_colours_apply.py            # recolour it
    python3 tools/aircraft_colours_apply.py --dry-run  # show the change
    python3 tools/aircraft_colours_apply.py --revert   # put the backup back

WHAT IT CHANGES, AND WHY
------------------------
PX4's standard_vtol ships with bright blue propellers and bright blue
elevons against a mid-grey airframe. Both were asked to change:

  * PROPELLERS, from blue to near-black. A real propeller is dark and
    almost invisible in the disc; a blue one reads as a toy and, at night
    with the new lighting, is the brightest thing on the aircraft.

  * ELEVONS (the request called them ailerons - on this airframe the same
    surface does both jobs, which is what elevon means) from blue to a
    grey DARKER than the fuselage. Darker rather than lighter so the
    moving surfaces stand out against the fixed structure, which is what
    makes a control check readable from the chase camera.

Near-black rather than black: a pure 0,0,0 surface takes no light at all
and goes completely flat, so the propeller would lose its shape. 0.05 is
dark enough to read as black and still catches an edge.

The fuselage is left alone at 0.175.

HOW
---
By visual name, in the model's own text. Done on the text rather than
through ElementTree because that would discard the file's comments and
formatting, and this is a file a person has to be able to diff afterwards
- the same reason the camera and lights tools work this way.

The file is backed up first, the result is parsed as XML, and anything
that fails to parse is restored automatically.
"""
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

MODEL = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SUFFIX = ".precolour"

# visual name -> (red, green, blue), and what it is.
COLOURS = {
    "rotor_0_visual": ((0.05, 0.05, 0.05), "hover rotor"),
    "rotor_1_visual": ((0.05, 0.05, 0.05), "hover rotor"),
    "rotor_2_visual": ((0.05, 0.05, 0.05), "hover rotor"),
    "rotor_3_visual": ((0.05, 0.05, 0.05), "hover rotor"),
    "rotor_puller_visual": ((0.05, 0.05, 0.05), "pusher propeller"),
    "left_elevon_visual": ((0.09, 0.09, 0.10), "elevon, darker than the body"),
    "right_elevon_visual": ((0.09, 0.09, 0.10), "elevon, darker than the body"),
}

VISUAL = re.compile(r"<visual\s+name=['\"]([^'\"]+)['\"]")
COLOUR_LINE = re.compile(r"^(\s*)<(ambient|diffuse)>[^<]*</\2>\s*$")


def recolour(lines):
    """Returns (new lines, what changed). Only the ambient and diffuse of
    a named visual are touched, and only until that visual closes."""
    out, changed = [], []
    inside = None
    for line in lines:
        found = VISUAL.search(line)
        if found:
            inside = found.group(1) if found.group(1) in COLOURS else None
        elif inside and "</visual>" in line:
            inside = None

        match = COLOUR_LINE.match(line.rstrip("\n")) if inside else None
        if match:
            r, g, b = COLOURS[inside][0]
            out.append(f"{match.group(1)}<{match.group(2)}>"
                       f"{r} {g} {b} 1.0</{match.group(2)}>\n")
            changed.append((inside, match.group(2)))
        else:
            out.append(line)
    return out, changed


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

    new_lines, changed = recolour(lines)
    if not changed:
        print("SKIP  nothing to recolour - are the visual names as expected?")
        print("      looked for: %s" % ", ".join(sorted(COLOURS)))
        return 0
    if new_lines == lines:
        print("SKIP  the aircraft already has these colours.")
        return 0

    by_visual = {}
    for name, field in changed:
        by_visual.setdefault(name, []).append(field)
    for name in sorted(by_visual):
        r, g, b = COLOURS[name][0]
        print("  %-22s -> %.2f %.2f %.2f   (%s)"
              % (name, r, g, b, COLOURS[name][1]))

    if dry_run:
        print("\nWOULD EDIT %s" % MODEL)
        print("Dry run - nothing written.")
        return 0

    backup = MODEL + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(MODEL, backup)
    with open(MODEL, "w") as handle:
        handle.writelines(new_lines)

    try:
        ET.parse(MODEL)
    except ET.ParseError as exc:
        shutil.copy2(backup, MODEL)
        print("FAILED: the edit broke the XML (%s) - restored from backup."
              % exc, file=sys.stderr)
        return 1

    print("\nOK    aircraft recoloured in %s" % MODEL)
    print("      backup at %s" % os.path.basename(backup))
    print("""
Restart the simulator to see it - the Stop icon, then the start icon.

To put the blue back:
     python3 tools/aircraft_colours_apply.py --revert""")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
