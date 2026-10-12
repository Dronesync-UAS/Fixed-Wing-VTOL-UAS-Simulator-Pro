"""
Motor failure injection / restoration. Uses MAV_CMD_INJECT_FAILURE.

REVISED 23 Aug 2026: this used to be one-shot (inject only, no way to
switch it off again). A live test that day showed the real problem with
that: once triggered, there was no way to recover the aircraft without
fully restarting PX4/Gazebo, because "Reset Scenario" only disarms and
repositions the airframe - it doesn't undo an actuator failure already
injected inside PX4 itself. This is now a toggle, matching GPS/RC
Signal/Data Link: press once to fail, press again to restore.

Numeric codes (FAILURE_UNIT_SYSTEM_MOTOR=10, FAILURE_TYPE_OFF=1,
FAILURE_TYPE_OK=0) were corrected earlier the same day against MAVLink's
own enum definitions - they were previously 8 and 2, which actually mean
"airspeed sensor" and "stuck", not "motor" and "off".

FIXED 12 Oct 2026 - THE UNIT NUMBER WAS NOT A REAL ONE. This sent 10 as
MAV_CMD_INJECT_FAILURE's failure unit. The MAVLink FAILURE_UNIT enum, and
PX4 v1.15.4's own copy of it in msg/VehicleCommand.msg lines 130-144, do
not define 10 at all - the system units start at 100:

    uint8 FAILURE_UNIT_SYSTEM_BATTERY = 100
    uint8 FAILURE_UNIT_SYSTEM_MOTOR = 101
    uint8 FAILURE_UNIT_SYSTEM_SERVO = 102
    uint8 FAILURE_UNIT_SYSTEM_AVOIDANCE = 103
    uint8 FAILURE_UNIT_SYSTEM_RC_SIGNAL = 104
    uint8 FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 105

A comment in this file claimed the numbers had been "cross-checked against
MAVLink's own enum definitions". They had not. The correct number is now
used, from simulator_link rather than copied into each plugin again.

The injection is also gated behind PX4's SYS_FAILURE_EN parameter, which
is 0 by default - failure.cpp lines 163-171 refuses outright when it is
not 1. That is now checked and said out loud, instead of the button
appearing to work and nothing happening.

NOT YET CONFIRMED IN FLIGHT with the corrected number.
"""

from simulator_link import (FAILURE_TYPE_OFF, FAILURE_TYPE_OK,
                            MAV_CMD_INJECT_FAILURE, FAILURE_UNIT_SYSTEM_MOTOR,
                            failure_injection_blocked,
                            mark_failure_cleared, mark_failure_injected,
                            send_command_and_wait)


state = {"active": False}


# FIXED 11 Oct 2026: fired blind and always claimed success. Now reports PX4's
# acknowledgement - with the caveat that MAV_CMD_INJECT_FAILURE is documented
# in this project's 10 Aug entry as accepted-but-ineffective on this PX4
# version (the reason the GPS dropout proxy exists), so "accepted" here means
# PX4 took the command, not that the failure is visible. Needs live
# confirmation per failure type.


def _send(failure_type):
    """Returns a message describing what PX4 said."""
    # PX4 ignores every injection while SYS_FAILURE_EN is 0, which is its
    # default - the button would otherwise look like it had worked.
    blocked = failure_injection_blocked()
    if blocked:
        return blocked
    result, text = send_command_and_wait(
        MAV_CMD_INJECT_FAILURE, FAILURE_UNIT_SYSTEM_MOTOR, failure_type, 0, 0, 0, 0, 0)
    if result == 0:  # MAV_RESULT_ACCEPTED
        return None
    if result is None:
        return "no acknowledgement from PX4"
    return f"PX4 {text} the command"


def toggle_motor_failure():
    if state["active"]:
        problem = _send(FAILURE_TYPE_OK)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not cleared - {problem}."
        state["active"] = False
        mark_failure_cleared("motor")
        return "Motor failure cleared (motor 0). Requires visual confirmation in Gazebo."
    else:
        problem = _send(FAILURE_TYPE_OFF)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = True
        mark_failure_injected("motor")
        return "Motor failure injected (motor 0). Requires visual confirmation in Gazebo."


PLUGIN = {
    "id": "motor_failure", "label": "Motor Failure", "category": "Failure Injection",
    "style": "warning", "handler": toggle_motor_failure,
}
