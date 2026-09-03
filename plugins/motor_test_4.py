"""
Individual motor spin test - Motor 4 (hover rotor). See motor_test_1.py
for the full explanation of how and why this works - identical mechanism,
different output number.
"""

from simulator_link import master

MAV_CMD_ACTUATOR_TEST = 310
MAV_PARAM_TYPE_INT32 = 6
MOTOR_FUNCTION = 4  # motor 4
TEST_VALUE = 0.15
TEST_DURATION_S = 2


def test_motor_4():
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b"COM_MOT_TEST_EN", 1.0, MAV_PARAM_TYPE_INT32)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_ACTUATOR_TEST,
        0, TEST_VALUE, TEST_DURATION_S, 0, 0, MOTOR_FUNCTION, 0, 0)
    return "Motor 4 test sent (aircraft must be DISARMED for this to work). Watch Gazebo - runs for up to 2s automatically."


PLUGIN = {
    "id": "motor_test_4", "label": "Test Motor 4", "category": "Function Test",
    "style": "normal", "handler": test_motor_4,
}
