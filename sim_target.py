"""
Which Gazebo world and model the station talks to.

Until 11 Oct 2026 the world name "training_area" was spelled out separately in
six files - freeze/resume, both reposition plugins, the camera topic, the
external-view helper and the wind control. Any new world meant finding and
editing all six, and missing one would leave a control silently talking to a
world that wasn't running.

Set GCS_WORLD to point the station at a different world, matching the
PX4_GZ_WORLD the simulator was launched with:

    GCS_WORLD=flat_test python3 instructor_station.py

The model name follows PX4's own convention of the airframe name plus an
instance number, and is overridable the same way for the rare case of a
second vehicle.
"""

import os

WORLD = os.environ.get("GCS_WORLD", "training_area")
MODEL = os.environ.get("GCS_MODEL", "standard_vtol_0")


def service(name):
    """Full path of one of Gazebo's own world services, e.g. "control"."""
    return f"/world/{WORLD}/{name}"
