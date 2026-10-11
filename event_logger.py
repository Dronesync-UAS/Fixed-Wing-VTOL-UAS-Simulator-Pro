"""
Instructor Station - Event logging

WHAT THIS DOES
---------------
Every instructor action (freeze, reposition, failure injected/cleared) and
every observed student response to an injected failure gets written to a
plain CSV file with a timestamp. This is a starting point for the
"performance data for assessment records" requirement - NOT a final
logging design. Exactly what needs to be captured, in what format, and for
how long, for CAA/RAE assessment purposes is still an open question for
your Head of Training to confirm; this makes sure the raw events aren't
lost while that's decided, using the same file and 3-column format already
used by the earlier prototype (10 Aug 2026 test rows), so nothing already
written is disturbed.

The file is human-readable (opens fine in Excel) - one row per event:
    timestamp_utc, event_type, details

`details` is a space-separated key=value list, matching the style already
used in this file (e.g. "component=gps type=off"). Every row also gets a
session_id appended automatically - a timestamp generated once when the
app starts, so rows can be grouped by "one continuous run of the app".
This is NOT a student or instructor identifier - the app has no concept
of who is at the controls, and building that is a separate, deliberately
un-guessed decision (see the compliance notes for this project).
"""
import csv
import os
import sys
import threading
from datetime import datetime, timezone

LOG_DIR = os.path.expanduser("~/uas_sim_logs")
LOG_FILE = os.path.join(LOG_DIR, "instructor_events.csv")

# One ID per run of the app, so rows from the same session can be grouped
# later even before proper student/session identification is designed.
SESSION_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# The station is multi-threaded - the HTTP server handles each request on its
# own thread, and the telemetry loop logs student responses from another. Two
# unsynchronised appends can interleave inside one row, and this file is the
# CAP722B assessment record, so a corrupted row is not a cosmetic problem.
_write_lock = threading.Lock()


def _ensure_log_file():
    os.makedirs(LOG_DIR, exist_ok=True)
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, "w", newline="") as f:
            csv.writer(f).writerow(["timestamp_utc", "event_type", "details"])


def log_event(event_type, details=""):
    """
    event_type: short label, e.g. "freeze", "resume", "reposition",
                "failure_injected", "failure_cleared", "student_response",
                "instructor_intervened", "no_mode_change_response"
    details: free-text specifics, e.g. "component=gps type=off instance=0"
             - session_id is appended automatically, no need to include it.
    """
    full_details = f"{details} session_id={SESSION_ID}".strip() if details else f"session_id={SESSION_ID}"
    row = [datetime.now(timezone.utc).isoformat(timespec="seconds"),
           event_type, full_details]
    try:
        with _write_lock:
            _ensure_log_file()
            with open(LOG_FILE, "a", newline="") as f:
                csv.writer(f).writerow(row)
    except OSError as exc:
        # A full or read-only disk must not propagate: this is called from
        # instructor controls and from the telemetry thread, where an
        # exception would take the whole telemetry loop down and leave the
        # console frozen with no explanation. Losing a log row is bad; losing
        # telemetry mid-exercise is worse. Say so on the console instead.
        print(f"[event_logger] could not write {event_type}: {exc}", file=sys.stderr)


def read_events():
    """Return all logged events as a list of dicts, most recent last.

    An unreadable log returns nothing rather than raising - the caller is a
    display, and the station should not fall over because the record is
    temporarily unavailable.
    """
    try:
        with _write_lock:
            _ensure_log_file()
            with open(LOG_FILE, newline="") as f:
                return list(csv.DictReader(f))
    except OSError as exc:
        print(f"[event_logger] could not read the log: {exc}", file=sys.stderr)
        return []
