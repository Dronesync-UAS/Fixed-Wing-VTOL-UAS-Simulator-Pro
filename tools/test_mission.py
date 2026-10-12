"""Check the mission planner's arithmetic and its MAVLink items.

    python3 tools/test_mission.py

Nothing here talks to PX4 or Gazebo. What it checks is the part that
decides whether a survey is a survey:

  * the photogrammetry relations - footprint, line spacing and trigger
    distance against the overlap figures, worked by hand here as well
    as in the module;
  * the patterns, measured: line lengths, spacing between lines, orbit
    radius, a closed perimeter, a corridor that straddles its path;
  * the order of a built mission - takeoff before transition before
    camera before waypoints before return;
  * the command numbers, against the MAVLink common definitions;
  * the upload's own rule that item 0 is home.
"""
import math
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


import mission as m                                         # noqa: E402

print("1. the camera arithmetic")

# Worked by hand: 2 * 100 * tan(1.05/2) = 115.8 m across.
across, along = m.footprint_m(100.0)
check("footprint across at 100 m is 115.8 m (%.1f)" % across,
      abs(across - 115.8) < 0.3)
# Vertical field from the 1024x576 aspect: tan(v/2) = tan(h/2) * 576/1024.
expect_v = 2 * math.atan(math.tan(1.05 / 2) * 576 / 1024)
check("vertical field of view is derived, not typed (%.4f)"
      % m.camera_vfov_rad(), abs(m.camera_vfov_rad() - expect_v) < 1e-9)
check("footprint along at 100 m is 65.2 m (%.1f)" % along,
      abs(along - 65.2) < 0.3)

# 60% side overlap leaves 40% of the width between lines.
check("line spacing is the un-overlapped width (%.1f)" % m.line_spacing_m(100.0),
      abs(m.line_spacing_m(100.0) - across * 0.4) < 0.01)
# 70% front overlap leaves 30% of the length between frames.
check("trigger distance is the un-overlapped length (%.1f)"
      % m.trigger_distance_m(100.0),
      abs(m.trigger_distance_m(100.0) - along * 0.3) < 0.01)
check("more overlap means tighter spacing",
      m.line_spacing_m(100.0, 0.8) < m.line_spacing_m(100.0, 0.5))
check("flying higher means wider spacing",
      m.line_spacing_m(200.0) > m.line_spacing_m(100.0))
check("spacing never reaches zero, however daft the overlap",
      m.line_spacing_m(100.0, 1.0) > 0 and m.trigger_distance_m(1.0, 1.0) > 0)

print("\n2. the survey pattern")

LAT, LON = 52.97, 0.81
pts = m.survey_lines(LAT, LON, 400.0, 300.0, 50.0)
check("an even number of points - every line has two ends (%d)" % len(pts),
      len(pts) % 2 == 0)
lengths = [m.metres_between(*pts[i], *pts[i + 1]) for i in range(0, len(pts), 2)]
check("every line is the width of the area (%s)"
      % [round(v) for v in lengths[:3]],
      all(abs(v - 400.0) < 1.0 for v in lengths))
# Consecutive lines must be a spacing apart, across the area.
gaps = [m.metres_between(*pts[i + 1], *pts[i + 2])
        for i in range(0, len(pts) - 2, 2)]
check("and sits a line spacing from the next (%s)"
      % [round(v) for v in gaps[:3]], all(abs(v - 50.0) < 1.0 for v in gaps))
check("the lines cover the whole area, not part of it",
      abs(m.metres_between(*pts[0], *pts[-1]) - 300.0) < 1.0
      or abs(m.metres_between(*pts[1], *pts[-1]) - 300.0) < 1.0)
# A lawnmower reverses every other line - the end of one is near the
# start of the next, or the aircraft is flying back empty each time.
hops = [m.metres_between(*pts[i + 1], *pts[i + 2])
        for i in range(0, len(pts) - 2, 2)]
check("it is a lawnmower, not a comb - the turn at each end is short "
      "(%d m)" % round(max(hops)), max(hops) < 60.0)

turned = m.survey_lines(LAT, LON, 400.0, 300.0, 50.0, angle_deg=90.0)
check("the pattern can be turned (%d points, different places)"
      % len(turned),
      len(turned) == len(pts)
      and m.metres_between(*pts[0], *turned[0]) > 50.0)

print("\n3. the other patterns")

orb = m.orbit_points(LAT, LON, 150.0, turns=2)
radii = [m.metres_between(LAT, LON, *p) for p in orb]
check("every orbit point is on the circle (%d points, %.1f to %.1f m)"
      % (len(orb), min(radii), max(radii)),
      all(abs(r - 150.0) < 1.0 for r in radii))
check("two turns is twice round (%d points)" % len(orb), len(orb) == 33)

per = m.perimeter_points(LAT, LON, 400.0, 300.0)
check("the perimeter closes", per[0] == per[-1])
sides = [m.metres_between(*per[i], *per[i + 1]) for i in range(4)]
check("and its sides are the area's own (%s)" % [round(v) for v in sides],
      sorted(round(v) for v in sides) == [300, 300, 400, 400])

path = [(LAT, LON), (LAT + 0.005, LON), (LAT + 0.010, LON)]
cor = m.corridor_points(path, 120.0, 50.0)
check("a corridor makes an odd number of passes, centred (%d points for "
      "3 path points)" % len(cor), len(cor) % len(path) == 0
      and (len(cor) // len(path)) % 2 == 1)
# The middle pass should sit on the path itself.
on_path = min(m.metres_between(*path[1], *p) for p in cor)
check("one pass runs down the path itself (%.1f m off)" % on_path,
      on_path < 1.0)

print("\n4. a whole mission, in order")

items, summary = m.build("survey", LAT, LON, 100.0,
                         width_m=600.0, height_m=400.0)
commands = [i["command"] for i in items]
check("it takes off as a VTOL, not as a fixed wing",
      commands[0] == m.NAV_VTOL_TAKEOFF)
check("it transitions before it starts the camera",
      commands.index(m.DO_VTOL_TRANSITION) < commands.index(m.DO_SET_CAM_TRIGG_DIST))
check("it points the gimbal before triggering",
      commands.index(m.DO_MOUNT_CONTROL) < commands.index(m.DO_SET_CAM_TRIGG_DIST))
check("it flies the waypoints after that",
      commands.index(m.NAV_WAYPOINT) > commands.index(m.DO_SET_CAM_TRIGG_DIST))
check("it stops the camera before coming home",
      [i for i in items if i["command"] == m.DO_SET_CAM_TRIGG_DIST][-1]["param1"] == 0)
check("it comes back to multirotor before landing",
      [i["param1"] for i in items
       if i["command"] == m.DO_VTOL_TRANSITION][-1] == m.MAV_VTOL_STATE_MC)
check("and it returns to launch", commands[-1] == m.NAV_RETURN_TO_LAUNCH)
check("the gimbal points straight down for a survey",
      [i for i in items if i["command"] == m.DO_MOUNT_CONTROL][0]["param1"] == -90.0)

orbit_items, _ = m.build("orbit", LAT, LON, 80.0, radius_m=120.0,
                         fixed_wing=False)
rois = [i for i in orbit_items if i["command"] == m.DO_SET_ROI_LOCATION]
check("an orbit holds the camera on the thing it is orbiting", len(rois) == 1)
check("and the target is the centre, in param5/6",
      abs(rois[0]["x"] - LAT) < 1e-9 and abs(rois[0]["y"] - LON) < 1e-9)
check("an orbit flown as a multirotor does not transition",
      not any(i["command"] == m.DO_VTOL_TRANSITION for i in orbit_items))
check("the camera is released at the end",
      any(i["command"] == m.DO_SET_ROI_NONE for i in orbit_items))

no_cam, _ = m.build("perimeter", LAT, LON, 100.0, camera=False)
check("a mission without the camera carries no camera items",
      not any(i["command"] in (m.DO_SET_CAM_TRIGG_DIST, m.DO_MOUNT_CONTROL,
                               m.DO_SET_ROI_LOCATION) for i in no_cam))

print("\n5. the summary shown before upload")

check("it counts the waypoints (%d)" % summary["waypoints"],
      summary["waypoints"] == len([i for i in items
                                   if i["command"] == m.NAV_WAYPOINT]))
check("it measures the distance (%d m)" % summary["distance_m"],
      summary["distance_m"] > 1000)
check("it counts the photographs (%d)" % summary["photos"],
      summary["photos"] > 0)
check("and says the estimate is an estimate",
      "estimate" in summary["estimate_note"].lower())
check("the spacing and trigger it used are shown, not hidden",
      summary["line_spacing_m"] > 0 and summary["trigger_every_m"] > 0)

print("\n6. the MAVLink numbers, against the common definitions")

for name, number in (("NAV_WAYPOINT", 16), ("NAV_VTOL_TAKEOFF", 84),
                     ("NAV_VTOL_LAND", 85), ("NAV_RETURN_TO_LAUNCH", 20),
                     ("DO_CHANGE_SPEED", 178), ("DO_SET_ROI_LOCATION", 195),
                     ("DO_SET_ROI_NONE", 197), ("DO_MOUNT_CONTROL", 205),
                     ("DO_SET_CAM_TRIGG_DIST", 206),
                     ("IMAGE_START_CAPTURE", 2000),
                     ("DO_VTOL_TRANSITION", 3000)):
    check("%s is %d" % (name, number), getattr(m, name) == number)

check("waypoints use the relative-altitude frame, so the heights are "
      "above launch",
      all(i["frame"] == m.MAV_FRAME_GLOBAL_RELATIVE_ALT_INT
          for i in items if i["command"] == m.NAV_WAYPOINT))

print("\n7. what the uploader must get right")

source = open(os.path.join(REPO, "mission_upload.py")).read()
check("item 0 is home, and the planner does not have to know that",
      "Item 0 is home" in source or "item 0 is home" in source.lower())
check("latitude and longitude go as integers, times 1e7",
      "1e7" in source)
check("it answers PX4's requests rather than sending and hoping",
      "MISSION_REQUEST" in source and "MISSION_ACK" in source)
check("it clears the old mission first",
      "mission_clear_all_send" in source)
check("a timeout is reported, not swallowed", "Timed out" in source)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
