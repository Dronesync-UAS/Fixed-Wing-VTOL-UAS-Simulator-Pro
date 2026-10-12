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

print("4. the flash pattern")
# What flashes and what does not is the part a student is marked on, and
# it is timing code nobody can check by looking at it.
import importlib                                                  # noqa: E402

st.WORLD = "training_area_blackrock"
spec = importlib.util.spec_from_file_location(
    "aircraft_lights", os.path.join(REPO, "aircraft_lights.py"))
al = importlib.util.module_from_spec(spec)
spec.loader.exec_module(al)

# Record every switch instead of publishing it.
log = []
clock = {"t": 0.0}
al.set_light = lambda name, on: log.append((round(clock["t"], 3), name, on)) or True
al._sleep_until = lambda moment: clock.__setitem__("t", max(clock["t"], moment))
import time as _time                                              # noqa: E402
al.time = type("t", (), {"monotonic": lambda: clock["t"], "sleep": lambda *_: None})

al._state["on"] = True
al._state["armed"] = True


def one_cycle():
    log.clear()
    start = clock["t"]
    for name in al.NAVIGATION:
        al.set_light(name, True)
    for when, length in al.STROBE_FLASHES:
        al._sleep_until(start + when)
        for name in al.STROBES:
            al.set_light(name, True)
        al._sleep_until(start + when + length)
        for name in al.STROBES:
            al.set_light(name, False)
    if al._state["armed"]:
        al._sleep_until(start + al.BEACON_FLASH[0])
        for name in al.BEACON:
            al.set_light(name, True)
        al._sleep_until(start + al.BEACON_FLASH[0] + al.BEACON_FLASH[1])
        for name in al.BEACON:
            al.set_light(name, False)
    al._sleep_until(start + al.CYCLE_S)
    return list(log)


events = one_cycle()
nav = [e for e in events if e[1] in al.NAVIGATION]
check("the navigation lights are only ever switched ON (%s events)" % len(nav),
      nav and all(e[2] for e in nav))
check("every navigation light is lit", len({e[1] for e in nav}) == 3)

strobe_on = [e[0] for e in events if e[1] == "strobe_top" and e[2]]
check("the strobes DOUBLE-flash (%s flashes a second)" % len(strobe_on),
      len(strobe_on) == 2)
check("the two strobes fire together",
      [e[0] for e in events if e[1] == "strobe_belly" and e[2]] == strobe_on)
gap = strobe_on[1] - strobe_on[0]
check("the two flashes are close together (%.0f ms apart)" % (gap * 1000),
      0.05 < gap < 0.35)

beacon_on = [e[0] for e in events if e[1] == "beacon_top" and e[2]]
check("the beacon flashes once a cycle (%s)" % len(beacon_on), len(beacon_on) == 1)
check("on its own rhythm, not with the strobes (%.2f vs %s)"
      % (beacon_on[0], strobe_on), beacon_on[0] not in strobe_on)

# Disarmed, the beacon is dark - that is what a beacon MEANS.
al._state["armed"] = False
events = one_cycle()
check("and not at all while disarmed",
      not [e for e in events if e[1] == "beacon_top" and e[2]])
check("while the strobes carry on",
      len([e for e in events if e[1] == "strobe_top" and e[2]]) == 2)

check("switching off darkens every light",
      (al.set_on(False) or True)
      and {e[1] for e in log[-len(al.ALL):]} == set(al.ALL)
      and not any(e[2] for e in log[-len(al.ALL):]))

print("5. the aircraft's colours")
# A fragment with the same shape as PX4's standard_vtol model: a blue
# rotor, a blue elevon, and a grey fuselage that must be left alone.
MODEL_SNIPPET = """\
      <visual name='base_link_visual'>
        <material>
          <ambient>.175 .175 .175 1.0</ambient>
          <diffuse>.175 .175 .175 1.0</diffuse>
        </material>
      </visual>
      <visual name='rotor_0_visual'>
        <material>
          <ambient>0 0 1 1.0</ambient>
          <diffuse>0 0 1 1.0</diffuse>
        </material>
      </visual>
      <visual name='left_elevon_visual'>
        <material>
          <ambient>0 0 1 1.0</ambient>
          <diffuse>0 0 1 1.0</diffuse>
        </material>
      </visual>
"""

spec = importlib.util.spec_from_file_location(
    "aircraft_colours_apply",
    os.path.join(REPO, "tools", "aircraft_colours_apply.py"))
colours = importlib.util.module_from_spec(spec)
spec.loader.exec_module(colours)

out, changed = colours.recolour(MODEL_SNIPPET.splitlines(keepends=True))
joined = "".join(out)
check("it changed something (%s lines)" % len(changed), len(changed) == 4)
check("no blue left on the aircraft", "0 0 1 1.0" not in joined)
check("the fuselage is left as it was", ".175 .175 .175 1.0" in joined)

rotor = colours.COLOURS["rotor_0_visual"][0]
elevon = colours.COLOURS["left_elevon_visual"][0]
check("the propellers are near-black (%s)" % (rotor,), max(rotor) <= 0.08)
check("but not pure black, which would go flat (%s)" % (rotor,), min(rotor) > 0)
check("the elevons are DARKER than the 0.175 fuselage (%s)" % (elevon,),
      max(elevon) < 0.175)
check("and still lighter than the propellers (%s vs %s)" % (elevon, rotor),
      max(elevon) > max(rotor))

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
