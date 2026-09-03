"""
GPS failure toggle. This uses the GPS dropout proxy already built and
confirmed working earlier in this project (~/instructor_panel/gps_dropout_proxy.py).
This plugin just starts/stops that existing, proven tool - it doesn't
reimplement it, to avoid duplicating a working solution.
"""

from simulator_link import start_background_script, stop_background_script, mark_failure_injected, mark_failure_cleared

PROXY_PATH = "/home/uas-sim/instructor_panel/gps_dropout_proxy.py"

state = {"active": False}


def toggle_gps_failure():
    if state["active"]:
        msg = stop_background_script("gps_proxy")
        state["active"] = False
        mark_failure_cleared("gps")
        return f"GPS failure cleared. ({msg})"
    else:
        msg = start_background_script("gps_proxy", ["python3", PROXY_PATH, "fail"])
        state["active"] = True
        mark_failure_injected("gps")
        return f"GPS failure injected. ({msg})"


PLUGIN = {
    "id": "gps_failure", "label": "Toggle GPS Failure", "category": "Failure Injection",
    "style": "warning", "handler": toggle_gps_failure,
}
