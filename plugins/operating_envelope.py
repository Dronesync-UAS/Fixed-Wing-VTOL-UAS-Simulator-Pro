"""
OPERATING ENVELOPE - the CAA 500 m limit, or 100 km for instructor
cross-country work.

NAMED FOR THE CONTROL, NOT THE MODULE. The envelopes live in
range_profile.py at the top level; this file is deliberately NOT called
range_profile.py as well. The plugin loader names each module after its
own filename, and two modules called range_profile - one importing the
other - is a circular import waiting for whoever next puts plugins/ on
the path.

Added 12 Oct 2026 on request. The two envelopes themselves, and why only
the range changes, are in range_profile.py at the top level; this file is
just the control that picks between them.

WHY IT IS IN SETTINGS AND NOT ON A RAIL. It is not a flying command. It
is set once at the top of a lesson, by the instructor, and it changes
what the warnings mean for the rest of that lesson - which is exactly the
kind of thing that should take two clicks and a panel, not one click on a
button sitting next to LAND.

THE STATION'S OWN LIMITS DICT is updated here rather than re-read,
because every warning, the altitude tape and the flight log all read that
one dict. Updating it in place means the change takes effect on the next
telemetry poll with nothing to restart.

NOT TESTED AGAINST A RUNNING SIMULATOR.
"""
import range_profile


def set_profile(profile="caa"):
    ok, message = range_profile.choose(profile)
    if not ok:
        return message

    # The station's LIMITS dict, found through the already-imported
    # module rather than imported at the top of this file: plugins are
    # loaded BY the station, so importing it here would be a cycle.
    import sys
    station = sys.modules.get("instructor_station") or sys.modules.get("__main__")
    limits = getattr(station, "LIMITS", None)
    if isinstance(limits, dict):
        limits.update(range_profile.limits())
    else:
        return (message + "  WARNING: the station's limits were not found, "
                "so the warnings are still using the old envelope. "
                "Restart the station.")
    return message


PLUGIN = {
    "id": "operating_envelope",
    "label": "Operating envelope",
    "category": "Simulation Control",
    "style": "normal",
    # A setting, not an action: it applies the moment its value
    # changes rather than waiting for its own button.
    "apply_on_change": True,
    "inputs": [{"name": "profile", "label": "Envelope", "type": "select",
                "default": range_profile.active_key(),
                "options": [{"value": key,
                             "label": range_profile.PROFILES[key]["label"]}
                            for key in ("caa", "extended")]}],
    "handler": set_profile,
}
