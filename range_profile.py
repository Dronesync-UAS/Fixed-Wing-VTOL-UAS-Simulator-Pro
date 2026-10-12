"""
Two operating envelopes: the CAA one a student flies inside, and an
extended one for instructor-only cross-country work.

Added 12 Oct 2026 on request: "two options, CAA compliant 500 m max and a
training option only for instructors of 100 km".

WHY A PROFILE RATHER THAN EDITING THE NUMBER. The 500 m figure is in the
flight log, on the altitude tape, in the breach warnings and in the event
log. Letting an instructor retype it would leave no record of which
envelope a flight was actually flown against, which is the one thing a
training record has to be able to answer. A named profile is recorded by
name in the event log and in every flight log written while it is active.

WHAT EACH ONE CHANGES. Only the lateral range. The 120 m ceiling and the
30 m/s speed limit are the same in both, deliberately: the request was
about distance, and quietly raising the height limit alongside it would
mean a student could be flown outside the height rule without anyone
having chosen that. If the extended profile should also lift the ceiling,
that is a one-line change here and it should be a decision somebody takes
on purpose.

WHAT 100 KM ACTUALLY GETS YOU, said plainly:

  * PX4 and the flight dynamics do not care. The aircraft will fly it.
  * The plan view will follow it - the backdrop will not, unless the
    imagery for that world was fetched at a matching extent. See
    tools/fetch_satellite.py --extent-km.
  * The ground you can SEE is a property of the world file, not of this
    setting. tools/far_ground_apply.py extends it; without that, the
    worlds run out between 2 km and 8 km from home depending on the
    world, and past that edge there is nothing under the aircraft.
  * Scenery is only ever near home. A long leg is a long leg over an
    empty plane.

NOT TESTED AGAINST A RUNNING SIMULATOR. Nothing here has been watched in
Gazebo or against PX4; the checks in tools/test_range_profile.py are
offline only.
"""

import json
import os

STATE_FILE = os.path.join(os.path.expanduser("~/uas_sim_logs"),
                          "range_profile.json")

# Shared by both profiles. Kept here rather than duplicated so that
# changing the ceiling changes it for both, which is what anybody editing
# it will expect.
CEILING_M = 120.0
GROUNDSPEED_MS = 30.0

PROFILES = {
    "caa": {
        "label": "CAA - 500 m",
        "range_m": 500.0,
        "ceiling_m": CEILING_M,
        "groundspeed_ms": GROUNDSPEED_MS,
        "note": "The envelope a student flies inside. 500 m lateral, "
                "120 m above launch.",
        "student_safe": True,
    },
    "extended": {
        "label": "Extended training - 100 km",
        "range_m": 100000.0,
        "ceiling_m": CEILING_M,
        "groundspeed_ms": GROUNDSPEED_MS,
        "note": "Instructor use only - 100 km lateral, which is outside "
                "the CAA limit a student is taught to. The ceiling stays "
                "at 120 m. Every flight flown on this profile is marked "
                "in the flight log.",
        "student_safe": False,
    },
}

DEFAULT = "caa"

# Deliberately module state rather than a parameter threaded through
# forty call sites: the limits are read from a dozen places that have no
# business knowing a profile exists.
_active = {"key": DEFAULT}


def _read_saved():
    """The profile chosen last time, or the default. A corrupt or missing
    file is not an error - it means a station that has never been set,
    and the safe answer for that is the CAA envelope."""
    try:
        with open(STATE_FILE) as handle:
            key = json.load(handle).get("profile")
    except (OSError, ValueError, AttributeError):
        return DEFAULT
    return key if key in PROFILES else DEFAULT


def _write_saved(key):
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as handle:
            json.dump({"profile": key}, handle)
    except OSError:
        pass        # a station that cannot remember still has to fly


def active_key():
    return _active["key"]


def active():
    return PROFILES[_active["key"]]


def limits():
    """Just the three numbers, in the shape the station's LIMITS dict
    wants them."""
    p = active()
    return {"range_m": p["range_m"], "ceiling_m": p["ceiling_m"],
            "groundspeed_ms": p["groundspeed_ms"]}


def choose(key):
    """Switch profile. Returns (ok, message). Logged either way: an
    envelope change that is not in the record is an envelope change that
    cannot be explained afterwards."""
    key = str(key).lower().strip()
    if key not in PROFILES:
        return False, ("Not changed - '%s' is not one of %s."
                       % (key, ", ".join(PROFILES)))
    was = _active["key"]
    _active["key"] = key
    _write_saved(key)
    profile = PROFILES[key]
    # Imported here rather than at the top: simulator_link opens the
    # MAVLink connection when it loads, and a module that only holds two
    # numbers has no business doing that at import time.
    try:
        from simulator_link import log_instructor_action
        log_instructor_action(
            "range_profile",
            "from=%s to=%s range_m=%.0f" % (was, key, profile["range_m"]))
    except Exception:       # noqa: BLE001 - logging must never stop a change
        pass
    if key == was:
        return True, "Already on %s. %s" % (profile["label"], profile["note"])
    return True, "Operating envelope: %s. %s" % (profile["label"],
                                                 profile["note"])


def restore():
    """Load the saved choice at start-up, without logging it as an
    instructor action - nobody pressed anything."""
    _active["key"] = _read_saved()
    return active()


def restore_limits():
    """restore(), then the three numbers. What the station calls at
    import time."""
    restore()
    return limits()


def describe():
    """For the flight log and for anything that has to say, later, which
    envelope a flight was flown against."""
    p = active()
    return {"profile": _active["key"], "label": p["label"],
            "student_safe": p["student_safe"], "range_m": p["range_m"],
            "ceiling_m": p["ceiling_m"]}
