"""Check the weather control's behaviour without Gazebo running.

    python3 tools/test_weather.py

Stubs `gz` so the exact published payloads can be inspected. What it cannot
prove: that Gazebo renders anything. That needs the simulator.

Worth testing because the failure that matters here is silent - a condition
that leaves the other emitter running (rain still falling inside "Fog"), or
a rate above Ogre's particle quota, which makes the emitter stop emitting
without reporting anything at all.
"""
import importlib.util
import os
import sys
import types

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

# --- stub the station's MAVLink link, which weather.py only logs through ---
sl = types.ModuleType("simulator_link")
actions = []
sl.log_instructor_action = lambda *a: actions.append(a)
sys.modules["simulator_link"] = sl

spec = importlib.util.spec_from_file_location(
    "weather", os.path.join(REPO, "plugins", "weather.py"))
W = importlib.util.module_from_spec(spec)
spec.loader.exec_module(W)

published = []


class _Result:
    returncode = 0
    stdout = ""
    stderr = ""


def fake_run(cmd, **kwargs):
    published.append({cmd[cmd.index("-t") + 1]: cmd[cmd.index("-p") + 1]})
    return _Result()


W.subprocess.run = fake_run

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


def publish_for(condition):
    published.clear()
    message = W.set_weather(condition)
    merged = {}
    for item in published:
        merged.update(item)
    return message, merged


print("1. every condition addresses BOTH emitters")
for condition in W.CONDITIONS:
    _, sent = publish_for(condition)
    check("%s -> fog and rain both set" % condition,
          set(sent) == {W.FOG_TOPIC, W.RAIN_TOPIC})

print("2. a condition that does not use an emitter switches it off")
_, sent = publish_for("fog")
check("fog: rain explicitly off", sent[W.RAIN_TOPIC] == W.OFF)
check("fog: fog on", "data: true" in sent[W.FOG_TOPIC])
_, sent = publish_for("rain")
check("rain: fog explicitly off", sent[W.FOG_TOPIC] == W.OFF)
_, sent = publish_for("clear")
check("clear: both off",
      sent[W.FOG_TOPIC] == W.OFF and sent[W.RAIN_TOPIC] == W.OFF)

print("3. rates stay under Ogre's 5000-particle quota")
# Lifetimes are fixed in the world file by tools/weather_apply.py.
LIFETIME = {W.FOG_TOPIC: 25, W.RAIN_TOPIC: 4}
QUOTA = 5000
for condition in W.CONDITIONS:
    _, sent = publish_for(condition)
    for topic, payload in sent.items():
        if "rate" not in payload:
            continue
        rate = float(payload.split("rate: {data:")[1].split("}")[0])
        alive = rate * LIFETIME[topic]
        check("%s %s: %.0f alive < %d" % (condition, topic.rsplit("/")[-1],
                                          alive, QUOTA), alive < QUOTA)

print("4. the status light follows the condition")
W.set_weather("fog")
check("on when not clear", W.state["active"] is True)
W.set_weather("clear")
check("off when clear", W.state["active"] is False)

print("5. a world restart resets it, so the light cannot lie")
W.set_weather("heavy_rain")
W.reset_state()
check("reset", W.state["active"] is False and W.state["condition"] == "clear")

print("6. an unknown condition is refused and changes nothing")
W.set_weather("fog")
published.clear()
message = W.set_weather("hurricane")
check("refused by name", "hurricane" in message and "not changed" in message)
check("nothing published", published == [])
check("state untouched", W.state["condition"] == "fog")

print("7. a failed publish is reported, not swallowed")
class _Fail:
    returncode = 1
    stdout = ""
    stderr = "Error: no such topic\n"
W.subprocess.run = lambda cmd, **kw: _Fail()
message = W.set_weather("clear")
check("reports the failure: %s" % message.strip(),
      "not changed" in message and "no such topic" in message)
W.subprocess.run = fake_run

print("8. every condition says the flight model is unaffected")
for condition in W.CONDITIONS:
    if condition == "clear":
        continue
    message, _ = publish_for(condition)
    check("%s carries the caveat" % condition, "camera view only" in message)

print("9. gz is called with the right message type")
publish_for("rain")
check("logged to the event record", any(a[0] == "weather" for a in actions))

print("10. the world geometry the rates assume")
# Guards the bug that made the first live look say "heavy rain is not much
# rain seen falling": Ogre reads particle_size as (width, height) and
# ignores Z, so a streak length written into Z renders as a tiny square.
import xml.etree.ElementTree as ET
wspec = importlib.util.spec_from_file_location(
    "weather_apply", os.path.join(REPO, "tools", "weather_apply.py"))
WA = importlib.util.module_from_spec(wspec)
wspec.loader.exec_module(WA)
block = WA.BLOCK.format(i="", ground=1.3, fog_topic=WA.FOG_TOPIC,
                        rain_topic=WA.RAIN_TOPIC)
root = ET.fromstring("<world>" + block + "</world>")
emitters = {e.get("name"): e for e in root.iter("particle_emitter")}
check("both emitters defined", set(emitters) == {"fog", "rain"})

for name, emitter in emitters.items():
    size = [float(v) for v in emitter.findtext("particle_size").split()]
    check("%s: particle width and height are non-zero" % name,
          size[0] > 0 and size[1] > 0)
    check("%s: nothing meaningful hidden in the ignored Z" % name,
          size[2] == 0)

rain = emitters["rain"]
rsize = [float(v) for v in rain.findtext("particle_size").split()]
check("rain particles are streaks, not squares (%.2f x %.2f)"
      % (rsize[0], rsize[1]), rsize[1] >= 5 * rsize[0])

# Rain must reach the ground inside its lifetime, or it vanishes mid-air.
pose = [float(v) for v in rain.findtext("pose").split()]
lifetime = float(rain.findtext("lifetime"))
slowest = float(rain.findtext("min_velocity"))
check("rain reaches the ground in %.1fs of %.1fs life"
      % (pose[2] / slowest, lifetime), pose[2] / slowest <= lifetime)

# Density is the whole point of the retune, so assert it rather than hope.
# Fog and rain need different measures: fog has to OBSCURE, so what matters
# is how many times over its billboards cover the footprint; rain has to be
# SEEN FALLING without becoming a wall, so what matters is streaks per
# square metre. One number for both would be meaningless.
QUOTA = 5000
for name, emitter in emitters.items():
    is_fog = name == "fog"
    heaviest = max(
        float(p.split("rate: {data:")[1].split("}")[0])
        for pair in W.CONDITIONS.values()
        for p in (pair[0] if is_fog else pair[1],)
        if "rate" in p)
    box = [float(v) for v in emitter.findtext("size").split()]
    footprint = max(box[0] * box[1], 1.0)
    psize = [float(v) for v in emitter.findtext("particle_size").split()]
    alive = heaviest * float(emitter.findtext("lifetime"))

    # The original fault was rates at roughly a tenth of the quota, which
    # looked like the feature not working.
    check("%s: full intensity uses %.0f%% of the particle budget"
          % (name, 100 * alive / QUOTA), alive >= 0.75 * QUOTA)

    if is_fog:
        coverage = alive * psize[0] * psize[1] / footprint
        check("fog: billboards cover the cell %.0fx over" % coverage,
              coverage >= 5)
    else:
        check("rain: %.2f streaks per square metre" % (alive / footprint),
              alive / footprint >= 0.5)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
