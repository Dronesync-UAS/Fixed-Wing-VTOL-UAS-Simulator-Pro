"""Drive real MAVLink messages through the station's reader and check the
arming readout in the top bar.

    python3 tools/test_arm_readout.py

Why this exists: on 11 Oct 2026 an instructor pressed ARM repeatedly while
PX4 was refusing it, because the console said "Disarmed" either way. The
readout under test turns HEARTBEAT.system_status into "Ready to arm" or
"Not ready - <PX4's own reason>". The mapping is not obvious - PX4 reports
MAV_STATE_UNINIT, not some "checks failed" state, when a disarmed aircraft
would refuse to arm - so it is worth a test that feeds real encoded MAVLink
messages through the station's own reader rather than calling the mapping
directly.

Binds the station's UDP port and starts its telemetry thread as a
side-effect of the import; it does not need PX4 to be running.
"""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import simulator_link as sl
from pymavlink.dialects.v20 import common as mav

MAVLINK = mav.MAVLink(None, srcSystem=1, srcComponent=1)
# QGroundControl's own identity on the wire: system 255, component 190
# (MAV_COMP_ID_MISSIONPLANNER). Measured on this machine, 14 Oct 2026.
QGC = mav.MAVLink(None, srcSystem=255, srcComponent=190)
ARMED_BIT = mav.MAV_MODE_FLAG_SAFETY_ARMED

queue = []
sl.master.recv_match = lambda **kw: queue.pop(0) if queue else None

def packed(link, msg):
    """Give the message its source ids, the way one off the wire has them.

    A message straight out of *_encode() reports system 0, component 0 -
    the ids are only written when it is packed. The reader now filters on
    the sender (see section 11), so a test feeding unpacked messages would
    be testing something that cannot occur.
    """
    msg.pack(link)
    return msg

def heartbeat(system_status, armed=False):
    return packed(MAVLINK, MAVLINK.heartbeat_encode(
        mav.MAV_TYPE_VTOL_QUADROTOR, mav.MAV_AUTOPILOT_PX4,
        ARMED_BIT if armed else 0, 0, system_status))

def statustext(text):
    return packed(MAVLINK, MAVLINK.statustext_encode(
        mav.MAV_SEVERITY_WARNING, text.encode()))

def qgc_heartbeat():
    """What QGroundControl puts on the link once a second.

    base_mode carries the ARMED and MANUAL_INPUT bits (192 measured) and
    custom_mode is 0, so read as if it came from the aircraft it says
    "armed, mode 0.0".
    """
    return packed(QGC, QGC.heartbeat_encode(
        mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID,
        ARMED_BIT | mav.MAV_MODE_FLAG_MANUAL_INPUT_ENABLED, 0,
        mav.MAV_STATE_ACTIVE))

def pump(*msgs):
    queue.extend(msgs)
    while queue:
        sl._read_one_message()

def show(tag):
    print("  %-28s ready=%-5s state=%-22r blocker=%r"
          % (tag, sl.telemetry["arm_ready"], sl.telemetry["arm_state"],
             sl.telemetry["arm_blocker"]))

fails = []
def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)

print("1. disarmed, checks failing (PX4 sends MAV_STATE_UNINIT)")
pump(statustext("Preflight Fail: Yaw estimate error"), heartbeat(0))
show("after UNINIT")
check("not ready", sl.telemetry["arm_ready"] is False)
check("reason surfaced", sl.telemetry["arm_blocker"] == "Preflight Fail: Yaw estimate error")
check("armed flag still false", sl.telemetry["armed"] is False)

print("2. a second, different complaint replaces the first")
pump(statustext("Preflight: GPS Vertical Pos Drift too high"), heartbeat(0))
check("newest reason wins",
      sl.telemetry["arm_blocker"] == "Preflight: GPS Vertical Pos Drift too high")

print("3. checks pass (MAV_STATE_STANDBY) - stale complaint must clear")
pump(heartbeat(3))
show("after STANDBY")
check("ready", sl.telemetry["arm_ready"] is True)
check("label", sl.telemetry["arm_state"] == "Ready to arm")
check("blocker cleared", sl.telemetry["arm_blocker"] is None)

print("4. armed (MAV_STATE_ACTIVE)")
pump(heartbeat(4, armed=True))
check("armed flag", sl.telemetry["armed"] is True)
check("label", sl.telemetry["arm_state"] == "Armed")

print("5. armed + failsafe (MAV_STATE_CRITICAL)")
pump(heartbeat(5, armed=True))
check("label", sl.telemetry["arm_state"] == "Armed - failsafe")

print("6. an OLD complaint must not be shown as the live reason")
pump(statustext("Preflight Fail: Yaw estimate error"))
sl._arm_blocker["t"] = time.monotonic() - (sl._ARM_BLOCKER_MAX_AGE_S + 1)
pump(heartbeat(0))
show("after stale UNINIT")
check("not ready", sl.telemetry["arm_ready"] is False)
check("stale reason dropped", sl.telemetry["arm_blocker"] is None)

print("7. unrelated STATUSTEXT is ignored")
pump(statustext("Takeoff detected"), heartbeat(0))
check("ignored", sl.telemetry["arm_blocker"] is None)

print("8. an unknown MAV_STATE does not crash the reader")
pump(heartbeat(99))
check("degrades safely",
      sl.telemetry["arm_ready"] is False and "99" in sl.telemetry["arm_state"])

print("9. reset_flight_state clears the readout")
pump(statustext("Preflight Fail: Yaw estimate error"), heartbeat(0))
sl.reset_flight_state()
check("reset", sl.telemetry["arm_ready"] is None
      and sl.telemetry["arm_blocker"] is None
      and sl.telemetry["arm_state"] == "Waiting for PX4")

print("10. /telemetry stays JSON-serialisable")
import json, math
safe = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
        for k, v in sl.telemetry.items()}
body = json.dumps(safe)
check("serialises", '"arm_ready"' in body and '"arm_state"' in body)

print("11. QGroundControl's heartbeat must not be read as the aircraft")
# The student flies QGC and the instructor watches this station, so QGC is
# always on the link. Measured 14 Oct 2026: its heartbeat reached the
# station's port at 1 Hz and the reader decoded it as the vehicle, so the
# instructor's top bar flickered to "Mode 0.0" and ARMED while the aircraft
# sat disarmed in Hold. Nothing is worse on a training device than a
# screen that says armed when the aircraft is not.
pump(heartbeat(3))                      # aircraft: disarmed, ready, Position
sl.telemetry["mode"] = "Position"
pump(qgc_heartbeat())
show("after QGC heartbeat")
check("mode untouched", sl.telemetry["mode"] == "Position")
check("armed untouched", sl.telemetry["armed"] is False)
check("arm readout untouched", sl.telemetry["arm_state"] == "Ready to arm")

print("12. a gimbal's heartbeat is ignored too")
GIMBAL = mav.MAVLink(None, srcSystem=1, srcComponent=mav.MAV_COMP_ID_GIMBAL)
pump(packed(GIMBAL, GIMBAL.heartbeat_encode(
    mav.MAV_TYPE_GIMBAL, mav.MAV_AUTOPILOT_INVALID, 0, 0, mav.MAV_STATE_ACTIVE)))
check("mode untouched", sl.telemetry["mode"] == "Position")

print("13. the aircraft still gets through after all that")
pump(heartbeat(4, armed=True))
check("armed", sl.telemetry["armed"] is True)
check("label", sl.telemetry["arm_state"] == "Armed")

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
