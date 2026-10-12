"""
COUNTER-UAS ENCOUNTER - what it feels like from inside the aircraft.

Added 12 Oct 2026 on request.

WHAT THIS IS, AND WHAT IT IS NOT

It is a scenario that makes the aircraft behave as it would if it flew
into the effect of a counter-UAS system: the satellites go, or the command
link goes, or both, in a realistic order, and the student has to notice
and do something about it.

It is NOT a model of counter-UAS equipment. Nothing here simulates radio
frequencies, detection ranges, effector types or anything else about the
system doing it. There is no transmitter, nothing is emitted, and nothing
in this file would help anyone build or operate one. It drives the same
three failure injections the station already had - PX4's own
MAV_CMD_INJECT_FAILURE for the links, and the GPS proxy for the
satellites - and the only thing it adds is the ORDER and the TIMING, which
is the part that makes it a scenario rather than a switch.

That is the right scope for a flight training device. A remote pilot
cannot do anything about the equipment; what they can do is recognise the
symptoms, know what their own aircraft will do about them, and fly it. UK
operators are also required to report the encounter afterwards, which is
why this writes a clearly labelled line into the assessment record.

THE PROFILES, and what each is teaching

  gnss        The satellites degrade and the position fix is lost. The
              aircraft falls back to whatever it can hold without GNSS.
              The lesson is recognising it from the console - the
              satellite count and the arming readout both move - before
              the aircraft starts drifting.

  c2          The command link goes. The lesson is PX4's own data-link
              failsafe, and the student's hands coming off.

  layered     GNSS first, then the command link a few seconds later. This
              is the realistic one: the aircraft is already coping with a
              degraded position when it loses the link as well, and the
              two failsafes interact.

  rf_denial   Both links at once, and the RC with them. Everything
              manual-control-shaped is gone. This is the worst case and
              the one a student should meet last.

WHAT IT WILL NOT DO. It does not disarm, terminate, or take the aircraft
away from the student. An encounter is something to fly out of, and the
instructor keeps every control they had - including CLEAR, which puts
everything back.

NOT YET FLOWN.
"""
import time

import plugin_loader
from simulator_link import (log_instructor_action, say_step, sequence_running,
                            start_sequence, telemetry, wait_until)

# Which of the station's existing injections each profile uses, and when.
# (seconds from the start, plugin id, what the student should see)
PROFILES = {
    "gnss": {
        "label": "GNSS denial",
        "steps": [(0.0, "gps_failure", "satellites dropping")],
    },
    "c2": {
        "label": "C2 link denial",
        "steps": [(0.0, "data_link_loss", "command link lost")],
    },
    "layered": {
        "label": "Layered - GNSS then C2",
        "steps": [(0.0, "gps_failure", "satellites dropping"),
                  (8.0, "data_link_loss", "command link lost as well")],
    },
    "rf_denial": {
        "label": "Full RF denial",
        "steps": [(0.0, "gps_failure", "satellites dropping"),
                  (3.0, "rc_signal_loss", "manual control link lost"),
                  (6.0, "data_link_loss", "command link lost")],
    },
}

state = {"active": False, "profile": None}


def _plugin(plugin_id):
    for entry in plugin_loader.LOADED:
        if entry.get("id") == plugin_id:
            return entry
    return None


def _is_on(plugin_id):
    entry = _plugin(plugin_id)
    module_state = getattr(entry.get("_module"), "state", None) if entry else None
    return bool(module_state and module_state.get("active"))


def _press(plugin_id, want_on):
    """Toggle an injection to the state we want, through its own handler -
    so there is one code path for injecting a failure, not two that can
    drift apart."""
    entry = _plugin(plugin_id)
    if entry is None:
        return f"{plugin_id} is not loaded"
    if _is_on(plugin_id) == want_on:
        return None
    try:
        entry["handler"]()
    except Exception as exc:                                # noqa: BLE001
        return f"{plugin_id} ({exc})"
    return None


def _clear_all():
    problems = []
    for profile in PROFILES.values():
        for _, plugin_id, _ in profile["steps"]:
            problem = _press(plugin_id, False)
            if problem:
                problems.append(problem)
    return problems


def cuas_encounter(profile="gnss", action="start"):
    if str(action) == "clear" or state["active"]:
        problems = _clear_all()
        state["active"] = False
        was = state["profile"]
        state["profile"] = None
        say_step(None)
        log_instructor_action("cuas_encounter", f"cleared profile={was}")
        if problems:
            return "Encounter cleared, except: " + ", ".join(problems)
        return ("Counter-UAS encounter cleared - every link restored. "
                "Logged as the end of the encounter.")

    chosen = PROFILES.get(str(profile).lower())
    if chosen is None:
        return f"Not sent - '{profile}' is not one of {', '.join(PROFILES)}."
    if not telemetry.get("armed"):
        return ("Not sent - the aircraft is disarmed. An encounter is "
                "something to fly out of; start it in flight.")
    if sequence_running():
        return "Not sent - a manoeuvre is already running."

    steps = []
    start = time.monotonic()

    def make_step(delay, plugin_id, what):
        def run():
            wait_until(lambda: time.monotonic() - start >= delay, delay + 1)
            say_step(f"Counter-UAS encounter: {what}")
            problem = _press(plugin_id, True)
            if problem:
                return f"Encounter stopped - could not inject {problem}."
            log_instructor_action(
                "cuas_effect",
                f"profile={profile} effect={plugin_id} at_s={delay:g} "
                f"alt_m={telemetry.get('altitude_m')} "
                f"mode={telemetry.get('mode')}")
            return None
        return run

    for delay, plugin_id, what in chosen["steps"]:
        steps.append(make_step(delay, plugin_id, what))

    def finish():
        say_step("Counter-UAS encounter running - press CLEAR to end it")
        return None

    steps.append(finish)
    if not start_sequence("cuas_encounter", steps):
        return "Not sent - a manoeuvre is already running."

    state["active"] = True
    state["profile"] = str(profile).lower()
    log_instructor_action(
        "cuas_encounter",
        f"started profile={state['profile']} "
        f"alt_m={telemetry.get('altitude_m')} mode={telemetry.get('mode')}")
    return (f"Counter-UAS encounter: {chosen['label']}. "
            f"{len(chosen['steps'])} effect(s) over "
            f"{chosen['steps'][-1][0]:.0f} s. Press this again to clear it. "
            "This simulates what the aircraft experiences - it models no "
            "equipment and emits nothing.")


PLUGIN = {
    "id": "cuas_encounter",
    "label": "C-UAS encounter",
    "category": "Failure Injection",
    "style": "warning",
    "inputs": [{"name": "profile", "label": "Encounter", "type": "select",
                "default": "gnss",
                "options": [{"value": key, "label": PROFILES[key]["label"]}
                            for key in ("gnss", "c2", "layered", "rf_denial")]}],
    "handler": cuas_encounter,
}
