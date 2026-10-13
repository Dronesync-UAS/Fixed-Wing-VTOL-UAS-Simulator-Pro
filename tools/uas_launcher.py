#!/usr/bin/env python3
"""
One command - or one desktop icon - that starts the whole simulator.

    python3 tools/uas_launcher.py                # last used training area
    python3 tools/uas_launcher.py blackrock      # a specific one
    python3 tools/uas_launcher.py --stop         # stop everything
    python3 tools/uas_launcher.py --status       # what is running
    python3 tools/uas_launcher.py --toggle       # what the desktop icon does

Before this, starting a session meant: open a terminal, run start_world.sh,
wait, open a second terminal, run instructor_station.py with the matching
GCS_WORLD, then open a browser. Four steps in three windows, and getting the
world name different between steps one and two left the station's controls
talking to a world that wasn't running - a failure that looks like broken
buttons, not like a typo.

This does the same thing in one step and makes the two agree by construction:
the world is chosen once here and passed to both.

Deliberately has no GUI toolkit dependency. tkinter is not installed by
default on Ubuntu, and a launcher that fails to launch because its own window
toolkit is missing would be worse than no launcher. Progress is printed
instead, and the desktop entry opens a terminal window to show it.

Install the desktop icons with:  tools/install_launcher.sh
"""

import argparse
import glob
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

PX4_DIR = os.path.expanduser("~/PX4-Autopilot")
LOG_DIR = os.path.expanduser("~/uas_sim_logs")
SIM_LOG = os.path.join(LOG_DIR, "sim_launch.log")
STATION_LOG = os.path.join(LOG_DIR, "gcs.log")
STATION_URL = "http://localhost:8080"
STATION_PORT = 8080

# Where the Gazebo camera is put once the window exists. Without this the
# view starts wherever the world left it, which on these worlds is pointing
# at empty desert - the aircraft is a few metres across on a 16 km terrain,
# so "not in view" is the normal case and finding it by hand is the first
# thing anyone has to do. 12 m matches the console's own Camera panel
# default, so the launcher and the panel agree.
CAMERA_VIEW = "rear_above"
CAMERA_DISTANCE_M = 12
CAMERA_TIMEOUT_S = 90

# PX4 prints this once its startup script has run; it is the earliest point
# at which it is listening for MAVLink, which is all the station needs.
PX4_READY = "Startup script returned successfully"
# ...and these mean it is never going to.
PX4_FAILED = ("ninja: build stopped", "make: ***")

# A first build of PX4 from clean takes minutes; a rebuild takes seconds.
# Wait long enough for the slow case rather than giving up on a build that
# was going to work.
PX4_TIMEOUT_S = 420
STATION_TIMEOUT_S = 60

# Process patterns, matching tools/start_world.sh so that stopping from here
# and stopping from there do the same thing.
PX4_PATTERNS = ("bin/px4", "gz sim")
STATION_PATTERN = "instructor_station.py"


def say(step, message):
    print("[%s] %s" % (step, message), flush=True)


# ---------------------------------------------------------------- state

def _pgrep(pattern):
    """PIDs whose command line contains `pattern`, or [] - never raises, so a
    missing pgrep degrades to "nothing running" rather than stopping a start."""
    try:
        out = subprocess.run(["pgrep", "-f", pattern], capture_output=True,
                             text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return []
    return [int(p) for p in out.stdout.split() if p.isdigit()]


def _port_open(port, host="127.0.0.1", timeout=0.5):
    with socket.socket() as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0


def _station_answering():
    """A listening port is not the same as a station: something else could
    hold 8080. Ask for an endpoint only the station serves."""
    if not _port_open(STATION_PORT):
        return False
    try:
        with urllib.request.urlopen(
                STATION_URL + "/connection_status", timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError, ValueError):
        return False


def simulator_running():
    return any(_pgrep(p) for p in PX4_PATTERNS)


# ---------------------------------------------------------------- stop

def stop_all(quiet=False):
    """Stop the simulator and the station. Returns what was actually stopped.

    Worth doing even on a start: Ctrl+C on a previous run leaves PX4 alive,
    and the next launch then dies with "PX4 server already running for
    instance 0", which says nothing about the real cause.
    """
    stopped = []
    for pattern in PX4_PATTERNS + (STATION_PATTERN,):
        pids = _pgrep(pattern)
        if not pids:
            continue
        stopped.append(pattern)
        subprocess.run(["pkill", "-f", pattern], capture_output=True)
    if stopped:
        if not quiet:
            say("stop", "stopping: %s" % ", ".join(stopped))
        time.sleep(2)
        # PX4's lock files live here; leaving them behind reproduces the
        # same "already running" error the kill was meant to prevent. Same
        # glob as tools/start_world.sh, so both clean up identically.
        for stale in glob.glob("/tmp/px4*"):
            if os.path.isdir(stale):
                shutil.rmtree(stale, ignore_errors=True)
            else:
                try:
                    os.remove(stale)
                except OSError:
                    pass
    elif not quiet:
        say("stop", "nothing was running")
    return stopped


# ---------------------------------------------------------------- start

def _install_repo_world(entry):
    """flat_test lives in this repo, not PX4's tree, so PX4 cannot resolve
    PX4_GZ_WORLD for it until it is copied across."""
    source = os.path.join(REPO, "sim", "worlds", entry["world"] + ".sdf")
    target = os.path.join(PX4_DIR, "Tools", "simulation", "gz", "worlds",
                          entry["world"] + ".sdf")
    if os.path.isfile(source) and not os.path.isfile(target):
        shutil.copy(source, target)
        return True
    return False


def check_prerequisites(entry):
    """Everything that would otherwise fail halfway through, checked up front
    so the message names the real problem."""
    problems = []
    if not os.path.isdir(PX4_DIR):
        problems.append("PX4 is not at %s" % PX4_DIR)
        return problems                       # nothing below can be true
    worlds = os.path.join(PX4_DIR, "Tools", "simulation", "gz", "worlds")
    repo_world = os.path.join(REPO, "sim", "worlds", entry["world"] + ".sdf")
    if not os.path.isfile(os.path.join(worlds, entry["world"] + ".sdf")) \
            and not os.path.isfile(repo_world):
        problems.append("world file %s.sdf is in neither %s nor this repo"
                        % (entry["world"], worlds))
    if not shutil.which("make"):
        problems.append("'make' is not installed")
    return problems


# Whether Gazebo shows its own window. PX4's SITL makefile reads HEADLESS
# from the environment and starts `gz sim -s` - the SERVER only - when it
# is 1. The physics still runs and the camera sensors still render, because
# gz-sim's sensors system builds its own rendering scene in the server
# process rather than borrowing the GUI's. So the console's nose and chase
# feeds work exactly as before; what disappears is the Gazebo window.
#
# Why that is worth having: on a two-screen training setup the Gazebo
# window is one more thing to find, move and accidentally close, and the
# console already shows the aircraft from two angles. It also gives back
# the GPU time the GUI was spending drawing a view nobody was watching.
#
# Set UAS_SHOW_GAZEBO=1 to get the window back - it is still the right
# place to go when something looks wrong with the world itself.
def gazebo_is_hidden():
    return os.environ.get("UAS_SHOW_GAZEBO", "0") != "1"


def start_simulator(entry):
    """Launch PX4 + Gazebo detached, with this world's own spawn height."""
    os.makedirs(LOG_DIR, exist_ok=True)
    env = dict(os.environ)
    if gazebo_is_hidden():
        env["HEADLESS"] = "1"
    # Each world's ground sits at a different height, so one spawn pose cannot
    # serve them: a sea-level spawn in Hoggar buries the aircraft, and
    # Hoggar's 605 m spawn over Black Rock drops it from 600 m.
    env["PX4_GZ_MODEL_POSE"] = "0,0,%s,0,0,0" % entry["spawn_z"]
    env["PX4_GZ_WORLD"] = entry["world"]

    # STDIN MUST NEVER REACH END-OF-FILE. This used to be
    # subprocess.DEVNULL, and /dev/null gives end-of-file on the first
    # read. PX4's own shell - the pxh> prompt - treats that as "the line
    # ended", prints a fresh prompt and reads again, for ever. Measured on
    # 13 Oct 2026: ~/uas_sim_logs/sim_launch.log had reached 19.5 GB, and
    # sampled anywhere in the middle it was nothing but the escape sequence
    # that clears the line followed by "pxh> ", with no newlines at all.
    #
    # tools/start_world.sh never showed this because it runs in a terminal,
    # and a terminal's stdin BLOCKS rather than ending. So the fix is to
    # give the launcher's PX4 the same thing: a pipe whose write end is
    # held open, so a read waits instead of returning nothing.
    #
    # The write end is passed to the child rather than kept here on
    # purpose - this launcher exits once everything is up, and anything it
    # held would close with it and bring the prompt loop straight back.
    read_fd, write_fd = os.pipe()
    os.set_inheritable(write_fd, True)
    try:
        with open(SIM_LOG, "w") as log:
            return subprocess.Popen(
                ["make", "px4_sitl", "gz_standard_vtol"],
                cwd=PX4_DIR, env=env, stdout=log, stderr=subprocess.STDOUT,
                stdin=read_fd, pass_fds=(write_fd,), start_new_session=True)
    finally:
        # The child has its own copies of both ends now.
        os.close(read_fd)
        os.close(write_fd)


def wait_for_simulator(process, timeout=PX4_TIMEOUT_S):
    """Watch PX4's log until it is up, or has clearly failed.

    Returns (ok, detail). Reading the log rather than sleeping a fixed time is
    the difference between "it is ready" and "it has probably had long
    enough", and it is also what lets a build failure be reported as one.
    """
    deadline = time.monotonic() + timeout
    last_note = 0.0
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return False, "the simulator exited (see %s)" % SIM_LOG
        try:
            with open(SIM_LOG, errors="replace") as handle:
                text = handle.read()
        except OSError:
            text = ""
        if PX4_READY in text:
            return True, ""
        for marker in PX4_FAILED:
            if marker in text:
                return False, "the build failed: %r in %s" % (marker, SIM_LOG)
        waited = time.monotonic() - (deadline - timeout)
        if waited - last_note >= 15:
            last_note = waited
            say("sim", "still starting (%ds)... first build can take minutes"
                % int(waited))
        time.sleep(1)
    return False, "gave up after %ds (see %s)" % (timeout, SIM_LOG)


def start_station(entry):
    """Launch the instructor station, pointed at the same world."""
    os.makedirs(LOG_DIR, exist_ok=True)
    env = dict(os.environ)
    env["GCS_WORLD"] = entry["world"]
    with open(STATION_LOG, "w") as log:
        return subprocess.Popen(
            [sys.executable, os.path.join(REPO, "instructor_station.py")],
            cwd=REPO, env=env, stdout=log, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, start_new_session=True)


def wait_for_station(process, timeout=STATION_TIMEOUT_S):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            return False, "the station exited (see %s)" % STATION_LOG
        if _station_answering():
            return True, ""
        time.sleep(0.5)
    return False, "the station did not answer on port %d (see %s)" % (
        STATION_PORT, STATION_LOG)


def _gui_services_up():
    """True once Gazebo's GUI is advertising its camera services.

    The GUI comes up well after PX4 reports ready, and /gui/follow is served
    by the GUI process rather than the server, so asking too early fails
    silently - the call returns fine and nothing moves.
    """
    try:
        result = subprocess.run(["gz", "service", "-l"],
                                capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return "/gui/follow" in result.stdout


def point_camera_at_aircraft(timeout=CAMERA_TIMEOUT_S):
    """Start the Gazebo view already looking at the aircraft.

    Never fatal. A session with the camera in the wrong place is a session;
    a launcher that refuses to finish because a camera service was slow is
    not.
    """
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _gui_services_up():
            break
        time.sleep(1)
    else:
        return "the Gazebo window did not advertise its camera in %ds" % timeout

    try:
        import gazebo_view
    except Exception as exc:
        return "could not load the view helper (%s)" % exc
    message = gazebo_view.set_view(CAMERA_VIEW, CAMERA_DISTANCE_M)
    # set_view reports failure in its text rather than by raising, because
    # its usual caller is a button on a web page.
    return None if message.startswith("External view") else message


def open_front_end():
    """The station opens its own desktop window when pywebview is installed;
    opening a browser as well would just leave a duplicate on screen."""
    if importlib.util.find_spec("webview") is not None:
        return "its own window"
    try:
        subprocess.Popen(["xdg-open", STATION_URL],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        return "a browser"
    except OSError:
        return None


def tile_windows():
    """Side-by-side station and Gazebo. Never fatal: a launcher must not fail
    because a window could not be moved."""
    script = os.path.join(REPO, "tools", "tile_windows.sh")
    if not (os.path.isfile(script) and shutil.which("wmctrl")):
        return False
    try:
        subprocess.Popen(["bash", script], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
        return True
    except OSError:
        return False


# ---------------------------------------------------------------- main

def resolve_environment(key):
    """Which training area to start: the argument, else the one the station
    last used, else the default - the same order sim_target applies."""
    if key:
        entry = sim_target.BY_KEY.get(key)
        if entry is None:
            return None, "'%s' is not a known training area. Choose from: %s" % (
                key, ", ".join(sorted(sim_target.BY_KEY)))
        return entry, None
    entry = sim_target.BY_WORLD.get(sim_target.WORLD)
    if entry is None:
        return None, "the remembered world '%s' is not in the environment list" \
            % sim_target.WORLD
    return entry, None


def print_status():
    sim = simulator_running()
    station = _station_answering()
    print("Simulator (PX4 + Gazebo): %s" % ("running" if sim else "not running"))
    print("Instructor station:       %s" % (
        "running at " + STATION_URL if station else "not running"))
    print("Training area:            %s" % sim_target.WORLD)
    print("Logs:                     %s" % LOG_DIR)
    return 0 if (sim and station) else 1


def toggle(key, open_ui=True, ask=input):
    """One icon for the whole thing: start it, or offer to stop it.

    Added 13 Oct 2026, replacing the two desktop icons - one to start and
    one to stop - with a single UAV Academy GCS Pro.

    IT NEVER STOPS WITHOUT BEING ASKED. A click on a dead simulator starts
    it with no questions, which is the common case and should stay one
    click. A click on a RUNNING one asks first, because the old red icon
    stopped everything the instant it was touched, and with one icon a
    stray double-click would otherwise end an exercise in front of a
    class. Restarting is on the same menu because that is what the day
    actually consists of: changing training area.

    `ask` is a seam for tools/test_launcher.py. Nothing here reads a key
    unless the simulator is already up.
    """
    if not simulator_running() and not _station_answering():
        return launch(key, open_ui=open_ui)

    print("The simulator is already running.")
    print_status()
    print()
    print("  1  stop it")
    print("  2  restart it (same training area, or name another below)")
    print("  3  leave it alone")
    try:
        choice = ask("\nWhich? [3] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        choice = ""

    if choice in ("1", "stop"):
        stop_all()
        return 0
    if choice in ("2", "restart"):
        stop_all()
        return launch(key, open_ui=open_ui)
    print("Left running.")
    return 0


def launch(key, open_ui=True):
    entry, problem = resolve_environment(key)
    if problem:
        print(problem, file=sys.stderr)
        return 2

    say("1/6", "training area: %s" % entry["label"])
    problems = check_prerequisites(entry)
    if problems:
        for item in problems:
            print("  cannot start - %s" % item, file=sys.stderr)
        return 2
    if _install_repo_world(entry):
        say("1/6", "installed %s.sdf into PX4's worlds" % entry["world"])

    cleared = stop_all(quiet=True)
    say("2/6", "stopped what was already running: %s" % ", ".join(cleared)
                if cleared else "nothing left running to clear")

    say("3/6", "starting PX4 and Gazebo (spawn height %s m)" % entry["spawn_z"])
    sim = start_simulator(entry)
    ok, detail = wait_for_simulator(sim)
    if not ok:
        print("  simulator did not start - %s" % detail, file=sys.stderr)
        _tail(SIM_LOG)
        return 1
    say("3/6", "simulator up")

    say("4/6", "starting the instructor station")
    if _station_answering():
        say("4/6", "a station is already running - reusing it")
        station = None
    else:
        station = start_station(entry)
    ok, detail = wait_for_station(station)
    if not ok:
        print("  station did not start - %s" % detail, file=sys.stderr)
        _tail(STATION_LOG)
        print("\n  The simulator is still running. Stop it with:"
              "\n    python3 %s --stop" % os.path.abspath(__file__),
              file=sys.stderr)
        return 1

    say("5/6", "pointing the Gazebo camera at the aircraft")
    problem = point_camera_at_aircraft()
    if problem:
        say("5/6", "camera left where it was - %s" % problem)
        say("5/6", "use Set External View in the console's Camera panel")
    else:
        say("5/6", "camera following the aircraft from behind and above")

    say("6/6", "ready")
    where = open_front_end() if open_ui else None
    if where:
        print("\n  Console opening in %s: %s" % (where, STATION_URL))
    else:
        print("\n  Console: %s" % STATION_URL)
    if tile_windows():
        print("  Tiling the station and Gazebo side by side.")
    print("  Logs: %s and %s" % (SIM_LOG, STATION_LOG))
    print("\n  To stop everything:  python3 %s --stop"
          % os.path.abspath(__file__))
    # The separate "Stop" icon was named here until 13 Oct 2026, when the
    # two icons merged into one. Telling an instructor to use an icon that
    # is no longer on the desktop is worse than saying nothing.
    print("  (or the X at the top right of the console, which asks first,")
    print("   or the UAV Academy GCS Pro icon again)")
    return 0


def _tail(path, lines=20):
    try:
        with open(path, errors="replace") as handle:
            tail = handle.read().splitlines()[-lines:]
    except OSError:
        return
    if tail:
        print("\n  last %d lines of %s:" % (len(tail), path), file=sys.stderr)
        for line in tail:
            print("    " + line, file=sys.stderr)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Start the simulator and the instructor station together.")
    parser.add_argument("world", nargs="?",
                        help="training area key (%s)"
                             % ", ".join(sorted(sim_target.BY_KEY)))
    parser.add_argument("--stop", action="store_true",
                        help="stop the simulator and the station")
    parser.add_argument("--toggle", action="store_true",
                        help="what the desktop icon does: start it if it is "
                             "not running, otherwise ask whether to stop or "
                             "restart it")
    parser.add_argument("--status", action="store_true",
                        help="report what is running")
    parser.add_argument("--no-browser", action="store_true",
                        help="start everything but do not open the console")
    parser.add_argument("--hold", action="store_true",
                        help="wait for Enter before exiting (used by the "
                             "desktop icon so the window stays readable)")
    args = parser.parse_args(argv)

    if sum((args.stop, args.status, args.toggle)) > 1:
        parser.error("--stop, --status and --toggle do different things; "
                     "pick one")

    if args.status:
        code = print_status()
    elif args.stop:
        stop_all()
        code = 0
    elif args.toggle:
        code = toggle(args.world, open_ui=not args.no_browser)
    else:
        code = launch(args.world, open_ui=not args.no_browser)

    if args.hold:
        try:
            input("\nPress Enter to close this window. "
                  "The simulator keeps running.\n")
        except (EOFError, KeyboardInterrupt):
            pass
    return code


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
