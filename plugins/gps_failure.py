"""
GPS failure toggle. This uses the GPS dropout proxy already built and
confirmed working earlier in this project. This plugin just starts/stops
that existing, proven tool - it doesn't reimplement it, to avoid
duplicating a working solution.

PATH UPDATED 5 Sep 2026: instructor_panel (the standalone prototype this
proxy script came from) was archived to
~/UAS-Academy/Archive/instructor_panel/ during a home-directory cleanup -
it's superseded by gcs_app but gps_dropout_proxy.py itself is still the
live, in-use tool, just relocated. Update PROXY_PATH again if it moves.
"""

from simulator_link import start_background_script, stop_background_script, mark_failure_injected, mark_failure_cleared
import os

PROXY_PATH = os.path.expanduser("~/UAS-Academy/Archive/instructor_panel/gps_dropout_proxy.py")

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
