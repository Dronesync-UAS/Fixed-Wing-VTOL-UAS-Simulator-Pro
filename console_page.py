"""
The instructor console's page: the rebuilt layout approved 11 Oct 2026.

WHAT CHANGED, AND WHY
---------------------
The old page was a grid of panels. Everything had equal weight, so the thing
an instructor actually watches - the aircraft - was one tile among fifteen,
and seeing it properly meant the Gazebo window. The new page gives the
picture the whole screen and puts the controls around it.

  hero          one of three views, full size: chase camera, nose camera,
                or the map. Click a corner tile, or the tabs, to swap.
  left rail     flight ops, then the emergency controls
  right rail    the instructor-only controls: failure injection, weather,
                wind, environment, freeze
  bottom band   the flight parameters, with the attitude gyro set across its
                top edge, and the CAP722B strip beneath them

Two layouts, because the right answer depends on the room:
  Pilot     the picture runs edge to edge and the rails float over it
  Station   solid rails inset the picture, so nothing ever overlaps it

ONE ELEMENT PER VIEW
--------------------
The three views are built once and MOVED between the hero slot and the two
corner tiles. They are not re-created per slot, and there is deliberately no
second <img> pointed at the same feed: each MJPEG stream is one HTTP
connection the station has to encode frames for, so a duplicated tag would
double the camera work for a picture nobody is looking at.

The canvas drawing - the nose camera's attitude overlay and the map's track,
terrain and rings - is the existing, proven code in instructor_station's
EXTRA_SCRIPT, reached through the same element ids it has always used
(#hud, #hud-on, #flightpath, #fp-*). This module provides those ids; it does
not re-implement any of it.

The classic page is still served at /classic, and nothing here deletes it.
"""

# ---------------------------------------------------------------------------
# Markup. Written as a plain string with explicit placeholders rather than a
# format template: this page is mostly CSS and JavaScript, and doubling every
# brace in it is how a working page quietly becomes a broken one.
# ---------------------------------------------------------------------------

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>UAV Academy GCS Pro</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:wght@400;500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap">
<style>
  :root {
    --ink: #ffffff;
    --dim: #c3ccd6;
    --panel: #151a22;
    --sunk: #1e2430;
    --good: #57cc7f;
    --warn: #ffc94d;
    --bad: #e03b3b;
  }
  * { box-sizing: border-box; }
  html, body { margin: 0; height: 100%; overflow: hidden; }
  body {
    background: #0f1319; color: var(--ink);
    font-family: 'IBM Plex Sans', system-ui, sans-serif;
    user-select: none;
  }
  button { font-family: inherit; transition: filter 80ms, transform 80ms; }
  button:hover { filter: brightness(1.15); }
  button:active { transform: translateY(1px); filter: brightness(1.35); }
  .mono { font-family: 'IBM Plex Mono', monospace; }

  /* ---------- top bar ---------- */
  #topbar {
    position: absolute; left: 0; right: 0; top: 0; height: 44px; z-index: 40;
    display: flex; align-items: center; gap: 12px; padding: 0 14px;
  }
  #topbar .badge {
    background: rgba(255,255,255,0.14); border-radius: 5px;
    padding: 4px 12px; font-size: 13px; font-weight: 500;
  }
  #t-mode { font-size: 14px; font-weight: 500; }
  .seg { display: flex; gap: 3px; background: rgba(0,0,0,0.5); border-radius: 8px; padding: 3px; }
  .seg button {
    height: 26px; padding: 0 14px; border: 0; border-radius: 6px; cursor: pointer;
    font-size: 12px; font-weight: 500; background: transparent; color: var(--ink);
  }
  .seg button.on { background: #ffffff; color: #10151d; font-weight: 600; }
  .icons { display: flex; align-items: center; gap: 16px; font-size: 13px; }
  .icons span.item { display: flex; align-items: center; gap: 6px; }
  #t-health.stale { color: #ff8a8a; }

  /* ---------- message strip ---------- */
  #status {
    position: absolute; left: 50%; top: 54px; transform: translateX(-50%); z-index: 45;
    max-width: 620px; display: flex; align-items: center; gap: 9px;
    padding: 7px 15px; border-radius: 8px; background: rgba(0,0,0,0.78);
    box-shadow: 0 3px 12px rgba(0,0,0,0.45); font-size: 13px; font-weight: 500;
  }
  #status.alert { background: rgba(120,26,26,0.94); }

  /* ---------- limit banner (CAP722B 5.3(c)) ---------- */
  #limit-banner {
    position: absolute; left: 50%; top: 96px; transform: translateX(-50%); z-index: 46;
    display: none; gap: 14px; align-items: center; padding: 8px 16px; border-radius: 8px;
    font-size: 13px; font-weight: 500; box-shadow: 0 3px 12px rgba(0,0,0,0.5);
  }
  #limit-banner.warn { background: #7a5a12; color: #ffe9b0; }
  #limit-banner.breach { background: #7b1a1a; color: #ffd6d6; }
  #limit-banner .tag { font-weight: 700; letter-spacing: 1px; }

  /* ---------- hero and views ---------- */
  #hero { position: absolute; overflow: hidden; background: #000; z-index: 10; }
  .view { position: absolute; inset: 0; background: #000; }
  .view img, .view canvas.fill { position: absolute; inset: 0; width: 100%; height: 100%; display: block; object-fit: cover; }
  canvas.hud { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  /* Behind the picture, not over it. It was painting on top of a working
     feed because it comes later in the markup - "No chase camera yet"
     printed across a chase camera that was plainly working. */
  .view .nosignal {
    position: absolute; inset: 0; z-index: 0;
    display: flex; align-items: center; justify-content: center;
    text-align: center; color: #8ea0b6; font-size: 13px; padding: 24px;
  }
  .view img { z-index: 1; }
  .hud-toggle {
    position: absolute; left: 10px; bottom: 8px; display: inline-flex; align-items: center;
    gap: 6px; font-size: 11px; color: #ffffff; background: rgba(0,0,0,0.55);
    padding: 4px 8px; border-radius: 6px; z-index: 3;
  }
  .fp-legend {
    position: absolute; left: 10px; bottom: 8px; display: flex; gap: 14px; flex-wrap: wrap;
    font-size: 11px; color: #d6e0ea; background: rgba(0,0,0,0.55);
    padding: 4px 9px; border-radius: 6px; z-index: 3;
  }
  .fp-legend b { color: #fff; font-weight: 600; }
  /* The classic page's stylesheet is still loaded for its canvas code, and
     it pins #flightpath to a fixed 420px height. An id selector beats a
     class one, so the map drew 420px tall inside a 900px hero and the rest
     of the screen went black - which is exactly what "map view not fully
     visible" looked like. Ancestor + id outranks it without !important. */
  .view canvas#flightpath, #hero canvas#flightpath, .tile canvas#flightpath {
    width: 100%; height: 100%; border-radius: 0; background: #0d1219;
  }

  /* a tile is small: its own captions would cover the picture, and the
     attitude overlay is drawn for a full-size view - at tile size its pitch
     ladder and readout boxes are unreadable and spill over the picture. */
  .tile .hud-toggle, .tile .fp-legend, .tile canvas.hud { display: none; }

  /* ---------- rails ---------- */
  .rail { position: absolute; z-index: 30; display: flex; flex-direction: column; gap: 6px; overflow-y: auto; }
  .rail { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.35) transparent; }
  .rail::-webkit-scrollbar { width: 8px; }
  .rail::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.35); border-radius: 4px; }
  .rail::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.55); }
  /* Each section collapses, because the right rail holds more controls than
     fit on a laptop screen and an instructor only uses a few per lesson. */
  .rail .head {
    width: 100%; display: flex; align-items: center; justify-content: space-between;
    gap: 6px; background: none; border: 0; padding: 4px 2px; margin-top: 2px;
    font-size: 10px; font-weight: 600; color: var(--dim); cursor: pointer;
    letter-spacing: 1px; text-transform: uppercase; text-align: left;
  }
  .rail .head:hover { color: var(--ink); }
  .rail .head .chev { transition: transform 120ms; font-size: 9px; }
  .rail .group.shut .chev { transform: rotate(-90deg); }
  .rail .group.shut .items { display: none; }
  .rail .items { display: flex; flex-direction: column; gap: 6px; }
  .rail .head.danger { color: #ffd0a8; }
  .rail hr { border: 0; border-top: 1px solid rgba(255,255,255,0.18); margin: 3px 0; width: 100%; }
  /* Labels are written for a wide panel ("RETURN TO LAUNCH", "HOVER FLIGHT
     (MC)") and the rail is 120px. Centre them, let them wrap to two tidy
     lines, and leave the status dot out of the centring so a lit control
     does not sit off-axis from an unlit one. */
  .rail button {
    width: 100%; min-height: 34px; border: 0; border-radius: 8px; cursor: pointer;
    font-size: 11.5px; font-weight: 500; color: var(--ink); padding: 5px 8px;
    line-height: 1.2; display: flex; align-items: center; justify-content: center;
    gap: 6px; text-align: center; position: relative;
  }
  .rail button .dot { position: absolute; left: 7px; top: 50%; margin-top: -4px; }
  .rail button.has-dot { padding-left: 20px; }
  .rail button.normal { background: var(--btn); }
  .rail button.highlight { background: #b5730f; color: #1a1205; font-weight: 600; }
  .rail button.arm { background: rgba(31,138,76,0.95); font-weight: 600; justify-content: center; }
  .rail button.disarm { background: rgba(176,58,58,0.95); font-weight: 600; justify-content: center; }
  .rail button.warning { background: rgba(123,26,45,0.95); color: #ffc3cd; }
  .rail button.warning.on { background: var(--bad); color: #fff; font-weight: 600; }
  .rail button.danger {
    min-height: 44px; border: 2px solid #ff6b6b; color: #ffd6d6; font-weight: 700;
    background: repeating-linear-gradient(45deg, #5a1414 0 9px, #46100f 9px 18px);
    justify-content: center; text-align: center;
  }
  .rail button.experimental { background: #3a2a52; color: #e2d4ff; }
  .rail .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: rgba(255,255,255,0.28); }
  .rail .dot.on { background: #ffffff; box-shadow: 0 0 7px rgba(255,255,255,0.95); }
  .rail .field { display: flex; flex-direction: column; gap: 2px; font-size: 10px; color: var(--dim); width: 100%; }
  .rail .field input, .rail .field select {
    width: 100%; background: #0d1219; color: var(--ink); border: 1px solid #2b3442;
    border-radius: 6px; padding: 5px 7px; font-family: inherit; font-size: 12px;
  }
  .rail .stack { display: flex; flex-direction: column; gap: 4px; width: 100%; }

  /* ---------- tiles ---------- */
  .tile { position: absolute; z-index: 35; border-radius: 9px; box-shadow: 0 5px 18px rgba(0,0,0,0.55); }
  .tile .body {
    position: absolute; inset: 0; border: 2px solid rgba(255,255,255,0.4);
    border-radius: 9px; overflow: hidden; cursor: pointer; background: #000;
  }
  .tile .bar {
    position: absolute; left: 0; right: 0; top: 0; height: 24px; padding: 0 9px; z-index: 4;
    display: flex; align-items: center; justify-content: space-between;
    background: rgba(0,0,0,0.68); border-radius: 7px 7px 0 0; cursor: grab;
    font-size: 12px; font-weight: 500;
  }
  .tile .grip {
    position: absolute; right: 0; bottom: 0; width: 20px; height: 20px; z-index: 4;
    cursor: nwse-resize; border-radius: 0 0 7px 0;
    background: linear-gradient(135deg, transparent 48%, rgba(255,255,255,0.85) 48% 56%,
                transparent 56%, transparent 68%, rgba(255,255,255,0.85) 68% 76%, transparent 76%);
  }
  #dragmask { position: absolute; inset: 0; z-index: 60; display: none; }

  /* ---------- bottom band ---------- */
  #bottom { position: absolute; left: 0; right: 0; bottom: 0; height: 104px; z-index: 30; display: flex; flex-direction: column; }
  #params { height: 62px; display: flex; align-items: center; padding: 0 16px; }
  #params .group { flex: 1 1 0; display: flex; justify-content: space-evenly; align-items: center; }
  #params .gyrogap { width: 144px; flex: none; }
  #params .p { text-align: center; }
  #params .p .k { font-size: 10px; color: var(--dim); }
  #params .p .v { font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 500; }
  #cap {
    height: 42px; display: flex; align-items: center; gap: 24px; padding: 0 16px;
    border-top: 1px solid rgba(255,255,255,0.12); font-size: 12px; color: var(--dim);
  }
  #cap .lim { display: flex; align-items: center; gap: 8px; }
  #cap .track { width: 110px; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.2); position: relative; }
  #cap .track i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; background: var(--good); }
  #cap .val { font-family: 'IBM Plex Mono', monospace; color: var(--ink); }
  #cap .pill { display: flex; align-items: center; gap: 8px; border-radius: 999px; padding: 5px 13px; background: rgba(22,40,30,0.95); }
  #cap .pill b { width: 8px; height: 8px; border-radius: 50%; background: var(--good); }
  #cap .pill span { font-size: 12px; font-weight: 600; color: #8fe3a9; }

  /* the gyro sits across the band's top edge: half in the view, half in
     the band. Drawn last in the markup so neither clips it. */
  #gyro {
    position: absolute; left: 50%; bottom: 42px; transform: translateX(-50%);
    width: 124px; height: 124px; border-radius: 50%; z-index: 50;
    box-shadow: 0 0 0 3px rgba(255,255,255,0.75), 0 6px 20px rgba(0,0,0,0.6);
    background: #10151d;
  }
</style>
</head>
<body>

<div id="topbar">
  <div class="badge">Instructor</div>
  <div id="t-mode">-</div>
  <div style="flex-grow: 1; display: flex; justify-content: center; gap: 20px; align-items: center">
    <div class="seg" id="viewtabs">
      <button data-view="chase">Chase</button>
      <button data-view="nose">Nose</button>
      <button data-view="map">Map</button>
    </div>
    <div style="display: flex; align-items: center; gap: 7px">
      <span style="font-size: 11px; color: var(--dim)">Layout</span>
      <div class="seg" id="layouttabs">
        <button data-layout="pilot">Pilot</button>
        <button data-layout="station">Station</button>
      </div>
    </div>
    <button id="resettiles" style="height: 26px; padding: 0 12px; border: 0; border-radius: 6px; cursor: pointer; font-size: 12px; background: rgba(0,0,0,0.5); color: #fff">Reset tiles</button>
  </div>
  <div class="icons">
    <span class="item" id="t-armcheck-wrap" title="Whether PX4 will accept ARM or TAKEOFF right now">
      <span id="t-armcheck" style="font-weight: 600">-</span>
    </span>
    <span class="item" id="t-armed-wrap"><span id="t-armed" style="font-weight: 600">-</span></span>
    <span class="item" title="GPS satellites">
      <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M5 15 L13 7"></path>
        <rect x="2.5" y="12.5" width="5" height="5" rx="1" transform="rotate(-45 5 15)"></rect>
        <rect x="10.5" y="4.5" width="5" height="5" rx="1" transform="rotate(-45 13 7)"></rect>
        <path d="M14 16a4 4 0 0 0-4-4"></path>
        <path d="M18 18a8 8 0 0 0-8-8"></path>
      </svg>
      <span class="mono" id="t-gps">-</span>
    </span>
    <span class="item" title="Battery remaining">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <rect x="2" y="8" width="17" height="9" rx="2"></rect>
        <path d="M21.5 11.5v2"></path>
        <rect id="batt-fill" x="4" y="10" width="13" height="5" rx="1" fill="#57cc7f" stroke="none"></rect>
      </svg>
      <span class="mono" id="t-batt">-</span>
    </span>
    <span class="item" title="Telemetry age and camera frame rate">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="2" y="7" width="13" height="11" rx="2"></rect>
        <path d="M15 11.5 L21.5 8v9L15 13.5z"></path>
      </svg>
      <span class="mono v" id="t-health">-</span>
    </span>
  </div>
</div>

<div id="status">Console ready.</div>
<div id="limit-banner" class="limit-banner"></div>

<div id="hero"></div>

<!-- the three views, created once and moved between the hero and the tiles -->
<div id="viewstore" style="display: none">
  <div class="view" id="view-chase" data-name="Chase">
    <img src="/chase_feed" alt="Chase camera" onerror="this.style.display='none'">
    <div class="nosignal">No chase camera yet. Add it with tools/chase_camera_apply.py, then restart the simulator.</div>
  </div>
  <div class="view" id="view-nose" data-name="Nose">
    <img src="/video_feed" alt="Nose camera" onerror="this.style.display='none'">
    <canvas id="hud" class="hud"></canvas>
    <div class="nosignal">No nose camera signal yet.</div>
    <label class="hud-toggle"><input type="checkbox" id="hud-on" checked> Attitude overlay</label>
  </div>
  <div class="view" id="view-map" data-name="Map">
    <canvas id="flightpath" class="fill"></canvas>
    <div class="fp-legend">
      <span><b id="fp-range">-</b> across</span>
      <span><b id="fp-dist">-</b> from home</span>
      <span><b id="fp-alt">-</b> altitude</span>
      <span><b id="fp-points">0</b> points</span>
    </div>
  </div>
</div>

<div class="rail" id="rail-left">__LEFT_RAIL__</div>
<div class="rail" id="rail-right">__RIGHT_RAIL__</div>

<div class="tile" id="tile-left">
  <div class="body"></div>
  <div class="bar"><span class="name">-</span><span style="color:#9fb0c4; letter-spacing:2px">&#8285;&#8285;</span></div>
  <div class="grip"></div>
</div>
<div class="tile" id="tile-right">
  <div class="body"></div>
  <div class="bar"><span class="name">-</span><span style="color:#9fb0c4; letter-spacing:2px">&#8285;&#8285;</span></div>
  <div class="grip"></div>
</div>

<div id="dragmask"></div>

<div id="bottom">
  <div id="params">
    <div class="group">
      <div class="p"><div class="k">Ground speed</div><div class="v" id="p-gs">-</div></div>
      <div class="p"><div class="k">Vertical speed</div><div class="v" id="p-vs">-</div></div>
      <div class="p"><div class="k">Altitude AGL</div><div class="v" id="p-alt">-</div></div>
    </div>
    <div class="gyrogap"></div>
    <div class="group">
      <div class="p"><div class="k">Airspeed</div><div class="v" id="p-as">-</div></div>
      <div class="p"><div class="k">Distance home</div><div class="v" id="p-dist">-</div></div>
      <div class="p"><div class="k">Flight time</div><div class="v" id="p-time">-</div></div>
      <div class="p"><div class="k">Link age</div><div class="v" id="p-link">-</div></div>
    </div>
  </div>
  <div id="cap">
    <span style="font-weight: 600; color: var(--ink)">CAP722B</span>
    <span class="lim">Range <span class="track"><i id="bar-range"></i></span><span class="val" id="val-range">-</span></span>
    <span class="lim">Ceiling <span class="track"><i id="bar-ceil"></i></span><span class="val" id="val-ceil">-</span></span>
    <span class="lim">Speed <span class="track"><i id="bar-spd"></i></span><span class="val" id="val-spd">-</span></span>
    <span style="flex-grow: 1"></span>
    <span class="pill" id="cap-pill"><b></b><span>Within limits</span></span>
  </div>
</div>

<canvas id="gyro" width="124" height="124"></canvas>

__EXTRA_STYLE__
__CONSOLE_SCRIPT__
__EXTRA_SCRIPT__
</body>
</html>
"""


SCRIPT = """
<script>
(function () {
  var SAVED = __SAVED__;
  var BAND = 104, TOPBAR = 44;
  var MIN_W = 150, MIN_H = 96, MAX_W = 520, MAX_H = 300;

  var state = {
    hero: SAVED.hero || 'chase',
    layout: SAVED.layout || 'pilot',
    tiles: SAVED.tiles || {},
    shut: SAVED.shut || []
  };

  var el = function (id) { return document.getElementById(id); };
  var hero = el('hero'), store = el('viewstore'), mask = el('dragmask');
  var tiles = { left: el('tile-left'), right: el('tile-right') };
  var views = { chase: el('view-chase'), nose: el('view-nose'), map: el('view-map') };

  // ---------- messages ----------
  function say(text, alert) {
    var s = el('status');
    s.innerText = text;
    s.className = alert ? 'alert' : '';
  }

  // ---------- layout geometry ----------
  // Pilot floats the rails over the picture; Station insets the picture so
  // nothing ever covers it. Everything else is identical, which is the whole
  // reason these are one console and not two.
  function applyLayout() {
    var pilot = state.layout === 'pilot';
    var left = el('rail-left'), right = el('rail-right');
    var railW = pilot ? 118 : 148;

    document.documentElement.style.setProperty('--btn', pilot ? 'rgba(0,0,0,0.58)' : '#1e2430');
    el('topbar').style.background = pilot ? 'rgba(0,0,0,0.62)' : 'var(--panel)';
    el('bottom').style.background = pilot ? 'rgba(0,0,0,0.72)' : 'var(--panel)';

    [left, right].forEach(function (rail) {
      rail.style.width = railW + 'px';
      rail.style.top = (pilot ? TOPBAR + 10 : TOPBAR) + 'px';
      rail.style.bottom = (pilot ? BAND + 10 : BAND) + 'px';
      rail.style.padding = pilot ? '8px' : '10px';
      rail.style.borderRadius = pilot ? '10px' : '0';
      rail.style.background = pilot ? 'rgba(0,0,0,0.52)' : 'var(--panel)';
    });
    left.style.left = pilot ? '10px' : '0';
    right.style.right = pilot ? '10px' : '0';

    hero.style.top = (pilot ? 0 : TOPBAR) + 'px';
    hero.style.bottom = BAND + 'px';
    hero.style.left = (pilot ? 0 : railW) + 'px';
    hero.style.right = (pilot ? 0 : railW) + 'px';
    // Switching layout resizes the hero, so the canvases need refitting for
    // the same reason a swap does.
    if (window.gcsRedraw) { window.gcsRedraw(); }

    el('layouttabs').querySelectorAll('button').forEach(function (b) {
      b.className = (b.dataset.layout === state.layout) ? 'on' : '';
    });
    placeTiles();
  }

  function home(side) {
    var pilot = state.layout === 'pilot';
    var w = 212, h = 120;
    var edge = pilot ? 128 : 160;
    return {
      x: side === 'left' ? edge : window.innerWidth - edge - w,
      y: window.innerHeight - BAND - 14 - h,
      w: w, h: h
    };
  }

  function frame(side) {
    var f = state.tiles[side];
    return (f && f.w) ? f : home(side);
  }

  function placeTiles() {
    ['left', 'right'].forEach(function (side) {
      var f = frame(side), t = tiles[side];
      t.style.left = f.x + 'px';
      t.style.top = f.y + 'px';
      t.style.width = f.w + 'px';
      t.style.height = f.h + 'px';
    });
  }

  // ---------- which view is where ----------
  // Two corners, three views: each corner shows whichever of its pair is not
  // currently the hero, so no view is ever unreachable.
  function applyHero() {
    var h = state.hero;
    var leftName = (h === 'map') ? 'chase' : 'map';
    var rightName = (h === 'nose') ? 'chase' : 'nose';
    if (leftName === rightName) { rightName = (h === 'chase') ? 'nose' : 'chase'; }

    hero.appendChild(views[h]);
    tiles.left.querySelector('.body').appendChild(views[leftName]);
    tiles.right.querySelector('.body').appendChild(views[rightName]);
    tiles.left.querySelector('.name').innerText = views[leftName].dataset.name;
    tiles.right.querySelector('.name').innerText = views[rightName].dataset.name;
    tiles.left.dataset.view = leftName;
    tiles.right.dataset.view = rightName;

    el('viewtabs').querySelectorAll('button').forEach(function (b) {
      b.className = (b.dataset.view === h) ? 'on' : '';
    });

    // A canvas keeps the size it was last fitted to, and the map is only
    // refitted once a second - so without this a swap showed a tile-sized
    // map stretched across the hero until the next tick.
    if (window.gcsRedraw) { window.gcsRedraw(); }
  }

  function setHero(name) {
    if (!views[name] || state.hero === name) { return; }
    state.hero = name;
    applyHero();
    save();
    say('Main screen: ' + views[name].dataset.name.toLowerCase() + '.');
  }

  // ---------- saving ----------
  var saveTimer = null;
  function save() {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(function () {
      fetch('/console_layout', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(state)
      }).catch(function () {});
    }, 400);
  }

  // ---------- drag and resize ----------
  var drag = null;
  function startDrag(side, mode, event) {
    event.preventDefault();
    var f = frame(side);
    drag = { side: side, mode: mode, x: event.clientX, y: event.clientY,
             ox: f.x, oy: f.y, ow: f.w, oh: f.h };
    mask.style.display = 'block';
    mask.style.cursor = (mode === 'resize') ? 'nwse-resize' : 'grabbing';
  }
  mask.addEventListener('mousemove', function (event) {
    if (!drag) { return; }
    var dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    var maxX = window.innerWidth, maxY = window.innerHeight - BAND;
    var f;
    if (drag.mode === 'resize') {
      f = { x: drag.ox, y: drag.oy,
            w: Math.max(MIN_W, Math.min(MAX_W, Math.min(drag.ow + dx, maxX - 4 - drag.ox))),
            h: Math.max(MIN_H, Math.min(MAX_H, Math.min(drag.oh + dy, maxY - 4 - drag.oy))) };
    } else {
      f = { x: Math.max(4, Math.min(maxX - drag.ow - 4, drag.ox + dx)),
            y: Math.max(TOPBAR + 4, Math.min(maxY - drag.oh - 4, drag.oy + dy)),
            w: drag.ow, h: drag.oh };
    }
    state.tiles[drag.side] = f;
    placeTiles();
    if (window.gcsRedraw) { window.gcsRedraw(); }
  });
  function endDrag() {
    if (!drag) { return; }
    drag = null;
    mask.style.display = 'none';
    save();
  }
  mask.addEventListener('mouseup', endDrag);
  mask.addEventListener('mouseleave', endDrag);

  ['left', 'right'].forEach(function (side) {
    var t = tiles[side];
    t.querySelector('.bar').addEventListener('mousedown', function (e) { startDrag(side, 'move', e); });
    t.querySelector('.grip').addEventListener('mousedown', function (e) { startDrag(side, 'resize', e); });
    t.querySelector('.body').addEventListener('click', function () { setHero(t.dataset.view); });
  });

  // ---------- collapsible rail sections ----------
  function applySections() {
    document.querySelectorAll('.rail .group').forEach(function (g) {
      g.classList.toggle('shut', state.shut.indexOf(g.dataset.section) !== -1);
    });
  }
  document.querySelectorAll('.rail').forEach(function (rail) {
    rail.addEventListener('click', function (e) {
      var head = e.target.closest('.head');
      if (!head) { return; }
      var id = head.parentNode.dataset.section;
      var at = state.shut.indexOf(id);
      if (at === -1) { state.shut.push(id); } else { state.shut.splice(at, 1); }
      applySections();
      save();
    });
  });

  // ---------- controls ----------
  el('viewtabs').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (b) { setHero(b.dataset.view); }
  });
  el('layouttabs').addEventListener('click', function (e) {
    var b = e.target.closest('button');
    if (!b) { return; }
    state.layout = b.dataset.layout;
    applyLayout();
    save();
    say('Layout: ' + (state.layout === 'pilot' ? 'Pilot' : 'Station') + '.');
  });
  el('resettiles').addEventListener('click', function () {
    state.tiles = {};
    placeTiles();
    save();
    say('Tiles back to their default size and corners.');
  });
  window.addEventListener('resize', function () { applyLayout(); });

  // ---------- plugin buttons ----------
  window.send = function (id) {
    say('Sending...');
    var params = new URLSearchParams();
    document.querySelectorAll('.param-input[data-plugin="' + id + '"]').forEach(function (e) {
      params.append(e.dataset.param, e.value);
    });
    var qs = params.toString();
    fetch('/action/' + id + (qs ? '?' + qs : '')).then(function (r) { return r.text(); })
      .then(function (t) {
        // PX4 refusals and armed failures are the ones worth colouring.
        var bad = /refus|denied|not sent|not confirmed|failed|cannot|ON\\.$/i.test(t);
        say(t, bad);
        refreshFailures();
      }).catch(function () { say('The station did not answer.', true); });
  };

  function refreshFailures() {
    fetch('/failure_status').then(function (r) { return r.json(); }).then(function (d) {
      for (var id in d) {
        var dot = el('dot-' + id);
        if (dot) { dot.className = 'dot' + (d[id] ? ' on' : ''); }
        var btn = el('btn-' + id);
        if (btn && btn.classList.contains('warning')) {
          btn.classList.toggle('on', !!d[id]);
        }
      }
    }).catch(function () {});
  }

  // ---------- telemetry ----------
  var started = null;
  function fmtTime(s) {
    var m = Math.floor(s / 60), r = Math.floor(s % 60);
    return (m < 10 ? '0' : '') + m + ':' + (r < 10 ? '0' : '') + r;
  }
  var telem = {};
  function refreshTelemetry() {
    fetch('/telemetry').then(function (r) { return r.json(); }).then(function (d) {
      telem = d;
      el('t-mode').innerText = d.mode;
      var armed = el('t-armed');
      armed.innerText = d.armed ? 'ARMED' : 'Disarmed';
      armed.style.color = d.armed ? '#ff8a8a' : '#8fe3a9';

      var chk = el('t-armcheck');
      var why = d.arm_blocker ? d.arm_blocker.replace(/^Preflight( Fail)?: */i, '') : '';
      chk.innerText = why ? (d.arm_state + ' - ' + why.slice(0, 44)) : d.arm_state;
      el('t-armcheck-wrap').title = d.arm_blocker
        ? ('PX4 says: ' + d.arm_blocker) : 'PX4 reports no blocking preflight check.';
      chk.style.color = (d.arm_ready === null) ? '#ffc94d'
        : (d.arm_ready ? '#8fe3a9' : '#ff8a8a');

      el('t-gps').innerText = (d.satellites !== null) ? d.satellites : '-';
      el('t-batt').innerText = (d.battery_pct !== null) ? (d.battery_pct + '%') : '-';
      var fill = el('batt-fill');
      if (d.battery_pct !== null) {
        fill.setAttribute('width', Math.max(1, 13 * d.battery_pct / 100));
        fill.setAttribute('fill', d.battery_pct < 20 ? '#e03b3b' : '#57cc7f');
      }

      el('p-gs').innerText = d.groundspeed_ms.toFixed(1) + ' m/s';
      el('p-as').innerText = d.airspeed_ms.toFixed(1) + ' m/s';
      el('p-alt').innerText = d.altitude_m.toFixed(1) + ' m';
      el('p-dist').innerText = d.range_from_home_m.toFixed(0) + ' m';

      if (d.armed && started === null) { started = Date.now(); }
      if (!d.armed) { started = null; }
      el('p-time').innerText = started ? fmtTime((Date.now() - started) / 1000) : '--:--';
    }).catch(function () {});
  }

  // Vertical speed is not in the telemetry feed, so derive it from the
  // altitude we do get rather than print a field that is always zero.
  var lastAlt = null, lastAltT = null;
  setInterval(function () {
    if (telem.altitude_m === undefined) { return; }
    var now = Date.now();
    if (lastAlt !== null && now > lastAltT) {
      var vs = (telem.altitude_m - lastAlt) / ((now - lastAltT) / 1000);
      el('p-vs').innerText = (Math.abs(vs) < 0.05 ? 0 : vs).toFixed(1) + ' m/s';
    }
    lastAlt = telem.altitude_m; lastAltT = now;
  }, 500);

  function refreshLink() {
    fetch('/health').then(function (r) { return r.json(); }).then(function (d) {
      var age = d.telemetry_age_s;
      el('p-link').innerText = (age === null) ? '--' : (age < 1 ? '<1 s' : age.toFixed(0) + ' s');
      el('p-link').style.color = (age !== null && age > 2) ? '#ff8a8a' : '#8fe3a9';
    }).catch(function () {});
  }

  // ---------- CAP722B strip ----------
  function refreshCap() {
    fetch('/limit_status').then(function (r) { return r.json(); }).then(function (d) {
      var pill = el('cap-pill');
      var level = d.level || 'ok';
      pill.querySelector('b').style.background =
        level === 'breach' ? '#e03b3b' : (level === 'warn' ? '#ffc94d' : '#57cc7f');
      pill.querySelector('span').innerText =
        level === 'breach' ? 'Limit exceeded' : (level === 'warn' ? 'Approaching limit' : 'Within limits');
      pill.querySelector('span').style.color =
        level === 'breach' ? '#ffd6d6' : (level === 'warn' ? '#ffe9b0' : '#8fe3a9');
      pill.style.background =
        level === 'breach' ? 'rgba(120,26,26,0.95)' : (level === 'warn' ? 'rgba(90,70,12,0.95)' : 'rgba(22,40,30,0.95)');
    }).catch(function () {});

    var lim = __LIMITS__;
    function bar(barId, valId, value, max, unit) {
      var pct = Math.max(0, Math.min(100, (value / max) * 100));
      var b = el(barId);
      b.style.width = pct + '%';
      b.style.background = pct >= 100 ? '#e03b3b' : (pct >= 90 ? '#ffc94d' : '#57cc7f');
      el(valId).innerText = value.toFixed(value < 10 ? 1 : 0) + '/' + max + ' ' + unit;
    }
    if (telem.range_from_home_m !== undefined) {
      bar('bar-range', 'val-range', telem.range_from_home_m, lim.range_m, 'm');
      bar('bar-ceil', 'val-ceil', telem.altitude_m, lim.ceiling_m, 'm');
      bar('bar-spd', 'val-spd', telem.groundspeed_ms, lim.groundspeed_ms, 'm/s');
    }
  }

  // ---------- the gyro ----------
  var gy = el('gyro'), gctx = gy.getContext('2d');
  function drawGyro() {
    var S = 124, c = S / 2;
    gctx.clearRect(0, 0, S, S);
    gctx.save();
    gctx.beginPath(); gctx.arc(c, c, c - 1, 0, 7); gctx.clip();

    var roll = telem.roll_deg || 0, pitch = telem.pitch_deg || 0;
    var pxPerDeg = 1.5;
    gctx.save();
    gctx.translate(c, c);
    gctx.rotate(-roll * Math.PI / 180);
    gctx.translate(0, pitch * pxPerDeg);
    gctx.fillStyle = '#4f9ad8'; gctx.fillRect(-S, -S, S * 2, S);
    gctx.fillStyle = '#8d6a3f'; gctx.fillRect(-S, 0, S * 2, S);
    gctx.strokeStyle = '#ffffff'; gctx.lineWidth = 2;
    gctx.beginPath(); gctx.moveTo(-S, 0); gctx.lineTo(S, 0); gctx.stroke();
    gctx.lineWidth = 1; gctx.strokeStyle = 'rgba(255,255,255,0.8)';
    [-20, -10, 10, 20].forEach(function (d) {
      var y = -d * pxPerDeg, half = (d % 20 === 0) ? 22 : 12;
      gctx.beginPath(); gctx.moveTo(-half, y); gctx.lineTo(half, y); gctx.stroke();
    });
    gctx.restore();

    // heading needle, red half to north
    var hdg = (telem.heading_deg || 0) * Math.PI / 180;
    gctx.save();
    gctx.translate(c, c); gctx.rotate(hdg);
    gctx.strokeStyle = '#ff4d4d'; gctx.lineWidth = 3; gctx.lineCap = 'round';
    gctx.beginPath(); gctx.moveTo(0, 0); gctx.lineTo(0, -46); gctx.stroke();
    gctx.strokeStyle = 'rgba(255,255,255,0.92)';
    gctx.beginPath(); gctx.moveTo(0, 0); gctx.lineTo(0, 46); gctx.stroke();
    gctx.restore();

    // fixed aircraft reference
    gctx.strokeStyle = '#ffc94d'; gctx.lineWidth = 4; gctx.lineCap = 'round';
    gctx.beginPath();
    gctx.moveTo(c - 30, c); gctx.lineTo(c - 8, c);
    gctx.moveTo(c + 8, c); gctx.lineTo(c + 30, c);
    gctx.stroke();
    gctx.fillStyle = '#ffc94d';
    gctx.beginPath(); gctx.arc(c, c, 3.5, 0, 7); gctx.fill();

    // roll pointer at the top
    gctx.fillStyle = '#ffc94d';
    gctx.beginPath();
    gctx.moveTo(c, 6); gctx.lineTo(c - 6, 15); gctx.lineTo(c + 6, 15);
    gctx.closePath(); gctx.fill();
    gctx.restore();

    // heading, in the half that sits on the black band
    gctx.fillStyle = '#ffffff';
    gctx.font = '600 15px "IBM Plex Mono", monospace';
    gctx.textAlign = 'center';
    gctx.shadowColor = 'rgba(0,0,0,0.85)'; gctx.shadowBlur = 4;
    gctx.fillText(String(Math.round(telem.heading_deg || 0)).padStart(3, '0') + '\\u00b0', c, S - 10);
    gctx.shadowBlur = 0;
  }

  // ---------- go ----------
  applyLayout();
  applyHero();
  applySections();
  refreshTelemetry(); refreshFailures(); refreshLink(); refreshCap();
  setInterval(refreshTelemetry, 500);
  setInterval(refreshFailures, 1000);
  setInterval(refreshLink, 1000);
  setInterval(refreshCap, 1000);
  setInterval(drawGyro, 100);
})();
</script>
"""
