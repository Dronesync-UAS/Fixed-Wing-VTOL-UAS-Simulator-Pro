from simulator_link import master, log_instructor_action
from pymavlink import mavutil


def mode_position():
    custom_mode = (3 << 16)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        0, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, custom_mode, 0, 0, 0, 0, 0)
    log_instructor_action("mode_change", "mode=position instructor_override=true")
    return "Switching to Position mode."


PLUGIN = {"id": "mode_position", "label": "Position", "category": "Flight Mode", "style": "normal", "handler": mode_position}
