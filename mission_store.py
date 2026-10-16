"""
Save and reload planned missions.

Added 12 Oct 2026, straight after mission.py: a plan that disappears
when the station restarts is a plan nobody will build twice. An
instructor planning a lesson wants the survey they set up last week,
not the one they can remember the numbers for.

WHERE. ~/uas_sim_logs/missions/, beside the flight logs and the payload
photographs, and OUTSIDE this repository - a saved mission is the
instructor's own work, not project source, and it must survive a git
checkout. One file per mission, named after it.

WHAT IS SAVED. The recipe AND the result. The parameters - pattern,
height, size, bearing, where it was centred - so the mission can be
rebuilt if the planner improves; and the built items, so it can be
uploaded unchanged even if the planner's arithmetic has moved on since.
Saving only the parameters would mean a saved lesson quietly changing
under an instructor; saving only the items would mean never being able
to adjust one.

ALSO WRITTEN: a QGroundControl .plan file beside it, so a plan made here
can be opened in the tool most remote pilots already use.

THE .plan FORMAT IS NOT VERIFIED. It is written to the documented
structure - fileType "Plan", a mission object holding SimpleItem
entries, plannedHomePosition - but nobody has opened one of these files
in QGroundControl. Said plainly because "exports to QGC" is the kind of
claim that gets believed. Our own .json round-trips and is tested.
"""

import json
import os
import re
import time

DIR = os.path.join(os.path.expanduser("~/uas_sim_logs"), "missions")

FORMAT_VERSION = 1

# QGroundControl's own numbers for a standard VTOL. MAV_TYPE 20 is
# MAV_TYPE_VTOL_RESERVED2 / quadplane in QGC's vehicleType field, and 12
# is PX4 in its firmwareType. Both are part of the unverified half.
QGC_VEHICLE_VTOL = 20
QGC_FIRMWARE_PX4 = 12


def safe_name(name):
    """A file name from whatever was typed. Spaces become underscores,
    anything that is not a letter, digit, dash or underscore is dropped,
    and an empty result becomes a timestamp - because refusing to save
    because of a stray slash is not helpful mid-lesson."""
    cleaned = re.sub(r"[^A-Za-z0-9 _-]", "", str(name)).strip()
    cleaned = re.sub(r"\s+", "_", cleaned)[:60]
    return cleaned or time.strftime("mission_%Y%m%d_%H%M%S")


def _path(name, suffix=".json"):
    return os.path.join(DIR, safe_name(name) + suffix)


def save(name, pattern, parameters, items, summary, world=None):
    """Write one mission. Returns (ok, message, path)."""
    if not items:
        return False, "Nothing to save - the mission is empty.", None
    try:
        os.makedirs(DIR, exist_ok=True)
    except OSError as exc:
        return False, "Could not make %s - %s." % (DIR, exc.strerror), None

    record = {
        "format": FORMAT_VERSION,
        "name": safe_name(name),
        "pattern": pattern,
        "saved": time.strftime("%Y-%m-%d %H:%M:%S"),
        "world": world,
        "parameters": parameters,
        "summary": summary,
        "items": items,
    }
    path = _path(name)
    try:
        with open(path, "w") as handle:
            json.dump(record, handle, indent=2)
    except OSError as exc:
        return False, "Could not write %s - %s." % (path, exc.strerror), None

    # The QGC file is a convenience, not the save. If it fails, the
    # mission is still saved and the message says which half worked.
    qgc_note = ""
    try:
        write_qgc_plan(_path(name, ".plan"), record)
    except (OSError, ValueError, KeyError) as exc:
        qgc_note = ("  The QGroundControl copy could not be written (%s), "
                    "but the mission itself is saved." % exc)

    return True, ("Saved as %s - %d items.%s"
                  % (record["name"], len(items), qgc_note)), path


def load(name):
    """Read one mission back. Returns (record, message). record is None
    if it could not be read."""
    path = _path(name)
    if not os.path.isfile(path):
        return None, ("No saved mission called %s. %s"
                      % (safe_name(name), _what_there_is()))
    try:
        with open(path) as handle:
            record = json.load(handle)
    except (OSError, ValueError) as exc:
        return None, "Could not read %s - %s." % (path, exc)
    if not record.get("items"):
        return None, "%s has no mission items in it." % safe_name(name)
    return record, ("Loaded %s: %s, %d items, planned %s."
                    % (record.get("name"), record.get("pattern", "?"),
                       len(record["items"]), record.get("saved", "?")))


def names():
    """Every saved mission, newest first."""
    try:
        files = [f for f in os.listdir(DIR) if f.endswith(".json")]
    except OSError:
        return []
    files.sort(key=lambda f: os.path.getmtime(os.path.join(DIR, f)),
               reverse=True)
    return [f[:-5] for f in files]


def _what_there_is():
    have = names()
    if not have:
        return "Nothing is saved yet."
    return "Saved: %s." % ", ".join(have[:8])


def delete(name):
    path = _path(name)
    if not os.path.isfile(path):
        return False, "No saved mission called %s." % safe_name(name)
    try:
        os.remove(path)
        plan = _path(name, ".plan")
        if os.path.isfile(plan):
            os.remove(plan)
    except OSError as exc:
        return False, "Could not delete it - %s." % exc.strerror
    return True, "Deleted %s." % safe_name(name)


def write_qgc_plan(path, record):
    """A QGroundControl .plan file. See the note at the top of this
    module: the structure is the documented one, and nobody has opened
    one of these in QGroundControl."""
    items = record["items"]
    home = None
    for it in items:
        if it.get("x") or it.get("y"):
            home = [it["x"], it["y"], it.get("z", 0.0)]
            break
    if home is None:
        raise ValueError("no positioned item to take a home position from")

    simple = []
    for n, it in enumerate(items, start=1):
        simple.append({
            "AMSLAltAboveTerrain": None,
            "Altitude": it.get("z", 0.0),
            "AltitudeMode": 1,
            "autoContinue": bool(it.get("autocontinue", 1)),
            "command": it["command"],
            "doJumpId": n,
            "frame": it["frame"],
            "params": [it["param1"], it["param2"], it["param3"],
                       it["param4"], it["x"], it["y"], it["z"]],
            "type": "SimpleItem",
        })

    plan = {
        "fileType": "Plan",
        "geoFence": {"circles": [], "polygons": [], "version": 2},
        "groundStation": "UAV Academy GCS Pro",
        "mission": {
            "cruiseSpeed": 16,
            "firmwareType": QGC_FIRMWARE_PX4,
            "globalPlanAltitudeMode": 1,
            "hoverSpeed": 5,
            "items": simple,
            "plannedHomePosition": home,
            "vehicleType": QGC_VEHICLE_VTOL,
            "version": 2,
        },
        "rallyPoints": {"points": [], "version": 2},
        "version": 1,
    }
    with open(path, "w") as handle:
        json.dump(plan, handle, indent=4)
    return path
