"""
CLIMB / DESCEND TO - change height while the aircraft is already flying.

Added 12 Oct 2026. Until now the only altitude control was the climb box
on TAKEOFF, and that only does anything from the ground: PX4 reads it as a
takeoff target and refuses to descend to it. Airborne there was no way to
change height at all, which is how an instructor ended up stuck at 20 m
with FORWARD FLIGHT refusing to transition below 40 m.

The command is MAV_CMD_DO_CHANGE_ALTITUDE (186). PX4 v1.15.4 treats it as
a reposition that only moves the altitude - navigator_main.cpp line 417:

        // A VEHICLE_CMD_DO_CHANGE_ALTITUDE has the exact same effect as a
        // VEHICLE_CMD_DO_REPOSITION with only the altitude field populated

It keeps the current latitude and longitude (lines 423-424), takes param1
as the new height ABOVE SEA LEVEL (line 425), and Commander switches the
aircraft into Hold to fly it (Commander.cpp lines 767-776).

Two things follow from the source and both are enforced here:

  * it only works ARMED - navigator_main.cpp line 412 tests the arming
    state before touching the setpoint, so a command sent on the ground is
    silently dropped;
  * the number is above SEA LEVEL, and an instructor thinks in height
    above the ground they are standing on. Home's own sea-level height is
    the difference between the two altitudes PX4 already reports, so the
    conversion is exact rather than a guess.

NOT YET FLOWN.
"""
from simulator_link import (home_amsl, log_instructor_action,
                            send_command_and_wait, status_since, telemetry)
import time

# MAV_CMD_DO_CHANGE_ALTITUDE. Sent by number: the pymavlink dialect
# bundled here is too old to name it.
MAV_CMD_DO_CHANGE_ALTITUDE = 186
MAV_FRAME_GLOBAL = 0

DEFAULT_ALT_M = 60.0
MIN_ALT_M = 5.0
# The station enforces a 120 m ceiling (CAP722B 5.3(c)).
MAX_ALT_M = 120.0


def climb_to(altitude_m=DEFAULT_ALT_M):
    try:
        target_agl = float(altitude_m)
    except (TypeError, ValueError):
        return f"Not sent - '{altitude_m}' is not a height in metres."
    if not MIN_ALT_M <= target_agl <= MAX_ALT_M:
        return (f"Not sent - the height must be between {MIN_ALT_M:g} m and "
                f"{MAX_ALT_M:g} m above home.")

    if not telemetry.get("armed"):
        return ("Not sent - the aircraft is disarmed. PX4 ignores an altitude "
                "change unless it is armed, so this would do nothing.")

    ground = home_amsl()
    if ground is None:
        return "Not sent - no altitude reading from the aircraft yet."

    now_agl = telemetry.get("altitude_m")
    target_amsl = ground + target_agl
    started = time.monotonic()

    result, text = send_command_and_wait(
        MAV_CMD_DO_CHANGE_ALTITUDE,
        target_amsl,        # param1: new height above sea level
        MAV_FRAME_GLOBAL)   # param2: the frame that number is in

    log_instructor_action(
        "climb_to",
        f"from_agl_m={now_agl} to_agl_m={target_agl:g} "
        f"to_amsl_m={target_amsl:.1f} result={text}")

    if result != 0:  # MAV_RESULT_ACCEPTED
        if result is None:
            return "Not confirmed - PX4 did not acknowledge."
        return f"PX4 refused the altitude change ({text})."

    time.sleep(0.8)
    said = status_since(started, ("altitude", "geofence", "reject"))
    note = ("  PX4: " + " / ".join(said[-2:])) if said else ""
    way = "Climbing" if (now_agl is None or target_agl > now_agl) else "Descending"
    return (f"{way} to {target_agl:g} m above home "
            f"({target_amsl:.0f} m above sea level). The aircraft holds its "
            f"position while it does.{note}")


PLUGIN = {
    "id": "climb_to",
    "label": "CLIMB / DESCEND TO",
    "category": "Flight Ops",
    "style": "normal",
    "inputs": [{"name": "altitude_m", "label": "Height (m)", "default": 60,
                "min": 5, "max": 120, "step": 5}],
    "handler": climb_to,
}
