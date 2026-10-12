"""
MISSION - plan a survey, corridor, orbit or perimeter, upload it, fly it.

Added 12 Oct 2026 on request, in the style of QGroundControl's Plan
view. The patterns and the arithmetic are in mission.py; the upload is
in mission_upload.py; this file is the control.

WHAT AN INSTRUCTOR SETS, and what is worked out for them:

  SET:       the pattern, the area or radius, the height, the pattern's
             bearing, and whether to fly it on the wing.
  WORKED OUT: line spacing and camera trigger distance, from the
             camera's field of view, the height and the overlap figures.
             Those are the numbers students get wrong by hand, and
             getting them wrong means a survey with gaps in it that
             nobody notices until the photographs are processed.

PLAN FIRST, UPLOAD SECOND, START THIRD. Three presses, not one. A
mission that uploads and launches on a single click is a mission nobody
has read, and the figures it reports - how far, how long, how many
frames - are there to be read before the aircraft moves.

NOT FLOWN. The patterns are checked arithmetically in
tools/test_mission.py; nothing has been uploaded to a running PX4.
"""
import mission
import mission_upload
from simulator_link import log_instructor_action, telemetry

# What was last planned, so UPLOAD and START have something to act on
# and the instructor is not asked to describe it three times.
planned = {"items": None, "summary": None, "what": None}


def _here():
    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None:
        return None, None
    return lat, lon


def mission_plan(pattern="survey", altitude_m=100, size_m=400,
                 bearing_deg=0, radius_m=150, fixed_wing="1",
                 action="plan"):
    try:
        alt = float(altitude_m)
        size = float(size_m)
        bearing = float(bearing_deg)
        radius = float(radius_m)
    except (TypeError, ValueError):
        return "Not planned - one of those figures is not a number."

    wing = str(fixed_wing).lower() in ("1", "true", "on", "yes")
    act = str(action).lower()

    if act == "upload":
        if not planned["items"]:
            return "Nothing to upload - plan a mission first."
        ok, said = mission_upload.upload(planned["items"])
        return said

    if act == "start":
        if not planned["items"]:
            return "Nothing to start - plan and upload a mission first."
        ok, said = mission_upload.start()
        return said

    # Planning.
    lat, lon = _here()
    if lat is None:
        return ("Not planned - no position from the aircraft yet. The "
                "pattern is built around where it is now.")
    if pattern not in mission.PATTERNS:
        return "Not planned - '%s' is not one of %s." % (
            pattern, ", ".join(mission.PATTERNS))
    if pattern == "corridor":
        return ("Corridor scans need a path drawn on the map, which the "
                "console cannot do yet. Survey, orbit and perimeter work "
                "from here.")
    if pattern == "waypoints":
        return ("Waypoint missions need points picked on the map, which the "
                "console cannot do yet. Survey, orbit and perimeter work "
                "from here.")

    try:
        items, summary = mission.build(
            pattern, lat, lon, alt,
            width_m=size, height_m=size * 0.75, angle_deg=bearing,
            radius_m=radius, turns=2, fixed_wing=wing)
    except ValueError as exc:
        return "Not planned - %s." % exc

    planned["items"] = items
    planned["summary"] = summary
    planned["what"] = pattern
    log_instructor_action(
        "mission_plan",
        "pattern=%s alt=%g size=%g bearing=%g waypoints=%d"
        % (pattern, alt, size, bearing, summary["waypoints"]))

    return ("%s planned: %d waypoints, %d m of track, about %.1f minutes, "
            "%d photographs. Lines %.0f m apart, camera every %.0f m at "
            "%g m. %s  Press UPLOAD to send it, then START to fly it."
            % (pattern.title(), summary["waypoints"], summary["distance_m"],
               summary["minutes"], summary["photos"],
               summary["line_spacing_m"], summary["trigger_every_m"],
               summary["altitude_m"], summary["estimate_note"]))


PLUGIN = {
    "id": "mission_plan",
    "label": "Plan / upload / start",
    "category": "Simulation Control",
    "style": "normal",
    "inputs": [
        {"name": "pattern", "label": "Pattern", "type": "select",
         "default": "survey",
         "options": [{"value": "survey", "label": "Survey (lawnmower)"},
                     {"value": "orbit", "label": "Orbit a target"},
                     {"value": "perimeter", "label": "Perimeter / boundary"}]},
        {"name": "altitude_m", "label": "Height (m)", "default": 100,
         "min": 20, "max": 2750, "step": 10},
        {"name": "size_m", "label": "Area across (m)", "default": 400,
         "min": 50, "max": 5000, "step": 50},
        {"name": "bearing_deg", "label": "Lines on (deg)", "default": 0,
         "min": 0, "max": 180, "step": 5},
        {"name": "radius_m", "label": "Orbit radius (m)", "default": 150,
         "min": 20, "max": 2000, "step": 10},
        {"name": "fixed_wing", "label": "Fly on the wing", "type": "select",
         "default": "1",
         "options": [{"value": "1", "label": "Yes - fixed wing"},
                     {"value": "0", "label": "No - multirotor"}]},
        {"name": "action", "label": "Then", "type": "select",
         "default": "plan",
         "options": [{"value": "plan", "label": "Plan it (shows the figures)"},
                     {"value": "upload", "label": "Upload the planned mission"},
                     {"value": "start", "label": "Start the uploaded mission"}]},
    ],
    "handler": mission_plan,
}
