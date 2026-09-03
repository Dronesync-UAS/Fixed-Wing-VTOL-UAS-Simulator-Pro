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

from simulator_link import master, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_MOTOR = 10
FAILURE_TYPE_OFF = 1
FAILURE_TYPE_OK = 0
PUSHER_MOTOR_INDEX = 4  # the forward pusher/puller motor, not a hover rotor

state = {"active": False}


def _send(failure_type):
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_INJECT_FAILURE,
        0, FAILURE_UNIT_SYSTEM_MOTOR, failure_type, PUSHER_MOTOR_INDEX, 0, 0, 0, 0)


def toggle_engine_failure():
    if state["active"]:
        _send(FAILURE_TYPE_OK)
        state["active"] = False
        mark_failure_cleared("engine_pusher")
        return "Engine (pusher) failure cleared. Requires visual confirmation in Gazebo."
    else:
        _send(FAILURE_TYPE_OFF)
        state["active"] = True
        mark_failure_injected("engine_pusher")
        return "Engine (pusher) failure injected. Requires visual confirmation in Gazebo."


PLUGIN = {
    "id": "engine_failure", "label": "Engine Failure", "category": "Failure Injection",
    "style": "warning", "handler": toggle_engine_failure,
}
