"""
Shaded-relief backdrop for the flight-path plan view, rendered from the
running world's own heightmap.

Added 11 Oct 2026 on request for "a satellite view rather than black
background". Deliberately built from the heightmap rather than satellite
imagery: it is the ground the student is actually flying over, not a
photograph of somewhere that looks similar; it works with no internet, no API
key and no licence terms, which matters for a station that has to run offline;
and it already exists in the repo.

How the placement is worked out, from the world file rather than assumed:
  * <heightmap><size>W H Z</size> gives the terrain's extent in metres
  * the terrain model's <pose> gives where that extent sits in the world
  * the world is ENU, so world X is east and world Y is north - the same axes
    the plan view already draws in

The plan view measures metres from home, and home is the spawn point at the
world origin, so world metres and plan-view metres line up directly. If the
spawn point ever moves away from the origin this needs the home position
subtracting.

IMAGE ORIENTATION IS NOT CONFIRMED. Gazebo's mapping from image row to world
Y is not documented in a way worth trusting, so FLIP_NORTH_SOUTH below is a
single switch. Check it against a feature you can recognise - fly to a ridge
and see whether it is where the backdrop says - and flip it if it is mirrored.
"""

import io
import os
import re
import threading
import xml.etree.ElementTree as ET

from PIL import Image

import sim_target

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")

# See the note above - flip this if the relief comes out mirrored north/south.
FLIP_NORTH_SOUTH = True

# The backdrop sits under a cyan track and a yellow aircraft marker, so it is
# rendered dark and low-contrast on purpose. Readability of the track wins.
RELIEF_MAX_ALPHA = 150
SUN_FROM_NORTHWEST = True

_cache = {"png": None, "info": None}
_lock = threading.Lock()


def reset():
    """Forget the rendered relief. Called when the world changes - the
    backdrop is per-world, and a stale one would show the wrong terrain under
    the new world's track."""
    with _lock:
        _cache["png"] = None
        _cache["info"] = None


def _world_file():
    path = os.path.join(PX4_WORLDS, f"{sim_target.WORLD}.sdf")
    return path if os.path.isfile(path) else None


def _find_terrain(world_path):
    """(heightmap file, size_x, size_y, pose_x, pose_y) or None.

    Returns the first model containing a heightmap - these worlds have one.
    """
    try:
        root = ET.parse(world_path).getroot()
    except ET.ParseError:
        return None
    world = root.find("world")
    if world is None:
        return None

    for model in world.findall("model"):
        heightmap = None
        for element in model.iter("heightmap"):
            heightmap = element
            break
        if heightmap is None:
            continue

        uri = (heightmap.findtext("uri") or "").strip()
        if uri.startswith("file://"):
            uri = uri[len("file://"):]
        image_path = os.path.normpath(os.path.join(PX4_WORLDS, uri))
        if not os.path.isfile(image_path):
            continue

        size = (heightmap.findtext("size") or "").split()
        if len(size) < 2:
            continue
        pose = (model.findtext("pose") or "0 0 0 0 0 0").split()
        return (image_path, float(size[0]), float(size[1]),
                float(pose[0]) if pose else 0.0,
                float(pose[1]) if len(pose) > 1 else 0.0)
    return None


def info():
    """Where the backdrop belongs, in the plan view's own metres-from-home
    axes. {"available": False} when the world has no heightmap - flat_test
    has none, and the plan view simply stays as it was."""
    with _lock:
        if _cache["info"] is not None:
            return _cache["info"]

        world_path = _world_file()
        terrain = _find_terrain(world_path) if world_path else None
        if terrain is None:
            result = {"available": False, "world": sim_target.WORLD}
        else:
            _, size_x, size_y, pose_x, pose_y = terrain
            result = {
                "available": True,
                "world": sim_target.WORLD,
                "east_min": pose_x - size_x / 2.0,
                "east_max": pose_x + size_x / 2.0,
                "north_min": pose_y - size_y / 2.0,
                "north_max": pose_y + size_y / 2.0,
            }
        _cache["info"] = result
        return result


def _shade(heights, width, height):
    """Hillshade plus a muted hypsometric tint, as RGBA bytes.

    Pure PIL and arithmetic - no numpy, so this works wherever the station
    already runs. A 513x513 heightmap is small enough that the cost is a
    one-off fraction of a second, and the result is cached.
    """
    lowest, highest = min(heights), max(heights)
    span = max(1, highest - lowest)

    # Light from the north-west, the cartographic convention: relief read
    # under any other lighting tends to invert into hollows by eye.
    dx_sun, dy_sun = (-1, -1) if SUN_FROM_NORTHWEST else (1, 1)

    out = bytearray(width * height * 4)
    for y in range(height):
        row = y * width
        y_prev = max(0, y - 1) * width
        y_next = min(height - 1, y + 1) * width
        for x in range(width):
            x_prev = max(0, x - 1)
            x_next = min(width - 1, x + 1)

            slope_x = heights[row + x_next] - heights[row + x_prev]
            slope_y = heights[y_next + x] - heights[y_prev + x]
            shade = 0.5 + 0.06 * (dx_sun * slope_x + dy_sun * slope_y)
            shade = 0.0 if shade < 0.0 else (1.0 if shade > 1.0 else shade)

            # Low ground blue-grey, high ground warm - enough to read terrain
            # at a glance without competing with the track colours.
            level = (heights[row + x] - lowest) / span
            red = 40 + 150 * level
            green = 55 + 130 * level
            blue = 70 + 60 * level

            index = (row + x) * 4
            out[index] = int(red * shade)
            out[index + 1] = int(green * shade)
            out[index + 2] = int(blue * shade)
            out[index + 3] = RELIEF_MAX_ALPHA
    return bytes(out)


def png():
    """The backdrop as PNG bytes, or None if this world has no heightmap."""
    with _lock:
        if _cache["png"] is not None:
            return _cache["png"]

    world_path = _world_file()
    terrain = _find_terrain(world_path) if world_path else None
    if terrain is None:
        return None

    image_path = terrain[0]
    with Image.open(image_path) as source:
        grey = source.convert("L")
        width, height = grey.size
        if FLIP_NORTH_SOUTH:
            grey = grey.transpose(Image.FLIP_TOP_BOTTOM)
        heights = list(grey.getdata())

    shaded = Image.frombytes("RGBA", (width, height), _shade(heights, width, height))
    buffer = io.BytesIO()
    shaded.save(buffer, format="PNG")
    data = buffer.getvalue()

    with _lock:
        _cache["png"] = data
    return data
