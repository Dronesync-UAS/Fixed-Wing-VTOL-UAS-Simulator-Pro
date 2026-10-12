"""
DAY / NIGHT - move the sun, without restarting the world.

Added 12 Oct 2026 for night operations training.

HOW, and why this way. Gazebo advertises a service for changing a light
while the world runs - gz-sim8 src/systems/user_commands/UserCommands.cc
line 619:

    this->dataPtr->AdvertiseService<LightCommand, msgs::Light>(
        "/world/" + validWorldName + "/light_config", "Light configuration");

and LightCommand::Execute finds the light BY NAME. Every world in this
project names its directional light "sun", so the same call works on all
of them. Editing the world file and restarting would also work and would
take a minute and a half; this takes a second, which is the difference
between "let's try it at dusk" being a thing an instructor does and a
thing an instructor plans.

WHAT IT CANNOT CHANGE. The scene's ambient light and its sky are not
lights, so they are not reachable through this service - they are fixed
when the world loads. Night here is therefore a very low, very warm sun
rather than true darkness: the sky stays as it was and the ground keeps
the ambient bounce the world file gave it. It looks like deep dusk. For
genuine darkness the world file has to change and Gazebo has to restart,
which tools/realistic_scene.py can do.

Said plainly because it matters for what the night exercise is worth: a
student flying this is flying in poor light, not in the dark.
"""
import subprocess

from sim_target import service
from simulator_link import log_instructor_action

SUN_LIGHT_NAME = "sun"

# Each setting: the sun's colour, how hard it strikes, and from where.
# The directions are elevation-and-bearing worked into a unit vector; the
# numbers are chosen to look right rather than to match an almanac, and
# this file does not pretend otherwise.
TIMES = {
    "day": {
        "label": "Midday",
        "diffuse": (1.0, 0.97, 0.90),
        "specular": (0.35, 0.35, 0.33),
        "direction": (-0.55, 0.35, -0.62),
    },
    "afternoon": {
        "label": "Late afternoon",
        "diffuse": (1.0, 0.89, 0.72),
        "specular": (0.30, 0.27, 0.22),
        "direction": (-0.80, 0.22, -0.30),
    },
    "dusk": {
        "label": "Dusk",
        "diffuse": (0.62, 0.42, 0.30),
        "specular": (0.12, 0.10, 0.09),
        "direction": (-0.95, 0.10, -0.08),
    },
    "night": {
        "label": "Night",
        # A cold, weak light low in the sky: moonlight, near enough for a
        # training exercise. Not darkness - see the note at the top.
        "diffuse": (0.10, 0.12, 0.20),
        "specular": (0.03, 0.03, 0.05),
        "direction": (-0.40, -0.70, -0.25),
    },
}

state = {"when": "day"}


def set_time(when="day"):
    setting = TIMES.get(str(when).lower())
    if setting is None:
        return f"Not sent - '{when}' is not one of {', '.join(TIMES)}."

    d, sp, dr = setting["diffuse"], setting["specular"], setting["direction"]
    request = (
        f"name: '{SUN_LIGHT_NAME}', type: DIRECTIONAL, "
        f"diffuse: {{r: {d[0]}, g: {d[1]}, b: {d[2]}, a: 1}}, "
        f"specular: {{r: {sp[0]}, g: {sp[1]}, b: {sp[2]}, a: 1}}, "
        f"direction: {{x: {dr[0]}, y: {dr[1]}, z: {dr[2]}}}")
    try:
        done = subprocess.run(
            ["gz", "service", "-s", service("light_config"),
             "--reqtype", "gz.msgs.Light", "--reptype", "gz.msgs.Boolean",
             "--timeout", "3000", "--req", request],
            check=False, timeout=8, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"Could not reach Gazebo - {exc}."

    output = (done.stdout or "") + (done.stderr or "")
    if "false" in output.lower() or done.returncode != 0:
        return (f"Gazebo refused the light change ({output.strip()[:120]}). "
                f"Check the world's directional light is named "
                f"'{SUN_LIGHT_NAME}'.")

    state["when"] = str(when).lower()
    log_instructor_action("time_of_day", f"when={state['when']}")
    extra = ("  Night here is deep dusk, not darkness: the sky and the "
             "ambient light belong to the world file and cannot be changed "
             "while it runs."
             if state["when"] == "night" else "")
    return f"Lighting set to {setting['label']}.{extra}"


PLUGIN = {
    "id": "time_of_day",
    "label": "Set lighting",
    "category": "Simulation Control",
    "style": "normal",
    "inputs": [{"name": "when", "label": "Time of day", "type": "select",
                "default": "day",
                "options": [{"value": key, "label": TIMES[key]["label"]}
                            for key in ("day", "afternoon", "dusk", "night")]}],
    "handler": set_time,
}
