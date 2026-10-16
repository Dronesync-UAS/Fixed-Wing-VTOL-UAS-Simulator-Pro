"""Checks every instructor control reports what actually happened:

    python3 tools/audit_commands.py

Two passes, with the MAVLink layer stubbed and no real process started:

  * PX4 controls - every handler is called once with PX4 refusing and once
    with PX4 silent, and fails if it claims success either time.
  * Gazebo controls - every handler that calls a Gazebo service is called
    once with every service timing out the way gz really does (exit 0, a
    message on stderr), and fails if it claims success, flips its own
    state, or writes the action into the assessment record anyway.

Why this exists: until 11 Oct 2026 not one plugin checked the COMMAND_ACK,
although simulator_link.send_command_and_wait had been there all along. Every
button fired blind and returned a success message, so a refused command was
indistinguishable from an obeyed one - which cost an afternoon of chasing
"the commands do not respond properly" when PX4 had been refusing them and
saying so. Run this after adding or changing a control.

REVISED 16 Oct 2026. From 12 Oct this check had quietly stopped covering the
controls that matter most. Its stand-in for simulator_link lacked names
added that day (FAILURE_TYPE_OFF, home_amsl, set_param, ...), so every
failure injection, TAKEOFF, NEW SESSION and the VTOL sequences failed to
import and were never called - while the summary still said "Checked 23
MAVLink controls". Gazebo controls were skipped outright, which is how
FREEZE and RESET TO SPAWN came to claim success whatever Gazebo said.
Constants are now read from simulator_link.py itself, a control that cannot
be loaded is counted and named in the summary, sequences are run step by
step, and the Gazebo controls have their own pass.

Exit code 0 if every control is honest, 1 otherwise.
"""
import ast
import importlib.util
import os
import subprocess
import sys
import tempfile
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# Keep this check off any simulator that is running. It calls real handlers,
# and some reach Gazebo through its Python bindings (the aircraft lights) or
# through helper modules rather than a subprocess - so a run with the
# simulator up could change the live world. A private transport partition
# means no running Gazebo can hear anything sent from here. Set before
# anything below imports gz.
os.environ["GZ_PARTITION"] = f"audit_commands_{os.getpid()}"

# No real process is started by this check, ever. ENVIRONMENT stops PX4 and
# Gazebo with kill and starts the launcher with Popen; until 16 Oct 2026 only
# the plugin's own module-level subprocess was replaced, and helpers that
# call subprocess themselves were not. Every plugin and helper here goes
# through subprocess.run or subprocess.Popen (nothing imports them by name or
# uses os.system), so replacing those two covers all of them.
_GZ_OK = types.SimpleNamespace(returncode=0, stdout="data: true\n", stderr="")
# What gz 13.6.0 really does when nothing answers, measured 16 Oct 2026: it
# EXITS 0, prints "Service call timed out" on stderr and nothing on stdout.
# So the exit code says nothing, and a control that trusts it is fooled -
# which is exactly what this models.
_GZ_DOWN = types.SimpleNamespace(returncode=0, stdout="",
                                 stderr="Service call timed out")
# A topic publish gets no reply. With nobody listening, gz topic -p exits 0
# and prints nothing - exactly what it does when it works (measured the same
# day).
_GZ_PUBLISHED = types.SimpleNamespace(returncode=0, stdout="", stderr="")
_PROCESS = {"result": _GZ_OK}


def _fake_run(*args, **kwargs):
    command = args[0] if args else kwargs.get("args", [])
    if (_PROCESS["result"] is _GZ_DOWN and isinstance(command, (list, tuple))
            and "topic" in command):
        return _GZ_PUBLISHED
    return _PROCESS["result"]


class _FakePopen:
    def __init__(self, *args, **kwargs):
        self.pid = 1
        self.returncode = None
        self.stdout = self.stderr = None

    def poll(self):
        # A launch that "fails" exits at once; one that works keeps running.
        if _PROCESS["result"].returncode:
            self.returncode = _PROCESS["result"].returncode
        return self.returncode

    def wait(self, timeout=None):
        return self.poll()

    def communicate(self, *args, **kwargs):
        return _PROCESS["result"].stdout, _PROCESS["result"].stderr

    def terminate(self):
        pass

    kill = terminate


subprocess.run = _fake_run
subprocess.Popen = _FakePopen

# Controls that send nothing PX4 acknowledges. PX4's answer cannot make them
# honest or dishonest, so the PX4 pass leaves them alone.
#
# These call a Gazebo service, which answers - so they get the Gazebo pass.
# Named rather than detected: EXTERNAL VIEW reaches Gazebo through a helper,
# not a subprocess of its own.
GAZEBO = {"freeze", "reset_spawn", "external_view", "time_of_day"}
# And these are checked by neither pass:
#   environment       - see NEVER_CALL
#   gps_failure       - a PARAM_SET, which PX4 never acknowledges; it reads
#                       the satellite count back instead
#   start_video,      - start a background script, which simulator_link's own
#   start_stabilizer    start_background_script reports on
#   wind_gust,        - publish on a Gazebo topic, which has no reply: with
#   conditions,         Gazebo gone, gz exits 0 and prints nothing, exactly
#   weather,            as when it works. No check inside the control could
#   aircraft_lights     tell the two apart, so neither can this one.
#   ceiling, operating_envelope, mission_plan - the station's own settings
NON_MAVLINK = GAZEBO | {"environment", "gps_failure", "start_video",
                        "start_stabilizer", "wind_gust", "conditions",
                        "weather", "aircraft_lights", "ceiling",
                        "operating_envelope", "mission_plan"}

# Never called at all. ENVIRONMENT stops the whole simulator and starts
# another; even with every process stubbed it is not something to press
# from a check.
NEVER_CALL = {"environment"}

# What a reply has to contain for it to count as saying "that did not work".
HONEST_WORDS = ("refus", "denied", "not sent", "no acknowledgement",
                "not confirmed", "no response", "not injected", "not cleared",
                "rejected", "unsupported", "failed",
                # Added 16 Oct 2026 - honest replies the list did not know:
                # "Idle spin not set - ...", "Not planned - ...",
                # "Weather not changed - ...", "Service call timed out".
                "not set", "not planned", "not changed", "timed out",
                "could not", "cannot")

RESULT = {"value": None, "text": ""}

# What the last sequence did, step by step. The real start_sequence runs the
# steps on a thread and reports through say_step; the handler's own reply is
# only "started". So the steps are run here, in order, and the verdict is
# taken from how the sequence ENDED, not from how it began.
SEQUENCE = {"said": [], "end": None}

# Every log_instructor_action call, so the Gazebo pass can tell whether a
# control wrote its action into the assessment record when nothing happened.
LOGGED = []


def _real_constants():
    """simulator_link's own UPPER_CASE constants, read from its source.

    The stand-in used to copy these by hand, and it fell behind the day
    after it was written. Reading them cannot fall behind. Parsed rather than
    imported because importing simulator_link opens the station's MAVLink
    port.
    """
    source = open(os.path.join(REPO, "simulator_link.py")).read()
    found = {}
    for node in ast.parse(source).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and node.targets[0].id.isupper()):
            try:
                found[node.targets[0].id] = ast.literal_eval(node.value)
            except ValueError:
                pass            # computed from mavutil - not needed here
    return found


def _install_stubs():
    sl = types.ModuleType("simulator_link")
    for name, value in _real_constants().items():
        setattr(sl, name, value)
    sl.telemetry = {"altitude_m": 100.0, "altitude_amsl_m": 1400.0, "armed": True,
                    "groundspeed_ms": 0.0, "battery_pct": 100, "heading_deg": 0,
                    "satellites": 10, "airspeed_ms": 20.0,
                    # An aircraft hovering at 100 m with a position, so the
                    # controls that refuse without one get as far as PX4.
                    "latitude": 51.0, "longitude": -1.0, "mode": "Hold / Loiter",
                    "in_air": True, "vtol_state": "Hover", "arm_ready": True}
    sl.log_instructor_action = lambda event_type, details="": LOGGED.append(event_type)
    sl.mark_failure_injected = lambda *a, **k: None
    sl.mark_failure_cleared = lambda *a, **k: None
    sl.reset_flight_state = lambda: None
    sl.start_background_script = lambda n, c: "started"
    sl.stop_background_script = lambda n: "stopped"
    sl.running_processes = {}
    sl.status_log = []
    sl.status_since = lambda *a, **k: []
    sl.home_amsl = lambda: 1300.0
    sl.offset_latlon = lambda lat, lon, bearing, distance: (lat, lon)
    sl.failure_injection_blocked = lambda: None

    def send_command_and_wait(command, *params, timeout=2.0):
        return RESULT["value"], RESULT["text"]
    sl.send_command_and_wait = send_command_and_wait

    def set_mode(main_mode, sub_mode=0, name=None):
        label = name or f"mode {main_mode}.{sub_mode}"
        if RESULT["value"] == 0:
            return f"{label}: accepted by PX4."
        if RESULT["value"] is None:
            return f"{label}: no response from PX4 (is it connected?)."
        return f"{label}: PX4 {RESULT['text']} the mode change."
    sl.set_mode = set_mode

    # set_param and read_param, in the words the real ones use.
    def set_param(name, value, integer=True, timeout=2.0):
        if RESULT["value"] == 0:
            return None
        if RESULT["value"] is None:
            return f"{name} was sent but PX4 did not confirm it"
        return (f"{name} came back as 0, not {float(value):g} - "
                "PX4 clamped it to its own limit")
    sl.set_param = set_param
    sl.read_param = lambda *a, **k: None if RESULT["value"] is None else 1.0
    sl.wait_for_armed = lambda *a, **k: RESULT["value"] == 0

    def say_step(text):
        if text:
            SEQUENCE["said"].append(text)
    sl.say_step = say_step

    def start_sequence(name, steps):
        for step in steps:
            problem = step()
            if problem:
                SEQUENCE["end"] = problem
                return True
        SEQUENCE["end"] = SEQUENCE["said"][-1] if SEQUENCE["said"] else None
        return True
    sl.start_sequence = start_sequence
    sl.sequence_running = lambda: False
    sl.cancel_sequence = lambda: None
    # Whatever a step waits for is taken to have arrived, so every sequence
    # reaches the command whose answer is being tested.
    sl.wait_until = lambda *a, **k: True

    class _Mav:
        def __getattr__(self, _):
            return lambda *a, **k: None

    class _Master:
        target_system = 1
        target_component = 1
        mav = _Mav()
    sl.master = _Master()
    sys.modules["simulator_link"] = sl

    # --- stub event_logger so this check never writes to the real compliance CSV ---
    # Added 16 Oct 2026. Stubbing simulator_link does not cover event_logger:
    # plugins and the modules they import (preflight.py, behind NEW SESSION,
    # for one) import it directly, and three tests wrote rows into
    # ~/uas_sim_logs/instructor_events.csv - the CAP722B assessment record -
    # that way. A run measured the same day made no log_event calls, but only
    # because NEW SESSION was one of the controls that failed to import; now
    # that it loads, this stub is what keeps those rows out of the record.
    el = types.ModuleType("event_logger")
    el.log_event = lambda *a, **k: None
    el.read_events = lambda: []
    el.SESSION_ID = "TEST"
    sys.modules["event_logger"] = el

    # --- keep the operating envelope this check picks off the saved one ---
    # Added 16 Oct 2026: the envelope controls save their choice to
    # ~/uas_sim_logs/range_profile.json. Measured that day, a run of this
    # check wrote {"profile": "caa"} there, so running it on a station set to
    # the extended envelope silently put it back on the CAA one. The plugins
    # import range_profile by name, so pointing this one module object at a
    # throwaway file covers every handler. test_range_profile.py does the
    # same.
    import range_profile
    range_profile.STATE_FILE = os.path.join(tempfile.mkdtemp(),
                                            "range_profile.json")

    video = types.ModuleType("video_feed")
    video.resubscribe = lambda: None
    video.camera_fps = lambda: 0.0
    video.camera_latency_ms = lambda: 0.0
    video.start_video_capture = lambda: None
    video.mjpeg_generator = lambda: iter(())
    sys.modules.setdefault("video_feed", video)


def _load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _press(plugin):
    """Call a handler as an instructor would, and return what it reported.

    A two-press control (FLIGHT TERMINATION arms on the first press) is
    pressed again, because the first press sends nothing for PX4 to answer.
    A sequence is judged on how it ended, not on its opening line.
    """
    SEQUENCE["said"].clear()
    SEQUENCE["end"] = None
    reply = plugin["handler"]()
    if "press again" in str(reply).lower():
        reply = plugin["handler"]()
    if SEQUENCE["end"]:
        reply = f"{reply} ... {SEQUENCE['end']}"
    return str(reply)


def _honest(reply):
    lowered = reply.lower()
    return any(word in lowered for word in HONEST_WORDS)


def main():
    _install_stubs()
    import plugin_loader
    plugin_dir = os.path.join(REPO, "plugins")
    failures = []
    not_loaded = []
    loaded = []

    for name in sorted(os.listdir(plugin_dir)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        try:
            module = _load(os.path.join(plugin_dir, name))
        except ImportError as exc:
            missing = getattr(exc, "name", None)
            if "from 'simulator_link'" in str(exc):
                wanted = str(exc).split("'")[1]
                failures.append(
                    f"{name}: NOT CHECKED - this audit's stand-in for "
                    f"simulator_link has no '{wanted}'. Add one in "
                    f"_install_stubs().")
            else:
                failures.append(f"{name}: NOT CHECKED - failed to import "
                                f"({missing or exc})")
            not_loaded.append(name[:-3])
            continue
        except Exception as exc:
            failures.append(f"{name}: NOT CHECKED - failed to import ({exc})")
            not_loaded.append(name[:-3])
            continue
        plugin = getattr(module, "PLUGIN", None)
        if plugin is None:
            failures.append(f"{name}: no PLUGIN dictionary")
            continue
        plugin["_module"] = module
        loaded.append(plugin)

    # One control acts through the others (COUNTER-UAS presses the failure
    # injections, NEW SESSION clears them), and finds them where the station
    # puts them.
    plugin_loader.LOADED[:] = loaded

    px4_checked = []
    for plugin in loaded:
        module = plugin["_module"]
        if plugin["id"] in NON_MAVLINK:
            continue
        px4_checked.append(plugin["id"])
        for value, text, label in ((2, "DENIED", "refusal"), (None, "", "silence")):
            RESULT["value"], RESULT["text"] = value, text
            if hasattr(module, "state"):
                module.state["active"] = False
            try:
                reply = _press(plugin)
            except Exception as exc:
                failures.append(f"{plugin['id']}: raised on {label} - {exc}")
                continue
            if not _honest(reply):
                failures.append(
                    f"{plugin['id']}: claims success when PX4 gave {label}:\n"
                    f"      {reply}")
            # A refused toggle must not flip its own state light.
            if hasattr(module, "state") and module.state.get("active") is True:
                failures.append(
                    f"{plugin['id']}: set its status light active although PX4 gave {label}")
    RESULT["value"], RESULT["text"] = 0, "accepted"

    # The Gazebo pass: every control that talks to Gazebo, with Gazebo down.
    gz_checked = []
    for plugin in loaded:
        module = plugin["_module"]
        if plugin["id"] not in GAZEBO or plugin["id"] in NEVER_CALL:
            continue
        gz_checked.append(plugin["id"])
        before = dict(getattr(module, "state", {}) or {})
        LOGGED.clear()
        _PROCESS["result"] = _GZ_DOWN
        try:
            reply = _press(plugin)
        except Exception as exc:
            failures.append(f"{plugin['id']}: raised with Gazebo down - {exc}")
            continue
        finally:
            _PROCESS["result"] = _GZ_OK
        if not _honest(reply):
            failures.append(
                f"{plugin['id']}: claims success with Gazebo down:\n      {reply}")
        after = dict(getattr(module, "state", {}) or {})
        if after != before:
            failures.append(
                f"{plugin['id']}: changed its own state with Gazebo down "
                f"({before} -> {after})")
        if LOGGED:
            failures.append(
                f"{plugin['id']}: wrote {', '.join(LOGGED)} into the assessment "
                f"record with Gazebo down - nothing happened")

    others = sorted(p["id"] for p in loaded
                    if p["id"] not in px4_checked and p["id"] not in gz_checked)
    print(f"Checked {len(px4_checked)} PX4 controls and {len(gz_checked)} "
          f"Gazebo controls.")
    if not_loaded:
        print(f"COULD NOT CHECK {len(not_loaded)}: {', '.join(not_loaded)}")
    print(f"Not checked by either pass: {', '.join(others)}\n")
    if failures:
        print("PROBLEMS:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"\n{len(failures)} problem(s).")
        return 1
    print("Every control reports refusals, silence and Gazebo failures honestly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
