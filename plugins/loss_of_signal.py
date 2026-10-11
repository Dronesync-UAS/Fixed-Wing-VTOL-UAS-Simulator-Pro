"""
RC (radio control) signal loss.

Simulates the pilot's manual control link being lost, using PX4's own
documented failure-injection system - this is the GCS/MAVLink equivalent
of the same technique PX4's own docs demonstrate via the console commands
"failure rc_signal off" / "failure rc_signal ok".
(https://docs.px4.io/main/en/debug/failure_injection)

This file used to be an unbuilt placeholder ("Loss of Signal / C2 Link -
NOT YET IMPLEMENTED"). It's now split into two separate, more precise
scenarios, because PX4 actually treats "losing the pilot's control link"
(RC signal) and "losing the link to the ground station" (data link /
C2) as two different, separately-simulatable failures - see
data_link_loss.py for the second one.

Numeric codes used below (FAILURE_UNIT_SYSTEM_RC_SIGNAL=13,
FAILURE_TYPE_OFF=1, FAILURE_TYPE_OK=0) were cross-checked against
MAVLink's own FAILURE_UNIT/FAILURE_TYPE definitions on 23 Aug 2026 -
see the same note in motor_failure.py and engine_failure.py, which had
been using incorrect numbers for over a month before this check.

Toggle: press once to fail, press again to restore - lets you test
PX4's RC-loss failsafe (the NAV_RCL_ACT parameter) and the student's
recovery response.

NOT YET VISUALLY/BEHAVIOURALLY CONFIRMED on this Gazebo Harmonic setup -
PX4's documentation for this system says it "is supported in Gazebo
Classic" without explicitly confirming Harmonic. Motor/engine failures
via the same mechanism do work on this setup despite similar wording, so
this is not a guaranteed blocker, but please confirm with a live test
(watch for the aircraft's mode changing to whatever your
NAV_RCL_ACT/COM_RCL_EXCEPT setup is configured to do) before relying on
this for a real training or assessment session.
"""

from simulator_link import send_command_and_wait, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_RC_SIGNAL = 13
FAILURE_TYPE_OFF = 1
FAILURE_TYPE_OK = 0

state = {"active": False}


# FIXED 11 Oct 2026: fired blind and always claimed success. Now reports PX4's
# acknowledgement - with the caveat that MAV_CMD_INJECT_FAILURE is documented
# in this project's 10 Aug entry as accepted-but-ineffective on this PX4
# version (the reason the GPS dropout proxy exists), so "accepted" here means
# PX4 took the command, not that the failure is visible. Needs live
# confirmation per failure type.


def _send(failure_type):
    """Returns a message describing what PX4 said."""
    result, text = send_command_and_wait(
        MAV_CMD_INJECT_FAILURE, FAILURE_UNIT_SYSTEM_RC_SIGNAL, failure_type, 0, 0, 0, 0, 0)
    if result == 0:  # MAV_RESULT_ACCEPTED
        return None
    if result is None:
        return "no acknowledgement from PX4"
    return f"PX4 {text} the command"


def toggle_rc_signal_loss():
    if state["active"]:
        problem = _send(FAILURE_TYPE_OK)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = False
        mark_failure_cleared("rc_signal")
        return "RC signal restored. Needs a live visual/behavioural confirmation in Gazebo (not yet done)."
    else:
        problem = _send(FAILURE_TYPE_OFF)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = True
        mark_failure_injected("rc_signal")
        return "RC signal loss injected. Needs a live visual/behavioural confirmation in Gazebo (not yet done)."


PLUGIN = {
    "id": "rc_signal_loss", "label": "RC Signal Loss", "category": "Failure Injection",
    "style": "warning", "handler": toggle_rc_signal_loss,
}
