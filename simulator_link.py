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

import math
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
    (3, 1): "Orbit", (3, 2): "Position (slow)",
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
    # Attitude from the ATTITUDE message (degrees) - added 3 Sep 2026 to
    # drive the FPV camera's artificial-horizon / gyro overlay.
    "roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0,
    "airspeed_ms": 0.0,
}

# Rolling record of where the aircraft has actually been, for the "Flight
# Path" plan-view window in the instructor station. Each point is
# (lat, lon, relative_alt_m, t_monotonic). Capped so a long session can't
# grow this without bound.
flight_path = []
_MAX_PATH_POINTS = 4000
home_latlon = {"lat": None, "lon": None}

# Last COMMAND_ACK seen for each command id, so a plugin can send a
# command and then find out whether PX4 actually accepted it (added
# 3 Sep 2026 - "the button does nothing" is almost always PX4 rejecting
# the command for a state reason it never surfaced).
command_acks = {}
MAV_RESULT_NAMES = {
    0: "accepted", 1: "temporarily rejected", 2: "denied",
    3: "unsupported", 4: "failed", 5: "in progress", 6: "cancelled",
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


def send_command_and_wait(command, *params, timeout=2.0):
    """Send a COMMAND_LONG and wait briefly for its COMMAND_ACK.

    Returns (result_code, human_text). result_code is the MAV_RESULT int,
    or None if PX4 never acknowledged. The telemetry loop is the only
    thread that reads the MAVLink socket; it stashes COMMAND_ACKs in
    `command_acks` and this function just polls that dict, so there's no
    contention over the connection."""
    params = (list(params) + [0.0] * 7)[:7]
    command_acks.pop(command, None)
    sent_at = time.monotonic()
    master.mav.command_long_send(
        master.target_system, master.target_component, command, 0, *params)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        ack = command_acks.get(command)
        if ack and ack["t"] >= sent_at:
            return ack["result"], MAV_RESULT_NAMES.get(ack["result"], f"result {ack['result']}")
        time.sleep(0.05)
    return None, "no acknowledgement from PX4"


def set_mode(main_mode, sub_mode=0, name=None):
    """Switch PX4 flight mode via MAV_CMD_DO_SET_MODE and report back what
    PX4 actually did. param2/param3 carry the PX4 custom main/sub mode
    numbers directly (NOT the bit-shifted HEARTBEAT packing - that only
    applies to the separate SET_MODE message; see Commander.cpp)."""
    label = name or f"mode {main_mode}.{sub_mode}"
    result, text = send_command_and_wait(
        mavutil.mavlink.MAV_CMD_DO_SET_MODE,
        mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, main_mode, sub_mode)
    if result == 0:
        return f"{label}: accepted by PX4."
    if result is None:
        return f"{label}: no response from PX4 (is it connected?)."
    return f"{label}: PX4 {text} the mode change."


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
            lat, lon = msg.lat / 1e7, msg.lon / 1e7
            if lat or lon:
                if home_latlon["lat"] is None:
                    home_latlon["lat"], home_latlon["lon"] = lat, lon
                if not flight_path or abs(flight_path[-1][0] - lat) + abs(flight_path[-1][1] - lon) > 1e-6:
                    flight_path.append((lat, lon, telemetry["altitude_m"], time.monotonic()))
                    if len(flight_path) > _MAX_PATH_POINTS:
                        del flight_path[0]
        elif t == "HOME_POSITION":
            home_latlon["lat"] = msg.latitude / 1e7
            home_latlon["lon"] = msg.longitude / 1e7
        elif t == "ATTITUDE":
            telemetry["roll_deg"] = round(math.degrees(msg.roll), 1)
            telemetry["pitch_deg"] = round(math.degrees(msg.pitch), 1)
            telemetry["yaw_deg"] = round(math.degrees(msg.yaw) % 360, 1)
        elif t == "VFR_HUD":
            # airspeed is NaN until PX4 has a usable airspeed estimate
            # (e.g. sitting on the ground) - NaN is not valid JSON and
            # breaks the whole /telemetry parse in the browser, so clamp it.
            telemetry["groundspeed_ms"] = round(msg.groundspeed, 1) if math.isfinite(msg.groundspeed) else 0.0
            telemetry["airspeed_ms"] = round(msg.airspeed, 1) if math.isfinite(msg.airspeed) else 0.0
            telemetry["heading_deg"] = msg.heading
        elif t == "GPS_RAW_INT":
            telemetry["satellites"] = msg.satellites_visible
        elif t == "BATTERY_STATUS":
            if msg.battery_remaining >= 0:
                telemetry["battery_pct"] = msg.battery_remaining
        elif t == "COMMAND_ACK":
            command_acks[msg.command] = {"result": msg.result, "t": time.monotonic()}


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

