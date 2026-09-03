"""
Individual motor spin test - Motor 5 (the forward pusher/puller motor,
not a hover rotor). See motor_test_1.py for the full explanation of how
and why this works.

NUMBERING ASSUMPTION, FLAGGED RATHER THAN GUESSED SILENTLY: this assumes
the standard_vtol airframe's pusher motor is wired as output function 5
in PX4's actuator numbering (motors are 1-12; the 4 hover rotors as
1-4 is a very standard convention, making the pusher the 5th motor
output) - this has NOT been independently confirmed for this specific
airframe/frame configuration. QGroundControl's own Actuators tab shows
the true output-to-function assignment for this exact aircraft; please
cross-check there if this button doesn't move the correct propeller.
"""

from simulator_link import master

MAV_CMD_ACTUATOR_TEST = 310
MAV_PARAM_TYPE_INT32 = 6
MOTOR_FUNCTION = 5  # assumed pusher - see docstring caveat above
TEST_VALUE = 0.15
TEST_DURATION_S = 2


def test_motor_5():
    master.mav.param_set_send(
        master.target_system, master.target_component,
        b"COM_MOT_TEST_EN", 1.0, MAV_PARAM_TYPE_INT32)
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_ACTUATOR_TEST,
        0, TEST_VALUE, TEST_DURATION_S, 0, 0, MOTOR_FUNCTION, 0, 0)
    return "Motor 5 (pusher, assumed numbering) test sent (aircraft must be DISARMED). Watch Gazebo - runs for up to 2s automatically."


PLUGIN = {
    "id": "motor_test_5", "label": "Test Motor 5 (Pusher)", "category": "Function Test",
    "style": "normal", "handler": test_motor_5,
}
