from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def land():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_LAND,
        0, 0, 0, 0, 0, 0, 0, 0)
    log_instructor_action("land")
    return "Land command sent."


PLUGIN = {"id": "land", "label": "LAND", "category": "Flight Ops", "style": "normal", "handler": land}
