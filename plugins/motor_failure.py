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
"""

from simulator_link import master, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_MOTOR = 10
FAILURE_TYPE_OFF = 1
FAILURE_TYPE_OK = 0

state = {"active": False}


def _send(failure_type):
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_INJECT_FAILURE,
        0, FAILURE_UNIT_SYSTEM_MOTOR, failure_type, 0, 0, 0, 0, 0)


def toggle_motor_failure():
    if state["active"]:
        _send(FAILURE_TYPE_OK)
        state["active"] = False
        mark_failure_cleared("motor")
        return "Motor failure cleared (motor 0). Requires visual confirmation in Gazebo."
    else:
        _send(FAILURE_TYPE_OFF)
        state["active"] = True
        mark_failure_injected("motor")
        return "Motor failure injected (motor 0). Requires visual confirmation in Gazebo."


PLUGIN = {
    "id": "motor_failure", "label": "Motor Failure", "category": "Failure Injection",
    "style": "warning", "handler": toggle_motor_failure,
}
