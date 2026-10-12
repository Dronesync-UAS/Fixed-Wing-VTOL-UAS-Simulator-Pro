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
NAVIGATION = ["nav_port", "nav_starboard", "nav_tail"]
STROBES = ["strobe_top", "strobe_belly"]
BEACON = ["beacon_top"]
ALL = NAVIGATION + STROBES + BEACON

# One second, as a list of (moment, strobes on, beacon on). A real
# high-intensity strobe double-flashes; a beacon is one slower pulse.
# Times are seconds from the start of each cycle.
CYCLE_S = 1.0
STROBE_FLASHES = [(0.00, 0.06), (0.16, 0.06)]     # (start, how long)
BEACON_FLASH = (0.55, 0.12)

_node = None
_lock = threading.Lock()
_thread = None
_state = {"on": False, "armed": False, "failed": None}


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


def set_light(name, on):
    """Switch one light. Returns True if the message went out."""
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


def set_armed(armed):
    """The beacon follows the armed state, as a real one follows the
    engines. Called from the telemetry loop."""
    _state["armed"] = bool(armed)


def status():
    return {"on": _state["on"], "armed": _state["armed"],
            "problem": _state["failed"]}
