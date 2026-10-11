"""Read-only survey of how this machine's Gazebo Harmonic setup loads world
systems, run before adding wind injection to the training world:

    python3 tools/wind_survey.py

Why this exists: gz-sim8 only loads its default world systems when the world
SDF itself declares none ("No systems loaded from SDF, loading defaults" in
SimulationRunner.cc). PX4 supplies its own default set - physics, IMU, NavSat,
magnetometer, airspeed, sensors - through a server.config. So dropping a
WindEffects <plugin> into a world file that currently has none would silently
suppress every one of those. Which file the plugin belongs in depends on
where the defaults actually come from on this machine, and that varies with
the Tools/simulation/gz submodule pin. This script finds out.

It CHANGES NOTHING. It writes a report to ~/wind_survey.txt and prints it.
"""
import os, re, subprocess, glob

PX4 = os.path.expanduser("~/PX4-Autopilot")
WORLDS = os.path.join(PX4, "Tools/simulation/gz/worlds")
WORLD = os.path.join(WORLDS, "training_area.sdf")
REPORT = os.path.expanduser("~/wind_survey.txt")

out = []


def say(line=""):
    out.append(str(line))


def run(cmd):
    """Best-effort shell capture - a missing tool is an answer, not an error."""
    try:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=120)
        return (r.stdout + r.stderr).strip() or "(no output)"
    except Exception as exc:
        return f"(failed: {exc})"


def show_file(path, limit=200):
    say(f"--- {path}")
    if not os.path.exists(path):
        say("    MISSING")
        return
    try:
        with open(path, errors="replace") as fh:
            lines = fh.read().splitlines()
    except Exception as exc:
        say(f"    unreadable: {exc}")
        return
    say(f"    ({len(lines)} lines)")
    for i, line in enumerate(lines[:limit], 1):
        say(f"    {i:4}: {line}")
    if len(lines) > limit:
        say(f"    ... {len(lines) - limit} more lines not shown")


say("=== 1. paths ===")
say(f"~/PX4-Autopilot          -> {os.path.realpath(PX4)}")
say(f"symlink?                 -> {os.path.islink(PX4)}")
say(f"worlds dir exists        -> {os.path.isdir(WORLDS)}")
say(f"training_area.sdf exists -> {os.path.isfile(WORLD)}")

say()
say("=== 2. training_area.sdf: systems and wind ===")
if os.path.isfile(WORLD):
    with open(WORLD, errors="replace") as fh:
        world_lines = fh.read().splitlines()
    say(f"total lines: {len(world_lines)}")
    for i, line in enumerate(world_lines, 1):
        if re.search(r"<plugin|filename=|<wind>|</world>|<world name|<spherical|<magnetic|<atmosphere", line):
            say(f"  {i:4}: {line.strip()}")
    plugin_count = sum(1 for l in world_lines if "<plugin" in l)
    say(f"plugin elements in world: {plugin_count}")
    say("VERDICT: " + ("world declares its own systems - WindEffects can go here"
                       if plugin_count else
                       "world declares NO systems - adding one here would suppress the defaults"))
else:
    say("world file not found - nothing else in this section is meaningful")

say()
say("=== 3. where do the default systems come from? ===")
say(f"GZ_SIM_SERVER_CONFIG_PATH = {os.environ.get('GZ_SIM_SERVER_CONFIG_PATH', '(not set in this shell)')}")
say("server.config files found:")
found = []
for root, dirs, files in os.walk(PX4, followlinks=True):
    # the PX4 tree is ~23GB; the config lives shallow, so stop early
    if root.count(os.sep) - PX4.count(os.sep) > 4:
        dirs[:] = []
        continue
    dirs[:] = [d for d in dirs if d not in (".git", "build", "node_modules")]
    if "server.config" in files:
        found.append(os.path.join(root, "server.config"))
for path in sorted(set(found)) + sorted(glob.glob("/usr/share/gz/gz-sim*/server.config")):
    say(f"  {path}")
if not found:
    say("  none under ~/PX4-Autopilot (searched 4 levels deep)")

say()
for path in sorted(set(found)):
    show_file(path)

say()
say("=== 4. launcher script ===")
show_file(os.path.join(PX4, "start_training_area.sh"))

say()
say("=== 5. gazebo + wind plugin availability ===")
say(f"gz --versions   -> {run('gz sim --versions 2>/dev/null || gz --version')}")
say(f"wind .so on disk -> {run('ls /usr/lib/*/gz-sim-8/plugins/*wind* 2>/dev/null; ls /usr/lib/*/gz-sim8/plugins/*wind* 2>/dev/null')}")

say()
say("=== 6. is the gz submodule tracked by git? ===")
say(run(f"git -C {PX4} status --short -- Tools/simulation/gz 2>&1 | head -5"))
say(run(f"git -C {PX4}/Tools/simulation/gz log --oneline -1 2>&1"))

say()
say("=== 7. other training_area variants ===")
for path in sorted(glob.glob(os.path.join(WORLDS, "training_area*.sdf"))):
    with open(path, errors="replace") as fh:
        text = fh.read()
    say(f"  {os.path.basename(path)}: plugins={text.count('<plugin')} wind={'<wind>' in text}")

say()
say("=== 8. leftover files from the earlier mis-paste (not deleted) ===")
junk = ["wind", "plugin", "horizontal", "magnitude", "sin", "noise", "direction",
        "vertical", "linear_velocity", "time_for_rise", "amplitude_percent",
        "period", "amplitude", "mean", "stddev", "force_approximation_scaling_factor"]
hits = [n for n in junk if os.path.exists(os.path.expanduser(f"~/{n}"))]
say("  " + (", ".join(hits) if hits else "none found"))

text = "\n".join(out)
with open(REPORT, "w") as fh:
    fh.write(text + "\n")
print(text)
print()
print(f"[saved to {REPORT}]")
