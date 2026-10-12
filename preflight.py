"""
The pre-flight checklist.

Added 12 Oct 2026, as Phase 2 of docs/DJI-style-development-plan.md. DJI
Pilot 2 opens with one and so does every real assessment form, and this
project had neither - an exercise simply started whenever somebody pressed
ARM.

It does two jobs at once, which is why it was built before the flashier
things on that plan:

  * it stops an exercise beginning from a state nobody checked, and
  * it writes down that the check happened, which is the part an
    assessment record is missing (see docs/CAP722B-readiness.md).

TWO KINDS OF ITEM

AUTOMATIC items are read from the aircraft. Nobody ticks them and nobody
can tick them - they go green when the aircraft says so. They are the ones
a person is worst at checking honestly under time pressure.

MANUAL items are the ones no telemetry can answer: is the area clear, has
the student been briefed, is the weather what you think it is. The
instructor ticks them, and the record says who ticked what and when - or
rather, says that someone did, because the station still has no concept of
who is at the controls. That gap is named in the readiness note.

WHAT IT DOES NOT DO

It does not block anything. An instructor who wants to fly with a red item
can, and the log will show the exercise started with it red. Making the
console refuse would be a safety feature on a real aircraft; on a
simulator it would only teach students to work around checklists.
"""
import threading
import time

import event_logger
from simulator_link import telemetry

# Each automatic item: a key, what it says on screen, and a function of the
# telemetry returning (ok, what the aircraft says). The threshold figures
# are this project's own - no standard is claimed for them.
MIN_SATELLITES = 8
MIN_BATTERY_PCT = 40
MAX_LINK_AGE_S = 2.0


def _arm_ready(t):
    state = t.get("arm_ready")
    if state is None:
        return None, t.get("arm_state") or "no heartbeat from PX4 yet"
    if state:
        return True, "PX4 will accept ARM"
    return False, t.get("arm_blocker") or "PX4 is refusing to arm"


def _satellites(t):
    n = t.get("satellites")
    if n is None:
        return None, "not reported yet"
    # 255 is UINT8_MAX: "unknown", which is what a GPS dropout injection
    # leaves behind. It is not a very good fix, it is no fix at all.
    if n == 255:
        return False, "255 - no fix (a GPS failure may still be injected)"
    return n >= MIN_SATELLITES, f"{n} satellites"


def _battery(t):
    pct = t.get("battery_pct")
    if pct is None:
        return None, "not reported yet"
    return pct >= MIN_BATTERY_PCT, f"{pct}%"


def _on_the_ground(t):
    if t.get("armed"):
        return False, "already armed"
    in_air = t.get("in_air")
    if in_air is None:
        return None, "not reported yet"
    return not in_air, "on the ground" if not in_air else "in the air"


def _home_known(t):
    if t.get("latitude") is None:
        return None, "no position yet"
    return True, "position fixed"


AUTOMATIC = [
    ("arm_ready", "PX4 accepts arming", _arm_ready),
    ("satellites", f"At least {MIN_SATELLITES} satellites", _satellites),
    ("battery", f"Battery above {MIN_BATTERY_PCT}%", _battery),
    ("on_ground", "Aircraft on the ground, disarmed", _on_the_ground),
    ("position", "Position and home point known", _home_known),
]

MANUAL = [
    ("area", "Training area clear of people and obstacles"),
    ("weather", "Weather and wind within the exercise's limits"),
    ("brief", "Student briefed on the exercise and the abort call"),
    ("failures", "Failure injections off unless the exercise needs them"),
    ("limits", "Height, range and speed limits agreed for this exercise"),
]

_ticks = {}
_lock = threading.Lock()


def state():
    """Everything the console needs to draw the checklist."""
    t = telemetry
    automatic = []
    for key, label, check in AUTOMATIC:
        ok, detail = check(t)
        automatic.append({"key": key, "label": label, "ok": ok,
                          "detail": detail, "kind": "auto"})
    with _lock:
        manual = [{"key": key, "label": label, "ok": bool(_ticks.get(key)),
                   "detail": "ticked" if _ticks.get(key) else "not ticked",
                   "kind": "manual"}
                  for key, label in MANUAL]
    items = automatic + manual
    return {
        "items": items,
        "ready": all(i["ok"] is True for i in items),
        "outstanding": [i["label"] for i in items if i["ok"] is not True],
    }


def tick(key, on):
    """Tick or untick one manual item."""
    if key not in {k for k, _ in MANUAL}:
        return False
    with _lock:
        _ticks[key] = bool(on)
    event_logger.log_event("preflight_item",
                           f"item={key} ticked={bool(on)}")
    return True


def reset():
    """Clear the manual ticks - a new session starts an unticked list."""
    with _lock:
        _ticks.clear()
    event_logger.log_event("preflight_reset")


def complete():
    """Write the whole checklist to the record, as it stands right now.

    Called when the instructor says the exercise is starting. Everything
    is written, green or not, because "started with the battery item red"
    is exactly the sort of thing a record exists to preserve.
    """
    snapshot = state()
    parts = [f"{i['key']}={'ok' if i['ok'] is True else 'NOT_OK'}"
             for i in snapshot["items"]]
    event_logger.log_event(
        "preflight_complete",
        f"ready={snapshot['ready']} " + " ".join(parts))
    return snapshot
