"""
Send a planned mission to PX4, and start it.

Added 12 Oct 2026 alongside mission.py, which builds the items. This
file is the half that needs a live link, kept separate so the planning
arithmetic can be checked on a machine with no simulator running.

THE UPLOAD IS A CONVERSATION, not a send. MAVLink's mission protocol:

    we  -> MISSION_COUNT (how many, including home as item 0)
    PX4 -> MISSION_REQUEST_INT (send me item n)       ... repeated
    we  -> MISSION_ITEM_INT (item n)                  ... repeated
    PX4 -> MISSION_ACK (accepted, or why not)

PX4 asks for the items it wants, in whatever order it likes, and may
ask for one twice. So this loop answers requests until the ack arrives
rather than sending the list and hoping.

ITEM 0 IS HOME. PX4 treats the first item as the home position and does
not fly to it. mission.py does not know about that, so the home item is
added here - one place, where the protocol is already being handled.

LATITUDE AND LONGITUDE ARE INTEGERS in MISSION_ITEM_INT: degrees times
1e7. Sending floats there is the classic way to end up with a mission
somewhere off the coast of Africa.

NOT FLOWN. The protocol is implemented from the MAVLink mission
specification; nothing here has been uploaded to a running PX4.
"""

import time

from pymavlink import mavutil

import mission
from simulator_link import master, log_instructor_action, telemetry

UPLOAD_TIMEOUT_S = 20.0
MISSION_TYPE_MISSION = 0


def _to_item_int(seq, it, target_system, target_component):
    return master.mav.mission_item_int_encode(
        target_system, target_component, seq,
        it["frame"], it["command"],
        0,                      # current: 0 for all but the first, set below
        it["autocontinue"],
        it["param1"], it["param2"], it["param3"], it["param4"],
        int(round(it["x"] * 1e7)), int(round(it["y"] * 1e7)),
        float(it["z"]),
        MISSION_TYPE_MISSION)


def upload(items, home_lat=None, home_lon=None):
    """Upload a list of mission.py items. Returns (ok, message)."""
    if not items:
        return False, "Nothing to upload - the mission is empty."

    lat = telemetry.get("latitude") if home_lat is None else home_lat
    lon = telemetry.get("longitude") if home_lon is None else home_lon
    if lat is None or lon is None:
        return False, ("Not uploaded - no position from the aircraft yet, so "
                       "there is nothing to call home.")

    # Item 0 is home and is never flown to.
    full = [mission.item(mission.NAV_WAYPOINT, lat=lat, lon=lon, alt=0.0)]
    full.extend(items)

    target_system = master.target_system or 1
    target_component = master.target_component or 1

    # Clear whatever is on board first. A partial old mission mixed with
    # a new one is the worst of both.
    master.mav.mission_clear_all_send(target_system, target_component,
                                      MISSION_TYPE_MISSION)
    time.sleep(0.2)

    master.mav.mission_count_send(target_system, target_component,
                                  len(full), MISSION_TYPE_MISSION)

    deadline = time.monotonic() + UPLOAD_TIMEOUT_S
    sent = set()
    while time.monotonic() < deadline:
        msg = master.recv_match(
            type=["MISSION_REQUEST", "MISSION_REQUEST_INT", "MISSION_ACK"],
            blocking=True, timeout=1.0)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == "MISSION_ACK":
            if msg.type == mavutil.mavlink.MAV_MISSION_ACCEPTED:
                log_instructor_action("mission_upload",
                                      "items=%d" % len(full))
                return True, ("Mission uploaded - %d items, %d waypoints."
                              % (len(full), len(full) - 1))
            return False, ("PX4 rejected the mission (code %s). Nothing is "
                           "loaded." % msg.type)
        seq = msg.seq
        if seq >= len(full):
            return False, ("PX4 asked for item %d of a %d item mission - "
                           "giving up rather than sending nonsense."
                           % (seq, len(full)))
        master.mav.send(_to_item_int(seq, full[seq],
                                     target_system, target_component))
        sent.add(seq)

    return False, ("Timed out after %.0f s - PX4 asked for %d of %d items. "
                   "Nothing is loaded."
                   % (UPLOAD_TIMEOUT_S, len(sent), len(full)))


def start():
    """Switch to AUTO.MISSION and run it from the beginning."""
    if not telemetry.get("armed"):
        return False, "Not started - the aircraft is disarmed."
    result, text = _send(mavutil.mavlink.MAV_CMD_MISSION_START, 0, 0)
    if result != mavutil.mavlink.MAV_RESULT_ACCEPTED:
        return False, "PX4 refused to start the mission (%s)." % text
    log_instructor_action("mission_start", "")
    return True, "Mission started."


def _send(command, *params):
    from simulator_link import send_command_and_wait
    return send_command_and_wait(command, *params)
