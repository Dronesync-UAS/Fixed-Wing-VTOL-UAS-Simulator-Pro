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
import tempfile
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
sl.home_amsl = lambda: (None if sl.telemetry.get("altitude_amsl_m") is None
                        else sl.telemetry["altitude_amsl_m"] - sl.telemetry["altitude_m"])
sl.offset_latlon = lambda lat, lon, bearing, dist: (lat, lon)
sl.say_step = lambda *a, **k: None
sl.cancel_sequence = lambda: None
sl.sequence_running = lambda: False
sl.start_sequence = lambda *a, **k: True
sl.wait_until = lambda *a, **k: True
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

new_session = load("new_session")

sent.clear(); modes.clear(); poses.clear(); resets.clear()
sl.telemetry["mode"] = "Takeoff"
sl.telemetry["armed"] = True
sl.running_processes = {"gps_proxy": object()}
reply = new_session.new_session(reset="standard")

check("switched the failure injection off", pressed == ["gps"])
check("standard: force-disarmed with PX4's 21196 (%s)" % (sent,),
      sent == [(ARM_DISARM, (0, 21196.0))])
check("standard: put PX4 into HOLD", modes == [(4, 3)])
check("standard: repositioned to the world's own spawn height",
      len(poses) == 1 and "z: 1.3" in " ".join(poses[0]))
check("standard: addressed the running world", any(st.WORLD in a for a in poses[0]))
check("standard: cleared the flight record", resets == [True])
check("standard: left Gazebo's own models alone",
      not any("reset" in " ".join(p) for p in poses))
check("standard: said what it did (%s...)" % reply[:40],
      "cleared" in reply and "HOLD" in reply and "spawn" in reply)

print("2b. NEW SESSION, hard")
sent.clear(); modes.clear(); poses.clear(); resets.clear()
sl.telemetry["mode"] = "Takeoff"
sl.telemetry["armed"] = True
reply = new_session.new_session(reset="hard")
check("hard: still force-disarms (%s)" % (sent[:1],),
      sent[0] == (ARM_DISARM, (0, 21196.0)))
check("hard: asked Gazebo to reset its models, not its clock",
      any("reset: {model_only: true}" in " ".join(p) for p in poses))
# Winding simulation time back under a running PX4 is the one thing this
# must never do.
check("hard: never asks for a full reset",
      not any("all: true" in " ".join(p) for p in poses))
check("hard: asked PX4 to reboot (%s)" % [c for c, _ in sent],
      any(c == 246 for c, _ in sent))
check("hard: says PX4 may refuse the reboot (%s...)" % reply[-60:],
      "reboot" in reply.lower())
check("hard: still repositioned and cleared the record",
      any("z: 1.3" in " ".join(p) for p in poses) and resets == [True])

print("3. LOITER hands PX4 a real centre")
import math

sl.telemetry.update({"latitude": 40.8750, "longitude": -119.0849,
                     "heading_deg": 0, "altitude_amsl_m": 1250.0,
                     "altitude_m": 50.0, "armed": True, "mode": "Hold / Loiter"})


def _real_offset(lat, lon, bearing_deg, distance_m):
    bearing = math.radians(bearing_deg)
    return (lat + distance_m * math.cos(bearing) / 110540.0,
            lon + distance_m * math.sin(bearing)
            / (111320.0 * math.cos(math.radians(lat))))


sl.offset_latlon = _real_offset
loiter = load("loiter_orbit")
sent.clear()
reply = loiter.loiter(radius_m=150, speed_ms=8)
cmd, params = sent[0]
check("sent DO_ORBIT (%s)" % cmd, cmd == 34)
check("radius and speed are the ones asked for (%s, %s)" % (params[0], params[1]),
      params[0] == 150.0 and params[1] == 8.0)
centre_ok = (params[4] is not None and not math.isnan(params[4])
             and params[5] is not None and not math.isnan(params[5]))
check("the centre is a real point, not NaN (%s, %s)" % (params[4], params[5]),
      centre_ok)
# Heading north, so a clockwise orbit has its centre due east - one radius
# away. The old code sent NaN here and PX4 flew a straight line instead.
north_m = (params[4] - 40.8750) * 110540.0
east_m = (params[5] + 119.0849) * 111320.0 * math.cos(math.radians(40.8750))
check("the centre is one radius off the right wing (%s m north, %s m east)"
      % (round(north_m, 1), round(east_m)),
      abs(north_m) < 1 and abs(east_m - 150) < 2)
check("and the aircraft is therefore on the circle",
      abs(math.hypot(north_m, east_m) - 150) < 2)

print("4. CLIMB / DESCEND TO")
climb = load("climb_to")
sl.telemetry.update({"armed": False})
check("refused while disarmed", "disarmed" in climb.climb_to(60).lower())
sl.telemetry.update({"armed": True})
check("refused above the ceiling", "between" in climb.climb_to(200))
sent.clear()
reply = climb.climb_to(80)
cmd, params = sent[0]
check("sent DO_CHANGE_ALTITUDE (%s)" % cmd, cmd == 186)
# Home sits at 1250 - 50 = 1200 m above sea level, so 80 m above home is
# 1280. PX4 reads this number as a height above SEA LEVEL.
check("converted 80 m above home into 1280 m above sea level (%s)" % params[0],
      abs(params[0] - 1280.0) < 0.01)
check("said both numbers (%s...)" % reply[:46],
      "80" in reply and "1280" in reply)

print("5. FORWARD FLIGHT")
steps_held = []
sl.start_sequence = lambda name, steps: steps_held.extend(steps) or True
sl.sequence_running = lambda: False
fwd = load("forward_flight")
sl.telemetry.update({"armed": True, "in_air": True, "altitude_m": 20.0,
                     "altitude_amsl_m": 1220.0, "vtol_state": "Hover",
                     "mode": "Hold / Loiter", "heading_deg": 0,
                     "latitude": 40.8750, "longitude": -119.0849})
check("refused below the minimum transition height",
      "no height to trade" in fwd.forward_flight(transition_m=10, cruise_m=100))
check("refused a cruise above the ceiling",
      "ceiling" in fwd.forward_flight(transition_m=40, cruise_m=200))
sl.telemetry.update({"in_air": False})
check("refused on the ground", "on the ground" in fwd.forward_flight())
sl.telemetry.update({"in_air": True})

steps_held.clear(); sent.clear(); modes.clear()
reply = fwd.forward_flight(transition_m=40, cruise_m=100)
check("accepted from 20 m instead of refusing (%s...)" % reply[:38],
      "climbing straight ahead" in reply)
# Seven since 12 Oct 2026: wings-level before the transition, and
# accelerate straight after it. A real VTOL transitions wings-level and
# does not turn until it is flying on the wing - see step_wings_level
# and step_settle for the PX4 figures behind that.
check("queued the seven steps (%s)" % len(steps_held), len(steps_held) == 7)

# The two that keep a transition safe, checked for what they actually
# wait on rather than only counted.
fwd_waits = {"rolls": 0}
sl.telemetry["roll_deg"] = 55.0          # hard over, mid-turn


def _level_out(predicate, timeout, poll=0.25):
    fwd_waits["rolls"] += 1
    if fwd_waits["rolls"] >= 2:
        sl.telemetry["roll_deg"] = 3.0
    return predicate()


_saved_wait = fwd.wait_until
fwd.wait_until = _level_out
sent.clear()
steps_held[3]()                           # step_wings_level
check("waits for wings level before transitioning, and does not "
      "command anything while it waits",
      fwd_waits["rolls"] >= 1 and not sent)

# And after the transition: accelerate straight before any turn.
fwd_waits["accel"] = 0
sl.telemetry["airspeed_ms"] = 9.0         # only just wing-borne


def _accelerate(predicate, timeout, poll=0.25):
    fwd_waits["accel"] += 1
    if fwd_waits["accel"] >= 2:
        sl.telemetry["airspeed_ms"] = 20.0
    return predicate()


fwd.wait_until = _accelerate
sent.clear()
steps_held[5]()                           # step_settle
check("waits to accelerate on the wing before turning (%d waits)"
      % fwd_waits["accel"], fwd_waits["accel"] >= 1)
check("and commands nothing while it does", not sent)
fwd.wait_until = _saved_wait
sl.telemetry.update({"roll_deg": 0.0, "airspeed_ms": 22.0})

# Run the steps by hand, with the aircraft reported as climbing: high
# enough to transition at once, then arriving at cruise height after a few
# climb-out legs, so the loop that keeps the climb straight is exercised
# rather than skipped.
sl.telemetry.update({"altitude_m": 45.0, "vtol_state": "Fixed wing",
                     "range_from_home_m": 100.0,
                     # Wings level and flying on the wing, so the two
                     # new steps pass straight through.
                     "roll_deg": 0.0, "airspeed_ms": 22.0})
climbing = {"n": 0}


def _climb(predicate, timeout, poll=0.25):
    climbing["n"] += 1
    if climbing["n"] >= 3:
        sl.telemetry["altitude_m"] = 100.0
    return predicate()


# Patched on the PLUGIN, not on the stub module. forward_flight.py does
# `from simulator_link import wait_until`, which binds the function at
# import time, so replacing simulator_link's attribute afterwards changes
# nothing the plugin can see - that mistake left this test spinning.
fwd.wait_until = _climb
fwd.time = type("t", (), {"monotonic": __import__("time").monotonic,
                          "sleep": lambda *_: None})
for step in steps_held:
    step()
reposition = [p for c, p in sent if c == mavutil.mavlink.MAV_CMD_DO_REPOSITION]
transition = [p for c, p in sent if c == mavutil.mavlink.MAV_CMD_DO_VTOL_TRANSITION]
check("asked for a transition to fixed wing (%s)" % (transition,),
      len(transition) == 1 and transition[0][0] == 4)
check("flew a climbing run, not a climb on the spot (%s legs)" % len(reposition),
      len(reposition) >= 1)
# REWRITTEN 12 Oct 2026. This used to require the leg to be re-aimed
# REPEATEDLY while climbing, which is what put the aircraft into a
# spiral: every DO_REPOSITION sets a loiter point, and re-aiming it on
# the aircraft's own heading once a second closes a feedback loop
# through the airframe. One leg, held, is now the correct answer.
check("sent ONE climb-out leg, not one a second (%s legs)" % len(reposition),
      len(reposition) == 1)

# The leg must be re-extended only when the aircraft has nearly reached
# it - and along the bearing it started on, NOT wherever the nose is
# pointing by then. This is the check that would have caught the spiral.
# Within ONE run, swing the nose right round while the aircraft climbs
# and stays close to the point it was sent to. Every leg it commands must
# be the SAME point: the bearing is taken once and held. If the targets
# start walking round with the heading, the feedback loop is back and
# the aircraft will spiral.
sl.telemetry.update({"altitude_m": 45.0, "range_from_home_m": 100.0,
                     "heading_deg": 0.0,
                     "latitude": 40.8750, "longitude": -119.0849})
swing = {"n": 0}


def _swing_the_nose(predicate, timeout, poll=0.25):
    swing["n"] += 1
    # The nose wanders 40 degrees further round on every pass.
    sl.telemetry["heading_deg"] = (swing["n"] * 40.0) % 360.0
    # And the aircraft is always nearly on top of its target, so the
    # loop always has a reason to extend the leg.
    if fwd._leg_target["lat"] is not None:
        sl.telemetry["latitude"] = fwd._leg_target["lat"] - 50.0 / 110540.0
        sl.telemetry["longitude"] = fwd._leg_target["lon"]
    if swing["n"] >= 5:
        sl.telemetry["altitude_m"] = 100.0
    return predicate()


fwd.wait_until = _swing_the_nose
sent.clear()
steps_held[-1]()
extended = [p for c, p in sent if c == mavutil.mavlink.MAV_CMD_DO_REPOSITION]
check("re-extended the leg as the aircraft ate into it (%s legs)"
      % len(extended), len(extended) >= 2)
if len(extended) >= 2:
    # The aircraft moves up the track between legs, so comparing each
    # target against one position says nothing. What does: the bearing
    # was due north at the start, so every target must sit on the same
    # meridian and each must be further north than the last. A target
    # that drifts east or west is a bearing following the nose.
    lons = [leg[5] for leg in extended]
    drift_m = ((max(lons) - min(lons)) * 111320.0
               * math.cos(math.radians(40.8750)))
    check("and held one bearing while the nose swung 200 degrees "
          "(%.1f m of sideways drift)" % drift_m, abs(drift_m) < 1.0)
    lats = [leg[4] for leg in extended]
    check("each leg reaching further along that same bearing",
          all(b > a for a, b in zip(lats, lats[1:])))
fwd.wait_until = _climb

# Far from home the leg must stop being extended, rather than walking the
# aircraft out through the station's range limit.
climbing["n"] = 0
sl.telemetry.update({"altitude_m": 45.0, "range_from_home_m": 460.0})
sent.clear()
steps_held[-1]()
check("stopped extending near the range limit",
      not any(c == mavutil.mavlink.MAV_CMD_DO_REPOSITION for c, _ in sent))

if reposition:
    p = reposition[0]
    # Commander answers UNSUPPORTED unless bit 0 of param2 is set.
    check("param2 bit 0 set, or PX4 answers UNSUPPORTED (%s)" % p[1],
          int(p[1]) & 1 == 1)
    # Home's own height is worked out ONCE, when the button is pressed
    # (1220 - 20 = 1200 m), and the later legs keep using it. Home does not
    # move, so re-deriving it from a changing altitude would drift the
    # target upwards as the aircraft climbed. Cruise 100 m above it = 1300.
    check("aimed at the cruise height above sea level (%s)" % p[6],
          abs(p[6] - 1300.0) < 0.01)
    ahead_n = (p[4] - 40.8750) * 110540.0
    check("aimed ahead on the current heading (%s m north)" % round(ahead_n),
          ahead_n > 100)

print("6. the flight track keeps its own beginning")
# A lesson longer than the buffer used to eat the start of its own track:
# `del flight_path[0]` on every point past the cap. The instructor watched
# the first half of the flight vanish while the second half kept drawing.
import re
source = open(os.path.join(REPO, "simulator_link.py"), encoding="utf-8").read()
block = re.search(
    r"(_MAX_PATH_POINTS = \d+\n\n\ndef _trim_flight_path\(\):.*?"
    r"flight_path\[:half\] = flight_path\[0:half:2\])", source, re.S)
check("the trimming code is where this test thinks it is", block is not None)
if block:
    ns = {"flight_path": []}
    exec(block.group(1), ns)
    path, trim = ns["flight_path"], ns["_trim_flight_path"]
    for i in range(40000):
        path.append((i, i, i, i))
        trim()
    check("stays bounded over a very long flight (%s points)" % len(path),
          len(path) <= ns["_MAX_PATH_POINTS"])
    check("the first point of the flight is still the first point (%s)"
          % path[0][0], path[0][0] == 0)
    check("and the latest point is the latest (%s)" % path[-1][0],
          path[-1][0] == 39999)
    # The newest flying is what an instructor is watching, so it must not
    # be the part that gets thinned.
    recent = path[-100:]
    gaps = [recent[i + 1][0] - recent[i][0] for i in range(len(recent) - 1)]
    check("recent flying is kept at full resolution (gap %s)"
          % max(gaps), max(gaps) == 1)

print("7. the counter-UAS encounter")
# It drives the station's existing injections in an order. The things
# worth proving: that it refuses on the ground, that each profile fires
# the effects it claims, and - most of all - that clearing it puts every
# link back, because an encounter nobody can end is not a training
# exercise.
fired = []


class _Toggle:
    def __init__(self, name):
        self.name = name
        self.state = {"active": False}

    def press(self):
        self.state["active"] = not self.state["active"]
        fired.append((self.name, self.state["active"]))
        return "toggled"


toggles = {name: _Toggle(name) for name in
           ("gps_failure", "data_link_loss", "rc_signal_loss")}
plugin_loader.LOADED = [
    {"id": name, "label": name, "handler": t.press, "_module": t}
    for name, t in toggles.items()]

cuas = load("cuas_encounter")
cuas.wait_until = lambda *a, **k: True
ran = []
cuas.start_sequence = lambda name, steps: ran.extend(steps) or True
cuas.sequence_running = lambda: False

sl.telemetry.update({"armed": False})
check("refused on the ground", "disarmed" in cuas.cuas_encounter("gnss"))
sl.telemetry.update({"armed": True, "altitude_m": 60.0, "mode": "Hold / Loiter"})
check("refused an encounter it does not have",
      "not one of" in cuas.cuas_encounter("death ray"))

for name, expect in (("gnss", {"gps_failure"}),
                     ("c2", {"data_link_loss"}),
                     ("layered", {"gps_failure", "data_link_loss"}),
                     ("rf_denial", {"gps_failure", "data_link_loss",
                                    "rc_signal_loss"})):
    for t in toggles.values():
        t.state["active"] = False
    cuas.state["active"] = False
    fired.clear(); ran.clear()
    reply = cuas.cuas_encounter(name)
    for step in ran:
        step()
    hit = {f[0] for f in fired if f[1]}
    check("%s fires %s (%s)" % (name, sorted(expect), sorted(hit)), hit == expect)

check("it says it models no equipment and emits nothing",
      "emits nothing" in reply)

# The one that matters: it must always be possible to end it.
fired.clear()
reply = cuas.cuas_encounter("rf_denial")
check("pressing it again clears instead of stacking", "cleared" in reply)
check("and every link is restored",
      not any(t.state["active"] for t in toggles.values()))
check("the encounter is recorded as ended", not cuas.state["active"])


print("8. switching training area")
# THE FAULT THIS EXISTS FOR, found 12 Oct 2026: six of the twelve
# training areas were in the drop-down but not in tools/start_world.sh's
# own table, so choosing one ran "start_world.sh coast", which answered
# "Unknown world: coast" and exited - into a log file nobody reads,
# while the station reported that the simulator was restarting. A switch
# that fails must say so.
import types as _types                                      # noqa: E402

# video_feed imports the gz bindings at module level, and terrain_backdrop
# reads world files. Neither is what this section is about, so both are
# stood in for - the same trick the rest of this file uses.
for _name, _attrs in (("terrain_backdrop", {"reset": lambda: None}),
                      ("video_feed", {"resubscribe": lambda: None})):
    _m = _types.ModuleType(_name)
    for _k, _v in _attrs.items():
        setattr(_m, _k, _v)
    sys.modules[_name] = _m

# The real sim_target, not this file's stub: section 8 is about the
# environment LIST, and the stub has no list. Section 8 is last, so
# nothing after it sees the swap.
_stspec = importlib.util.spec_from_file_location(
    "sim_target", os.path.join(REPO, "sim_target.py"))
_st = importlib.util.module_from_spec(_stspec)
_stspec.loader.exec_module(_st)
sys.modules["sim_target"] = _st
sim_target = _st

_envspec = importlib.util.spec_from_file_location(
    "env_plugin", os.path.join(REPO, "plugins", "environment.py"))
_env = importlib.util.module_from_spec(_envspec)
_envspec.loader.exec_module(_env)

_unlaunchable = [e["key"] for e in sim_target.ENVIRONMENTS
                 if not _env._launcher_knows(e["key"])]
check("every training area offered is one the launcher can actually "
      "start (%s)" % (", ".join(_unlaunchable) or "all of them"),
      not _unlaunchable)

_holder2 = tempfile.mkdtemp()
_fake = os.path.join(_holder2, "refuser.sh")
with open(_fake, "w") as _h:
    _h.write('#!/bin/bash\necho "Unknown world: $1"\nexit 1\n')
_env.LAUNCHER = _fake
_env.LAUNCH_LOG = os.path.join(_holder2, "launch.log")
_env.LAUNCH_CHECK_S = 2.0
_env._launcher_knows = lambda k: True
_said = _env.select_environment("coast")
check("a launcher that refuses is reported (%s)" % _said[:60],
      "not changed" in _said.lower())
check("and the reason it gave is passed on", "Unknown world" in _said)

with open(_fake, "w") as _h:
    _h.write('#!/bin/bash\necho "Usage: start_world.sh <world>"\nexit 0\n')
_said = _env.select_environment("coast")
check("a launcher that prints its usage and quits is also reported",
      "not changed" in _said.lower() and "Usage" in _said)

import shutil as _sh2                                       # noqa: E402
_sh2.rmtree(_holder2, ignore_errors=True)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
