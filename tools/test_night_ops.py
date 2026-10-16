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
import struct
import xml.etree.ElementTree as ET
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
st.world_topic = lambda name: f"/world/{st.WORLD}/{name}"
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
# Two calls go out now, not one: the sun, then the sky dome. Pick each
# out by what it is for rather than by position, so adding a third does
# not quietly break this.
light_call = [c for c in sent if any("light_config" in a for a in c)][-1]
sky_call = [c for c in sent if any("material_color" in a for a in c)][-1]

request = light_call[light_call.index("--req") + 1]
check("asks Gazebo for the light every world here calls 'sun'",
      "name: 'sun'" in request)
check("through the world's own light_config service",
      any("light_config" in a and st.WORLD in a for a in light_call))
check("and says night is not darkness", "not darkness" in reply)

sky_request = sky_call[sky_call.index("-p") + 1]
check("dims the painted sky dome as well as the sun",
      "sky_dome" in sky_request)
check("on the world's own material_color topic",
      any("material_color" in a and st.WORLD in a for a in sky_call))
check("to a night sky, not a blue one (%s)" % tod.TIMES["night"]["sky"][2],
      tod.TIMES["night"]["sky"][2] < 0.2)
tod.set_time("day")
day_request = [c for c in sent if any("material_color" in a for a in c)][-1]
check("and puts it back at midday",
      "emissive: {r: 1.0, g: 1.0, b: 1.0" in
      day_request[day_request.index("-p") + 1])

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

# NO WING LIGHTS, from 13 Oct 2026. Removed on instruction - the reference
# photographs show none, and at 40 m range they threw coloured pools on
# the ground in daylight. The tool must also TAKE THEM OUT of a model that
# already has them, which it could not do when it only ever added.
check("there are no wingtip navigation lights (%s)"
      % ", ".join(sorted(by_name)),
      "nav_port" not in by_name and "nav_starboard" not in by_name)
check("and the tool knows to remove them from a model that has them",
      set(lights.OBSOLETE) == {"nav_port", "nav_starboard"})

# THE TAIL LIGHT IS THE GPS INDICATOR. Green with a fix, red without, and
# it FLASHES - the colour is the message, so a student watching the
# aircraft sees the gps_failure injection on the airframe.
tail_colour, tail_where = by_name["nav_tail"]
check("the tail light is behind the aircraft (%s)" % (tail_where,),
      tail_where[0] < 0)
check("and starts GREEN, the has-a-fix colour (%s)" % (tail_colour,),
      tail_colour[1] > 0.5 and tail_colour[0] < 0.2)
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
# The colour is logged too: the GPS light's colour IS its message,
# so a test that only recorded on/off would pass with it stuck green.
al.set_light = (lambda name, on, rgb=None:
                log.append((round(clock["t"], 3), name, on, rgb)) or True)
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
    # The GPS flash comes last in the cycle - see the note on GPS_FLASH.
    al._sleep_until(start + al.GPS_FLASH[0])
    al.set_light(al.GPS_LIGHT, True,
                 al.GPS_GREEN if al._state["gps"] else al.GPS_RED)
    al._sleep_until(start + al.GPS_FLASH[0] + al.GPS_FLASH[1])
    al.set_light(al.GPS_LIGHT, False)
    al._sleep_until(start + al.CYCLE_S)
    return list(log)


events = one_cycle()

# The GPS light flashes - on AND off in a cycle - which is what separates
# it from the steady position lights it replaced.
gps = [e for e in events if e[1] == al.GPS_LIGHT]
check("the GPS light flashes rather than sitting on (%d events)" % len(gps),
      any(e[2] for e in gps) and any(not e[2] for e in gps))

al._state["gps"] = True
green = [e for e in one_cycle() if e[1] == al.GPS_LIGHT and e[2]]
al._state["gps"] = False
red = [e for e in one_cycle() if e[1] == al.GPS_LIGHT and e[2]]
al._state["gps"] = True
check("with a fix it is sent GREEN (%s)" % (green[0][3] if green else None,),
      green and green[0][3] == al.GPS_GREEN)
check("and with GPS lost it is sent RED (%s)" % (red[0][3] if red else None,),
      red and red[0][3] == al.GPS_RED)

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

print("4b. the GPS failure the tail light reports")
# The control that drives the tail light red. It used to start a proxy
# that sat between PX4 and QGroundControl, needed port plumbing nobody
# did, and took its commands by TYPING - so started as a background
# script its command thread died with EOFError at once while the console
# reported "GPS failure injected." Measured on 14 Oct 2026. A control
# that claims an injection it has not made is worse than no control, and
# nothing here checked it.
import types as _types                                       # noqa: E402

_sent = []
_fake_master = _types.SimpleNamespace(
    target_system=1, target_component=1,
    mav=_types.SimpleNamespace(
        param_set_send=lambda sysid, comp, name, value, kind:
            _sent.append((name, value, kind))))
_fake_telem = {"satellites": 10}
_marks = []

_gps_mod = _types.ModuleType("gps_failure_under_test")
_gps_src = open(os.path.join(REPO, "plugins", "gps_failure.py")).read()
_gps_ns = {
    "master": _fake_master,
    "telemetry": _fake_telem,
    "mark_failure_injected": lambda k: _marks.append(("injected", k)),
    "mark_failure_cleared": lambda k: _marks.append(("cleared", k)),
}
# Run the module with simulator_link's names already provided, so the test
# never opens a MAVLink connection.
_body = _gps_src.replace(
    "from simulator_link import (master, telemetry, mark_failure_injected,\n"
    "                            mark_failure_cleared)", "")
exec(compile(_body, "gps_failure.py", "exec"), _gps_ns)

check("it sets PX4's own SIM_GPS_USED, not a proxy",
      _gps_ns["PARAM"] == b"SIM_GPS_USED")
# SensorGpsSim: fix_type is 3 at 4 or more satellites, 0 below.
check("and 0 is below the 4 PX4 calls a fix",
      _gps_ns["SATELLITES_NONE"] == 0 and _gps_ns["SATELLITES_OK"] >= 4)

_fake_telem["satellites"] = 0        # what the aircraft reports once it lands
message = _gps_ns["toggle_gps_failure"]()
check("injecting sends 0 satellites (%s)" % (_sent[-1][0],),
      _sent and _sent[-1][0] == b"SIM_GPS_USED"
      and struct.unpack("<i", struct.pack("<f", _sent[-1][1]))[0] == 0)
check("and it reports what the AIRCRAFT said, not what was sent",
      "0 satellites" in message and "injected" in message)
check("the failure is marked for the console's lights",
      ("injected", "gps") in _marks)

_fake_telem["satellites"] = 10
message = _gps_ns["toggle_gps_failure"]()
check("clearing puts the satellites back (%d)"
      % struct.unpack("<i", struct.pack("<f", _sent[-1][1]))[0],
      struct.unpack("<i", struct.pack("<f", _sent[-1][1]))[0] == 10)
check("and says so", "cleared" in message and "10" in message)

# The honest-failure path: if the aircraft never reports the change, say so
# rather than claiming an injection.
_fake_telem["satellites"] = 10
message = _gps_ns["toggle_gps_failure"]()
check("an injection the aircraft does not confirm is NOT claimed (%s)"
      % message[:48], "not reported the change" in message)

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

# 12 Oct 2026: the lights tool used to test for the FIRST light only, so
# once the beacon was added to its list it could never reach a model the
# tool had already edited. Found by verify_install.py on the
# instructor's machine, which had five of the six.
import importlib.util as _ilu                              # noqa: E402
import tempfile as _tf                                     # noqa: E402

_spec = _ilu.spec_from_file_location(
    "aircraft_lights_apply",
    os.path.join(REPO, "tools", "aircraft_lights_apply.py"))
_al = _ilu.module_from_spec(_spec)
_spec.loader.exec_module(_al)

print("\nThe lights tool adds what is missing, not all or nothing")

_holder = _tf.mkdtemp()
_model = os.path.join(_holder, "model.sdf")


def _write_model(how_many):
    body = ""
    for name, (r, g, b), (x, y, z), _ in _al.LIGHTS[:how_many]:
        body += _al.LIGHT_BLOCK.format(i="      ", name=name, r=r, g=g, b=b,
                                       x=x, y=y, z=z)
    with open(_model, "w") as handle:
        handle.write('<sdf version="1.9">\n  <model name="standard_vtol">\n'
                     '    <link name="%s">\n%s    </link>\n'
                     '  </model>\n</sdf>\n' % (_al.LINK, body))


_al.MODEL = _model
_write_model(len(_al.LIGHTS) - 1)       # every light but the last
_al.main([])
_text = open(_model).read()
check("a model missing one light gets that one added",
      all('name="%s"' % n in _text for n, _, _, _ in _al.LIGHTS))
check("and no light is added twice",
      all(_text.count('name="%s"' % n) == 1 for n, _, _, _ in _al.LIGHTS))
try:
    ET.parse(_model)
    check("and the model still parses", True)
except Exception as _exc:               # noqa: BLE001
    check("and the model still parses (%s)" % _exc, False)

_write_model(0)                          # bare model, nothing applied
_al.main([])
_text = open(_model).read()
check("a bare model gets all %d" % len(_al.LIGHTS),
      all('name="%s"' % n in _text for n, _, _, _ in _al.LIGHTS))

import shutil as _sh                                        # noqa: E402
_sh.rmtree(_holder, ignore_errors=True)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)

