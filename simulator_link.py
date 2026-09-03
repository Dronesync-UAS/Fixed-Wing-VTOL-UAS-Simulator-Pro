"""
Shared connection to the simulator. Plugins import `master` from here
rather than each opening their own connection.

Waiting for PX4's first heartbeat can take a little while, or hang
altogether if the simulator hasn't been started yet. That wait now runs
in a background thread instead of blocking this whole module from
finishing its import - which used to freeze the app before its window
had even opened. instructor_station.py reads `connection_status` to show
a "Connecting to the simulator" screen in the app itself until PX4
answers.
"""

import threading
import subprocess
import time
from pymavlink import mavutil

import event_logger

# Tracks any background scripts plugins start (video stream, proxies, etc)
# so the same one isn't launched twice.
running_processes = {}


def start_background_script(name, command_list):
    proc = running_processes.get(name)
    if proc is not None and proc.poll() is None:
        return f"{name} is already running."
    running_processes[name] = subprocess.Popen(command_list)
    return f"{name} started."


def stop_background_script(name):
    proc = running_processes.get(name)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        return f"{name} stopped."
    return f"{name} was not running."


PX4_MODES = {
    (1, 0): "Manual", (2, 0): "Altitude", (3, 0): "Position",
    (4, 1): "Ready", (4, 2): "Takeoff", (4, 3): "Hold / Loiter",
    (4, 4): "Mission", (4, 5): "Return to Launch", (4, 6): "Land",
    (4, 8): "Follow", (5, 0): "Acro", (6, 0): "Offboard",
    (7, 0): "Stabilized", (8, 0): "Rattitude",
}

telemetry = {
    "armed": False, "mode": "Unknown", "altitude_m": 0.0,
    "altitude_amsl_m": None,
    "groundspeed_ms": 0.0, "battery_pct": None,
    "heading_deg": 0, "satellites": None,
}
# altitude_amsl_m is the aircraft's real height above sea level, as PX4
# itself understands it - not height above the ground/spawn point (that's
# altitude_m, above). Added 23 Aug 2026 because the TAKEOFF button was
# sending PX4 a plain "20" as its target and PX4 read that as "20 metres
# above sea level" - fine on a low-elevation world, but this training
# area's real Hoggar Mountains location sits at roughly 2000m above sea
# level, so "20" meant "descend about 2km", which PX4 correctly refused
# every time with "Already higher than takeoff altitude (not descending)".
# takeoff.py now reads this value and adds the intended climb to it
# before sending the command, instead of sending a bare number.

# Read by instructor_station.py to show the "Connecting to the simulator"
# screen until PX4 replies.
connection_status = {"connected": False, "message": "Connecting to the simulator..."}

master = mavutil.mavlink_connection('udpin:localhost:14540')


def _decode_mode(custom_mode):
    main_mode = (custom_mode >> 16) & 0xFF
    sub_mode = (custom_mode >> 24) & 0xFF
    return PX4_MODES.get((main_mode, sub_mode), f"Mode {main_mode}.{sub_mode}")


# ---------------------------------------------------------------------------
# Failure-injection vs. student-response logging.
#
# When the instructor injects a failure, the vehicle's state at that instant
# is recorded here. The telemetry loop below then watches for the aircraft's
# *own* next mode change (the student's control input, coming from whatever
# the student is actually flying with) and logs that as the response, with a
# reaction time. If the instructor acts first instead (e.g. takes over with
# RTL), that's logged separately as an instructor intervention, so an
# instructor's own corrective action is never mistaken for a student
# decision. If nothing happens for RESPONSE_TIMEOUT_S, that silence is
# logged too, rather than just letting the window close unrecorded.
#
# This is a sensible default, not a final assessment-logging design - what
# exactly should count as "the student's response" is a question for your
# Head of Training (see the compliance notes for this project).
#
# REVISED 23 Aug 2026: this used to track only ONE pending failure at a
# time in a single shared slot. A live test that day stacked several
# failures close together (RC signal, GPS, engine, motor, data link, all
# within about a minute) and showed the real consequence: injecting a
# second failure before the first was resolved silently overwrote the
# first one's tracking, so its eventual "cleared" log entry no longer
# matched what had actually happened. Failures are now tracked in a
# dictionary keyed by component name, so several can be pending at once
# and each is closed out correctly on its own. When more than one is
# active at the moment a response/intervention/timeout is logged, that's
# noted explicitly (multiple_failures_active=true) rather than silently
# attributing one mode change to only one of them - a genuine ambiguity
# (which failure was the student actually reacting to?) worth flagging
# in the record rather than guessing, particularly relevant to your Head
# of Training's eventual grading design.
# ---------------------------------------------------------------------------
RESPONSE_TIMEOUT_S = 45

_active_failures = {}  # component name -> {"start", "start_mode", "start_alt"}
_failure_lock = threading.Lock()


def mark_failure_injected(component, extra=""):
    """Call right after an instructor plugin injects a failure, so the
    aircraft's next mode change can be matched back to it as the
    student's response."""
    with _failure_lock:
        _active_failures[component] = {
            "start": time.monotonic(),
            "start_mode": telemetry["mode"],
            "start_alt": telemetry["altitude_m"],
        }
    details = f"component={component} type=off mode_at_injection={telemetry['mode']} alt_at_injection_m={telemetry['altitude_m']}"
    if extra:
        details += f" {extra}"
    event_logger.log_event("failure_injected", details)


def mark_failure_cleared(component):
    """Call when an instructor plugin clears/restores a failure it injected."""
    with _failure_lock:
        _active_failures.pop(component, None)
    event_logger.log_event("failure_cleared", f"component={component}")


def log_instructor_action(event_type, details=""):
    """Call from any instructor-console plugin that issues a command to the
    aircraft or the simulation (arm, RTL, freeze, reset, etc). Logs the
    action itself, and - if any failures are currently awaiting the
    student's response - closes each of them out as an instructor
    intervention instead of letting the resulting telemetry change be
    mistaken for what the student decided to do."""
    with _failure_lock:
        pending = list(_active_failures.items())
        _active_failures.clear()
    event_logger.log_event(event_type, details)
    multi = len(pending) > 1
    for component, f in pending:
        reaction_s = round(time.monotonic() - f["start"], 1)
        extra = " multiple_failures_active=true" if multi else ""
        event_logger.log_event(
            "instructor_intervened",
            f"component={component} action={event_type} time_since_injection_s={reaction_s}{extra}",
        )


def _check_failure_response(new_mode):
    """Called on every heartbeat with the aircraft's current mode. Any
    active failures whose mode-at-injection differs from this new mode
    are treated as having just received their first observable sign of
    the student reacting (a mode change from the student's own input,
    not one this console just sent - log_instructor_action() already
    intercepts and relabels those)."""
    with _failure_lock:
        responded = [(c, f) for c, f in _active_failures.items() if new_mode != f["start_mode"]]
        for component, _ in responded:
            _active_failures.pop(component, None)
    multi = len(responded) > 1
    for component, f in responded:
        reaction_s = round(time.monotonic() - f["start"], 1)
        extra = " multiple_failures_active=true" if multi else ""
        event_logger.log_event(
            "student_response",
            f"component={component} reaction_time_s={reaction_s} mode_before={f['start_mode']} mode_after={new_mode}{extra}",
        )


def _watch_for_no_response():
    """Runs continuously alongside the telemetry loop. Any failure that
    has been awaiting a response for longer than RESPONSE_TIMEOUT_S is
    logged as such - a flat line (no mode change at all) is itself a
    finding worth having in the record, not just silence."""
    while True:
        time.sleep(5)
        with _failure_lock:
            timed_out = [
                (c, f) for c, f in _active_failures.items()
                if (time.monotonic() - f["start"]) > RESPONSE_TIMEOUT_S
            ]
            for component, _ in timed_out:
                _active_failures.pop(component, None)
        for component, f in timed_out:
            event_logger.log_event(
                "no_mode_change_response",
                f"component={component} mode_throughout={f['start_mode']} timeout_s={RESPONSE_TIMEOUT_S}",
            )


threading.Thread(target=_watch_for_no_response, daemon=True).start()


def _telemetry_loop():
    while True:
        msg = master.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        t = msg.get_type()
        if t == "HEARTBEAT":
            telemetry["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            new_mode = _decode_mode(msg.custom_mode)
            _check_failure_response(new_mode)
            telemetry["mode"] = new_mode
        elif t == "GLOBAL_POSITION_INT":
            telemetry["altitude_m"] = round(msg.relative_alt / 1000.0, 1)
            telemetry["altitude_amsl_m"] = round(msg.alt / 1000.0, 1)
        elif t == "VFR_HUD":
            telemetry["groundspeed_ms"] = round(msg.groundspeed, 1)
            telemetry["heading_deg"] = msg.heading
        elif t == "GPS_RAW_INT":
            telemetry["satellites"] = msg.satellites_visible
        elif t == "BATTERY_STATUS":
            if msg.battery_remaining >= 0:
                telemetry["battery_pct"] = msg.battery_remaining


def _connect_then_start_telemetry():
    """Waits for PX4's first heartbeat without blocking the rest of the
    app from starting, updating the on-screen message while it waits so
    the instructor isn't just looking at a frozen window."""
    start = time.monotonic()
    print("Connecting to the simulator...")
    while not master.wait_heartbeat(timeout=3):
        waited = int(time.monotonic() - start)
        connection_status["message"] = (
            f"Still waiting for the simulator ({waited}s)... "
            "check that PX4 and Gazebo are running."
        )
    connection_status["connected"] = True
    connection_status["message"] = "Connected."
    print("Connected.")
    event_logger.log_event("session_start")
    _telemetry_loop()


threading.Thread(target=_connect_then_start_telemetry, daemon=True).start()
