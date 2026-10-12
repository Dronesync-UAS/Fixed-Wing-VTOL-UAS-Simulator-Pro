"""Check ARM cannot fly the aircraft, and that NEW SESSION clears up.

    python3 tools/test_recovery.py

These two controls are the ones that bite hardest when they are wrong. ARM
armed in whatever mode PX4 was left in, so an ARM pressed after a TAKEOFF
flew a stale takeoff and crashed. NEW SESSION force-disarms, moves the
aircraft and wipes the flight record, so it is worth knowing exactly what
it sends before it is pressed between two students.

Runs against stubs - no PX4, no Gazebo.
"""
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

sent = []          # every COMMAND_LONG the plugins sent
modes = []         # every mode change
poses = []         # every gz set_pose
resets = []

sl = types.ModuleType("simulator_link")
sl.telemetry = {"armed": False, "mode": "Hold / Loiter", "altitude_amsl_m": 1200.0,
                "arm_blocker": None}
sl.running_processes = {}


def _send(command, *params, timeout=2.0):
    sent.append((command, params))
    return 0, "accepted"


def _set_mode(main, sub=0, name=None):
    modes.append((main, sub))
    return f"{name}: accepted by PX4."


sl.send_command_and_wait = _send
sl.set_mode = _set_mode
sl.log_instructor_action = lambda *a, **k: None
sl.reset_flight_state = lambda: resets.append(True)
sl.stop_background_script = lambda name: f"{name} stopped."
sl.status_since = lambda *a, **k: []
sl.wait_for_armed = lambda *a, **k: True
sys.modules["simulator_link"] = sl

st = types.ModuleType("sim_target")
st.MODEL = "standard_vtol_0"
st.WORLD = "training_area_blackrock"
st.service = lambda name: f"/world/{st.WORLD}/{name}"
st.environment = lambda: {"key": "blackrock", "spawn_z": 1.3}
sys.modules["sim_target"] = st

import subprocess
subprocess.run = lambda *a, **k: poses.append(a[0]) or types.SimpleNamespace(returncode=0)

from pymavlink import mavutil  # noqa: E402
ARM_DISARM = mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM


def load(name):
    path = os.path.join(REPO, "plugins", name + ".py")
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


print("1. ARM arms, and does not fly")
arm = load("arm")
for mode in ("Hold / Loiter", "Position", "Manual", "Ready", "Stabilized"):
    sent.clear(); modes.clear()
    sl.telemetry["mode"] = mode
    arm.arm()
    check("%s: armed without changing mode" % mode,
          modes == [] and sent == [(ARM_DISARM, (1,))])

for mode in ("Takeoff", "Mission", "Return to Launch", "Land", "Follow"):
    sent.clear(); modes.clear()
    sl.telemetry["mode"] = mode
    reply = arm.arm()
    check("%s: put into HOLD before arming" % mode, modes == [(4, 3)])
    check("%s: and still armed" % mode, sent == [(ARM_DISARM, (1,))])
    check("%s: and says why" % mode, "HOLD" in reply and mode in reply)

print("2. NEW SESSION clears up")
import plugin_loader  # noqa: E402

gps = types.SimpleNamespace(state={"active": True})
pressed = []


def fake_toggle():
    gps.state["active"] = False
    pressed.append("gps")
    return "GPS failure cleared."


plugin_loader.LOADED = [{"id": "gps_failure", "label": "GPS failure",
                         "handler": fake_toggle, "_module": gps}]

sent.clear(); modes.clear(); poses.clear(); resets.clear()
sl.telemetry["mode"] = "Takeoff"
sl.telemetry["armed"] = True
sl.running_processes = {"gps_proxy": object()}
reply = load("new_session").new_session()

check("switched the failure injection off", pressed == ["gps"])
check("force-disarmed with PX4's 21196 (%s)" % (sent,),
      sent == [(ARM_DISARM, (0, 21196.0))])
check("put PX4 into HOLD", modes == [(4, 3)])
check("repositioned to the world's own spawn height",
      len(poses) == 1 and "z: 1.3" in " ".join(poses[0]))
check("addressed the running world", any(st.WORLD in a for a in poses[0]))
check("cleared the flight record", resets == [True])
check("said what it did (%s...)" % reply[:40],
      "cleared" in reply and "HOLD" in reply and "spawn" in reply)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
