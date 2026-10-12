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
  /* One text size across the whole bar. It had five - 11, 12, 13, 14 and
     whatever the icons inherited - and the eye reads that as five levels
     of importance when they are all just labels. */
  #topbar {
    position: absolute; left: 0; right: 0; top: 0; height: 52px; z-index: 40;
    display: flex; align-items: center; gap: 10px; padding: 0 12px;
    font-size: 14px;
    /* One line, always. With the window buttons added it started wrapping
       at 1600px and the aircraft's own state - the right-hand end - was
       the part that fell off, which is the last thing that should. */
    flex-wrap: nowrap; overflow: hidden; white-space: nowrap;
  }
  #topbar, #topbar button, #topbar label, #topbar span { font-size: 14px; }
  #topbar .badge {
    background: rgba(255,255,255,0.14); border-radius: 6px;
    padding: 5px 13px; font-weight: 500;
  }
  #t-mode { font-weight: 500; }
  .seg { display: flex; gap: 3px; background: rgba(0,0,0,0.5); border-radius: 9px; padding: 3px; flex: none; }
  .seg button {
    height: 30px; padding: 0 15px; border: 0; border-radius: 7px; cursor: pointer;
    font-weight: 500; background: transparent; color: var(--ink);
  }
  .seg button.on { background: #ffffff; color: #10151d; font-weight: 600; }
  /* The aircraft's state never shrinks and never wraps; the controls to
     its left give up their space first. */
  .icons { display: flex; align-items: center; gap: 16px; flex: none; }
  #topbar .tools { display: flex; align-items: center; gap: 8px; min-width: 0; }
  #topbar .topbtn, #topbar .topswitch { flex: none; }
  .icons span.item { display: flex; align-items: center; gap: 7px; }
  /* The icons were drawn at whatever size their glyph happened to be, so a
     satellite dish and a battery sat at different weights beside the same
     number. One size, set here, for all of them. */
  .icons svg { width: 20px; height: 20px; display: block; flex: none; }
  .icons .num { font-variant-numeric: tabular-nums; }
  #t-health.stale { color: #ff8a8a; }

  /* ---------- message strip ---------- */
  /* Moved off the attitude display. At the top centre it printed straight
     across the roll arc - the part of the gauge an instructor is reading
     while the message is still fading. The left is empty except for the
     bank/pitch line, so it goes there. */
  #status {
    position: absolute; left: 16px; top: 92px; z-index: 45;
    max-width: 540px; display: flex; align-items: center; gap: 9px;
    padding: 7px 15px; border-radius: 8px; background: rgba(0,0,0,0.78);
    box-shadow: 0 3px 12px rgba(0,0,0,0.45); font-size: 13px; font-weight: 500;
    transition: opacity 500ms;
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
  /* z-index 2 is the whole reason the overlay is visible: the camera image
     below is z-index 1, and a canvas with no z-index of its own painted
     underneath it - the overlay was drawn every frame and never seen. */
  canvas.hud { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 2; }
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
  /* Top left, not bottom left: the bottom corners of the main screen are
     where the two small views sit, and the legend was printing underneath
     the chase tile. 52px clears the top bar, which the main screen runs
     behind rather than below. */
  .fp-legend {
    position: absolute; left: 10px; top: 52px; display: flex; gap: 14px; flex-wrap: wrap;
    font-size: 11px; color: #d6e0ea; background: rgba(0,0,0,0.55);
    padding: 4px 9px; border-radius: 6px; z-index: 3;
  }
  .fp-legend b { color: #fff; font-weight: 600; }
  .fp-legend .mapzoom { display: flex; align-items: center; gap: 6px; }
  .fp-legend .mapzoom button {
    min-height: 0; padding: 1px 7px; border: 1px solid rgba(255,255,255,0.3);
    border-radius: 5px; background: rgba(255,255,255,0.14); color: #fff;
    font-size: 12px; line-height: 16px; cursor: pointer;
  }
  .fp-legend .mapzoom button:hover { background: rgba(255,255,255,0.28); }
  .fp-legend #fp-zoom { min-width: 30px; text-align: center; }
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
  /* The gauge and alarm switches live in the top bar. They govern every
     view, so they cannot belong to one of them, and anywhere over the
     picture puts them under a corner tile where they cannot be clicked. */
  .topswitch {
    display: inline-flex; align-items: center; gap: 5px; height: 26px;
    padding: 0 10px; border-radius: 6px; background: rgba(0,0,0,0.5);
    font-size: 12px; color: var(--ink); cursor: pointer;
  }

  /* ---------- rails ---------- */
  /* A rail is a panel, not furniture: it can be dragged off its edge,
     resized, and turned on its side into a horizontal bar. Docked is just
     the frame it has before anyone moves it. */
  .rail { position: absolute; z-index: 30; display: flex; flex-direction: column; overflow: hidden; }
  .rail .railbody { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 6px; overflow: auto; }
  .rail.floating { border-radius: 10px; box-shadow: 0 6px 22px rgba(0,0,0,0.55); }
  /* The handle is on screen whether the panel is docked or floating. It was
     only drawn once floating, so the one gesture that got a docked panel
     moving - grabbing its top 10 pixels - had nothing to show for it, and
     the rails read as fixed furniture. */
  .railbar {
    display: flex; align-items: center; justify-content: space-between; gap: 6px;
    height: 24px; flex: none; padding: 0 5px; margin-bottom: 4px;
    background: rgba(255,255,255,0.1); border: 1px solid rgba(255,255,255,0.16);
    border-radius: 7px; cursor: grab;
    font-size: 11px; font-weight: 600; color: var(--ink);
  }
  .railbar:hover { background: rgba(255,255,255,0.19); }
  .railbar:active { cursor: grabbing; }
  .railbar .name { display: flex; align-items: center; gap: 5px; overflow: hidden; }
  /* two columns of dots: the convention for "drag me" */
  .railbar .dots {
    width: 9px; height: 13px; flex: none; opacity: 0.75;
    background-image: radial-gradient(circle, var(--ink) 1px, transparent 1.2px);
    background-size: 4px 4px; background-position: 0 1px;
  }
  .railbar .turn {
    width: 20px; height: 18px; min-height: 0; padding: 0; border: 0; border-radius: 4px;
    background: rgba(255,255,255,0.14); color: var(--ink); cursor: pointer;
    font-size: 11px; display: flex; align-items: center; justify-content: center;
  }
  .rail .railgrip {
    position: absolute; right: 0; bottom: 0; width: 18px; height: 18px; display: block;
    cursor: nwse-resize; border-radius: 0 0 9px 0; z-index: 2;
    background: linear-gradient(135deg, transparent 50%, rgba(255,255,255,0.8) 50% 58%,
                transparent 58%, transparent 70%, rgba(255,255,255,0.8) 70% 78%, transparent 78%);
  }

  /* Turned on its side: sections run left to right, each with its buttons
     in a row, and the whole bar scrolls sideways instead of down. */
  .rail.horizontal .railbody { flex-direction: row; overflow-x: auto; overflow-y: hidden; align-items: flex-start; }
  .rail.horizontal .items { flex-direction: row; flex-wrap: nowrap; }
  .rail.horizontal button { width: auto; min-width: 86px; white-space: nowrap; }
  .rail.horizontal .stack { min-width: 104px; }
  .rail.horizontal hr { display: none; }
  /* The scrollbar used to float over the right-hand edge of whatever was
     under it, which on a number box is exactly where its up/down arrows
     are - "Distance (m)" could not be nudged while the pointer was near
     the scrollbar. scrollbar-gutter reserves the space instead of
     borrowing it. */
  .rail .railbody { scrollbar-gutter: stable; padding-right: 2px; }
  .rail { scrollbar-width: thin; scrollbar-color: rgba(255,255,255,0.35) transparent; }
  .rail::-webkit-scrollbar { width: 10px; }
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

  /* ---------- pre-flight checklist ---------- */
  #preflight {
    position: absolute; left: 50%; top: 60px; transform: translateX(-50%);
    width: 470px; max-height: calc(100% - 190px); overflow: auto; z-index: 55;
    display: none; flex-direction: column; border-radius: 12px;
    background: rgba(12,16,22,0.97); border: 1px solid rgba(255,255,255,0.22);
    box-shadow: 0 14px 44px rgba(0,0,0,0.75);
  }
  #preflight.open { display: flex; }
  #preflight .pf-head {
    display: flex; align-items: center; gap: 10px; padding: 11px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.14); font-size: 14px;
  }
  #preflight .pf-head b { flex: 1; }
  #preflight .pf-state { font-size: 12px; font-weight: 600; }
  #preflight .pf-state.ready { color: var(--good); }
  #preflight .pf-state.notready { color: #ffc400; }
  #preflight .pf-head button {
    min-height: 0; width: 26px; height: 24px; padding: 0; border: 0;
    border-radius: 6px; background: rgba(255,255,255,0.14); color: #fff;
    cursor: pointer; font-size: 16px; line-height: 1;
  }
  #preflight .pf-item {
    display: flex; align-items: flex-start; gap: 10px; padding: 9px 14px;
    border-bottom: 1px solid rgba(255,255,255,0.07); font-size: 13px;
  }
  #preflight .pf-item .mark {
    width: 18px; height: 18px; flex: none; margin-top: 1px; border-radius: 5px;
    display: flex; align-items: center; justify-content: center;
    font-size: 12px; font-weight: 700;
  }
  #preflight .pf-item.ok .mark { background: rgba(31,138,76,0.95); color: #fff; }
  #preflight .pf-item.bad .mark { background: rgba(176,58,58,0.95); color: #fff; }
  #preflight .pf-item.unknown .mark { background: rgba(255,255,255,0.18); color: var(--dim); }
  #preflight .pf-item .text { flex: 1; }
  #preflight .pf-item .detail { display: block; font-size: 11px; color: var(--dim); }
  /* An automatic item cannot be ticked by hand - that is the point of it. */
  #preflight .pf-item.auto { cursor: default; }
  #preflight .pf-item.manual { cursor: pointer; }
  #preflight .pf-item.manual:hover { background: rgba(255,255,255,0.06); }
  #preflight .pf-item .who {
    font-size: 10px; color: var(--dim); text-transform: uppercase;
    letter-spacing: 1px; flex: none; margin-top: 3px;
  }
  #preflight .pf-foot {
    display: flex; align-items: center; gap: 12px; padding: 12px 14px;
  }
  #preflight .pf-foot button {
    min-height: 0; padding: 7px 14px; border: 0; border-radius: 7px;
    background: #b5730f; color: #1a1205; font-weight: 600; cursor: pointer;
    font-size: 13px;
  }
  #preflight .pf-note { font-size: 11px; color: var(--dim); }

  /* ---------- top bar buttons ---------- */
  .topbtn {
    height: 30px; padding: 0 13px; border: 0; border-radius: 7px;
    cursor: pointer; background: rgba(0,0,0,0.5); color: #fff; font-weight: 500;
  }
  .topbtn.danger { background: rgba(123,26,45,0.95); color: #ffc3cd; }
  .topsel {
    height: 30px; padding: 0 8px; border: 1px solid rgba(255,255,255,0.18);
    border-radius: 7px; background: rgba(0,0,0,0.5); color: #fff; cursor: pointer;
  }
  /* A standing reminder, for as long as a rendered view is on: nothing in
     the simulation knows anything about temperature. */
  #irnote {
    position: absolute; left: 50%; transform: translateX(-50%); bottom: 112px;
    z-index: 46; display: none; padding: 4px 12px; border-radius: 6px;
    background: rgba(90,60,0,0.9); color: #ffe6a8; font-size: 12px;
  }
  #irnote.on { display: block; }

  /* ---------- windows ---------- */
  /* A window, not another column entry: these are things an instructor
     stops to do - a ground check, or setting up a failure - rather than
     things reached for while watching a student fly. */
  .window {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%, -50%);
    z-index: 58; display: none; flex-direction: column;
    max-width: 820px; max-height: calc(100% - 180px); overflow: auto;
    border-radius: 12px; background: rgba(12,16,22,0.98);
    border: 1px solid rgba(255,255,255,0.22);
    box-shadow: 0 18px 54px rgba(0,0,0,0.8);
  }
  .window.open { display: flex; }
  /* Failure injection sits in the one part of the screen with nothing on
     it: inboard of the right-hand column, below the aircraft's state
     readouts in the gauge's top corner, above the corner view. Everything
     an instructor reads while a student flies - the tapes, the heading,
     the attitude indicator, the parameter band - stays uncovered. */
  .window.topright {
    left: auto; right: 158px; top: 178px; transform: none;
    min-width: 0; width: 204px;
  }
  .window.topright .win-controls { min-width: 0; }
  .window.topright .win-controls button {
    min-height: 30px; padding: 5px 10px; font-size: 12px;
  }
  .window.topright .win-note { font-size: 11px; line-height: 1.35; }
  .window.topright .win-body { padding: 10px 12px 12px; }
  .window.topright .win-head { padding: 9px 12px; font-size: 13px; }
  .win-head {
    display: flex; align-items: center; gap: 10px; padding: 12px 15px;
    border-bottom: 1px solid rgba(255,255,255,0.14); font-size: 15px;
  }
  .win-head b { flex: 1; }
  .win-close {
    min-height: 0; width: 28px; height: 26px; padding: 0; border: 0;
    border-radius: 6px; background: rgba(255,255,255,0.14); color: #fff;
    cursor: pointer; font-size: 18px; line-height: 1;
  }
  .win-note { padding: 10px 15px 0; font-size: 12px; color: var(--dim); }
  .win-body { display: flex; gap: 20px; padding: 14px 15px 16px; align-items: flex-start; justify-content: center; }
  .win-body:has(.airframe) .win-controls { display: none; }
  .win-controls { display: flex; flex-direction: column; gap: 8px; min-width: 210px; flex: 1; }
  .win-control { display: flex; flex-direction: column; gap: 3px; }
  .win-controls button {
    min-height: 34px; padding: 7px 12px; border: 0; border-radius: 8px;
    background: var(--btn); color: var(--ink); cursor: pointer; font-size: 13px;
    display: flex; align-items: center; gap: 9px; text-align: left;
  }
  .win-controls button.warning { background: rgba(123,26,45,0.95); color: #ffc3cd; }
  .win-controls button.warning.on { background: var(--bad); color: #fff; font-weight: 600; }
  .win-controls .dot { width: 9px; height: 9px; border-radius: 50%; flex: none; background: rgba(255,255,255,0.28); }
  .win-controls .dot.on { background: #ffffff; box-shadow: 0 0 7px rgba(255,255,255,0.95); }
  .win-controls .field { display: flex; align-items: center; gap: 8px; font-size: 11px; color: var(--dim); }
  .win-controls .field input, .win-controls .field select {
    flex: 1; background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.18);
    border-radius: 6px; color: var(--ink); padding: 4px 7px; font-size: 12px;
  }
  /* the aircraft, seen from above */
  /* The window is sized by the aircraft, not the other way round: with
     the button list gone there is nothing else in it to fill the space. */
  #win-motors { width: 372px; }
  #win-motors .win-body { padding: 6px 10px 12px; }
  .airframe { width: 352px; height: 344px; flex: none; margin: 0 auto; }
  .airframe .body { fill: #39404d; }
  .airframe .wing { fill: #2c323d; }
  .airframe .disc { fill: rgba(90,160,220,0.18); stroke: rgba(255,255,255,0.45); stroke-width: 1.5; }
  .airframe .arrow { fill: none; stroke: #ffc94d; stroke-width: 2.6; stroke-linecap: round; }
  .airframe .arrowhead { fill: #ffc94d; }
  .airframe .num { fill: #fff; font: 700 15px 'IBM Plex Mono', monospace; text-anchor: middle; }
  .airframe .spin { fill: #9fb0c4; font: 600 9px 'IBM Plex Sans', sans-serif; text-anchor: middle; letter-spacing: 1px; }
  .airframe .role { fill: #7f8c9e; font: 600 9px 'IBM Plex Sans', sans-serif; text-anchor: middle; letter-spacing: 1px; }
  .airframe .nose { fill: #7f8c9e; font: 600 10px 'IBM Plex Sans', sans-serif; text-anchor: middle; letter-spacing: 2px; }
  /* the rotor under the pointer, and the one being tested, light up */
  .airframe .rotor { cursor: pointer; }
  .airframe .rotor:hover .disc, .airframe .rotor.lit .disc {
    fill: rgba(255,201,77,0.33); stroke: #ffc94d;
  }

  /* ---------- bottom band ---------- */
  #bottom { position: absolute; left: 0; right: 0; bottom: 0; height: 104px; z-index: 30; display: flex; flex-direction: column; }
  #params { height: 62px; display: flex; align-items: center; padding: 0 16px; }
  #params .group { flex: 1 1 0; display: flex; justify-content: space-evenly; align-items: center; }
  #params .gyrogap { width: 212px; flex: none; }
  #params .p { text-align: center; }
  #params .p .k { font-size: 10px; color: var(--dim); }
  #params .p .v { font-family: 'IBM Plex Mono', monospace; font-size: 20px; font-weight: 500; }
  /* The limit row is tightened so it ends before the gyro's lower half,
     which now reaches 12px from the bottom - at the old widths the
     instrument sat on top of the speed figure. */
  #cap {
    height: 42px; display: flex; align-items: center; gap: 14px; padding: 0 16px;
    border-top: 1px solid rgba(255,255,255,0.12); font-size: 12px; color: var(--dim);
  }
  #cap .lim { display: flex; align-items: center; gap: 8px; }
  #cap .track { width: 72px; height: 6px; border-radius: 3px; background: rgba(255,255,255,0.2); position: relative; }
  #cap .track i { position: absolute; left: 0; top: 0; bottom: 0; border-radius: 3px; background: var(--good); }
  #cap .val { font-family: 'IBM Plex Mono', monospace; color: var(--ink); }
  #cap .pill { display: flex; align-items: center; gap: 8px; border-radius: 999px; padding: 5px 13px; background: rgba(22,40,30,0.95); }
  #cap .pill b { width: 8px; height: 8px; border-radius: 50%; background: var(--good); }
  #cap .pill span { font-size: 12px; font-weight: 600; color: #8fe3a9; }

  /* the gyro sits across the band's top edge: half in the view, half in
     the band. Drawn last in the markup so neither clips it. */
  /* 184px across, centred on the band's top edge: bottom 12 + half of 184
     puts the horizon exactly on the 104px band. The bezel, the glass and
     the drop shadow are all drawn on the canvas, so the element itself
     carries no background - a CSS ring would sit outside the painted rim. */
  #gyro {
    position: absolute; left: 50%; bottom: 12px; transform: translateX(-50%);
    width: 184px; height: 184px; border-radius: 50%; z-index: 50;
    box-shadow: 0 8px 26px rgba(0,0,0,0.75);
    background: transparent;
  }
</style>
</head>
<body>

<div id="topbar">
  <div class="badge">Instructor</div>
  <div id="t-mode">-</div>
  <div class="tools" style="flex: 1 1 auto; justify-content: center; gap: 14px">
    <div class="seg" id="viewtabs">
      <button data-view="chase">Chase</button>
      <button data-view="nose">Nose</button>
      <button data-view="map">Map</button>
    </div>
    <div style="display: flex; align-items: center; gap: 7px">
      <div class="seg" id="layouttabs" title="Pilot floats the controls over the picture; Station insets it so nothing covers it">
        <button data-layout="pilot">Pilot</button>
        <button data-layout="station">Station</button>
      </div>
    </div>
    <button class="topbtn" id="resettiles" title="Put every panel back to its default place and size">Reset</button>
    <label class="topswitch" title="The flight display drawn over the camera views"><input type="checkbox" id="hud-on" checked> Gauge</label>
    <label class="topswitch" title="The low-altitude warning tone"><input type="checkbox" id="alarm-on" checked> Alarm</label>
    <label class="topswitch" title="Call out each command and each change of state"><input type="checkbox" id="voice-on"> Voice</label>
    <button class="topbtn" id="pf-open">Checklist</button>
    <button class="topbtn" data-open-win="motors">Motors</button>
    <button class="topbtn danger" data-open-win="failures">Failures</button>
    <select id="viewmode" class="topsel" title="How the camera pictures are rendered. The infrared views are renderings of the colour camera, not a thermal sensor.">
      <option value="normal">Daylight</option>
      <option value="night_vision">Night vision</option>
      <option value="white_hot">IR white hot</option>
      <option value="black_hot">IR black hot</option>
    </select>
  </div>
  <div class="icons">
    <span class="item" id="t-armcheck-wrap" title="Whether PX4 will accept ARM or TAKEOFF right now">
      <span id="t-armcheck" style="font-weight: 600">-</span>
    </span>
    <span class="item" id="t-armed-wrap"><span id="t-armed" style="font-weight: 600">-</span></span>
    <span class="item" title="GPS satellites">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <path d="M5 15 L13 7"></path>
        <rect x="2.5" y="12.5" width="5" height="5" rx="1" transform="rotate(-45 5 15)"></rect>
        <rect x="10.5" y="4.5" width="5" height="5" rx="1" transform="rotate(-45 13 7)"></rect>
        <path d="M14 16a4 4 0 0 0-4-4"></path>
        <path d="M18 18a8 8 0 0 0-8-8"></path>
      </svg>
      <span class="mono num" id="t-gps">-</span>
    </span>
    <span class="item" title="Battery remaining">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" aria-hidden="true">
        <rect x="2" y="8" width="17" height="9" rx="2"></rect>
        <path d="M21.5 11.5v2"></path>
        <rect id="batt-fill" x="4" y="10" width="13" height="5" rx="1" fill="#57cc7f" stroke="none"></rect>
      </svg>
      <span class="mono num" id="t-batt">-</span>
    </span>
    <span class="item" title="Telemetry age and camera frame rate">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
        <rect x="2" y="7" width="13" height="11" rx="2"></rect>
        <path d="M15 11.5 L21.5 8v9L15 13.5z"></path>
      </svg>
      <span class="mono num v" id="t-health">-</span>
    </span>
  </div>
</div>

<div id="status">Console ready.</div>
<div id="irnote">Simulated infrared - a rendering of the colour camera, not a thermal sensor.</div>
<div id="limit-banner" class="limit-banner"></div>

<div id="hero"></div>

<!-- the three views, created once and moved between the hero and the tiles -->
<div id="viewstore" style="display: none">
  <div class="view" id="view-chase" data-name="Chase">
    <img src="/chase_feed" alt="Chase camera" onerror="this.style.display='none'">
    <canvas class="hud"></canvas>
    <div class="nosignal">No chase camera yet. Add it with tools/chase_camera_apply.py, then restart the simulator.</div>
  </div>
  <div class="view" id="view-nose" data-name="Nose">
    <img src="/video_feed" alt="Nose camera" onerror="this.style.display='none'">
    <canvas id="hud" class="hud"></canvas>
    <div class="nosignal">No nose camera signal yet.</div>
  </div>
  <div class="view" id="view-map" data-name="Map">
    <canvas id="flightpath" class="fill"></canvas>
    <div class="fp-legend">
      <span><b id="fp-range">-</b> across</span>
      <span><b id="fp-dist">-</b> from home</span>
      <span><b id="fp-alt">-</b> altitude</span>
      <span><b id="fp-points">0</b> points</span>
      <span>map: <b id="fp-backdrop">-</b></span>
      <span class="mapzoom">
        <button data-mapzoom="out" title="Zoom out">&minus;</button>
        <b id="fp-zoom">1x</b>
        <button data-mapzoom="in" title="Zoom in">+</button>
        <button data-mapzoom="fit" title="Back to the fitted view">Fit</button>
      </span>
    </div>
  </div>
</div>

<div class="rail" id="rail-left">
  <div class="railbar" title="Drag to move this panel; its corner resizes it">
    <span class="name"><i class="dots"></i>Flight</span>
    <button class="turn" title="Turn this panel on its side" aria-label="Turn this panel on its side">&#8646;</button>
  </div>
  <div class="railbody">__LEFT_RAIL__</div>
  <div class="railgrip"></div>
</div>
<div class="rail" id="rail-right">
  <div class="railbar" title="Drag to move this panel; its corner resizes it">
    <span class="name"><i class="dots"></i>Instructor</span>
    <button class="turn" title="Turn this panel on its side" aria-label="Turn this panel on its side">&#8646;</button>
  </div>
  <div class="railbody">__RIGHT_RAIL__</div>
  <div class="railgrip"></div>
</div>

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

<!-- The pre-flight checklist. A panel rather than a rail section: it is
     worked down once before an exercise and then put away, which is a
     different gesture from pressing a control. -->
<div id="preflight">
  <div class="pf-head">
    <b>Pre-flight checklist</b>
    <span id="pf-state" class="pf-state">-</span>
    <button id="pf-close" title="Put it away">&times;</button>
  </div>
  <div id="pf-items"></div>
  <div class="pf-foot">
    <button id="pf-complete">Start the exercise</button>
    <span class="pf-note">Recorded as it stands, green or not.</span>
  </div>
</div>

<!-- Function test and Failure injection, as windows rather than as more
     entries in a column. Rendered by the station from the same plugins. -->
__WINDOWS__

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

<canvas id="gyro" width="184" height="184"></canvas>

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
  var BAND = 104, TOPBAR = 52;
  var MIN_W = 150, MIN_H = 96, MAX_W = 520, MAX_H = 300;

  var state = {
    hero: SAVED.hero || 'chase',
    layout: SAVED.layout || 'pilot',
    tiles: SAVED.tiles || {},
    // A side appears here only once it has been dragged off its edge; until
    // then the rail is docked and the layout switch owns its geometry.
    rails: SAVED.rails || {},
    shut: SAVED.shut || []
  };

  var el = function (id) { return document.getElementById(id); };
  var hero = el('hero'), store = el('viewstore'), mask = el('dragmask');
  var tiles = { left: el('tile-left'), right: el('tile-right') };
  var views = { chase: el('view-chase'), nose: el('view-nose'), map: el('view-map') };

  // ---------- messages ----------
  // The last reply from the station. An ordinary one fades after a few
  // seconds - it was staying on screen for the rest of the flight. An
  // alert does not fade, because an alert is a thing that went wrong and
  // the instructor may be looking at the aircraft when it appears.
  var sayTimer = null;
  function say(text, alert) {
    var s = el('status');
    s.innerText = text;
    s.className = alert ? 'alert' : '';
    s.style.opacity = '1';
    if (sayTimer) { clearTimeout(sayTimer); sayTimer = null; }
    if (!alert) {
      sayTimer = setTimeout(function () { s.style.opacity = '0'; }, 6000);
    }
  }

  // ---------- layout geometry ----------
  // Pilot floats the rails over the picture; Station insets the picture so
  // nothing ever covers it. Everything else is identical, which is the whole
  // reason these are one console and not two.
  function applyLayout() {
    var pilot = state.layout === 'pilot';
    // Wider since the scrollbar got a gutter of its own: at the old width
    // the labels started wrapping to three lines.
    var railW = pilot ? 132 : 162;

    document.documentElement.style.setProperty('--btn', pilot ? 'rgba(0,0,0,0.58)' : '#1e2430');
    el('topbar').style.background = pilot ? 'rgba(0,0,0,0.62)' : 'var(--panel)';
    el('bottom').style.background = pilot ? 'rgba(0,0,0,0.72)' : 'var(--panel)';

    ['left', 'right'].forEach(function (side) {
      var rail = el('rail-' + side), f = state.rails[side];
      var floating = !!(f && f.w);
      rail.classList.toggle('floating', floating);
      rail.classList.toggle('horizontal', !!(f && f.horizontal));
      rail.style.padding = pilot || floating ? '8px' : '10px';
      rail.style.background = (pilot || floating) ? 'rgba(0,0,0,0.62)' : 'var(--panel)';
      if (floating) {
        rail.style.left = f.x + 'px';
        rail.style.top = f.y + 'px';
        rail.style.right = 'auto';
        rail.style.bottom = 'auto';
        rail.style.width = f.w + 'px';
        rail.style.height = f.h + 'px';
        rail.style.borderRadius = '10px';
      } else {
        rail.style.width = railW + 'px';
        rail.style.height = 'auto';
        rail.style.top = (pilot ? TOPBAR + 10 : TOPBAR) + 'px';
        rail.style.bottom = (pilot ? BAND + 10 : BAND) + 'px';
        rail.style.left = side === 'left' ? (pilot ? '10px' : '0') : 'auto';
        rail.style.right = side === 'right' ? (pilot ? '10px' : '0') : 'auto';
        rail.style.borderRadius = pilot ? '10px' : '0';
      }
    });

    // The picture is only inset for a rail that is still docked. A rail the
    // instructor has dragged out floats over it, like everything else they
    // have moved - insetting for a panel that is no longer at the edge
    // would leave a bar of dead space where it used to be.
    function inset(side) {
      var f = state.rails[side];
      return (pilot || (f && f.w)) ? 0 : railW;
    }
    hero.style.top = (pilot ? 0 : TOPBAR) + 'px';
    hero.style.bottom = BAND + 'px';
    hero.style.left = inset('left') + 'px';
    hero.style.right = inset('right') + 'px';
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
    // 400x250, the size the instructor settled on by dragging them there.
    // The old 212x120 was small enough that the map and the chase camera
    // had to be swapped into the main screen to be read at all, which
    // defeats the point of having them in the corner. Shrunk on a narrow
    // screen so the two never meet in the middle.
    var w = Math.min(400, Math.max(212, (window.innerWidth - 420) / 2));
    var h = Math.round(w * 0.625);
    var edge = pilot ? 142 : 172;
    return {
      x: side === 'left' ? edge : window.innerWidth - edge - w,
      y: window.innerHeight - BAND - 14 - h,
      w: w, h: h
    };
  }

  // Where a rail sits the moment it is first dragged off its edge: exactly
  // where it already was, so it does not jump out from under the pointer.
  function railHome(side) {
    var box = el('rail-' + side).getBoundingClientRect();
    return { x: Math.round(box.left), y: Math.round(box.top),
             w: Math.round(box.width), h: Math.round(box.height),
             horizontal: false };
  }

  // Lift a panel off its edge, keeping the shape it already had. A no-op
  // once it is floating, so grabbing the handle a second time just moves it.
  function undock(side) {
    if (state.rails[side] && state.rails[side].w) { return; }
    state.rails[side] = railHome(side);
    applyLayout();
  }

  var LIMITS_FOR = {
    tile: { minW: MIN_W, maxW: MAX_W, minH: MIN_H, maxH: MAX_H },
    rail: { minW: 96, maxW: 760, minH: 90, maxH: 2000 }
  };

  function frameOf(kind, side) {
    if (kind === 'rail') {
      var r = state.rails[side];
      return (r && r.w) ? r : railHome(side);
    }
    var f = state.tiles[side];
    return (f && f.w) ? f : home(side);
  }

  function frame(side) { return frameOf('tile', side); }

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
  function startDrag(kind, side, mode, event) {
    event.preventDefault();
    var f = frameOf(kind, side);
    drag = { kind: kind, side: side, mode: mode, x: event.clientX, y: event.clientY,
             ox: f.x, oy: f.y, ow: f.w, oh: f.h, horizontal: !!f.horizontal };
    mask.style.display = 'block';
    mask.style.cursor = (mode === 'resize') ? 'nwse-resize' : 'grabbing';
  }
  mask.addEventListener('mousemove', function (event) {
    if (!drag) { return; }
    var dx = event.clientX - drag.x, dy = event.clientY - drag.y;
    var lim = LIMITS_FOR[drag.kind];
    var maxX = window.innerWidth, maxY = window.innerHeight - BAND;
    var f;
    if (drag.mode === 'resize') {
      f = { x: drag.ox, y: drag.oy,
            w: Math.max(lim.minW, Math.min(lim.maxW, Math.min(drag.ow + dx, maxX - 4 - drag.ox))),
            h: Math.max(lim.minH, Math.min(lim.maxH, Math.min(drag.oh + dy, maxY - 4 - drag.oy))) };
    } else {
      f = { x: Math.max(4, Math.min(maxX - drag.ow - 4, drag.ox + dx)),
            y: Math.max(TOPBAR + 4, Math.min(maxY - drag.oh - 4, drag.oy + dy)),
            w: drag.ow, h: drag.oh };
    }
    f.horizontal = drag.horizontal;
    if (drag.kind === 'rail') {
      state.rails[drag.side] = f;
      applyLayout();
    } else {
      state.tiles[drag.side] = f;
      placeTiles();
    }
    if (window.gcsRedraw) { window.gcsRedraw(); }
  });
  function endDrag() {
    // The mask comes down whether or not a drag was running. Releasing the
    // button outside the window used to leave it up, and with it covering
    // everything at z-index 60 the whole console stopped taking clicks.
    mask.style.display = 'none';
    if (!drag) { return; }
    drag = null;
    save();
  }
  mask.addEventListener('mouseup', endDrag);
  window.addEventListener('mouseup', endDrag);
  window.addEventListener('blur', endDrag);

  ['left', 'right'].forEach(function (side) {
    var t = tiles[side];
    t.querySelector('.bar').addEventListener('mousedown', function (e) { startDrag('tile', side, 'move', e); });
    t.querySelector('.grip').addEventListener('mousedown', function (e) { startDrag('tile', side, 'resize', e); });
    t.querySelector('.body').addEventListener('click', function () { setHero(t.dataset.view); });

    // A docked rail is dragged by its whole header strip; once floating it
    // has a bar of its own, and the grip in its corner resizes it.
    var rail = el('rail-' + side);
    rail.querySelector('.railbar').addEventListener('mousedown', function (e) {
      if (e.target.closest('.turn')) { return; }
      undock(side);
      startDrag('rail', side, 'move', e);
    });
    rail.querySelector('.railgrip').addEventListener('mousedown', function (e) {
      undock(side);
      startDrag('rail', side, 'resize', e);
    });
    rail.querySelector('.turn').addEventListener('click', function () {
      undock(side);
      var f = frameOf('rail', side);
      var turned = !f.horizontal;
      // Swap the long side with the short one, so turning a tall column
      // gives a wide bar rather than a square nobody wanted.
      state.rails[side] = { x: f.x, y: f.y, w: f.h, h: f.w, horizontal: turned };
      applyLayout();
      save();
      say((side === 'left' ? 'Flight' : 'Instructor') + ' panel is now '
          + (turned ? 'a horizontal bar.' : 'a column.'));
    });
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
    state.rails = {};
    applyLayout();
    placeTiles();
    save();
    say('Panels back to their default places.');
  });
  window.addEventListener('resize', function () { applyLayout(); });

  // ---------- plugin buttons ----------
  // What each control is called out as, when the Voice switch is on. The
  // button's own label is used for anything not listed - these are the ones
  // whose label reads badly aloud ("FORWARD FLIGHT (FW)").
  var SPOKEN_CONTROL = {
    arm: 'Arm', disarm: 'Disarm', takeoff: 'Take off', land: 'Land',
    rtl: 'Return to launch', hold: 'Hold', loiter: 'Loiter',
    climb_to: 'Changing altitude', forward_flight: 'Forward flight',
    hover_flight: 'Hover', mode_position: 'Position mode',
    mode_manual: 'Manual mode', set_home: 'Home set',
    new_session: 'New session', reset_scenario: 'Scenario reset',
    reset_spawn: 'Back to spawn', freeze: 'Freeze',
    flight_termination: 'Flight termination',
    gps_failure: 'G P S failure', data_link_loss: 'Data link failure',
    rc_signal_loss: 'R C signal failure', engine_failure: 'Engine failure',
    motor_failure: 'Motor failure'
  };

  window.send = function (id) {
    say('Sending...');
    if (window.gcsSpeak) {
      // By id, not by the onclick attribute: this file's JavaScript is a
      // plain Python string, so a backslash written here never reaches the
      // browser - the escaped quotes came out bare and broke the page.
      var button = document.getElementById('btn-' + id);
      window.gcsSpeak(SPOKEN_CONTROL[id]
                      || (button ? button.innerText.trim() : id), true);
    }
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
      window.gcsTelemetry = d;
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
  // Drawn as a real attitude indicator is: a metal bezel carrying a fixed
  // roll scale, glass showing sky over ground with a labelled pitch ladder,
  // and a fixed yellow aircraft symbol. The heading sits in a window in the
  // lower half, where an EFIS puts it, rather than on a compass needle -
  // a needle on an attitude indicator is not a thing real panels have.
  var GY = 184;
  var gy = el('gyro'), gctx = gy.getContext('2d');

  function gyroFit() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var px = Math.round(GY * dpr);
    if (gy.width !== px) { gy.width = px; gy.height = px; }
    gctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  function gyroBox(x, y, w, h, r) {
    gctx.beginPath();
    gctx.moveTo(x + r, y);
    gctx.arcTo(x + w, y, x + w, y + h, r);
    gctx.arcTo(x + w, y + h, x, y + h, r);
    gctx.arcTo(x, y + h, x, y, r);
    gctx.arcTo(x, y, x + w, y, r);
    gctx.closePath();
  }

  function drawGyro() {
    gyroFit();
    var S = GY, c = S / 2, R = c - 13;
    var roll = telem.roll_deg || 0, pitch = telem.pitch_deg || 0;
    // +-30 degrees across the glass, which is the span a real attitude
    // indicator shows. It was +-26, chosen to make the numbers fit rather
    // than to match anything.
    var pxPerDeg = R / 30;
    gctx.clearRect(0, 0, S, S);

    // --- the glass: sky over ground, rolling and pitching -------------
    gctx.save();
    gctx.beginPath(); gctx.arc(c, c, R, 0, 7); gctx.clip();

    gctx.save();
    gctx.translate(c, c);
    gctx.rotate(-roll * Math.PI / 180);
    gctx.translate(0, pitch * pxPerDeg);

    var sky = gctx.createLinearGradient(0, -S, 0, 0);
    sky.addColorStop(0, '#17436f'); sky.addColorStop(1, '#5ba6dc');
    gctx.fillStyle = sky; gctx.fillRect(-S, -S * 2, S * 2, S * 2);
    var gnd = gctx.createLinearGradient(0, 0, 0, S);
    gnd.addColorStop(0, '#5f9e28'); gnd.addColorStop(1, '#2f5513');
    gctx.fillStyle = gnd; gctx.fillRect(-S, 0, S * 2, S * 2);

    gctx.strokeStyle = '#ffffff'; gctx.lineWidth = 2.5;
    gctx.beginPath(); gctx.moveTo(-S, 0); gctx.lineTo(S, 0); gctx.stroke();

    // A real pitch ladder is read by its numbers, not by counting rungs.
    // This one had none: five identical white bars either side of the
    // horizon told the instructor the aircraft was pitched, but not how
    // far, which is the one thing it exists to say.
    gctx.font = '700 11px "IBM Plex Mono", monospace';
    gctx.textAlign = 'center'; gctx.textBaseline = 'middle';
    for (var d = -30; d <= 30; d += 5) {
      if (d === 0) { continue; }
      var y = -d * pxPerDeg, ten = (d % 10 === 0), half = ten ? 26 : 13;
      gctx.lineWidth = ten ? 2.2 : 1.5;
      gctx.strokeStyle = 'rgba(255,255,255,0.95)';
      gctx.beginPath(); gctx.moveTo(-half, y); gctx.lineTo(half, y); gctx.stroke();
      if (ten) {
        gctx.lineJoin = 'round';
        gctx.strokeStyle = 'rgba(0,0,0,0.8)'; gctx.lineWidth = 3;
        gctx.strokeText(Math.abs(d), -half - 12, y);
        gctx.strokeText(Math.abs(d), half + 12, y);
        gctx.fillStyle = '#ffffff';
        gctx.fillText(Math.abs(d), -half - 12, y);
        gctx.fillText(Math.abs(d), half + 12, y);
      }
    }
    gctx.restore();

    // curved glass: light at the top, shaded at the bottom
    var gloss = gctx.createLinearGradient(0, c - R, 0, c + R);
    gloss.addColorStop(0, 'rgba(255,255,255,0.18)');
    gloss.addColorStop(0.45, 'rgba(255,255,255,0)');
    gloss.addColorStop(1, 'rgba(0,0,0,0.32)');
    gctx.fillStyle = gloss; gctx.fillRect(c - R, c - R, R * 2, R * 2);
    gctx.restore();

    // --- the bezel, and the fixed roll scale it carries ---------------
    var bez = gctx.createLinearGradient(0, 0, 0, S);
    bez.addColorStop(0, '#5a6477'); bez.addColorStop(0.5, '#262c37'); bez.addColorStop(1, '#13171e');
    gctx.lineWidth = c - R;
    gctx.strokeStyle = bez;
    gctx.beginPath(); gctx.arc(c, c, (c + R) / 2, 0, 7); gctx.stroke();
    gctx.lineWidth = 1.5; gctx.strokeStyle = 'rgba(0,0,0,0.85)';
    gctx.beginPath(); gctx.arc(c, c, R + 0.75, 0, 7); gctx.stroke();

    // The marks a real bank scale carries: 10, 20 and 30 close in, then 45
    // and 60. 20 was being drawn the same length as 45, which is not what
    // the eye is trained on.
    gctx.strokeStyle = '#ffffff'; gctx.lineCap = 'butt';
    [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60].forEach(function (a) {
      var ar = (a - 90) * Math.PI / 180;
      var big = (a % 30 === 0), r2 = R + (c - R) * (big ? 0.92 : 0.6);
      gctx.lineWidth = big ? 2.4 : 1.6;
      gctx.beginPath();
      gctx.moveTo(c + Math.cos(ar) * R, c + Math.sin(ar) * R);
      gctx.lineTo(c + Math.cos(ar) * r2, c + Math.sin(ar) * r2);
      gctx.stroke();
    });
    gctx.fillStyle = '#ffffff';
    gctx.beginPath();
    gctx.moveTo(c, c - R); gctx.lineTo(c - 6, c - R - 9); gctx.lineTo(c + 6, c - R - 9);
    gctx.closePath(); gctx.fill();

    // the bank pointer, which rolls with the aircraft
    var pa = (-roll - 90) * Math.PI / 180;
    gctx.fillStyle = '#ffb02e';
    gctx.beginPath();
    gctx.moveTo(c + Math.cos(pa) * (R - 2), c + Math.sin(pa) * (R - 2));
    gctx.lineTo(c + Math.cos(pa - 0.08) * (R - 15), c + Math.sin(pa - 0.08) * (R - 15));
    gctx.lineTo(c + Math.cos(pa + 0.08) * (R - 15), c + Math.sin(pa + 0.08) * (R - 15));
    gctx.closePath(); gctx.fill();

    // --- the fixed aircraft symbol ------------------------------------
    function wings() {
      gctx.beginPath();
      gctx.moveTo(c - 54, c); gctx.lineTo(c - 20, c); gctx.lineTo(c - 20, c + 10);
      gctx.moveTo(c + 54, c); gctx.lineTo(c + 20, c); gctx.lineTo(c + 20, c + 10);
      gctx.stroke();
    }
    gctx.lineCap = 'round'; gctx.lineJoin = 'round';
    gctx.strokeStyle = 'rgba(0,0,0,0.8)'; gctx.lineWidth = 7.5; wings();
    gctx.strokeStyle = '#ffc94d'; gctx.lineWidth = 4; wings();
    gctx.fillStyle = 'rgba(0,0,0,0.8)';
    gctx.beginPath(); gctx.arc(c, c, 5, 0, 7); gctx.fill();
    gctx.fillStyle = '#ffc94d';
    gctx.beginPath(); gctx.arc(c, c, 3, 0, 7); gctx.fill();

    // --- bank in figures, beside the heading ---------------------------
    var bankTxt = Math.abs(roll) < 1 ? '0\u00b0'
                : Math.abs(Math.round(roll)) + '\u00b0 '
                  + (roll > 0 ? 'R' : 'L');
    gctx.font = '700 12px "IBM Plex Mono", monospace';
    gctx.textAlign = 'center'; gctx.textBaseline = 'middle';
    gctx.lineJoin = 'round';
    gctx.strokeStyle = 'rgba(0,0,0,0.85)'; gctx.lineWidth = 3.5;
    gctx.strokeText(bankTxt, c, c - R * 0.52);
    gctx.fillStyle = Math.abs(roll) > 45 ? '#ffb02e' : '#ffffff';
    gctx.fillText(bankTxt, c, c - R * 0.52);

    // --- heading window, in the half that sits on the black band ------
    var hw = 58, hh = 22, hx = c - hw / 2, hy = c + R * 0.40;
    gctx.fillStyle = 'rgba(6,9,13,0.92)';
    gctx.strokeStyle = 'rgba(255,255,255,0.6)'; gctx.lineWidth = 1.5;
    gyroBox(hx, hy, hw, hh, 4); gctx.fill(); gctx.stroke();
    gctx.fillStyle = '#ffffff';
    gctx.font = '600 16px "IBM Plex Mono", monospace';
    gctx.textAlign = 'center'; gctx.textBaseline = 'middle';
    gctx.fillText(String(Math.round(telem.heading_deg || 0)).padStart(3, '0') + '°',
                  c, hy + hh / 2 + 1);
    gctx.font = '600 8px -apple-system, sans-serif';
    gctx.fillStyle = 'rgba(255,255,255,0.65)';
    gctx.fillText('HDG', c, hy - 6);
  }

  // ---------- how the camera pictures are rendered ----------
  el('viewmode').addEventListener('change', function () {
    var mode = el('viewmode').value;
    fetch('/view_mode?mode=' + mode).then(function (r) { return r.json(); })
      .then(function (d) {
        el('irnote').classList.toggle('on', mode !== 'normal');
        say('Camera view: ' + el('viewmode').selectedOptions[0].text
            + (mode === 'normal' ? '.'
               : '. This is a rendering of the colour camera, not a '
                 + 'thermal sensor - it has no temperature information.'));
      }).catch(function () { say('The station did not answer.', true); });
  });

  // ---------- windows ----------
  // One open at a time, closed by its X or by Escape. Opening one closes
  // the checklist and the other, because two panels over the picture is
  // the clutter these were built to remove.
  function closeWindows() {
    document.querySelectorAll('.window').forEach(function (w) {
      w.classList.remove('open');
    });
  }
  function openWindow(id) {
    var win = el('win-' + id);
    if (!win) { return; }
    closeWindows();
    el('preflight').classList.remove('open');
    win.classList.add('open');
  }
  document.addEventListener('click', function (e) {
    var open = e.target.closest ? e.target.closest('[data-open-win]') : null;
    if (open) { openWindow(open.dataset.openWin); return; }
    var close = e.target.closest ? e.target.closest('.win-close') : null;
    if (close) { closeWindows(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape') { closeWindows(); el('preflight').classList.remove('open'); }
  });

  // The aircraft diagram is the control: clicking a rotor runs that
  // rotor's test, which is the gesture a ground check actually wants -
  // point at the propeller you are watching.
  document.querySelectorAll('.airframe .rotor').forEach(function (rotor) {
    rotor.addEventListener('click', function () {
      var id = rotor.dataset.motor;
      if (!id) { return; }
      send(id);
      rotor.classList.add('lit');
      setTimeout(function () { rotor.classList.remove('lit'); }, 3200);
    });
  });
  // Hovering a button lights the propeller it belongs to, so there is no
  // guessing which one "Motor 3" is.
  document.querySelectorAll('.win-controls button[data-motor]').forEach(function (b) {
    function light(on) {
      var rotor = document.querySelector('.airframe .rotor[data-motor="' + b.dataset.motor + '"]');
      if (rotor) { rotor.classList.toggle('lit', on); }
    }
    b.addEventListener('mouseenter', function () { light(true); });
    b.addEventListener('mouseleave', function () { light(false); });
  });

  // ---------- pre-flight checklist ----------
  var pf = el('preflight');

  function drawPreflight(d) {
    var state = el('pf-state');
    state.innerText = d.ready ? 'Ready'
      : (d.outstanding.length + ' outstanding');
    state.className = 'pf-state ' + (d.ready ? 'ready' : 'notready');
    el('pf-items').innerHTML = d.items.map(function (i) {
      var cls = i.ok === true ? 'ok' : (i.ok === false ? 'bad' : 'unknown');
      var mark = i.ok === true ? '\u2713' : (i.ok === false ? '\u2715' : '?');
      return '<div class="pf-item ' + cls + ' ' + i.kind + '"'
           + (i.kind === 'manual' ? ' data-item="' + i.key + '"' : '')
           + '><span class="mark">' + mark + '</span>'
           + '<span class="text">' + i.label
           + '<span class="detail">' + i.detail + '</span></span>'
           + '<span class="who">' + (i.kind === 'auto' ? 'aircraft' : 'you')
           + '</span></div>';
    }).join('');
  }

  function refreshPreflight() {
    if (!pf.classList.contains('open')) { return; }
    fetch('/preflight').then(function (r) { return r.json(); })
      .then(drawPreflight).catch(function () {});
  }

  el('pf-open').addEventListener('click', function () {
    pf.classList.add('open');
    refreshPreflight();
  });
  el('pf-close').addEventListener('click', function () {
    pf.classList.remove('open');
  });
  el('pf-items').addEventListener('click', function (e) {
    var row = e.target.closest('.pf-item.manual');
    if (!row) { return; }
    var on = row.classList.contains('ok') ? '0' : '1';
    fetch('/preflight_tick?item=' + row.dataset.item + '&on=' + on)
      .then(function (r) { return r.json(); })
      .then(drawPreflight).catch(function () {});
  });
  el('pf-complete').addEventListener('click', function () {
    fetch('/preflight_complete').then(function (r) { return r.json(); })
      .then(function (d) {
        drawPreflight(d);
        pf.classList.remove('open');
        say(d.ready
            ? 'Checklist complete - all items green. Written to the record.'
            : 'Exercise started with ' + d.outstanding.length
              + ' item(s) not green: ' + d.outstanding.join(', ')
              + '. Written to the record.', !d.ready);
      }).catch(function () { say('The station did not answer.', true); });
  });
  setInterval(refreshPreflight, 1000);

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
