import sim_target
from sim_target import MODEL, service
from simulator_link import send_command_and_wait, log_instructor_action
from pymavlink import mavutil
import subprocess



def reset_scenario():
    # Disarm first for safety. FIXED 11 Oct 2026: this fired blind and the
    # button reported a completed reset either way - so an aircraft PX4
    # refused to disarm would be repositioned while still armed, and the
    # instructor would be told the scenario had been reset.
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0)
    if result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
        reason = text or "no acknowledgement from PX4"
        return (f"Scenario not reset - PX4 would not disarm ({reason}). "
                "PX4 refuses a plain disarm in flight; land first.")
    # Then reposition to the known-safe spawn point
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
        "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
        "--timeout", "2000", "--req", req
    ])
    log_instructor_action("reset_scenario")
    return "Scenario reset: disarmed and repositioned to spawn."


PLUGIN = {
    "id": "reset_scenario", "label": "Reset Scenario", "category": "Simulation Control",
    "style": "normal", "handler": reset_scenario,
}
