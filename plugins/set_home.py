from simulator_link import send_command_and_wait, log_instructor_action
from pymavlink import mavutil

# FIXED 11 Oct 2026: fired the command and reported success regardless, so a
# command PX4 refused was indistinguishable from one it obeyed. PX4 answers
# every command with a COMMAND_ACK - report what it actually said.


def set_home_here():
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_DO_SET_HOME, 1)  # param1=1: use current position
    log_instructor_action("set_home", f"result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "Home position set to the current location."
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    return f"PX4 refused to set home ({text})."


PLUGIN = {"id": "set_home", "label": "Set Home Here", "category": "Simulation Control", "style": "normal", "handler": set_home_here}
