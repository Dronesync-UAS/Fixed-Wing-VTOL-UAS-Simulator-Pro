"""
"Hover flight" button - transitions the standard VTOL back from fixed
wing to multicopter (hover). Added 3 Sep 2026 alongside FORWARD FLIGHT so
there is an obvious way back to hover during training.
"""
from simulator_link import (cancel_sequence, log_instructor_action,
                            say_step, send_command_and_wait)
from pymavlink import mavutil

MAV_VTOL_STATE_MC = 3  # MAV_VTOL_STATE enum

# FIXED 11 Oct 2026: fired the command and reported success regardless, so a
# command PX4 refused was indistinguishable from one it obeyed. PX4 answers
# every command with a COMMAND_ACK - report what it actually said.


def hover_flight():
    # A FORWARD FLIGHT still part-way through its climb would otherwise go
    # on commanding the aircraft away after this brought it back to hover.
    cancel_sequence()
    say_step(None)
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_DO_VTOL_TRANSITION,
        MAV_VTOL_STATE_MC,   # param1: target VTOL state
        0)                   # param2: 0 = normal transition
    log_instructor_action("vtol_transition", f"target=multicopter result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "Transitioning back to multicopter (hover)."
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    # PX4 blocks VTOL transitions in Takeoff, Land, RTL and Orbit
    # (vtol_att_control_main.cpp), which is the usual reason this is refused.
    return (f"PX4 refused the transition ({text}). It blocks transitions "
            "during Takeoff, Land, RTL and Orbit - press HOLD first.")


PLUGIN = {
    "id": "hover_flight",
    "label": "HOVER FLIGHT (MC)",
    "category": "Flight Mode",
    "style": "highlight",
    "handler": hover_flight,
}
