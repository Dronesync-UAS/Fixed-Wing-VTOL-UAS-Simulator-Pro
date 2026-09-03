"""
Resets the aircraft back to its confirmed-safe spawn point. A full
"reposition anywhere" control would need a coordinate input form -
this simple version covers the most common instructor need (recover
from a bad state) without that extra complexity yet.
"""

import subprocess

from simulator_link import log_instructor_action

SPAWN_POSE = "0,0,615.5,0,0,0"


def reset_to_spawn():
    x, y, z, roll, pitch, yaw = SPAWN_POSE.split(",")
    req = (f"name: 'standard_vtol_0', position: {{x: {x}, y: {y}, z: {z}}}, "
           f"orientation: {{x: 0, y: 0, z: 0, w: 1}}")
    subprocess.run([
        "gz", "service", "-s", "/world/training_area/set_pose",
        "--reqtype", "gz.msgs.Pose",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "2000",
        "--req", req
    ])
    log_instructor_action("reset_spawn")
    return "Aircraft repositioned to spawn point."


PLUGIN = {
    "id": "reset_spawn", "label": "Reset to Spawn Point", "category": "Simulation Control",
    "style": "normal", "handler": reset_to_spawn,
}
