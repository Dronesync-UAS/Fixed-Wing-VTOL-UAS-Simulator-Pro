"""
The payload gimbal: where it is pointing, and how it is told where to point.

Added 12 Oct 2026. The gimbal itself is built into the aircraft model by
tools/gimbal_apply.py - two revolute joints, a camera and a one-ray lidar
standing in for a laser rangefinder. This module is the half that decides
the angles.

THE TWO THINGS IT DOES
----------------------
MANUAL POINTING. The operator drags in the picture; the station adds
that drag to the current aim and publishes two joint positions.

STABILISED, although the mount is not. A real EO/IR ball holds its line
of sight while the aircraft rolls; the one in the model is two joints
bolted to the airframe with no inertial loop of its own, so left alone
the picture would roll with the aircraft. The station holds it instead:
a manual aim is remembered as a bearing and a depression IN THE WORLD,
and the joint angles are recomputed from the aircraft's own attitude ten
times a second. It can be switched off, which shows what the bare mount
does - worth seeing once, not worth flying a lesson on - and the console
says which it is.

TARGET LOCK. The operator clicks a point. The station slews the boresight
onto it, waits for the gimbal to settle, measures the range, and works out
WHERE ON THE GROUND that is - a latitude, a longitude and an altitude.
From then on it recomputes the pointing angles from the aircraft's own
position and attitude ten times a second, so the picture stays on the
ground point while the aircraft flies past it. This is the thing that
makes a payload screen worth training on: holding a target through a turn
is the skill, and it cannot be practised against a camera that only ever
points where the airframe points.

FRAMES, SIGNS AND THE ONE THING THAT IS EASY TO GET BACKWARDS
--------------------------------------------------------------
Two different conventions meet here and they disagree about which way is
positive:

  * MAVLink attitude (what PX4 sends, and what simulator_link stores) is
    NED/FRD - x north, y east, z DOWN; roll positive right-wing-down,
    pitch positive nose-up, yaw clockwise from north. All the geometry
    below is done in that frame, because that is the frame the numbers
    arrive in.
  * Gazebo's body frame for this model is FLU - x forward, y LEFT, z up.
    The port wingtip light sits at y = +1.05 in the model, which is how
    that is known rather than assumed.

So a pan angle the operator thinks of as "20 degrees right" is +20 here,
and the yaw JOINT has to be driven to -20, because a positive rotation
about the model's +Z turns the camera to port. The pitch joint needs no
sign flip: a positive rotation about the model's +Y points the camera
down, and tilt is measured as a depression angle, 0 at the horizon and
+90 straight down.

The pure geometry below is deliberately free of Gazebo and of PX4, so
tools/test_payload.py can drive it with made-up aircraft states and check
the answers against hand-worked cases.

RANGE, AND SAYING HOW OLD IT IS
--------------------------------
A rangefinder reading with no age on it is a trap: a stale number looks
exactly like a live one. Every reading here carries the time it was taken
and the console shows it, which is the practice the EO/IR integration
literature recommends. When the lidar has not reported - because the
gimbal has not been added to the model yet, or the ray went off into the
sky - the station falls back to intersecting the line of sight with the
ground at the aircraft's own height above it, and SAYS that is what it
did. A computed range and a measured range are not the same thing and are
not presented as the same thing.

WHAT HAS BEEN TESTED. The geometry, by tools/test_payload.py, against
hand-worked cases: straight down, level forward, a banked aircraft, and a
lock held while the aircraft moves. What has NOT been tested is any of it
against a running Gazebo - no gimbal has been watched moving.
"""
import math
import threading
import time

import sim_target

EARTH_M_PER_DEG = 111320.0          # one degree of latitude, near enough

# How often the lock loop re-aims. Ten times a second is fast enough that
# the picture does not visibly step, and slow enough to be free.
LOCK_HZ = 10.0

# How long after a slew before the range is trusted for a new lock. The
# joints are tuned to settle in about a third of a second; this is that
# with room to spare.
SETTLE_S = 0.9

# A range reading older than this is shown as stale rather than as fact.
RANGE_STALE_S = 1.5

# Digital zoom. There is no runtime field-of-view change in gz-sim 8 that
# this project could find documented, so zoom is done by cropping the
# centre of the frame and scaling it back up - which is what a real
# payload's DIGITAL zoom does too, and is labelled as digital on screen.
ZOOM_MIN = 1.0
ZOOM_MAX = 12.0

PAN_LIMIT = sim_target.GIMBAL_PAN_LIMIT_DEG
TILT_UP = sim_target.GIMBAL_TILT_UP_DEG
TILT_DOWN = sim_target.GIMBAL_TILT_DOWN_DEG


state = {
    # Where it is pointing, as the station believes. The model has no joint
    # feedback subscription, so this is the commanded angle, not a measured
    # one - which is worth knowing if the gimbal ever fails to follow.
    "pan_deg": 0.0,
    "tilt_deg": 30.0,
    "zoom": 1.0,
    "mode": "manual",          # manual | acquiring | lock
    # See STABILISED above. When this is on, an aim is remembered as a
    # direction in the world and the joints are driven from it.
    "stabilise": True,
    "world_az_deg": 0.0,       # bearing from north, clockwise
    "world_el_deg": 30.0,      # depression below the horizon
    "target": None,            # {"lat":, "lon":, "alt_amsl":}
    "range_m": None,
    "range_source": None,      # "laser" | "computed" | None
    "range_at": 0.0,           # time.monotonic() of the reading
    "lasing": False,
    "problem": None,           # why the gimbal is not reachable, if it is not
    "commanded": 0,            # how many joint commands have gone out
}

_lock = threading.Lock()
_node = None                   # the gz transport node and its publishers
_laser = {"range_m": None, "at": 0.0}
_loop_started = False


# ---------------------------------------------------------------------
# PURE GEOMETRY - no Gazebo, no PX4, no module state.
# ---------------------------------------------------------------------

def clamp(value, low, high):
    return low if value < low else (high if value > high else value)


def clamp_angles(pan_deg, tilt_deg):
    """Fold pan into +-180 and clamp tilt to the mount's travel."""
    pan = (pan_deg + 180.0) % 360.0 - 180.0
    return clamp(pan, -PAN_LIMIT, PAN_LIMIT), clamp(tilt_deg, TILT_UP, TILT_DOWN)


def body_to_ned(roll_deg, pitch_deg, yaw_deg, vector):
    """Rotate a body-frame (FRD) vector into NED.

    The usual aerospace 3-2-1: yaw about down, then pitch about right,
    then roll about forward.
    """
    r, p, y = (math.radians(roll_deg), math.radians(pitch_deg),
               math.radians(yaw_deg))
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    x, yv, z = vector
    north = (cy * cp) * x + (cy * sp * sr - sy * cr) * yv + (cy * sp * cr + sy * sr) * z
    east = (sy * cp) * x + (sy * sp * sr + cy * cr) * yv + (sy * sp * cr - cy * sr) * z
    down = (-sp) * x + (cp * sr) * yv + (cp * cr) * z
    return north, east, down


def ned_to_body(roll_deg, pitch_deg, yaw_deg, vector):
    """The inverse of body_to_ned. The matrix is orthonormal, so this is
    its transpose, written out rather than inverted."""
    r, p, y = (math.radians(roll_deg), math.radians(pitch_deg),
               math.radians(yaw_deg))
    cr, sr = math.cos(r), math.sin(r)
    cp, sp = math.cos(p), math.sin(p)
    cy, sy = math.cos(y), math.sin(y)
    n, e, d = vector
    fwd = (cy * cp) * n + (sy * cp) * e + (-sp) * d
    right = (cy * sp * sr - sy * cr) * n + (sy * sp * sr + cy * cr) * e + (cp * sr) * d
    down = (cy * sp * cr + sy * sr) * n + (sy * sp * cr - cy * sr) * e + (cp * cr) * d
    return fwd, right, down


def boresight_body(pan_deg, tilt_deg):
    """The unit vector the camera looks along, in body FRD.

    pan is positive to the right, tilt is a depression angle - 0 at the
    horizon, +90 straight down. So tilt 90 gives (0, 0, 1), which is down.
    """
    pan, tilt = math.radians(pan_deg), math.radians(tilt_deg)
    return (math.cos(tilt) * math.cos(pan),
            math.cos(tilt) * math.sin(pan),
            math.sin(tilt))


def boresight_ned(roll_deg, pitch_deg, yaw_deg, pan_deg, tilt_deg):
    return body_to_ned(roll_deg, pitch_deg, yaw_deg,
                       boresight_body(pan_deg, tilt_deg))


def pixel_offset_deg(u, v, hfov_rad, aspect):
    """Where a click sits, as a pan and tilt offset from the boresight.

    u and v are fractions of the frame from its centre: -0.5 at the left
    and top edges, +0.5 at the right and bottom. A pinhole camera's angle
    off axis is atan(2 * fraction * tan(fov / 2)) - not simply
    fraction * fov, which is only true near the middle and is out by
    several degrees at the edge of a 60 degree lens.

    This treats the two axes independently, which is an approximation: a
    strict projection would compose the two rotations. At the corner of a
    60 degree frame the two differ by under a degree, and the target lock
    re-measures from the boresight anyway.
    """
    half_h = math.tan(hfov_rad / 2.0)
    half_v = half_h * aspect
    return (math.degrees(math.atan(2.0 * u * half_h)),
            math.degrees(math.atan(2.0 * v * half_v)))


def project_target(lat, lon, alt_amsl, direction_ned, range_m):
    """Where a line of sight of a given length ends up, as lat/lon/alt.

    Flat-earth, which over the few kilometres a training sortie covers is
    accurate to well under a metre and is a great deal easier to read than
    the spherical form.
    """
    north, east, down = direction_ned
    dlat = (north * range_m) / EARTH_M_PER_DEG
    dlon = (east * range_m) / (EARTH_M_PER_DEG * math.cos(math.radians(lat)))
    return {"lat": lat + dlat, "lon": lon + dlon,
            "alt_amsl": alt_amsl - down * range_m}


def aim_at_target(lat, lon, alt_amsl, roll_deg, pitch_deg, yaw_deg, target):
    """The pan and tilt that put the boresight on a fixed ground point.

    Returns (pan_deg, tilt_deg, slant_range_m), or None when the aircraft
    is exactly on top of the target and there is no direction to point.
    """
    north = (target["lat"] - lat) * EARTH_M_PER_DEG
    east = ((target["lon"] - lon) * EARTH_M_PER_DEG
            * math.cos(math.radians(lat)))
    down = alt_amsl - target["alt_amsl"]
    distance = math.sqrt(north * north + east * east + down * down)
    if distance < 1e-6:
        return None
    unit = (north / distance, east / distance, down / distance)
    fwd, right, dwn = ned_to_body(roll_deg, pitch_deg, yaw_deg, unit)
    pan = math.degrees(math.atan2(right, fwd))
    tilt = math.degrees(math.asin(clamp(dwn, -1.0, 1.0)))
    return pan, tilt, distance


def ground_range(direction_ned, height_agl_m):
    """How far to the ground along a line of sight, when nothing measured it.

    Only meaningful looking downwards: a ray at or above the horizon never
    meets a flat ground, and this returns None rather than a huge number
    that would read as a measurement.
    """
    down = direction_ned[2]
    if height_agl_m is None or height_agl_m <= 0 or down <= 0.02:
        return None
    return height_agl_m / down


# ---------------------------------------------------------------------
# TALKING TO GAZEBO
# ---------------------------------------------------------------------

def _publishers():
    """The two joint publishers and the lidar subscription, or None.

    Rebuilt only once: the joint topics are scoped to the MODEL, not the
    world, so unlike the camera feeds they survive an environment switch.
    """
    global _node
    with _lock:
        if _node is not None:
            return _node
        try:
            from gz.transport13 import Node
            from gz.msgs10.double_pb2 import Double
        except ImportError as exc:
            state["problem"] = f"gz python bindings not available ({exc})"
            return None
        node = Node()
        pubs = {}
        for joint in sim_target.GIMBAL_JOINTS:
            pubs[joint] = node.advertise(sim_target.gimbal_joint_topic(joint),
                                         Double)
        try:
            from gz.msgs10.laserscan_pb2 import LaserScan
            node.subscribe(LaserScan, sim_target.LRF_TOPIC, _on_scan)
        except Exception:                                  # noqa: BLE001
            # No lidar message type, or no such topic yet. The rangefinder
            # then falls back to the computed range, which is reported as
            # computed. Not a reason to refuse to point the gimbal.
            pass
        _node = {"node": node, "pubs": pubs, "Double": Double}
        state["problem"] = None
        return _node


def _on_scan(msg):
    """One lidar return. The sensor has a single ray, so ranges[0] is it."""
    try:
        value = msg.ranges[0]
    except (AttributeError, IndexError):
        return
    if not math.isfinite(value) or value <= 0:
        # The ray went off into the sky. That is a real answer - "no
        # return" - and is recorded as such rather than kept as the last
        # good range for ever.
        _laser["range_m"] = None
    else:
        _laser["range_m"] = round(float(value), 1)
    _laser["at"] = time.monotonic()


def _publish(pan_deg, tilt_deg):
    """Send the two joint positions. See the module docstring for the sign."""
    node = _publishers()
    if node is None:
        return False
    yaw_joint, pitch_joint = sim_target.GIMBAL_JOINTS
    message = node["Double"]()
    message.data = math.radians(-pan_deg)       # +pan is right, +joint is port
    node["pubs"][yaw_joint].publish(message)
    message = node["Double"]()
    message.data = math.radians(tilt_deg)       # +tilt is down, +joint is down
    node["pubs"][pitch_joint].publish(message)
    state["commanded"] += 1
    return True


# ---------------------------------------------------------------------
# THE CONTROLS THE CONSOLE CALLS
# ---------------------------------------------------------------------

def _aircraft():
    """The aircraft state this module needs, or None if it is not known yet.

    Imported here rather than at module scope so the geometry above can be
    tested without the MAVLink link existing at all.
    """
    from simulator_link import telemetry, home_amsl
    lat, lon = telemetry.get("latitude"), telemetry.get("longitude")
    if lat is None or lon is None:
        return None
    amsl = telemetry.get("altitude_amsl_m")
    if amsl is None:
        ground = home_amsl()
        amsl = (ground or 0.0) + (telemetry.get("altitude_m") or 0.0)
    return {
        "lat": lat, "lon": lon, "alt_amsl": amsl,
        "agl": telemetry.get("altitude_m"),
        "roll": telemetry.get("roll_deg") or 0.0,
        "pitch": telemetry.get("pitch_deg") or 0.0,
        "yaw": telemetry.get("yaw_deg") or 0.0,
    }


def world_from_body(roll_deg, pitch_deg, yaw_deg, pan_deg, tilt_deg):
    """The bearing and depression, in the world, that a body aim points at.

    Bearing is from north, clockwise; depression is positive downwards -
    the same pair the operator already reads, measured against the ground
    instead of against the airframe.
    """
    north, east, down = boresight_ned(roll_deg, pitch_deg, yaw_deg,
                                      pan_deg, tilt_deg)
    bearing = math.degrees(math.atan2(east, north)) % 360.0
    depression = math.degrees(math.asin(clamp(down, -1.0, 1.0)))
    return bearing, depression


def body_from_world(roll_deg, pitch_deg, yaw_deg, bearing_deg, depression_deg):
    """The inverse: what to drive the joints to, to look that way."""
    bearing = math.radians(bearing_deg)
    depression = math.radians(depression_deg)
    horizontal = math.cos(depression)
    unit = (horizontal * math.cos(bearing), horizontal * math.sin(bearing),
            math.sin(depression))
    fwd, right, down = ned_to_body(roll_deg, pitch_deg, yaw_deg, unit)
    return (math.degrees(math.atan2(right, fwd)),
            math.degrees(math.asin(clamp(down, -1.0, 1.0))))


def aim(pan_deg, tilt_deg, break_lock=True, remember=True):
    """Point the gimbal. Any manual aim drops a target lock by default.

    `remember` is what makes stabilisation work: an aim the OPERATOR
    asked for is also stored as a direction in the world, so the holding
    loop has something to hold. An aim that loop issues itself must not
    overwrite it, or the gimbal would drift round with the aircraft one
    small correction at a time.
    """
    pan, tilt = clamp_angles(pan_deg, tilt_deg)
    state["pan_deg"], state["tilt_deg"] = round(pan, 2), round(tilt, 2)
    if break_lock and state["mode"] != "manual":
        state["mode"] = "manual"
        state["target"] = None
    if remember:
        aircraft = _aircraft()
        if aircraft is not None:
            bearing, depression = world_from_body(
                aircraft["roll"], aircraft["pitch"], aircraft["yaw"], pan, tilt)
            state["world_az_deg"] = round(bearing, 2)
            state["world_el_deg"] = round(depression, 2)
    _publish(pan, tilt)
    start_lock_loop()
    return state["pan_deg"], state["tilt_deg"]


def nudge(d_pan_deg, d_tilt_deg):
    """Relative slew - what a drag in the picture does."""
    return aim(state["pan_deg"] + d_pan_deg, state["tilt_deg"] + d_tilt_deg)


def set_zoom(zoom):
    state["zoom"] = round(clamp(float(zoom), ZOOM_MIN, ZOOM_MAX), 2)
    return state["zoom"]


def effective_fov_rad(base_fov_rad=None):
    """The field of view actually on screen, after digital zoom."""
    base = base_fov_rad or sim_target.GIMBAL_FOV_RAD
    # Cropping the middle 1/zoom of the frame narrows the angle it covers.
    return 2.0 * math.atan(math.tan(base / 2.0) / state["zoom"])


def stow():
    """Park it looking straight down - where a payload sits for landing."""
    return aim(0.0, TILT_DOWN)


def centre():
    """Forward and level: the view the nose camera has."""
    return aim(0.0, 0.0)


def measure_range(force_compute=False):
    """The best range available, with where it came from and how old it is."""
    aircraft = _aircraft()
    laser_age = time.monotonic() - _laser["at"] if _laser["at"] else None
    if (not force_compute and _laser["range_m"] is not None
            and laser_age is not None and laser_age < RANGE_STALE_S):
        state["range_m"] = _laser["range_m"]
        state["range_source"] = "laser"
        state["range_at"] = _laser["at"]
        return state["range_m"]
    if aircraft is None:
        state["range_m"], state["range_source"] = None, None
        return None
    direction = boresight_ned(aircraft["roll"], aircraft["pitch"],
                              aircraft["yaw"],
                              state["pan_deg"], state["tilt_deg"])
    computed = ground_range(direction, aircraft["agl"])
    state["range_m"] = round(computed, 1) if computed else None
    state["range_source"] = "computed" if computed else None
    state["range_at"] = time.monotonic()
    return state["range_m"]


def lase():
    """Fire the rangefinder once, for the console's LRF button.

    On a real payload this is a deliberate act with a safety case around
    it, which is why it is a button and not something that happens
    continuously. Here it just takes the latest reading.
    """
    state["lasing"] = True
    try:
        value = measure_range()
    finally:
        state["lasing"] = False
    if value is None:
        return "No return - the line of sight is not meeting anything."
    where = ("laser" if state["range_source"] == "laser"
             else "computed from the aircraft's height, not measured")
    return f"Range {value:.0f} m ({where})."


def lock_on(u=0.0, v=0.0):
    """Hold the picture on the point under a click.

    Slews the boresight onto it first, lets the gimbal settle, then
    measures and fixes the ground point - which is the order a real
    slew-to-cue-then-lase sequence runs in, and avoids ranging to whatever
    happened to be under the boresight before the slew.
    """
    aircraft = _aircraft()
    if aircraft is None:
        return "No aircraft position yet - nothing to lock on to."
    d_pan, d_tilt = pixel_offset_deg(u, v, effective_fov_rad(), _aspect())
    aim(state["pan_deg"] + d_pan, state["tilt_deg"] + d_tilt)
    state["mode"] = "acquiring"
    threading.Thread(target=_acquire, daemon=True).start()
    return "Slewing to the point, then locking on."


def _aspect():
    from video_feed import payload as feed
    return (feed.height / feed.width) if feed.width else 0.5625


def _acquire():
    time.sleep(SETTLE_S)
    if state["mode"] != "acquiring":
        return                                  # cancelled while slewing
    aircraft = _aircraft()
    distance = measure_range()
    if aircraft is None or distance is None:
        state["mode"] = "manual"
        state["target"] = None
        return
    direction = boresight_ned(aircraft["roll"], aircraft["pitch"],
                              aircraft["yaw"],
                              state["pan_deg"], state["tilt_deg"])
    state["target"] = project_target(aircraft["lat"], aircraft["lon"],
                                     aircraft["alt_amsl"], direction, distance)
    state["mode"] = "lock"
    start_lock_loop()


def unlock():
    state["mode"] = "manual"
    state["target"] = None
    return "Target lock released."


def set_stabilise(on):
    state["stabilise"] = bool(on)
    if state["stabilise"]:
        start_lock_loop()
    return state["stabilise"]


def _stabilise_step():
    """Hold the remembered world direction while the aircraft manoeuvres.

    Manual pointing only: in target lock the aim is worked out from the
    ground point instead, which is a stronger form of the same thing.
    """
    if not state["stabilise"] or state["mode"] != "manual":
        return False
    aircraft = _aircraft()
    if aircraft is None:
        return False
    pan, tilt = body_from_world(aircraft["roll"], aircraft["pitch"],
                                aircraft["yaw"], state["world_az_deg"],
                                state["world_el_deg"])
    wanted_pan, wanted_tilt = clamp_angles(pan, tilt)
    # Held at the stop when the aircraft takes the line of sight outside
    # the mount's travel, rather than wrapped round to the other side -
    # which would swing the picture through 180 degrees and lose whatever
    # the operator was watching.
    aim(wanted_pan, wanted_tilt, break_lock=False, remember=False)
    return True


def _lock_step():
    """One pass of the holding loop: target lock if there is one, and
    otherwise stabilisation. Separated so a test can call it directly."""
    if state["mode"] != "lock" or not state["target"]:
        return _stabilise_step()
    aircraft = _aircraft()
    if aircraft is None:
        return False
    answer = aim_at_target(aircraft["lat"], aircraft["lon"],
                           aircraft["alt_amsl"], aircraft["roll"],
                           aircraft["pitch"], aircraft["yaw"], state["target"])
    if answer is None:
        return False
    pan, tilt, distance = answer
    wanted_pan, wanted_tilt = clamp_angles(pan, tilt)
    # Off the end of the mount's travel: the aircraft has flown somewhere
    # the gimbal cannot look. Say so instead of sitting against the stop
    # pretending to be locked.
    if abs(wanted_tilt - tilt) > 0.5 or abs(wanted_pan - pan) > 0.5:
        state["mode"] = "manual"
        state["target"] = None
        return False
    aim(wanted_pan, wanted_tilt, break_lock=False)
    state["range_m"] = round(distance, 1)
    state["range_source"] = "computed"
    state["range_at"] = time.monotonic()
    return True


def start_lock_loop():
    global _loop_started
    if _loop_started:
        return
    _loop_started = True

    def run():
        while True:
            time.sleep(1.0 / LOCK_HZ)
            try:
                _lock_step()
            except Exception:                              # noqa: BLE001
                # A lock that cannot be computed must not take the station
                # down; the next pass tries again.
                pass

    threading.Thread(target=run, daemon=True).start()


def status():
    """Everything the payload screen needs, in one answer."""
    age = (round(time.monotonic() - state["range_at"], 1)
           if state["range_at"] else None)
    return {
        "pan_deg": state["pan_deg"],
        "tilt_deg": state["tilt_deg"],
        "zoom": state["zoom"],
        "mode": state["mode"],
        "target": state["target"],
        "range_m": state["range_m"],
        "range_source": state["range_source"],
        "range_age_s": age,
        "range_stale": (age is not None and age > RANGE_STALE_S),
        "fov_deg": round(math.degrees(effective_fov_rad()), 1),
        "pan_limit_deg": PAN_LIMIT,
        "tilt_up_deg": TILT_UP,
        "tilt_down_deg": TILT_DOWN,
        "zoom_max": ZOOM_MAX,
        "problem": state["problem"],
        "stabilised": state["stabilise"],
        "world_az_deg": state["world_az_deg"],
        "world_el_deg": state["world_el_deg"],
    }


# ---------------------------------------------------------------------
# THE CHASE BOOM
#
# Not the payload, but the same mechanism: two joints on the aircraft
# driven by position commands, so it lives here rather than in a second
# file that would repeat the gz-transport plumbing. See
# tools/chase_angles_apply.py for the geometry and for why azimuth +90 is
# the view from the STARBOARD side.
# ---------------------------------------------------------------------

chase = {"az_deg": 0.0, "el_deg": 7.0, "preset": "behind"}

# The angles each named view needs. Elevation is positive upwards: the
# camera rises and tilts down to keep the aircraft in frame.
#   behind    the default: over the aircraft's shoulder
#   port      off the left wing, looking right across the aircraft
#   starboard off the right wing
#   nose      ahead of the aircraft, looking back at it
#   top       high above and behind, looking down - the circuit view
#   low       below and behind, looking up - the aircraft against the sky
#
# ELEVATION LOWERED 12 Oct 2026. These started at 13.8 degrees, which
# reproduced the old fixed camera at 9 m back and 2.2 m up. On screen
# that was almost all ground: the camera's vertical half-angle is
# atan(tan(0.6) * 9/16) = 0.367 rad = 21 degrees, so a 13.8 degree
# down-tilt puts the horizon two thirds of the way from the middle to
# the top of the frame.
#
# At 7 degrees the horizon sits a third of the way up from the middle,
# which is about a third of the frame in sky - enough to judge attitude
# against, which is what an external view is for. The aircraft stays in
# the middle whatever the elevation, because the boom tilts the camera
# by the same angle it raises it.
CHASE_PRESETS = {
    "behind": (0.0, 7.0),
    "port": (-90.0, 7.0),
    "starboard": (90.0, 7.0),
    "nose": (180.0, 6.0),
    "top": (0.0, 60.0),
    "low": (0.0, -14.0),
}

_chase_node = None


def _chase_publishers():
    global _chase_node
    with _lock:
        if _chase_node is not None:
            return _chase_node
        try:
            from gz.transport13 import Node
            from gz.msgs10.double_pb2 import Double
        except ImportError:
            return None
        node = Node()
        pubs = {j: node.advertise(sim_target.chase_boom_topic(j), Double)
                for j in sim_target.CHASE_BOOM_JOINTS}
        _chase_node = {"node": node, "pubs": pubs, "Double": Double}
        return _chase_node


def chase_view(preset=None, az_deg=None, el_deg=None):
    """Swing the chase boom. Named preset, or explicit angles."""
    if preset is not None:
        if preset not in CHASE_PRESETS:
            return None
        az_deg, el_deg = CHASE_PRESETS[preset]
        chase["preset"] = preset
    else:
        chase["preset"] = "custom"
    az = (float(az_deg) + 180.0) % 360.0 - 180.0
    el = clamp(float(el_deg), -28.0, 83.0)      # the joint's own travel
    chase["az_deg"], chase["el_deg"] = round(az, 1), round(el, 1)
    node = _chase_publishers()
    if node is None:
        return chase
    az_joint, el_joint = sim_target.CHASE_BOOM_JOINTS
    message = node["Double"]()
    message.data = math.radians(az)
    node["pubs"][az_joint].publish(message)
    message = node["Double"]()
    message.data = math.radians(el)
    node["pubs"][el_joint].publish(message)
    return chase


def chase_status():
    return dict(chase, presets=list(CHASE_PRESETS))
