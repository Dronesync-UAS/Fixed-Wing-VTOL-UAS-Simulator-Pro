#!/usr/bin/env python3
"""
Is everything built today actually installed on THIS machine?

    python3 tools/verify_install.py

Nothing here needs PX4 or Gazebo running. It answers one question - is the
machine in the state the work assumed - and for anything that is not, it
prints the single command that fixes it.

WHAT IT CHECKS, and in which of the two places things live:

  IN THE REPOSITORY (git pull brings these)
    the modules and plugins added today, the world files' ground extent,
    the eleven offline checks, the .gitignore entries.

  OUTSIDE THE REPOSITORY (a tool has to be run, once, per machine)
    the aircraft model under ~/PX4-Autopilot - its legs, its gimbal, its
    chase boom; the downloaded satellite imagery; the Mapbox token file.

That split is the whole point of this script. A git pull cannot put legs
on the aircraft, and every time someone has been surprised by something
missing, it has been something in the second group.

WHAT IT CANNOT CHECK. Whether any of it LOOKS right. The gimbal could be
installed and pointing at the sky; the imagery could be the wrong place;
a widened world could have a visible seam at the horizon. Those need
Gazebo running and a pair of eyes - tools/verify_live.py covers the half
of that which a script can see.

The token is never printed, only its presence and its permissions.
"""

import glob
import json
import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AIRCRAFT = os.path.expanduser(
    "~/PX4-Autopilot/Tools/simulation/gz/models/standard_vtol/model.sdf")
SATELLITE = os.path.join(REPO, "sim", "worlds", "satellite")
TOKEN_FILE = os.path.expanduser("~/.mapbox_token")

GREEN, RED, AMBER, OFF = "\033[32m", "\033[31m", "\033[33m", "\033[0m"
if not sys.stdout.isatty():
    GREEN = RED = AMBER = OFF = ""

problems = []       # (what is wrong, the command that fixes it)


def ok(label, extra=""):
    print("  %sOK  %s %s%s" % (GREEN, OFF, label, ("  " + extra) if extra else ""))


def bad(label, fix, extra=""):
    print("  %sNO  %s %s%s" % (RED, OFF, label, ("  " + extra) if extra else ""))
    problems.append((label, fix))


def note(label, extra=""):
    print("  %s--  %s %s%s" % (AMBER, OFF, label, ("  " + extra) if extra else ""))


def heading(text):
    print("\n" + text)
    print("-" * len(text))


# ---------------------------------------------------------------------------
heading("1. This machine")

print("  python %s" % sys.version.split()[0])
if sys.version_info < (3, 8):
    bad("Python is older than 3.8", "ask - nothing here was written for it")
else:
    ok("Python version")

try:
    import PIL
    ok("Pillow (image library)", "version %s" % PIL.__version__)
except ImportError:
    bad("Pillow is not installed - the imagery fetcher needs it",
        "pip3 install --user Pillow")

for tool, what in (("gz", "Gazebo's command line"),
                   ("ffmpeg", "video recording of the payload feed")):
    found = subprocess.run(["which", tool], capture_output=True, text=True)
    if found.returncode == 0:
        ok("%s found" % what, found.stdout.strip())
    elif tool == "gz":
        bad("%s not found" % what,
            "nothing here can be verified live without it - check your "
            "Gazebo Harmonic install")
    else:
        note("%s not found - photos still work, recordings will not be "
             "turned into a video file" % what)

# ---------------------------------------------------------------------------
heading("2. In the repository - today's modules and controls")

EXPECTED_FILES = [
    ("range_profile.py", "the two operating envelopes"),
    ("plugins/operating_envelope.py", "the control that picks between them"),
    ("motor_sound.py", "the motor sound"),
    ("gimbal.py", "the payload gimbal's pointing"),
    ("flight_log.py", "the flight recorder"),
    ("payload_media.py", "photos and recordings"),
    ("scenery.py", "what is in each training area"),
    ("tools/far_ground_apply.py", "widens a world's visible ground"),
    ("tools/gimbal_apply.py", "puts the gimbal on the aircraft"),
    ("tools/aircraft_legs_apply.py", "puts the legs on the aircraft"),
    ("tools/chase_angles_apply.py", "puts the chase boom on the aircraft"),
    ("tools/fetch_satellite.py", "downloads the imagery"),
    ("tools/test_range_profile.py", "checks the envelopes"),
]
missing = [name for name, _ in EXPECTED_FILES
           if not os.path.isfile(os.path.join(REPO, name))]
for name, what in EXPECTED_FILES:
    if name not in missing:
        ok(name, what)
for name in missing:
    bad("%s is missing" % name,
        "git pull origin claude/pensive-lamport-af8mkq")

# The two names that must never collide - a plugin called range_profile.py
# importing a module called range_profile.py is a circular import.
if os.path.isfile(os.path.join(REPO, "plugins", "range_profile.py")):
    bad("plugins/range_profile.py exists and will shadow range_profile.py",
        "rm plugins/range_profile.py")
else:
    ok("no module-name clash between the plugin and the envelopes")

for line in ("satellite/", "*.sdf.prefarground"):
    with open(os.path.join(REPO, ".gitignore")) as handle:
        present = line in handle.read()
    if present:
        ok(".gitignore covers %s" % line)
    else:
        bad(".gitignore does not cover %s" % line,
            "git pull origin claude/pensive-lamport-af8mkq")

# ---------------------------------------------------------------------------
heading("3. The training worlds - here, and where Gazebo loads them")

PLANE_SIZE = re.compile(
    r"<plane>\s*(?:<normal>[^<]*</normal>\s*)?<size>\s*"
    r"([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*</size>")
GROUND_BOX = re.compile(
    r'<collision name="ground_collision">.*?<box>\s*<size>\s*'
    r'([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*</size>', re.DOTALL)

worlds = sorted(glob.glob(os.path.join(REPO, "sim", "worlds", "*.sdf")))
if not worlds:
    bad("no world files found at all",
        "git pull origin claude/pensive-lamport-af8mkq")

unparsed, narrow = [], []
plane_worlds, heightmap_worlds = [], []
for path in worlds:
    name = os.path.basename(path)
    try:
        ET.parse(path)
    except ET.ParseError:
        unparsed.append(name)
        continue
    text = open(path).read()
    if "<heightmap>" in text:
        heightmap_worlds.append(name)
        continue
    plane_worlds.append(name)
    plane = PLANE_SIZE.search(text)
    box = GROUND_BOX.search(text)
    if not plane or float(plane.group(1)) < 200000:
        narrow.append(name)
    elif not box or float(box.group(1)) < 200000:
        narrow.append(name + " (collision)")

if unparsed:
    bad("these world files do not parse: %s" % ", ".join(unparsed),
        "git checkout sim/worlds   (this throws away local edits to them)")
else:
    ok("all %d world files parse" % len(worlds))

if narrow:
    bad("the visible ground still ends at 4 km in: %s" % ", ".join(narrow),
        "python3 tools/far_ground_apply.py --all")
else:
    ok("all %d plane worlds reach 110 km from home" % len(plane_worlds))

# THE WORLDS THAT ACTUALLY LOAD are the copies in PX4's tree, not these.
# Checking only the repository was this script's own blind spot on the day
# it was written: it reported every world healthy while six of them were
# not installed at all and could not be flown.
sys.path.insert(0, os.path.join(REPO, "tools"))
try:
    import install_worlds as iw
except Exception as exc:                  # noqa: BLE001
    iw = None
    bad("could not load tools/install_worlds.py (%s)" % exc,
        "git pull origin claude/pensive-lamport-af8mkq")

if iw is not None:
    if not os.path.isdir(iw.PX4_WORLDS):
        bad("PX4's own worlds folder is not there, so no world can load",
            "check PX4-Autopilot is at ~/PX4-Autopilot")
    else:
        not_installed, out_of_date, px4_newer = [], [], []
        for path in iw.repo_worlds():
            name = os.path.basename(path)
            how = iw.state(path, os.path.join(iw.PX4_WORLDS, name))
            if how == "new":
                not_installed.append(name)
            elif how == "older":
                out_of_date.append(name)
            elif how == "newer":
                px4_newer.append(name)
        if not_installed:
            bad("%d world(s) are not installed where Gazebo loads them, so "
                "they cannot be flown: %s"
                % (len(not_installed), ", ".join(not_installed)),
                "python3 tools/install_worlds.py")
        if out_of_date:
            bad("%d installed world(s) are older than this repository's, so "
                "today's edits are not in what loads: %s"
                % (len(out_of_date), ", ".join(out_of_date)),
                "python3 tools/install_worlds.py")
        if px4_newer:
            bad("%d installed world(s) are NEWER than this repository's - "
                "something edited them in PX4's tree: %s"
                % (len(px4_newer), ", ".join(px4_newer)),
                "python3 tools/install_worlds.py --list   (read it before "
                "overwriting anything)")
        if not (not_installed or out_of_date or px4_newer):
            ok("every world is installed where Gazebo loads it, and identical")

        missing_media = [m for m in iw.media_needed()
                         if not os.path.isfile(os.path.join(iw.PX4_MEDIA, m))]
        if missing_media:
            bad("%d heightmap/texture file(s) a world needs are not installed "
                "- that world loads as an empty void: %s"
                % (len(missing_media), ", ".join(missing_media)),
                "python3 tools/install_worlds.py")
        else:
            ok("every heightmap and texture the worlds need is installed")

note("%d worlds stand on a heightmap and were left that way on purpose "
     "- long flights need one of the plane worlds" % len(heightmap_worlds),
     ", ".join(w.replace(".sdf", "") for w in heightmap_worlds))

# ---------------------------------------------------------------------------
heading("4. Outside the repository - the aircraft model")

if not os.path.isfile(AIRCRAFT):
    bad("the aircraft model is not where it was expected",
        "there is nothing to run; check PX4-Autopilot is at ~/PX4-Autopilot")
    model_text = ""
else:
    model_text = open(AIRCRAFT).read()
    ok("found", AIRCRAFT)

MODEL_PARTS = [
    ("gimbal_yaw_link", "the payload gimbal",
     "python3 tools/gimbal_apply.py"),
    ("payload_camera", "the payload camera",
     "python3 tools/gimbal_apply.py"),
    ("payload_lrf", "the laser rangefinder",
     "python3 tools/gimbal_apply.py"),
    ("leg_front_left_tube", "the four legs",
     "python3 tools/aircraft_legs_apply.py"),
    ("chase_az_link", "the chase boom, which gives the four chase angles",
     "python3 tools/chase_angles_apply.py"),
]
if model_text:
    for marker, what, fix in MODEL_PARTS:
        if marker in model_text:
            ok(what)
        else:
            bad("%s is not on the aircraft" % what, fix)

# ---------------------------------------------------------------------------
heading("5. Outside the repository - the satellite imagery")

sys.path.insert(0, REPO)
try:
    import sim_target
    environments = sim_target.ENVIRONMENTS
except Exception as exc:              # noqa: BLE001
    environments = []
    bad("could not read the environment list (%s)" % exc,
        "git pull origin claude/pensive-lamport-af8mkq")

if not os.path.isdir(SATELLITE):
    note("no imagery downloaded yet - the plan view falls back to shaded "
         "relief, which needs no internet")
    note("to download it: python3 tools/fetch_satellite.py --all "
         "--provider mapbox")
else:
    for env in environments:
        image = os.path.join(SATELLITE, env["world"] + ".png")
        meta = os.path.join(SATELLITE, env["world"] + ".json")
        if not os.path.isfile(image):
            note("%-11s no imagery" % env["key"])
            continue
        size_kb = os.path.getsize(image) / 1024
        extent, mpp = "?", "-"
        try:
            with open(meta) as handle:
                m = json.load(handle)
            extent = "%.0f km" % m.get("extent_km",
                                       (m["east_max"] - m["east_min"]) / 1000.0)
            # Fetched before 12 Oct 2026, when the sidecar started
            # carrying the resolution. Not a fault.
            mpp = ("%.0f m/px" % m["metres_per_pixel"]
                   if "metres_per_pixel" in m else "-")
        except (OSError, ValueError, KeyError):
            bad("%s imagery has no readable sidecar, so the plan view cannot "
                "place it" % env["key"],
                "python3 tools/fetch_satellite.py %s --provider mapbox"
                % env["key"])
            continue
        # A nearly-empty PNG is usually a provider returning blank tiles -
        # worth saying, not worth failing: Uyuni really is a white salt flat.
        flag = "  (very small - check it is not blank)" if size_kb < 60 else ""
        ok("%-11s %-7s %-9s %5.0f KB%s"
           % (env["key"], extent, mpp, size_kb, flag))

if os.path.isfile(TOKEN_FILE):
    mode = os.stat(TOKEN_FILE).st_mode & 0o777
    if mode & 0o077:
        bad("the Mapbox token file is readable by other users (mode %s)"
            % oct(mode), "chmod 600 ~/.mapbox_token")
    else:
        ok("Mapbox token file present and owner-only", oct(mode))
else:
    note("no ~/.mapbox_token - only needed to download more imagery")

# ---------------------------------------------------------------------------
heading("6. The offline checks")

CHECKS = ["offline_render_check", "test_console_browser", "test_flight_display",
          "test_night_ops", "test_sound_and_gear", "test_payload",
          "test_flight_log", "test_scenery", "test_terrain_fetch",
          "test_recovery", "test_range_profile", "test_install_worlds"]

for name in CHECKS:
    path = os.path.join(REPO, "tools", name + ".py")
    if not os.path.isfile(path):
        bad("%s.py is missing" % name,
            "git pull origin claude/pensive-lamport-af8mkq")
        continue
    done = subprocess.run([sys.executable, path], cwd=REPO,
                          capture_output=True, text=True)
    if done.returncode == 0:
        ok(name)
    else:
        tail = (done.stdout + done.stderr).strip().splitlines()
        bad("%s FAILED" % name, "python3 tools/%s.py   (read what it says)"
            % name, "last line: " + (tail[-1] if tail else "no output"))

# ---------------------------------------------------------------------------
print("\n" + "=" * 68)
if not problems:
    print("Everything this script can check is in place.")
    print()
    print("What it could NOT check: whether any of it LOOKS right in")
    print("Gazebo. Start PX4, Gazebo and the station, then run:")
    print()
    print("    python3 tools/verify_live.py")
    sys.exit(0)

print("%d thing(s) need doing. In order:" % len(problems))
for i, (what, fix) in enumerate(problems, 1):
    print("\n  %d. %s" % (i, what))
    print("     %s" % fix)
print()
print("Run each command on its own, at the $ shell, and wait for it to")
print("finish before the next one. Then run this script again.")
sys.exit(1)
