"""Sets each world's <magnetic_field> to the real field at its own coordinates:

    python3 tools/fix_magnetic_field.py --dry-run
    python3 tools/fix_magnetic_field.py
    python3 tools/fix_magnetic_field.py --revert

The problem. All five worlds carry
`<magnetic_field>6e-06 2.3e-05 -4.2e-05</magnetic_field>`, which is sdformat's
own default value (spec default: 5.5645e-6 22.8758e-6 -42.3884e-6) rounded off -
not a value for anywhere these worlds are set. The five worlds are four
genuinely different places, two of them in the southern hemisphere where the
field's vertical component points the other way.

Why it only started mattering today. Until the Magnetometer system was added
(tools/add_world_systems.py) nothing simulated a magnetometer, so the world's
magnetic field had no consumer. Now PX4 receives a simulated field and compares
it against what its own world-magnetic model expects at the GPS position. With
the placeholder in place the two disagree badly, and the EKF will not converge
on a heading - which presents exactly as the repeating
"Preflight Fail: Yaw estimate error" seen on 11 Oct, and which blocks arming.

How wrong the placeholder is, per world (placeholder: 48260 nT, declination
14.62 deg, inclination 60.49 deg):

    Hoggar, Algeria    38264 nT, decl  1.53, incl  28.08  -> 32 deg inclination error
    Black Rock, USA    49607 nT, decl 12.82, incl  64.24  ->  4 deg
    Nullarbor, AU      58088 nT, decl  3.68, incl -64.31  -> 125 deg, sign inverted
    Uyuni, Bolivia     22410 nT, decl -9.33, incl -19.27  -> 80 deg, sign inverted

Where the numbers come from. Computed from the IGRF model via the `ppigrf`
package for each world's own declared latitude, longitude and elevation, at
2026-10-11. Not estimated, not copied from another world. The secular drift of
the field is small enough (tens of nT a year) that these stay good for years;
recompute if a world's coordinates change.

Units and frame are per the SDF spec: tesla, in the frame set by
`<spherical_coordinates>` - ENU in these worlds, so the vector is
(East, North, Up). A negative Up component means the field points into the
ground, as it does in the northern hemisphere.

Each world is checked against the coordinates its value was computed for and
skipped if they no longer match, so a moved world gets a clear message instead
of a wrong field. Backups go to <name>.sdf.premag, the result is re-parsed as
XML, and anything that fails to parse is restored.
"""
import glob
import os
import re
import shutil
import sys
import xml.etree.ElementTree as ET

WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
SUFFIX = ".premag"

# world file -> (place, latitude, longitude, elevation m, East T, North T, Up T)
FIELDS = {
    "training_area.sdf":
        ("Hoggar Mountains, Algeria", 23.2667, 5.6333, 1400.0,
         9.01e-07, 3.375e-05, -1.801e-05),
    "flat_test.sdf":
        ("Hoggar Mountains, Algeria", 23.2667, 5.6333, 1400.0,
         9.01e-07, 3.375e-05, -1.801e-05),
    "training_area_blackrock.sdf":
        ("Black Rock Desert, USA", 40.87498, -119.08493, 1190.0,
         4.785e-06, 2.102e-05, -4.468e-05),
    "training_area_nullarbor.sdf":
        ("Nullarbor Plain, Australia", -31.49561, 129.04713, 97.0,
         1.615e-06, 2.513e-05, 5.235e-05),
    "training_area_uyuni.sdf":
        ("Salar de Uyuni, Bolivia", -20.14322, -67.55527, 3651.0,
         -3.429e-06, 2.087e-05, 7.394e-06),
}

MAG_RE = re.compile(r"(<magnetic_field>)([^<]*)(</magnetic_field>)")


def revert():
    restored = 0
    for backup in sorted(glob.glob(os.path.join(WORLDS, "*.sdf" + SUFFIX))):
        target = backup[: -len(SUFFIX)]
        shutil.copy2(backup, target)
        print(f"restored {os.path.basename(target)}")
        restored += 1
    print(f"\n{restored} file(s) restored." if restored else
          f"\nNo {SUFFIX} backups found - nothing to restore.")
    return 0


def declared_coords(path):
    try:
        world = ET.parse(path).getroot().find("world")
        sc = world.find("spherical_coordinates")
        return (float(sc.findtext("latitude_deg")),
                float(sc.findtext("longitude_deg")))
    except (ET.ParseError, AttributeError, TypeError, ValueError):
        return None


def apply(dry_run):
    changed = skipped = failed = 0
    for name in sorted(FIELDS):
        path = os.path.join(WORLDS, name)
        place, lat, lon, elev, east, north, up = FIELDS[name]
        if not os.path.isfile(path):
            print(f"SKIP  {name}: not installed in {WORLDS}")
            skipped += 1
            continue

        coords = declared_coords(path)
        if coords is None:
            print(f"SKIP  {name}: could not read its spherical_coordinates")
            skipped += 1
            continue
        if abs(coords[0] - lat) > 0.001 or abs(coords[1] - lon) > 0.001:
            print(f"SKIP  {name}: world is at {coords[0]}, {coords[1]} but this "
                  f"field was computed for {lat}, {lon} - recompute before using")
            skipped += 1
            continue

        with open(path) as fh:
            text = fh.read()
        match = MAG_RE.search(text)
        if not match:
            print(f"SKIP  {name}: no <magnetic_field> element")
            skipped += 1
            continue

        wanted = f"{east:.4g} {north:.4g} {up:.4g}"
        if match.group(2).strip() == wanted:
            print(f"SKIP  {name}: already correct for {place}")
            skipped += 1
            continue

        if dry_run:
            print(f"WOULD SET {name}: {match.group(2).strip()}  ->  {wanted}   ({place})")
            changed += 1
            continue

        backup = path + SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as fh:
            fh.write(MAG_RE.sub(lambda m: m.group(1) + wanted + m.group(3), text, count=1))

        try:
            ET.parse(path)
        except ET.ParseError as exc:
            shutil.copy2(backup, path)
            print(f"FAIL  {name}: XML broke ({exc}) - reverted")
            failed += 1
            continue

        print(f"OK    {name}: {wanted}   ({place})")
        changed += 1

    print(f"\nchanged={changed} skipped={skipped} failed={failed}")
    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    elif changed and not failed:
        print("""
Restart the simulator - Gazebo reads the magnetic field at load:

  bash ~/PX4-Autopilot/gcs_app/tools/start_flat_test.sh

Then watch for "Preflight Fail: Yaw estimate error". If it stops, the
placeholder field was the cause and arming should work normally. If it
continues, say so - the next suspect is PX4's own EKF mag settings, not the
world, and this change is still correct on its own terms.

To undo:  python3 tools/fix_magnetic_field.py --revert""")
    return 1 if failed else 0


if __name__ == "__main__":
    if "--revert" in sys.argv:
        sys.exit(revert())
    sys.exit(apply("--dry-run" in sys.argv))
