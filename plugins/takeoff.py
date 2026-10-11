from simulator_link import (master, send_command_and_wait, log_instructor_action,
                            telemetry)
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

    # FIXED 11 Oct 2026: this used to fire the command and report success
    # regardless, so a takeoff PX4 refused looked like a button that did
    # nothing - and gave the instructor no way to find out why. PX4 answers
    # every command with a COMMAND_ACK; report what it actually said.
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0, 0, 0, 0, 0, 0, target_amsl)
    log_instructor_action("takeoff",
                          f"climb_m={CLIMB_ABOVE_CURRENT_M} "
                          f"target_amsl_m={target_amsl} result={text}")

    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return f"Taking off - climbing {CLIMB_ABOVE_CURRENT_M} m above the current position."
    if result is None:
        return ("Takeoff not confirmed - PX4 did not acknowledge. Check the "
                "simulator is still running.")
    if telemetry.get("armed") is False:
        return (f"PX4 refused the takeoff ({text}) - the aircraft is disarmed. "
                "Arming is usually blocked by a preflight check; the simulator "
                "console lists them with 'commander check'.")
    return f"PX4 refused the takeoff ({text})."


PLUGIN = {"id": "takeoff", "label": "TAKEOFF", "category": "Flight Ops", "style": "normal", "handler": takeoff}
