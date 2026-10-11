"""Adds a runtime-controllable weather cell to the training worlds:

    python3 tools/weather_apply.py            # edit every training world
    python3 tools/weather_apply.py --dry-run  # show the change, write nothing
    python3 tools/weather_apply.py --revert   # put the backups back

Mirrors tools/wind_apply.py, including its safety: every file is backed up to
<name>.sdf.preweather first, the result is parsed as XML, and anything that
fails to parse is restored automatically. Re-running is harmless.

WHAT GETS ADDED, and why it is shaped this way
----------------------------------------------
Two things before </world>:

  the ParticleEmitter system plugin
      filename="gz-sim-particle-emitter-system",
      name="gz::sim::systems::ParticleEmitter".
      Safe to add only because these worlds already declare their own
      systems - gz-sim8 skips its entire default system set once a world
      declares any, so adding a plugin to a world that declared none would
      silently remove physics, IMU, NavSat and the camera. Same reasoning
      wind_apply.py records, checked by tools/wind_survey.py.

  a static model "weather_cell" holding two particle emitters
      fog  - large, slow, scaling billboards. This is how Gazebo itself does
             fog: gz-sim8's own examples/worlds/particle_emitter.sdf calls a
             particle emitter a "fog_generator". There is no alternative -
             gz-rendering8 has NO fog API at all (zero occurrences of "fog"
             in Scene.hh, and zero in gz-sim8's RenderUtil.cc, both checked
             11 Oct 2026), so particles are not a workaround for fog, they
             are the mechanism.
      rain - small, fast, falling particles.

Both start with <emitting>false</emitting>, so adding this changes nothing
until an instructor turns it on - the same rule wind followed.

VALUES THAT ARE NOT ARBITRARY
-----------------------------
Emission direction is the emitter's own local +X. Not a guess:
gz-rendering8's Ogre2ParticleEmitter::CreateParticleSystem() calls
setDirection(Ogre::Vector3::UNIT_X) and nothing else ever changes it. So
rain needs its emitter pitched 90 degrees about Y, which maps local +X onto
world -Z: straight down. Fog drifts and needs no rotation.

Ogre's particle quota is 5000 per emitter (setParticleQuota(5000) in the
same function). Particles alive at once is roughly rate x lifetime, so the
rate ceiling is 5000/lifetime: ~200/s for fog's 25 s, ~1250/s for rain's
4 s. The station's intensity settings stay under that ceiling on purpose -
exceed it and Ogre silently stops emitting rather than erroring.

Particle size is read as (width, height) ONLY. Ogre2ParticleEmitter uses
particleSize[0] and particleSize[1] and never touches [2], so a value in Z
is silently discarded. The first version of this file put rain's streak
length in Z and got 8 cm squares - visible as "heavy rain is not much rain",
which is exactly how a silently-ignored field presents.

Ground height differs by world - Black Rock's playa is at ~1 m, Hoggar's
clearing at ~605 m - so the model is placed at each world's own ground
height, taken from sim_target, and the emitters sit at heights ABOVE that.
A fixed world Z would bury the weather 600 m underground in Hoggar.

WHAT THIS DOES NOT DO
---------------------
It does not affect how the aircraft flies. Particles are rendering only;
nothing in gz-sim8 couples them to aerodynamics. Wind is the only weather
that touches the flight model, and that already works through the station's
wind control. This degrades what the camera sees, which is a real training
scenario - flying into a cell - but it must not be described as flying in
weather.
"""
import os
import sys
import shutil
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
import sim_target                                            # noqa: E402

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
REPO_WORLDS = os.path.join(REPO, "sim", "worlds")
SUFFIX = ".preweather"

FOG_TOPIC = "/weather/fog"
RAIN_TOPIC = "/weather/rain"

BLOCK = """\
{i}<!-- Weather cell. Switched on at runtime by the instructor station over
{i}     {fog_topic} and {rain_topic} (gz.msgs.ParticleEmitter);
{i}     both start off, so an untouched sim looks exactly as it did before.
{i}     Rendering only - this does not change how the aircraft flies.
{i}     Added by tools/weather_apply.py. -->
{i}<plugin filename="gz-sim-particle-emitter-system"
{i}        name="gz::sim::systems::ParticleEmitter">
{i}</plugin>
{i}<model name="weather_cell">
{i}  <static>true</static>
{i}  <!-- At this world's own ground height; emitter heights below are
{i}       relative to it, so the cell sits over the ground in every world. -->
{i}  <pose>0 0 {ground} 0 0 0</pose>
{i}  <link name="weather_link">
{i}    <particle_emitter name="fog" type="box">
{i}      <topic>{fog_topic}</topic>
{i}      <emitting>false</emitting>
{i}      <!-- Tighter than the first attempt (was 240 x 240): the same
{i}           particle budget spread over a quarter of the area is four times
{i}           the obscuration. -->
{i}      <pose>0 0 45 0 0 0</pose>
{i}      <size>120 120 30</size>
{i}      <!-- X and Y only; Z is ignored (see the rain emitter below). -->
{i}      <particle_size>18 18 0</particle_size>
{i}      <lifetime>25</lifetime>
{i}      <min_velocity>0.1</min_velocity>
{i}      <max_velocity>0.5</max_velocity>
{i}      <scale_rate>0.5</scale_rate>
{i}      <rate>160</rate>
{i}      <particle_scatter_ratio>0.9</particle_scatter_ratio>
{i}      <material>
{i}        <diffuse>0.85 0.87 0.90</diffuse>
{i}        <specular>0.85 0.87 0.90</specular>
{i}      </material>
{i}    </particle_emitter>
{i}    <!-- Pitched 90 degrees about Y so the emitter's local +X, which is the
{i}         only direction Ogre2ParticleEmitter ever emits along, points at
{i}         world -Z. Without this, rain falls sideways. -->
{i}    <particle_emitter name="rain" type="box">
{i}      <topic>{rain_topic}</topic>
{i}      <emitting>false</emitting>
{i}      <!-- 45 m, not 95: the fall time sets the lifetime, the lifetime sets
{i}           the rate ceiling (quota/lifetime), and the rate sets how much
{i}           rain you can actually see. Halving the drop roughly trebles the
{i}           rain. 45 m at 12-16 m/s is ~3.2 s, inside the 4 s lifetime. -->
{i}      <pose>0 0 45 0 1.5707963 0</pose>
{i}      <size>70 70 0</size>
{i}      <!-- Only X and Y are read - Ogre2ParticleEmitter passes them to
{i}           setDefaultDimensions(width, height) and ignores Z. 0.12 x 2.0 is
{i}           a falling streak; the first attempt put the length in Z and so
{i}           rendered 8 cm squares, which is why heavy rain looked like
{i}           almost nothing. -->
{i}      <particle_size>0.12 2.0 0</particle_size>
{i}      <lifetime>4</lifetime>
{i}      <min_velocity>12</min_velocity>
{i}      <max_velocity>16</max_velocity>
{i}      <scale_rate>0</scale_rate>
{i}      <rate>450</rate>
{i}      <particle_scatter_ratio>0.4</particle_scatter_ratio>
{i}      <material>
{i}        <diffuse>0.60 0.68 0.78</diffuse>
{i}        <specular>0.60 0.68 0.78</specular>
{i}      </material>
{i}    </particle_emitter>
{i}  </link>
{i}</model>
"""


def world_paths():
    """Each training world once, from the copy the simulator actually loads.

    PX4's tree wins where the world exists there, and this repo's copy is
    used only for a world PX4 has never seen - flat_test, which lives here
    and is installed into PX4's tree at launch.

    FIXED 11 Oct 2026: this used to return BOTH copies of every world. It
    did keep them in step, but it edited files under git, so a routine
    `git pull` then refused with "local changes would be overwritten" - the
    same trap that cost half an hour earlier the same day. The repo's copies
    carry the weather cell as committed content instead.
    """
    found = []
    for env in sim_target.ENVIRONMENTS:
        name = env["world"] + ".sdf"
        px4 = os.path.join(PX4_WORLDS, name)
        repo = os.path.join(REPO_WORLDS, name)
        if os.path.isfile(px4):
            found.append((px4, env))
        elif os.path.isfile(repo):
            found.append((repo, env))
    return found


def revert():
    restored = 0
    for path, _ in world_paths():
        backup = path + SUFFIX
        if os.path.exists(backup):
            shutil.copy2(backup, path)
            print("restored %s from backup" % os.path.basename(path))
            restored += 1
    print("\n%d file(s) restored." % restored if restored else
          "\nNo %s backups found - nothing to restore." % SUFFIX)
    return 0


def apply(dry_run):
    paths = world_paths()
    if not paths:
        print("No training worlds found in %s or %s" % (PX4_WORLDS, REPO_WORLDS))
        return 1

    edited = skipped = failed = 0
    for path, env in paths:
        name = os.path.basename(path)
        with open(path) as handle:
            lines = handle.read().splitlines(keepends=True)
        joined = "".join(lines)

        if "weather_cell" in joined or "ParticleEmitter" in joined:
            print("SKIP  %s: already has a weather cell (%s)"
                  % (name, os.path.dirname(path)))
            skipped += 1
            continue

        close = next((n for n, line in enumerate(lines)
                      if line.strip() == "</world>"), None)
        if close is None:
            print("SKIP  %s: no </world> line found - left alone" % name)
            skipped += 1
            continue

        indent = lines[close][: len(lines[close]) - len(lines[close].lstrip())]
        # The spawn height is "just above this world's ground", which is the
        # reference the weather cell wants too.
        ground = round(float(env["spawn_z"]), 1)
        block = BLOCK.format(i=indent + "  ", ground=ground,
                             fog_topic=FOG_TOPIC, rain_topic=RAIN_TOPIC)

        if dry_run:
            print("WOULD EDIT %s: insert %d lines before line %d (ground %sm)"
                  % (name, block.count("\n"), close + 1, ground))
            edited += 1
            continue

        backup = path + SUFFIX
        if not os.path.exists(backup):
            shutil.copy2(path, backup)
        with open(path, "w") as handle:
            handle.writelines(lines[:close] + [block] + lines[close:])

        # A world that no longer parses stops the sim launching at all, so
        # undo rather than leave it broken.
        try:
            ET.parse(path)
        except ET.ParseError as exc:
            shutil.copy2(backup, path)
            print("FAIL  %s: XML broke (%s) - reverted from backup" % (name, exc))
            failed += 1
            continue

        print("OK    %s: weather cell added at %s m\n        in %s"
              % (name, ground, os.path.dirname(path)))
        edited += 1

    print()
    print("edited=%d skipped=%d failed=%d" % (edited, skipped, failed))
    if dry_run:
        print("\nDry run - nothing written. Re-run without --dry-run to apply.")
    elif edited and not failed:
        print("""
Next, in this order:

1. Restart the simulator - the desktop icon, or:
     python3 tools/uas_launcher.py

2. Check the endpoints appeared (a terminal, while it runs):
     gz topic -l | grep weather
   Expect both:
     %s
     %s
   Nothing listed means the plugin did not load - say so before going on.

3. In the station, use the Weather control under
   "Experimental - In Development".""" % (FOG_TOPIC, RAIN_TOPIC))
    return 1 if failed else 0


def main(argv):
    if "--revert" in argv:
        return revert()
    return apply("--dry-run" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
