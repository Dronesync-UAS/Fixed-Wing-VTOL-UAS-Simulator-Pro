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
import sys
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
    # Straight-line distance from the home/launch point, metres. Added
    # 6 Sep 2026 for the operational-limit checks (CAP722B 5.3(c)).
    "range_from_home_m": 0.0,
    # Arming readiness, read straight out of HEARTBEAT.system_status.
    # Added 11 Oct 2026: the console said "Disarmed" but never why PX4 was
    # refusing to arm, so the instructor pressed ARM over and over while the
    # EKF was still converging. See _ARM_STATES for where the values come from.
    "arm_ready": None,                  # True / False / None (no heartbeat yet)
    "arm_state": "Waiting for PX4",     # short label for the console
    "arm_blocker": None,                # PX4's own words, out of STATUSTEXT
    # Where the aircraft is. Added 12 Oct 2026: LOITER has to hand PX4 a
    # centre for its orbit, and that centre is worked out from the
    # aircraft's own position - see plugins/loiter_orbit.py for why NaN
    # (meaning "here") sends it off in a straight line instead.
    "latitude": None, "longitude": None,
    # MAV_VTOL_STATE and MAV_LANDED_STATE out of EXTENDED_SYS_STATE: which
    # half of the VTOL is flying, and whether it is flying at all.
    "vtol_state": None,                 # "Hover", "Fixed wing", "Transitioning..."
    "in_air": None,                     # True / False / None (not reported yet)
    # What a multi-step manoeuvre is doing right now, for the console.
    "sequence": None,
}

VTOL_STATES = {0: None, 1: "Transitioning to fixed wing",
               2: "Transitioning to hover", 3: "Hover", 4: "Fixed wing"}

# HEARTBEAT.system_status (the MAVLink MAV_STATE enum), as PX4 v1.15.4 fills
# it in - src/modules/mavlink/streams/HEARTBEAT.hpp lines 107-127:
#
#     uint8_t system_status = MAV_STATE_UNINIT;
#     if (arming_state == ARMING_STATE_ARMED)   -> ACTIVE, or CRITICAL in failsafe
#     else if (calibration in progress)         -> CALIBRATING
#     else if (pre_flight_checks_pass)          -> STANDBY
#
# Note the first line. When the aircraft is disarmed and its preflight checks
# are NOT passing, nothing overwrites the initial value, so PX4 reports
# MAV_STATE_UNINIT. That is the "ARM will be refused" case - it does not mean
# PX4 is still booting, which is what the name suggests. This readout exists
# precisely to make that state visible.
#
# Written as plain integers (minimal.xml, MAV_STATE) rather than
# mavutil.mavlink.MAV_STATE_* so an older pymavlink missing one of the names
# still imports.
_ARM_STATES = {
    0: (False, "Not ready"),           # MAV_STATE_UNINIT
    1: (False, "Booting"),             # MAV_STATE_BOOT
    2: (False, "Calibrating"),         # MAV_STATE_CALIBRATING
    3: (True,  "Ready to arm"),        # MAV_STATE_STANDBY
    4: (True,  "Armed"),               # MAV_STATE_ACTIVE
    5: (True,  "Armed - failsafe"),    # MAV_STATE_CRITICAL
    6: (False, "Emergency"),           # MAV_STATE_EMERGENCY
    7: (False, "Powering off"),        # MAV_STATE_POWEROFF
    8: (False, "Flight termination"),  # MAV_STATE_FLIGHT_TERMINATION
}

# STATUSTEXT lines that say WHY arming is being refused, e.g.
#   "Preflight Fail: Yaw estimate error"
#   "Preflight: GPS Vertical Pos Drift too high"
# PX4 repeats these for as long as the condition holds, so a recent one is the
# live reason and an older one is history - hence the age check.
_ARM_BLOCKER_PREFIXES = ("preflight", "arming denied", "arm denied")
_ARM_BLOCKER_MAX_AGE_S = 15.0
_arm_blocker = {"text": None, "t": None}

# Every STATUSTEXT PX4 sends, with the time it arrived, so a command can
# report PX4's own words rather than only its COMMAND_ACK. A takeoff is the
# case that needs it: PX4 accepts the command and THEN says what it is
# really doing - "Using default takeoff altitude: 2.5 m", "Already higher
# than takeoff altitude" - and none of that reaches the instructor through
# the ack alone. Capped so a long session cannot grow it without bound.
_STATUS_LOG_MAX = 60
status_log = []

# Link health, for the "how fresh is this data" readout (CAP722B 5.2(d)).
# `last_msg_t` is a time.monotonic() stamp updated every time ANY MAVLink
# message is processed; the instructor station turns it into an age.
link_health = {"last_msg_t": None}

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


# MAV_CMD_INJECT_FAILURE's unit numbers, taken from PX4 v1.15.4's own
# msg/VehicleCommand.msg lines 130-144 (identical to MAVLink's FAILURE_UNIT
# enum). They are NOT a dense 0..n list, which is how the station came to be
# sending 10, 13 and 14 - none of which is a defined value.
FAILURE_UNIT_SYSTEM_MOTOR = 101
FAILURE_UNIT_SYSTEM_SERVO = 102
FAILURE_UNIT_SYSTEM_RC_SIGNAL = 104
FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 105
FAILURE_TYPE_OK = 0
FAILURE_TYPE_OFF = 1

MAV_CMD_INJECT_FAILURE = 420

# PX4 refuses every injection unless this parameter is 1 - see its own
# failure command, src/systemcmds/failure/failure.cpp lines 163-171:
#     if (param != 1) { PX4_ERR("Failure injection disabled by
#                               SYS_FAILURE_EN param."); return 1; }
# Without the check here, a failure button is simply inert and says nothing.
FAILURE_ENABLE_PARAM = "SYS_FAILURE_EN"

_param_values = {}


def read_param(name, timeout=2.0):
    """Ask PX4 for one parameter and wait briefly for its value.

    Returns a float, or None if PX4 did not answer. The telemetry thread is
    the only reader of the socket, so this asks and then polls what that
    thread stored, the same way send_command_and_wait does."""
    _param_values.pop(name, None)
    try:
        master.mav.param_request_read_send(
            master.target_system, master.target_component,
            name.encode("ascii"), -1)
    except Exception:                                      # noqa: BLE001
        return None
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if name in _param_values:
            return _param_values[name]
        time.sleep(0.05)
    return None


def failure_injection_blocked():
    """A sentence explaining why injection will not work, or None.

    Checked once and remembered: the answer cannot change without someone
    setting the parameter, and asking on every button press would add a
    two-second wait to every failure."""
    if _failure_enable.get("checked"):
        return _failure_enable["reason"]
    value = read_param(FAILURE_ENABLE_PARAM)
    _failure_enable["checked"] = True
    if value is None:
        _failure_enable["reason"] = None       # could not ask; do not block
    elif int(value) != 1:
        _failure_enable["reason"] = (
            f"{FAILURE_ENABLE_PARAM} is {int(value)}, so PX4 ignores every "
            "failure injection. In the PX4 window, at its pxh> prompt, type: "
            f"param set {FAILURE_ENABLE_PARAM} 1")
    else:
        _failure_enable["reason"] = None
    return _failure_enable["reason"]


_failure_enable = {"checked": False, "reason": None}


def home_amsl():
    """Height of the home point above sea level, metres, or None.

    PX4 reports both an absolute height and a height relative to home in the
    same message, so the difference is exact rather than a guess - and every
    altitude command PX4 takes is absolute, while every altitude an
    instructor thinks in is above the ground they are standing on."""
    amsl = telemetry.get("altitude_amsl_m")
    rel = telemetry.get("altitude_m")
    if amsl is None or rel is None:
        return None
    return amsl - rel


def offset_latlon(lat, lon, bearing_deg, distance_m):
    """A point `distance_m` away on a given compass bearing.

    Equirectangular, like _range_from_home - exact enough over the few
    hundred metres these controls work in, and it inverts that function so
    the two agree."""
    bearing = math.radians(bearing_deg)
    north = distance_m * math.cos(bearing)
    east = distance_m * math.sin(bearing)
    return (lat + north / 110540.0,
            lon + east / (111320.0 * math.cos(math.radians(lat))))


# ---- multi-step manoeuvres -------------------------------------------
# A VTOL departure is three commands with waits between them: climb, then
# transition once high enough, then climb away. A button handler has to
# return a sentence straight away, so the steps run on their own thread and
# report where they are through telemetry["sequence"], which the console
# already polls.
_sequence_lock = threading.Lock()
_sequence = {"thread": None, "cancel": False}


def sequence_running():
    thread = _sequence["thread"]
    return thread is not None and thread.is_alive()


def cancel_sequence():
    _sequence["cancel"] = True


def say_step(text):
    telemetry["sequence"] = text


def wait_until(predicate, timeout, poll=0.25):
    """True once the predicate holds, False on timeout or cancellation."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _sequence["cancel"]:
            return False
        if predicate():
            return True
        time.sleep(poll)
    return False


def start_sequence(name, steps):
    """Run `steps` - a list of no-argument callables - on a background
    thread. A step returning a string ends the sequence with that message
    (a failure); returning None carries on. Only one runs at a time."""
    with _sequence_lock:
        if sequence_running():
            return False
        _sequence["cancel"] = False

        def run():
            try:
                for step in steps:
                    if _sequence["cancel"]:
                        say_step(f"{name}: stopped.")
                        return
                    problem = step()
                    if problem:
                        say_step(problem)
                        log_instructor_action(name, f"stopped: {problem}")
                        return
                say_step(None)
            except Exception as exc:                       # noqa: BLE001
                say_step(f"{name} failed: {exc}")
                log_instructor_action(name, f"exception: {exc!r}")

        _sequence["thread"] = threading.Thread(target=run, daemon=True)
        _sequence["thread"].start()
        return True


def status_since(since_t, contains=()):
    """PX4's STATUSTEXT lines since a given time.monotonic() stamp.

    `contains` narrows it to lines holding one of those words (lower case),
    so a command can quote the messages that belong to it rather than
    whatever else PX4 happened to say."""
    out = []
    for entry in list(status_log):
        if entry["t"] < since_t:
            continue
        low = entry["text"].lower()
        if contains and not any(word in low for word in contains):
            continue
        out.append(entry["text"])
    return out


def wait_for_armed(timeout=4.0):
    """Block until PX4's heartbeat says the aircraft is armed, or give up.

    The arming state comes from HEARTBEAT, which arrives at 1 Hz, so a
    command sent the instant after an ARM ack would otherwise still see
    the old value."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if telemetry.get("armed"):
            return True
        time.sleep(0.05)
    return bool(telemetry.get("armed"))


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


def _range_from_home(lat, lon):
    """Straight-line ground distance (m) from the home point to (lat, lon),
    equirectangular approximation - fine for the few-km ranges involved."""
    hlat, hlon = home_latlon["lat"], home_latlon["lon"]
    if hlat is None:
        return 0.0
    x = math.radians(lon - hlon) * math.cos(math.radians(hlat)) * 6371000.0
    y = math.radians(lat - hlat) * 6371000.0
    return round(math.hypot(x, y), 1)


def reset_flight_state():
    """Forget everything tied to the world that was running.

    Added 11 Oct 2026 with the environment selector. Without this, switching
    environment left the previous world's track on the plan view and its home
    position in place - so the track showed two worlds at once, and range from
    home was computed against a point thousands of kilometres away, which also
    drives the CAP722B range limit. The telemetry loop re-learns home from the
    next HOME_POSITION or position message.
    """
    flight_path.clear()
    home_latlon["lat"] = None
    home_latlon["lon"] = None
    command_acks.clear()
    telemetry["range_from_home_m"] = 0.0
    telemetry["arm_ready"] = None
    telemetry["arm_state"] = "Waiting for PX4"
    telemetry["arm_blocker"] = None
    _arm_blocker["text"] = None
    _arm_blocker["t"] = None
    link_health["last_msg_t"] = None


def _update_arm_readiness(system_status):
    """Turn HEARTBEAT.system_status into the console's arming readout.

    Kept separate from the HEARTBEAT branch because the interesting part is
    not the lookup, it is deciding when PX4's last complaint has stopped
    being the reason for anything.
    """
    ready, label = _ARM_STATES.get(
        system_status, (False, "Unknown state %s" % system_status))
    telemetry["arm_ready"] = ready
    telemetry["arm_state"] = label
    stale = (_arm_blocker["t"] is None
             or time.monotonic() - _arm_blocker["t"] > _ARM_BLOCKER_MAX_AGE_S)
    # Once PX4 says the checks pass, whatever it was complaining about a
    # moment ago is no longer blocking anything, so don't keep showing it.
    telemetry["arm_blocker"] = None if (ready or stale) else _arm_blocker["text"]


def _telemetry_loop():
    while True:
        try:
            _read_one_message()
        except Exception as exc:
            # This loop is the station's only reader of the MAVLink socket.
            # Any escaping exception - a field missing on a message variant, a
            # log write failing on a full disk - used to end the thread, and
            # the console then froze on its last values with no indication
            # why. Keep reading, and say what happened.
            print(f"[telemetry] ignored a bad message: {exc!r}", file=sys.stderr)
            time.sleep(0.1)


def _read_one_message():
        msg = master.recv_match(blocking=True, timeout=1)
        if msg is None:
            return
        link_health["last_msg_t"] = time.monotonic()
        t = msg.get_type()
        if t == "HEARTBEAT":
            telemetry["armed"] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
            _update_arm_readiness(msg.system_status)
            new_mode = _decode_mode(msg.custom_mode)
            _check_failure_response(new_mode)
            telemetry["mode"] = new_mode
        elif t == "EXTENDED_SYS_STATE":
            telemetry["vtol_state"] = VTOL_STATES.get(msg.vtol_state)
            # MAV_LANDED_STATE: 1 on ground, 2 in air, 3 taking off, 4 landing
            telemetry["in_air"] = (msg.landed_state in (2, 3, 4)
                                   if msg.landed_state else None)
        elif t == "GLOBAL_POSITION_INT":
            telemetry["altitude_m"] = round(msg.relative_alt / 1000.0, 1)
            telemetry["altitude_amsl_m"] = round(msg.alt / 1000.0, 1)
            lat, lon = msg.lat / 1e7, msg.lon / 1e7
            telemetry["latitude"], telemetry["longitude"] = lat, lon
            if lat or lon:
                if home_latlon["lat"] is None:
                    home_latlon["lat"], home_latlon["lon"] = lat, lon
                telemetry["range_from_home_m"] = _range_from_home(lat, lon)
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
        elif t == "STATUSTEXT":
            text = msg.text
            if isinstance(text, bytes):
                text = text.decode("utf-8", "replace")
            text = text.strip()
            status_log.append({"text": text, "t": time.monotonic()})
            del status_log[:-_STATUS_LOG_MAX]
            if text.lower().startswith(_ARM_BLOCKER_PREFIXES):
                _arm_blocker["text"] = text
                _arm_blocker["t"] = time.monotonic()
        elif t == "PARAM_VALUE":
            name = msg.param_id
            if isinstance(name, bytes):
                name = name.decode("ascii", "replace")
            _param_values[name.rstrip("\x00")] = msg.param_value
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

