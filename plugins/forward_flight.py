"""
"Forward flight" button for the standard VTOL - added 3 Sep 2026,
revised same day to use Stabilized on instructor request.

Sequence:
  1. Stabilized mode - PX4's attitude-stabilised manual mode. In fixed
     wing this is the closest equivalent to ArduPlane's FBWA: the
     autopilot holds the aircraft level and it flies straight ahead with
     no stick input, but a student can hand-fly it.
  2. Multicopter -> fixed-wing transition.

Guards:
  * won't transition below MIN_TRANSITION_ALT_M - the aircraft pitches
    down to build airspeed during the transition and needs the height.
  * PX4 refuses a FW transition while in Takeoff, Land, RTL or Orbit
    (vtol_att_control_main.cpp). If the aircraft is orbiting (e.g. after
    the LOITER button), press HOLD first, then this.
"""
from simulator_link import send_command_and_wait, set_mode, log_instructor_action, telemetry
from pymavlink import mavutil

PX4_MAIN_MODE_STABILIZED = 7      # px4_custom_mode.h
MAV_VTOL_STATE_FW = 4             # MAV_VTOL_STATE enum

MIN_TRANSITION_ALT_M = 40         # above home, before we allow FW transition


def forward_flight():
    alt = telemetry.get("altitude_m")
    if alt is None:
        return "Forward flight not sent - no altitude reading yet."
    if alt < MIN_TRANSITION_ALT_M:
        return (f"Forward flight not sent - only {alt:g} m above home. "
                f"Climb to at least {MIN_TRANSITION_ALT_M} m first.")

    # 1. Stabilized (attitude-stabilised forward flight)
    mode_result = set_mode(PX4_MAIN_MODE_STABILIZED, name="Stabilized")

    # 2. Transition to fixed wing
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_DO_VTOL_TRANSITION,
        MAV_VTOL_STATE_FW,   # param1: target VTOL state
        0)                   # param2: 0 = normal (speed-based) transition

    log_instructor_action("vtol_transition",
                          f"target=fixed_wing mode=stabilized alt_m={alt:g} "
                          f"{mode_result} result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return f"Forward flight ({alt:g} m): {mode_result} Transitioning to fixed wing."
    if result is None:
        return f"{mode_result} No acknowledgement of the transition from PX4."
    # The guard in this file's docstring is the usual cause.
    return (f"{mode_result} PX4 refused the transition ({text}) - it blocks "
            "transitions during Takeoff, Land, RTL and Orbit. Press HOLD first.")


PLUGIN = {
    "id": "forward_flight",
    "label": "FORWARD FLIGHT (FW)",
    "category": "Flight Mode",
    "style": "highlight",
    "handler": forward_flight,
}
