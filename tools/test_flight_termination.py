"""Check the flight-termination control without PX4 running.

    python3 tools/test_flight_termination.py

The guard is the point: there is no undo once PX4 enters TERMINATION, so a
single mis-click would end a lesson. These checks pin the two-press
behaviour, the expiry of a forgotten arming press, the refusal while
disarmed, and - as much as a test can - the honesty of the message, which
has to say that no canopy appears in the simulator.
"""
import importlib.util, os, sys, types, time
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sl = types.ModuleType("simulator_link")
sent = []
sl.telemetry = {"armed": True}
sl.log_instructor_action = lambda *a: None
def fake_send(cmd, *params):
    sent.append((cmd, params))
    return (0, "accepted")
sl.send_command_and_wait = fake_send
sys.modules["simulator_link"] = sl
spec = importlib.util.spec_from_file_location("ft", os.path.join(REPO, "plugins", "flight_termination.py"))
FT = importlib.util.module_from_spec(spec); spec.loader.exec_module(FT)

fails = []
def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond: fails.append(tag)

print("1. one press only arms it")
msg = FT.terminate_flight()
check("armed, nothing sent", "ARMED" in msg and sent == [])

print("2. the second press sends the real command")
msg = FT.terminate_flight()
check("sent DO_FLIGHTTERMINATION (185)", sent and sent[0][0] == 185)
check("param1 is the real termination, not the off value", sent[0][1][0] == 1.0)
check("says no canopy appears", "no canopy" in msg)
check("says how to recover", "Reset Scenario" in msg)

print("3. an arming press expires rather than lingering")
sent.clear(); FT.state["armed_at"] = None; FT.state["active"] = False
FT.terminate_flight()
FT.state["armed_at"] = time.monotonic() - (FT.ARM_WINDOW_S + 1)
msg = FT.terminate_flight()
check("re-arms instead of firing", "ARMED" in msg and sent == [])

print("4. disarmed is refused before anything is sent")
sent.clear(); FT.state["armed_at"] = time.monotonic(); sl.telemetry["armed"] = False
msg = FT.terminate_flight()
check("refused", "disarmed" in msg and sent == [])
print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
