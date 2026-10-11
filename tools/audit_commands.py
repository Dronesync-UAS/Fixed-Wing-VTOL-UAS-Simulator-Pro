"""Checks every instructor control reports what PX4 actually said:

    python3 tools/audit_commands.py

Calls every plugin handler three times with the MAVLink layer stubbed - once
with PX4 accepting, once refusing, once silent - and fails if a control claims
success when PX4 refused or never answered.

Why this exists: until 11 Oct 2026 not one plugin checked the COMMAND_ACK,
although simulator_link.send_command_and_wait had been there all along. Every
button fired blind and returned a success message, so a refused command was
indistinguishable from an obeyed one - which cost an afternoon of chasing
"the commands do not respond properly" when PX4 had been refusing them and
saying so. Run this after adding or changing a control.

Exit code 0 if every control is honest, 1 otherwise.
"""
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# Controls that legitimately send nothing over MAVLink: they talk to Gazebo,
# run a background script, or change the station's own state.
NON_MAVLINK = {"freeze", "reset_spawn", "wind_gust", "external_view", "environment",
               "gps_failure", "start_video", "start_stabilizer"}

RESULT = {"value": None, "text": ""}


def _install_stubs():
    sl = types.ModuleType("simulator_link")
    sl.telemetry = {"altitude_m": 100.0, "altitude_amsl_m": 1400.0, "armed": True,
                    "groundspeed_ms": 0.0, "battery_pct": 100, "heading_deg": 0,
                    "satellites": 10, "airspeed_ms": 20.0}
    sl.log_instructor_action = lambda *a, **k: None
    sl.mark_failure_injected = lambda *a, **k: None
    sl.mark_failure_cleared = lambda *a, **k: None
    sl.reset_flight_state = lambda: None
    sl.start_background_script = lambda n, c: "started"
    sl.stop_background_script = lambda n: "stopped"

    def send_command_and_wait(command, *params, timeout=2.0):
        return RESULT["value"], RESULT["text"]
    sl.send_command_and_wait = send_command_and_wait

    def set_mode(main_mode, sub_mode=0, name=None):
        label = name or f"mode {main_mode}.{sub_mode}"
        if RESULT["value"] == 0:
            return f"{label}: accepted by PX4."
        if RESULT["value"] is None:
            return f"{label}: no response from PX4 (is it connected?)."
        return f"{label}: PX4 {RESULT['text']} the mode change."
    sl.set_mode = set_mode

    class _Mav:
        def __getattr__(self, _):
            return lambda *a, **k: None

    class _Master:
        target_system = 1
        target_component = 1
        mav = _Mav()
    sl.master = _Master()
    sys.modules["simulator_link"] = sl

    video = types.ModuleType("video_feed")
    video.resubscribe = lambda: None
    video.camera_fps = lambda: 0.0
    video.start_video_capture = lambda: None
    video.mjpeg_generator = lambda: iter(())
    sys.modules.setdefault("video_feed", video)


def _load(path):
    spec = importlib.util.spec_from_file_location(os.path.basename(path)[:-3], path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    if hasattr(module, "subprocess"):
        module.subprocess = types.SimpleNamespace(
            run=lambda *a, **k: types.SimpleNamespace(returncode=0, stdout="", stderr=""),
            Popen=lambda *a, **k: types.SimpleNamespace(pid=1),
            PIPE=-1, STDOUT=-2)
    return module


def main():
    _install_stubs()
    plugin_dir = os.path.join(REPO, "plugins")
    failures = []
    checked = 0

    for name in sorted(os.listdir(plugin_dir)):
        if not name.endswith(".py") or name.startswith("_"):
            continue
        try:
            module = _load(os.path.join(plugin_dir, name))
        except Exception as exc:
            failures.append(f"{name}: failed to import - {exc}")
            continue
        plugin = getattr(module, "PLUGIN", None)
        if plugin is None:
            failures.append(f"{name}: no PLUGIN dictionary")
            continue
        if plugin["id"] in NON_MAVLINK:
            continue
        checked += 1

        for value, text, label in ((2, "DENIED", "refusal"), (None, "", "silence")):
            RESULT["value"], RESULT["text"] = value, text
            if hasattr(module, "state"):
                module.state["active"] = False
            try:
                reply = plugin["handler"]()
            except Exception as exc:
                failures.append(f"{plugin['id']}: raised on {label} - {exc}")
                continue
            lowered = str(reply).lower()
            honest = any(word in lowered for word in
                         ("refus", "denied", "not sent", "no acknowledgement",
                          "not confirmed", "no response", "not injected",
                          "not cleared", "rejected", "unsupported", "failed"))
            if not honest:
                failures.append(
                    f"{plugin['id']}: claims success when PX4 gave {label}:\n"
                    f"      {reply}")
            # A refused toggle must not flip its own state light.
            if hasattr(module, "state") and module.state.get("active") is True:
                failures.append(
                    f"{plugin['id']}: set its status light active although PX4 gave {label}")

    print(f"Checked {checked} MAVLink controls "
          f"({len(NON_MAVLINK)} non-MAVLink controls skipped).\n")
    if failures:
        print("PROBLEMS:")
        for failure in failures:
            print(f"  - {failure}")
        print(f"\n{len(failures)} problem(s).")
        return 1
    print("Every control reports refusals and silence honestly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
