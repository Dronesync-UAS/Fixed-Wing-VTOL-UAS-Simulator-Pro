"""
PROPELLERS THAT TURN WHEN THE AIRCRAFT IS ARMED.

Added 12 Oct 2026, on the observation that arming did not visibly do
anything to the propellers.

THE CAUSE, AND IT IS A REAL ONE
--------------------------------
PX4's own airframe file for this aircraft -
ROMFS/px4fmu_common/init.d-posix/airframes/4004_gz_standard_vtol in
v1.15.4 - sets

    param set-default SIM_GZ_EC_MIN1 10      (and 2, 3, 4)
    param set-default SIM_GZ_EC_MAX1 1500

Those numbers are the rotor speed the gz bridge sends Gazebo, in radians
a second: the same units as the model's own <maxRotVelocity>1500</>. So
an armed aircraft sitting on the ground spins its rotors at 10 rad/s -
1.6 turns a second, about 95 rpm. On screen that is a propeller which is
not moving.

A real multirotor spins up to a clearly audible, clearly visible idle
the instant it is armed, and that moment matters: it is the point at
which the aircraft becomes dangerous, and a student should learn to
treat it that way.

WHAT THIS SETS IT TO, AND WHY THAT NUMBER
------------------------------------------
Worked out from the aircraft's own model rather than picked:

    thrust per rotor = motorConstant * omega^2        (the gz
        MulticopterMotorModel's own relation)
    motorConstant = 2e-05                             (model.sdf line 763)
    aircraft mass = 5 kg                              (model.sdf line 10)

Hovering needs 5 * 9.81 / 4 = 12.3 N a rotor, so

    omega_hover = sqrt(12.3 / 2e-05) = 784 rad/s

A real machine idles at roughly 15-20% of its hover speed. 130 rad/s is
17% of 784, which puts 0.34 N under each rotor - 1.4 N in total, under
3% of the aircraft's weight. It will not lift anything, and it will not
creep.

WHY NOT HIGHER. The minimum is a floor on what the controller can ask
for, so raising it eats into the authority the mixer has to reduce
thrust on one rotor to hold attitude, and at some point the aircraft
cannot descend. 17% is well below where that becomes an argument. Do not
raise it much without flying it.

THE PUSHER IS LEFT ALONE. PX4 sets SIM_GZ_EC_MIN5 to 0, and that is
correct: a fixed-wing pusher does NOT windmill on the pad, and making it
do so would teach the wrong thing.

HOW IT IS APPLIED. Over MAVLink, at runtime, after the station connects.
Nothing is written to PX4's saved parameters and nothing in PX4's tree
is edited - so the next person to run the same build without this
station gets PX4's own values back.

NOT YET FLOWN. The arithmetic is off the model and the airframe file;
nobody has armed the aircraft and watched the propellers with this set.
"""
import simulator_link
from simulator_link import log_instructor_action

# The four hover rotors. The pusher (channel 5) is deliberately absent.
CHANNELS = (1, 2, 3, 4)
PARAM = "SIM_GZ_EC_MIN%d"

# PX4's own value, so the control can put it back.
PX4_DEFAULT = 10

# See the docstring for where this comes from.
IDLE_RAD_S = 130

# Refuse anything that would be a quarter of hover speed or more. At that
# point the floor starts eating the mixer's authority and the aircraft
# may not be able to descend, and this is not a setting to discover that
# with.
MAX_SAFE_RAD_S = 190

state = {"active": False, "value": None}


def apply_idle(value=IDLE_RAD_S, quiet=False):
    """Set the armed idle speed on the four hover rotors."""
    try:
        wanted = int(float(value))
    except (TypeError, ValueError):
        return "Idle spin not set - '%s' is not a number." % value
    if wanted < 0 or wanted > MAX_SAFE_RAD_S:
        return ("Idle spin not set - keep it between 0 and %d rad/s. Above "
                "that it starts eating the controller's authority to hold "
                "attitude at low throttle." % MAX_SAFE_RAD_S)

    problems = []
    for channel in CHANNELS:
        problem = simulator_link.set_param(PARAM % channel, wanted)
        if problem:
            problems.append(problem)
    if problems:
        state["active"] = False
        return "Idle spin not set - %s" % problems[0]

    state["active"] = wanted > PX4_DEFAULT
    state["value"] = wanted
    log_instructor_action("idle_spin", "rad_s=%d" % wanted)
    if quiet:
        return None
    if wanted <= PX4_DEFAULT:
        return ("Idle spin back to PX4's own %d rad/s - the propellers will "
                "barely turn when armed." % PX4_DEFAULT)
    return ("Idle spin %d rad/s on the four hover rotors - about %d%% of "
            "hover speed, so the propellers turn visibly the moment the "
            "aircraft is armed. The pusher is left stopped, as a real one "
            "is." % (wanted, round(wanted / 784.0 * 100)))


def toggle_idle(value=IDLE_RAD_S):
    """The console button: on, then back to PX4's own value."""
    if state["active"]:
        return apply_idle(PX4_DEFAULT)
    return apply_idle(value)


PLUGIN = {
    "id": "idle_spin",
    "label": "Idle spin on arm",
    "category": "Simulation Control",
    "style": "normal",
    "inputs": [
        {"name": "value", "label": "Idle (rad/s)", "default": IDLE_RAD_S,
         "min": 0, "max": MAX_SAFE_RAD_S, "step": 10},
    ],
    "handler": toggle_idle,
}
