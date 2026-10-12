"""
Autonomous mission planning: surveys, corridors, orbits and waypoints,
with the gimbal camera as part of the plan rather than an afterthought.

Added 12 Oct 2026 on request, in the style of QGroundControl's Plan
view, which is the one most remote pilots have already been taught.

WHAT THIS FILE IS. Pure geometry and MAVLink mission items. No pymavlink
import, no network, no PX4 - so every pattern can be checked on a
machine with neither simulator running, which is how
tools/test_mission.py checks it. The sending lives in mission_upload.py.

THE PATTERNS, and what each is for in training:

  SURVEY      the lawnmower. Parallel lines across an area, camera
              triggering by distance. The bread-and-butter mapping
              sortie, and the one a student has to be able to plan.
  CORRIDOR    parallel lines following a line rather than filling an
              area: pipelines, railways, rivers, power lines, a road
              after a flood.
  ORBIT       circle a point at a fixed radius with the camera held on
              it. Structure inspection, incident overwatch, and the
              exercise that shows a student what a gimbal is for.
  WAYPOINTS   a list of points, flown in order. The plain case.
  PERIMETER   fly the edge of an area rather than fill it. Boundary
              patrol and search along a fence line.

THE NUMBERS ARE WORKED OUT, NOT TYPED. Line spacing comes from the
camera's field of view, the height above ground and the side overlap;
the trigger distance comes from the same three and the front overlap.
Those are the standard photogrammetry relations:

    ground width covered by one frame
        = 2 * height * tan(horizontal_fov / 2)
    line spacing = that width * (1 - side_overlap)
    ground height covered by one frame
        = 2 * height * tan(vertical_fov / 2)
    trigger distance = that height * (1 - front_overlap)

MAVLINK COMMAND NUMBERS are read from the MAVLink common.xml message
definitions, not recalled:

    16   NAV_WAYPOINT              84   NAV_VTOL_TAKEOFF
    19   NAV_LOITER_TIME           85   NAV_VTOL_LAND
    20   NAV_RETURN_TO_LAUNCH      178  DO_CHANGE_SPEED
    195  DO_SET_ROI_LOCATION       206  DO_SET_CAM_TRIGG_DIST
    197  DO_SET_ROI_NONE           2000 IMAGE_START_CAPTURE
    205  DO_MOUNT_CONTROL          2001 IMAGE_STOP_CAPTURE
    3000 DO_VTOL_TRANSITION

DO_SET_CAM_TRIGG_DIST param1 is the trigger distance in metres and 0
stops triggering; DO_SET_ROI_LOCATION carries the target in param5/6/7
as latitude, longitude and altitude. Both from the same definitions.

NOT FLOWN. Every pattern here has been checked arithmetically and
nothing has been uploaded to PX4 from this file.
"""

import math

# --- MAVLink, by number so no dialect has to be imported here ----------
NAV_WAYPOINT = 16
NAV_LOITER_TIME = 19
NAV_RETURN_TO_LAUNCH = 20
NAV_VTOL_TAKEOFF = 84
NAV_VTOL_LAND = 85
DO_CHANGE_SPEED = 178
DO_SET_ROI_LOCATION = 195
DO_SET_ROI_NONE = 197
DO_MOUNT_CONTROL = 205
DO_SET_CAM_TRIGG_DIST = 206
IMAGE_START_CAPTURE = 2000
IMAGE_STOP_CAPTURE = 2001
DO_VTOL_TRANSITION = 3000

MAV_FRAME_GLOBAL_RELATIVE_ALT_INT = 6
MAV_FRAME_MISSION = 2
MAV_VTOL_STATE_FW = 4
MAV_VTOL_STATE_MC = 3

NAN = float("nan")

# The payload camera as tools/gimbal_apply.py builds it: 1024x576 at a
# 1.05 rad horizontal field of view. The vertical field follows from the
# aspect ratio, which is why it is derived rather than typed.
CAMERA_HFOV_RAD = 1.05
CAMERA_W, CAMERA_H = 1024, 576

# Defaults a student would be taught, not invented: 70% front and 60%
# side overlap is the usual starting point for mapping, and gives
# enough redundancy for a photogrammetry package to tie frames together.
DEFAULT_FRONT_OVERLAP = 0.70
DEFAULT_SIDE_OVERLAP = 0.60

# Metres per degree. Flat earth, good to a few parts in a thousand over
# the tens of kilometres anything here covers.
M_PER_DEG_LAT = 110540.0
M_PER_DEG_LON_EQ = 111320.0


def camera_vfov_rad(hfov_rad=CAMERA_HFOV_RAD, width=CAMERA_W, height=CAMERA_H):
    """Vertical field of view from the horizontal one and the aspect
    ratio. Derived rather than declared: the two cannot then disagree
    when the image size changes."""
    return 2.0 * math.atan(math.tan(hfov_rad / 2.0) * (height / float(width)))


def footprint_m(height_m, hfov_rad=CAMERA_HFOV_RAD):
    """(across, along) metres of ground in one frame, from a camera
    pointing straight down at `height_m`."""
    across = 2.0 * height_m * math.tan(hfov_rad / 2.0)
    along = 2.0 * height_m * math.tan(camera_vfov_rad(hfov_rad) / 2.0)
    return across, along


def line_spacing_m(height_m, side_overlap=DEFAULT_SIDE_OVERLAP,
                   hfov_rad=CAMERA_HFOV_RAD):
    across, _ = footprint_m(height_m, hfov_rad)
    return max(1.0, across * (1.0 - side_overlap))


def trigger_distance_m(height_m, front_overlap=DEFAULT_FRONT_OVERLAP,
                       hfov_rad=CAMERA_HFOV_RAD):
    _, along = footprint_m(height_m, hfov_rad)
    return max(1.0, along * (1.0 - front_overlap))


# --- local metres <-> latitude and longitude ---------------------------

def offset(lat, lon, north_m, east_m):
    """A point `north_m` north and `east_m` east of (lat, lon)."""
    d_lat = north_m / M_PER_DEG_LAT
    d_lon = east_m / (M_PER_DEG_LON_EQ * math.cos(math.radians(lat)))
    return lat + d_lat, lon + d_lon


def metres_between(lat1, lon1, lat2, lon2):
    north = (lat2 - lat1) * M_PER_DEG_LAT
    east = ((lon2 - lon1) * M_PER_DEG_LON_EQ
            * math.cos(math.radians((lat1 + lat2) / 2.0)))
    return math.hypot(north, east)


def _rotate(x, y, degrees):
    r = math.radians(degrees)
    c, s = math.cos(r), math.sin(r)
    return x * c - y * s, x * s + y * c


# --- one mission item --------------------------------------------------

def item(command, p1=0.0, p2=0.0, p3=0.0, p4=0.0,
         lat=0.0, lon=0.0, alt=0.0, frame=None, autocontinue=1):
    """One mission item, as a plain dict. The sender turns these into
    MISSION_ITEM_INT messages; keeping them dicts is what lets every
    pattern be checked without pymavlink."""
    if frame is None:
        frame = (MAV_FRAME_MISSION if lat == 0.0 and lon == 0.0 and alt == 0.0
                 else MAV_FRAME_GLOBAL_RELATIVE_ALT_INT)
    return {"command": command, "frame": frame, "autocontinue": autocontinue,
            "param1": float(p1), "param2": float(p2),
            "param3": float(p3), "param4": float(p4),
            "x": float(lat), "y": float(lon), "z": float(alt)}


# --- the patterns ------------------------------------------------------

def survey_lines(centre_lat, centre_lon, width_m, height_m_area,
                 spacing_m, angle_deg=0.0):
    """Lawnmower lines filling a rectangle, as (lat, lon) pairs in the
    order they are flown.

    Every other line is reversed, which is what makes it a lawnmower
    rather than a comb: the aircraft turns at the end of each line and
    flies back, instead of flying back to the start each time.

    `angle_deg` turns the whole pattern. Lines are flown along the
    rectangle's long axis before rotation, because turning costs time
    and fewer, longer lines means fewer turns.
    """
    if spacing_m <= 0:
        raise ValueError("line spacing must be positive")
    # Lines run along the local x axis, stacked along y.
    half_w, half_h = width_m / 2.0, height_m_area / 2.0
    count = max(1, int(math.ceil(height_m_area / spacing_m)) + 1)
    # Spread the lines evenly rather than leaving a wide gap at one
    # edge: the ends matter as much as the middle on a survey.
    step = height_m_area / (count - 1) if count > 1 else 0.0

    points = []
    for n in range(count):
        y = -half_h + n * step
        ends = [(-half_w, y), (half_w, y)]
        if n % 2:
            ends.reverse()
        for x, yy in ends:
            east, north = _rotate(x, yy, angle_deg)
            points.append(offset(centre_lat, centre_lon, north, east))
    return points


def corridor_points(path, width_m, spacing_m):
    """Parallel passes either side of a path, for a pipeline, river or
    road. `path` is a list of (lat, lon) in order.

    One pass down the centre when the corridor is narrower than the
    spacing, otherwise an odd number of passes centred on it, flown
    alternately in each direction.
    """
    if len(path) < 2:
        raise ValueError("a corridor needs at least two points")
    if spacing_m <= 0:
        raise ValueError("line spacing must be positive")

    passes = max(1, int(math.ceil(width_m / spacing_m)))
    if passes % 2 == 0:
        passes += 1               # keep one pass on the centre line
    offsets = [(n - (passes - 1) / 2.0) * spacing_m for n in range(passes)]

    points = []
    for n, side in enumerate(offsets):
        leg = []
        for i, (lat, lon) in enumerate(path):
            # The local normal, from the neighbouring points.
            prev = path[max(0, i - 1)]
            nxt = path[min(len(path) - 1, i + 1)]
            north = (nxt[0] - prev[0]) * M_PER_DEG_LAT
            east = ((nxt[1] - prev[1]) * M_PER_DEG_LON_EQ
                    * math.cos(math.radians(lat)))
            length = math.hypot(north, east) or 1.0
            # Rotate the direction 90 degrees to get the normal.
            n_north, n_east = -east / length, north / length
            leg.append(offset(lat, lon, n_north * side, n_east * side))
        if n % 2:
            leg.reverse()
        points.extend(leg)
    return points


def orbit_points(lat, lon, radius_m, turns=1, points_per_turn=16,
                 clockwise=True):
    """A circle around a point, as waypoints. PX4 flies between them, so
    sixteen a turn is a circle to the eye and leaves the turn radius to
    the autopilot rather than demanding one it cannot fly."""
    if radius_m <= 0:
        raise ValueError("orbit radius must be positive")
    out = []
    total = max(3, int(points_per_turn * turns))
    for n in range(total + 1):
        angle = 2.0 * math.pi * n / points_per_turn
        if not clockwise:
            angle = -angle
        north = radius_m * math.cos(angle)
        east = radius_m * math.sin(angle)
        out.append(offset(lat, lon, north, east))
    return out


def perimeter_points(centre_lat, centre_lon, width_m, height_m_area,
                     angle_deg=0.0):
    """The edge of a rectangle, closed. Boundary patrol and fence-line
    search."""
    half_w, half_h = width_m / 2.0, height_m_area / 2.0
    corners = [(-half_w, -half_h), (half_w, -half_h),
               (half_w, half_h), (-half_w, half_h), (-half_w, -half_h)]
    out = []
    for x, y in corners:
        east, north = _rotate(x, y, angle_deg)
        out.append(offset(centre_lat, centre_lon, north, east))
    return out


# --- camera and gimbal items -------------------------------------------

def camera_trigger_every(distance_m):
    """Trigger the camera every `distance_m` of ground. 0 stops it -
    DO_SET_CAM_TRIGG_DIST param1, from the MAVLink definitions."""
    return item(DO_SET_CAM_TRIGG_DIST, p1=distance_m, p2=0, p3=0)


def camera_trigger_off():
    return item(DO_SET_CAM_TRIGG_DIST, p1=0)


def gimbal_down(pitch_deg=-90.0, yaw_deg=0.0):
    """Point the gimbal. DO_MOUNT_CONTROL param1 is pitch and param3 is
    yaw, in degrees; straight down is -90, which is what a mapping
    sortie wants and the one most often got wrong by hand."""
    return item(DO_MOUNT_CONTROL, p1=pitch_deg, p2=0.0, p3=yaw_deg, p4=0,
                frame=MAV_FRAME_MISSION)


def gimbal_at_target(lat, lon, alt_m=0.0):
    """Hold the camera on a place on the ground while the aircraft flies
    past it - DO_SET_ROI_LOCATION, target in param5/6/7. This is the one
    that makes an orbit an inspection rather than a circle."""
    return item(DO_SET_ROI_LOCATION, p1=0, lat=lat, lon=lon, alt=alt_m)


def gimbal_release():
    return item(DO_SET_ROI_NONE, frame=MAV_FRAME_MISSION)


# --- putting a whole mission together ----------------------------------

PATTERNS = ("survey", "corridor", "orbit", "perimeter", "waypoints")


def build(pattern, home_lat, home_lon, altitude_m,
          width_m=400.0, height_m=300.0, angle_deg=0.0,
          radius_m=150.0, turns=2, path=None, points=None,
          front_overlap=DEFAULT_FRONT_OVERLAP,
          side_overlap=DEFAULT_SIDE_OVERLAP,
          speed_ms=None, camera=True, fixed_wing=True,
          return_home=True, centre_lat=None, centre_lon=None):
    """A complete mission, as a list of items, ready to upload.

    THE SHAPE OF EVERY MISSION, and why:

      1. VTOL takeoff to the working height. NAV_VTOL_TAKEOFF rather
         than NAV_TAKEOFF, or a VTOL takes off as a fixed wing and
         there is nothing underneath it.
      2. Transition to fixed wing, if the pattern is to be flown on the
         wing. An orbit at 150 m is better flown as a multirotor; a
         survey covering half a kilometre is not.
      3. Point the gimbal and start the camera.
      4. The pattern.
      5. Stop the camera, release the gimbal.
      6. Return to launch, which for a VTOL ends in a hover landing.

    Returns (items, summary). The summary is what the console shows
    before anybody presses upload: how far, how long, how many frames.
    """
    if pattern not in PATTERNS:
        raise ValueError("unknown pattern %r" % (pattern,))
    lat = home_lat if centre_lat is None else centre_lat
    lon = home_lon if centre_lon is None else centre_lon

    spacing = line_spacing_m(altitude_m, side_overlap)
    trigger = trigger_distance_m(altitude_m, front_overlap)

    if pattern == "survey":
        track = survey_lines(lat, lon, width_m, height_m, spacing, angle_deg)
    elif pattern == "corridor":
        track = corridor_points(path or [(lat, lon)], width_m, spacing)
    elif pattern == "orbit":
        track = orbit_points(lat, lon, radius_m, turns)
    elif pattern == "perimeter":
        track = perimeter_points(lat, lon, width_m, height_m, angle_deg)
    else:
        track = list(points or [])
        if not track:
            raise ValueError("a waypoint mission needs some waypoints")

    out = []
    # 1. Takeoff. PX4 reads item 0 as home, so the first real item is
    #    index 1 - the sender adds the home item.
    out.append(item(NAV_VTOL_TAKEOFF, p2=0, p4=NAN,
                    lat=home_lat, lon=home_lon, alt=altitude_m))
    if speed_ms:
        out.append(item(DO_CHANGE_SPEED, p1=1, p2=speed_ms, p3=-1,
                        frame=MAV_FRAME_MISSION))
    if fixed_wing:
        out.append(item(DO_VTOL_TRANSITION, p1=MAV_VTOL_STATE_FW,
                        frame=MAV_FRAME_MISSION))

    if camera:
        if pattern == "orbit":
            # Hold the camera on the thing being inspected, which is
            # the whole point of orbiting it.
            out.append(gimbal_at_target(lat, lon, 0.0))
        else:
            out.append(gimbal_down(-90.0))
        out.append(camera_trigger_every(trigger))

    for wlat, wlon in track:
        out.append(item(NAV_WAYPOINT, p1=0, p4=NAN,
                        lat=wlat, lon=wlon, alt=altitude_m))

    if camera:
        out.append(camera_trigger_off())
        out.append(gimbal_release())

    if fixed_wing:
        # Back to multirotor before the landing, and with room to do it:
        # a back transition is a deceleration, not a stop.
        out.append(item(DO_VTOL_TRANSITION, p1=MAV_VTOL_STATE_MC,
                        frame=MAV_FRAME_MISSION))
    if return_home:
        out.append(item(NAV_RETURN_TO_LAUNCH, frame=MAV_FRAME_MISSION))

    return out, summarise(track, altitude_m, trigger, spacing,
                          speed_ms or (16.0 if fixed_wing else 8.0))


def summarise(track, altitude_m, trigger_m, spacing_m, speed_ms):
    """What the console shows before anyone presses upload. An estimate
    said plainly as an estimate: the turns at the end of each line are
    not modelled, so a real survey takes longer than this says."""
    distance = 0.0
    for a, b in zip(track, track[1:]):
        distance += metres_between(a[0], a[1], b[0], b[1])
    return {
        "waypoints": len(track),
        "distance_m": round(distance),
        "minutes": round(distance / max(1.0, speed_ms) / 60.0, 1),
        "photos": int(distance // trigger_m) if trigger_m else 0,
        "line_spacing_m": round(spacing_m, 1),
        "trigger_every_m": round(trigger_m, 1),
        "altitude_m": altitude_m,
        "estimate_note": ("Straight-line estimate - the turn at the end of "
                          "each line is not counted, so allow longer."),
    }
