#!/usr/bin/env python3
"""
With PX4, Gazebo and the station all running - is any of it actually
talking to anything?

    python3 tools/verify_live.py

Run it at the $ shell, in a fourth window, with the other three already
up. It changes nothing: it reads Gazebo's topic list and asks the station
the same questions the browser asks it.

START THEM IN THIS ORDER, each in its own window, waiting for each:

    1. PX4 and Gazebo together, the way you normally start them.
    2. python3 instructor_station.py
    3. this script.

WHAT IT CHECKS
  * Gazebo is up, and which world it has loaded.
  * The aircraft is in that world.
  * Each camera is publishing: nose, chase, payload. A camera that is
    installed but not publishing is the commonest failure here, and it
    looks identical to one that is not installed.
  * The rangefinder is publishing.
  * The gimbal's and the boom's joint controllers are listening.
  * The station answers on port 8080, has a MAVLink link to PX4, and its
    telemetry carries the operating envelope.

WHAT IT CANNOT CHECK. Whether the picture is right way up, whether the
gimbal points where the console says, whether the horizon looks right in
a widened world, whether the motor sound is convincing. Those need eyes.
The script says so at the end rather than letting a row of OKs imply
more than it means.
"""

import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

STATION = "http://localhost:8080"
GZ_TIMEOUT = 10

GREEN, RED, AMBER, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = AMBER = OFF = ""

problems = []


def ok(label, extra=""):
    print("  %sOK  %s %s%s" % (GREEN, OFF, label, ("  " + extra) if extra else ""))


def bad(label, fix):
    print("  %sNO  %s %s" % (RED, OFF, label))
    problems.append((label, fix))


def note(label):
    print("  %s--  %s %s" % (AMBER, OFF, label))


def heading(text):
    print("\n" + text)
    print("-" * len(text))


def gz(*args):
    """Run a gz command. Returns its output, or None if gz is not there or
    did not answer - which is itself the answer to "is Gazebo running"."""
    try:
        done = subprocess.run(["gz"] + list(args), capture_output=True,
                              text=True, timeout=GZ_TIMEOUT)
    except (OSError, subprocess.SubprocessError):
        return None
    return done.stdout if done.returncode == 0 else None


def station(path):
    try:
        with urllib.request.urlopen(STATION + path, timeout=5) as response:
            return response.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None


# ---------------------------------------------------------------------------
heading("1. Gazebo")

topics = gz("topic", "-l")
if topics is None:
    bad("Gazebo is not answering - no topic list",
        "start PX4 and Gazebo the way you normally do, then run this again")
    print("\nNothing else can be checked without it. Stopping here.")
    sys.exit(1)

topic_list = [line.strip() for line in topics.splitlines() if line.strip()]
ok("Gazebo is up", "%d topics" % len(topic_list))

import sim_target                                            # noqa: E402

print("  the station is set to world %r, model %r"
      % (sim_target.WORLD, sim_target.MODEL))

worlds_seen = sorted({t.split("/")[2] for t in topic_list
                      if t.startswith("/world/") and len(t.split("/")) > 2})
if sim_target.WORLD in worlds_seen:
    ok("that world is the one Gazebo has loaded")
else:
    bad("Gazebo has %s loaded, the station expects %s"
        % (", ".join(worlds_seen) or "no world", sim_target.WORLD),
        "either restart Gazebo with the right world, or start the station "
        "with GCS_WORLD=%s python3 instructor_station.py"
        % (worlds_seen[0] if worlds_seen else "training_area"))

if any(("/model/%s/" % sim_target.MODEL) in t for t in topic_list):
    ok("the aircraft %s is in the world" % sim_target.MODEL)
else:
    bad("no topics for model %s - the aircraft is not in the world"
        % sim_target.MODEL,
        "check PX4 started with the standard_vtol airframe (SYS_AUTOSTART 4004)")

# ---------------------------------------------------------------------------
heading("2. The three cameras and the rangefinder")

CAMERAS = [
    ("nose (FPV)", [sim_target.camera_topic()], None),
    ("chase", sim_target.chase_camera_topics(),
     "python3 tools/chase_angles_apply.py   (then restart Gazebo)"),
    ("payload gimbal", [sim_target.gimbal_camera_topic()],
     "python3 tools/gimbal_apply.py   (then restart Gazebo)"),
]
for what, candidates, fix in CAMERAS:
    found = [t for t in candidates if t in topic_list]
    if found:
        ok("%s camera is publishing" % what, found[0])
    elif fix:
        bad("%s camera is not publishing" % what, fix)
    else:
        bad("%s camera is not publishing" % what,
            "this one ships with the aircraft - check PX4's model.sdf was "
            "not replaced by a PX4 update")

if "/uas/payload/lrf" in topic_list:
    ok("laser rangefinder is publishing", "/uas/payload/lrf")
else:
    bad("laser rangefinder is not publishing",
        "python3 tools/gimbal_apply.py   (then restart Gazebo)")

# ---------------------------------------------------------------------------
heading("3. The things the station steers")

# A JointPositionController SUBSCRIBES, so its topic appears in the list
# only once something has published to it. gz topic -i tells us whether
# anybody is listening, which is the question that matters.
JOINTS = [
    ("gimbal pan", sim_target.gimbal_joint_topic("gimbal_yaw_joint"),
     "python3 tools/gimbal_apply.py   (then restart Gazebo)"),
    ("gimbal tilt", sim_target.gimbal_joint_topic("gimbal_pitch_joint"),
     "python3 tools/gimbal_apply.py   (then restart Gazebo)"),
    ("chase boom bearing", sim_target.chase_boom_topic("chase_az_joint"),
     "python3 tools/chase_angles_apply.py   (then restart Gazebo)"),
    ("chase boom elevation", sim_target.chase_boom_topic("chase_el_joint"),
     "python3 tools/chase_angles_apply.py   (then restart Gazebo)"),
]
for what, topic, fix in JOINTS:
    info = gz("topic", "-i", "-t", topic)
    if info and "Subscribers" in info and info.count("gz.msgs.Double"):
        ok("%s controller is listening" % what, topic)
    elif topic in topic_list:
        note("%s topic exists but nothing is subscribed to it - the "
             "controller did not load" % what)
        problems.append(("%s controller did not load" % what, fix))
    else:
        bad("%s controller is not listening" % what, fix)

# ---------------------------------------------------------------------------
heading("4. The instructor station")

page = station("/")
if page is None:
    bad("nothing is answering on %s" % STATION,
        "python3 instructor_station.py   (in its own window, and leave it "
        "running)")
    print("\nNothing else can be checked without it. Stopping here.")
else:
    ok("the station is answering on port 8080",
       "%d KB page" % (len(page) // 1024) if len(page) >= 1024
       else "%d byte page - suspiciously small" % len(page))
    for marker, what in (('id="view-payload"', "the payload view"),
                         ('id="view-chase"', "the chase view"),
                         ('btn-operating_envelope', "the operating envelope control"),
                         ('gcsMotorDemand', "the motor sound")):
        if marker in page:
            ok("%s is on the page" % what)
        else:
            bad("%s is missing from the page" % what,
                "git pull origin claude/pensive-lamport-af8mkq   then "
                "restart the station")

    raw = station("/telemetry")
    telemetry = None
    if raw:
        try:
            telemetry = json.loads(raw)
        except ValueError:
            bad("the station's telemetry is not valid JSON",
                "look at the station's own window for an error")
    if telemetry is not None:
        limits = telemetry.get("limits") or {}
        if limits.get("range_m"):
            which = ("CAA 500 m" if limits["range_m"] <= 500
                     else "extended %.0f km" % (limits["range_m"] / 1000))
            ok("the operating envelope is being sent with telemetry", which)
        else:
            bad("telemetry carries no limits - the page will use whatever it "
                "was rendered with",
                "git pull origin claude/pensive-lamport-af8mkq   then "
                "restart the station")

        if telemetry.get("mode"):
            ok("PX4 is talking to the station", "mode %s" % telemetry["mode"])
        else:
            bad("the station has no MAVLink data from PX4",
                "check PX4 is running and its window shows a pxh> prompt")

        alt = telemetry.get("altitude_m")
        if alt is not None:
            ok("altitude is being read", "%.1f m" % alt)

    for path, what in (("/terrain_info", "the plan view's backdrop"),
                       ("/payload_status", "the payload panel"),
                       ("/chase_view", "the chase angle selector"),
                       ("/flight_log", "the flight log"),
                       ("/health", "the health readout")):
        answer = station(path)
        if answer is None:
            bad("%s does not answer (%s)" % (what, path),
                "git pull origin claude/pensive-lamport-af8mkq   then "
                "restart the station")
        else:
            ok("%s answers" % what, path)

    # Which backdrop is actually under the track - the question that gets
    # asked by squinting at a pale square otherwise.
    raw = station("/terrain_info")
    if raw:
        try:
            info = json.loads(raw)
            if info.get("available"):
                span = (info.get("east_max", 0) - info.get("east_min", 0)) / 1000.0
                ok("backdrop in use: %s, %.0f km across"
                   % (info.get("source", "?"), span))
            else:
                note("this world has no backdrop - the plan view draws the "
                     "track on plain background")
        except ValueError:
            pass

# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
if not problems:
    print("Everything a script can see is working.")
else:
    print("%d thing(s) need doing:" % len(problems))
    for i, (what, fix) in enumerate(problems, 1):
        print("\n  %d. %s" % (i, what))
        print("     %s" % fix)
    print()
    print("Run each command on its own, at the $ shell. Anything that says")
    print("'then restart Gazebo' means PX4 and Gazebo both have to be")
    print("stopped and started again before it takes effect.")

print("""
STILL NOT CHECKED - these need your eyes, not a script:

  * four legs and a gimbal pod visible under the belly
  * all lights off until you switch them on
  * propellers visibly spinning when ARMED, and the motor sound starting
  * the payload picture being the right way up, and the gimbal moving
    where the console says it should
  * LOITER flying nose-first round the circle, not crabbing
  * the chase view showing sky as well as ground, and the four angles
  * the horizon in a widened world (coast, airfield, estate, flood,
    forest, lowlands) past 4 km from home
""")
sys.exit(1 if problems else 0)
