"""
ARM, and nothing else.

FIXED 12 Oct 2026: pressing ARM made the aircraft take off and crash.

ARM was sending COMPONENT_ARM_DISARM and no more, so whatever flight mode
PX4 happened to be sitting in took effect the instant it armed. An earlier
press of TAKEOFF leaves PX4 in AUTO_TAKEOFF, and that mode outlives the
failed attempt - PX4 v1.15.4 Commander.cpp lines 1035-1045 shows
VEHICLE_CMD_NAV_TAKEOFF doing nothing but change the mode:

    case vehicle_command_s::VEHICLE_CMD_NAV_TAKEOFF: {
            if (_user_mode_intention.change(vehicle_status_s::NAVIGATION_STATE_AUTO_TAKEOFF, ...

PX4's own "commander takeoff" console command confirms the arming is a
separate step (Commander.cpp lines 338-344: send NAV_TAKEOFF, wait for the
reply, then send ARM). So an ARM pressed any time after a TAKEOFF executes
that stale takeoff - and it flew the stale setpoint, which until this
morning's fix was latitude 0, longitude 0.

ARM now puts PX4 into HOLD first whenever it is in a mode that would start
flying the moment it arms. HOLD on the ground does nothing at all, so ARM
means arm and only arm. Pressing TAKEOFF afterwards sets the mode again.
"""
from simulator_link import (log_instructor_action, send_command_and_wait,
                            set_mode, telemetry)
from pymavlink import mavutil

PX4_MAIN_MODE_AUTO = 4
PX4_SUB_MODE_AUTO_LOITER = 3

# The PX4 mode names (simulator_link.PX4_MODES) that make the aircraft fly
# somewhere as soon as it is armed. "Hold / Loiter" and "Ready" are not
# here: on the ground they hold position, which is what ARM should do.
FLIES_ON_ARM = ("Takeoff", "Mission", "Return to Launch", "Land", "Follow",
                "Orbit", "Offboard")


def arm():
    mode = telemetry.get("mode") or ""
    held = None
    if mode in FLIES_ON_ARM:
        held = set_mode(PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LOITER,
                        name="HOLD (AUTO loiter)")
        log_instructor_action("arm", f"mode_was={mode} switched_to_hold={held}")

    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    log_instructor_action("arm", f"mode_at_arm={telemetry.get('mode')} result={text}")

    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        if held is not None:
            return (f"Armed. PX4 was still in {mode} from an earlier command, "
                    "so it was put into HOLD first - arming in that mode would "
                    "have started flying immediately. Press TAKEOFF when ready.")
        return "Armed."
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    return (f"PX4 refused to arm ({text}). Arming is usually blocked by a "
            "preflight check; 'commander check' in the simulator console "
            "lists them.")


PLUGIN = {"id": "arm", "label": "ARM", "category": "Flight Ops", "style": "arm", "handler": arm}
