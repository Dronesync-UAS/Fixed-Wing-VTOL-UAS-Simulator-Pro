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

from simulator_link import master, mark_failure_injected, mark_failure_cleared

MAV_CMD_INJECT_FAILURE = 420
FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 14
FAILURE_TYPE_OFF = 1
FAILURE_TYPE_OK = 0

state = {"active": False}


def _send(failure_type):
    master.mav.command_long_send(
        master.target_system, master.target_component,
        MAV_CMD_INJECT_FAILURE,
        0, FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL, failure_type, 0, 0, 0, 0, 0)


def toggle_data_link_loss():
    if state["active"]:
        _send(FAILURE_TYPE_OK)
        state["active"] = False
        mark_failure_cleared("data_link")
        return "Data link restored. Needs a live confirmation in Gazebo (not yet done) - watch whether this screen kept updating throughout."
    else:
        _send(FAILURE_TYPE_OFF)
        state["active"] = True
        mark_failure_injected("data_link")
        return "Data link (C2) loss injected. Needs a live confirmation in Gazebo (not yet done) - watch whether this screen keeps updating or freezes."


PLUGIN = {
    "id": "data_link_loss", "label": "Data Link (C2) Loss", "category": "Failure Injection",
    "style": "warning", "handler": toggle_data_link_loss,
}
