"""
Training environment selector.

Picks which world the simulator runs in and points the station at it, without
dropping to a terminal. Added 11 Oct 2026 on request.

What it does when you press the button:
  1. stops the running PX4 and Gazebo
  2. relaunches them in the chosen world, at that world's own spawn height
  3. points the station's Gazebo controls - freeze, reposition, wind - at the
     new world name
  4. re-subscribes the camera feed, whose topic carries the world name
  5. remembers the choice, so the next start-up comes back to it

The simulator takes roughly 15-30 seconds to come up. Telemetry returns on its
own once PX4 is listening again; if it does not, restart the station.

Worlds are listed with their RELIEF - the height range within the station's
500 m range limit. That is the number that decides whether a world can be
flown: with a 120 m ceiling, a world with more relief than that inside the
range limit has no airspace a student can legally use. It is why the Hoggar
world needed its clearing widened before it was usable at all.

This replaces nothing - the same thing can still be done from a terminal with
tools/start_world.sh, which this calls.
"""

import os
import subprocess

import sim_target
import terrain_backdrop
import video_feed
from simulator_link import log_instructor_action

GCS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(GCS, "tools", "start_world.sh")
LAUNCH_LOG = os.path.expanduser("~/uas_sim_logs/sim_launch.log")

DEFAULT_KEY = "blackrock"


def _launch(key):
    """Start the simulator in the chosen world, detached from the station.

    Output goes to a log file rather than the station's terminal: the build
    and launch are noisy, and the station's own terminal is where connection
    messages need to stay readable.
    """
    os.makedirs(os.path.dirname(LAUNCH_LOG), exist_ok=True)
    try:
        with open(LAUNCH_LOG, "w") as log:
            subprocess.Popen(["bash", LAUNCHER, key],
                             stdout=log, stderr=subprocess.STDOUT,
                             start_new_session=True)
    except OSError as exc:
        return f"could not start the launcher ({exc.strerror})"
    return None


def select_environment(environment=DEFAULT_KEY):
    entry = sim_target.BY_KEY.get(environment)
    if entry is None:
        return f"Environment not changed - '{environment}' is not a known world."
    if not os.path.isfile(LAUNCHER):
        return f"Environment not changed - {LAUNCHER} is missing."

    error = _launch(entry["key"])
    if error:
        return f"Environment not changed - {error}"

    # Point the station at the new world before the simulator finishes coming
    # up: the controls are only used once it is running, and doing it here
    # means there is no window where they address the old world.
    save_warning = sim_target.set_world(entry["world"])
    terrain_backdrop.reset()
    try:
        video_feed.resubscribe()
    except Exception as exc:                      # a camera that fails to
        save_warning = f"camera feed not reconnected ({exc})"   # resubscribe
                                                  # must not fail the switch
    log_instructor_action("environment", f"world={entry['world']}")

    message = (f"Loading {entry['label']}. The simulator restarts - "
               f"about 15-30 seconds. Telemetry returns on its own.")
    return f"{message} (Note: {save_warning}.)" if save_warning else message


PLUGIN = {
    "id": "environment",
    "label": "Load Environment",
    "category": "Simulation Control",
    "style": "normal",
    "inputs": [
        {"name": "environment", "label": "Training area", "type": "select",
         "default": DEFAULT_KEY,
         "options": [
             {"value": e["key"],
              "label": f"{e['label']}  ({e['relief_m']:g} m relief)"}
             for e in sim_target.ENVIRONMENTS]},
    ],
    "handler": select_environment,
}
