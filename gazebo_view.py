"""
External ("chase plane") camera views of the aircraft in the Gazebo window,
driven from the instructor station the same way freeze/reposition are - by
calling Gazebo's own services directly.

Added 11 Oct 2026 on request: a full view of the aircraft from behind and
above, fixed alternatives (top-down, side, front), and a manual view.

How it works, confirmed against gz-gui 8's CameraTracking source rather than
assumed:

  /gui/follow        (gz.msgs.StringMsg  -> gz.msgs.Boolean)
      Sets which model the Gazebo camera follows, by name. An empty name
      releases the camera, which is what "manual" below does - the mouse then
      flies the view freely in the Gazebo window.

  /gui/follow/offset (gz.msgs.Vector3d   -> gz.msgs.Boolean)
      Where the camera sits relative to the aircraft. The offset is in the
      aircraft's OWN frame (gz-gui's trackWorldFrame defaults to false), so it
      rotates with the aircraft and a "behind" view stays behind through a
      turn. gz-gui's own default is (-3, 0, 2) - behind and above - which is
      where the sign convention below comes from: -x is behind, +y is left,
      +z is above.
      It is ignored unless a follow target is already set, so the two calls
      below always go out in that order.

Note this moves the camera in the GAZEBO window, not inside the GCS page. The
alternative - extra camera sensors streamed into a GCS panel like the FPV feed
- was rejected for now: it costs a second rendered camera on a machine whose
performance is already noted as marginal (12 July entry), and manual free-look
would have to be rebuilt from scratch when Gazebo already has it.

This build (gz 8.15.0) does not advertise the newer /gui/track service, so the
deprecated-but-present /gui/follow pair is used. If a later Gazebo drops them,
/gui/track with gz.msgs.CameraTrack is the replacement and does the same job.
"""

import subprocess

# Confirmed for this setup in the 10 Aug entry, and used by the reposition
# plugins too.
MODEL = "standard_vtol_0"

# Offset per view as a fraction of the instructor's chosen distance, in the
# aircraft's frame: (forward, left, up). Scaling with distance rather than
# hard-coding metres means one distance box drives every view.
VIEWS = {
    "rear_above": (-0.90, 0.00, 0.35),
    "top_down": (-0.15, 0.00, 1.00),
    "left_side": (0.00, 0.90, 0.25),
    "right_side": (0.00, -0.90, 0.25),
    "front": (0.90, 0.00, 0.25),
}

VIEW_LABELS = {
    "rear_above": "rear and above",
    "top_down": "top-down",
    "left_side": "left side",
    "right_side": "right side",
    "front": "front",
    "manual": "manual (free mouse look)",
}


def _service(name, reqtype, req):
    """Returns None on success, or a message for the instructor console."""
    try:
        result = subprocess.run([
            "gz", "service", "-s", name,
            "--reqtype", reqtype,
            "--reptype", "gz.msgs.Boolean",
            "--timeout", "2000",
            "--req", req,
        ], capture_output=True, text=True)
    except OSError as exc:
        return f"cannot run gz ({exc.strerror})"
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip().splitlines()
        return detail[0] if detail else f"gz service exited {result.returncode}"
    return None


def set_view(view, distance_m):
    """Point the Gazebo camera at the aircraft from the named viewpoint."""
    if view == "manual":
        error = _service("/gui/follow", "gz.msgs.StringMsg", 'data: ""')
        if error:
            return f"View not changed - {error}"
        return ("Manual view: camera released. Drag with the left mouse button in the "
                "Gazebo window to look around, scroll to zoom.")

    if view not in VIEWS:
        return f"View not changed - '{view}' is not a known viewpoint."
    try:
        distance = float(distance_m)
    except (TypeError, ValueError):
        return f"View not changed - '{distance_m}' is not a distance in metres."
    if distance <= 0:
        return "View not changed - distance must be greater than 0 m."

    # Target first: the offset service ignores the request when no target is
    # set, so the order of these two calls matters.
    error = _service("/gui/follow", "gz.msgs.StringMsg", f'data: "{MODEL}"')
    if error:
        return f"View not changed - {error}"

    fwd, left, up = (axis * distance for axis in VIEWS[view])
    error = _service("/gui/follow/offset", "gz.msgs.Vector3d",
                     f"x: {fwd:.2f}, y: {left:.2f}, z: {up:.2f}")
    if error:
        return f"Following the aircraft, but the offset was not applied - {error}"

    return f"External view: {VIEW_LABELS[view]}, {distance:g} m from the aircraft."
