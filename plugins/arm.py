from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def arm():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 1, 0, 0, 0, 0, 0, 0)
    log_instructor_action("arm")
    return "Arm command sent."


PLUGIN = {"id": "arm", "label": "ARM", "category": "Flight Ops", "style": "arm", "handler": arm}
