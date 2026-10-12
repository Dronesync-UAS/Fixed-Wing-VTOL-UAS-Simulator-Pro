"""
CEILING - the height limit, in metres, up to 9000 ft.

Added 12 Oct 2026 on request: "in settings give an option to set
altitude up to 9000ft (also refer in meters as default)".

METRES ARE THE DEFAULT and the figure typed is metres, because that is
what every other height on this station is in - the altitude tape, the
climb control, the flight log. Feet are shown alongside, because the
request was in feet and because a student will be asked for both.

9000 ft is 2743.2 m. The limit offered is 2750 m, which is a round
number in the working unit and a little above what was asked for.

SEPARATE FROM THE OPERATING ENVELOPE on purpose. The envelope is about
DISTANCE and is a named thing that goes in the training record; the
ceiling is a number an instructor raises for one exercise. Raising it
above the 120 m a student is taught to says so in the reply and is
written to the flight log.

NOT TESTED AGAINST A RUNNING SIMULATOR.
"""
import range_profile


def set_ceiling(ceiling_m=120):
    ok, message = range_profile.set_ceiling(ceiling_m)
    if not ok:
        return message

    # The station's own LIMITS dict, which every warning, the altitude
    # tape and the flight log read. Found through the loaded module
    # rather than imported: plugins are loaded BY the station.
    import sys
    station = sys.modules.get("instructor_station") or sys.modules.get("__main__")
    limits = getattr(station, "LIMITS", None)
    if isinstance(limits, dict):
        limits.update(range_profile.limits())
    else:
        return (message + "  WARNING: the station's limits were not found, "
                "so the warnings are still using the old ceiling. Restart "
                "the station.")
    return message


PLUGIN = {
    "id": "ceiling",
    "label": "Set ceiling",
    "category": "Simulation Control",
    "style": "normal",
    # A setting, not an action: it applies the moment its value
    # changes rather than waiting for its own button.
    "apply_on_change": True,
    "inputs": [
        {"name": "ceiling_m", "label": "Ceiling (m)", "default": 120,
         "min": 30, "max": 2750, "step": 10},
    ],
    "handler": set_ceiling,
}
