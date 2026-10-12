"""
FORWARD FLIGHT - the whole departure, not just the transition.

REBUILT 12 Oct 2026. It used to refuse below 40 m and leave the
instructor to find the climb themselves - and until today there was no
control that could climb an airborne aircraft, so the button was simply
unusable from a 20 m hover. Asked for instead: press it at 20 m and have
the aircraft climb away in a straight line to cruise height, transitioning
on the way.

THE SEQUENCE, and why it is in this order:

  1. If PX4 is in Takeoff, Land, RTL or Orbit, switch to Hold. PX4 refuses
     a transition to fixed wing in exactly those four modes -
     vtol_att_control_main.cpp v1.15.4 lines 171-178:

         // deny transition from MC to FW in Takeoff, Land, RTL and Orbit

  2. Fly a straight climbing run to the transition height, on the current
     heading. MAV_CMD_DO_REPOSITION, lat/lon a set distance ahead and the
     altitude set - so the aircraft goes forward and up together rather
     than climbing on the spot. Param2 must have bit 0 set or Commander
     answers UNSUPPORTED without doing anything (Commander.cpp lines
     748-753) - a trap worth knowing about.

  3. Wait until it is there. The transition needs the height because the
     aircraft pitches down to build airspeed, losing some of it.

  4. Transition to fixed wing.

  5. Once the transition is done, carry on climbing in the same direction
     to cruise height.

Steps 2 to 5 run on a background thread, because a button handler has to
answer at once; where the sequence has got to shows on the console.

THE RUN LENGTH is kept inside the station's 500 m range limit, so a
departure cannot breach CAP722B 5.3(c) on its own. Fixed wing will carry
on past the last waypoint, so the instructor still has to fly it.

NOT YET FLOWN. Every step is read off the PX4 source; none of it has been
watched in Gazebo.
"""
from simulator_link import (home_amsl, log_instructor_action, offset_latlon,
                            send_command_and_wait, say_step, sequence_running,
                            set_mode, start_sequence, telemetry, wait_until)
from pymavlink import mavutil

PX4_MAIN_MODE_AUTO = 4
PX4_SUB_MODE_AUTO_LOITER = 3
MAV_VTOL_STATE_FW = 4

NAN = float("nan")

# PX4 refuses a transition to fixed wing in these four modes.
BLOCKS_TRANSITION = ("Takeoff", "Land", "Return to Launch", "Orbit")

DEFAULT_TRANSITION_M = 40.0
DEFAULT_CRUISE_M = 100.0
# Below this the aircraft has no height to trade for airspeed during the
# transition. 40 m is this project's own figure, not one from a standard.
MIN_TRANSITION_M = 30.0
MAX_CRUISE_M = 120.0           # the station's ceiling, CAP722B 5.3(c)

# How far ahead each leg is aimed. Both inside the 500 m range limit.
CLIMB_RUN_M = 200.0
CRUISE_RUN_M = 420.0

REPOSITION_CHANGE_MODE = 1     # param2 bit 0: "change mode to guided"


def _reposition(distance_m, target_agl, ground):
    """Aim at a point `distance_m` ahead on the current heading, at
    `target_agl` above home. Returns a problem string, or None."""
    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None:
        return "Forward flight stopped - lost the aircraft's position."
    heading = telemetry.get("heading_deg") or 0
    to_lat, to_lon = offset_latlon(lat, lon, heading, distance_m)
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_DO_REPOSITION,
        -1,                        # param1: ground speed, -1 = PX4's default
        REPOSITION_CHANGE_MODE,    # param2: see the note above - must be 1
        0,                         # param3: unused
        NAN,                       # param4: yaw, NaN = leave it alone
        to_lat, to_lon,            # param5/6: where to go
        ground + target_agl)       # param7: height above SEA LEVEL
    if result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return f"Forward flight stopped - PX4 refused the climb ({text})."
    return None


def forward_flight(transition_m=DEFAULT_TRANSITION_M, cruise_m=DEFAULT_CRUISE_M):
    try:
        transition_alt = float(transition_m)
        cruise_alt = float(cruise_m)
    except (TypeError, ValueError):
        return f"Not sent - '{transition_m}' / '{cruise_m}' are not heights."
    if transition_alt < MIN_TRANSITION_M:
        return (f"Not sent - transitioning below {MIN_TRANSITION_M:g} m leaves "
                "no height to trade for airspeed.")
    if not transition_alt <= cruise_alt <= MAX_CRUISE_M:
        return (f"Not sent - cruise height must be between the transition "
                f"height and the {MAX_CRUISE_M:g} m ceiling.")

    if not telemetry.get("armed"):
        return "Not sent - the aircraft is disarmed."
    if telemetry.get("in_air") is False:
        return ("Not sent - the aircraft is still on the ground. Take off "
                "first, then press this.")
    ground = home_amsl()
    alt = telemetry.get("altitude_m")
    if ground is None or alt is None:
        return "Not sent - no altitude reading from the aircraft yet."
    if sequence_running():
        return "Not sent - a manoeuvre is already running. Wait for it to finish."

    if telemetry.get("vtol_state") == "Fixed wing":
        return "Already in fixed wing."

    def step_clear_mode():
        if telemetry.get("mode") in BLOCKS_TRANSITION:
            say_step("Forward flight: leaving %s, which blocks the transition"
                     % telemetry.get("mode"))
            set_mode(PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LOITER, name="HOLD")
            wait_until(lambda: telemetry.get("mode") not in BLOCKS_TRANSITION, 4)
        return None

    def step_climb_to_transition():
        if telemetry.get("altitude_m", 0) >= transition_alt - 2:
            return None
        say_step(f"Forward flight: climbing to {transition_alt:g} m")
        return _reposition(CLIMB_RUN_M, transition_alt, ground)

    def step_wait_for_height():
        if telemetry.get("altitude_m", 0) >= transition_alt - 2:
            return None
        reached = wait_until(
            lambda: (telemetry.get("altitude_m") or 0) >= transition_alt - 2, 90)
        if not reached:
            return (f"Forward flight stopped - still below {transition_alt:g} m "
                    "after 90 seconds. Check the aircraft is climbing.")
        return None

    def step_transition():
        say_step("Forward flight: transitioning to fixed wing")
        result, text = send_command_and_wait(
            mavutil.mavlink.MAV_CMD_DO_VTOL_TRANSITION,
            MAV_VTOL_STATE_FW,   # param1: target VTOL state
            0)                   # param2: 0 = normal, speed-based transition
        if result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            return (f"Forward flight stopped - PX4 refused the transition "
                    f"({text}) in {telemetry.get('mode')} mode.")
        wait_until(lambda: telemetry.get("vtol_state") == "Fixed wing", 60)
        return None

    def step_climb_to_cruise():
        say_step(f"Forward flight: climbing away to {cruise_alt:g} m")
        problem = _reposition(CRUISE_RUN_M, cruise_alt, ground)
        if problem:
            return problem
        wait_until(lambda: (telemetry.get("altitude_m") or 0) >= cruise_alt - 5, 120)
        say_step(None)
        return None

    started = start_sequence("forward_flight", [
        step_clear_mode, step_climb_to_transition, step_wait_for_height,
        step_transition, step_climb_to_cruise])
    if not started:
        return "Not sent - a manoeuvre is already running."

    log_instructor_action(
        "forward_flight",
        f"from_agl_m={alt} transition_m={transition_alt:g} cruise_m={cruise_alt:g}")
    if alt >= transition_alt - 2:
        return (f"Forward flight from {alt:g} m: transitioning to fixed wing, "
                f"then climbing away to {cruise_alt:g} m.")
    return (f"Forward flight from {alt:g} m: climbing straight ahead to "
            f"{transition_alt:g} m, transitioning to fixed wing there, then "
            f"on up to {cruise_alt:g} m. Watch the step shown under the gauge.")


PLUGIN = {
    "id": "forward_flight",
    "label": "FORWARD FLIGHT (FW)",
    "category": "Flight Mode",
    "style": "highlight",
    "inputs": [
        {"name": "transition_m", "label": "Transition at (m)", "default": 40,
         "min": 30, "max": 120, "step": 5},
        {"name": "cruise_m", "label": "Cruise at (m)", "default": 100,
         "min": 30, "max": 120, "step": 10},
    ],
    "handler": forward_flight,
}
