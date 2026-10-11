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

print()
print("FAILED: %s" % fails if fails else "all checks passed")
sys.exit(1 if fails else 0)
