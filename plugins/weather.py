"""
Visibility and precipitation.

Switches on a weather cell over the training area: fog that thickens, rain,
or both. The cell is built into each world by tools/weather_apply.py and
starts off, so this control is the only thing that turns it on.

READ THIS BEFORE USING IT IN A LESSON
-------------------------------------
This changes what the camera SEES. It does not change how the aircraft
FLIES. Gazebo Harmonic's particle emitters are a rendering feature and
nothing in gz-sim8 couples them to aerodynamics. Wind is the only weather in
this simulator that touches the flight model, and that is the separate Wind
control.

So the honest description of this control is: it degrades the instructor's
and student's view, which is a real scenario - flying into a cell and losing
sight of the aircraft on camera. It is not "flying in bad weather", and must
not be logged or taught as if it were.

WHY PARTICLES AND NOT FOG
-------------------------
There is no fog. gz-rendering8 has no fog API - zero occurrences of "fog" in
Scene.hh - and gz-sim8's RenderUtil.cc has none either (both checked
11 Oct 2026). Gazebo's own example world calls a particle emitter a
"fog_generator"; particles are not a workaround here, they are the only
mechanism that exists.

RATES ARE CAPPED FOR A REASON
-----------------------------
Ogre holds 5000 particles per emitter (setParticleQuota(5000) in
Ogre2ParticleEmitter::CreateParticleSystem). Particles alive at once is
about rate x lifetime, so fog's 25 s lifetime caps it near 200/s and rain's
11 s near 450/s. Past the quota Ogre silently stops emitting rather than
reporting anything, so the settings below stay well under it.
"""

import subprocess

import sim_target
from simulator_link import log_instructor_action

FOG_TOPIC = "/weather/fog"
RAIN_TOPIC = "/weather/rain"
MESSAGE_TYPE = "gz.msgs.ParticleEmitter"

OFF = "emitting: {data: false}"

# label -> (fog payload or None, rain payload or None)
# Rates chosen against the quota ceilings in the docstring, not picked to
# look round.
CONDITIONS = {
    "clear": (OFF, OFF),
    "haze": ("emitting: {data: true}, rate: {data: 4}", OFF),
    "fog": ("emitting: {data: true}, rate: {data: 14}", OFF),
    "rain": (OFF, "emitting: {data: true}, rate: {data: 120}"),
    "heavy_rain": (OFF, "emitting: {data: true}, rate: {data: 300}"),
    "fog_and_rain": ("emitting: {data: true}, rate: {data: 14}",
                     "emitting: {data: true}, rate: {data: 120}"),
}

LABELS = {
    "clear": "Clear",
    "haze": "Haze - thin, aircraft still visible",
    "fog": "Fog - aircraft lost in the cell",
    "rain": "Rain",
    "heavy_rain": "Heavy rain",
    "fog_and_rain": "Fog and rain",
}

# "active" is the key instructor_station.failure_status() looks for to light
# the button's on/off dot; "condition" is this plugin's own detail.
state = {"active": False, "condition": "clear"}


def reset_state():
    """Forget the condition when the world restarts.

    Same trap the wind control fell into on 11 Oct: a fresh world loads with
    both emitters off, but the station's own state lived only in the station,
    so the panel kept claiming weather was on over a clear world. A readout
    that lies is worse than no readout.
    """
    state["active"] = False
    state["condition"] = "clear"


sim_target.on_world_change(reset_state)


def _publish(topic, payload):
    """Returns None on success, or a message to show the instructor."""
    try:
        result = subprocess.run(
            ["gz", "topic", "-t", topic, "-m", MESSAGE_TYPE, "-p", payload],
            capture_output=True, text=True)
    except OSError as exc:
        # No gz on PATH means Gazebo is not running in this shell. Report it
        # rather than taking the station down.
        return "cannot run gz (%s)" % exc.strerror
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[0] if detail else "gz topic exited %d" % result.returncode
    return None


def set_weather(condition="clear"):
    payloads = CONDITIONS.get(condition)
    if payloads is None:
        return "Weather not changed - '%s' is not a known condition." % condition

    fog_payload, rain_payload = payloads
    # Both emitters are always addressed, even when a condition only uses
    # one. Leaving the other at whatever the last condition set is how you
    # end up with rain still falling inside "Fog".
    for topic, payload in ((FOG_TOPIC, fog_payload), (RAIN_TOPIC, rain_payload)):
        error = _publish(topic, payload)
        if error:
            return "Weather not changed - %s (%s)." % (error, topic)

    state["condition"] = condition
    state["active"] = condition != "clear"
    log_instructor_action("weather", "condition=%s" % condition)
    if condition == "clear":
        return "Weather cleared."
    return ("%s. Note: this changes the camera view only - the aircraft's "
            "flight is unaffected. Use Wind for that." % LABELS[condition])


PLUGIN = {
    "id": "weather",
    "label": "Set Weather",
    "category": "Experimental - In Development",
    "style": "experimental",
    "inputs": [
        {"name": "condition", "label": "Condition", "type": "select",
         "default": "clear",
         "options": [{"value": key, "label": LABELS[key]} for key in
                     ("clear", "haze", "fog", "rain", "heavy_rain",
                      "fog_and_rain")]},
    ],
    "handler": set_weather,
}
