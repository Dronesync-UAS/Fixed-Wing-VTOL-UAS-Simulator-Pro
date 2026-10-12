"""
AIRCRAFT LIGHTS - navigation and anti-collision lights, on and off.

Added 12 Oct 2026 for night operations.

The lights themselves are added to the aircraft model by
tools/aircraft_lights_apply.py, which also explains the colours. The short
version, because it is the part a student gets asked: RED to port, GREEN
to starboard, WHITE at the tail, WHITE strobes above and below. Red on
your left and green on your right means the aircraft is coming towards
you, and that is the whole reason the convention exists.

SWITCHING. Gazebo's light_config service is the same one the time-of-day
control uses, and it finds a light by name. A light inside a model is
named within it, so the names are scoped - gz-sim resolves a scoped name
through entitiesFromScopedName, which is why the bare light name works
here as well.

There is no brightness control and no flashing. Gazebo has no flashing
light; making a strobe flash would mean a process per light toggling it
several times a second, and that is a running cost for an effect. They are
steady, and the console says so rather than letting it look broken.

NOT YET SEEN WORKING. The service and the message are read off the gz-sim8
source; nobody has watched these lights come on.
"""
import subprocess

from sim_target import service
from simulator_link import log_instructor_action

# The names tools/aircraft_lights_apply.py gives them.
LIGHTS = ["nav_port", "nav_starboard", "nav_tail", "strobe_top", "strobe_belly"]
STROBES = ["strobe_top", "strobe_belly"]

state = {"active": False}


def _set(name, on):
    """Returns None if Gazebo took it, or a short reason if it did not."""
    request = f"name: '{name}', type: POINT, is_light_off: {str(not on).lower()}"
    try:
        done = subprocess.run(
            ["gz", "service", "-s", service("light_config"),
             "--reqtype", "gz.msgs.Light", "--reptype", "gz.msgs.Boolean",
             "--timeout", "3000", "--req", request],
            check=False, timeout=8, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return str(exc)
    if done.returncode != 0:
        return (done.stderr or done.stdout or "no answer").strip()[:90]
    return None


def toggle_lights(which="all"):
    wanted = STROBES if str(which) == "strobes" else LIGHTS
    on = not state["active"]
    problems = [f"{name} ({why})" for name in wanted
                for why in [_set(name, on)] if why]

    if len(problems) == len(wanted):
        return ("No lights responded - %s. Have they been added to the "
                "aircraft? Run tools/aircraft_lights_apply.py, then restart "
                "the simulator." % problems[0])

    state["active"] = on
    log_instructor_action("aircraft_lights",
                          f"which={which} on={on} failed={len(problems)}")
    what = "Strobes" if str(which) == "strobes" else "Navigation lights and strobes"
    note = ("  They are steady, not flashing - Gazebo has no flashing light."
            if on else "")
    partly = ("  Some did not respond: " + ", ".join(problems) if problems else "")
    return f"{what} {'on' if on else 'off'}.{note}{partly}"


PLUGIN = {
    "id": "aircraft_lights",
    "label": "Aircraft lights",
    "category": "Simulation Control",
    "style": "normal",
    "inputs": [{"name": "which", "label": "Which", "type": "select",
                "default": "all",
                "options": [{"value": "all", "label": "All lights"},
                            {"value": "strobes", "label": "Strobes only"}]}],
    "handler": toggle_lights,
}
