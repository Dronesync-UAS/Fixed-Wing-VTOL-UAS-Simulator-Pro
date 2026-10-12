"""
A record of every flight, and how it was flown.

Added 12 Oct 2026. event_logger.py already writes what the INSTRUCTOR
does; this writes what the AIRCRAFT did, which is the other half of a
debrief and the half CAP 722B's record-keeping expects a remote pilot to
keep (AMC1 Article 8(2) requires accurate, auditable flight logs; the
clause numbering is quoted from the CAA's own guidance page and has not
been checked against the printed fifth edition here).

WHAT COUNTS AS A FLIGHT
-----------------------
From the moment PX4 reports ARMED to the moment it reports DISARMED,
with a short grace period so a bounce on landing, or a disarm-and-rearm
on the pad inside a few seconds, does not split one circuit into three
flights. A flight that never leaves the ground is still recorded - an
arm, a run-up and a disarm is a real event in a training record, and a
log that quietly drops it is a log that cannot be audited.

WHAT GETS WRITTEN
-----------------
    ~/uas_sim_logs/flights/
        flight_20261012_143201/
            track.csv        one row every half second, while armed
            summary.json     the numbers below, worked out at shutdown
        flights.jsonl        one line per finished flight, for the list

track.csv is deliberately flat and wide: it opens in Excel, which is what
an instructor actually has.

THE PERFORMANCE NUMBERS, AND WHY THESE ONES
--------------------------------------------
Each one answers a question an instructor asks at a debrief:

  duration, airborne_s        how long, and how much of it off the ground
  max_alt_agl_m               did they go above the height limit
  max_range_m                 did they go beyond the range limit
  max_groundspeed_ms          and how fast
  limit_breaches              how long they spent outside each limit, which
                              is the number that matters - a one-sample
                              spike and a two-minute excursion are not the
                              same event
  transitions                 how many times they changed between hover and
                              wing-borne flight, and whether any failed
  time_hover_s/time_fw_s      the split, which is the shape of the sortie
  max_climb_ms/max_sink_ms    how aggressively they flew it
  landing_sink_ms             how hard they put it down - the single most
                              useful number on a VTOL debrief
  battery_used_pct            whether the sortie was planned to fit
  modes                       seconds spent in each PX4 flight mode
  failures_injected           what the instructor did to them
  checklist                   what the pre-flight looked like at take-off

HOW IT IS SAMPLED. Half a second. Every number above is computed from the
samples rather than from an event, so a figure can always be traced back
to a row in track.csv - which is what makes it auditable rather than
asserted.

WHAT IS NOT IN IT. Any identification of who was flying. The station has
no concept of a student, and event_logger.py says plainly why inventing
one here would be the wrong place to decide it. The summary carries the
session id so a flight can be tied to whatever record the school keeps
alongside.

TESTED by tools/test_flight_log.py, which drives the recorder with a
made-up flight and checks every number above against one worked out by
hand. Never run against a real PX4 session.
"""
import csv
import json
import os
import threading
import time
from datetime import datetime, timezone

LOG_DIR = os.path.expanduser("~/uas_sim_logs/flights")
INDEX_FILE = os.path.join(LOG_DIR, "flights.jsonl")

SAMPLE_S = 0.5

# A disarm shorter than this is treated as part of the same flight, so a
# bounce or a quick re-arm on the pad does not become three records.
REARM_GRACE_S = 20.0

# Above this the aircraft counts as airborne for the "airborne" figure.
# PX4's own in_air flag is used when it has reported one; this is the
# fallback for the stretch before EXTENDED_SYS_STATE arrives.
AIRBORNE_AGL_M = 1.5

COLUMNS = [
    "t_s", "utc", "armed", "mode", "vtol_state", "in_air",
    "lat", "lon", "alt_agl_m", "alt_amsl_m",
    "groundspeed_ms", "airspeed_ms", "climb_ms",
    "roll_deg", "pitch_deg", "yaw_deg", "heading_deg",
    "range_from_home_m", "battery_pct", "satellites", "throttle_pct",
]


def _stamp(when=None):
    return (when or datetime.now()).strftime("%Y%m%d_%H%M%S")


def _free_folder():
    """A folder name no flight is already using.

    The name is the time to the second, which is unique in practice - the
    grace period alone makes two flights a second apart impossible. The
    suffix is for the case that is not practice: the station restarted
    twice inside the same second, which would otherwise have the second
    flight writing over the first one's track.
    """
    base = os.path.join(LOG_DIR, "flight_%s" % _stamp())
    if not os.path.exists(base):
        return base
    for extra in range(2, 100):
        candidate = "%s_%d" % (base, extra)
        if not os.path.exists(candidate):
            return candidate
    return base


class Flight:
    """One armed-to-disarmed record, being written as it happens."""

    def __init__(self, limits, checklist=None):
        self.started = time.time()
        self.started_mono = time.monotonic()
        self.folder = _free_folder()
        self.rows = 0
        self.limits = dict(limits or {})
        self.checklist = checklist
        self.ended_mono = None
        self._handle = None
        self._writer = None
        self._last = None               # the previous sample, for rates
        self._open()

        self.peak = {"alt_agl_m": 0.0, "range_from_home_m": 0.0,
                     "groundspeed_ms": 0.0, "airspeed_ms": 0.0,
                     "climb_ms": 0.0, "sink_ms": 0.0}
        self.seconds = {"airborne": 0.0, "hover": 0.0, "fixed_wing": 0.0,
                        "transitioning": 0.0}
        self.modes = {}
        self.breaches = {}
        self.battery = {"first": None, "last": None}
        self.transitions = []
        self.failures = []
        self.landing_sink_ms = None
        self._recent_sink = []

    # -- writing ---------------------------------------------------------
    def _open(self):
        try:
            os.makedirs(self.folder, exist_ok=True)
            self._handle = open(os.path.join(self.folder, "track.csv"),
                                "w", newline="")
            self._writer = csv.writer(self._handle)
            self._writer.writerow(COLUMNS)
        except OSError:
            # A log that cannot be written must not stop the flight. The
            # summary still gets computed in memory and the console says
            # the track is missing.
            self._handle = self._writer = None

    def sample(self, telemetry, elapsed_s):
        """One row. elapsed_s is seconds since the previous sample."""
        alt = _number(telemetry.get("altitude_m"))
        amsl = _number(telemetry.get("altitude_amsl_m"))
        climb = 0.0
        if self._last is not None and elapsed_s > 0:
            previous = _number(self._last.get("altitude_m"))
            if previous is not None and alt is not None:
                climb = (alt - previous) / elapsed_s
        row = {
            "t_s": round(time.monotonic() - self.started_mono, 2),
            "utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "armed": int(bool(telemetry.get("armed"))),
            "mode": telemetry.get("mode"),
            "vtol_state": telemetry.get("vtol_state"),
            "in_air": telemetry.get("in_air"),
            "lat": telemetry.get("latitude"),
            "lon": telemetry.get("longitude"),
            "alt_agl_m": alt, "alt_amsl_m": amsl,
            "groundspeed_ms": _number(telemetry.get("groundspeed_ms")),
            "airspeed_ms": _number(telemetry.get("airspeed_ms")),
            "climb_ms": round(climb, 2),
            "roll_deg": telemetry.get("roll_deg"),
            "pitch_deg": telemetry.get("pitch_deg"),
            "yaw_deg": telemetry.get("yaw_deg"),
            "heading_deg": telemetry.get("heading_deg"),
            "range_from_home_m": _number(telemetry.get("range_from_home_m")),
            "battery_pct": telemetry.get("battery_pct"),
            "satellites": telemetry.get("satellites"),
            "throttle_pct": telemetry.get("throttle_pct"),
        }
        if self._writer is not None:
            try:
                self._writer.writerow([row[c] for c in COLUMNS])
                self._handle.flush()
            except (OSError, ValueError):
                self._writer = None
        self.rows += 1
        self._accumulate(row, telemetry, elapsed_s)
        self._last = dict(telemetry)
        return row

    # -- the running totals ----------------------------------------------
    def _accumulate(self, row, telemetry, elapsed_s):
        for key in ("alt_agl_m", "range_from_home_m", "groundspeed_ms",
                    "airspeed_ms"):
            value = row.get(key)
            if value is not None and value > self.peak[key]:
                self.peak[key] = round(value, 1)
        climb = row["climb_ms"]
        if climb > self.peak["climb_ms"]:
            self.peak["climb_ms"] = round(climb, 1)
        if -climb > self.peak["sink_ms"]:
            self.peak["sink_ms"] = round(-climb, 1)

        airborne = telemetry.get("in_air")
        if airborne is None:
            airborne = (row["alt_agl_m"] or 0) > AIRBORNE_AGL_M
        if airborne:
            self.seconds["airborne"] += elapsed_s
            # Keep the last few seconds of sink rate: the landing figure is
            # the worst of them at the moment the aircraft touches down,
            # not the instant reading after it has already stopped.
            self._recent_sink.append(-climb)
            del self._recent_sink[:-8]
        elif self._recent_sink:
            self.landing_sink_ms = round(max(self._recent_sink), 1)
            self._recent_sink = []

        vtol = telemetry.get("vtol_state")
        if vtol == "Hover":
            self.seconds["hover"] += elapsed_s
        elif vtol == "Fixed wing":
            self.seconds["fixed_wing"] += elapsed_s
        elif vtol:
            self.seconds["transitioning"] += elapsed_s
        previous_vtol = (self._last or {}).get("vtol_state")
        if vtol and previous_vtol and vtol != previous_vtol and (
                "Transition" in vtol):
            self.transitions.append({"t_s": row["t_s"], "to": vtol})

        mode = telemetry.get("mode")
        if mode:
            self.modes[mode] = round(self.modes.get(mode, 0.0) + elapsed_s, 1)

        battery = telemetry.get("battery_pct")
        if battery is not None:
            if self.battery["first"] is None:
                self.battery["first"] = battery
            self.battery["last"] = battery

        for key, reading, cap in (
                ("ceiling", row["alt_agl_m"], self.limits.get("ceiling_m")),
                ("range", row["range_from_home_m"], self.limits.get("range_m")),
                ("groundspeed", row["groundspeed_ms"],
                 self.limits.get("groundspeed_ms"))):
            if cap and reading is not None and reading > cap:
                entry = self.breaches.setdefault(
                    key, {"seconds": 0.0, "worst": 0.0, "limit": cap})
                entry["seconds"] = round(entry["seconds"] + elapsed_s, 1)
                entry["worst"] = max(entry["worst"], round(reading, 1))

    def note_failure(self, what):
        self.failures.append({"t_s": round(time.monotonic() - self.started_mono, 1),
                              "what": what})

    # -- finishing --------------------------------------------------------
    def summary(self):
        duration = round((self.ended_mono or time.monotonic())
                         - self.started_mono, 1)
        used = None
        if self.battery["first"] is not None and self.battery["last"] is not None:
            used = self.battery["first"] - self.battery["last"]
        return {
            "folder": self.folder,
            "started_utc": datetime.fromtimestamp(
                self.started, timezone.utc).isoformat(timespec="seconds"),
            "duration_s": duration,
            "airborne_s": round(self.seconds["airborne"], 1),
            "samples": self.rows,
            "left_the_ground": self.seconds["airborne"] > 0,
            "max_alt_agl_m": self.peak["alt_agl_m"],
            "max_range_m": self.peak["range_from_home_m"],
            "max_groundspeed_ms": self.peak["groundspeed_ms"],
            "max_airspeed_ms": self.peak["airspeed_ms"],
            "max_climb_ms": self.peak["climb_ms"],
            "max_sink_ms": self.peak["sink_ms"],
            "landing_sink_ms": self.landing_sink_ms,
            "time_hover_s": round(self.seconds["hover"], 1),
            "time_fixed_wing_s": round(self.seconds["fixed_wing"], 1),
            "time_transitioning_s": round(self.seconds["transitioning"], 1),
            "transitions": self.transitions,
            "modes_s": self.modes,
            "battery_used_pct": used,
            "limit_breaches": self.breaches,
            "failures_injected": self.failures,
            "checklist": self.checklist,
            "limits": self.limits,
        }

    def close(self, session_id=None, world=None):
        self.ended_mono = time.monotonic()
        if self._handle is not None:
            try:
                self._handle.close()
            except OSError:
                pass
            self._handle = self._writer = None
        record = self.summary()
        record["session_id"] = session_id
        record["world"] = world
        record["ended_utc"] = datetime.now(timezone.utc).isoformat(
            timespec="seconds")
        try:
            with open(os.path.join(self.folder, "summary.json"), "w") as handle:
                json.dump(record, handle, indent=2, sort_keys=True)
            os.makedirs(LOG_DIR, exist_ok=True)
            with open(INDEX_FILE, "a") as handle:
                handle.write(json.dumps(_index_entry(record)) + "\n")
        except OSError:
            pass
        return record


def _index_entry(record):
    """The short form that the console's flight list shows."""
    return {k: record.get(k) for k in (
        "folder", "started_utc", "ended_utc", "duration_s", "airborne_s",
        "max_alt_agl_m", "max_range_m", "max_groundspeed_ms",
        "landing_sink_ms", "battery_used_pct", "world", "session_id")}


def _number(value):
    try:
        return round(float(value), 2)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------
# THE RECORDER - one per station, started at boot.
# ---------------------------------------------------------------------

class Recorder:
    def __init__(self, telemetry, limits_source, checklist_source=None,
                 session_id=None, world_source=None):
        self._telemetry = telemetry
        self._limits = limits_source
        self._checklist = checklist_source
        self._session_id = session_id
        self._world = world_source
        self.current = None
        self.last = None
        self._disarmed_since = None
        self._last_sample = None
        self._lock = threading.Lock()
        self._started = False

    def tick(self, now=None):
        """One pass. Separated from the thread so a test can drive it."""
        now = now if now is not None else time.monotonic()
        armed = bool(self._telemetry.get("armed"))
        with self._lock:
            if armed:
                self._disarmed_since = None
                if self.current is None:
                    self.current = Flight(
                        self._limits() if callable(self._limits) else self._limits,
                        self._checklist() if callable(self._checklist) else None)
                    self._last_sample = now
            elif self.current is not None:
                if self._disarmed_since is None:
                    self._disarmed_since = now
                elif now - self._disarmed_since >= REARM_GRACE_S:
                    self.last = self.current.close(
                        self._session_id,
                        self._world() if callable(self._world) else self._world)
                    self.current = None
                    self._disarmed_since = None
                    return self.last
            if self.current is not None:
                elapsed = now - (self._last_sample or now)
                self._last_sample = now
                self.current.sample(self._telemetry, elapsed)
        return None

    def note_failure(self, what):
        if self.current is not None:
            self.current.note_failure(what)

    def status(self):
        """What the console shows while a flight is in progress."""
        with self._lock:
            flight = self.current
            if flight is None:
                return {"recording": False, "last": _index_entry(self.last)
                        if self.last else None}
            live = flight.summary()
            live["recording"] = True
            return live

    def start(self):
        if self._started:
            return
        self._started = True

        def run():
            while True:
                time.sleep(SAMPLE_S)
                try:
                    self.tick()
                except Exception:                          # noqa: BLE001
                    # The flight log must never be the thing that takes the
                    # station down mid-exercise.
                    pass

        threading.Thread(target=run, daemon=True).start()


def recent(limit=25):
    """The finished flights, newest first, for the console's list."""
    try:
        with open(INDEX_FILE) as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-limit * 2:]):
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
        if len(out) >= limit:
            break
    return out
