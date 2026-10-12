"""
Which Gazebo world and model the station talks to, and the list of training
environments it can switch between.

Until 11 Oct 2026 the world name "training_area" was spelled out separately in
six files - freeze/resume, both reposition plugins, the camera topic, the
external-view helper and the wind control. Any new world meant finding and
editing all six, and missing one would leave a control silently talking to a
world that wasn't running.

The world can be set three ways, in this order of precedence:

  1. GCS_WORLD in the environment, for a one-off session:
         GCS_WORLD=flat_test python3 instructor_station.py
  2. the last environment chosen from the station's Environment panel, which
     is remembered in ~/uas_sim_logs/gcs_world.json
  3. the default below

RELIEF FIGURES are the height range within the station's 500 m range limit,
measured from each world's own heightmap on 11 Oct 2026. They are the number
that decides whether a world is usable: the station also enforces a 120 m
ceiling, so a world with more relief than that inside the range limit has no
airspace a student can legally fly in. Hoggar is listed at 0 m because its
clearing was widened to 600 m that day - beyond 1 km it still rises 582 m.
"""

import json
import os

DEFAULT_WORLD = "training_area"
STATE_FILE = os.path.join(os.path.expanduser("~/uas_sim_logs"), "gcs_world.json")

# key | world file name | spawn height (m) | relief within 500 m | description
ENVIRONMENTS = [
    {"key": "blackrock", "world": "training_area_blackrock", "spawn_z": 1.3,
     "relief_m": 0.6,
     "label": "Black Rock playa, Nevada - flattest"},
    {"key": "nullarbor", "world": "training_area_nullarbor", "spawn_z": 11.3,
     "relief_m": 7.9,
     "label": "Nullarbor Plain, Australia - gently undulating"},
    {"key": "uyuni", "world": "training_area_uyuni", "spawn_z": 8.3,
     "relief_m": 9.5,
     "label": "Salar de Uyuni, Bolivia - gently undulating"},
    {"key": "hoggar", "world": "training_area", "spawn_z": 605.1,
     "relief_m": 0.0,
     "label": "Hoggar Mountains, Algeria - flat to 600 m, mountains beyond"},
    {"key": "lowlands", "world": "training_area_lowlands", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Cambridgeshire fens, England - flat, farmed, hedged"},
    # Added 12 Oct 2026. All six are flat ground with scenery over it,
    # except the valley, whose floor is flat out to 520 m either side -
    # beyond the 500 m range limit, so still no relief anywhere a
    # student can legally fly.
    {"key": "coast", "world": "training_area_coast", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "North Norfolk coast - shoreline, harbour, pine belt"},
    {"key": "airfield", "world": "training_area_airfield", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Licensed airfield - runway, markings, circuits"},
    {"key": "estate", "world": "training_area_estate", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Industrial estate, Thames estuary - obstacles and clutter"},
    {"key": "forest", "world": "training_area_forest", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Thetford Forest - plantation blocks and firebreaks"},
    {"key": "valley", "world": "training_area_valley", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Valley, north Wales - flat floor, 200 m ridges either side"},
    {"key": "flood", "world": "training_area_flood", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Flooded farmland, Somerset Levels - flood response"},
    {"key": "flat", "world": "flat_test", "spawn_z": 0.3,
     "relief_m": 0.0,
     "label": "Plain flat ground, no scenery - for isolating faults"},
]

BY_KEY = {env["key"]: env for env in ENVIRONMENTS}
BY_WORLD = {env["world"]: env for env in ENVIRONMENTS}


def _remembered():
    try:
        with open(STATE_FILE) as handle:
            value = json.load(handle).get("world")
        return value if value in BY_WORLD else None
    except (OSError, ValueError, AttributeError):
        return None


WORLD = os.environ.get("GCS_WORLD") or _remembered() or DEFAULT_WORLD
MODEL = os.environ.get("GCS_MODEL", "standard_vtol_0")


def remember(world):
    """Persist the chosen world so the next start-up uses it. Failing to save
    must not stop a switch that has otherwise worked, so this reports rather
    than raises."""
    try:
        os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
        with open(STATE_FILE, "w") as handle:
            json.dump({"world": world}, handle)
        return None
    except OSError as exc:
        return f"could not save the choice ({exc.strerror})"


# Things that hold state tied to the running world and must forget it when the
# world changes. Plugins register here at import; the environment control calls
# world_changed() after a switch. A registry rather than imports, because
# plugins are loaded from files and are not importable by name.
_on_world_change = []


def on_world_change(callback):
    _on_world_change.append(callback)
    return callback


def world_changed():
    for callback in _on_world_change:
        try:
            callback()
        except Exception:
            # One plugin failing to reset must not abandon the rest, nor fail
            # the switch itself.
            pass


def set_world(world):
    """Point the station at a different world, from now on.

    Everything that talks to Gazebo builds its topic or service name through
    service() or reads sim_target.WORLD at call time, so this takes effect
    without a restart - except the camera feed, which holds a subscription and
    is re-subscribed separately by video_feed.resubscribe().
    """
    global WORLD
    WORLD = world
    return remember(world)


def environment():
    """The entry for the current world, or None for a world not in the list."""
    return BY_WORLD.get(WORLD)


# The aircraft's two cameras, as link/sensor pairs. The nose camera is part
# of the model as this project has it; the chase camera is added by
# tools/chase_camera_apply.py, and these names are the contract between that
# tool and the topics the station subscribes to - change one and the other
# stops finding it.
NOSE_CAMERA = ("camera_pitch_link", "fpv_camera")
CHASE_CAMERA = ("base_link", "chase_camera")

# The payload gimbal, added by tools/gimbal_apply.py. Same contract as the
# cameras above: these names appear in the model file the tool writes, in
# the topics the station subscribes and publishes to, and nowhere else.
# Change one without the other and the payload view goes quiet with no
# error anywhere.
GIMBAL_LINKS = ("gimbal_yaw_link", "gimbal_pitch_link")
GIMBAL_JOINTS = ("gimbal_yaw_joint", "gimbal_pitch_joint")
GIMBAL_CAMERA = (GIMBAL_LINKS[1], "payload_camera")

# The rangefinder is given an explicit topic in the model rather than
# letting Gazebo derive one. The derived name for a lidar is not the same
# shape as the one for a camera, and guessing it wrong is a silent
# failure; an explicit topic is one fewer thing to be wrong about.
LRF_TOPIC = "/uas/payload/lrf"

# How far the gimbal can look. Written here because the station clamps to
# these and the model file is generated from them.
GIMBAL_PAN_LIMIT_DEG = 180.0
GIMBAL_TILT_UP_DEG = -30.0      # above the horizon
GIMBAL_TILT_DOWN_DEG = 90.0     # straight down

# The chase camera's boom, added by tools/chase_angles_apply.py. The
# camera MOVES onto chase_el_link when that tool is run, which changes the
# topic it publishes on - so the station subscribes to the old base_link
# topic and the new one at the same time and takes whichever is live. See
# chase_camera_topics() below.
CHASE_BOOM_LINKS = ("chase_az_link", "chase_el_link")
CHASE_BOOM_JOINTS = ("chase_az_joint", "chase_el_joint")

# The camera's widest field of view, in radians, as written into the model.
# The station reads the real value out of Gazebo's camera_info when it can
# and falls back to this.
GIMBAL_FOV_RAD = 1.05


def world_topic(name):
    """A topic published under this world, e.g. material_color.

    Same shape as service(); named apart because a reader who sees
    service() reasonably expects a request and an answer, and a topic
    gives neither.
    """
    return f"/world/{WORLD}/{name}"


def service(name):
    """Full path of one of Gazebo's own world services, e.g. "control"."""
    return f"/world/{WORLD}/{name}"


def _image_topic(link, sensor):
    return f"/world/{WORLD}/model/{MODEL}/link/{link}/sensor/{sensor}/image"


def camera_topic():
    """The nose (FPV) camera."""
    return _image_topic(*NOSE_CAMERA)


def gimbal_camera_topic():
    """The payload gimbal's camera.

    Only publishes once tools/gimbal_apply.py has added the gimbal to the
    aircraft model; until then the topic has no publisher, which the feed's
    watchdog treats exactly like a camera that has not started yet.
    """
    return _image_topic(*GIMBAL_CAMERA)


def gimbal_joint_topic(joint):
    """Where a gz-sim JointPositionController listens for this joint.

    /model/<model>/joint/<joint>/<axis>/cmd_pos, taking a gz.msgs.Double -
    the documented default for that system in gz-sim 8 (Harmonic). Note it
    is scoped to the MODEL, not the world, so it does not change when the
    environment does.
    """
    return f"/model/{MODEL}/joint/{joint}/0/cmd_pos"


def chase_camera_topic():
    """The chase camera - behind and above the aircraft, looking forward.

    Only publishes once tools/chase_camera_apply.py has added the sensor to
    the aircraft model. Until then the topic simply has no publisher, which
    the feed's watchdog treats the same as a camera that has not started yet.
    """
    return _image_topic(*CHASE_CAMERA)


def chase_camera_topics():
    """Both places the chase camera can be, as a list.

    The camera starts on base_link and moves to the boom's elevation link
    when tools/chase_angles_apply.py is run. Rather than make that tool
    compulsory, or ask the station to work out which was done, the feed
    subscribes to both: only one of them ever has a publisher, so only one
    ever delivers a frame.
    """
    return [_image_topic(*CHASE_CAMERA),
            _image_topic(CHASE_BOOM_LINKS[1], CHASE_CAMERA[1])]


def chase_boom_topic(joint):
    """Where the boom's position controller for this joint listens."""
    return f"/model/{MODEL}/joint/{joint}/0/cmd_pos"
