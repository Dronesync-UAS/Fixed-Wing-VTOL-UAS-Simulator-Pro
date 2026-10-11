from simulator_link import send_command_and_wait, log_instructor_action
from pymavlink import mavutil

# FIXED 11 Oct 2026: fired the command and reported success regardless, so a
# command PX4 refused was indistinguishable from one it obeyed. PX4 answers
# every command with a COMMAND_ACK - report what it actually said.


def arm():
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
    log_instructor_action("arm", f"result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "Armed."
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    return (f"PX4 refused to arm ({text}). Arming is usually blocked by a "
            "preflight check; 'commander check' in the simulator console "
            "lists them.")


PLUGIN = {"id": "arm", "label": "ARM", "category": "Flight Ops", "style": "arm", "handler": arm}
