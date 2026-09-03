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
from datetime import datetime, timezone

LOG_DIR = os.path.expanduser("~/uas_sim_logs")
LOG_FILE = os.path.join(LOG_DIR, "instructor_events.csv")

# One ID per run of the app, so rows from the same session can be grouped
# later even before proper student/session identification is designed.
SESSION_ID = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


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
    _ensure_log_file()
    full_details = f"{details} session_id={SESSION_ID}".strip() if details else f"session_id={SESSION_ID}"
    with open(LOG_FILE, "a", newline="") as f:
        csv.writer(f).writerow([
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
            event_type,
            full_details,
        ])


def read_events():
    """Return all logged events as a list of dicts, most recent last."""
    _ensure_log_file()
    with open(LOG_FILE, newline="") as f:
        return list(csv.DictReader(f))
