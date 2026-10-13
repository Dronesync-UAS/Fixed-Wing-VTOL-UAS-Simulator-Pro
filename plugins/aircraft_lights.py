"""
AIRCRAFT LIGHTS - on and off.

The lights are added to the model by tools/aircraft_lights_apply.py, which
explains the colours, and driven by aircraft_lights.py, which explains the
flash pattern. The short version, because it is the part a student gets
asked: RED to port, GREEN to starboard, WHITE at the tail, all steady;
white strobes double-flashing; a red beacon while armed. Red on your left
and green on your right means the aircraft is coming towards you.

This file is only the button.
"""
import aircraft_lights
from simulator_link import log_instructor_action

state = {"active": False}


def toggle_lights(on=None):
    """Switch the lights. No argument means toggle, which is what the rail
    button does; the settings switch sends on=1 or on=0 so that a checkbox
    and the lights cannot disagree about which way round they are."""
    if on is None:
        wanted = not state["active"]
    else:
        wanted = str(on).lower() in ("1", "true", "on", "yes")
    problem = aircraft_lights.set_on(wanted)
    if problem and wanted:
        return (f"Lights not switched on - {problem}. Have they been added "
                "to the aircraft? Run tools/aircraft_lights_apply.py, then "
                "restart the simulator.")
    state["active"] = wanted
    log_instructor_action("aircraft_lights", f"on={wanted}")
    if wanted:
        # Kept in step with what the aircraft actually carries. The wingtip
        # navigation lights were removed on 13 Oct 2026 and the tail light
        # became the GPS indicator; this text still described the old set
        # until 14 Oct, which is the kind of thing a student reads and
        # believes.
        return ("Lights on. White strobes double-flashing above and below, "
                "and the red beacon flashes while the aircraft is armed. "
                "The tail light is the GPS indicator: flashing GREEN with a "
                "fix, flashing RED if GPS is lost. Set the lighting to "
                "Night to see them properly.")
    return "Lights off."


PLUGIN = {
    "id": "aircraft_lights",
    "label": "Aircraft lights",
    "category": "Simulation Control",
    "style": "normal",
    "handler": toggle_lights,
}
