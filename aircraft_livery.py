"""
The aircraft's fuselage colour, changed from the console while it flies.

WHY IT IS DONE HERE AND NOT IN THE MODEL FILE
---------------------------------------------
tools/aircraft_livery_apply.py writes a colour into the aircraft's model
file, and that needs PX4 and Gazebo restarting to take effect - a minute
and a half, mid-lesson, to answer "can we see it better in orange?".

Gazebo will recolour a visual while it runs, over the same
/world/NAME/material_color topic that plugins/time_of_day.py already uses
to dim the sky at dusk. Proven on the live aircraft on 13 Oct 2026: the
fuselage went from orange to grey with nothing restarted.

So the model file carries the colour the simulator STARTS at, and this
changes it from there. The two agree because the station re-applies the
remembered choice at start-up.

THE TWO SCHEMES, and why only two
---------------------------------
  Search and Rescue   orange. High-visibility, which is what a student
                      holding visual line of sight needs, and what a real
                      SAR airframe is painted.
  Dark grey           the aircraft as it really looks. The reference
                      photographs of the DeltaQuad - supplied 13 Oct 2026 -
                      show a matte near-black airframe, so this is the
                      honest one for a briefing about the real aircraft.

A longer list was considered and dropped: a swatch book is not a decision
anybody makes well in the five minutes before a lesson.

WHAT IT DOES NOT TOUCH
----------------------
The propellers and the elevons. They are near-black on purpose - dark
moving surfaces against lighter fixed structure is what makes a control
check readable from the chase camera - and white propellers were asked
against on 13 Oct 2026.

FIRE AND FORGET. material_color is a topic, not a service, so nothing
comes back to say the aircraft heard. If the simulator is not running the
publish simply goes nowhere, which is why the station re-applies the
choice whenever a world is loaded rather than only when the button is
pressed.
"""

import subprocess

import sim_target

# The fuselage visual, scoped the way gz wants it: model::link::visual.
# Built from sim_target.MODEL so a renamed model does not silently stop
# this working - the same contract the cameras and the gimbal use.
AIRFRAME_VISUAL = "%s::base_link::base_link_visual" % sim_target.MODEL

SCHEMES = {
    "sar": {
        "label": "Search and Rescue (orange)",
        "rgb": (0.95, 0.35, 0.05),
        "why": "high visibility - easiest to keep in sight, and what a real "
               "SAR airframe is painted",
    },
    "grey": {
        "label": "Dark grey (as the real aircraft)",
        "rgb": (0.175, 0.175, 0.175),
        "why": "what the DeltaQuad actually looks like - for a briefing "
               "about the real aircraft rather than for visibility",
    },
}
DEFAULT = "sar"

state = {"scheme": DEFAULT}


def _publish(rgb):
    """Send the colour. True if the command went out at all."""
    red, green, blue = rgb
    # Ambient is the same hue darkened rather than a grey: a bright
    # aircraft with a grey shadow side reads as two different aircraft.
    request = (
        "entity: {name: '%s', type: VISUAL}, "
        "ambient: {r: %.3f, g: %.3f, b: %.3f, a: 1}, "
        "diffuse: {r: %.3f, g: %.3f, b: %.3f, a: 1}, "
        "specular: {r: 0.05, g: 0.05, b: 0.05, a: 1}, "
        "emissive: {r: 0, g: 0, b: 0, a: 1}"
        % (AIRFRAME_VISUAL, red * 0.55, green * 0.55, blue * 0.55,
           red, green, blue))
    try:
        subprocess.run(
            ["gz", "topic", "-t", sim_target.world_topic("material_color"),
             "-m", "gz.msgs.MaterialColor", "-p", request],
            check=False, timeout=6, capture_output=True, text=True)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def set_scheme(scheme):
    """Change the fuselage colour. Returns (ok, message)."""
    key = str(scheme or "").lower()
    if key not in SCHEMES:
        return False, ("'%s' is not a livery. Choose from: %s"
                       % (scheme, ", ".join(sorted(SCHEMES))))
    state["scheme"] = key
    sent = _publish(SCHEMES[key]["rgb"])
    if not sent:
        return False, ("Livery set to %s, but the simulator could not be "
                       "reached - it will be applied when it starts."
                       % SCHEMES[key]["label"])
    return True, "Fuselage: %s." % SCHEMES[key]["label"]


def reapply():
    """Put the remembered colour back on. Called when a world is loaded:
    a new world means a newly spawned aircraft, wearing the colour from
    its model file rather than the one the instructor chose."""
    return _publish(SCHEMES[state["scheme"]]["rgb"])


def status():
    return {
        "scheme": state["scheme"],
        "label": SCHEMES[state["scheme"]]["label"],
        "schemes": [{"id": key, "label": value["label"], "why": value["why"]}
                    for key, value in sorted(SCHEMES.items())],
    }
