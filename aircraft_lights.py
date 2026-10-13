"""
The aircraft's own lights, and the way they flash.

Added 12 Oct 2026 for night operations.

WHAT FLASHES, AND WHAT DOES NOT. "Like real aircraft" means:

  * the NAVIGATION lights - red to port, green to starboard, white at the
    tail - are STEADY. They are position lights; their whole job is to let
    another pilot read, continuously, which way this aircraft is pointing.
    Flashing them would be wrong, and a student taught that will be marked
    wrong.
  * the ANTI-COLLISION STROBES are white and flash hard, in a double
    flash about once a second. That is the pattern a real high-intensity
    strobe fires.
  * the BEACON is red and flashes on its own slower rhythm. On a real
    aircraft it means the engines are running or about to be - which maps
    exactly onto "armed" here, and that is how it is driven.

HOW. Gazebo takes a light change on a topic as well as a service - gz-sim8
UserCommands.cc line 622 publishes the same handler on
/world/<world>/light_config - and gz.msgs.Light carries is_light_off
(light.proto field 19). A persistent publisher on that topic costs
nothing per message, which is what makes a flash affordable; the `gz
service` command line would be a new process several times a second.

THE PATTERN RUNS ON ONE THREAD for all the lights, so the strobes stay in
step with each other, which they are on a real airframe.

NOT YET SEEN WORKING. The topic, the message and the field are read off
the gz-sim8 and gz-msgs10 sources; nobody has watched these flash.
"""
import threading
import time

import sim_target

# The names tools/aircraft_lights_apply.py gives them.
#
# NO WING LIGHTS. There were red and green wingtip navigation lights until
# 13 Oct 2026, removed on instruction; the reference photographs of the
# DeltaQuad show none, and at 40 m range they were throwing large coloured
# pools onto the ground in daylight.
#
# THE TAIL LIGHT IS THE GPS INDICATOR, not a position light. Flashing
# GREEN means the aircraft is on and has GPS; flashing RED means GPS has
# been lost. That makes the gps_failure injection visible on the airframe
# itself, which is the point of it in a lesson - a student watching the
# aircraft sees the failure, not just a line on the console.
NAVIGATION = []
GPS_LIGHT = "nav_tail"
GPS_GREEN = (0.05, 0.9, 0.15)
GPS_RED = (0.95, 0.06, 0.06)
STROBES = ["strobe_top", "strobe_belly"]
BEACON = ["beacon_top"]
ALL = NAVIGATION + [GPS_LIGHT] + STROBES + BEACON

# One second, as a list of (moment, strobes on, beacon on). A real
# high-intensity strobe double-flashes; a beacon is one slower pulse.
# Times are seconds from the start of each cycle.
CYCLE_S = 1.0
STROBE_FLASHES = [(0.00, 0.06), (0.16, 0.06)]     # (start, how long)
BEACON_FLASH = (0.55, 0.12)
# Slower and longer than a strobe: this one is meant to be READ, not just
# noticed, and its colour is the message.
#
# AFTER THE BEACON IN THE CYCLE, and that is not cosmetic. _run walks the
# cycle in order with _sleep_until, so an event placed earlier in the code
# but later in time stops the ones after it from firing at all. Putting
# this flash first - the first version did - ate the opening 0.65 s and
# both strobes then fired together at the end. The strobes are at 0.00 and
# 0.16, the beacon at 0.55 to 0.67, so this sits clear of both.
GPS_FLASH = (0.70, 0.25)

_node = None
_lock = threading.Lock()
_thread = None
_state = {"on": False, "armed": False, "gps": True, "failed": None}


def _publisher():
    """The gz publisher for this world's light_config topic, or None.

    Rebuilt when the world changes, because the topic has the world's name
    in it - the same reason the camera feeds re-subscribe.
    """
    global _node
    topic = f"/world/{sim_target.WORLD}/light_config"
    with _lock:
        if _node is not None and _node["topic"] == topic:
            return _node
        try:
            from gz.transport13 import Node
            from gz.msgs10.light_pb2 import Light
        except ImportError as exc:
            _state["failed"] = f"gz python bindings not available ({exc})"
            return None
        node = Node()
        publisher = node.advertise(topic, Light)
        _node = {"node": node, "pub": publisher, "topic": topic, "Light": Light}
        return _node


def set_light(name, on, rgb=None):
    """Switch one light, optionally changing its colour. True if it went out.

    The colour fields are only set when a colour is asked for, and when
    they are, the attenuation and range are set with them. Gazebo applies
    the whole message, so leaving those at their protobuf defaults of zero
    would turn the light into one with no reach at all.
    """
    handle = _publisher()
    if handle is None:
        return False
    message = handle["Light"]()
    message.name = name
    # POINT is 0 in gz.msgs.Light.LightType, and these are all point
    # lights; the field has to be set or Gazebo reads it as a directional
    # light and the change is refused.
    message.type = 0
    message.is_light_off = not on
    if rgb is not None:
        red, green, blue = rgb
        message.diffuse.r, message.diffuse.g = red, green
        message.diffuse.b, message.diffuse.a = blue, 1.0
        message.specular.r, message.specular.g = red, green
        message.specular.b, message.specular.a = blue, 1.0
        # The figures tools/aircraft_lights_apply.py writes into the model.
        message.attenuation_constant = 0.2
        message.attenuation_linear = 0.08
        message.attenuation_quadratic = 0.01
        message.range = 40.0
        message.cast_shadows = False
    try:
        handle["pub"].publish(message)
        return True
    except Exception as exc:                                # noqa: BLE001
        _state["failed"] = str(exc)
        return False


def _run():
    """The flash pattern. One thread, so the strobes stay in step."""
    while True:
        if not _state["on"]:
            time.sleep(0.2)
            continue
        start = time.monotonic()
        # Navigation lights are steady: set once per cycle so that a world
        # change or a respawn does not leave them off.
        for name in NAVIGATION:
            set_light(name, True)

        for when, length in STROBE_FLASHES:
            _sleep_until(start + when)
            if not _state["on"]:
                break
            for name in STROBES:
                set_light(name, True)
            _sleep_until(start + when + length)
            for name in STROBES:
                set_light(name, False)

        # The beacon means "engines running", which here is "armed".
        if _state["armed"] and _state["on"]:
            _sleep_until(start + BEACON_FLASH[0])
            for name in BEACON:
                set_light(name, True)
            _sleep_until(start + BEACON_FLASH[0] + BEACON_FLASH[1])
            for name in BEACON:
                set_light(name, False)

        # The GPS light. Its COLOUR is the message, so it is sent on every
        # flash rather than only when the state changes - a respawn or a
        # world switch brings the aircraft back wearing the colour from its
        # model file, and this puts the right one back within a second.
        _sleep_until(start + GPS_FLASH[0])
        if _state["on"]:
            set_light(GPS_LIGHT, True,
                      GPS_GREEN if _state["gps"] else GPS_RED)
            _sleep_until(start + GPS_FLASH[0] + GPS_FLASH[1])
            set_light(GPS_LIGHT, False)

        _sleep_until(start + CYCLE_S)


def _sleep_until(moment):
    remaining = moment - time.monotonic()
    if remaining > 0:
        time.sleep(remaining)


def start():
    """Begin the pattern thread. Idle until the lights are switched on."""
    global _thread
    if _thread is None or not _thread.is_alive():
        _thread = threading.Thread(target=_run, daemon=True)
        _thread.start()


def set_on(on):
    """Switch the whole set on or off."""
    _state["on"] = bool(on)
    start()
    if not on:
        for name in ALL:
            set_light(name, False)
    return _state["failed"]


def all_off():
    """Switch every light off, whatever the station thinks they are.

    Added 12 Oct 2026. A Gazebo <light> in a model file is ON the moment
    the world loads - there is no "off" element in SDF, only the runtime
    light_config message this module sends. So the aircraft came up with
    all six lights burning and nothing in the console claiming they were
    on, which is the worst of both. The station now sends this once,
    shortly after start-up, so the lights begin off and switching them
    on is a deliberate act during the pre-flight check.
    """
    _state["on"] = False
    _state["armed"] = False
    sent = 0
    for name in ALL:
        if set_light(name, False):
            sent += 1
    return sent


def set_gps(ok):
    """Tell the tail light whether the aircraft has GPS.

    Called from the telemetry loop. Cheap to call repeatedly: it only
    stores a flag, and the flash thread reads it."""
    _state["gps"] = bool(ok)


def set_armed(armed):
    """The beacon follows the armed state, as a real one follows the
    engines. Called from the telemetry loop."""
    _state["armed"] = bool(armed)


def status():
    return {"on": _state["on"], "armed": _state["armed"],
            "problem": _state["failed"]}
