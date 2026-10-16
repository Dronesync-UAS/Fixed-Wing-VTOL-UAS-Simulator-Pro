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

THE SKY MOVES WITH IT, since 12 Oct 2026. The worlds now carry a painted
sky dome (tools/sky_dome_apply.py) whose image is an emissive map, so the
sun does not touch it and it would stay bright blue at midnight. Gazebo
will recolour a named visual while the world runs - gz-sim8
src/systems/user_commands/UserCommands.cc line 636 subscribes
/world/NAME/material_color, and VisualCommand::Execute looks the entity up
by scoped name - so each time of day also dims the dome. That is what
makes the night sky dark rather than blue.

WHAT STILL CANNOT CHANGE. The scene's AMBIENT light is not a light and not
a visual, so nothing here reaches it; it is fixed when the world loads, at
0.26 0.28 0.32. So night is a dark sky and a weak moon over ground that
still carries a quarter of its daylight bounce. It looks like deep dusk at
ground level.

Said plainly because it matters for what the night exercise is worth: a
student flying this is flying in poor light, not in the dark.

THE DIM IS FIRE-AND-FORGET. material_color is a topic, not a service, so
Gazebo sends back no answer and this plugin cannot tell you whether the
dome was found. A world without a dome logs a warning in the Gazebo
window and is otherwise unharmed.
"""
import subprocess

from sim_target import service, world_topic
from simulator_link import log_instructor_action

SUN_LIGHT_NAME = "sun"

# The dome from tools/sky_dome_apply.py. A scoped visual name is what
# gz-sim8's entitiesFromScopedName() wants; model::link::visual is
# unambiguous even if another world ever has a visual called the same.
SKY_VISUAL = "sky_dome::sky_dome_link::sky_dome_visual"

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
        "sky": (1.00, 1.00, 1.00),
    },
    "afternoon": {
        "label": "Late afternoon",
        "diffuse": (1.0, 0.89, 0.72),
        "specular": (0.30, 0.27, 0.22),
        "direction": (-0.80, 0.22, -0.30),
        "sky": (1.00, 0.93, 0.84),
    },
    "dusk": {
        "label": "Dusk",
        "diffuse": (0.62, 0.42, 0.30),
        "specular": (0.12, 0.10, 0.09),
        "direction": (-0.95, 0.10, -0.08),
        "sky": (0.42, 0.33, 0.34),
    },
    "night": {
        "label": "Night",
        # A cold, weak light low in the sky: moonlight, near enough for a
        # training exercise. Not darkness - see the note at the top.
        "diffuse": (0.10, 0.12, 0.20),
        "specular": (0.03, 0.03, 0.05),
        "direction": (-0.40, -0.70, -0.25),
        "sky": (0.07, 0.08, 0.14),
    },
}

state = {"when": "day"}


def set_sky(tint):
    """Dim the painted sky dome to match the sun. Returns a note, or ""."""
    r, g, b = tint
    request = (f"entity: {{name: '{SKY_VISUAL}', type: VISUAL}}, "
               f"ambient: {{r: 0, g: 0, b: 0, a: 1}}, "
               f"diffuse: {{r: 0, g: 0, b: 0, a: 1}}, "
               f"specular: {{r: 0, g: 0, b: 0, a: 1}}, "
               f"emissive: {{r: {r}, g: {g}, b: {b}, a: 1}}")
    try:
        subprocess.run(
            ["gz", "topic", "-t", world_topic("material_color"),
             "-m", "gz.msgs.MaterialColor", "-p", request],
            check=False, timeout=6, capture_output=True, text=True)
    except (OSError, subprocess.SubprocessError) as exc:
        return f"  The sky was left as it was ({exc})."
    return ""


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
    sky_note = set_sky(setting["sky"])
    extra = ("  The sky dims with it, but the ground keeps the world's fixed "
             "ambient light: this is deep dusk at ground level, not darkness."
             if state["when"] == "night" else "")
    return f"Lighting set to {setting['label']}.{extra}{sky_note}"


PLUGIN = {
    "id": "time_of_day",
    "label": "Set lighting",
    "category": "Simulation Control",
    "style": "normal",
    # A setting, not an action: it applies the moment its value
    # changes rather than waiting for its own button.
    "apply_on_change": True,
    "inputs": [{"name": "when", "label": "Time of day", "type": "select",
                "default": "day",
                "options": [{"value": key, "label": TIMES[key]["label"]}
                            for key in ("day", "afternoon", "dusk", "night")]}],
    "handler": set_time,
}
