"""Check the flight log against a flight worked out by hand.

    python3 tools/test_flight_log.py

Needs neither PX4 nor Gazebo. The recorder is driven with a made-up
sortie whose every number is known in advance, so each figure in the
summary can be checked rather than merely inspected.

The flight: arm on the pad, climb to 80 m, transition, run out to 400 m
at 22 m/s, come back, land firmly, disarm. One deliberate excursion
above a 120 m ceiling, so the limit-breach figures have something to
report.
"""
import json
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


def near(a, b, tol):
    return a is not None and abs(a - b) <= tol


import flight_log                                           # noqa: E402

work = tempfile.mkdtemp()
flight_log.LOG_DIR = work
flight_log.INDEX_FILE = os.path.join(work, "flights.jsonl")

LIMITS = {"ceiling_m": 120.0, "range_m": 500.0, "groundspeed_ms": 25.0}

telemetry = {"armed": False, "mode": "Hold", "vtol_state": None,
             "in_air": False, "latitude": 23.5, "longitude": 6.5,
             "altitude_m": 0.0, "altitude_amsl_m": 1200.0,
             "groundspeed_ms": 0.0, "airspeed_ms": 0.0,
             "range_from_home_m": 0.0, "battery_pct": 98,
             "roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0,
             "heading_deg": 0, "satellites": 12, "throttle_pct": 0.0}

recorder = flight_log.Recorder(telemetry, lambda: LIMITS,
                               lambda: {"ready": True, "outstanding": []},
                               session_id="TEST", world_source=lambda: "flat_test")

clock = [0.0]


def step(seconds=0.5, **changes):
    telemetry.update(changes)
    clock[0] += seconds
    return recorder.tick(clock[0])


print("1. a flight starts at ARM and not before")
step(0.5)
check("nothing is recorded while disarmed", recorder.current is None)
step(0.5, armed=True, mode="Takeoff")
check("arming starts a flight", recorder.current is not None)
folder = recorder.current.folder

print("2. flying it")
# Climb to 80 m in 20 s - 4 m/s. Half-second samples.
for i in range(1, 41):
    step(0.5, altitude_m=i * 2.0, altitude_amsl_m=1200.0 + i * 2.0,
         in_air=i * 2.0 > 1.5, vtol_state="Hover", groundspeed_ms=1.0,
         battery_pct=98 - i // 8)
check("the climb rate was caught (max %.1f m/s)"
      % recorder.current.peak["climb_ms"],
      near(recorder.current.peak["climb_ms"], 4.0, 0.2))

# Transition and run out to 400 m at 22 m/s.
step(0.5, vtol_state="Transitioning to fixed wing", airspeed_ms=14.0)
for i in range(1, 41):
    step(0.5, vtol_state="Fixed wing", mode="Hold", groundspeed_ms=22.0,
         airspeed_ms=23.0, range_from_home_m=i * 10.0, altitude_m=80.0,
         altitude_amsl_m=1280.0)
check("the range was caught", near(recorder.current.peak["range_from_home_m"], 400.0, 1))
check("so was the ground speed", near(recorder.current.peak["groundspeed_ms"], 22.0, 0.1))
check("a transition was noticed", len(recorder.current.transitions) >= 1)

print("3. an excursion above the ceiling")
# Ten seconds at 135 m: 20 samples of half a second.
for _ in range(20):
    step(0.5, altitude_m=135.0, altitude_amsl_m=1335.0)
breach = recorder.current.breaches.get("ceiling")
check("the ceiling breach was recorded", breach is not None)
check("for about ten seconds (%.1f)" % (breach or {}).get("seconds", -1),
      near((breach or {}).get("seconds"), 10.0, 0.6))
check("with the worst height (%.1f)" % (breach or {}).get("worst", -1),
      near((breach or {}).get("worst"), 135.0, 0.1))
check("and no range breach, because it stayed inside 500 m",
      "range" not in recorder.current.breaches)

print("4. coming back and landing firmly")
step(0.5, vtol_state="Transitioning to hover", groundspeed_ms=8.0)
for i in range(1, 28):
    step(0.5, vtol_state="Hover", altitude_m=max(0.0, 135.0 - i * 5.0),
         altitude_amsl_m=1200.0 + max(0.0, 135.0 - i * 5.0),
         groundspeed_ms=2.0, range_from_home_m=max(0.0, 400.0 - i * 15.0))
check("the sink rate was caught (max %.1f m/s)"
      % recorder.current.peak["sink_ms"],
      near(recorder.current.peak["sink_ms"], 10.0, 0.5))
step(0.5, altitude_m=0.0, in_air=False, groundspeed_ms=0.0, vtol_state="Hover")
check("the landing sink rate was taken from just before touchdown (%s)"
      % recorder.current.landing_sink_ms,
      recorder.current.landing_sink_ms is not None
      and recorder.current.landing_sink_ms >= 9.0)

print("5. the flight ends, and only after the grace period")
step(0.5, armed=False)
check("a momentary disarm does not end it", recorder.current is not None)
step(flight_log.REARM_GRACE_S + 1.0, armed=False)
check("but a real one does", recorder.current is None)
summary = recorder.last
check("a summary came back", summary is not None)

print("6. the numbers in the summary")
check("it left the ground", summary["left_the_ground"] is True)
check("the maximum height (%s)" % summary["max_alt_agl_m"],
      near(summary["max_alt_agl_m"], 135.0, 0.1))
check("the maximum range (%s)" % summary["max_range_m"],
      near(summary["max_range_m"], 400.0, 1))
check("time in fixed wing is counted (%s s)" % summary["time_fixed_wing_s"],
      summary["time_fixed_wing_s"] > 15.0)
check("and time in hover (%s s)" % summary["time_hover_s"],
      summary["time_hover_s"] > 15.0)
check("battery used (%s%%)" % summary["battery_used_pct"],
      summary["battery_used_pct"] and summary["battery_used_pct"] > 0)
check("the modes are broken down", "Takeoff" in summary["modes_s"]
      and "Hold" in summary["modes_s"])
check("the checklist state was captured",
      summary["checklist"] == {"ready": True, "outstanding": []})
check("the session id is on it", summary["session_id"] == "TEST")
check("so is the world", summary["world"] == "flat_test")

print("7. what landed on disk")
check("the track was written", os.path.exists(os.path.join(folder, "track.csv")))
check("so was the summary", os.path.exists(os.path.join(folder, "summary.json")))
rows = open(os.path.join(folder, "track.csv")).read().splitlines()
check("the track has a header and many rows (%d)" % len(rows), len(rows) > 100)
check("the header is the documented column list",
      rows[0].split(",") == flight_log.COLUMNS)
saved = json.load(open(os.path.join(folder, "summary.json")))
check("the saved summary matches the one returned",
      saved["max_alt_agl_m"] == summary["max_alt_agl_m"])

listed = flight_log.recent()
check("the flight appears in the index", len(listed) == 1
      and listed[0]["folder"] == folder)

print("8. a flight that never leaves the ground is still a flight")
clock[0] += 1.0
step(0.5, armed=True, altitude_m=0.0, in_air=False, mode="Hold",
     vtol_state="Hover", groundspeed_ms=0.0, range_from_home_m=0.0)
for _ in range(6):
    step(0.5)
step(0.5, armed=False)
step(flight_log.REARM_GRACE_S + 1.0, armed=False)
ground = recorder.last
check("it was recorded", ground is not None and ground["folder"] != folder)
check("and marked as never having left the ground",
      ground["left_the_ground"] is False)
check("the index now has two", len(flight_log.recent()) == 2)

shutil.rmtree(work, ignore_errors=True)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
