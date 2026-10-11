from sim_target import MODEL, service
from simulator_link import master, log_instructor_action
from pymavlink import mavutil
import subprocess

SPAWN_POSE = "0,0,615.5,0,0,0"


def reset_scenario():
    # Disarm first for safety
    master.mav.command_long_send(
        master.target_system, master.target_component,
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM,
        0, 0, 0, 0, 0, 0, 0, 0)
    # Then reposition to the known-safe spawn point
    x, y, z, roll, pitch, yaw = SPAWN_POSE.split(",")
    req = (f"name: '{MODEL}', position: {{x: {x}, y: {y}, z: {z}}}, "
           f"orientation: {{x: 0, y: 0, z: 0, w: 1}}")
    subprocess.run([
        "gz", "service", "-s", service("set_pose"),
        "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
        "--timeout", "2000", "--req", req
    ])
    log_instructor_action("reset_scenario")
    return "Scenario reset: disarmed and repositioned to spawn."


PLUGIN = {
    "id": "reset_scenario", "label": "Reset Scenario", "category": "Simulation Control",
    "style": "normal", "handler": reset_scenario,
}
