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


def toggle_lights():
    wanted = not state["active"]
    problem = aircraft_lights.set_on(wanted)
    if problem and wanted:
        return (f"Lights not switched on - {problem}. Have they been added "
                "to the aircraft? Run tools/aircraft_lights_apply.py, then "
                "restart the simulator.")
    state["active"] = wanted
    log_instructor_action("aircraft_lights", f"on={wanted}")
    if wanted:
        return ("Lights on. Navigation lights steady - red to port, green to "
                "starboard, white at the tail. Strobes double-flashing. The "
                "red beacon flashes while the aircraft is armed. Set the "
                "lighting to Night to see them.")
    return "Lights off."


PLUGIN = {
    "id": "aircraft_lights",
    "label": "Aircraft lights",
    "category": "Simulation Control",
    "style": "normal",
    "handler": toggle_lights,
}
