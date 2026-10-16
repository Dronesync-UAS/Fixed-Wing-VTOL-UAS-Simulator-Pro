"""
TAKEOFF, with the climb height set on the console.

HISTORY, because two separate faults have been fixed here and both are easy
to reintroduce.

23 Aug 2026: this sent a hardcoded "20" as the target altitude. PX4 reads
param7 as height above MEAN SEA LEVEL, not "climb 20 m from here", so on
this training area's real Hoggar Mountains location (about 2000 m AMSL) a
plain 20 told PX4 to descend two kilometres. It refused every time with
"Already higher than takeoff altitude (not descending)". The height is now
read from the aircraft and the climb added to it, which is what
QGroundControl does.

12 Oct 2026: param5 and param6 - the takeoff point's latitude and longitude
- were being sent as 0, and 0 is a perfectly finite number. PX4
v1.15.4 src/modules/navigator/navigator_main.cpp lines 622-631:

    if (PX4_ISFINITE(cmd.param5) && PX4_ISFINITE(cmd.param6)) {
            rep->current.lat = cmd.param5;
            rep->current.lon = cmd.param6;
    } else {
            // If one of them is non-finite set the current global position as target
            rep->current.lat = get_global_position()->lat;
            rep->current.lon = get_global_position()->lon;
    }

So every takeoff was commanded to latitude 0, longitude 0 - the Atlantic off
West Africa - rather than straight up from where the aircraft stood. NaN is
now sent for both, which is the documented way to say "here", and the way
QGroundControl says it.

NOT CONFIRMED: whether that is what made the aircraft stop climbing at about
10 m when 20 was asked for. It is a real defect and it was fixed, but the
link between it and that symptom has not been proven. The messages PX4 sends
during a takeoff are now reported back, so the next attempt will say.

ARMING. PX4 disarms again about ten seconds after arming if the aircraft has
not taken off (COM_DISARM_PRFLT, default 10.0 s). Pressing ARM and then
reaching for TAKEOFF loses that race often enough that TAKEOFF looked like a
dead button. TAKEOFF now arms the aircraft itself when it is disarmed, so
there is no window to miss. ARM is still there for arming on its own.
"""
from simulator_link import (log_instructor_action, send_command_and_wait,
                            status_since, telemetry, wait_for_armed)
from pymavlink import mavutil
import time

DEFAULT_CLIMB_M = 20.0
MIN_CLIMB_M = 5.0
# The station enforces a 120 m ceiling (CAP722B 5.3(c)); a takeoff that
# climbed past it would breach the limit the moment it finished.
MAX_CLIMB_M = 120.0

NAN = float("nan")

# PX4's own words during a takeoff, worth quoting back to the instructor.
_TAKEOFF_WORDS = ("takeoff", "altitude", "arm", "transition", "reject", "deny")


def takeoff(altitude_m=DEFAULT_CLIMB_M):
    try:
        climb = float(altitude_m)
    except (TypeError, ValueError):
        return f"Takeoff not sent - '{altitude_m}' is not a height in metres."
    if not MIN_CLIMB_M <= climb <= MAX_CLIMB_M:
        return (f"Takeoff not sent - the climb must be between "
                f"{MIN_CLIMB_M:g} m and {MAX_CLIMB_M:g} m.")

    current_amsl = telemetry.get("altitude_amsl_m")
    if current_amsl is None:
        return ("Takeoff not sent - no altitude reading from the aircraft yet. "
                "Wait a couple of seconds for telemetry to connect and try again.")

    started = time.monotonic()
    armed_here = False
    if not telemetry.get("armed"):
        arm_result, arm_text = send_command_and_wait(
            mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
        if arm_result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
            log_instructor_action("takeoff", f"arm_refused={arm_text}")
            blocker = telemetry.get("arm_blocker")
            return (f"Takeoff not sent - PX4 would not arm ({arm_text})."
                    + (f" PX4 says: {blocker}" if blocker else ""))
        if not wait_for_armed():
            return ("Takeoff not sent - PX4 accepted ARM but the aircraft has "
                    "not reported itself armed. Try again.")
        armed_here = True

    # Re-read the height: arming can take a second, and the number below is
    # an absolute sea-level target, so a stale reading moves the target.
    current_amsl = telemetry.get("altitude_amsl_m", current_amsl)
    target_amsl = current_amsl + climb

    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_NAV_TAKEOFF,
        0,      # param1: minimum pitch (fixed wing); ignored in hover
        0, 0,   # param2-3: unused
        NAN,    # param4: yaw - NaN keeps the current heading
        NAN,    # param5: latitude  - NaN means "where the aircraft is"
        NAN,    # param6: longitude - the same; 0 here meant null island
        target_amsl)  # param7: target height above MEAN SEA LEVEL

    log_instructor_action(
        "takeoff",
        f"climb_m={climb:g} target_amsl_m={target_amsl:.1f} "
        f"armed_by_button={armed_here} result={text}")

    if result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
        if result is None:
            return ("Takeoff not confirmed - PX4 did not acknowledge. Check the "
                    "simulator is still running.")
        if telemetry.get("armed") is False:
            return (f"PX4 refused the takeoff ({text}) - the aircraft is disarmed. "
                    "Arming is usually blocked by a preflight check; the simulator "
                    "console lists them with 'commander check'.")
        return f"PX4 refused the takeoff ({text})."

    # Accepted is not the same as doing what was asked: PX4 says the rest in
    # STATUSTEXT. Give it a moment to speak, then quote it.
    time.sleep(1.2)
    said = status_since(started, _TAKEOFF_WORDS)
    note = ("  PX4: " + " / ".join(said[-3:])) if said else ""
    lead = "Armed, and taking off" if armed_here else "Taking off"
    return f"{lead} - climbing {climb:g} m to {target_amsl:.0f} m above sea level.{note}"


PLUGIN = {
    "id": "takeoff",
    "label": "TAKEOFF",
    "category": "Flight Ops",
    "style": "normal",
    "inputs": [{"name": "altitude_m", "label": "Climb (m)",
                "default": 20, "min": 5, "max": 120, "step": 5}],
    "handler": takeoff,
}
