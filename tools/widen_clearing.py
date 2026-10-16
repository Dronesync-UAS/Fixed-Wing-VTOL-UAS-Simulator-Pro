"""Widens the flat clearing in the training world's heightmap:

    python3 tools/widen_clearing.py --dry-run
    python3 tools/widen_clearing.py
    python3 tools/widen_clearing.py --revert

The problem it fixes. The carved clearing is flat out to about 400 m from the
spawn. Beyond that the real Hoggar terrain rises fast - measured from the
heightmap itself, +235 m above home within 600 m, and +397 m within 800 m.
The operating limits in instructor_station.py are a 500 m range from home and
a 120 m ceiling. So outside 400 m there is no airspace a student can legally
use: at the 120 m ceiling they are already 115 m below ground in places. Flying
at the default ~9 m takeoff altitude puts the aircraft among rock spires as
soon as it leaves the clearing, which is exactly what was seen on 11 Oct.

The fix is to make the flat area match the limits rather than to fly outside
them: flat to 600 m (comfortably past the 500 m range limit), then blended
smoothly back into the real terrain by 1000 m so there is no cliff at the
join. Everything beyond 1000 m is untouched real SRTM data, so the scenery and
the terrain-awareness value of the world are kept.

Why not simply fly higher: climbing above 400 m to clear the ridges breaks the
120 m ceiling the training is built around. The limits model real UK rules and
are the point of the exercise, so the terrain gives way, not the limits.

Only the Hoggar heightmap is touched - the other three worlds have their own
terrain and their own clearings, and are left alone. The heightmap is backed
up alongside itself before any change, and --revert puts it back.
"""
import math
import os
import shutil
import sys

from PIL import Image

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
REPO_WORLDS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "sim", "worlds")
HEIGHTMAP = os.path.join("media", "hoggar_real_heightmap.png")
SUFFIX = ".preclearing"

# From the world file: <size>4000 4000 1151</size> and the terrain model's
# <pose>-779.7 0 0>. The spawn is the world origin.
TERRAIN_SIZE_M = 4000.0
TERRAIN_Z_M = 1151.0
TERRAIN_POSE_X = -779.7
TERRAIN_POSE_Y = 0.0

FLAT_RADIUS_M = 600.0     # fully flat - past the 500 m range limit
BLEND_RADIUS_M = 1000.0   # blended back into real terrain by here


def targets():
    """Both copies: the live one PX4 loads, and the repo's backup copy."""
    found = []
    for base in (PX4_WORLDS, REPO_WORLDS):
        path = os.path.join(base, HEIGHTMAP)
        if os.path.isfile(path):
            found.append(path)
    return found


def revert():
    restored = 0
    for path in targets():
        backup = path + SUFFIX
        if os.path.isfile(backup):
            shutil.copy2(backup, path)
            print(f"restored {path}")
            restored += 1
    print(f"\n{restored} file(s) restored." if restored else
          f"\nNo {SUFFIX} backups found - nothing to restore.")
    return 0


def carve(path, dry_run):
    with Image.open(path) as source:
        grey = source.convert("L")
        width, height = grey.size
        pixels = list(grey.getdata())

    metres_per_px = TERRAIN_SIZE_M / (width - 1)
    centre_col = (width - 1) / 2.0 + (0.0 - TERRAIN_POSE_X) / metres_per_px
    centre_row = (height - 1) / 2.0 + (0.0 - TERRAIN_POSE_Y) / metres_per_px

    level = pixels[int(round(centre_row)) * width + int(round(centre_col))]
    print(f"  {os.path.basename(path)}: {width}x{height}, {metres_per_px:.2f} m/px")
    print(f"    spawn pixel ({centre_col:.0f}, {centre_row:.0f}), clearing level "
          f"{level}/255 = {level / 255 * TERRAIN_Z_M:.1f} m")

    flat_px = FLAT_RADIUS_M / metres_per_px
    blend_px = BLEND_RADIUS_M / metres_per_px
    changed = 0
    out = list(pixels)
    for row in range(height):
        dy = row - centre_row
        for col in range(width):
            distance = math.hypot(col - centre_col, dy)
            if distance >= blend_px:
                continue
            if distance <= flat_px:
                new = level
            else:
                # Smoothstep across the blend band: no cliff at either join,
                # which a linear ramp would leave at the outer edge.
                t = (distance - flat_px) / (blend_px - flat_px)
                t = t * t * (3 - 2 * t)
                new = int(round(level * (1 - t) + pixels[row * width + col] * t))
            if new != pixels[row * width + col]:
                out[row * width + col] = new
                changed += 1

    print(f"    flat to {FLAT_RADIUS_M:.0f} m, blended out to {BLEND_RADIUS_M:.0f} m; "
          f"{changed} pixels changed")
    if dry_run:
        return

    backup = path + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    image = Image.new("L", (width, height))
    image.putdata(out)
    image.save(path)
    print(f"    written (backup at {os.path.basename(backup)})")


def main(dry_run):
    paths = targets()
    if not paths:
        print(f"Heightmap not found in {PX4_WORLDS} or {REPO_WORLDS}")
        return 1
    for path in paths:
        carve(path, dry_run)
    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    else:
        print(f"""
Restart the simulator so Gazebo reloads the terrain:

  pkill -f 'bin/px4'; pkill -f 'gz sim'; sleep 2; rm -rf /tmp/px4*
  bash ~/PX4-Autopilot/start_training_area.sh

You now have flat ground to {FLAT_RADIUS_M:.0f} m, past the 500 m range limit, with the
real mountains still there beyond {BLEND_RADIUS_M:.0f} m as scenery and for terrain awareness.

To undo:  python3 tools/widen_clearing.py --revert""")
    return 0


if __name__ == "__main__":
    if "--revert" in sys.argv:
        sys.exit(revert())
    sys.exit(main("--dry-run" in sys.argv))
