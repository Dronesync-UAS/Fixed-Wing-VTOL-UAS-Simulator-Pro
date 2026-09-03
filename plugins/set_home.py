from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def set_home_here():
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_HOME,
        0, 1, 0, 0, 0, 0, 0, 0)  # param1=1: use current position
    log_instructor_action("set_home")
    return "Home position set to current location."


PLUGIN = {"id": "set_home", "label": "Set Home Here", "category": "Simulation Control", "style": "normal", "handler": set_home_here}
