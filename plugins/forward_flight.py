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
departure cannot breach the station's range envelope on its own. Once the
aircraft is close to that limit, or has reached cruise height, the leg
stops being extended and PX4 settles into its own fixed-wing loiter -
which is what a fixed wing does when it runs out of waypoints, and is the
point at which the instructor takes over.

FLOWN ONCE, 12 Oct 2026, AND IT WAS WRONG. The departure worked as far
as the transition, then the aircraft wound up into a steep spiral and
ended up inverted. The cause is written out above step_climb_to_cruise:
the climb-out leg was re-aimed on the aircraft's own heading once a
second, which closes a feedback loop through the airframe. That is
fixed. The fix itself has NOT been flown.
"""
from simulator_link import (home_amsl, log_instructor_action, offset_latlon,
                            send_command_and_wait, say_step, sequence_running,
                            set_mode, start_sequence, telemetry, wait_until)
from pymavlink import mavutil
import math
import time

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
# Stop extending the climb-out leg once the aircraft is this far from
# home, so a departure cannot walk itself through the 500 m range limit.
MAX_RUN_RANGE_M = 380.0

REPOSITION_CHANGE_MODE = 1     # param2 bit 0: "change mode to guided"

# Re-extend the climb-out leg only once the aircraft is within this far
# of the point it was sent to. A fixed wing cruises at about 16 m/s, so
# a 420 m leg lasts around 26 seconds; re-sending it before then just
# re-tasks the navigator for nothing.
EXTEND_WITHIN_M = 150.0

# After the transition, before any turn. PX4 declares a front transition
# complete at VT_ARSP_TRANS - 10 m/s by default, from
# vtol_att_control_params.c in v1.15.4 - which is only just wing-borne.
# A real crew accelerates straight before turning, so the station waits
# for a margin over that figure.
SETTLE_AIRSPEED_MS = 16.0
SETTLE_TIMEOUT_S = 20.0
# If there is no airspeed reading at all, this much straight flight
# instead. Short, but better than turning the instant PX4 says "fixed
# wing".
SETTLE_MIN_S = 6.0

# Where the current leg was aimed, so the loop can tell how much of it is
# left without re-deriving it from a heading that has since changed.
_leg_target = {"lat": None, "lon": None}


def _distance_to_target(bearing):
    """Metres from the aircraft to the point the current leg was aimed
    at. Returns a large number if either position is unknown, which makes
    the caller leave PX4 alone - the safe way round."""
    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None or _leg_target["lat"] is None:
        return float("inf")
    # Flat-earth, which is good to a few parts in a thousand over the
    # hundreds of metres this is ever used for.
    north = (_leg_target["lat"] - lat) * 110540.0
    east = ((_leg_target["lon"] - lon) * 111320.0
            * math.cos(math.radians(lat)))
    return math.hypot(north, east)


def _reposition(distance_m, target_agl, ground, bearing=None):
    """Aim at a point `distance_m` away at `target_agl` above home.

    `bearing` is the direction to aim in. Leaving it None uses the
    aircraft's CURRENT heading, which is right for the first leg of a
    departure and WRONG for anything repeated - see the note on
    step_climb_to_cruise below.
    """
    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None:
        return "Forward flight stopped - lost the aircraft's position."
    heading = telemetry.get("heading_deg") or 0 if bearing is None else bearing
    to_lat, to_lon = offset_latlon(lat, lon, heading, distance_m)
    _leg_target["lat"], _leg_target["lon"] = to_lat, to_lon
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

    def step_wings_level():
        """A real VTOL transitions straight and level. Turning through
        it is how you lose one: the wing is only part-loaded, the lift
        motors are unloading, and a bank in that window is a bank with
        very little to hold it up. PX4 will not refuse it, so the
        station waits instead.

        30 degrees of roll is the gate, and three seconds of patience -
        a VTOL rolls level in about one."""
        rolled = wait_until(
            lambda: abs(telemetry.get("roll_deg") or 0) < 30.0, 3)
        if not rolled:
            say_step("Forward flight: waiting for wings level before "
                     "transitioning")
            wait_until(lambda: abs(telemetry.get("roll_deg") or 0) < 30.0, 8)
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

    def step_settle():
        """Wing-borne is not the same as flying. PX4 declares the
        transition over at VT_ARSP_TRANS, 10 m/s by default
        (vtol_att_control_params.c), which for this airframe is barely
        above the speed the wing needs. Turning there is what a real
        crew would never do: accelerate first, on the wing, straight.

        Real practice is to be wings-level and accelerating before any
        turn, so this waits for airspeed to build past the transition
        figure with a margin, or for a short fixed pause if the airspeed
        reading is not available."""
        say_step("Forward flight: accelerating on the wing before turning")
        settled = wait_until(
            lambda: (telemetry.get("airspeed_ms") or 0) >= SETTLE_AIRSPEED_MS,
            SETTLE_TIMEOUT_S)
        if not settled:
            # No airspeed, or it never got there. Give it the fixed
            # pause anyway rather than commanding a turn immediately.
            wait_until(lambda: False, SETTLE_MIN_S)
        return None

    def step_climb_to_cruise():
        # REWRITTEN 12 Oct 2026, after the instructor reported the
        # aircraft "went crazy" on departure and ended up inverted.
        #
        # THE FAULT. This loop re-sent MAV_CMD_DO_REPOSITION about once a
        # second for up to three minutes, aiming 420 m ahead on the
        # CURRENT heading each time. Every DO_REPOSITION sets a LOITER
        # setpoint at the target - navigator_main.cpp v1.15.4 line 291:
        #
        #     rep->current.type = position_setpoint_s::SETPOINT_TYPE_LOITER;
        #
        # So the loiter centre was being moved to wherever the nose
        # happened to point, once a second. Any small bank turned the
        # nose, which swung the target further round, which commanded
        # more bank. That is a positive feedback loop, and on a fixed
        # wing it winds up into a steeply banked spiral - which is what
        # was seen.
        #
        # THE FIX. Take the bearing ONCE, at the start of the leg, and
        # hold it. The target is then a fixed direction in the world, not
        # a direction relative to the aircraft, so there is no loop to
        # close. The leg is only re-extended when the aircraft has
        # actually eaten into it, and always along that same fixed
        # bearing.
        # Already near the range limit when this step starts: commanding
        # an outbound leg at all would walk the aircraft through the
        # station's envelope. Found by tools/test_recovery.py, which
        # checked the loop for this and not the first command.
        range_m = telemetry.get("range_from_home_m") or 0
        if range_m > MAX_RUN_RANGE_M:
            say_step(f"Forward flight: holding - {int(range_m)} m from "
                     "home, already near the range limit")
            return None

        bearing = telemetry.get("heading_deg") or 0
        say_step(f"Forward flight: climbing away to {cruise_alt:g} m "
                 f"on {bearing:.0f} degrees")

        problem = _reposition(CRUISE_RUN_M, cruise_alt, ground, bearing)
        if problem:
            return problem

        deadline = time.monotonic() + 180
        # A hard cap as well as the deadline: if anything below starts
        # re-commanding faster than intended, this stops it being
        # hundreds of navigator re-taskings.
        extensions_left = 8

        while time.monotonic() < deadline:
            # One slow pass. Nothing is commanded inside this wait, so
            # PX4 is left alone to fly the leg it was given.
            wait_until(
                lambda: (telemetry.get("altitude_m") or 0) >= cruise_alt - 3,
                5)

            alt = telemetry.get("altitude_m") or 0
            if alt >= cruise_alt - 3:
                break

            range_m = telemetry.get("range_from_home_m") or 0
            if range_m > MAX_RUN_RANGE_M:
                say_step(f"Forward flight: holding {int(alt)} m - "
                         f"{int(range_m)} m from home, near the range limit")
                return None

            # Only re-extend when the aircraft is getting close to the
            # point it was sent to, and only along the SAME bearing.
            # Re-sending the same command while it is still half a
            # kilometre away achieves nothing and risks the thrash this
            # rewrite exists to stop.
            if extensions_left <= 0:
                continue
            if _distance_to_target(bearing) > EXTEND_WITHIN_M:
                continue
            extensions_left -= 1
            problem = _reposition(CRUISE_RUN_M, cruise_alt, ground, bearing)
            if problem:
                return problem

        say_step(None)
        return None

    started = start_sequence("forward_flight", [
        step_clear_mode, step_climb_to_transition, step_wait_for_height,
        step_wings_level, step_transition, step_settle, step_climb_to_cruise])
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
