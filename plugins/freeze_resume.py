"""
Freeze/resume the simulation. Uses Gazebo's own world control service
directly (the same technique already confirmed working in this
project's instructor panel prototype).

FIXED 16 Oct 2026: this ignored Gazebo's answer. It flipped its own
frozen/resumed state, wrote "freeze" or "resume" into the assessment
record and said "Simulation frozen." whatever happened - so with Gazebo
not answering, the instructor was told the exercise was paused while it
carried on, and the record said so too. tools/audit_commands.py caught it
once it was given a Gazebo pass.

The answer has to be READ, not inferred from the exit code: gz 13.6.0
exits 0 when a service call times out, printing "Service call timed out"
on stderr and nothing on stdout (measured 16 Oct 2026). A world that
paused answers "data: true" (measured the same day, on an empty world in
a private partition). So that, and only that, counts as done.
"""

import subprocess

from sim_target import service
from simulator_link import log_instructor_action

state = {"frozen": False}


def _ask_gazebo(paused):
    """None if Gazebo did it, or Gazebo's own reason why not."""
    try:
        done = subprocess.run([
            "gz", "service", "-s", service("control"),
            "--reqtype", "gz.msgs.WorldControl",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "2000",
            "--req", f"pause: {paused}"
        ], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"could not run gz ({exc})"
    if "data: true" in (done.stdout or ""):
        return None
    detail = ((done.stderr or "") + (done.stdout or "")).strip().splitlines()
    return detail[0] if detail else "Gazebo gave no answer"


def toggle_freeze():
    want_frozen = not state["frozen"]
    problem = _ask_gazebo("true" if want_frozen else "false")
    if problem:
        # Leave the state, the light and the record alone: nothing changed.
        return (f"{'Freeze' if want_frozen else 'Resume'} not confirmed - "
                f"Gazebo said: {problem}. The simulation is still "
                f"{'running' if want_frozen else 'frozen'} as far as the "
                "station knows.")
    state["frozen"] = want_frozen
    log_instructor_action("freeze" if state["frozen"] else "resume")
    return "Simulation frozen." if state["frozen"] else "Simulation resumed."


PLUGIN = {
    "id": "freeze", "label": "Freeze / Resume", "category": "Simulation Control",
    "style": "normal", "handler": toggle_freeze,
}
