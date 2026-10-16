"""
Resets the aircraft back to its confirmed-safe spawn point. A full
"reposition anywhere" control would need a coordinate input form -
this simple version covers the most common instructor need (recover
from a bad state) without that extra complexity yet.

FIXED 16 Oct 2026: this ignored Gazebo's answer. It wrote "reset_spawn"
into the assessment record and said "Aircraft repositioned to spawn
point." whatever happened. tools/audit_commands.py caught it once it was
given a Gazebo pass.

The answer has to be READ, not inferred from the exit code: gz 13.6.0
exits 0 when a service call times out, printing "Service call timed out"
on stderr and nothing on stdout (measured 16 Oct 2026). So "data: true"
is what counts as done.

WHAT "data: true" DOES NOT PROVE. Gazebo answers it for set_pose on a
model that does not exist (measured the same day, on an empty world in a
private partition) - it means Gazebo took the request, not that the
aircraft moved. The reply says "accepted" for that reason; confirming the
move would mean reading the aircraft's position back afterwards, which
this does not do.
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
    try:
        done = subprocess.run([
            "gz", "service", "-s", service("set_pose"),
            "--reqtype", "gz.msgs.Pose",
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "2000",
            "--req", req
        ], capture_output=True, text=True, timeout=8)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Reset not confirmed - could not run gz ({exc})."
    if "data: true" not in (done.stdout or ""):
        detail = ((done.stderr or "") + (done.stdout or "")).strip().splitlines()
        reason = detail[0] if detail else "Gazebo gave no answer"
        # Nothing is written to the record: as far as anyone can tell,
        # nothing happened.
        return (f"Reset not confirmed - Gazebo said: {reason}. The aircraft "
                "may not have moved.")
    log_instructor_action("reset_spawn")
    return "Gazebo accepted the reset to the spawn point."


PLUGIN = {
    "id": "reset_spawn", "label": "Reset to Spawn Point", "category": "Simulation Control",
    "style": "normal", "handler": reset_to_spawn,
}
