"""
Flight termination - the control a parachute-equipped UAS actually has.

WHAT IT DOES, AND WHAT IT DOES NOT
----------------------------------
Pressing this twice sends MAV_CMD_DO_FLIGHTTERMINATION. PX4 v1.15.4 puts the
aircraft into NAVIGATION_STATE_TERMINATION: control stops, outputs go to
their failsafe values, and the airframe falls.

It does NOT make a canopy appear in Gazebo. There is no parachute on this
model and nothing in the simulator to deploy one.

WHY THE BUTTON IS NOT CALLED "PARACHUTE"
----------------------------------------
Because sending MAV_CMD_DO_PARACHUTE to PX4 would do nothing at all, and a
button that silently does nothing is the exact fault this project spent
11 Oct 2026 removing from the motor tests. Read against PX4 v1.15.4:

  Commander.cpp:961   handles VEHICLE_CMD_DO_FLIGHTTERMINATION - with
                      param1 > 0.5 and the aircraft armed, it changes the
                      navigation state to TERMINATION.
  Commander.cpp:1885  that state sets actuator_armed.force_failsafe.
  Commander.cpp:1888  on force_failsafe going true while armed, PX4 calls
                      send_parachute_command().
  Commander.cpp:2960  which PUBLISHES VEHICLE_CMD_DO_PARACHUTE outwards, to
                      target_component 161 (MAV_COMP_ID_PARACHUTE).

So PX4 is the sender of the parachute command, not its receiver. The real
aircraft's chute is a separate MAVLink component that listens on 161; the
simulator has no such component. Terminating the flight is therefore the
honest, working half of this control, and it is the half that trains the
decision - a student watching the aircraft stop flying is the point.

GUARDED ON PURPOSE
------------------
Two presses within 10 seconds. There is no undo in the air: PX4 will not
leave TERMINATION, so the only way back is Reset Scenario. A single
mis-click ending a lesson is worse than an extra click every time.
"""

import time

from pymavlink import mavutil

from simulator_link import send_command_and_wait, log_instructor_action, telemetry

MAV_CMD_DO_FLIGHTTERMINATION = 185

# How long an arming press stays live. Long enough to be a deliberate
# double-press, short enough that a forgotten one cannot fire later.
ARM_WINDOW_S = 10.0

state = {"active": False, "armed_at": None}


def _armed_recently():
    at = state["armed_at"]
    return at is not None and (time.monotonic() - at) < ARM_WINDOW_S


def terminate_flight():
    if not _armed_recently():
        state["armed_at"] = time.monotonic()
        return (f"Flight termination ARMED - press again within {ARM_WINDOW_S:.0f} "
                "seconds to terminate. The aircraft will stop flying and fall; "
                "only Reset Scenario recovers it.")

    state["armed_at"] = None

    if telemetry.get("armed") is False:
        return ("Flight termination not sent - the aircraft is disarmed, and PX4 "
                "refuses termination unless it is armed.")

    # param1 > 0.5 is the real termination; 0 is the "off" that PX4 accepts
    # but does not act on once terminated.
    result, text = send_command_and_wait(MAV_CMD_DO_FLIGHTTERMINATION, 1.0)
    log_instructor_action("flight_termination", f"result={text}")

    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        state["active"] = True
        return ("Flight TERMINATED. PX4 has cut control and emitted its parachute "
                "release command - no canopy appears in the simulator. "
                "Reset Scenario to fly again.")
    if result is None:
        return ("Flight termination not confirmed - PX4 did not acknowledge. "
                "Check the simulator is still running.")
    return f"PX4 refused the flight termination ({text})."


PLUGIN = {
    "id": "flight_termination",
    "label": "TERMINATE FLIGHT",
    # Its own section at the foot of the left rail. In "Flight Ops" the
    # plugins load in filename order, which put this between DISARM and
    # HOLD - the worst place on the console for a control with no undo.
    "category": "Emergency",
    "style": "danger",
    "handler": terminate_flight,
}
