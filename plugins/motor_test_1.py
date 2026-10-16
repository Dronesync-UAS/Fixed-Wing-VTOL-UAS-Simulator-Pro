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

import struct

from simulator_link import master, send_command_and_wait

# FIXED 11 Oct 2026: this sent the float 1.0 while declaring the parameter as
# MAV_PARAM_TYPE_INT32, so PX4 reinterpreted the float's bit pattern and stored
# COM_MOT_TEST_EN as 1065353216 - visible in `param show -c` on the machine.
# An integer parameter has to be sent as its bit pattern packed into
# PARAM_SET's float field.
def _as_int32(value):
    return struct.unpack("<f", struct.pack("<i", int(value)))[0]


MAV_CMD_ACTUATOR_TEST = 310
MAV_PARAM_TYPE_INT32 = 6
MOTOR_FUNCTION = 1  # motor 1
TEST_VALUE = 0.15   # gentle throttle, just enough to visibly confirm spin
TEST_DURATION_S = 2  # PX4 caps this at 3s regardless; self-stopping


def test_motor_1():
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b"COM_MOT_TEST_EN", _as_int32(1), MAV_PARAM_TYPE_INT32)
    # FIXED 11 Oct 2026: fired blind and always claimed success. PX4 denies
    # this command outright while armed, which is the single most likely
    # reason a motor test appears to do nothing - so report what it said.
    result, text = send_command_and_wait(
        MAV_CMD_ACTUATOR_TEST,
        TEST_VALUE, TEST_DURATION_S, 0, 0, MOTOR_FUNCTION, 0, 0)
    if result == 0:  # MAV_RESULT_ACCEPTED
        return ("Motor 1 test running - watch Gazebo. Stops itself after "
                f"{TEST_DURATION_S}s.")
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    return (f"PX4 refused the motor test ({text}). It rejects actuator tests "
            "while armed - disarm first.")


PLUGIN = {
    "id": "motor_test_1", "label": "Test Motor 1", "category": "Function Test",
    "style": "normal", "handler": test_motor_1,
}
