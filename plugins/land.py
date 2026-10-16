from simulator_link import send_command_and_wait, log_instructor_action
from pymavlink import mavutil

# FIXED 11 Oct 2026: this fired the command and reported success regardless,
# so a command PX4 refused looked like a button that did nothing. PX4
# acknowledges every command; report what it actually said.


def land():
    result, text = send_command_and_wait(mavutil.mavlink.MAV_CMD_NAV_LAND)
    log_instructor_action("land", f"result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "Landing."
    if result is None:
        return ("Land not confirmed - PX4 did not acknowledge. Check the "
                "simulator is still running.")
    return f"PX4 refused the land ({text})."


PLUGIN = {"id": "land", "label": "LAND", "category": "Flight Ops", "style": "normal", "handler": land}
