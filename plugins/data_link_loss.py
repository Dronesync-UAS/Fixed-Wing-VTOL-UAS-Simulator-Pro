"""
Data link (C2 / telemetry) loss.

Simulates the link between the aircraft and the ground station(s) being
lost, using PX4's own documented failure-injection system - the
GCS/MAVLink equivalent of PX4's own console commands
"failure mavlink_signal off" / "failure mavlink_signal ok".
(https://docs.px4.io/main/en/debug/failure_injection and
https://docs.px4.io/main/en/simulation/failsafes - see "Data Link Loss"
and the NAV_DLL_ACT parameter)

IMPORTANT - GENUINELY UNCERTAIN, FLAGGING RATHER THAN GUESSING: it is not
confirmed from PX4's documentation alone whether this failure type (a)
makes PX4 *internally* believe it has lost contact with the ground
station (triggering its own NAV_DLL_ACT failsafe, e.g. auto-RTL) while
still sending normal telemetry to this app and to QGroundControl, or
(b) actually stops PX4's outbound telemetry to every connected ground
station, including this Instructor Station's own dashboard. A real data
link failure would affect every ground station equally, so if it is (b),
expect this app's own screen to stop updating too until the link is
restored - that would be realistic behaviour, not a crash. Please note
which of these two actually happens the first time this is tested live,
so this comment (and the automatic logging below) can be corrected to
match reality.

If it turns out to be (b), the "reaction time" this app logs for this
scenario will include however long the outage itself lasts, on top of
the aircraft's own failsafe/student response - worth bearing in mind
when reading this scenario's log entries, and worth flagging to your
Head of Training as a logging-accuracy caveat specific to this failure
type.

Numeric codes (FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL=14, FAILURE_TYPE_OFF=1,
FAILURE_TYPE_OK=0) cross-checked against MAVLink's own enum definitions
on 23 Aug 2026 - see the matching note in rc_signal_loss.py,
motor_failure.py and engine_failure.py.

Toggle: press once to fail, press again to restore.

NOT YET VISUALLY/BEHAVIOURALLY CONFIRMED on this Gazebo Harmonic setup -
same caveat as rc_signal_loss.py (PX4's docs mention Gazebo Classic
specifically, not Harmonic, for this mechanism).
"""

from simulator_link import send_command_and_wait, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 14
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
        MAV_CMD_INJECT_FAILURE, FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL, failure_type, 0, 0, 0, 0, 0)
    if result == 0:  # MAV_RESULT_ACCEPTED
        return None
    if result is None:
        return "no acknowledgement from PX4"
    return f"PX4 {text} the command"


def toggle_data_link_loss():
    if state["active"]:
        problem = _send(FAILURE_TYPE_OK)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = False
        mark_failure_cleared("data_link")
        return "Data link restored. Needs a live confirmation in Gazebo (not yet done) - watch whether this screen kept updating throughout."
    else:
        problem = _send(FAILURE_TYPE_OFF)
        if problem:
            # Leave the state and the status light alone when PX4
            # did not take the command - a light that says "failed"
            # while the aircraft is healthy is worse than no light.
            return f"Not injected - {problem}."
        state["active"] = True
        mark_failure_injected("data_link")
        return "Data link (C2) loss injected. Needs a live confirmation in Gazebo (not yet done) - watch whether this screen keeps updating or freezes."


PLUGIN = {
    "id": "data_link_loss", "label": "Data Link (C2) Loss", "category": "Failure Injection",
    "style": "warning", "handler": toggle_data_link_loss,
}
