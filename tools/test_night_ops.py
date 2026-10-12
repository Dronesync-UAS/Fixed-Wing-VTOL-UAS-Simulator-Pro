"""Check the night-operations pieces, with no Gazebo and no PX4.

    python3 tools/test_night_ops.py

Three things worth proving before anyone flies at night with them:

  * the infrared views actually change the picture, and change it the way
    they say - white hot bright where black hot is dark;
  * the lighting control sends Gazebo a light named the same as the one
    every world in this project actually has;
  * the aircraft's lights are the colours a student will be marked on -
    red to port and green to starboard, not the other way round, which is
    the single easiest thing to get backwards here.
"""
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


print("1. the infrared views")
from PIL import Image  # noqa: E402

# A stand-in for a camera frame: dark on the left, bright on the right.
frame = Image.new("RGB", (40, 10))
for x in range(40):
    for y in range(10):
        frame.putpixel((x, y), (x * 6, x * 6, x * 6))

sys.modules.setdefault("gz", types.ModuleType("gz"))
spec = importlib.util.spec_from_file_location(
    "video_feed_probe", os.path.join(REPO, "video_feed.py"))
try:
    vf = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vf)
    have_module = True
except ImportError:
    # gz-transport is not installed on every machine; pull the renderings
    # out of the source instead so this check still means something.
    have_module = False
    source = open(os.path.join(REPO, "video_feed.py"), encoding="utf-8").read()
    start = source.index("def _luminance")
    end = source.index("class CameraFeed")
    # One namespace for globals AND locals: with two, the functions
    # defined in there cannot see each other.
    from PIL import ImageOps
    ns = {"ImageOps": ImageOps}
    exec(compile(source[start:end], "video_feed", "exec"), ns)
    vf = types.SimpleNamespace(**ns)

check("there are four views, daylight included", len(vf.VIEW_MODES) == 4)
check("daylight does nothing to the picture", vf.VIEW_MODES["normal"] is None)

white = vf.VIEW_MODES["white_hot"](frame)
black = vf.VIEW_MODES["black_hot"](frame)
night = vf.VIEW_MODES["night_vision"](frame)
dark_end, bright_end = (2, 5), (37, 5)

check("white hot keeps bright things bright (%s -> %s)"
      % (frame.getpixel(bright_end)[0], white.getpixel(bright_end)[0]),
      white.getpixel(bright_end)[0] > white.getpixel(dark_end)[0])
check("black hot turns them round (%s vs %s)"
      % (black.getpixel(bright_end)[0], black.getpixel(dark_end)[0]),
      black.getpixel(bright_end)[0] < black.getpixel(dark_end)[0])
check("both are grey, with no colour left (%s)" % (white.getpixel(bright_end),),
      len(set(white.getpixel(bright_end))) == 1)
r, g, b = night.getpixel(bright_end)
check("night vision is green (%s)" % ((r, g, b),), g > r and g > b)

print("2. the lighting control")
spec = importlib.util.spec_from_file_location(
    "time_of_day", os.path.join(REPO, "plugins", "time_of_day.py"))
st = types.ModuleType("sim_target")
st.WORLD = "training_area_blackrock"
st.service = lambda name: f"/world/{st.WORLD}/{name}"
sys.modules["sim_target"] = st
sl = types.ModuleType("simulator_link")
sl.log_instructor_action = lambda *a, **k: None
sys.modules["simulator_link"] = sl
tod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tod)

sent = []
import subprocess  # noqa: E402
subprocess.run = lambda *a, **k: sent.append(a[0]) or types.SimpleNamespace(
    returncode=0, stdout="data: true", stderr="")

check("refuses a time it does not have", "not one of" in tod.set_time("teatime"))
reply = tod.set_time("night")
check("night accepted (%s...)" % reply[:28], "Night" in reply)
request = sent[-1][sent[-1].index("--req") + 1]
check("asks Gazebo for the light every world here calls 'sun'",
      "name: 'sun'" in request)
check("through the world's own light_config service",
      any("light_config" in a and st.WORLD in a for a in sent[-1]))
check("and says night is not darkness", "not darkness" in reply)

day = tod.TIMES["day"]["diffuse"]
night_c = tod.TIMES["night"]["diffuse"]
check("night is dimmer than day (%s vs %s)" % (sum(night_c), sum(day)),
      sum(night_c) < sum(day) / 3)
check("and colder (%s)" % (night_c,), night_c[2] > night_c[0])

print("3. the aircraft's lights")
lights = importlib.util.module_from_spec(importlib.util.spec_from_file_location(
    "aircraft_lights_apply", os.path.join(REPO, "tools", "aircraft_lights_apply.py")))
importlib.util.spec_from_file_location(
    "aircraft_lights_apply",
    os.path.join(REPO, "tools", "aircraft_lights_apply.py")).loader.exec_module(lights)

by_name = {name: (colour, where) for name, colour, where, _ in lights.LIGHTS}
port_colour, port_where = by_name["nav_port"]
star_colour, star_where = by_name["nav_starboard"]

# The one thing worth a test of its own: a student taught these the wrong
# way round will be marked wrong, and they are easy to swap by accident.
check("port is RED (%s)" % (port_colour,),
      port_colour[0] > 0.5 and port_colour[1] < 0.2)
check("starboard is GREEN (%s)" % (star_colour,),
      star_colour[1] > 0.5 and star_colour[0] < 0.2)
check("port is on the LEFT, +y in the aircraft's own axes (%s)" % (port_where,),
      port_where[1] > 0)
check("starboard is on the RIGHT (%s)" % (star_where,), star_where[1] < 0)
check("the tail light is white and behind (%s)" % (by_name["nav_tail"],),
      by_name["nav_tail"][1][0] < 0 and min(by_name["nav_tail"][0]) > 0.8)
check("one strobe above and one below (%s, %s)"
      % (by_name["strobe_top"][1][2], by_name["strobe_belly"][1][2]),
      by_name["strobe_top"][1][2] > 0 and by_name["strobe_belly"][1][2] < 0)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
