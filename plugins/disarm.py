from simulator_link import send_command_and_wait, log_instructor_action
from pymavlink import mavutil

# FIXED 11 Oct 2026: fired the command and reported success regardless, so a
# command PX4 refused was indistinguishable from one it obeyed. PX4 answers
# every command with a COMMAND_ACK - report what it actually said.


def disarm():
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
    log_instructor_action("disarm", f"result={text}")
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return "Disarmed."
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    # PX4 refuses a plain disarm in flight; say so rather than leaving the
    # instructor wondering whether the button worked.
    return (f"PX4 refused to disarm ({text}). PX4 will not disarm in flight "
            "unless forced - land or use Reset Scenario instead.")


PLUGIN = {"id": "disarm", "label": "DISARM", "category": "Flight Ops", "style": "disarm", "handler": disarm}
