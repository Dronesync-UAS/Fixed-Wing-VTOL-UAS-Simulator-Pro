"""
NEW SESSION - put everything back to how it was before the last student
flew, in one press.

Added 12 Oct 2026 on request, after a crash left the station in a state
that took five separate controls to clear: a failure injection still
switched on, PX4 still sitting in the Takeoff mode that caused the crash,
the aircraft on its back where it landed, and the previous flight's track
still drawn across the plan view.

What it does, in this order, and why the order matters:

  1. Switches off every failure injection that is still on. A GPS dropout
     left running reports 255 satellites, which blocks arming - and looks
     like a broken simulator rather than a switch somebody left on.
  2. Stops any background script still running behind one of those.
  3. Disarms, with PX4's force flag. A plain disarm is refused in flight,
     and after a crash PX4 often still believes it is flying.
     21196 is PX4's own force value - v1.15.4 Commander.cpp lines 320-331:
         // 21196: force arming/disarming (e.g. allow arming to override
         // preflight checks and disarming in flight)
  4. Puts PX4 into HOLD. Whatever mode it was in is still live, and the
     next ARM would run it. HOLD on the ground does nothing.
  5. Puts the aircraft back on the spawn point, upright.
  6. Forgets the old flight: the track on the plan view, the home point,
     and the stale command acknowledgements.

WHAT IT CANNOT DO. It does not restart PX4. If the EKF has given up - the
arming readout stays red with the aircraft sitting level and still on the
pad, with satellites back to a sensible number - PX4 itself has to be
restarted, and no button here can do that.

It also cannot cancel the aircraft's momentum: Gazebo's set_pose moves the
model, it does not stop it. A model that was tumbling hard may need a
second press once it has settled.
"""
import subprocess

import plugin_loader
import sim_target
from sim_target import MODEL, service
from simulator_link import (log_instructor_action, reset_flight_state,
                            running_processes, send_command_and_wait, set_mode,
                            stop_background_script, telemetry)
from pymavlink import mavutil

PX4_MAIN_MODE_AUTO = 4
PX4_SUB_MODE_AUTO_LOITER = 3

# PX4's force flag for ARM_DISARM param2 - see the note above.
PX4_FORCE = 21196.0


def _clear_failures():
    """Press every failure toggle that is still on. The toggles clear
    themselves on a second press, so this is their own code path rather
    than a second way of undoing them that could drift out of step."""
    cleared = []
    for plugin in plugin_loader.LOADED:
        module = plugin.get("_module")
        state = getattr(module, "state", None)
        if isinstance(state, dict) and state.get("active"):
            try:
                plugin["handler"]()
            except Exception as exc:                      # noqa: BLE001
                cleared.append(f"{plugin['label']} (failed: {exc})")
                continue
            cleared.append(plugin["label"])
    return cleared


def new_session():
    steps = []

    cleared = _clear_failures()
    if cleared:
        steps.append("cleared " + ", ".join(cleared))

    for name in list(running_processes):
        stop_background_script(name)

    was_armed = telemetry.get("armed")
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, PX4_FORCE)
    if result == mavutil.mavlink.MAV_RESULT_ACCEPTED:
        steps.append("disarmed" if was_armed else "confirmed disarmed")
    else:
        steps.append(f"PX4 would not disarm ({text})")

    mode_was = telemetry.get("mode")
    set_mode(PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LOITER, name="HOLD")
    steps.append(f"mode {mode_was} -> HOLD")

    environment = sim_target.environment()
    if environment is None:
        steps.append(f"could NOT reposition - '{sim_target.WORLD}' is not in "
                     "the environment list, so its spawn height is unknown")
    else:
        req = (f"name: '{MODEL}', position: {{x: 0, y: 0, "
               f"z: {environment['spawn_z']}}}, "
               f"orientation: {{x: 0, y: 0, z: 0, w: 1}}")
        try:
            subprocess.run(
                ["gz", "service", "-s", service("set_pose"),
                 "--reqtype", "gz.msgs.Pose", "--reptype", "gz.msgs.Boolean",
                 "--timeout", "2000", "--req", req],
                check=False, timeout=8)
            steps.append("back on the spawn point, upright")
        except (OSError, subprocess.SubprocessError) as exc:
            steps.append(f"could NOT reposition ({exc})")

    reset_flight_state()
    steps.append("track and home point cleared")

    log_instructor_action("new_session", "; ".join(steps))
    return ("New session: " + "; ".join(steps)
            + ". Give PX4 a few seconds to settle, then check the arming "
              "readout before arming.")


PLUGIN = {
    "id": "new_session",
    "label": "NEW SESSION",
    "category": "Simulation Control",
    "style": "highlight",
    "handler": new_session,
}
