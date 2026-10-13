"""Exercise tools/uas_launcher.py against a stand-in PX4 and station.

    python3 tools/test_launcher.py

What this can and cannot prove: it drives the launcher's real orchestration -
readiness detection, build-failure detection, the timeout, the station wait,
stop and status - against a fake PX4 build (a one-line Makefile) and a fake
station (an HTTP server answering /connection_status). It does not prove that
PX4 itself starts, which needs the real thing on the real machine.

Worth testing at all because the failure modes here are the slow ones: a
launcher that waits a fixed number of seconds instead of watching for the
ready line reports success on a build that has already died, and the person
then hunts for a simulator that was never there.
"""
import importlib.util
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
spec = importlib.util.spec_from_file_location(
    "uas_launcher", os.path.join(REPO, "tools", "uas_launcher.py"))
L = importlib.util.module_from_spec(spec)
spec.loader.exec_module(L)

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def fake_px4(tmp, body):
    """A directory that behaves like PX4-Autopilot for `make px4_sitl ...`."""
    px4 = os.path.join(tmp, "PX4-Autopilot")
    worlds = os.path.join(px4, "Tools", "simulation", "gz", "worlds")
    os.makedirs(worlds, exist_ok=True)
    for env in L.sim_target.ENVIRONMENTS:
        open(os.path.join(worlds, env["world"] + ".sdf"), "w").close()
    with open(os.path.join(px4, "Makefile"), "w") as handle:
        handle.write("px4_sitl gz_standard_vtol:\n" + body)
    return px4


READY_LINE = "INFO  [px4] " + L.PX4_READY


print("1. prerequisites are checked before anything is started")
entry = L.sim_target.BY_KEY["blackrock"]
L.PX4_DIR = "/nonexistent-px4"
problems = L.check_prerequisites(entry)
check("missing PX4 reported", any("not at" in p for p in problems))

with tempfile.TemporaryDirectory() as tmp:
    L.LOG_DIR = tmp
    L.SIM_LOG = os.path.join(tmp, "sim.log")
    L.STATION_LOG = os.path.join(tmp, "gcs.log")

    print("2. a PX4 that comes up is detected from its own ready line")
    L.PX4_DIR = fake_px4(tmp, "\t@echo '%s'\n\t@sleep 20\n" % READY_LINE)
    check("prerequisites now pass", L.check_prerequisites(entry) == [])
    started = time.monotonic()
    proc = L.start_simulator(entry)
    ok, detail = L.wait_for_simulator(proc, timeout=30)
    took = time.monotonic() - started
    check("reported up (%s)" % (detail or "no error"), ok)
    check("detected promptly, not by waiting out a timer (%.1fs)" % took,
          took < 10)
    check("spawn height passed through",
          "0,0,1.3,0,0,0" == "0,0,%s,0,0,0" % entry["spawn_z"])
    proc.kill()

    print("3. a build that fails is reported as a failure, not a timeout")
    L.PX4_DIR = fake_px4(tmp, "\t@echo 'ninja: build stopped: interrupted'\n"
                              "\t@exit 1\n")
    proc = L.start_simulator(entry)
    ok, detail = L.wait_for_simulator(proc, timeout=25)
    check("not reported as up", not ok)
    check("names the build failure: %s" % detail,
          "build failed" in detail or "exited" in detail)

    print("4. a PX4 that never says anything times out with the log named")
    L.PX4_DIR = fake_px4(tmp, "\t@sleep 20\n")
    proc = L.start_simulator(entry)
    ok, detail = L.wait_for_simulator(proc, timeout=4)
    check("not reported as up", not ok)
    check("names the log: %s" % detail, L.SIM_LOG in detail)
    proc.kill()

    print("5. the station wait wants a real answer, not just an open port")
    port = free_port()
    L.STATION_PORT = port
    L.STATION_URL = "http://localhost:%d" % port
    # A plain listening socket that answers nothing: the launcher must not
    # mistake this for the station, or it reports ready and opens a dead page.
    dead = socket.socket()
    dead.bind(("127.0.0.1", port))
    dead.listen(1)
    check("open-but-silent port is not accepted", not L._station_answering())
    dead.close()

    print("6. a station that answers /connection_status is accepted")
    stub = os.path.join(tmp, "stub_station.py")
    with open(stub, "w") as handle:
        handle.write(
            "import sys\n"
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class H(BaseHTTPRequestHandler):\n"
            "    def do_GET(self):\n"
            "        self.send_response(200 if self.path=='/connection_status'"
            " else 404)\n"
            "        self.send_header('Content-type','application/json')\n"
            "        self.end_headers()\n"
            "        self.wfile.write(b'{\"connected\": true}')\n"
            "    def log_message(self, *a): pass\n"
            "HTTPServer(('127.0.0.1', int(sys.argv[1])), H).serve_forever()\n")
    station = subprocess.Popen([sys.executable, stub, str(port)],
                               stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL,
                               start_new_session=True)
    ok, detail = L.wait_for_station(station, timeout=15)
    check("station accepted (%s)" % (detail or "no error"), ok)
    check("status agrees", L._station_answering())

    print("7. a station that dies is reported, and does not hang the launcher")
    station.kill()
    station.wait()
    time.sleep(0.5)
    dead_proc = subprocess.Popen([sys.executable, "-c", "raise SystemExit(1)"])
    ok, detail = L.wait_for_station(dead_proc, timeout=10)
    check("not reported as up", not ok)
    check("names the log: %s" % detail, L.STATION_LOG in detail)

    print("8. an unknown training area is refused by name")
    chosen, problem = L.resolve_environment("atlantis")
    check("refused", chosen is None and "atlantis" in problem)
    check("lists the real ones", "blackrock" in problem)

    print("9. no argument falls back to the remembered world")
    chosen, problem = L.resolve_environment(None)
    check("resolved %s" % (chosen or {}).get("key"),
          problem is None and chosen["world"] == L.sim_target.WORLD)

print("10. the Gazebo camera step waits, then gives up without blocking")
# The GUI advertises /gui/follow well after PX4 says it is ready, so asking
# too early fails silently: the call succeeds and nothing moves. And a
# camera that never turns up must not stop the launcher finishing.
calls = []


def fake_gz(cmd, **kwargs):
    calls.append(cmd)
    out = type("R", (), {"returncode": 0, "stdout": "", "stderr": ""})()
    if cmd[:3] == ["gz", "service", "-l"]:
        out.stdout = "/gui/follow\n/gui/follow/offset\n" if fake_gz.up else "/world/x\n"
    return out


fake_gz.up = False
L.subprocess.run = fake_gz

started = time.monotonic()
problem = L.point_camera_at_aircraft(timeout=3)
check("gives up rather than hanging (%.1fs)" % (time.monotonic() - started),
      problem is not None and time.monotonic() - started < 10)
check("says what was not ready: %s" % problem, "camera" in problem)
check("asked for the service list", any(c[:3] == ["gz", "service", "-l"]
                                        for c in calls))

fake_gz.up = True
calls.clear()
problem = L.point_camera_at_aircraft(timeout=10)
check("succeeds once the GUI is up (%s)" % (problem or "no problem"),
      problem is None)
followed = [c for c in calls if "-s" in c and "/gui/follow" in c]
check("set the follow target first",
      followed and followed[0][followed[0].index("-s") + 1] == "/gui/follow")
check("then sent the offset, which is ignored without a target",
      any("/gui/follow/offset" in c for c in calls))
check("aimed from behind and above at the panel's own default distance",
      L.CAMERA_VIEW == "rear_above" and L.CAMERA_DISTANCE_M == 12)

print("11. PX4's stdin never reaches end-of-file")
# Measured 13 Oct 2026: ~/uas_sim_logs/sim_launch.log had reached 19.5 GB,
# and sampled anywhere in the middle it was nothing but "clear the line,
# print pxh> " over and over with no newlines. The cause was stdin on
# /dev/null, which ends immediately; PX4's shell read the end, printed a
# fresh prompt and read again, for ever. A terminal BLOCKS instead, which
# is why tools/start_world.sh never showed it.
#
# The check is on the behaviour rather than on the source, because the
# source reads perfectly reasonably either way - DEVNULL looks like the
# careful choice, and it is the one that filled the disk.
import subprocess as _sp                                     # noqa: E402

_probe = ("import sys; sys.stdout.write("
          "'EOF' if sys.stdin.readline() == '' else 'DATA')")


def _stdin_ends(**plumbing):
    """True if a child reading stdin gets end-of-file straight away."""
    proc = _sp.Popen([sys.executable, "-c", _probe],
                     stdout=_sp.PIPE, text=True, start_new_session=True,
                     **plumbing)
    try:
        return proc.communicate(timeout=5)[0].strip() == "EOF"
    except _sp.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)
        return False


check("/dev/null really does end at once - the trap this avoids",
      _stdin_ends(stdin=_sp.DEVNULL))

_r, _w = os.pipe()
os.set_inheritable(_w, True)
try:
    # The launcher exits once everything is up, so its own copies of both
    # ends are closed immediately here too. If the child only stayed alive
    # because the parent held the pipe, this is where that would show.
    _ends = _stdin_ends(stdin=_r, pass_fds=(_w,))
finally:
    os.close(_r)
    os.close(_w)
check("a pipe whose write end the child holds does not end, so the "
      "prompt cannot loop", not _ends)

_src = open(os.path.join(REPO, "tools", "uas_launcher.py")).read()
_start = _src[_src.index("def start_simulator"):]
_start = _start[:_start.index("\ndef ")]
check("and start_simulator uses it rather than DEVNULL",
      "pass_fds=(write_fd,)" in _start and "stdin=subprocess.DEVNULL" not in _start)

print("12. one icon: start it, or ask before stopping it")
# The two desktop icons became one on 13 Oct 2026. The old red icon
# stopped everything the instant it was touched; with a single icon that
# behaviour would end an exercise on a stray double-click, so a click on a
# RUNNING simulator asks first and anything unexpected leaves it alone.
import contextlib as _ctx                                    # noqa: E402
import io as _io                                             # noqa: E402

_real = (L.stop_all, L.launch, L.simulator_running, L._station_answering)


def _toggle(running, answer):
    """Returns what the toggle did, as a list of calls."""
    done = []
    L.stop_all = lambda *a, **k: done.append("stop") or []
    L.launch = lambda key, open_ui=True: done.append("start") or 0
    L.simulator_running = lambda: running
    L._station_answering = lambda: running

    def ask(_prompt):
        if isinstance(answer, type) and issubclass(answer, BaseException):
            raise answer
        if answer is None:
            raise AssertionError("asked when nothing was running")
        return answer

    with _ctx.redirect_stdout(_io.StringIO()):
        L.toggle("coast", ask=ask)
    return done


try:
    check("a click on a stopped simulator starts it, with no questions",
          _toggle(False, None) == ["start"])
    check("a click on a running one can stop it", _toggle(True, "1") == ["stop"])
    check("or restart it, which is what changing training area needs",
          _toggle(True, "2") == ["stop", "start"])
    check("or leave it alone", _toggle(True, "3") == [])
    # The dangerous direction is stopping something by accident, so every
    # answer that is not deliberately "stop" has to mean "leave it".
    check("just pressing Enter leaves it running", _toggle(True, "") == [])
    check("and so does a stray keypress", _toggle(True, "x") == [])
    check("and so does closing the window mid-question",
          _toggle(True, EOFError) == [])
    check("and so does Ctrl+C", _toggle(True, KeyboardInterrupt) == [])
finally:
    (L.stop_all, L.launch, L.simulator_running, L._station_answering) = _real

_installer = open(os.path.join(REPO, "tools", "install_launcher.sh")).read()
check("the installer writes one entry, pointed at --toggle",
      "--toggle" in _installer and "uav-academy-gcs-pro.desktop" in _installer)
check("and clears away the two icons it replaces",
      "OLD_START" in _installer and "OLD_STOP" in _installer)

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
