"""
"Hover flight" button - transitions the standard VTOL back from fixed
wing to multicopter (hover). Added 3 Sep 2026 alongside FORWARD FLIGHT so
there is an obvious way back to hover during training.
"""
from simulator_link import master, log_instructor_action
from pymavlink import mavutil

MAV_VTOL_STATE_MC = 3  # MAV_VTOL_STATE enum


def hover_flight():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_VTOL_TRANSITION,
        0,
        MAV_VTOL_STATE_MC,   # param1: target VTOL state
        0,                   # param2: 0 = normal transition
        0, 0, 0, 0, 0)
    log_instructor_action("vtol_transition", "target=multicopter")
    return "Transitioning back to multicopter (hover)."


PLUGIN = {
    "id": "hover_flight",
    "label": "HOVER FLIGHT (MC)",
    "category": "Flight Mode",
    "style": "highlight",
    "handler": hover_flight,
}
