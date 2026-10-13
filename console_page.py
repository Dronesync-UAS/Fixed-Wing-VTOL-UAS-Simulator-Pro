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
  /* A laptop at 1100 is the narrowest machine this is taught on, and the
     bar grew a fourth view tab and a Log button on 12 Oct 2026. Rather
     than drop a control, everything tightens below 1300: the padding and
     the gaps go, and the Instructor badge - which says nothing that
     changes - goes with them. Measured, not guessed: the browser check
     fails the build if anything overlaps the aircraft's state at 1100. */
  @media (max-width: 1300px) {
    #topbar { gap: 9px; padding: 0 10px; }
    #topbar .badge { display: none; }
    #topbar .tools { gap: 8px !important; }
    #topbar .topbtn { padding: 0 9px; }
    #topbar .seg button { padding: 0 9px; }
    #topbar .icons { gap: 10px; }
  }
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
  /* The message panel, at the foot of the right rail. Sized to fill
     whatever is left under the last control, so it is always in the
     same place and always the same shape. */
  #status {
    /* Takes whatever is left under the last control, and gives it back
       when the screen is short: on a 1280x720 laptop the controls come
       first and the message gets two lines. It is the only thing in the
       rail allowed to shrink, which is what makes "the rails never
       scroll" a promise that can be kept. */
    flex: 1 1 auto; min-height: 40px; margin-top: 8px;
    display: flex; flex-direction: column; gap: 5px; overflow: hidden;
    padding: 8px 10px; border-radius: 9px;
    background: rgba(255,255,255,0.05);
    border-left: 4px solid rgba(255,255,255,0.3);
    transition: background 200ms, border-color 200ms, opacity 400ms;
  }
  #status .msg-head {
    font-size: 9.5px; letter-spacing: 1px; font-weight: 700; color: var(--dim);
  }
  #status .msg-text {
    flex: 1 1 auto; min-height: 0; overflow: auto;
    font-size: 11.5px; line-height: 1.35; color: var(--ink);
  }
  #status .msg-age { font-size: 9.5px; color: var(--dim); }
  /* On a short screen the heading and the age are the first things to
     go - the message itself is the point. */
  /* A 1280x720 laptop is the smallest screen this is taught on, and the
     rails have to hold everything on it without scrolling. Below 800 px
     tall the whole rail tightens: the message loses its heading, the
     buttons lose two pixels each, and the gaps close by one. Measured,
     not guessed - the browser check fails the build if either rail
     overflows at 1280x720. */
  @media (max-height: 800px) {
    #status { margin-top: 6px; padding: 5px 9px; min-height: 22px; }
    #status .msg-head, #status .msg-age { display: none; }
    .rail button { min-height: 30px; }
    .rail button.danger { min-height: 36px; }
    .rail .railbody, .rail .items { gap: 3px; }
    .rail .head { padding: 1px 2px; margin-top: 0; }
  }
  /* Three states, because "what the station just said" and "something
     is wrong" should not look the same at a glance. */
  #status.empty { opacity: 0.45; }
  #status.empty .msg-text { color: var(--dim); }
  #status.ok {
    background: rgba(26,70,44,0.5); border-left-color: #57cc7f;
  }
  #status.ok .msg-head { color: #8fe3a9; }
  #status.alert {
    background: rgba(120,26,26,0.92); border-left-color: #ff6b6b;
  }
  #status.alert .msg-head { color: #ffb3b3; }
  #status.alert .msg-text { color: #ffe0e0; }
  /* An alert pulses for a few seconds so it is caught out of the corner
     of the eye, then settles - a panel that pulses for ever stops being
     a signal. */
  #status.alert.fresh { animation: msgpulse 900ms ease-in-out 4; }
  @keyframes msgpulse {
    0%, 100% { box-shadow: 0 0 0 0 rgba(255,80,80, 0); }
    50% { box-shadow: 0 0 0 4px rgba(255,80,80, 0.45); }
  }

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
  /* NO SCROLLING, as of 12 Oct 2026. The rail used to scroll, and the
     scrollbar sat over the right-hand end of every control in it - which
     is exactly where the number boxes and the drop-downs are. A control
     a mouse cannot reach might as well not be there.
     So the rails are fixed: everything in them is on screen at once, and
     tools/test_console_browser.py fails the build if the content of
     either one is taller than the rail at 1280x720, which is the
     smallest screen this is taught on. If a new control will not fit,
     something has to move to the settings window - that is the trade,
     and it is made on purpose. */
  .rail .railbody {
    flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 4px;
    overflow: hidden;
  }
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
  /* Each section collapses, because the right rail holds more controls than
     fit on a laptop screen and an instructor only uses a few per lesson. */
  .rail .head {
    width: 100%; display: flex; align-items: center; justify-content: space-between;
    gap: 6px; background: none; border: 0; padding: 2px 2px; margin-top: 1px;
    font-size: 10px; font-weight: 600; color: var(--dim); cursor: pointer;
    letter-spacing: 1px; text-transform: uppercase; text-align: left;
  }
  .rail .head:hover { color: var(--ink); }
  .rail .head .chev { transition: transform 120ms; font-size: 9px; }
  .rail .group.shut .chev { transform: rotate(-90deg); }
  .rail .group.shut .items { display: none; }
  .rail .items { display: flex; flex-direction: column; gap: 4px; }
  .rail .head.danger { color: #ffd0a8; }
  .rail hr { border: 0; border-top: 1px solid rgba(255,255,255,0.18); margin: 3px 0; width: 100%; }
  /* Labels are written for a wide panel ("RETURN TO LAUNCH", "HOVER FLIGHT
     (MC)") and the rail is 120px. Centre them, let them wrap to two tidy
     lines, and leave the status dot out of the centring so a lit control
     does not sit off-axis from an unlit one. */
  .rail button {
    width: 100%; min-height: 32px; border: 0; border-radius: 8px; cursor: pointer;
    font-size: 11.5px; font-weight: 500; color: var(--ink); padding: 4px 8px;
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
    min-height: 40px; border: 2px solid #ff6b6b; color: #ffd6d6; font-weight: 700;
    background: repeating-linear-gradient(45deg, #5a1414 0 9px, #46100f 9px 18px);
    justify-content: center; text-align: center;
  }
  .rail button.experimental { background: #3a2a52; color: #e2d4ff; }
  .rail .dot { width: 8px; height: 8px; border-radius: 50%; flex: none; background: rgba(255,255,255,0.28); }
  .rail .dot.on { background: #ffffff; box-shadow: 0 0 7px rgba(255,255,255,0.95); }
  /* Label beside the box, not above it. A rail that does not scroll is
     a rail where every line counts, and six numbers on their own lines
     was 70 px of label. A drop-down keeps the full width - its options
     are words, not two digits - which is what .wide is for. */
  .rail .field {
    display: flex; flex-direction: row; align-items: center; gap: 5px;
    font-size: 9px; color: var(--dim); width: 100%;
  }
  .rail .field > span { flex: 0 0 46px; text-align: right; line-height: 1.05; }
  .rail .field > input, .rail .field > select { flex: 1 1 auto; min-width: 0; }
  /* The box and its arrows are one unit. The NATIVE spinners are off:
     they sat inside the box and clipped the third digit, so "100" came
     out as "10C". These are drawn beside it instead, so they cannot
     overlap the value, and they are twice the size - which matters on
     a touchscreen and matters more when the alternative is typing. */
  .rail .field > .num { flex: 1 1 auto; min-width: 0; display: flex; gap: 2px; }
  .rail .field .num > input { flex: 1 1 auto; min-width: 0; text-align: center; }
  .rail .field input[type=number] {
    -moz-appearance: textfield; appearance: textfield;
  }
  .rail .field input[type=number]::-webkit-outer-spin-button,
  .rail .field input[type=number]::-webkit-inner-spin-button {
    -webkit-appearance: none; margin: 0;
  }
  .rail .field .step {
    flex: 0 0 18px; display: flex; flex-direction: column; gap: 1px;
  }
  .rail .field .step button {
    flex: 1 1 0; min-height: 0; height: auto; width: 18px; padding: 0;
    border: 1px solid #2b3442; border-radius: 4px; background: #141b24;
    color: var(--ink); font-size: 7px; line-height: 1; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  .rail .field .step button:hover { background: #22303f; }
  .rail .field .step button:active { background: #324558; }
  .rail .field.wide { flex-direction: column; align-items: stretch; gap: 1px; }
  .rail .field.wide > span { flex: none; text-align: left; }
  .rail .field input, .rail .field select {
    width: 100%; background: #0d1219; color: var(--ink); border: 1px solid #2b3442;
    border-radius: 6px; padding: 3px 6px; font-family: inherit; font-size: 11.5px;
  }
  /* A control with numbers to set is one block, not three loose rows -
     it reads as "these belong to that button", which is what a GCS
     looks like and what the loose version did not. */
  .rail .stack {
    display: flex; flex-direction: column; gap: 3px; padding: 3px 5px 4px;
    border-radius: 9px; background: rgba(255,255,255,0.045);
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
    position: absolute; left: 50%; top: 60px;
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
  .topbtn.icon { padding: 0 9px; display: flex; align-items: center; }
  .topbtn.icon svg { width: 20px; height: 20px; display: block; }
  /* The close button reads red only on hover. Permanently red next to the
     settings gear it would pull the eye away from the failure controls,
     which are the ones that matter in a lesson. */
  .topbtn.icon.close:hover { background: #c2384a; color: #fff; }

  /* ---------- "do you want to exit?" ---------- */
  .askback {
    position: fixed; inset: 0; z-index: 200; display: none;
    align-items: center; justify-content: center;
    background: rgba(6,9,14,0.62); backdrop-filter: blur(2px);
  }
  .askback.open { display: flex; }
  .askcard {
    width: 340px; max-width: calc(100vw - 32px); padding: 20px 22px 18px;
    border-radius: 14px; background: #141a24;
    border: 1px solid rgba(255,255,255,0.14);
    box-shadow: 0 30px 80px rgba(0,0,0,0.75); text-align: center;
  }
  .asktitle { font-size: 17px; font-weight: 600; color: #fff; }
  .asknote { margin-top: 8px; font-size: 12px; color: #93a1b8; line-height: 1.45; }
  .askrow { margin-top: 18px; display: flex; gap: 10px; justify-content: center; }
  .askrow button {
    min-width: 92px; height: 36px; border-radius: 9px; cursor: pointer;
    font-size: 13px; font-weight: 600; border: 1px solid rgba(255,255,255,0.16);
  }
  /* No is the wider, lit one: the safe answer should be the easy answer. */
  .askno { background: rgba(255,255,255,0.14); color: #fff; }
  .askno:hover { background: rgba(255,255,255,0.22); }
  .askyes { background: #c2384a; color: #fff; border-color: #c2384a; }
  .askyes:hover { background: #d84054; }
  .askcard.going .askrow { display: none; }
  /* ---------- the payload and chase control strips ---------- */
  /* Across the bottom of the picture, which is where DJI puts a payload's
     controls and therefore where a remote pilot's hand already goes. */
  /* Only on the main screen. In a corner tile the strip is unreadable,
     and - the reason this rule exists - it sat over the bottom of the
     picture and swallowed clicks meant for the strip of whichever view
     WAS the hero.

     AT THE TOP, not the bottom, which is where the first draft put it.
     The bottom of this screen is full: the attitude instrument is
     centred on the band, and the two corner views sit either side of it.
     A strip across the bottom therefore had to overlap one of the three,
     and being underneath the corner view in the stacking order, it
     swallowed its own clicks. The top of the picture is empty. */
  .paybar { display: none; }
  #hero > .view > .paybar {
    position: absolute; left: 50%; transform: translateX(-50%); top: 12px;
    z-index: 47; display: flex; align-items: center; gap: 8px;
    padding: 7px 12px; border-radius: 10px;
    background: rgba(12,16,22,0.78); backdrop-filter: blur(7px);
    border: 1px solid rgba(255,255,255,0.1);
    font-size: 12px; max-width: calc(100% - 40px); flex-wrap: wrap;
    justify-content: center;
  }
  .paybar button {
    height: 28px; padding: 0 11px; border: 0; border-radius: 7px; cursor: pointer;
    background: rgba(255,255,255,0.1); color: #fff; font-weight: 600;
    font-size: 12px;
  }
  .paybar button:hover { background: rgba(255,255,255,0.19); }
  .paybar button.on { background: #b5730f; color: #1a1205; }
  .paybar button.rec { background: #8c2230; color: #ffd8de; }
  .paybar .payread {
    font-family: 'IBM Plex Mono', monospace; color: var(--dim);
    white-space: nowrap;
  }
  .paybar .paygroup { display: flex; align-items: center; gap: 6px; }
  .paybar .paygroup b {
    font-family: 'IBM Plex Mono', monospace; min-width: 44px; text-align: center;
  }
  .paybar .topsel { height: 28px; font-size: 12px; }
  /* The chase strip is secondary to the payload one, so it is quieter -
     and pushed left, clear of the heading tape the flight gauge draws
     across the top middle of that view. */
  /* Clear of the left rail, which floats at x=10 and is up to 162 wide
     in Station layout. At left:14 this strip printed straight over the
     rail's own heading - visible the moment it was looked at on a real
     screen rather than in a test. */
  #hero > .view > .chasebar {
    left: 176px; transform: none; opacity: 0.92;
  }
  /* DRAGGED LIKE EVERYTHING ELSE, added 13 Oct 2026. The rails, the corner
     tiles and the pop-up panels could all be moved and remembered; this
     strip was the one container nailed to the picture. Once dragged it is
     fixed to the window rather than to the view, because the view itself
     moves between the hero slot and a corner tile and a strip pinned to it
     would travel into a 400 px tile with it. */
  #hero > .view > .chasebar.floating,
  .chasebar.floating {
    position: fixed; left: auto; top: auto; transform: none; z-index: 48;
  }
  .chasebar .striphandle {
    cursor: grab; padding: 0 2px; color: #7f8da4; font-size: 13px;
    line-height: 1; letter-spacing: -1px; user-select: none;
  }
  .chasebar.dragging { box-shadow: 0 18px 48px rgba(0,0,0,0.8); }
  .chasebar.dragging .striphandle { cursor: grabbing; }
  /* In Pilot layout the picture starts at the top of the window and the
     bar floats over it, so a strip pinned to the top of the picture
     would be underneath it. */
  #hero.under-topbar > .view > .paybar { top: 64px; }
  /* The gimbal picture takes the drag, so it must not try to be dragged
     as an image by the browser. */
  .pay-hud {
    position: absolute; inset: 0; width: 100%; height: 100%;
    pointer-events: none; z-index: 2;
  }
  /* The payload view is the one that is blank until a tool has been
     run, so its "no signal" message is a short set of instructions
     rather than a sentence - the instructor should not have to come
     back and ask what to type. */
  /* Digital zoom on the camera views, added 12 Oct 2026: "make all view
     screen with a zoom in and out where by placing the mouse icon
     hovering on the screen the mouse wheel can be used to zoom in and
     out". The nose and chase cameras have no real zoom - these are fixed
     sensors on the airframe - so this scales the picture and crops it,
     the same digital zoom the payload view already labels as such. */
  #view-chase img, #view-nose img {
    transform-origin: center center;
    transition: transform 0.12s linear;
  }
  .view .zoomtag {
    position: absolute; left: 10px; bottom: 10px; z-index: 36;
    padding: 2px 8px; border-radius: 4px;
    font: 600 11px/1.4 ui-monospace, monospace; letter-spacing: 0.04em;
    color: #cfe0f5; background: rgba(10,16,24,0.78);
    border: 1px solid rgba(120,160,200,0.3);
    pointer-events: none; opacity: 0; transition: opacity 0.3s;
  }
  .view .zoomtag.on { opacity: 1; }
  #msg-float {
    position: absolute; left: 50%; transform: translateX(-50%);
    bottom: 212px;            /* clear of the gyro, which owns the bottom centre */
    max-width: 52%; z-index: 40;
    padding: 9px 16px; border-radius: 7px;
    font: 600 15px/1.35 system-ui, sans-serif; text-align: center;
    color: #eaf3ff; background: rgba(14,22,32,0.92);
    border: 1px solid rgba(120,160,200,0.45);
    box-shadow: 0 4px 18px rgba(0,0,0,0.5);
    cursor: pointer; pointer-events: auto;
    transition: opacity 0.25s;
  }
  #msg-float.empty { display: none; }
  #msg-float.alert {
    color: #ffe2e2; background: rgba(104,20,20,0.95);
    border-color: rgba(255,120,120,0.7);
    cursor: default;          /* a warning is not dismissed by a stray click */
  }
  #msg-float.fresh { animation: msgpulse 1.1s ease-out 2; }
  @keyframes msgpulse {
    0% { box-shadow: 0 0 0 0 rgba(255,190,80,0.55); }
    100% { box-shadow: 0 0 0 16px rgba(255,190,80,0); }
  }
  #msg-float .hint {
    display: block; margin-top: 3px; font-weight: 400; font-size: 11px;
    color: rgba(190,210,235,0.6);
  }
  #view-payload .nosignal {
    max-width: 440px; display: flex; flex-direction: column; gap: 7px;
    text-align: left; line-height: 1.4; padding: 14px 16px;
  }
  #view-payload .nosignal code {
    font-family: 'IBM Plex Mono', monospace; font-size: 12px;
    background: rgba(0,0,0,0.55); padding: 5px 8px; border-radius: 5px;
    user-select: all;
  }
  #view-payload img { user-select: none; -webkit-user-drag: none; }
  #view-payload.slewing { cursor: grabbing; }
  #view-payload.picking { cursor: crosshair; }

  /* ---------- settings ---------- */
  #win-settings { width: 560px; }
  .win-body.settings { flex-direction: row; gap: 0; align-items: stretch; padding: 0; }
  .set-tabs {
    display: flex; flex-direction: column; gap: 2px; padding: 10px 8px;
    border-right: 1px solid rgba(255,255,255,0.1); flex: none; width: 146px;
  }
  .set-tabs button {
    text-align: left; border: 0; border-radius: 7px; cursor: pointer;
    background: transparent; color: var(--dim); padding: 8px 10px; font-size: 12px;
  }
  .set-tabs button:hover { background: rgba(255,255,255,0.07); color: #fff; }
  .set-tabs button.on { background: rgba(255,255,255,0.13); color: #fff; font-weight: 600; }
  .set-panes { flex: 1 1 auto; padding: 12px 14px; min-width: 0; max-height: 440px; overflow-y: auto; }
  .set-pane { display: none; flex-direction: column; gap: 14px; }
  .set-pane.on { display: flex; }
  .set-pane .group { display: block; }
  .set-pane .sethead {
    font-size: 11px; letter-spacing: 0.08em; text-transform: uppercase;
    color: var(--dim); margin-bottom: 8px;
  }
  .set-pane .items { display: flex; flex-direction: column; gap: 7px; }

  /* The external view angle: a reading, two arrows and a lock. The arrows
     are deliberately large - they get held down while watching the picture
     rather than the button. */
  .anglebox { display: flex; align-items: center; gap: 6px; }
  .anglebox #angle-read {
    min-width: 58px; text-align: right; font-size: 16px; font-weight: 600;
    color: #fff; font-variant-numeric: tabular-nums;
  }
  .anglebox button {
    width: 30px; height: 28px; border-radius: 6px; cursor: pointer;
    border: 1px solid rgba(255,255,255,0.18); background: rgba(255,255,255,0.07);
    color: #dbe3f0; font-size: 12px; line-height: 1;
  }
  .anglebox button:hover { background: rgba(255,255,255,0.14); color: #fff; }
  .anglebox button:disabled { opacity: 0.35; cursor: default; }
  .anglebox .anglelock { width: auto; padding: 0 12px; font-size: 12px; }
  .anglebox .anglelock.locked {
    background: rgba(90,200,120,0.22); border-color: rgba(90,200,120,0.55);
    color: #bdf0cb;
  }
  .set-note { font-size: 11px; color: #7f8da4; margin-top: -8px; line-height: 1.4; }
  .set-note.locked { color: #8fc9a3; }

  /* ---------- the flight log ---------- */
  #win-flightlog { width: 560px; }
  .win-body.flightlog { flex-direction: column; gap: 10px; align-items: stretch; }
  .fl-now {
    padding: 9px 12px; border-radius: 8px; background: rgba(255,255,255,0.07);
    font-size: 12px;
  }
  .fl-now.live { background: rgba(123,26,45,0.5); color: #ffd8de; }
  .fl-list { max-height: 330px; overflow-y: auto; display: flex; flex-direction: column; gap: 6px; }
  .fl-row {
    display: grid; grid-template-columns: 136px 1fr; gap: 10px;
    padding: 8px 10px; border-radius: 8px; background: rgba(255,255,255,0.05);
    font-size: 12px;
  }
  .fl-row .when { color: var(--dim); font-family: 'IBM Plex Mono', monospace; }
  .fl-row .nums { display: flex; flex-wrap: wrap; gap: 10px; }
  .fl-row .nums b { font-family: 'IBM Plex Mono', monospace; font-weight: 600; }
  .fl-row.breach { background: rgba(123,26,45,0.4); }
  .fl-foot { font-size: 11px; color: var(--dim); }

  .set-row { display: flex; align-items: center; gap: 12px; }
  .set-label { width: 112px; flex: none; color: var(--dim); font-size: 12px; }
  .set-stack { display: flex; flex-direction: column; gap: 6px; }
  .set-inline { display: flex; align-items: center; gap: 10px; }
  .set-hint { font-size: 11px; color: var(--dim); max-width: 232px; line-height: 1.35; }
  #motor-volume { width: 104px; }
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
  /* Semi-transparent, so the picture underneath is still readable - a
     panel over a camera view should dim what is behind it, not delete it.
     Backdrop blur keeps the text legible over a busy picture. */
  .window {
    position: absolute; z-index: 58; display: none; flex-direction: column;
    max-width: 820px; max-height: calc(100% - 180px); overflow: auto;
    border-radius: 12px; background: rgba(12,16,22,0.78);
    backdrop-filter: blur(7px); -webkit-backdrop-filter: blur(7px);
    border: 1px solid rgba(255,255,255,0.26);
    box-shadow: 0 18px 54px rgba(0,0,0,0.7);
  }
  .window.open { display: flex; }
  /* Dragged by its title bar, like every other panel on this console. */
  .win-head { cursor: grab; }
  .win-head:active { cursor: grabbing; }
  .window.dragging { box-shadow: 0 22px 64px rgba(0,0,0,0.85); }
  /* Failure injection sits in the one part of the screen with nothing on
     it: inboard of the right-hand column, below the aircraft's state
     readouts in the gauge's top corner, above the corner view. Everything
     an instructor reads while a student flies - the tapes, the heading,
     the attitude indicator, the parameter band - stays uncovered. */
  .window.topright { min-width: 0; width: 204px; }
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
  #preflight { background: rgba(12,16,22,0.82); backdrop-filter: blur(7px);
               -webkit-backdrop-filter: blur(7px); }
  #preflight .pf-head { cursor: grab; }
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
  <!-- Only what is used in flight stays on the bar. Everything set once
       and left alone - the gauge, the alarm, the voice, how the camera is
       rendered, the layout - lives behind the gear, which is where a DJI
       controller puts the same things. The bar had grown until the camera
       view select was printing over the aircraft's own state. -->
  <div class="tools" style="flex: 1 1 auto; justify-content: center; gap: 14px">
    <!-- Which picture is on the main screen. Kept first and kept visible
         at all times: a remote pilot used to a DJI controller expects the
         camera selector to be one tap away and never buried, and this is
         the control that gets used most in a lesson. -->
    <div class="seg" id="viewtabs">
      <button data-view="chase">Chase</button>
      <button data-view="nose">Nose</button>
      <button data-view="payload">Payload</button>
      <button data-view="map">Map</button>
    </div>
    <button class="topbtn" id="pf-open">Checklist</button>
    <button class="topbtn" data-open-win="motors">Motors</button>
    <button class="topbtn danger" data-open-win="failures">Failures</button>
    <button class="topbtn" data-open-win="flightlog">Log</button>
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
    <!-- LAST on the bar, on the instruction of 12 Oct 2026. Settings on
         the far right is where every tablet and every GCS puts it, and a
         control nobody touches in flight should not sit between two that
         are. -->
    <button class="topbtn icon" id="settings-open" title="Settings" aria-label="Settings">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.1" stroke-linecap="round" aria-hidden="true">
        <path d="M4 7h16M4 12h16M4 17h16"></path>
      </svg>
    </button>
    <!-- CLOSE, where every application keeps it: last on the bar, top
         right. Added 13 Oct 2026, when the separate red "stop" desktop
         icon was merged away - this is where that one-click stop went.
         It always asks first; see the dialog below. -->
    <button class="topbtn icon close" id="exit-open" title="Exit the GCS"
            aria-label="Exit">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" aria-hidden="true">
        <path d="M6 6l12 12M18 6L6 18"></path>
      </svg>
    </button>
  </div>
</div>

<!-- DO YOU WANT TO EXIT? Deliberately a dialog of its own rather than one
     of the draggable panels: it must appear in the middle, over
     everything, and it must not be possible to drag it somewhere and
     leave it there. No is the default - Escape, the backdrop and Enter
     all mean No, and only the Yes button means yes. -->
<div id="exit-ask" class="askback" role="dialog" aria-modal="true"
     aria-labelledby="exit-title">
  <div class="askcard">
    <div class="asktitle" id="exit-title">Do you want to exit?</div>
    <div class="asknote">This stops the simulator and the instructor
      station. Any exercise in progress ends.</div>
    <div class="askrow">
      <button class="askno" id="exit-no">No</button>
      <button class="askyes" id="exit-yes">Yes</button>
    </div>
  </div>
</div>

<div id="irnote">Simulated infrared - a rendering of the colour camera, not a thermal sensor.</div>
<div id="limit-banner" class="limit-banner"></div>

<div id="hero"></div>

<!-- MESSAGES IN THE PICTURE, added 12 Oct 2026 on request: "place
     messages in the main screen away from the gyroscope grid". The rail
     panel is still there and still the record; this is the copy the
     instructor actually sees, because the eye is on the picture, not on
     the column. Sat above the gyro rather than beside it - the gyro owns
     the bottom centre, and anything over it hides the attitude at the
     moment attitude matters. Clicking it dismisses it, UNLESS it is a
     warning: a warning that can be waved away with a stray click is not
     a warning. -->
<div id="msg-float" class="empty"><span id="msg-float-text"></span></div>

<!-- the three views, created once and moved between the hero and the tiles -->
<div id="viewstore" style="display: none">
  <div class="view" id="view-chase" data-name="Chase">
    <img src="/chase_feed" alt="Chase camera" onerror="this.style.display='none'">
    <canvas class="hud"></canvas>
    <div class="nosignal">No chase camera yet. Add it with tools/chase_camera_apply.py, then restart the simulator.</div>
    <!-- Which way round the aircraft the external view looks from. These
         only do anything once tools/chase_angles_apply.py has put the
         camera on its boom; before that the view stays behind the
         aircraft and the buttons report that nothing moved. -->
    <div class="paybar chasebar" id="chasebar">
      <span class="striphandle" title="Drag to move this strip; where it is put is remembered">&#8942;&#8942;</span>
      <span class="payread">External view</span>
      <button data-chase="behind" class="on">Behind</button>
      <button data-chase="port">Left</button>
      <button data-chase="starboard">Right</button>
      <button data-chase="nose">Front</button>
      <button data-chase="top">Top</button>
      <button data-chase="low">Low</button>
    </div>
  </div>
  <div class="view" id="view-nose" data-name="Nose">
    <img src="/video_feed" alt="Nose camera" onerror="this.style.display='none'">
    <canvas id="hud" class="hud"></canvas>
    <div class="nosignal">No nose camera signal yet.</div>
  </div>
  <!-- The payload gimbal. Drag to slew, wheel to zoom, TRACK then click to
       lock onto a point. The control strip sits across the bottom, which
       is where DJI's payload controls live and therefore where a remote
       pilot's hand already goes. -->
  <div class="view" id="view-payload" data-name="Payload">
    <img src="/payload_feed" alt="Payload camera" onerror="this.style.display='none'">
    <!-- Deliberately NOT class="hud": the flight gauge draws into every
         canvas.hud, and an artificial horizon over a sensor picture is
         not what a payload operator is looking at. This one carries a
         reticle and the pointing angles instead. -->
    <canvas class="pay-hud" id="pay-hud"></canvas>
    <div class="nosignal" id="pay-nosignal">
      <b>No picture from the gimbal camera.</b>
      <span>The gimbal has to be added to the aircraft once. In a terminal:</span>
      <code>python3 tools/gimbal_apply.py</code>
      <span>Then stop the simulator and start it again. If it is still blank
        after that, check Gazebo is publishing the picture:</span>
      <code>gz topic -l | grep payload</code>
      <span id="pay-topic"></span>
    </div>
    <div class="paybar" id="paybar">
      <span class="payread" id="pay-read">-</span>
      <span class="paygroup">
        <button data-pay="zoomout" title="Zoom out">&minus;</button>
        <b id="pay-zoom">1.0x</b>
        <button data-pay="zoomin" title="Zoom in">+</button>
      </span>
      <select id="pay-view" class="topsel" title="These are renderings of the colour camera, not a thermal sensor.">
        <option value="normal">Day</option>
        <option value="white_hot">IR white hot</option>
        <option value="black_hot">IR black hot</option>
        <option value="night_vision">Night vision</option>
      </select>
      <button data-pay="lase" title="Fire the rangefinder once">LRF</button>
      <button data-pay="track" id="pay-track" title="Then click the target you want held">TRACK</button>
      <button data-pay="photo" title="Save a photograph with its position">PHOTO</button>
      <button data-pay="record" id="pay-record" title="Start or stop recording">REC</button>
      <button data-pay="stab" id="pay-stab" title="Hold the line of sight while the aircraft moves">STAB</button>
      <button data-pay="centre" title="Point it straight ahead">Centre</button>
      <button data-pay="stow" title="Point it straight down">Stow</button>
    </div>
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
  <div class="railbody">__RIGHT_RAIL__
    <!-- THE MESSAGE PANEL. Every reply from the station lands here.
         It used to be a small box floating in a corner of the picture,
         which was both easy to miss and - for an alert, which never
         faded - permanently in the way. Here it is always in the same
         place, at eye level in the column the instructor is already
         working, and it fills the space under TERMINATE that nothing
         else needs. -->
    <div id="status" class="empty">
      <div class="msg-head">MESSAGE</div>
      <div class="msg-text" id="status-text">Console ready.</div>
      <div class="msg-age" id="status-age"></div>
    </div>
  </div>
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

<!-- SETTINGS. Rebuilt 12 Oct 2026 with categories down the side, because
     it had become one column that everything new was appended to, and
     "where is the wind control" was becoming a question. The tabs are
     the answer to that question: a thing is in the tab it belongs to.

     The three plugin groups are filled in by the station from
     SETTINGS_GROUPS; the last placeholder in the Session tab catches any
     control no group claims, so nothing can silently disappear when the
     layout changes. -->
<div class="window" id="win-settings">
  <div class="win-head"><b>Settings</b>
    <button class="win-close" data-win="settings" title="Close">&times;</button>
  </div>
  <div class="win-body settings">
    <div class="set-tabs" id="set-tabs">
      <button data-tab="display" class="on">Display</button>
      <button data-tab="sound">Warnings &amp; sound</button>
      <button data-tab="environment">Environment</button>
      <button data-tab="aircraft">Aircraft</button>
      <button data-tab="mission">Mission</button>
      <button data-tab="session">Session</button>
    </div>
    <div class="set-panes">
      <div class="set-pane on" data-pane="display">
        <div class="set-row">
          <span class="set-label">Layout</span>
          <div class="seg" id="layouttabs" title="Pilot floats the controls over the picture; Station insets it so nothing covers it">
            <button data-layout="pilot">Pilot</button>
            <button data-layout="station">Station</button>
          </div>
        </div>
        <div class="set-row">
          <span class="set-label">Camera view</span>
          <select id="viewmode" class="topsel" title="The infrared views are renderings of the colour camera, not a thermal sensor.">
            <option value="normal">Daylight</option>
            <option value="night_vision">Night vision</option>
            <option value="white_hot">IR white hot</option>
            <option value="black_hot">IR black hot</option>
          </select>
        </div>
        <div class="set-row">
          <span class="set-label">Flight display</span>
          <label class="topswitch"><input type="checkbox" id="hud-on" checked> Gauge over the camera views</label>
        </div>
        <div class="set-row">
          <span class="set-label">Panels</span>
          <button class="topbtn" id="resettiles" title="Put every panel back to its default place and size">Reset every panel</button>
        </div>
      </div>

      <div class="set-pane" data-pane="sound">
        <div class="set-row">
          <span class="set-label">Warnings</span>
          <div class="set-stack">
            <label class="topswitch"><input type="checkbox" id="alarm-on" checked> Alarm tone</label>
            <label class="topswitch"><input type="checkbox" id="voice-on"> Spoken callouts</label>
          </div>
        </div>
        <div class="set-row">
          <span class="set-label">Motor sound</span>
          <div class="set-stack">
            <div class="set-inline">
              <label class="topswitch"><input type="checkbox" id="motor-sound-on" checked> On</label>
              <input type="range" id="motor-volume" min="0" max="100" value="60"
                     title="How loud the motors are">
            </div>
            <span class="set-hint">Synthesised, and driven by the throttle. A
              browser stays silent until the page has been clicked.</span>
          </div>
        </div>
        <div class="set-row">
          <span class="set-label">Lights</span>
          <div class="set-stack">
            <label class="topswitch"><input type="checkbox" id="lights-on"> Navigation lights</label>
            <span class="set-hint">Red to port, green to starboard, white at the
              tail, all steady. White strobes double-flash; the red beacon
              flashes while armed.</span>
          </div>
        </div>
      </div>

      <div class="set-pane" data-pane="environment">__SETTINGS_ENVIRONMENT__</div>
      <div class="set-pane" data-pane="aircraft">
        <!-- EXTERNAL VIEW ANGLE. How far above the aircraft the chase
             camera sits, in degrees, for the Behind view. The arrows move
             the camera straight away so the angle can be judged by eye;
             LOCK writes it down, and from then on every session opens at
             it until it is changed again. Works on the ground and in the
             air alike - the boom is a camera mount and the flight
             controller knows nothing about it.

             Top and Low are deliberately not affected. They exist to be
             different angles, and forcing this figure on them would leave
             six buttons that all did the same thing. -->
        <!-- FUSELAGE COLOUR. Changed while the aircraft flies - Gazebo
             will recolour a visual at runtime, so this needs no restart.
             Lock keeps it for every future session, like the angle below. -->
        <div class="set-row">
          <span class="set-label">Fuselage</span>
          <span>
            <select id="livery" class="topsel" title="Orange is easiest to keep in sight; grey is what the real aircraft looks like"></select>
            <button id="livery-lock" class="anglelock">Lock</button>
          </span>
        </div>
        <div class="set-note" id="livery-note">Not locked &mdash; this session only.</div>
        <div class="set-row">
          <span class="set-label">External view angle</span>
          <div class="anglebox">
            <span id="angle-read" title="Degrees above the aircraft">17&deg;</span>
            <button id="angle-up" title="Raise the view (the camera climbs)">&#9650;</button>
            <button id="angle-down" title="Lower the view (the camera drops)">&#9660;</button>
            <button id="angle-lock" class="anglelock">Lock</button>
          </div>
        </div>
        <div class="set-note" id="angle-note">
          Not locked &mdash; this session only. Lock keeps it for every future session.
        </div>
        __SETTINGS_AIRCRAFT__
      </div>
      <!-- Mission planning has its own tab: it is a job, not a setting,
           and it is the one panel an instructor needs room to read
           before anything flies. -->
      <div class="set-pane" data-pane="mission">__SETTINGS_MISSION__</div>
      <div class="set-pane" data-pane="session">__SETTINGS_SESSION__
        __SETTINGS_OTHER__
      </div>
    </div>
  </div>
</div>

<!-- The flight record. Every flight is written whether or not anyone
     opens this; this is just where it is read back. -->
<div class="window" id="win-flightlog">
  <div class="win-head"><b>Flight log</b>
    <button class="win-close" data-win="flightlog" title="Close">&times;</button>
  </div>
  <div class="win-body flightlog">
    <div id="fl-now" class="fl-now">No flight in progress.</div>
    <div id="fl-list" class="fl-list"></div>
    <div class="fl-foot" id="fl-foot"></div>
  </div>
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
    shut: SAVED.shut || [],
    // Where each pop-up panel was last dragged to.
    windows: SAVED.windows || {}
  };

  var el = function (id) { return document.getElementById(id); };
  var hero = el('hero'), store = el('viewstore'), mask = el('dragmask');
  var tiles = { left: el('tile-left'), right: el('tile-right') };
  var views = { chase: el('view-chase'), nose: el('view-nose'),
                payload: el('view-payload'), map: el('view-map') };
  // The order the corner tiles work through, so adding a fourth view did
  // not mean adding a fourth corner. Whatever is not the hero and not in
  // the other corner goes in the next free slot, and the view tabs reach
  // all of them anyway.
  var VIEW_ORDER = ['chase', 'nose', 'payload', 'map'];

  // ---------- messages ----------
  // The last reply from the station. An ordinary one fades after a few
  // seconds - it was staying on screen for the rest of the flight. An
  // alert does not fade, because an alert is a thing that went wrong and
  // the instructor may be looking at the aircraft when it appears.
  var sayTimer = null;
  // EVERY message clears itself, which the first version did not: an
  // alert stayed on screen for the rest of the flight, so by the end of
  // a lesson the panel was showing something that had happened twenty
  // minutes earlier. An ordinary reply goes after half a minute, an
  // alert after two - long enough to walk back to the screen, short
  // enough that it is never stale.
  var SAY_CLEAR_S = 30, ALERT_CLEAR_S = 120;
  var saidAt = null;

  // Test seams. Waiting two minutes to prove an alert clears is not a
  // test anyone runs, so the check shortens the timers instead.
  window.gcsSayClearSeconds = function (ordinary, alert) {
    SAY_CLEAR_S = ordinary;
    ALERT_CLEAR_S = alert;
  };

  // Clearing both copies is one job, so it is one function - the rail
  // panel and the floating one going out of step was the first thing
  // that went wrong when the float was added.
  function clearSaid() {
    el('status-text').innerText = 'Nothing to report.';
    el('status-age').innerText = '';
    el('status').className = 'empty';
    el('msg-float').className = 'empty';
    saidAt = null;
  }

  function say(text, alert) {
    var s = el('status');
    el('status-text').innerText = text;
    s.className = alert ? 'alert fresh' : 'ok';

    // The same words in the picture, which is where the eye is.
    var f = el('msg-float');
    el('msg-float-text').innerHTML = '';
    el('msg-float-text').appendChild(document.createTextNode(text));
    if (!alert) {
      var hint = document.createElement('span');
      hint.className = 'hint';
      hint.appendChild(document.createTextNode('click to dismiss'));
      el('msg-float-text').appendChild(hint);
    }
    f.className = alert ? 'alert fresh' : 'fresh';

    saidAt = Date.now();
    if (sayTimer) { clearTimeout(sayTimer); }
    sayTimer = setTimeout(clearSaid,
                          (alert ? ALERT_CLEAR_S : SAY_CLEAR_S) * 1000);
    // The pulse is a one-off; take the class off so a later alert can
    // restart it rather than finding it already applied.
    setTimeout(function () {
      s.classList.remove('fresh');
      f.classList.remove('fresh');
    }, 4000);
  }

  // ---------- digital zoom on the camera views ----------
  // Asked for 12 Oct 2026: hover any view, roll the wheel, it zooms. The
  // payload view already had its own wheel handler driving the REAL
  // gimbal zoom, so it is deliberately left alone here - two handlers on
  // one element would fight. The map has its own too, below.
  //
  // DIGITAL, and the tag says so. The nose and chase cameras are fixed
  // sensors; there is nothing to zoom optically, so this scales the
  // picture and the window crops it. Past about 3x it looks like what it
  // is.
  var VIEW_ZOOM_MIN = 1.0, VIEW_ZOOM_MAX = 6.0, VIEW_ZOOM_STEP = 1.2;
  var viewZoom = {};

  function applyViewZoom(name) {
    var view = el('view-' + name);
    if (!view) { return; }
    var img = view.querySelector('img');
    var z = viewZoom[name] || 1;
    if (img) { img.style.transform = 'scale(' + z.toFixed(3) + ')'; }
    var tag = view.querySelector('.zoomtag');
    if (!tag) {
      tag = document.createElement('div');
      tag.className = 'zoomtag';
      view.appendChild(tag);
    }
    tag.innerText = z > 1.001 ? ('DIGITAL ZOOM ' + z.toFixed(1) + 'x')
                              : 'ZOOM 1.0x';
    tag.className = 'zoomtag' + (z > 1.001 ? ' on' : '');
    if (z <= 1.001) {
      // Show 1.0x briefly on the way back down, then let it fade, so
      // the instructor can see they are back to the full picture.
      tag.classList.add('on');
      setTimeout(function () {
        if ((viewZoom[name] || 1) <= 1.001) { tag.classList.remove('on'); }
      }, 1200);
    }
  }

  window.gcsViewZoom = function (name) { return viewZoom[name] || 1; };

  ['chase', 'nose'].forEach(function (name) {
    var view = el('view-' + name);
    if (!view) { return; }
    viewZoom[name] = 1;
    // Built now rather than on the first zoom: a tag that does not
    // exist until something happens cannot be checked, and the check is
    // the only thing standing between "digital zoom" and an instructor
    // believing the aircraft carries a zoom lens.
    applyViewZoom(name);
    view.addEventListener('wheel', function (e) {
      e.preventDefault();
      var z = viewZoom[name] || 1;
      z = (e.deltaY < 0) ? z * VIEW_ZOOM_STEP : z / VIEW_ZOOM_STEP;
      viewZoom[name] = Math.max(VIEW_ZOOM_MIN, Math.min(VIEW_ZOOM_MAX, z));
      applyViewZoom(name);
    }, { passive: false });
  });

  // Click to dismiss - but never a warning. A warning waved away by a
  // stray click while reaching for a control is a warning nobody read.
  el('msg-float').addEventListener('click', function () {
    if (el('msg-float').classList.contains('alert')) { return; }
    if (sayTimer) { clearTimeout(sayTimer); }
    clearSaid();
  });

  // How long ago it was said. An instructor who looks away and back
  // needs to know whether the panel is reporting now or a minute ago.
  setInterval(function () {
    if (!saidAt) { return; }
    var seconds = Math.round((Date.now() - saidAt) / 1000);
    el('status-age').innerText = seconds < 3 ? 'just now'
      : (seconds < 60 ? seconds + ' s ago'
         : Math.round(seconds / 60) + ' min ago');
  }, 1000);

  window.gcsSay = say;

  // ---------- layout geometry ----------
  // Pilot floats the rails over the picture; Station insets the picture so
  // nothing ever covers it. Everything else is identical, which is the whole
  // reason these are one console and not two.
  function applyLayout() {
    var pilot = state.layout === 'pilot';
    // WIDER on 12 Oct 2026, twice over: once when the scrollbar got a
    // gutter, and again when the number boxes grew arrows beside them.
    // A label, a three-digit box and a stepper need about 115 px before
    // padding, and squeezing that into 132 was what clipped the values.
    // The figure itself lives in railWidth(), because the corner views
    // need it too.
    var railW = railWidth();

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
    // In Pilot the picture runs up behind the floating top bar, so
    // anything pinned to the top of the picture has to start below it.
    hero.classList.toggle('under-topbar', pilot);
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

  // The rail's width, in ONE place. It used to be written out in
  // applyLayout and again as a magic "142" in home(), and when the rails
  // were widened on 12 Oct 2026 only one of them changed - so the corner
  // views moved under the right-hand rail and covered the message panel.
  function railWidth() {
    return state.layout === 'pilot' ? 166 : 182;
  }

  // How far in from the window edge a corner view starts: past the rail,
  // plus the rail's own margin, plus a gap.
  function railEdge() {
    return railWidth() + (state.layout === 'pilot' ? 10 : 0) + 10;
  }

  function home(side) {
    // 400x250, the size the instructor settled on by dragging them there.
    // The old 212x120 was small enough that the map and the chase camera
    // had to be swapped into the main screen to be read at all, which
    // defeats the point of having them in the corner. Shrunk on a narrow
    // screen so the two never meet in the middle.
    var edge = railEdge();
    var between = window.innerWidth - 2 * edge - 24;
    var w = Math.min(400, Math.max(212, between / 2));
    var h = Math.round(w * 0.625);
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
    // The two corners show the next two views after the hero, wrapping
    // round. With four views one is always off-screen; the tabs reach it,
    // and showing three pictures at once was already more than anyone
    // watches. The payload view is skipped in the corners unless it is
    // the hero - it is the one view that is useless at tile size, and a
    // rendered camera nobody is looking at still costs frames.
    var ring = VIEW_ORDER.filter(function (n) {
      return n !== h && !(n === 'payload' && h !== 'payload');
    });
    var at = VIEW_ORDER.indexOf(h);
    var rotated = ring.slice(at % ring.length).concat(ring.slice(0, at % ring.length));
    var leftName = rotated[0], rightName = rotated[1] || rotated[0];
    if (leftName === rightName) { rightName = ring[ring.length - 1]; }

    // PARK EVERYTHING ELSE. This is the bug that made the payload
    // controls print over the chase view and left "TARGET LOCK" written
    // across the bottom of the screen for the rest of the session.
    //
    // With three views and three slots, every view was re-parented on
    // every swap, so nothing could be left behind. With four views and
    // three slots one is always homeless - and appendChild only MOVES
    // the view it is given. Select Payload, then Chase, and the payload
    // view was still a child of #hero: invisible itself, but its
    // control strip and its canvas were not, and both sat on top of the
    // picture and the left-hand controls with no way to get rid of them.
    for (var name in views) {
      if (name !== h && name !== leftName && name !== rightName) {
        store.appendChild(views[name]);
      }
    }
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

  // ---------- settings that apply the moment they change ----------
  // Asked for 12 Oct 2026: "any manual changes on any numerical value in
  // the command columns must respond to the change as soon as the value
  // has been changed".
  //
  // NOT EVERY CONTROL, and this is the important part. A number beside a
  // BUTTON is an argument to that button - "Climb (m) 60" next to CLIMB
  // means climb to 60 when pressed. Firing on change there would send
  // the aircraft climbing while somebody is still typing the second
  // digit. So a plugin has to declare itself as a setting
  // (apply_on_change), and only those fire. Everything else keeps its
  // button, which is what makes the button honest.
  //
  // Debounced, because a stepper held down emits a value every 45 ms and
  // each one would otherwise be a command to PX4.
  var applyTimers = {};
  document.addEventListener('change', function (e) {
    var input = e.target.closest ? e.target.closest('.param-input') : null;
    if (!input) { return; }
    var id = input.dataset.plugin;
    var button = document.getElementById('btn-' + id);
    if (!button || button.dataset.applyOnChange !== '1') { return; }
    if (applyTimers[id]) { clearTimeout(applyTimers[id]); }
    applyTimers[id] = setTimeout(function () {
      applyTimers[id] = null;
      window.gcsAction(id);
    }, 350);
  });
  // 'input' as well as 'change': a number box fires change only when it
  // loses focus, and an instructor who types a figure and then looks at
  // the picture never gives it back.
  document.addEventListener('input', function (e) {
    var input = e.target.closest ? e.target.closest('.param-input') : null;
    if (!input || input.type === 'text') { return; }
    var id = input.dataset.plugin;
    var button = document.getElementById('btn-' + id);
    if (!button || button.dataset.applyOnChange !== '1') { return; }
    if (applyTimers[id]) { clearTimeout(applyTimers[id]); }
    applyTimers[id] = setTimeout(function () {
      applyTimers[id] = null;
      window.gcsAction(id);
    }, 700);
  });

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

    // __LIMITS__ is whatever envelope the page was rendered with. The
    // instructor can switch envelope mid-session, so the live figure in
    // telemetry wins when it is there.
    var lim = (telem && telem.limits) ? telem.limits : __LIMITS__;
    // 100000 m in a bar label is unreadable, and the extended envelope
    // is exactly that. Anything a kilometre or more reads in km.
    function fmtLim(v, unit) {
      if (unit === 'm' && v >= 1000) { return (v / 1000) + ' km'; }
      return v + ' ' + unit;
    }
    function bar(barId, valId, value, max, unit) {
      var pct = Math.max(0, Math.min(100, (value / max) * 100));
      var b = el(barId);
      b.style.width = pct + '%';
      b.style.background = pct >= 100 ? '#e03b3b' : (pct >= 90 ? '#ffc94d' : '#57cc7f');
      el(valId).innerText = value.toFixed(value < 10 ? 1 : 0) + '/'
        + fmtLim(max, unit);
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
  // The gauge itself now lives in attitude_gauge.py, so this page and the
  // QGC-shaped one draw the same instrument rather than two copies that
  // drift. It reads window.gcsTelemetry, which this page already keeps up
  // to date a few lines above.
  function drawGyro() {
    if (window.gcsDrawAttitude) { window.gcsDrawAttitude('gyro', 184); }
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

  // ---------- the number steppers ----------
  // Press for one step, hold to run. The acceleration is the point:
  // "typing is taking too long" means going from 20 to 400 should be a
  // held button, not forty clicks or a keyboard. stepUp/stepDown are
  // the browser's own, so each control's own min, max and step are
  // honoured without this code knowing any of them.
  var holding = null;

  function stepOnce(button) {
    var input = el(button.dataset.for);
    if (!input) { return; }
    if (button.dataset.step === 'up') { input.stepUp(); } else { input.stepDown(); }
    // Fire the same event typing would, so anything watching the field
    // sees the change.
    input.dispatchEvent(new Event('change', { bubbles: true }));
  }

  function stopHolding() {
    if (!holding) { return; }
    clearTimeout(holding.timer);
    holding = null;
  }

  document.addEventListener('mousedown', function (e) {
    var button = e.target.closest ? e.target.closest('.step button[data-step]') : null;
    if (!button) { return; }
    e.preventDefault();
    stopHolding();
    stepOnce(button);
    holding = { button: button, delay: 420, timer: null };
    function again() {
      if (!holding) { return; }
      stepOnce(holding.button);
      // Faster the longer it is held, down to a floor - so a short hold
      // nudges and a long one travels.
      holding.delay = Math.max(45, holding.delay * 0.72);
      holding.timer = setTimeout(again, holding.delay);
    }
    holding.timer = setTimeout(again, holding.delay);
  });
  window.addEventListener('mouseup', stopHolding);
  window.addEventListener('blur', stopHolding);

  // ---------- the payload gimbal ----------
  // Three gestures, which are the three a payload operator already knows:
  // drag to slew, wheel to zoom, and - after arming it with TRACK -
  // click the thing you want held in frame. Nothing here guesses what
  // the gimbal did: every control sends its command and redraws from the
  // answer the station sends back, so the readout cannot drift away from
  // where the gimbal actually is.
  var pay = { status: null, picking: false, drag: null, wheelTimer: null,
              wheelSteps: 0 };
  var payView = el('view-payload');

  function payDraw(d) {
    if (!d) { return; }
    pay.status = d;
    el('pay-zoom').innerText = d.zoom.toFixed(1) + 'x';
    var range = '-';
    if (d.range_m != null) {
      range = Math.round(d.range_m) + ' m';
      // A rangefinder reading with no age on it is a trap: a stale number
      // looks exactly like a live one.
      if (d.range_source === 'computed') { range += ' (calc)'; }
      else if (d.range_stale) { range += ' (' + d.range_age_s + 's old)'; }
    }
    el('pay-read').innerText =
      'PAN ' + d.pan_deg.toFixed(0) + '\u00b0  TILT ' + d.tilt_deg.toFixed(0)
      + '\u00b0  FOV ' + d.fov_deg.toFixed(0) + '\u00b0  RNG ' + range
      + '  ' + (d.mode === 'lock' ? 'LOCK'
                : (d.mode === 'acquiring' ? 'ACQUIRING' : 'MANUAL'));
    var track = el('pay-track');
    track.className = (d.mode === 'lock' || d.mode === 'acquiring' || pay.picking)
      ? 'on' : '';
    track.innerText = (d.mode === 'lock') ? 'UNLOCK' : 'TRACK';
    el('pay-stab').className = d.stabilised ? 'on' : '';
    var rec = el('pay-record');
    rec.className = d.recording && d.recording.on ? 'rec' : '';
    rec.innerText = (d.recording && d.recording.on)
      ? 'REC ' + Math.round(d.recording.seconds) + 's' : 'REC';
    el('pay-nosignal').style.display = d.camera_live ? 'none' : '';
    if (!d.camera_live && d.topic) {
      el('pay-topic').innerText = 'Listening on ' + d.topic;
    }
    if (d.said) { say(d.said); }
  }

  // The reticle. A payload picture with no marks on it gives an operator
  // nothing to aim with and no sense of how wide the view is: the ticks
  // are drawn at a tenth of the field of view, so counting them off is a
  // rough measure of angle, which is how a real sensor operator judges
  // how far to slew.
  function payReticle() {
    var cv = el('pay-hud');
    if (!cv || !cv.parentElement || !cv.parentElement.offsetWidth) { return; }
    var box = cv.getBoundingClientRect();
    var dpr = window.devicePixelRatio || 1;
    if (cv.width !== Math.round(box.width * dpr)) {
      cv.width = Math.round(box.width * dpr);
      cv.height = Math.round(box.height * dpr);
    }
    var g = cv.getContext('2d');
    var w = box.width, h = box.height;
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    var d = pay.status;
    var cx = w / 2, cy = h / 2;
    var locked = d && d.mode === 'lock';
    g.strokeStyle = locked ? 'rgba(255,196,0,0.95)' : 'rgba(255,255,255,0.8)';
    g.lineWidth = 1.4;
    // A gap in the middle, so the reticle never hides the thing it is on.
    g.beginPath();
    g.moveTo(cx - 34, cy); g.lineTo(cx - 9, cy);
    g.moveTo(cx + 9, cy); g.lineTo(cx + 34, cy);
    g.moveTo(cx, cy - 34); g.lineTo(cx, cy - 9);
    g.moveTo(cx, cy + 9); g.lineTo(cx, cy + 34);
    g.stroke();
    if (locked) {
      g.strokeRect(cx - 26, cy - 26, 52, 52);
    }
    // Ticks every tenth of the frame along the middle lines.
    g.strokeStyle = 'rgba(255,255,255,0.45)';
    g.beginPath();
    for (var i = -4; i <= 4; i++) {
      if (!i) { continue; }
      var x = cx + i * w / 10, y = cy + i * h / 10;
      g.moveTo(x, cy - 5); g.lineTo(x, cy + 5);
      g.moveTo(cx - 5, y); g.lineTo(cx + 5, y);
    }
    g.stroke();
    if (!d) { return; }
    g.font = '600 12px "IBM Plex Mono", monospace';
    g.fillStyle = locked ? 'rgba(255,196,0,0.95)' : 'rgba(255,255,255,0.85)';
    g.fillText((d.zoom).toFixed(1) + 'x  ' + d.fov_deg.toFixed(0)
               + '\u00b0 FOV (digital zoom)', 14, h - 40);
    g.fillStyle = 'rgba(255,255,255,0.7)';
    g.fillText(locked ? 'TARGET LOCK'
               : (d.stabilised
                  ? 'STABILISED  brg ' + Math.round(d.world_az_deg)
                    + '\u00b0  depr ' + Math.round(d.world_el_deg) + '\u00b0'
                  : 'UNSTABILISED - the picture will roll with the aircraft'),
               14, h - 22);
  }
  var reticleWasOn = false;
  setInterval(function () {
    var on = (state.hero === 'payload');
    if (on) { payReticle(); reticleWasOn = true; }
    else if (reticleWasOn) {
      // A canvas keeps its pixels. Parking the view hides it, but
      // clearing it as well means a stale frame cannot reappear if the
      // element is ever shown again before the first redraw.
      var cv = el('pay-hud');
      if (cv && cv.width) { cv.getContext('2d').clearRect(0, 0, cv.width, cv.height); }
      reticleWasOn = false;
    }
  }, 200);

  function payCall(path) {
    return fetch(path).then(function (r) { return r.json(); })
      .then(payDraw).catch(function () { say('The station did not answer.', true); });
  }

  el('paybar').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button') : null;
    if (!b) { return; }
    var what = b.dataset.pay;
    if (what === 'zoomin') { payCall('/payload_zoom?steps=1'); }
    else if (what === 'zoomout') { payCall('/payload_zoom?steps=-1'); }
    else if (what === 'lase') { payCall('/payload_lase'); }
    else if (what === 'photo') { payCall('/payload_photo'); }
    else if (what === 'stab') {
      var on = pay.status && pay.status.stabilised;
      payCall('/payload_stabilise?on=' + (on ? '0' : '1'));
    }
    else if (what === 'centre') { payCall('/payload_centre'); }
    else if (what === 'stow') { payCall('/payload_stow'); }
    else if (what === 'record') {
      var on = pay.status && pay.status.recording && pay.status.recording.on;
      payCall('/payload_record?on=' + (on ? '0' : '1'));
    } else if (what === 'track') {
      if (pay.status && pay.status.mode === 'lock') {
        pay.picking = false;
        payView.classList.remove('picking');
        payCall('/payload_unlock');
      } else {
        pay.picking = !pay.picking;
        payView.classList.toggle('picking', pay.picking);
        say(pay.picking
            ? 'Click the target you want the gimbal to hold.'
            : 'Target selection cancelled.');
        payDraw(pay.status);
      }
    }
  });

  el('pay-view').addEventListener('change', function () {
    payCall('/payload_view?mode=' + el('pay-view').value);
  });

  // Drag to slew. The movement is converted through the field of view
  // actually on screen, so a drag of half the frame moves the gimbal by
  // half the frame whatever the zoom - which is what makes a zoomed-in
  // view usable rather than unusably twitchy.
  payView.addEventListener('mousedown', function (e) {
    if (e.button !== 0 || e.target.closest('.paybar')) { return; }
    e.preventDefault();
    var box = payView.getBoundingClientRect();
    pay.drag = { x: e.clientX, y: e.clientY, box: box, moved: 0 };
    payView.classList.add('slewing');
  });

  window.addEventListener('mousemove', function (e) {
    if (!pay.drag) { return; }
    var dx = e.clientX - pay.drag.x, dy = e.clientY - pay.drag.y;
    if (Math.abs(dx) < 2 && Math.abs(dy) < 2) { return; }
    pay.drag.moved += Math.abs(dx) + Math.abs(dy);
    pay.drag.x = e.clientX; pay.drag.y = e.clientY;
    var fov = pay.status ? pay.status.fov_deg : 60;
    var box = pay.drag.box;
    // Dragging left moves the picture left, which means the camera has to
    // look right - hence the sign.
    var dpan = -(dx / Math.max(1, box.width)) * fov;
    var dtilt = -(dy / Math.max(1, box.height)) * fov * (box.height / Math.max(1, box.width));
    payCall('/payload_aim?dpan=' + dpan.toFixed(3) + '&dtilt=' + dtilt.toFixed(3));
  });

  window.addEventListener('mouseup', function (e) {
    if (!pay.drag) { return; }
    var moved = pay.drag.moved;
    var box = pay.drag.box;
    pay.drag = null;
    payView.classList.remove('slewing');
    // A click, not a drag, and target selection is armed: that is the
    // point to hold. u and v are fractions of the frame from its centre.
    if (moved < 6 && pay.picking) {
      var u = (e.clientX - box.left) / Math.max(1, box.width) - 0.5;
      var v = (e.clientY - box.top) / Math.max(1, box.height) - 0.5;
      if (u > -0.5 && u < 0.5 && v > -0.5 && v < 0.5) {
        pay.picking = false;
        payView.classList.remove('picking');
        payCall('/payload_lock?u=' + u.toFixed(4) + '&v=' + v.toFixed(4));
      }
    }
  });

  // The wheel fires far faster than the station needs to hear about it,
  // so the notches are added up and sent as one step a frame.
  payView.addEventListener('wheel', function (e) {
    e.preventDefault();
    pay.wheelSteps += (e.deltaY < 0) ? 1 : -1;
    if (pay.wheelTimer) { return; }
    pay.wheelTimer = setTimeout(function () {
      var steps = pay.wheelSteps;
      pay.wheelSteps = 0;
      pay.wheelTimer = null;
      payCall('/payload_zoom?steps=' + steps);
    }, 70);
  }, { passive: false });

  function refreshPayload() {
    // Only while the payload picture is actually on screen. Polling a
    // panel nobody is looking at is how a console ends up slow.
    if (state.hero !== 'payload') { return; }
    fetch('/payload_status').then(function (r) { return r.json(); })
      .then(payDraw).catch(function () {});
  }
  setInterval(refreshPayload, 500);

  // ---------- which way the external view looks from ----------
  el('chasebar').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button') : null;
    if (!b) { return; }
    fetch('/chase_view?preset=' + b.dataset.chase)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        el('chasebar').querySelectorAll('button').forEach(function (x) {
          x.className = (x.dataset.chase === d.preset) ? 'on' : '';
        });
        // Say what actually happened. This used to claim "only moves
        // once the camera is on its boom" after every click, worked or
        // not, which told an instructor nothing and sent a day of
        // debugging the wrong way.
        if (d.sent) {
          say('External view: ' + b.innerText + '.');
        } else {
          say('External view ' + b.innerText + ' NOT sent - the station '
              + 'could not reach the boom. Run tools/chase_angles_apply.py '
              + 'and restart the simulator.', true);
        }
      }).catch(function () { say('The station did not answer.', true); });
  });

  // ---------- exit ----------
  // The X on the top bar, and the question it asks. No is the default in
  // every sense: Escape, the backdrop, Enter and anything that is not the
  // Yes button all mean No. Only Yes shuts anything down.
  var exitBox = el('exit-ask');
  function askExit(show) {
    exitBox.classList.toggle('open', show);
    if (show) { el('exit-no').focus(); }
  }
  el('exit-open').addEventListener('click', function () { askExit(true); });
  el('exit-no').addEventListener('click', function () { askExit(false); });
  exitBox.addEventListener('mousedown', function (e) {
    // A click on the dark backdrop, but not one inside the card.
    if (e.target === exitBox) { askExit(false); }
  });
  el('exit-yes').addEventListener('click', function () {
    var card = exitBox.querySelector('.askcard');
    card.classList.add('going');
    exitBox.querySelector('.asktitle').textContent = 'Closing down\\u2026';
    exitBox.querySelector('.asknote').textContent =
      'Stopping the simulator and the station. This window can be closed.';
    // The station stops itself a moment after answering, so this request
    // is expected to fail as it goes - which is not an error to report.
    fetch('/exit', { method: 'POST' }).catch(function () {});
    setTimeout(function () {
      exitBox.querySelector('.asktitle').textContent = 'Closed.';
      exitBox.querySelector('.asknote').textContent =
        'The simulator and the station have stopped. Start them again '
        + 'with the UAV Academy GCS Pro icon.';
      // Only works if the browser opened this window itself, which the
      // kiosk shortcut does; harmless otherwise, hence the message above.
      try { window.close(); } catch (err) { /* nothing to do */ }
    }, 2500);
  });

  // ---------- the fuselage colour ----------
  // The list comes from the station rather than being written out here,
  // so adding a scheme is a one-file change.
  var livery = { now: null, locked: null };
  function liveryDraw() {
    var lockedHere = (livery.locked && livery.locked === livery.now);
    el('livery-lock').classList.toggle('locked', !!lockedHere);
    el('livery-lock').textContent = lockedHere ? 'Locked' : 'Lock';
    var note = el('livery-note');
    note.classList.toggle('locked', !!lockedHere);
    note.textContent = lockedHere
      ? 'Locked. Every session starts in this colour.'
      : 'This session only. Lock keeps it for every future session.';
  }
  function liveryRead(d) {
    if (!el('livery').options.length && d.schemes) {
      d.schemes.forEach(function (s) {
        var o = document.createElement('option');
        o.value = s.id; o.textContent = s.label; o.title = s.why;
        el('livery').appendChild(o);
      });
    }
    livery.now = d.scheme;
    livery.locked = d.locked || null;
    el('livery').value = d.scheme;
    liveryDraw();
    if (d.message) { say(d.message, d.ok === false); }
  }
  function liverySend(lock) {
    fetch('/livery?scheme=' + encodeURIComponent(el('livery').value)
          + (lock ? '&lock=1' : ''))
      .then(function (r) { return r.json(); })
      .then(liveryRead)
      .catch(function () { say('The station did not answer.', true); });
  }
  el('livery').addEventListener('change', function () { liverySend(false); });
  el('livery-lock').addEventListener('click', function () { liverySend(true); });
  fetch('/livery').then(function (r) { return r.json(); })
    .then(liveryRead).catch(function () {});

  // ---------- the external view's angle ----------
  // Settings > Aircraft. The arrows move the camera at once so the angle
  // can be judged by eye; Lock writes it down and every future session
  // opens at it. Nothing here cares whether the aircraft is flying.
  var ANGLE_STEP = 2;            // degrees per press, and per wheel notch
  var ANGLE_MIN = -28, ANGLE_MAX = 83;   // the boom joint's own travel
  var angle = { deg: 17, locked: null, timer: null };

  function angleDraw() {
    el('angle-read').textContent = angle.deg.toFixed(0) + '\\u00b0';
    el('angle-up').disabled = angle.deg >= ANGLE_MAX;
    el('angle-down').disabled = angle.deg <= ANGLE_MIN;
    var lockedHere = (angle.locked !== null
                      && Math.abs(angle.locked - angle.deg) < 0.05);
    el('angle-lock').classList.toggle('locked', lockedHere);
    el('angle-lock').textContent = lockedHere ? 'Locked' : 'Lock';
    var note = el('angle-note');
    note.classList.toggle('locked', lockedHere);
    if (lockedHere) {
      note.textContent = 'Locked at ' + angle.deg.toFixed(0)
        + '\\u00b0. Every session opens at this angle until it is changed.';
    } else if (angle.locked !== null) {
      note.textContent = 'This session only. Locked angle is still '
        + angle.locked.toFixed(0) + '\\u00b0 - press Lock to replace it.';
    } else {
      note.textContent = 'Not locked - this session only. '
        + 'Lock keeps it for every future session.';
    }
  }

  // One request per burst. Holding an arrow down, or spinning the wheel,
  // would otherwise put a command on the wire per repeat.
  function angleSend(lock) {
    if (angle.timer) { clearTimeout(angle.timer); }
    angle.timer = setTimeout(function () {
      angle.timer = null;
      fetch('/chase_view?el=' + angle.deg + (lock ? '&lock=1' : ''))
        .then(function (r) { return r.json(); })
        .then(function (d) {
          if (typeof d.view_angle_deg === 'number') { angle.deg = d.view_angle_deg; }
          angle.locked = (typeof d.locked_deg === 'number') ? d.locked_deg : null;
          angleDraw();
          if (lock) {
            say('External view angle locked at ' + angle.deg.toFixed(0)
                + '\\u00b0 for every future session.');
          } else if (!d.sent) {
            say('The angle was set but the boom did not move - run '
                + 'tools/chase_angles_apply.py and restart the simulator.', true);
          }
        }).catch(function () { say('The station did not answer.', true); });
    }, lock ? 0 : 160);
  }

  function angleNudge(by) {
    angle.deg = Math.max(ANGLE_MIN, Math.min(ANGLE_MAX, angle.deg + by));
    angleDraw();
    angleSend(false);
  }
  el('angle-up').addEventListener('click', function () { angleNudge(ANGLE_STEP); });
  el('angle-down').addEventListener('click', function () { angleNudge(-ANGLE_STEP); });
  el('angle-lock').addEventListener('click', function () { angleSend(true); });
  // The wheel over the reading does the same, which is the gesture people
  // try first on a number with arrows beside it.
  el('angle-read').addEventListener('wheel', function (e) {
    e.preventDefault();
    angleNudge(e.deltaY < 0 ? ANGLE_STEP : -ANGLE_STEP);
  }, { passive: false });

  // Read the angle the station is actually on, rather than assuming the
  // factory one - it may already have applied a locked angle at start-up.
  fetch('/chase_view?read=1').then(function (r) { return r.json(); })
    .then(function (d) {
      if (typeof d.view_angle_deg === 'number') { angle.deg = d.view_angle_deg; }
      angle.locked = (typeof d.locked_deg === 'number') ? d.locked_deg : null;
      angleDraw();
    }).catch(function () { angleDraw(); });

  // ---------- settings, by category ----------
  el('set-tabs').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button') : null;
    if (!b) { return; }
    el('set-tabs').querySelectorAll('button').forEach(function (x) {
      x.className = (x === b) ? 'on' : '';
    });
    document.querySelectorAll('.set-pane').forEach(function (pane) {
      pane.classList.toggle('on', pane.dataset.pane === b.dataset.tab);
    });
  });

  // ---------- the flight log ----------
  function flightRow(f) {
    var when = (f.started_utc || '').replace('T', ' ').replace('+00:00', 'Z');
    var mins = Math.floor((f.duration_s || 0) / 60);
    var secs = Math.round((f.duration_s || 0) % 60);
    var nums = [
      ['time', mins + 'm ' + secs + 's'],
      ['airborne', Math.round(f.airborne_s || 0) + 's'],
      ['max alt', Math.round(f.max_alt_agl_m || 0) + ' m'],
      ['max range', Math.round(f.max_range_m || 0) + ' m'],
      ['max gs', (f.max_groundspeed_ms || 0).toFixed(1) + ' m/s']
    ];
    if (f.landing_sink_ms != null) {
      nums.push(['landing', f.landing_sink_ms.toFixed(1) + ' m/s down']);
    }
    if (f.battery_used_pct != null) {
      nums.push(['battery', f.battery_used_pct + '%']);
    }
    return '<div class="fl-row"><span class="when">' + when + '</span>'
      + '<span class="nums">'
      + nums.map(function (n) { return n[0] + ' <b>' + n[1] + '</b>'; }).join('')
      + '</span></div>';
  }

  function refreshFlightLog() {
    if (!el('win-flightlog').classList.contains('open')) { return; }
    fetch('/flight_log').then(function (r) { return r.json(); })
      .then(function (d) {
        var now = el('fl-now');
        if (d.now && d.now.recording) {
          now.className = 'fl-now live';
          now.innerText = 'Recording: ' + Math.round(d.now.duration_s) + ' s, '
            + Math.round(d.now.airborne_s) + ' s airborne, max '
            + Math.round(d.now.max_alt_agl_m) + ' m, '
            + Math.round(d.now.max_range_m) + ' m out'
            + (Object.keys(d.now.limit_breaches || {}).length
               ? '  -  OUTSIDE LIMITS: '
                 + Object.keys(d.now.limit_breaches).join(', ') : '');
        } else {
          now.className = 'fl-now';
          now.innerText = 'No flight in progress. A flight is recorded from '
            + 'ARM to DISARM, automatically.';
        }
        el('fl-list').innerHTML = (d.flights || []).map(flightRow).join('')
          || '<div class="fl-row"><span class="when">-</span>'
             + '<span class="nums">No finished flights yet.</span></div>';
        el('fl-foot').innerText = 'Written to ' + d.folder
          + ' - one folder per flight, with track.csv and summary.json.';
      }).catch(function () {});
  }
  setInterval(refreshFlightLog, 1000);
  window.gcsRefreshFlightLog = refreshFlightLog;

  // ---------- the aircraft's lights ----------
  // The same plugin the rail button uses, but told which way to go rather
  // than asked to toggle - a checkbox that only ever says "flip it" ends
  // up showing the opposite of the truth the first time anything else
  // touches the lights.
  el('lights-on').addEventListener('change', function () {
    var want = el('lights-on').checked;
    fetch('/action/aircraft_lights?on=' + (want ? '1' : '0'))
      .then(function (r) { return r.text(); })
      .then(function (text) {
        say(text, text.indexOf('not switched on') !== -1);
        // The station refuses if the lights are not in the model. Put the
        // switch back rather than leave it claiming they are on.
        if (text.indexOf('not switched on') !== -1) {
          el('lights-on').checked = false;
        }
      }).catch(function () {
        el('lights-on').checked = !want;
        say('The station did not answer.', true);
      });
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
  // Where a panel opens if it has not been dragged anywhere yet: the gap
  // between the left-hand controls and the attitude display, which is the
  // one part of the picture with nothing on it. The tapes, the heading,
  // the message, the instrument and the corner views all stay uncovered.
  function neutralSpot(win) {
    var w = win.offsetWidth || 320, h = win.offsetHeight || 260;
    var railRight = 10, band = BAND;
    var left = el('rail-left');
    if (left) { railRight = left.getBoundingClientRect().right; }
    var x = railRight + 18;
    var y = TOPBAR + 56;
    // Never off the bottom, and never under the parameter band.
    y = Math.min(y, window.innerHeight - band - h - 14);
    x = Math.min(x, window.innerWidth - w - 14);
    return { x: Math.max(8, x), y: Math.max(TOPBAR + 8, y) };
  }

  function placeWindow(win) {
    var saved = state.windows[win.id];
    var at = (saved && saved.x != null) ? saved : neutralSpot(win);
    win.style.left = Math.round(at.x) + 'px';
    win.style.top = Math.round(at.y) + 'px';
    win.style.right = 'auto';
    win.style.bottom = 'auto';
    win.style.transform = 'none';
  }

  function openWindow(id) {
    var win = el('win-' + id);
    if (!win) { return; }
    closeWindows();
    el('preflight').classList.remove('open');
    win.classList.add('open');
    placeWindow(win);
    // Fill it now rather than at the next tick: a window that opens
    // empty and populates a second later reads as broken.
    if (id === 'flightlog' && window.gcsRefreshFlightLog) {
      window.gcsRefreshFlightLog();
    }
  }

  // Dragged by the title bar, and where it is dragged to is remembered.
  function makeDraggable(win, handle) {
    if (!win || !handle) { return; }
    handle.addEventListener('mousedown', function (e) {
      if (e.target.closest('button')) { return; }
      e.preventDefault();
      var box = win.getBoundingClientRect();
      var grabX = e.clientX - box.left, grabY = e.clientY - box.top;
      win.classList.add('dragging');
      mask.style.display = 'block';
      mask.style.cursor = 'grabbing';

      function move(ev) {
        var x = Math.max(4, Math.min(window.innerWidth - box.width - 4,
                                     ev.clientX - grabX));
        var y = Math.max(TOPBAR + 2,
                         Math.min(window.innerHeight - 40, ev.clientY - grabY));
        win.style.left = Math.round(x) + 'px';
        win.style.top = Math.round(y) + 'px';
        win.style.right = 'auto';
        win.style.transform = 'none';
      }
      function drop() {
        document.removeEventListener('mousemove', move);
        document.removeEventListener('mouseup', drop);
        win.classList.remove('dragging');
        mask.style.display = 'none';
        state.windows[win.id] = { x: parseFloat(win.style.left),
                                  y: parseFloat(win.style.top) };
        save();
      }
      document.addEventListener('mousemove', move);
      document.addEventListener('mouseup', drop);
    });
  }

  document.querySelectorAll('.window').forEach(function (win) {
    makeDraggable(win, win.querySelector('.win-head'));
  });
  makeDraggable(el('preflight'), el('preflight').querySelector('.pf-head'));

  // The external view strip. It has to become fixed-position before it is
  // dragged, or the first drag jumps: left/top mean one thing inside the
  // view and another against the window.
  var strip = el('chasebar');
  if (strip) {
    var stripHandle = strip.querySelector('.striphandle');
    stripHandle.addEventListener('mousedown', function () {
      var box = strip.getBoundingClientRect();
      strip.classList.add('floating');
      strip.style.left = Math.round(box.left) + 'px';
      strip.style.top = Math.round(box.top) + 'px';
    });
    makeDraggable(strip, stripHandle);
    // Put it back where it was last left, on every load.
    var stripAt = state.windows[strip.id];
    if (stripAt && stripAt.x != null) {
      strip.classList.add('floating');
      strip.style.left = Math.round(stripAt.x) + 'px';
      strip.style.top = Math.round(stripAt.y) + 'px';
    }
  }
  document.addEventListener('click', function (e) {
    var open = e.target.closest ? e.target.closest('[data-open-win]') : null;
    if (open) { openWindow(open.dataset.openWin); return; }
    var close = e.target.closest ? e.target.closest('.win-close') : null;
    if (close) { closeWindows(); }
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    // The exit question first: if it is up, Escape answers it and nothing
    // else. Otherwise Escape would shut the panels behind the dialog and
    // leave the dialog itself sitting there.
    if (exitBox.classList.contains('open')) { askExit(false); return; }
    closeWindows();
    el('preflight').classList.remove('open');
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

  el('settings-open').addEventListener('click', function () {
    openWindow('settings');
  });

  el('pf-open').addEventListener('click', function () {
    closeWindows();
    pf.classList.add('open');
    placeWindow(pf);
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
