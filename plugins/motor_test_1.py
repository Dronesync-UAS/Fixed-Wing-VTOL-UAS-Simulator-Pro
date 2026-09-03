"""
Individual motor spin test - Motor 1 (front-right hover rotor, typical
standard_vtol numbering - cross-check against QGroundControl's own
Actuators tab, which shows the true output-to-function mapping for this
specific airframe, before relying on which physical propeller this is).

WHY THIS EXISTS: built 23 Aug 2026 in response to a live test where the
aircraft armed, spun all 4 propellers unevenly, then disarmed itself, and
separately where takeoff attempts resulted in uncontrolled spinning. This
lets each motor be confirmed working on its own, disarmed, before ever
attempting to fly - the same "confirm the individual actuators, then fly"
sequence real aircraft ground checks follow.

HOW THIS WORKS - sourced directly from PX4's own source code for this
project's pinned version (v1.15.4), not guessed:
- MAV_CMD_ACTUATOR_TEST (numeric ID 310) is PX4's own modern command for
  this (msg/VehicleCommand.msg, release/1.15) - distinct from the older
  ArduPilot-style MAV_CMD_DO_MOTOR_TEST, which PX4 does not implement.
- param1 = test value, -1 to 1 (0 = minimum confirm-spin thrust).
- param2 = timeout in SECONDS. PX4 hard-caps this internally to a maximum
  of 3 seconds regardless of what's requested (src/modules/commander/
  Commander.cpp, handleCommandActuatorTest) - each test is automatically
  self-limiting, it doesn't need a separate "stop" button.
- param5 = which output to test: 1-12 for motors, 33+ for servos. This
  plugin tests motor 1.
- PX4 REJECTS this command outright while armed (Commander.cpp:
  `if (isArmed() ...) return ... DENIED`). This is a genuine PX4 safety
  rule, not a bug in this app - motor tests only work while disarmed.
- PX4 also requires the parameter COM_MOT_TEST_EN=1 to be set first, or
  it denies the command - this plugin sets that parameter automatically
  each time, so nothing needs to be pre-configured manually.

NOT YET LIVE-TESTED on this Gazebo Harmonic setup. A separate, known PX4
issue (GitHub #23721, closed as "not planned") reports actuator testing
not working in SITL with Gazebo *Classic* specifically, because the
simulation only applies actuator outputs while armed - which would
directly conflict with the disarmed-only rule above. That issue doesn't
mention Gazebo Harmonic either way. Please treat this as needing live
confirmation, the same as several other features in this project.
"""

from simulator_link import master

MAV_CMD_ACTUATOR_TEST = 310
MAV_PARAM_TYPE_INT32 = 6
MOTOR_FUNCTION = 1  # motor 1
TEST_VALUE = 0.15   # gentle throttle, just enough to visibly confirm spin
TEST_DURATION_S = 2  # PX4 caps this at 3s regardless; self-stopping


def test_motor_1():
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b"COM_MOT_TEST_EN", 1.0, MAV_PARAM_TYPE_INT32)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_ACTUATOR_TEST,
        0, TEST_VALUE, TEST_DURATION_S, 0, 0, MOTOR_FUNCTION, 0, 0)
    return "Motor 1 test sent (aircraft must be DISARMED for this to work). Watch Gazebo - runs for up to 2s automatically."


PLUGIN = {
    "id": "motor_test_1", "label": "Test Motor 1", "category": "Function Test",
    "style": "normal", "handler": test_motor_1,
}
