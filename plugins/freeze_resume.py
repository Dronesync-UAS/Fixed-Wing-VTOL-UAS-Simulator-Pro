"""
Freeze/resume the simulation. Uses Gazebo's own world control service
directly (the same technique already confirmed working in this
project's instructor panel prototype).
"""

import subprocess

from sim_target import service
from simulator_link import log_instructor_action

state = {"frozen": False}


def toggle_freeze():
    paused = "true" if not state["frozen"] else "false"
    subprocess.run([
        "gz", "service", "-s", service("control"),
        "--reqtype", "gz.msgs.WorldControl",
        "--reptype", "gz.msgs.Boolean",
        "--timeout", "2000",
        "--req", f"pause: {paused}"
    ])
    state["frozen"] = not state["frozen"]
    log_instructor_action("freeze" if state["frozen"] else "resume")
    return "Simulation frozen." if state["frozen"] else "Simulation resumed."


PLUGIN = {
    "id": "freeze", "label": "Freeze / Resume", "category": "Simulation Control",
    "style": "normal", "handler": toggle_freeze,
}
