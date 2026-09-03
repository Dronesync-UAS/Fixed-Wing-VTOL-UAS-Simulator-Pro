from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def disarm():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0, 0, 0, 0, 0, 0, 0)
    log_instructor_action("disarm")
    return "Disarm command sent."


PLUGIN = {"id": "disarm", "label": "DISARM", "category": "Flight Ops", "style": "disarm", "handler": disarm}
