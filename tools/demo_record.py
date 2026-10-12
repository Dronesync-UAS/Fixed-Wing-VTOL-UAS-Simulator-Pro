#!/usr/bin/env python3
"""
Record a scripted demonstration of the station, for showing to someone.

    python3 tools/demo_record.py --list
    python3 tools/demo_record.py short
    python3 tools/demo_record.py full

WHAT IT DOES. Starts ffmpeg recording the screen, then drives the
station over its own HTTP interface on a timeline, then stops recording
and tells you where the file is. The flying is scripted so the same
demonstration comes out the same way twice - which is the whole point of
showing it to somebody who is only going to see it once.

WHAT IT CANNOT DO. Switch which view is on the main screen, or press the
payload buttons. Those live in the browser, and the station has no way
to reach into the page. So the script PRINTS THE CUES, with a countdown,
and you click along. They are few and they are spaced out.

RUN ORDER, each in its own window:

    1. PX4 and Gazebo               tools/start_world.sh coast
    2. the station                  GCS_WORLD=training_area_coast python3 instructor_station.py
    3. the console in a browser, full screen
    4. this script

ABOUT SIXTY SECONDS. "short" is 60 s and assumes the aircraft is already
hovering, because a departure alone eats most of a minute: climb to the
transition height, transition, accelerate. "full" is 150 s and flies the
whole thing from disarmed. If you have one minute, use "short" and have
the aircraft hovering before you start.

NOT RUN ANYWHERE. This script has never been executed - there is no
display, no Gazebo and no station on the machine it was written on. The
ffmpeg command line and the station's endpoints are both read from
things that do work, but the first run of this is yours.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request

STATION = "http://localhost:8080"
OUT_DIR = os.path.join(os.path.expanduser("~/uas_sim_logs"), "demo")


def station(path):
    try:
        with urllib.request.urlopen(STATION + path, timeout=8) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError) as exc:
        return "LOCAL ERROR: %s" % exc


def action(plugin, **params):
    qs = "&".join("%s=%s" % (k, v) for k, v in params.items())
    return station("/action/%s%s" % (plugin, ("?" + qs) if qs else ""))


def payload(what, **params):
    """The gimbal's own endpoints are /payload_<what>, NOT /action/... -
    they are not plugins. Getting that wrong was the first thing this
    script did and it answered 404 cheerfully."""
    qs = "&".join("%s=%s" % (k, v) for k, v in params.items())
    return station("/payload_%s%s" % (what, ("?" + qs) if qs else ""))


def telemetry():
    raw = station("/telemetry")
    try:
        return json.loads(raw)
    except ValueError:
        return {}


# Each step: (at what second, what to do, what to say on screen)
#   do is either ("action", plugin, params) or ("cue", text) or
#   ("wait_for", key, value) - a cue is something for you to click.
SHORT = [
    (0, ("cue", "Make sure the CHASE view is on the main screen"),
     "Chase view, aircraft hovering"),
    (2, ("action", "aircraft_lights", {}), "Navigation lights on"),
    (6, ("action", "time_of_day", {"when": "dusk"}), "Dusk"),
    (12, ("cue", "Click PAYLOAD in the top bar"), "The sensor operator's screen"),
    (16, ("payload", "centre", {}), "Gimbal centred"),
    (20, ("cue", "Drag in the picture, then roll the wheel to zoom"),
     "Slew and zoom"),
    (28, ("cue", "Click CHASE, then the LEFT angle button"),
     "Four external angles"),
    (34, ("action", "loiter", {"radius_m": 150, "speed_ms": 8}),
     "Orbiting, nose-first"),
    (44, ("cue", "Open Settings and show the Mission tab"),
     "Mission planning"),
    (50, ("action", "mission_plan", {"pattern": "survey", "altitude_m": 100,
                                     "size_m": 400, "action": "plan"}),
     "A 400 m survey planned - read the figures"),
    (58, ("cue", "Stop"), "Done"),
]

FULL = [
    (0, ("cue", "CHASE view on the main screen, aircraft disarmed"),
     "On the ground"),
    (3, ("action", "arm", {}), "ARM - propellers spin up"),
    (8, ("action", "aircraft_lights", {}), "Navigation lights and strobes"),
    (13, ("action", "takeoff", {"altitude_m": 20}), "Vertical takeoff"),
    (30, ("wait_for", "altitude_m", 18), "Climbing to 20 m"),
    (34, ("action", "forward_flight", {"transition_m": 40, "cruise_m": 100}),
     "Transition to fixed wing - wings level, then accelerate"),
    (75, ("cue", "Click PAYLOAD in the top bar"), "The sensor screen"),
    (80, ("payload", "lase", {}), "Laser rangefinder"),
    (88, ("cue", "Drag to slew, wheel to zoom, TRACK then click a target"),
     "Target tracking"),
    (100, ("cue", "Click CHASE and run through the angle buttons"),
     "Four external angles"),
    (110, ("action", "loiter", {"radius_m": 150, "speed_ms": 16}),
     "Orbit, nose-first"),
    (125, ("cue", "Settings, Mission tab"), "Mission planning"),
    (130, ("action", "mission_plan", {"pattern": "survey", "altitude_m": 100,
                                      "size_m": 600, "action": "plan"}),
     "A 600 m survey - spacing and photo count worked out"),
    (140, ("action", "rtl", {}), "Return to launch"),
    (148, ("cue", "Stop"), "Done"),
]

SCRIPTS = {"short": (SHORT, 60), "full": (FULL, 150)}


def check_ready(want_airborne):
    problems = []
    if not shutil.which("ffmpeg"):
        problems.append("ffmpeg is not installed - sudo apt install -y ffmpeg")
    if not os.environ.get("DISPLAY"):
        problems.append("DISPLAY is not set - this has to run on the desktop, "
                        "not over a plain ssh session")
    t = telemetry()
    if not t:
        problems.append("the station is not answering on %s - start it first"
                        % STATION)
    elif want_airborne and not t.get("armed"):
        problems.append("the 'short' demo expects the aircraft already "
                        "hovering. Arm and take off first, or use 'full'")
    return problems


def start_ffmpeg(path, seconds):
    size = os.environ.get("GCS_DEMO_SIZE", "1920x1080")
    # x11grab of the whole screen. 25 fps and a fast preset: this is a
    # screen recording to show somebody, not a master.
    command = ["ffmpeg", "-y", "-f", "x11grab", "-framerate", "25",
               "-video_size", size, "-i", os.environ["DISPLAY"],
               "-t", str(seconds + 3),
               "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p",
               "-crf", "23", path]
    return subprocess.Popen(command, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def main():
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("script", nargs="?", default="short",
                        choices=sorted(SCRIPTS))
    parser.add_argument("--list", action="store_true",
                        help="print the running order and stop")
    parser.add_argument("--dry-run", action="store_true",
                        help="walk the timeline without recording, so the "
                             "cues can be rehearsed")
    args = parser.parse_args()

    steps, seconds = SCRIPTS[args.script]

    if args.list:
        print("%s - %d seconds\n" % (args.script, seconds))
        for at, what, caption in steps:
            kind = what[0]
            doing = {"cue": "CLICK: " + what[1],
                     "action": "station: " + what[1],
                     "payload": "gimbal: " + what[1],
                     "wait_for": "wait for " + what[1]}[kind]
            print("  %3ds  %-46s %s" % (at, doing, caption))
        print("\nAnything marked CLICK is for you - the station cannot "
              "reach into the browser.")
        return 0

    problems = check_ready(args.script == "short" and not args.dry_run)
    if problems and not args.dry_run:
        print("Not ready:\n")
        for p in problems:
            print("  - " + p)
        return 1

    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, time.strftime("demo_%Y%m%d_%H%M%S.mp4"))

    print("\n%s demo, %d seconds." % (args.script.title(), seconds))
    print("Put the console on screen, full screen, and do not move the "
          "mouse except when told.\n")
    for n in (5, 4, 3, 2, 1):
        print("  starting in %d..." % n)
        time.sleep(1)

    recorder = None
    if not args.dry_run:
        recorder = start_ffmpeg(path, seconds)
        print("  RECORDING\n")

    began = time.monotonic()
    for at, what, caption in steps:
        while time.monotonic() - began < at:
            time.sleep(0.05)
        now = int(time.monotonic() - began)
        kind = what[0]
        if kind == "cue":
            print("  %3ds  >>> %s <<<   (%s)" % (now, what[1], caption))
        elif kind == "wait_for":
            key, value = what[1], what[2]
            print("  %3ds  waiting for %s >= %s   (%s)"
                  % (now, key, value, caption))
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline:
                if (telemetry().get(key) or 0) >= value:
                    break
                time.sleep(0.5)
        elif kind == "payload":
            said = payload(what[1], **what[2])
            print("  %3ds  gimbal %-15s %s" % (now, what[1], said.strip()[:70]))
            print("        (%s)" % caption)
        else:
            said = action(what[1], **what[2])
            print("  %3ds  %-22s %s" % (now, what[1], said.strip()[:80]))
            print("        (%s)" % caption)

    while time.monotonic() - began < seconds:
        time.sleep(0.2)

    if recorder is not None:
        print("\n  finishing the recording...")
        recorder.wait(timeout=30)
        size_mb = (os.path.getsize(path) / 1e6) if os.path.isfile(path) else 0
        print("\nSaved %s  (%.1f MB)" % (path, size_mb))
        print("\nPlay it before you show it to anybody.")
    else:
        print("\nDry run - nothing recorded.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
