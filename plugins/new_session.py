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

HARD, added 12 Oct 2026 because the standard reset was not enough to get a
new session started after a crash. On top of everything above it asks
Gazebo to reset its models, which puts every model back to the pose the
world file gave it AND clears the velocities that set_pose leaves behind -
an aircraft left tumbling or sliding is the thing that most often stops
the next session starting.

It is a model-only reset on purpose. Gazebo will also reset simulation
TIME, and PX4 is attached to that clock: winding it back to zero under a
running autopilot is not something to do to recover a lesson.

WHAT IT STILL CANNOT DO. It does not restart PX4. PX4 can be asked to
reboot over MAVLink, and this does ask - but in SITL that almost certainly
comes back refused: v1.15.4 Commander.cpp lines 1217-1226 puts the reboot
behind

        #if defined(CONFIG_BOARDCTL_RESET)

which is a board feature a POSIX build does not have, and the else branch
answers DENIED. The attempt is made and the answer reported rather than
quietly skipped, so the instructor learns whether this build can or not.
When it cannot, and PX4 is still refusing to arm a level aircraft sitting
on the pad, PX4 itself has to be restarted from its own window - and the
reply says so.

NOT YET RUN AGAINST GAZEBO.
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

# MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, param1 = 1 ("reboot autopilot").
MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN = 246


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


def _gazebo_reset_models():
    """Ask Gazebo to put every model back where the world file put it.

    gz.msgs.WorldControl carries a WorldReset with `all`, `time_only` and
    `model_only`. Only the models are reset: `all` would also wind
    simulation time back to zero, and PX4 is running off that clock."""
    subprocess.run(
        ["gz", "service", "-s", service("control"),
         "--reqtype", "gz.msgs.WorldControl", "--reptype", "gz.msgs.Boolean",
         "--timeout", "3000", "--req", "reset: {model_only: true}"],
        check=False, timeout=10)


def new_session(reset="hard"):
    hard = str(reset).lower().startswith("hard")
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

    if hard:
        try:
            _gazebo_reset_models()
            steps.append("Gazebo models reset, velocities cleared")
        except (OSError, subprocess.SubprocessError) as exc:
            steps.append(f"Gazebo model reset failed ({exc})")
        # Worth asking even though a POSIX build almost certainly refuses -
        # see the note at the top of this file.
        reboot, reboot_text = send_command_and_wait(
            MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 1)
        if reboot == mavutil.mavlink.MAV_RESULT_ACCEPTED:
            steps.append("PX4 is rebooting - give it half a minute")
        else:
            steps.append("PX4 would not reboot from here (%s); restart it in "
                         "its own window if it still refuses to arm"
                         % (reboot_text or "no answer"))

    reset_flight_state()
    steps.append("track and home point cleared")
    try:
        import preflight
        preflight.reset()
        steps.append("pre-flight checklist cleared")
    except Exception:                                      # noqa: BLE001
        pass

    log_instructor_action("new_session", f"hard={hard} " + "; ".join(steps))
    return ("New session: " + "; ".join(steps)
            + ". Give PX4 a few seconds to settle, then check the arming "
              "readout before arming.")


PLUGIN = {
    "id": "new_session",
    "label": "NEW SESSION",
    "category": "Simulation Control",
    "style": "highlight",
    "inputs": [{"name": "reset", "label": "Reset", "type": "select",
                "default": "hard",
                "options": [
                    {"value": "hard",
                     "label": "Hard - also reset Gazebo"},
                    {"value": "standard",
                     "label": "Standard - leave Gazebo alone"}]}],
    "handler": new_session,
}
