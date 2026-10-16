"""
THE AIR THE AIRCRAFT IS FLYING IN - set as a named condition, not a number.

Added 12 Oct 2026, on the instruction to make the aircraft's movement as
realistic as possible.

WHAT WAS ACTUALLY UNREALISTIC
-----------------------------
Not much, and it is worth being precise rather than vague about it. The
flight dynamics are PX4 v1.15.4's own SITL control running against
Gazebo's LiftDrag system and the standard_vtol airframe's own mass,
inertia and aerofoil coefficients. That IS the reference implementation;
there is nothing in this project that could make it more faithful, and
hand-tuning its coefficients would make it less.

The IMU in the model already carries Gaussian noise with a dynamic bias
and a 1000 s correlation time - PX4's own figures, not placeholders - so
the instruments are not unrealistically clean either.

What was unrealistic was the AIR. Every world ships with
<wind><linear_velocity>0 0 0</linear_velocity>, and nothing set it unless
an instructor pressed the wind button. An aircraft hovering in
mathematically still air sits as though nailed in place, and a student
who learns to hover in that has learned nothing about holding a position.
Real air is never still.

WHAT THIS DOES
--------------
Sets the wind to a named condition off the Beaufort scale, with the
direction the instructor chooses. The speeds below are the standard
Beaufort mean speeds at 10 m, which is the scale every pilot already
knows - so "Force 4" means the same here as it does in a forecast.

The world files already describe how the wind VARIES: the WindEffects
system in each of them carries a sinusoidal variation and a Gaussian
noise term on both magnitude and direction. So setting a mean here gives
a wind that breathes, rather than a constant push.

DEFAULT AT START-UP. The station applies Force 1, light air, when it
comes up - see instructor_station. One metre a second is barely
perceptible and well inside anything the airframe cares about, but it is
not zero, and a hover in it looks like a hover rather than a photograph.
Press Calm to switch it off.

WHERE THE OPERATING LIMIT SITS. Most small UAS are cleared to about
10 m/s, so Force 5 is at the edge and Force 6 is beyond it for most
types. That is a teaching point, not a simulator limit: the aircraft
will try, and the flight log will show what it cost.

NOT FLOWN. The wind path itself is proven - plugins/wind_gust.py
confirmed on 11 Oct that the topic exists and is accepted - but no
flight has been flown at any of these settings, and the direction
convention is still the one wind_gust.py flags as reasoned rather than
measured.
"""
import math
import subprocess

import sim_target
from sim_target import service
from simulator_link import log_instructor_action

# The Beaufort scale, as every pilot already knows it: force number,
# name, and the mean speed at 10 m in metres a second. The speeds are
# the middle of each band.
BEAUFORT = [
    (0, "Calm", 0.0),
    (1, "Light air", 1.0),
    (2, "Light breeze", 2.5),
    (3, "Gentle breeze", 4.5),
    (4, "Moderate breeze", 6.7),
    (5, "Fresh breeze", 9.3),
    (6, "Strong breeze", 12.3),
]

BY_FORCE = {force: (name, speed) for force, name, speed in BEAUFORT}

# What the station sets when it starts, so an untouched session is not
# flown in dead air. See the docstring.
DEFAULT_FORCE = 1

# Most small UAS are cleared to about this. Above it the console says so.
TYPICAL_LIMIT_MS = 10.0

state = {"force": None, "direction_deg": 270}


def reset_state():
    """Forget the condition when the world changes.

    A new world loads with its own <wind> at zero, so the station's idea
    of what the air is doing would otherwise be wrong - the same trap
    wind_gust.py documents from 11 Oct, where a crosswind left running
    across a restart was mistaken for a flight-control fault.
    """
    state["force"] = None


sim_target.on_world_change(reset_state)


def _vector(speed_ms, direction_deg):
    """Aviation wind direction (degrees FROM, true) -> Gazebo ENU velocity.

    Same convention and same arithmetic as plugins/wind_gust.py - the
    world declares an ENU frame, so x is east and y is north, and wind
    "from 270" blows towards the east.
    """
    towards = math.radians(direction_deg + 180.0)
    return speed_ms * math.sin(towards), speed_ms * math.cos(towards)


def _publish(payload):
    try:
        result = subprocess.run(
            ["gz", "topic", "-t", service("wind"), "-m", "gz.msgs.Wind",
             "-p", payload], capture_output=True, text=True)
    except OSError as exc:
        return f"cannot run gz ({exc.strerror})"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[0] if detail else f"gz topic exited {result.returncode}"
    return None


def apply_force(force, direction_deg=None, quiet=False):
    """Set the air to a Beaufort force. Returns a message, or None if quiet."""
    try:
        force = int(force)
    except (TypeError, ValueError):
        return f"Conditions not set - '{force}' is not a force number."
    if force not in BY_FORCE:
        return ("Conditions not set - force must be 0 to %d."
                % max(BY_FORCE))
    if direction_deg is not None:
        try:
            direction = float(direction_deg)
        except (TypeError, ValueError):
            return f"Conditions not set - '{direction_deg}' is not a bearing."
        if not 0 <= direction <= 360:
            return "Conditions not set - the bearing must be 0 to 360."
        state["direction_deg"] = direction
    name, speed = BY_FORCE[force]
    east, north = _vector(speed, state["direction_deg"])
    problem = _publish("linear_velocity: {x: %.3f, y: %.3f, z: 0}, "
                       "enable_wind: true" % (east, north))
    if problem:
        return f"Conditions not set - {problem}"
    state["force"] = force
    log_instructor_action("conditions",
                          f"force={force} speed_ms={speed:g} "
                          f"direction_deg={state['direction_deg']:g}")
    if quiet:
        return None
    if force == 0:
        return ("Calm - mathematically still air. Real air never is; this "
                "is for isolating a handling problem, not for a lesson.")
    note = ""
    if speed > TYPICAL_LIMIT_MS:
        note = (" This is beyond the wind limit most small UAS are cleared "
                "to - the aircraft will try, and the flight log will show "
                "what it cost.")
    return ("Force %d, %s: %.1f m/s from %g° true.%s"
            % (force, name.lower(), speed, state["direction_deg"], note))


def set_conditions(force=DEFAULT_FORCE, direction_deg=270):
    return apply_force(force, direction_deg)


PLUGIN = {
    "id": "conditions",
    "label": "Conditions",
    "category": "Simulation Control",
    "style": "normal",
    # A setting, not an action: it applies the moment its value
    # changes rather than waiting for its own button.
    "apply_on_change": True,
    "inputs": [
        {"name": "force", "label": "Beaufort force", "default": DEFAULT_FORCE,
         "min": 0, "max": max(BY_FORCE), "step": 1},
        {"name": "direction_deg", "label": "From (°true)", "default": 270,
         "min": 0, "max": 360, "step": 10},
    ],
    "handler": set_conditions,
}
