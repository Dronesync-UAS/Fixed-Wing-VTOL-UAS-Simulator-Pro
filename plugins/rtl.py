from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def rtl():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_NAV_RETURN_TO_LAUNCH,
        0, 0, 0, 0, 0, 0, 0, 0)
    log_instructor_action("rtl")
    return "Return to Launch command sent."


PLUGIN = {"id": "rtl", "label": "RETURN TO LAUNCH", "category": "Flight Ops", "style": "normal", "handler": rtl}
