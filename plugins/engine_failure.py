"""
Engine (pusher motor) failure / restoration - separate from the
hover-motor failure plugin, for practicing the specific "engine out in
forward flight" scenario.

REVISED 23 Aug 2026: converted to a toggle (press once to fail, press
again to restore), for the same reason as motor_failure.py - a live
test that day showed there was previously no way to recover the
aircraft from this failure without fully restarting PX4/Gazebo.

Numeric codes corrected earlier the same day - see motor_failure.py.
"""

from simulator_link import send_command_and_wait, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_MOTOR = 10
FAILURE_TYPE_OFF = 1
FAILURE_TYPE_OK = 0
PUSHER_MOTOR_INDEX = 4  # the forward pusher/puller motor, not a hover rotor

state = {"active": False}


# FIXED 11 Oct 2026: fired blind and always claimed success. Now reports PX4's
# acknowledgement - with the caveat that MAV_CMD_INJECT_FAILURE is documented
# in this project's 10 Aug entry as accepted-but-ineffective on this PX4
# version (the reason the GPS dropout proxy exists), so "accepted" here means
# PX4 took the command, not that the failure is visible. Needs live
# confirmation per failure type.


def _send(failure_type):
    """Returns a message describing what PX4 said."""
    result, text = send_command_and_wait(
        MAV_CMD_INJECT_FAILURE, FAILURE_UNIT_SYSTEM_MOTOR, failure_type, PUSHER_MOTOR_INDEX, 0, 0, 0, 0)
    if result == 0:  # MAV_RESULT_ACCEPTED
        return None
    if result is None:
        return "no acknowledgement from PX4"
    return f"PX4 {text} the command"


def toggle_engine_failure():
    if state["active"]:
        problem = _send(FAILURE_TYPE_OK)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not cleared - {problem}."
        state["active"] = False
        mark_failure_cleared("engine_pusher")
        return "Engine (pusher) failure cleared. Requires visual confirmation in Gazebo."
    else:
        problem = _send(FAILURE_TYPE_OFF)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = True
        mark_failure_injected("engine_pusher")
        return "Engine (pusher) failure injected. Requires visual confirmation in Gazebo."


PLUGIN = {
    "id": "engine_failure", "label": "Engine Failure", "category": "Failure Injection",
    "style": "warning", "handler": toggle_engine_failure,
}
