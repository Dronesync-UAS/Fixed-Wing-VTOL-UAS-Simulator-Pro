"""
"Loiter" button with an instructor-set radius - added 3 Sep 2026 on
request. Uses MAV_CMD_DO_ORBIT around the aircraft's current position:

  * multicopter: orbits at the given radius (PX4 clamps it to
    [~1 m, MC_ORBIT_RAD_MAX], default max 1000 m)
  * fixed wing: loiters in a circle of the given radius

The radius comes from the number box next to the button on the console.
A negative radius makes PX4 orbit counter-clockwise; this button keeps it
positive (clockwise) and validates the input before sending anything.
"""
from simulator_link import master, log_instructor_action

DEFAULT_RADIUS_M = 150.0
NAN = float("nan")

# The pymavlink dialect bundled here (ardupilotmega v1.0) is too old to
# name MAV_CMD_DO_ORBIT, so use its numeric id directly - PX4 handles the
# command by number regardless.
MAV_CMD_DO_ORBIT = 34


def loiter(radius_m=DEFAULT_RADIUS_M):
    try:
        radius = float(radius_m)
    except (TypeError, ValueError):
        return f"Loiter not sent - '{radius_m}' is not a valid radius in metres."
    if not radius > 0:
        return "Loiter not sent - radius must be greater than 0 m."

    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_DO_ORBIT,
        0,
        radius,   # param1: radius (m), positive = clockwise
        NAN,      # param2: tangential speed - let PX4 pick a default
        0,        # param3: yaw behaviour (0 = face circle centre)
        NAN,      # param4: number of orbits (NaN = unlimited)
        NAN, NAN, NAN)  # param5-7: centre lat/lon/alt (NaN = current position)

    log_instructor_action("loiter", f"radius_m={radius:g}")
    return f"Loitering in a {radius:g} m circle around the current position."


PLUGIN = {
    "id": "loiter",
    "label": "LOITER",
    "category": "Flight Mode",
    "style": "normal",
    "inputs": [{"name": "radius_m", "label": "Radius (m)", "default": 150, "min": 10, "step": 10}],
    "handler": loiter,
}
