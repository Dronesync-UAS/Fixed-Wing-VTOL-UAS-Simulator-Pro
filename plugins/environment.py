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
import time

import sim_target
import terrain_backdrop
import video_feed
from simulator_link import log_instructor_action, reset_flight_state

GCS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAUNCHER = os.path.join(GCS, "tools", "start_world.sh")
LAUNCH_LOG = os.path.expanduser("~/uas_sim_logs/sim_launch.log")

DEFAULT_KEY = "blackrock"


# How long to wait before deciding the launcher is under way. It takes
# 15-30 seconds to bring Gazebo and PX4 up, so this cannot wait for
# success - but anything that is going to REFUSE does so at once: an
# unknown world, a missing world file, worlds that would not install.
LAUNCH_CHECK_S = 3.0


def _launcher_knows(key):
    """Whether tools/start_world.sh has this world in its own table.

    IT HAD SEVEN MISSING until 12 Oct 2026, which is the whole reason
    this check exists: six training areas were in sim/worlds and in this
    plugin's drop-down but not in the launcher, so choosing one ran
    "start_world.sh coast", which answered "Unknown world: coast" and
    exited - into a log file nobody reads, while this plugin cheerfully
    reported that the simulator was restarting.
    """
    try:
        with open(LAUNCHER) as handle:
            return ("\n%s|" % key) in handle.read()
    except OSError:
        return True          # cannot tell; let the launcher answer


def _tail(path, lines=6):
    try:
        with open(path) as handle:
            return " / ".join(handle.read().strip().splitlines()[-lines:])
    except OSError:
        return ""


def _launch(key):
    """Start the simulator in the chosen world, detached from the station.

    Output goes to a log file rather than the station's terminal: the build
    and launch are noisy, and the station's own terminal is where connection
    messages need to stay readable.

    BUT THE EXIT CODE IS CHECKED. This used to fire and forget, so a
    launcher that refused looked exactly like one that worked - the
    station said "the simulator restarts" and nothing happened. It now
    waits a few seconds, which is long enough for a refusal and far too
    short for a success, and reports what the log says if it died.
    """
    os.makedirs(os.path.dirname(LAUNCH_LOG), exist_ok=True)
    try:
        with open(LAUNCH_LOG, "w") as log:
            process = subprocess.Popen(["bash", LAUNCHER, key],
                                       stdout=log, stderr=subprocess.STDOUT,
                                       start_new_session=True)
    except OSError as exc:
        return f"could not start the launcher ({exc.strerror})"

    deadline = time.monotonic() + LAUNCH_CHECK_S
    while time.monotonic() < deadline:
        code = process.poll()
        if code is None:
            time.sleep(0.25)
            continue
        if code == 0:
            # Exited cleanly in under three seconds. start_world.sh does
            # not return until the simulator stops, so this means it
            # printed its usage and gave up.
            return ("the launcher stopped straight away. It said: %s"
                    % (_tail(LAUNCH_LOG) or "nothing"))
        return ("the launcher refused (exit %d). It said: %s"
                % (code, _tail(LAUNCH_LOG) or "nothing"))
    return None


def select_environment(environment=DEFAULT_KEY):
    entry = sim_target.BY_KEY.get(environment)
    if entry is None:
        return f"Environment not changed - '{environment}' is not a known world."
    if not os.path.isfile(LAUNCHER):
        return f"Environment not changed - {LAUNCHER} is missing."
    if not _launcher_knows(entry["key"]):
        return (f"Environment not changed - tools/start_world.sh does not "
                f"know '{entry['key']}', so it cannot launch it. The world "
                f"file exists; the launcher's own list is what is missing it.")

    error = _launch(entry["key"])
    if error:
        return f"Environment not changed - {error}"

    # Point the station at the new world before the simulator finishes coming
    # up: the controls are only used once it is running, and doing it here
    # means there is no window where they address the old world.
    save_warning = sim_target.set_world(entry["world"])
    terrain_backdrop.reset()
    # The previous world's track and home point are meaningless here, and a
    # stale home makes the range-from-home limit nonsense - it is computed
    # against a point that can be thousands of kilometres away.
    reset_flight_state()
    # A fresh world loads with <wind> at zero, so anything holding state tied
    # to the old world - the wind control's on/off light, for one - must
    # forget it.
    sim_target.world_changed()
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
