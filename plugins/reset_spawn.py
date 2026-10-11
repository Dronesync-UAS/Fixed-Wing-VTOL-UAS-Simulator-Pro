"""
Resets the aircraft back to its confirmed-safe spawn point. A full
"reposition anywhere" control would need a coordinate input form -
this simple version covers the most common instructor need (recover
from a bad state) without that extra complexity yet.
"""

import subprocess

import sim_target
from sim_target import MODEL, service
from simulator_link import log_instructor_action



def reset_to_spawn():
    # The spawn height belongs to the world, not to this plugin: Hoggar's
    # clearing is at 605 m and Black Rock's playa at 1 m, so a fixed value
    # here teleported the aircraft 600 m into the air on every world but
    # one. Taken from the environment list instead, which is also what
    # launches each world.
    environment = sim_target.environment()
    if environment is None:
        return (f"Reset not sent - '{sim_target.WORLD}' is not in the "
                "environment list, so its spawn height is unknown.")
    x, y, z = 0.0, 0.0, environment["spawn_z"]
    req = (f"name: '{MODEL}', position: {{x: {x}, y: {y}, z: {z}}}, "
           f"orientation: {{x: 0, y: 0, z: 0, w: 1}}")
    subprocess.run([
        "gz", "service", "-s", service("set_pose"),
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
