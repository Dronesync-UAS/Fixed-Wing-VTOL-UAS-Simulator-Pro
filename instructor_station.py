#!/usr/bin/env python3
"""
UAV Academy GCS Pro

The instructor-only desktop ground control station (renamed from
"UAS Academy Instructor Station" on 5 Sep 2026). A plainer "UAV Academy
GCS" for students is planned for later, once this one is tested and
working.

Built around a plugin system so new scenarios can be added later by just
dropping a new file into the plugins/ folder - nothing else needs to change.

Run this AFTER the simulator is already running.
"""

import http.server
import socketserver
import json
import math
import threading
import sys
import os
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))

from simulator_link import telemetry, connection_status, flight_path, home_latlon
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
            button = f'<button class="{p["style"]}" onclick="send(\'{p["id"]}\')">{dot}{p["label"]}</button>'

            # Plugins may declare an "inputs" list - number boxes the
            # instructor fills in before pressing the button (e.g. LOITER
            # radius). Their values are sent as query parameters and passed
            # to the plugin's handler as keyword arguments.
            fields = ""
            for inp in p.get("inputs", []):
                fid = f'in-{p["id"]}-{inp["name"]}'
                attrs = f'value="{inp.get("default", "")}"'
                if "min" in inp:
                    attrs += f' min="{inp["min"]}"'
                if "max" in inp:
                    attrs += f' max="{inp["max"]}"'
                attrs += f' step="{inp.get("step", "any")}"'
                fields += (
                    f'<label class="field"><span>{inp["label"]}</span>'
                    f'<input type="number" id="{fid}" class="param-input" '
                    f'data-plugin="{p["id"]}" data-param="{inp["name"]}" {attrs}></label>'
                )
            if fields:
                html += f'<div class="btn-stack">{fields}{button}</div>'
            else:
                html += button
        html += '</div></div>'
    return html


# Shown immediately when the app window opens, before PX4 has answered.
# Polls /connection_status and reloads itself once connected, at which
# point the server below starts handing out PAGE_TEMPLATE instead.
CONNECTING_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>UAV Academy GCS Pro</title>
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
  <div class="brand">UAV ACADEMY GCS PRO</div>
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
<title>UAV Academy GCS Pro</title>
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

  /* Buttons that take an instructor-entered value before firing (e.g.
     LOITER radius) - the number box(es) sit directly above the button. */
  .btn-stack {{ display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 110px; }}
  .btn-stack button {{ width: 100%; flex: none; }}
  .field {{ display: flex; flex-direction: column; gap: 2px; }}
  .field span {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; color: #62708a; }}
  .param-input {{
    background: #0d1219; border: 1px solid #2c3a4d; border-radius: 7px;
    color: #eee; font-size: 13px; font-weight: 600; padding: 8px 10px; width: 100%;
  }}
  .param-input:focus {{ outline: none; border-color: #4a90d9; }}

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
    <div class="brand">UAV ACADEMY GCS PRO</div>
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
        <div class="panel-title">Live Nose Camera (FPV) &mdash; Forward View + Attitude</div>
        <div class="fpv-wrap">
          <img src="/video_feed" class="fpv-video"
               onerror="this.style.display='none'; document.getElementById('video-fallback').style.display='block';">
          <canvas id="hud" class="fpv-hud" width="960" height="540"></canvas>
        </div>
        <div id="video-fallback" style="display:none; color:#62708a; font-size:12px; padding:20px; text-align:center;">
          No video signal yet - camera stream starts once the simulator is running.
        </div>
        <label class="hud-toggle"><input type="checkbox" id="hud-on" checked> Attitude overlay</label>
      </div>
      <div id="status">Ready.</div>
    </div>
  </div>

<script>
function send(id) {{
  document.getElementById('status').innerText = 'Sending...';
  const params = new URLSearchParams();
  document.querySelectorAll('.param-input[data-plugin="' + id + '"]').forEach(el => {{
    params.append(el.dataset.param, el.value);
  }});
  const qs = params.toString();
  fetch('/action/' + id + (qs ? '?' + qs : '')).then(r => r.text()).then(t => {{
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


# ---------------------------------------------------------------------------
# Extra views bolted onto the page after PAGE_TEMPLATE.format() - kept as
# plain strings (not format templates) so the JS below doesn't need every
# brace doubled. Added 3 Sep 2026:
#   * Flight Path  - a north-up plan view of where the aircraft has flown,
#                    from GLOBAL_POSITION_INT history (/flight_path).
#   * FPV overlay  - an artificial-horizon / attitude ("gyro") HUD drawn
#                    on top of the nose-camera stream, from ATTITUDE.
# ---------------------------------------------------------------------------
EXTRA_PANELS = """
<div class="panel" id="flightpath-panel" style="max-width: 900px; margin-top: 14px;">
  <div class="panel-title">Flight Path &mdash; Plan View (North Up)</div>
  <canvas id="flightpath"></canvas>
  <div class="fp-legend">
    <span><b id="fp-range">-</b> across</span>
    <span><b id="fp-dist">-</b> from home</span>
    <span><b id="fp-alt">-</b> altitude</span>
    <span><b id="fp-points">0</b> track points</span>
    <span style="color:#ffd24a">&#9650;</span> aircraft
    <span style="color:#4caf50">&#9679;</span> home
  </div>
</div>
"""

EXTRA_STYLE = """
<style>
  .fpv-wrap { position: relative; width: 100%; border-radius: 10px; overflow: hidden; background: #000; }
  .fpv-video { width: 100%; display: block; }
  .fpv-hud { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .hud-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: #62708a; margin-top: 8px; }
  #flightpath { width: 100%; height: 420px; display: block; background: #0d1219; border-radius: 10px; }
  .fp-legend { display: flex; gap: 16px; font-size: 11px; color: #62708a; margin-top: 8px; flex-wrap: wrap; align-items: center; }
  .fp-legend b { color: #eee; font-weight: 600; }
</style>
"""

EXTRA_SCRIPT = """
<script>
(function () {
  var telem = {};
  function poll() {
    fetch('/telemetry').then(function (r) { return r.json(); })
      .then(function (d) { telem = d; }).catch(function () {});
  }
  setInterval(poll, 200); poll();

  function fit(cv) {
    var w = cv.clientWidth, h = cv.clientHeight;
    if (w && h && (cv.width !== w || cv.height !== h)) { cv.width = w; cv.height = h; }
  }

  // ---------- FPV artificial-horizon / attitude overlay ----------
  var hud = document.getElementById('hud');
  var hctx = hud.getContext('2d');
  function drawHud() {
    var w = hud.width, h = hud.height, cx = w / 2, cy = h / 2;
    hctx.clearRect(0, 0, w, h);
    if (!w || !h || !document.getElementById('hud-on').checked) return;

    var rollDeg = telem.roll_deg || 0;
    var pitchDeg = telem.pitch_deg || 0;
    var pxPerDeg = h / 50;

    hctx.save();
    hctx.translate(cx, cy);
    hctx.rotate(-rollDeg * Math.PI / 180);
    hctx.translate(0, pitchDeg * pxPerDeg);
    hctx.strokeStyle = 'rgba(120,220,255,0.9)';
    hctx.fillStyle = 'rgba(120,220,255,0.95)';
    hctx.lineWidth = 2;
    hctx.font = '12px -apple-system, sans-serif';
    hctx.textAlign = 'left';
    hctx.beginPath(); hctx.moveTo(-w, 0); hctx.lineTo(w, 0); hctx.stroke();
    for (var d = -40; d <= 40; d += 10) {
      if (d === 0) continue;
      var y = -d * pxPerDeg;
      var half = (d % 20 === 0) ? 74 : 42;
      var tick = (d < 0) ? -7 : 7;
      hctx.beginPath();
      hctx.moveTo(-half, y + tick); hctx.lineTo(-half, y); hctx.lineTo(half, y); hctx.lineTo(half, y + tick);
      hctx.stroke();
      hctx.fillText(Math.abs(d), half + 6, y + 4);
      hctx.fillText(Math.abs(d), -half - 20, y + 4);
    }
    hctx.restore();

    // fixed aircraft reference
    hctx.strokeStyle = '#ffd24a'; hctx.lineWidth = 3;
    hctx.beginPath();
    hctx.moveTo(cx - 70, cy); hctx.lineTo(cx - 24, cy); hctx.lineTo(cx - 12, cy + 12);
    hctx.moveTo(cx + 70, cy); hctx.lineTo(cx + 24, cy); hctx.lineTo(cx + 12, cy + 12);
    hctx.stroke();
    hctx.fillStyle = '#ffd24a';
    hctx.beginPath(); hctx.arc(cx, cy, 3, 0, 7); hctx.fill();

    // roll scale (fixed) + rolling pointer
    hctx.strokeStyle = 'rgba(255,255,255,0.8)'; hctx.lineWidth = 2;
    var R = Math.min(w, h) * 0.36;
    hctx.beginPath(); hctx.arc(cx, cy, R, Math.PI * 1.18, Math.PI * 1.82); hctx.stroke();
    [-60, -45, -30, -15, 0, 15, 30, 45, 60].forEach(function (a) {
      var ar = (a - 90) * Math.PI / 180;
      var inr = (a % 30 === 0) ? R - 13 : R - 8;
      hctx.beginPath();
      hctx.moveTo(cx + Math.cos(ar) * R, cy + Math.sin(ar) * R);
      hctx.lineTo(cx + Math.cos(ar) * inr, cy + Math.sin(ar) * inr);
      hctx.stroke();
    });
    var pa = (-rollDeg - 90) * Math.PI / 180;
    hctx.fillStyle = '#ff5252';
    hctx.beginPath();
    hctx.moveTo(cx + Math.cos(pa) * R, cy + Math.sin(pa) * R);
    hctx.lineTo(cx + Math.cos(pa - 0.045) * (R + 13), cy + Math.sin(pa - 0.045) * (R + 13));
    hctx.lineTo(cx + Math.cos(pa + 0.045) * (R + 13), cy + Math.sin(pa + 0.045) * (R + 13));
    hctx.closePath(); hctx.fill();

    // readout boxes: airspeed (L), altitude (R), heading (top)
    function box(x, y, txt) {
      hctx.fillStyle = 'rgba(0,0,0,0.5)';
      hctx.fillRect(x - 46, y - 14, 92, 28);
      hctx.strokeStyle = 'rgba(120,220,255,0.9)'; hctx.lineWidth = 1;
      hctx.strokeRect(x - 46, y - 14, 92, 28);
      hctx.fillStyle = '#dff6ff'; hctx.font = 'bold 14px -apple-system, sans-serif';
      hctx.textAlign = 'center'; hctx.fillText(txt, x, y + 5);
    }
    var spd = (telem.airspeed_ms != null && telem.airspeed_ms > 0.2) ? telem.airspeed_ms : telem.groundspeed_ms;
    box(64, cy, (spd != null ? spd.toFixed(0) : '--') + ' m/s');
    box(w - 64, cy, (telem.altitude_m != null ? telem.altitude_m.toFixed(0) : '--') + ' m');
    box(cx, 22, (telem.heading_deg != null ? telem.heading_deg : '--') + '\\u00b0');

    hctx.fillStyle = '#9fe6ff'; hctx.font = '11px -apple-system, sans-serif'; hctx.textAlign = 'center';
    hctx.fillText('BANK ' + rollDeg.toFixed(0) + '\\u00b0   PITCH ' + pitchDeg.toFixed(0) + '\\u00b0', cx, h - 12);
  }

  // ---------- Flight path plan view ----------
  var fp = document.getElementById('flightpath');
  var fctx = fp.getContext('2d');
  function niceStep(x) {
    if (x <= 0) return 100;
    var p = Math.pow(10, Math.floor(Math.log(x) / Math.LN10));
    var n = x / p;
    return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
  }
  function fmt(m) { return m >= 1000 ? (m / 1000).toFixed(m >= 10000 ? 0 : 1) + ' km' : m.toFixed(0) + ' m'; }
  function drawPath() {
    fetch('/flight_path').then(function (r) { return r.json(); }).then(function (data) {
      var W = fp.width, H = fp.height;
      fctx.clearRect(0, 0, W, H);
      if (!W || !H) return;
      var pts = data.points || [];
      document.getElementById('fp-points').innerText = pts.length;
      var home = (data.home && data.home.lat != null) ? data.home
               : (pts.length ? { lat: pts[0][0], lon: pts[0][1] } : null);
      if (!home || !pts.length) return;

      var latR = home.lat * Math.PI / 180;
      var mx = [], my = [], maxAbs = 25;
      for (var i = 0; i < pts.length; i++) {
        var ex = (pts[i][1] - home.lon) * Math.cos(latR) * 111320;
        var ny = (pts[i][0] - home.lat) * 110540;
        mx.push(ex); my.push(ny);
        maxAbs = Math.max(maxAbs, Math.abs(ex), Math.abs(ny));
      }
      maxAbs *= 1.15;
      var scale = Math.min(W, H) / (2 * maxAbs);
      var ox = W / 2, oy = H / 2;

      var step = niceStep(maxAbs / 2.2);
      fctx.strokeStyle = '#1f2b3a'; fctx.fillStyle = '#3d4b5e';
      fctx.font = '10px -apple-system, sans-serif'; fctx.textAlign = 'left'; fctx.lineWidth = 1;
      for (var rr = step; rr <= maxAbs; rr += step) {
        fctx.beginPath(); fctx.arc(ox, oy, rr * scale, 0, 7); fctx.stroke();
        fctx.fillText(fmt(rr), ox + 4, oy - rr * scale + 12);
      }
      fctx.fillStyle = '#62708a'; fctx.textAlign = 'center';
      fctx.fillText('N', ox, 12);

      fctx.strokeStyle = '#4ad0ff'; fctx.lineWidth = 2; fctx.beginPath();
      for (var j = 0; j < pts.length; j++) {
        var X = ox + mx[j] * scale, Y = oy - my[j] * scale;
        if (j) fctx.lineTo(X, Y); else fctx.moveTo(X, Y);
      }
      fctx.stroke();

      fctx.fillStyle = '#4caf50';
      fctx.beginPath(); fctx.arc(ox, oy, 5, 0, 7); fctx.fill();

      var last = pts.length - 1;
      var hx = ox + mx[last] * scale, hy = oy - my[last] * scale;
      var hdg = (telem.heading_deg || 0) * Math.PI / 180;
      fctx.save(); fctx.translate(hx, hy); fctx.rotate(hdg);
      fctx.fillStyle = '#ffd24a';
      fctx.beginPath(); fctx.moveTo(0, -10); fctx.lineTo(7, 8); fctx.lineTo(0, 3); fctx.lineTo(-7, 8);
      fctx.closePath(); fctx.fill();
      fctx.restore();

      var dist = Math.sqrt(mx[last] * mx[last] + my[last] * my[last]);
      document.getElementById('fp-range').innerText = fmt(maxAbs * 2);
      document.getElementById('fp-dist').innerText = fmt(dist);
      document.getElementById('fp-alt').innerText = pts[last][2].toFixed(0) + ' m';
    }).catch(function () {});
  }

  setInterval(function () { fit(hud); drawHud(); }, 150);
  setInterval(function () { fit(fp); drawPath(); }, 1000);
  fit(fp); drawPath();
})();
</script>
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
                page = PAGE_TEMPLATE.format(buttons=render_buttons())
                page = page.replace('<div id="status">Ready.</div>',
                                    EXTRA_PANELS + '<div id="status">Ready.</div>')
                page = page.replace("</body>", EXTRA_STYLE + EXTRA_SCRIPT + "</body>")
                self.wfile.write(page.encode("utf-8"))
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
            # NaN / inf are not valid JSON and make JSON.parse() throw in
            # the browser, taking the whole telemetry panel down with them.
            safe = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                    for k, v in telemetry.items()}
            self.wfile.write(json.dumps(safe).encode("utf-8"))
        elif self.path == "/failure_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(failure_status()).encode("utf-8"))
        elif self.path == "/flight_path":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {
                "home": home_latlon,
                "points": [[round(p[0], 7), round(p[1], 7), p[2]] for p in flight_path],
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
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
            parsed = urlparse(self.path)
            action_id = parsed.path.split("/action/")[1]
            plugin = plugins_by_id.get(action_id)
            if plugin is None:
                self._respond("Unknown action.", 404)
                return
            # Any query parameters (from a plugin's "inputs" boxes) are
            # passed straight through to the handler as keyword arguments,
            # e.g. /action/loiter?radius_m=200 -> loiter(radius_m="200").
            kwargs = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            try:
                result = plugin["handler"](**kwargs)
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
    print(f"UAV Academy GCS Pro running - open a browser to: http://localhost:{PORT}")

    # The instructor window is just a convenience wrapper around the local
    # web server - it is NOT the station itself. Closing it (or a WebKit
    # backend crash, or pywebview not being installed) must not take the
    # server down with it, or the instructor silently loses live telemetry,
    # the camera feed and - most importantly - event logging mid-session.
    # Added 3 Sep 2026 after the window disappearing was repeatedly
    # mistaken for the whole station crashing. Whatever happens to the
    # window, we fall through to the keep-alive loop below and the station
    # stays reachable in a browser at http://localhost:PORT until Ctrl+C.
    try:
        import webview
    except ImportError:
        webview = None
        print("\n(pywebview not installed - running in browser mode instead.")
        print(f"Open a browser to http://localhost:{PORT} manually.)\n")

    if webview is not None:
        try:
            webview.create_window("UAV Academy GCS Pro", f"http://localhost:{PORT}",
                                   width=1000, height=850, background_color="#0b1017")
            webview.start()
        except Exception as e:
            print(f"\n(Instructor window unavailable: {e} - running in browser mode instead.)")
        print(f"\nInstructor window closed - station still running at http://localhost:{PORT}")
        print("Press Ctrl+C in this terminal to shut the station down.\n")

    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down UAV Academy GCS Pro.")
