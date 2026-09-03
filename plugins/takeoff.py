from simulator_link import master, log_instructor_action, telemetry
from pymavlink import mavutil

CLIMB_ABOVE_CURRENT_M = 20

# FIXED 23 Aug 2026: this used to send a hardcoded "20" as the target
# altitude. PX4 treats that number as an absolute height above sea level,
# not "climb 20m from here" - fine on a near-sea-level world, but this
# training area's real Hoggar Mountains location sits at roughly 2000m
# above sea level, so a plain "20" told PX4 to descend about 2km below
# where it already was. PX4 correctly refused every time with "Already
# higher than takeoff altitude (not descending)" - confirmed by testing
# QGroundControl's own Takeoff button (which computes this correctly)
# against this same aircraft, which took off normally. Now reads the
# aircraft's real current height above sea level from telemetry and adds
# the intended climb to it, matching what QGroundControl does.


def takeoff():
    current_amsl = telemetry.get("altitude_amsl_m")
    if current_amsl is None:
        return ("Takeoff not sent - no altitude reading from the aircraft yet. "
                "Wait a couple of seconds for telemetry to connect and try again.")

    target_amsl = current_amsl + CLIMB_ABOVE_CURRENT_M
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, 0, target_amsl)
    log_instructor_action("takeoff", f"climb_m={CLIMB_ABOVE_CURRENT_M} target_amsl_m={target_amsl}")
    return f"Takeoff command sent (climbing {CLIMB_ABOVE_CURRENT_M}m above current position)."


PLUGIN = {"id": "takeoff", "label": "TAKEOFF", "category": "Flight Ops", "style": "normal", "handler": takeoff}
