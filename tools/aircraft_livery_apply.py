#!/usr/bin/env python3
"""
Puts a high-visibility training livery on the aircraft.

    python3 tools/aircraft_livery_apply.py             # safety orange
    python3 tools/aircraft_livery_apply.py --colour white
    python3 tools/aircraft_livery_apply.py --list
    python3 tools/aircraft_livery_apply.py --dry-run
    python3 tools/aircraft_livery_apply.py --revert

WHAT IS WRONG WITH IT NOW
-------------------------
The airframe is 0.175 grey - PX4's own figure, and the one thing
tools/aircraft_colours_apply.py deliberately left alone when it darkened
the propellers and elevons. Against the ground, in the chase view, the
aircraft reads as a dark silhouette: you can see THAT it is there and not
much about how it is sitting.

That matters more here than it would in a game. A remote pilot has to hold
visual line of sight and judge the aircraft's attitude by eye, and a
student practising that on a grey-on-grey aircraft is practising the wrong
thing. Real training airframes are high-visibility for exactly this
reason.

WHAT IT CHANGES
---------------
  * THE AIRFRAME, from 0.175 grey to a bright colour. Safety orange by
    default; white, yellow and the original grey are also offered,
    because the right answer depends on what you fly over - orange
    disappears over the Nullarbor and sings over grass.

  * WINGTIP MARKERS, red to port and green to starboard, as small solid
    blocks at the tips. tools/aircraft_lights_apply.py already puts
    navigation LIGHTS there, but a light is only visible at night; the
    blocks give the same left-from-right cue in daylight, which is when
    most training happens.

WHAT IT DOES NOT CHANGE
-----------------------
The propellers and the elevons stay near-black. That was a deliberate
decision on 12 Oct 2026 - dark moving surfaces against lighter fixed
structure is what makes a control check readable from the chase camera -
and a bright airframe only makes that contrast better.

COLOURS ONLY, NO TEXTURE. Measured on 13 Oct 2026 by spawning test boxes
into a running world: a PBR <albedo_map> renders NEAR-BLACK in this Gazebo
Harmonic / ogre2 build, while a plain <diffuse> colour renders correctly
and an <emissive_map> renders its texture. So a painted-on registration or
a photographic livery is not available here, and anything that tries one
will come out black. Plain colours are what works.

HOW
---
By visual name, in the model's own text, like the colour, light, leg and
gimbal tools - not through ElementTree, which would throw away the file's
comments and formatting. The file is backed up first, the result is parsed
as XML, and anything that fails to parse is put back.

NOT YET SEEN IN GAZEBO at the time of writing.
"""

import argparse
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

MODEL = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SUFFIX = ".prelivery"

AIRFRAME_VISUAL = "base_link_visual"
# The propellers stay NEAR-BLACK. On the real DeltaQuad - photographs
# supplied 13 Oct 2026 - they are white, and white would read better at
# frame rate, but white propellers were asked against on the same day and
# that is the decision. --white-props is here for anyone who changes their
# mind; it is not the default.
PROP_VISUALS = ("rotor_0_visual", "rotor_1_visual", "rotor_2_visual",
                "rotor_3_visual", "rotor_puller_visual")
PROP_WHITE = (0.88, 0.88, 0.86)
MARKER = "tipmark_port"          # how we know the markers are already on

# The choices, and what each is for. Kept short deliberately: a list of
# twenty swatches is a decision nobody makes well before a lesson.
LIVERIES = {
    "orange": ((0.95, 0.35, 0.05), "safety orange - best over grass and crop"),
    "white":  ((0.90, 0.90, 0.88), "white - best over dark ground and water"),
    "yellow": ((0.95, 0.80, 0.10), "yellow - best over woodland and shadow"),
    "grey":   ((0.175, 0.175, 0.175), "the original grey - low visibility"),
}
DEFAULT = "orange"

# Taken from the nav lights, which were placed against the model's own wing
# geometry: the tips are 1.05 m either side of the centreline.
TIP_Y = 1.05
TIP_SIZE = (0.12, 0.10, 0.045)
PORT_RED = (0.85, 0.06, 0.06)
STARBOARD_GREEN = (0.06, 0.75, 0.16)

VISUAL = re.compile(r"<visual\s+name=['\"]([^'\"]+)['\"]")
COLOUR_LINE = re.compile(r"^(\s*)<(ambient|diffuse)>[^<]*</\2>\s*$")


def tip_block(name, y, rgb, what):
    """One wingtip marker, as SDF."""
    red, green, blue = rgb
    return (
        '      <!-- %s. A light says the same thing, but only after dark;\n'
        '           this is the daylight version. -->\n'
        '      <visual name="%s">\n'
        '        <pose>0.0 %.3f 0.05 0 0 0</pose>\n'
        '        <geometry><box><size>%g %g %g</size></box></geometry>\n'
        '        <material>\n'
        '          <ambient>%.3f %.3f %.3f 1</ambient>\n'
        '          <diffuse>%.3f %.3f %.3f 1</diffuse>\n'
        '          <specular>0.05 0.05 0.05 1</specular>\n'
        '        </material>\n'
        '      </visual>\n'
        % (what, name, y, TIP_SIZE[0], TIP_SIZE[1], TIP_SIZE[2],
           red * 0.55, green * 0.55, blue * 0.55, red, green, blue))


def recolour(lines, rgb, props):
    """Only the ambient and diffuse of named visuals, and only until each
    visual closes."""
    out, inside, changed = [], None, False
    wanted = {AIRFRAME_VISUAL: rgb}
    if props:
        wanted.update({name: PROP_WHITE for name in PROP_VISUALS})
    for line in lines:
        found = VISUAL.search(line)
        if found:
            inside = found.group(1) if found.group(1) in wanted else None
        if inside:
            red, green, blue = wanted[inside]
            m = COLOUR_LINE.match(line)
            if m:
                pad, tag = m.group(1), m.group(2)
                # Ambient is the colour in shadow, so it is the same hue
                # darkened rather than a grey - a bright aircraft with a
                # grey shadow side looks like two aircraft.
                scale = 0.55 if tag == "ambient" else 1.0
                line = "%s<%s>%.3f %.3f %.3f 1.0</%s>\n" % (
                    pad, tag, red * scale, green * scale, blue * scale, tag)
                changed = True
        if "</visual>" in line:
            inside = None
        out.append(line)
    return out, changed


def add_tip_markers(text):
    """Put the two markers just before base_link's last visual closes."""
    if MARKER in text:
        return text, False
    # Either quote style: PX4's own file uses single quotes for this
    # attribute and the tools here write double, so both appear in it.
    found = re.search(r"<visual\s+name=['\"]%s['\"]" % AIRFRAME_VISUAL, text)
    if not found:
        return text, False
    close = text.index("</visual>", found.start()) + len("</visual>\n")
    blocks = (tip_block("tipmark_port", TIP_Y, PORT_RED,
                        "PORT (left) wingtip - RED")
              + tip_block("tipmark_starboard", -TIP_Y, STARBOARD_GREEN,
                          "STARBOARD (right) wingtip - GREEN"))
    return text[:close] + blocks + text[close:], True


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--colour", "--color", dest="colour", default=DEFAULT,
                        choices=sorted(LIVERIES),
                        help="airframe colour (default %s)" % DEFAULT)
    parser.add_argument("--white-props", action="store_true",
                        help="make the propellers white, as the real "
                             "DeltaQuad's are. Off by default: asked "
                             "against on 13 Oct 2026")
    parser.add_argument("--no-tips", action="store_true",
                        help="recolour the airframe but add no wingtip marks")
    parser.add_argument("--list", action="store_true",
                        help="the colours, and what each is for")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--revert", action="store_true",
                        help="put the backup back")
    args = parser.parse_args(argv)

    if args.list:
        for name, (rgb, what) in sorted(LIVERIES.items()):
            print("  %-8s %-22s %s" % (name, "%.2f %.2f %.2f" % rgb, what))
        return 0

    if not os.path.isfile(MODEL):
        print("Not found: %s" % MODEL, file=sys.stderr)
        return 1

    if args.revert:
        backup = MODEL + SUFFIX
        if not os.path.isfile(backup):
            print("No backup to put back (%s)." % backup)
            return 1
        shutil.copyfile(backup, MODEL)
        print("Put back %s" % backup)
        return 0

    with open(MODEL) as handle:
        text = handle.read()
    rgb, what = LIVERIES[args.colour]
    lines, recoloured = recolour(text.splitlines(True), rgb,
                                 args.white_props)
    text_out = "".join(lines)
    tipped = False
    if not args.no_tips:
        text_out, tipped = add_tip_markers(text_out)

    if not recoloured and not tipped:
        print("Already %s, with its wingtip marks. Nothing to do."
              % args.colour)
        return 0

    print("%s %s" % ("WOULD EDIT" if args.dry_run else "EDIT", MODEL))
    print("  airframe  -> %s (%s)" % (args.colour, what))
    print("  propellers-> %s" % ("white" if args.white_props
                                 else "near-black, left as they were"))
    print("  wingtips  -> %s" % ("red to port, green to starboard"
                                 if tipped else "already there"))
    if args.dry_run:
        print("\nDry run - nothing written.")
        return 0

    shutil.copyfile(MODEL, MODEL + SUFFIX)
    with open(MODEL, "w") as handle:
        handle.write(text_out)
    try:
        ET.parse(MODEL)
    except ET.ParseError as problem:
        shutil.copyfile(MODEL + SUFFIX, MODEL)
        print("FAILED to parse (%s) - the model was put back." % problem,
              file=sys.stderr)
        return 1

    print("\nRestart PX4 and Gazebo to see it.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
