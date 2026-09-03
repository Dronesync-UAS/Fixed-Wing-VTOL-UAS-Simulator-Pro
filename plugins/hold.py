from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def hold():
    custom_mode = (4 << 16) | (3 << 24)  # AUTO / LOITER
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, custom_mode, 0, 0, 0, 0, 0)
    log_instructor_action("hold")
    return "Holding position."


PLUGIN = {"id": "hold", "label": "HOLD", "category": "Flight Ops", "style": "normal", "handler": hold}
