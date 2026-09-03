#!/usr/bin/env python3
"""
UAS Academy Ground Control Station - Instructor Station

A desktop app for instructors, built around a plugin system so new
scenarios can be added later by just dropping a new file into the
plugins/ folder - nothing else needs to change.

Run this AFTER the simulator is already running.
"""

import http.server
import socketserver
import json
import threading
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from simulator_link import telemetry, connection_status
from plugin_loader import load_plugins
from video_feed import start_video_capture, mjpeg_generator

PORT = 8080
_video_node = start_video_capture()  # starts listening for camera frames immediately
plugins = load_plugins()
plugins_by_id = {p["id"]: p for p in plugins}

# Group plugins by category, in a sensible fixed order
CATEGORY_ORDER = ["Flight Ops", "Flight Mode", "Function Test", "Failure Injection", "Simulation Control", "Camera", "Experimental - In Development"]
categories = {cat: [] for cat in CATEGORY_ORDER}
for p in plugins:
    categories.setdefault(p["category"], []).append(p)


def failure_status():
    """Which plugins are currently in their "active/failed" state, so the
    button can show a live on/off light. Only plugins that expose a
    module-level `state` dict with an "active" key are included (the
    toggle-style failure plugins) - added 23 Aug 2026, directly prompted
    by a live test where a motor/engine/GPS/RC failure was left switched
    on without anyone noticing, because there was no visual reminder."""
    status = {}
    for p in plugins:
        state = getattr(p.get("_module"), "state", None)
        if isinstance(state, dict) and "active" in state:
            status[p["id"]] = bool(state["active"])
    return status


def render_buttons():
    html = ""
    status = failure_status()
    for cat in CATEGORY_ORDER:
        items = categories.get(cat, [])
        if not items:
            continue
        html += f'<div class="panel"><div class="panel-title">{cat}</div><div class="row">'
        for p in items:
            dot = ""
            if p["id"] in status:
                dot_class = "dot-active" if status[p["id"]] else "dot-inactive"
                dot = f'<span class="status-dot {dot_class}" id="dot-{p["id"]}"></span>'
            html += f'<button class="{p["style"]}" onclick="send(\'{p["id"]}\')">{dot}{p["label"]}</button>'
        html += '</div></div>'
    return html


# Shown immediately when the app window opens, before PX4 has answered.
# Polls /connection_status and reloads itself once connected, at which
# point the server below starts handing out PAGE_TEMPLATE instead.
CONNECTING_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>UAS Academy - Instructor Station</title>
<style>
  body {
    font-family: -apple-system, 'Segoe UI', sans-serif;
    background: #0a0e14; color: #eee; margin: 0; height: 100vh;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }
  .brand { font-weight: 700; font-size: 15px; letter-spacing: 1px; color: #4a90d9; margin-bottom: 26px; }
  .spinner {
    width: 34px; height: 34px; border-radius: 50%;
    border: 3px solid #232f40; border-top-color: #4a90d9;
    animation: spin 0.9s linear infinite; margin-bottom: 22px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  #msg { font-size: 14px; color: #9aa7bd; max-width: 440px; text-align: center; line-height: 1.5; }
</style>
</head>
<body>
  <div class="brand">UAS ACADEMY &mdash; INSTRUCTOR STATION</div>
  <div class="spinner"></div>
  <div id="msg">Connecting to the simulator...</div>
<script>
function poll() {
  fetch('/connection_status').then(r => r.json()).then(d => {
    document.getElementById('msg').innerText = d.message;
    if (d.connected) {
      location.reload();
    } else {
      setTimeout(poll, 700);
    }
  }).catch(() => setTimeout(poll, 700));
}
poll();
</script>
</body>
</html>
"""


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>UAS Academy - Instructor Station</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, 'Segoe UI', sans-serif;
    background: #0a0e14; color: #eee; margin: 0; height: 100vh; overflow: hidden;
    display: flex; flex-direction: column;
  }}

  /* ===== Top status bar ===== */
  .topbar {{
    background: #10151d; border-bottom: 1px solid #1f2733;
    display: flex; align-items: center; padding: 0 20px; height: 56px; flex-shrink: 0;
    gap: 28px;
  }}
  .brand {{ font-weight: 700; font-size: 15px; letter-spacing: 1px; color: #4a90d9; margin-right: 10px; }}
  .status-item {{ display: flex; flex-direction: column; }}
  .status-item .k {{ font-size: 9px; color: #62708a; text-transform: uppercase; letter-spacing: 0.5px; }}
  .status-item .v {{ font-size: 14px; font-weight: 600; margin-top: 1px; }}
  .armed-yes {{ color: #ff5252; }}
  .armed-no {{ color: #4caf50; }}

  /* ===== Body: sidebar + main ===== */
  .body-row {{ display: flex; flex: 1; overflow: hidden; }}

  .sidebar {{
    width: 200px; background: #0d1219; border-right: 1px solid #1f2733;
    padding: 14px 0; overflow-y: auto; flex-shrink: 0;
  }}
  .nav-item {{
    padding: 10px 20px; font-size: 13px; color: #62708a; cursor: default;
    border-left: 3px solid transparent;
  }}
  .nav-item.active {{ color: #eee; border-left-color: #4a90d9; background: #131a24; }}

  .main {{ flex: 1; padding: 20px; overflow-y: auto; }}

  .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 14px; max-width: 900px; }}
  .panel {{ background: #131c28; border: 1px solid #232f40; border-radius: 14px; padding: 16px; }}
  .panel-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #62708a; margin-bottom: 10px; }}
  .row {{ display: flex; gap: 8px; flex-wrap: wrap; }}

  button {{
    position: relative;
    font-size: 13px; font-weight: 600; padding: 11px 14px;
    border-radius: 9px; border: none; cursor: pointer; flex: 1; min-width: 110px;
    transition: transform 0.08s ease;
  }}
  button:active {{ transform: scale(0.96); }}
  .arm {{ background: #2e7d32; color: white; }}
  .disarm {{ background: #c62828; color: white; }}
  .normal {{ background: #1565c0; color: white; }}
  .highlight {{ background: #ef6c00; color: white; }}
  .warning {{ background: #ad1457; color: white; }}
  .experimental {{ background: #1a1a1a; color: #666; border: 1px dashed #333; cursor: not-allowed; }}

  /* Small on/off status light for toggle-style failure buttons (GPS, RC
     Signal, Data Link, Motor, Engine) - added 23 Aug 2026 so a failure
     left switched on is impossible to miss, after a live test where
     exactly that happened. Red+pulsing = currently active/failed,
     matching the standard aviation convention that red means a fault
     needs attention; green = normal/restored. */
  .status-dot {{
    position: absolute; top: 6px; right: 6px;
    width: 10px; height: 10px; border-radius: 50%;
    border: 1.5px solid rgba(0,0,0,0.35);
  }}
  .dot-inactive {{ background: #4caf50; }}
  .dot-active {{
    background: #ff1744;
    box-shadow: 0 0 6px 2px rgba(255,23,68,0.6);
    animation: dotpulse 1.1s ease-in-out infinite;
  }}
  @keyframes dotpulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.45; }} }}

  .video-placeholder {{
    background: #0d1219; border: 1px dashed #2c3a4d; border-radius: 14px;
    padding: 40px 20px; text-align: center; color: #4a5568; font-size: 12px;
    max-width: 900px; margin-top: 14px;
  }}

  #status {{ margin-top: 16px; font-size: 12px; color: #62708a; }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">UAS ACADEMY</div>
    <div class="status-item"><div class="k">Vehicle</div><div class="v">STANDARD_VTOL-01</div></div>
    <div class="status-item"><div class="k">Mode</div><div class="v" id="t-mode">-</div></div>
    <div class="status-item"><div class="k">Status</div><div class="v" id="t-armed">-</div></div>
    <div class="status-item"><div class="k">Altitude</div><div class="v" id="t-alt">-</div></div>
    <div class="status-item"><div class="k">Speed</div><div class="v" id="t-speed">-</div></div>
    <div class="status-item"><div class="k">Heading</div><div class="v" id="t-heading">-</div></div>
    <div class="status-item"><div class="k">GPS</div><div class="v" id="t-gps">-</div></div>
    <div class="status-item"><div class="k">Battery</div><div class="v" id="t-batt">-</div></div>
  </div>

  <div class="body-row">
    <div class="sidebar">
      <div class="nav-item active">INSTRUCTOR<br><span style="font-size:11px;color:#4a5568;">Simulator Controls</span></div>
      <div class="nav-item">FLY (coming soon)</div>
      <div class="nav-item">PLAN / MISSION (coming soon)</div>
      <div class="nav-item">PAYLOAD / CAMERA (coming soon)</div>
      <div class="nav-item">LOGS (coming soon)</div>
    </div>

    <div class="main">
      <div class="grid">
        {buttons}
      </div>
      <div class="panel" style="max-width: 900px; margin-top: 14px;">
        <div class="panel-title">Live Nose Camera (FPV)</div>
        <img src="/video_feed" style="width: 100%; border-radius: 10px; display: block; background: #000;"
             onerror="this.style.display='none'; document.getElementById('video-fallback').style.display='block';">
        <div id="video-fallback" style="display:none; color:#62708a; font-size:12px; padding:20px; text-align:center;">
          No video signal yet - camera stream starts once the simulator is running.
        </div>
      </div>
      <div id="status">Ready.</div>
    </div>
  </div>

<script>
function send(id) {{
  document.getElementById('status').innerText = 'Sending...';
  fetch('/action/' + id).then(r => r.text()).then(t => {{
    document.getElementById('status').innerText = t;
    refreshFailureStatus();
  }});
}}
function refreshTelemetry() {{
  fetch('/telemetry').then(r => r.json()).then(d => {{
    const armedEl = document.getElementById('t-armed');
    armedEl.innerText = d.armed ? 'ARMED' : 'Disarmed';
    armedEl.className = 'v ' + (d.armed ? 'armed-yes' : 'armed-no');
    document.getElementById('t-mode').innerText = d.mode;
    document.getElementById('t-alt').innerText = d.altitude_m + ' m';
    document.getElementById('t-speed').innerText = d.groundspeed_ms + ' m/s';
    document.getElementById('t-heading').innerText = d.heading_deg + '\\u00b0';
    document.getElementById('t-gps').innerText = d.satellites !== null ? d.satellites + ' sats' : '-';
    document.getElementById('t-batt').innerText = d.battery_pct !== null ? d.battery_pct + '%' : '-';
  }});
}}
function refreshFailureStatus() {{
  fetch('/failure_status').then(r => r.json()).then(d => {{
    for (const id in d) {{
      const dot = document.getElementById('dot-' + id);
      if (dot) {{
        dot.className = 'status-dot ' + (d[id] ? 'dot-active' : 'dot-inactive');
      }}
    }}
  }});
}}
setInterval(refreshTelemetry, 1000);
setInterval(refreshFailureStatus, 1000);
refreshTelemetry();
refreshFailureStatus();
</script>
</body>
</html>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _respond(self, text, code=200):
        self.send_response(code)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if connection_status["connected"]:
                self.wfile.write(PAGE_TEMPLATE.format(buttons=render_buttons()).encode("utf-8"))
            else:
                self.wfile.write(CONNECTING_PAGE.encode("utf-8"))
        elif self.path == "/connection_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(connection_status).encode("utf-8"))
        elif self.path == "/telemetry":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(telemetry).encode("utf-8"))
        elif self.path == "/failure_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(failure_status()).encode("utf-8"))
        elif self.path == "/video_feed":
            self.send_response(200)
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for chunk in mjpeg_generator():
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path.startswith("/action/"):
            action_id = self.path.split("/action/")[1]
            plugin = plugins_by_id.get(action_id)
            if plugin is None:
                self._respond("Unknown action.", 404)
                return
            try:
                result = plugin["handler"]()
                self._respond(result)
            except Exception as e:
                self._respond(f"Error: {e}", 500)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def run_server():
    with ThreadedServer(("", PORT), Handler) as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    print(f"Loaded {len(plugins)} controls across {len([c for c in categories.values() if c])} categories.")
    threading.Thread(target=run_server, daemon=True).start()
    print(f"Instructor Station running - open a browser to: http://localhost:{PORT}")

    try:
        import webview
        webview.create_window("UAS Academy - Instructor Station", f"http://localhost:{PORT}",
                               width=1000, height=850, background_color="#0b1017")
        webview.start()
    except ImportError:
        print("\n(pywebview not installed - running in browser mode instead.")
        print(f"Open a browser to http://localhost:{PORT} manually.)\n")
        import time
        while True:
            time.sleep(1)
