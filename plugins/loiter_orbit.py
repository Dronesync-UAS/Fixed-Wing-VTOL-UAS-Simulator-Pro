"""
LOITER - fly a circle of the instructor's chosen radius.

FIXED 12 Oct 2026: pressing this made the aircraft fly away backwards in a
straight line instead of circling.

The cause is in PX4 v1.15.4, and it is worth writing down because the old
code looked correct. It sent NaN for the orbit centre, which the MAVLink
spec says means "use the current position". PX4 does exactly that -
FlightTaskOrbit.cpp line 170, in activate():

        _center = _position;

and then flies to the nearest point on the circle
(_generate_circle_approach_setpoints, line 296):

        position_to_center_xy = center2d - Vector2f(_position);
        closest_point_on_circle = Vector2f(_position)
            + position_to_center_xy.unit_or_zero()
              * (position_to_center_xy.norm() - _orbit_radius);

With the centre ON the aircraft, position_to_center_xy is a sub-metre
scrap of estimator noise. unit_or_zero() turns that noise into a unit
vector pointing in an arbitrary direction, and (norm - radius) is about
minus the whole radius - so the target comes out one full radius away, on
a bearing decided by nothing but noise. The aircraft flies a 150 m
straight line to it. Hence "backwards, in a straight line".

The centre has to be a real point the aircraft is already standing on the
edge of. This sends one radius out to the side - to the right for a
clockwise orbit - so the aircraft is on the circle from the first instant
and flies the circle rather than a line to it.

SPEED. The old code sent NaN for the orbit speed too. PX4 only overwrites
its speed when the value is finite (FlightTaskOrbit.cpp lines 72-75), so
it kept the 1 m/s that activate() sets - a lap of a 150 m circle in a
quarter of an hour, which from the ground looks like a hover. A speed is
now sent, and PX4 still clamps it to what the radius can take.

NOT YET FLOWN. The reasoning above is read off the PX4 source; nobody has
watched the aircraft fly a circle with it.
"""
import math

from simulator_link import (log_instructor_action, offset_latlon,
                            send_command_and_wait, telemetry)

DEFAULT_RADIUS_M = 150.0
DEFAULT_SPEED_MS = 8.0
NAN = float("nan")

# The pymavlink dialect bundled here (ardupilotmega v1.0) is too old to
# name MAV_CMD_DO_ORBIT, so use its numeric id directly - PX4 handles the
# command by number regardless.
MAV_CMD_DO_ORBIT = 34

# MAVLink's ORBIT_YAW_BEHAVIOUR, checked against common.xml:
#   0 HOLD_FRONT_TO_CIRCLE_CENTER   nose at the centre (MAVLink's default)
#   3 HOLD_FRONT_TANGENT_TO_CIRCLE  nose along the flight path
# Both are offered, because they are two different exercises. Pointing at
# the centre is what you want when the camera is the point - the aircraft
# circles a thing and keeps looking at it. Pointing along the track is what
# a fixed wing does naturally and what a student flying a circuit expects.
YAW_BEHAVIOURS = {"centre": 0, "track": 3}


def loiter(radius_m=DEFAULT_RADIUS_M, speed_ms=DEFAULT_SPEED_MS, nose="centre"):
    yaw_behaviour = YAW_BEHAVIOURS.get(str(nose).lower())
    if yaw_behaviour is None:
        return f"Loiter not sent - '{nose}' is not a nose direction."
    try:
        radius = float(radius_m)
        speed = float(speed_ms)
    except (TypeError, ValueError):
        return f"Loiter not sent - '{radius_m}' / '{speed_ms}' are not numbers."
    if not radius > 0:
        return "Loiter not sent - radius must be greater than 0 m."
    if not 1.0 <= speed <= 25.0:
        return "Loiter not sent - speed must be between 1 and 25 m/s."

    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None:
        return ("Loiter not sent - no position from the aircraft yet. Wait a "
                "couple of seconds for telemetry and try again.")
    if not telemetry.get("armed"):
        return "Loiter not sent - the aircraft is disarmed."

    # One radius out to the right of the nose: for a clockwise orbit that
    # puts the aircraft on the circle travelling along it, which is how a
    # loiter is entered.
    heading = telemetry.get("heading_deg") or 0
    centre_lat, centre_lon = offset_latlon(lat, lon, heading + 90.0, radius)
    alt_amsl = telemetry.get("altitude_amsl_m")

    result, text = send_command_and_wait(
        MAV_CMD_DO_ORBIT,
        radius,            # param1: radius (m); positive = clockwise
        speed,             # param2: tangential speed (m/s)
        yaw_behaviour,     # param3: yaw behaviour - see the note above
        NAN,               # param4: number of orbits (NaN = unlimited)
        centre_lat,        # param5: centre latitude
        centre_lon,        # param6: centre longitude
        alt_amsl if alt_amsl is not None else NAN)   # param7: centre altitude

    log_instructor_action(
        "loiter",
        f"radius_m={radius:g} speed_ms={speed:g} nose={nose} "
        f"centre={centre_lat:.6f},{centre_lon:.6f} result={text}")
    if result == 0:  # MAV_RESULT_ACCEPTED
        facing = ("nose pointing at the centre" if nose == "centre"
                  else "nose along the track")
        return (f"Loitering clockwise in a {radius:g} m circle at {speed:g} m/s, "
                f"{facing}. The centre is one radius off the right wing of "
                "where the aircraft was - not the home point.")
    if result is None:
        return "Loiter not confirmed - PX4 did not acknowledge."
    return (f"PX4 refused the loiter ({text}). It refuses an orbit while the "
            "aircraft is transitioning between hover and fixed wing.")


PLUGIN = {
    "id": "loiter",
    "label": "LOITER",
    "category": "Flight Mode",
    "style": "normal",
    "inputs": [
        {"name": "radius_m", "label": "Radius (m)", "default": 150, "min": 10,
         "max": 450, "step": 10},
        {"name": "speed_ms", "label": "Speed (m/s)", "default": 8, "min": 1,
         "max": 25, "step": 1},
        {"name": "nose", "label": "Nose", "type": "select", "default": "centre",
         "options": [{"value": "centre", "label": "At the centre"},
                     {"value": "track", "label": "Along the track"}]},
    ],
    "handler": loiter,
}
