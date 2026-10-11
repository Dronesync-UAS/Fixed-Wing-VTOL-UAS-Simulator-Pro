"""
External view of the aircraft in the Gazebo window - the "chase plane" view
an instructor needs to see what the student's aircraft is actually doing,
rather than only the nose camera.

Pick a viewpoint and a distance, press the button. The camera stays with the
aircraft as it flies, in the aircraft's own frame, so "rear and above" remains
behind the aircraft through a turn. "Manual" releases the camera for free
mouse look in the Gazebo window.

The mechanics, and why this drives the Gazebo window rather than adding a
panel to the station, are documented in gazebo_view.py.
"""

from gazebo_view import VIEW_LABELS, set_view
from simulator_link import log_instructor_action

DEFAULT_VIEW = "rear_above"
DEFAULT_DISTANCE_M = 20


def external_view(view=DEFAULT_VIEW, distance_m=DEFAULT_DISTANCE_M):
    message = set_view(view, distance_m)
    # Only log a view that was actually applied - set_view's failures all come
    # back starting with "View not changed".
    if not message.startswith("View not changed"):
        log_instructor_action("external_view", f"view={view}, distance_m={distance_m}")
    return message


PLUGIN = {
    "id": "external_view",
    "label": "Set External View",
    "category": "Camera",
    "style": "normal",
    "inputs": [
        {"name": "view", "label": "Viewpoint", "type": "select",
         "default": DEFAULT_VIEW,
         "options": [{"value": key, "label": VIEW_LABELS[key].capitalize()}
                     for key in ("rear_above", "top_down", "left_side",
                                 "right_side", "front", "manual")]},
        {"name": "distance_m", "label": "Distance (m)", "default": DEFAULT_DISTANCE_M,
         "min": 5, "step": 5},
    ],
    "handler": external_view,
}
