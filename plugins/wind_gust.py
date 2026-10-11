"""
Wind / gust control. Sets wind in Gazebo at runtime, using the same
"talk to Gazebo's own service/topic directly" technique already proven in
freeze_resume.py and reset_spawn.py.

CONFIRMED 11 Oct 2026 (this is what the earlier "unconfirmed" note was
waiting on):
  * The WindEffects system plugin is now declared in all four
    training_area*.sdf worlds, alongside the 8 systems PX4 already
    declared there - added by tools/wind_apply.py, which also explains why
    the plugin had to go in the world file rather than a server.config.
  * /world/training_area/wind exists and accepts commands, and the
    plugin's own wind_info service reads back the commanded value. So the
    instructor -> Gazebo path is proven, not assumed.

NOT YET CONFIRMED - why this is still filed as experimental:
  * No flight has been flown with wind set, so how strongly the aircraft
    actually responds has not been observed. Gazebo's LiftDrag system does
    subtract wind from the airspeed vector, so the wings should feel it,
    but "should" is not "seen".
  * The direction convention below (which way is north in this world) is
    reasoned from the world's ENU frame, not measured. Check it with one
    flight: set 270 (from the west) and confirm the aircraft drifts EAST.
    If it drifts the wrong way, the fix is the sign of x/y in _wind_vector.

Move this to a normal category once both of those are observed.

Direction follows the aviation convention the instructors already use:
the direction the wind comes FROM, in degrees true. 270 = a westerly.
"""

import math
import subprocess

from sim_target import service
from simulator_link import log_instructor_action

# Zero wind still carries enable_wind, so "calm" is an explicit command
# rather than switching the wind system off underneath the aircraft.
CALM = "linear_velocity: {x: 0, y: 0, z: 0}, enable_wind: true"

state = {"active": False}


def _wind_vector(speed_ms, direction_deg):
    """Aviation wind direction (degrees FROM, true) -> Gazebo ENU velocity.

    The world declares an ENU frame, so world X is east and Y is north.
    Wind "from 270" blows towards 090, i.e. towards the east: +x.
    """
    towards = math.radians(direction_deg + 180.0)
    return speed_ms * math.sin(towards), speed_ms * math.cos(towards)


def _publish(payload):
    """Returns None on success, or a message to show the instructor."""
    try:
        result = subprocess.run([
            "gz", "topic", "-t", service("wind"),
            "-m", "gz.msgs.Wind",
            "-p", payload,
        ], capture_output=True, text=True)
    except OSError as exc:
        # No gz on PATH means Gazebo isn't installed/running in this shell.
        # Report it on the console rather than taking the station down.
        return f"cannot run gz ({exc.strerror})"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[0] if detail else f"gz topic exited {result.returncode}"
    return None


def set_wind(speed_ms=8, direction_deg=270):
    if state["active"]:
        error = _publish(CALM)
        if error:
            return f"Wind not cleared - {error}"
        state["active"] = False
        log_instructor_action("wind_calm")
        return "Wind set to calm."

    try:
        speed = float(speed_ms)
        direction = float(direction_deg)
    except (TypeError, ValueError):
        return f"Wind not set - '{speed_ms}' / '{direction_deg}' are not numbers."
    if speed < 0:
        return "Wind not set - speed cannot be negative."
    if not 0 <= direction <= 360:
        return "Wind not set - direction must be between 0 and 360 degrees."

    east, north = _wind_vector(speed, direction)
    error = _publish(
        f"linear_velocity: {{x: {east:.3f}, y: {north:.3f}, z: 0}}, enable_wind: true")
    if error:
        return f"Wind not set - {error}"

    state["active"] = True
    log_instructor_action("wind_set", f"speed_ms={speed:g}, direction_deg={direction:g}")
    return f"Wind set: {speed:g} m/s from {direction:g}°."


PLUGIN = {
    "id": "wind_gust",
    "label": "Wind On / Off",
    "category": "Experimental - In Development",
    "style": "experimental",
    "inputs": [
        {"name": "speed_ms", "label": "Speed (m/s)", "default": 8, "min": 0, "step": 1},
        {"name": "direction_deg", "label": "From (°true)", "default": 270, "min": 0, "step": 10},
    ],
    "handler": set_wind,
}
