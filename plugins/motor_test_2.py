"""
Individual motor spin test - Motor 2 (hover rotor). See motor_test_1.py
for the full explanation of how and why this works - identical mechanism,
different output number.
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
MOTOR_FUNCTION = 2  # motor 2
TEST_VALUE = 0.15
TEST_DURATION_S = 2


def test_motor_2():
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
        return ("Motor 2 test running - watch Gazebo. Stops itself after "
                f"{TEST_DURATION_S}s.")
    if result is None:
        return "No acknowledgement from PX4 - is the simulator running?"
    return (f"PX4 refused the motor test ({text}). It rejects actuator tests "
            "while armed - disarm first.")


PLUGIN = {
    "id": "motor_test_2", "label": "Test Motor 2", "category": "Function Test",
    "style": "normal", "handler": test_motor_2,
}
