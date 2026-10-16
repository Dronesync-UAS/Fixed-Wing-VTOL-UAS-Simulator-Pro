"""Puts natural and man-made features into the training worlds:

    python3 tools/scenery_apply.py                 # every world
    python3 tools/scenery_apply.py --world uyuni   # just one
    python3 tools/scenery_apply.py --dry-run       # show what it would do
    python3 tools/scenery_apply.py --revert        # put the backups back

WHY. Every world was bare ground. That was survivable when the only
pictures were a nose camera at the horizon and a chase camera at the
aircraft; it is not survivable now there is a gimbal, because a sensor
operator cannot be taught to find and hold a target in an empty desert.
scenery.py is what goes in each place, and why those things; this file
only writes it.

WHAT IT TOUCHES. The world files in sim/worlds, which ARE tracked by
git - unlike the aircraft model, which is PX4's. Each one is backed up
to <name>.sdf.prescenery first, the result is parsed as XML, and
anything that fails to parse is put back automatically. Running it twice
does nothing the second time.

THE COST. Between 40 and 130 static models per world, all built from
boxes, cylinders and spheres - no meshes, so nothing has to be installed
and no resource path has to resolve. That is more for Gazebo to draw
than an empty plane, on a machine whose graphics were already called
marginal. If the simulator slows noticeably, --revert takes it all out
again, and sim/worlds/flat_test.sdf is deliberately left bare so there is
always one world to fall back to.
"""
import os
import shutil
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import scenery                                              # noqa: E402
import sim_target                                           # noqa: E402

WORLDS_DIR = os.path.join(REPO, "sim", "worlds")
SUFFIX = ".prescenery"
MARKER = "<!-- SCENERY: added by tools/scenery_apply.py"


def _material(colour, surface=scenery.DEFAULT_SURFACE):
    """One object's material, including how it behaves in light.

    THE <pbr> BLOCK, added 12 Oct 2026. Until then every object in every
    world carried the same flat material, so water, a painted container,
    wet mud and a hedge all caught light identically - a large part of
    why the scenery read as coloured cardboard.

    ROUGHNESS AND METALNESS ARE SCALARS HERE, not texture maps, and that
    is the whole trick. A box face in SDF maps one texture across its
    entire face, so a brick image on a 14 m wall would be one enormous
    brick. These two numbers need no texture coordinates at all, so they
    improve every object immediately and cannot be stretched wrong.

    The ambient and diffuse are kept as well: ogre2 uses the PBR block,
    and anything that falls back to the simple path still gets a colour
    rather than white.
    """
    r, g, b = colour
    roughness, metalness = scenery.SURFACES.get(
        surface, scenery.SURFACES[scenery.DEFAULT_SURFACE])
    return ("<material><ambient>%g %g %g 1</ambient>"
            "<diffuse>%g %g %g 1</diffuse>"
            "<specular>0.04 0.04 0.04 1</specular>"
            "<pbr><metal>"
            "<roughness>%g</roughness>"
            "<metalness>%g</metalness>"
            "</metal></pbr></material>"
            % (r * 0.55, g * 0.55, b * 0.55, r, g, b, roughness, metalness))


def _part_xml(kind, a, index):
    """One visual (and its collision, if it is an obstacle)."""
    name = "p%d" % index
    if kind == "box":
        geometry = "<box><size>%g %g %g</size></box>" % (a["sx"], a["sy"], a["sz"])
        pose = "%g %g %g 0 0 %g" % (a["x"], a["y"], a["z"], a.get("yaw", 0.0))
    elif kind == "cylinder":
        geometry = ("<cylinder><radius>%g</radius><length>%g</length></cylinder>"
                    % (a["r"], a["h"]))
        pose = "%g %g %g 0 %g %g" % (a["x"], a["y"], a["z"],
                                     a.get("pitch", 0.0), a.get("yaw", 0.0))
    elif kind == "sphere":
        squash = a.get("squash", 1.0)
        if abs(squash - 1.0) < 1e-6:
            geometry = "<sphere><radius>%g</radius></sphere>" % a["r"]
        else:
            # A bush, a tree canopy and a pond are all wider than they
            # are tall. SDF 1.9 has <ellipsoid> for exactly this, so it
            # is used rather than a sphere sunk into the ground - a sunk
            # sphere looks right from directly above and wrong from the
            # side, which is the angle the chase camera sees it from.
            geometry = ("<ellipsoid><radii>%g %g %g</radii></ellipsoid>"
                        % (a["r"], a["r"], a["r"] * squash))
        pose = "%g %g %g 0 0 0" % (a["x"], a["y"], a["z"])
    elif kind == "cone":
        # A cone drawn as a cylinder: gz-sim 8 does gain a <cone> in
        # later releases, and relying on it would make these worlds
        # refuse to load on the version this project is pinned to.
        geometry = ("<cylinder><radius>%g</radius><length>%g</length></cylinder>"
                    % (a["r"] * 0.72, a["h"]))
        pose = "%g %g %g 0 0 0" % (a["x"], a["y"], a["z"] + a["h"] / 2)
    else:
        return ""
    out = ('<visual name="%s"><pose>%s</pose><geometry>%s</geometry>%s</visual>'
           % (name, pose, geometry,
              _material(a["colour"],
                        a.get("surface", scenery.DEFAULT_SURFACE))))
    if a.get("collide"):
        out += ('<collision name="%s_c"><pose>%s</pose><geometry>%s</geometry>'
                '<surface><friction><ode/></friction><bounce/><contact/>'
                '</surface></collision>' % (name, pose, geometry))
    return out


def model_xml(index, yaw, x, y, parts):
    body = "".join(_part_xml(kind, args, n)
                   for n, (kind, args) in enumerate(parts))
    return ('    <model name="scenery_%d">\n'
            '      <static>true</static>\n'
            '      <pose>%g %g 0 0 0 %g</pose>\n'
            '      <link name="l">%s</link>\n'
            '    </model>\n' % (index, x, y, yaw, body))


def block(world):
    items = scenery.layout(world)
    if not items:
        return None
    out = ("    %s.\n"
           "         %d features, laid out deterministically from the world's\n"
           "         own name - see scenery.py for what is here and why. The\n"
           "         first %g m around the launch point is left clear. Payload\n"
           "         targets 1-3 are at %s. -->\n"
           % (MARKER, len(items), scenery.CLEAR_RADIUS_M,
              ", ".join("%d: %03d deg / %g m" % (t["number"], t["bearing_deg"],
                                                 t["range_m"])
                        for t in scenery.target_positions())))
    for index, (yaw, x, y, parts) in enumerate(items):
        out += model_xml(index, yaw, x, y, parts)
    return out


def _world_path(world):
    return os.path.join(WORLDS_DIR, world + ".sdf")


def _apply_one(world, dry_run):
    path = _world_path(world)
    if not os.path.isfile(path):
        print("SKIP  %s - no such world file" % world)
        return 0
    text = open(path).read()
    if MARKER in text:
        print("SKIP  %s already has its scenery." % world)
        return 0
    added = block(world)
    if added is None:
        print("SKIP  %s has no theme in scenery.WORLD_THEMES." % world)
        return 0
    at = text.rfind("</world>")
    if at < 0:
        print("Cannot add scenery to %s - no </world>" % world, file=sys.stderr)
        return 1
    result = text[:at] + added + text[at:]

    if dry_run:
        items = scenery.layout(world)
        print("WOULD EDIT %s" % path)
        print("  %d features, %d shapes, %d lines"
              % (len(items), sum(len(p[3]) for p in items),
                 added.count("\n")))
        return 0

    backup = path + SUFFIX
    if not os.path.exists(backup):
        shutil.copy2(path, backup)
    with open(path, "w") as handle:
        handle.write(result)
    try:
        ET.parse(path)
    except ET.ParseError as exc:
        shutil.copy2(backup, path)
        print("FAILED: %s - the edit broke the XML (%s), restored."
              % (world, exc), file=sys.stderr)
        return 1
    print("OK    %s - %d features added" % (world, len(scenery.layout(world))))
    return 0


def revert():
    done = 0
    for world in scenery.WORLD_THEMES:
        path = _world_path(world)
        backup = path + SUFFIX
        if os.path.exists(backup):
            shutil.copy2(backup, path)
            print("Restored %s" % os.path.basename(path))
            done += 1
    if not done:
        print("No %s backups found - nothing to restore." % SUFFIX)
    else:
        print("Restart the simulator for it to take effect.")
    return 0


def main(argv):
    if "--revert" in argv:
        return revert()
    dry = "--dry-run" in argv
    only = None
    if "--world" in argv:
        key = argv[argv.index("--world") + 1]
        entry = sim_target.BY_KEY.get(key)
        only = entry["world"] if entry else key
    worlds = [only] if only else list(scenery.WORLD_THEMES)
    bad = 0
    for world in worlds:
        bad += _apply_one(world, dry)
    if not dry and not bad:
        print("""
Next:

1. Restart the simulator - the Stop icon, then the start icon.

2. Choose the Payload view and look around. The three marked targets
   are listed in docs/scenery-targets.md.

To take it all out again:
     python3 tools/scenery_apply.py --revert""")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
