"""Offline check of instructor_station's HTML rendering + plugin/limit
logic. Stubs out every hardware-facing import so nothing touches MAVLink,
Gazebo, or the real event-log CSV. Run it after editing instructor_station.py
/ simulator_link.py / video_feed.py / any plugin:

    python3 tools/offline_render_check.py

It verifies: the page still assembles, PAGE_TEMPLATE.format() has no brace
errors, the JS blob is present, plugins load, the LOITER radius input
renders, plugin handlers run, and the CAP722B limit/health logic classifies
correctly. It does NOT test actual flight behaviour - that needs the sim.
"""
import sys, types, importlib.util, os

GCS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# --- stub simulator_link ---
sl = types.ModuleType("simulator_link")
sl.telemetry = {"armed": False, "mode": "Hold", "altitude_m": 0.0, "altitude_amsl_m": 1200.0,
                "groundspeed_ms": 0.0, "battery_pct": 100, "heading_deg": 0, "satellites": 10}
sl.connection_status = {"connected": True, "message": "Connected."}
class _M:
    class mav:
        @staticmethod
        def command_long_send(*a, **k): pass
    target_system = 1
    target_component = 1
sl.master = _M()
sl.reset_flight_state = lambda: None
sl.log_instructor_action = lambda *a, **k: None
sl.mark_failure_injected = lambda *a, **k: None
sl.mark_failure_cleared = lambda *a, **k: None
sl.start_background_script = lambda *a, **k: None
sl.stop_background_script = lambda *a, **k: None
sl.running_processes = {}
sl.RESPONSE_TIMEOUT_S = 45
sl.telemetry.update({"roll_deg": 0.0, "pitch_deg": 0.0, "yaw_deg": 0.0,
                     "airspeed_ms": 0.0, "range_from_home_m": 0.0,
                     "arm_ready": None, "arm_state": "Waiting for PX4",
                     "arm_blocker": None})
sl.flight_path = [(23.5, 6.5, 100.0, 1.0), (23.5012, 6.5009, 120.0, 2.0), (23.5021, 6.5, 130.0, 3.0)]
sl.home_latlon = {"lat": 23.5, "lon": 6.5}
sl.link_health = {"last_msg_t": None}
sl.command_acks = {}
sl.MAV_RESULT_NAMES = {0: "accepted"}
sl.send_command_and_wait = lambda *a, **k: (0, "accepted")
sl.status_log = []
sl.home_amsl = lambda: 1200.0
sl.on_armed_change = lambda cb: None
# The tail light follows the GPS fix - see aircraft_lights.set_gps.
sl.on_gps_change = lambda cb: None
sl.GPS_FIX_SATELLITES = 6
sl.on_failure = lambda cb: None
sl.failure_injection_blocked = lambda: None
sl.read_param = lambda *a, **k: 1.0
sl.FAILURE_UNIT_SYSTEM_MOTOR = 101
sl.FAILURE_UNIT_SYSTEM_SERVO = 102
sl.FAILURE_UNIT_SYSTEM_RC_SIGNAL = 104
sl.FAILURE_UNIT_SYSTEM_MAVLINK_SIGNAL = 105
sl.FAILURE_TYPE_OK = 0
sl.FAILURE_TYPE_OFF = 1
sl.MAV_CMD_INJECT_FAILURE = 420
sl.offset_latlon = lambda lat, lon, bearing, dist: (lat, lon)
sl.say_step = lambda *a, **k: None
sl.cancel_sequence = lambda: None
sl.sequence_running = lambda: False
sl.start_sequence = lambda *a, **k: True
sl.wait_until = lambda *a, **k: True
sl.VTOL_STATES = {3: "Hover", 4: "Fixed wing"}
sl.status_since = lambda *a, **k: []
sl.wait_for_armed = lambda *a, **k: True
sl.set_mode = lambda m, s=0, name=None: f"{name or 'mode'}: accepted by PX4."
sys.modules["simulator_link"] = sl
al = types.ModuleType("aircraft_lights")
al.set_armed = lambda *a, **k: None
al.set_gps = lambda *a, **k: None
al.set_on = lambda on: None
al.status = lambda: {"on": False, "armed": False, "problem": None}
# No wingtip lights from 13 Oct 2026, and the tail light is the GPS
# indicator rather than a position light.
al.NAVIGATION = []
al.GPS_LIGHT = "nav_tail"
al.STROBES = ["strobe_top", "strobe_belly"]
al.BEACON = ["beacon_top"]
al.ALL = al.NAVIGATION + [al.GPS_LIGHT] + al.STROBES + al.BEACON
sys.modules["aircraft_lights"] = al

# --- stub event_logger so this check never writes to the real compliance CSV ---
el = types.ModuleType("event_logger")
el.log_event = lambda *a, **k: None
el.read_events = lambda: []
el.SESSION_ID = "TEST"
sys.modules["event_logger"] = el

# --- stub video_feed ---
vf = types.ModuleType("video_feed")
vf.start_video_capture = lambda: None
vf.mjpeg_generator = lambda: iter(())
vf.camera_fps = lambda: 0.0
class _Feed:
    def fov_rad(self): return 1.5708
    def mjpeg_generator(self): return iter(())
    def fps(self): return 0.0
    def current_topic(self): return None
    def resubscribe(self): return None
    def start(self): return None
vf.FEEDS = {"nose": _Feed(), "chase": _Feed()}
vf.nose = vf.FEEDS["nose"]
vf.chase = vf.FEEDS["chase"]
sys.modules["video_feed"] = vf

# --- real plugin_loader, but load actual plugin files (they only import the stub) ---
sys.path.insert(0, GCS)

spec = importlib.util.spec_from_file_location("instructor_station", os.path.join(GCS, "instructor_station.py"))
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

print("plugins loaded:", len(mod.plugins))
btns = mod.render_buttons()
page = mod.PAGE_TEMPLATE.format(buttons=btns)
page = page.replace('<div id="status">Ready.</div>', mod.EXTRA_PANELS + '<div id="status">Ready.</div>')
# Assembled the way the server assembles it, flight display included -
# this was building a page the server never serves, so the three tokens
# below had been printing False since the display moved into its own
# module and nothing noticed.
import flight_display
page = page.replace("</body>", mod.EXTRA_STYLE + mod.EXTRA_SCRIPT
                    + mod._limits_script()
                    + flight_display.STYLE + flight_display.script()
                    + mod.LAYOUT_STYLE + mod.LAYOUT_SCRIPT + "</body>")
print("full page assembled OK, length", len(page))
for tok in ('id="hud"', 'id="flightpath"', 'fpv-wrap', "fetch('/flight_path')",
            "gcsDrawHud", "LOW ALTITUDE", "roll_deg", "GCS_LIMITS"):
    print(f"  contains {tok!r}:", tok in page)

for pid in ("hold", "forward_flight", "hover_flight", "loiter", "mode_manual", "mode_position"):
    p = mod.plugins_by_id.get(pid)
    print(f"  {pid:15} present={p is not None}  inputs={p.get('inputs') if p else None}")

assert 'data-param="radius_m"' in btns, "radius input not rendered"
assert 'FORWARD FLIGHT (FW)' in btns
assert 'btn-stack' in btns
print("\nLOITER block:")
i = btns.index('btn-stack')
print(btns[i-6:i+400])

# exercise the loiter handler with a value + validation paths
print("\nhandler tests:")
print("  loiter('200'):", mod.plugins_by_id["loiter"]["handler"](radius_m="200"))
print("  loiter('abc'):", mod.plugins_by_id["loiter"]["handler"](radius_m="abc"))
print("  loiter('-5') :", mod.plugins_by_id["loiter"]["handler"](radius_m="-5"))
print("  loiter()     :", mod.plugins_by_id["loiter"]["handler"]())
print("  hold()       :", mod.plugins_by_id["hold"]["handler"]())
print("  forward()    :", mod.plugins_by_id["forward_flight"]["handler"]())

print("\n--- CAP722B features ---")
for tok in ('id="limit-banner"', 'id="t-health"', "fetch('/limit_status')", "fetch('/health')", "APPROACHING LIMIT"):
    print(f"  page contains {tok!r}:", tok in page)
sl.telemetry["altitude_m"] = 135.0        # over 120 ceiling
sl.telemetry["groundspeed_ms"] = 28.0     # ~93% of 30 -> warn
sl.telemetry["range_from_home_m"] = 470.0 # ~94% of 500 -> warn
sl.telemetry["battery_pct"] = 12          # below 15 critical
print("  limit_status():", mod.limit_status())
sl.telemetry["altitude_m"] = 10.0
sl.telemetry["groundspeed_ms"] = 3.0
sl.telemetry["range_from_home_m"] = 20.0
sl.telemetry["battery_pct"] = 80
print("  limit_status() (all ok):", mod.limit_status())
print("  health_status():", mod.health_status())

# --- arming readout (added 11 Oct 2026) ---------------------------------
# The console used to say "Disarmed" and nothing else, so a refused ARM
# looked identical to an aircraft that simply had not been armed yet. These
# tokens are what turns HEARTBEAT.system_status into something readable;
# the readout's own logic is tested against real MAVLink messages in
# simulator_link, this only checks the page still carries the wiring.
# --- rebuilt console (added 11 Oct 2026) ------------------------------
print("\n--- rebuilt console ---")
console = mod.render_console()
print("  page assembled, length", len(console))
for tok in ('id="hero"', 'id="tile-left"', 'id="tile-right"', 'id="gyro"',
            'id="view-chase"', 'id="view-nose"', 'id="view-map"',
            'id="rail-left"', 'id="rail-right"', 'id="hud"', 'id="hud-on"',
            'id="flightpath"', 'id="limit-banner"', 'id="t-health"',
            "/console_layout", "CAP722B"):
    print(f"  contains {tok!r}:", tok in console)
print("  no placeholder left:",
      not any(t in console for t in ("__LEFT_RAIL__", "__RIGHT_RAIL__",
                                     "__SAVED__", "__LIMITS__",
                                     "__CONSOLE_SCRIPT__", "__EXTRA_SCRIPT__",
                                     "__EXTRA_STYLE__")))
# Each feed must appear exactly once: a second <img> on the same MJPEG
# endpoint doubles the station's encoding work for a duplicate picture.
print("  one /chase_feed tag:", console.count('src="/chase_feed"') == 1)
print("  one /video_feed tag:", console.count('src="/video_feed"') == 1)
left = mod.render_rail(mod.LEFT_CATEGORIES)
right = mod.render_rail(mod.RIGHT_CATEGORIES)
print("  arm/disarm on the left rail:",
      'id="btn-arm"' in left and 'id="btn-disarm"' in left)
print("  failure injection on the right rail:",
      'id="btn-gps_failure"' in right and 'id="btn-motor_failure"' in right)
print("  every plugin reachable from one rail or the other:",
      all(('id="btn-%s"' % p["id"]) in (left + right) for p in mod.plugins))
import tempfile
mod.LAYOUT_FILE = os.path.join(tempfile.mkdtemp(), "gcs_layout.json")
print("  console layout round-trips:",
      mod.write_console_layout({"hero": "map", "layout": "station",
                                "tiles": {"left": {"x": 10, "y": 20, "w": 9999, "h": 5}}})
      and mod.read_console_layout()["hero"] == "map")
saved = mod.read_console_layout()
print("  an absurd tile size is clamped, not stored:",
      saved["tiles"]["left"]["w"] == mod.TILE_MAX_W
      and saved["tiles"]["left"]["h"] == mod.TILE_MIN_H)
mod.write_console_layout({"rails": {"right": {"x": 5, "y": 5, "w": -40, "h": 99999,
                                              "horizontal": True}}})
rail = mod.read_console_layout()["rails"]["right"]
print("  a rail panel round-trips, clamped:",
      rail["w"] == mod.RAIL_MIN_W and rail["h"] == mod.RAIL_MAX_H
      and rail["horizontal"] is True)

print("\n--- arming readout ---")
for tok in ('id="t-armcheck"', ">Arming<", ".arm-ready", ".arm-wait",
            ".arm-block", "d.arm_state", "d.arm_blocker",
            "d.arm_ready === null", "/^Preflight( Fail)?: */i"):
    print(f"  page contains {tok!r}:", tok in page)
