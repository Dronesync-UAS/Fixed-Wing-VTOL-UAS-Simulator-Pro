"""
UAV Academy GCS Pro, laid out the way QGroundControl lays out its Fly view.

WHY THIS EXISTS
---------------
Decided 13 Oct 2026, after running QGroundControl beside this station for
an afternoon. The conclusion was not that one is better than the other but
that they do different jobs:

  * QGC is the better GROUND STATION. Years of work, used operationally,
    and it is what a student will meet in the real world. Students fly on
    standard QGC.
  * This is the better TRAINING DEVICE. Failure injection, scenario
    control, weather, the checklist, the records - QGC cannot do any of
    it, and nothing off the shelf replaces it.

So the instructor's console keeps all forty-two of its controls and takes
QGC's LAYOUT, so that an instructor watching a student's QGC screen is
reading the same shapes in the same places rather than translating
between two different designs.

WHAT WAS COPIED, AND FROM WHERE
-------------------------------
Measured from a screenshot of QGC's own Fly view taken on this machine on
13 Oct 2026, not from memory:

  top bar         translucent over the map: arm state in words, vehicle
                  type, flight mode, then GPS / battery / link on the right
  left strip      the primary flight actions, icon above a small label
  right strip     the camera controls, top right
  main canvas     the map, full bleed, edge to edge
  picture-in-     bottom left, small: whatever the main canvas is not
    picture       showing. Clicking it swaps the two.
  telemetry       bottom centre, two rows of four, icon then value
  compass         bottom right, a rose with the heading beneath it

WHAT QGC HAS NO EQUIVALENT FOR
------------------------------
The instructor's own controls. They go in a drawer off the right-hand
edge, closed by default, so the resting state of the screen is QGC's and
nothing an instructor needs is more than one tap away. Putting them in the
settings window instead was tried on paper and rejected: a failure has to
be injectable while watching the aircraft, not from inside a dialog.

WHAT IS REUSED RATHER THAN REBUILT
----------------------------------
The map drawing, the attitude gauge and the control buttons are the
existing, proven code. This module supplies the element ids they already
look for - #flightpath, #fp-backdrop, #fp-alt, #fp-dist, #fp-points,
#fp-range, #fp-zoom, #limit-banner, #t-health, #view-map, and canvases of
class "hud" - so instructor_station's EXTRA_SCRIPT and flight_display
attach to this page unchanged. Nothing here re-implements them.

The classic page is still at /classic and the current console is still at
/. This one is served at /pro while it is being judged.
"""

# ---------------------------------------------------------------------------
# The page
# ---------------------------------------------------------------------------

TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>UAV Academy GCS Pro</title>
<style>
  /* QGC'S OWN PALETTE AND UNITS, taken from its source at v5.1.5 rather
     than sampled off a screenshot.

     Colours: src/QmlControls/QGCPalette.cc. The macro is
     DECLARE_QGC_COLOR(name, lightDisabled, lightEnabled, darkDisabled,
     darkEnabled), so the FOURTH value is the one a dark-themed QGC uses.

     Sizes: everything in QGC derives from two numbers, which it works out
     from the platform font - defaultFontPixelHeight and
     defaultFontPixelWidth. Measured on this machine's QGC, maximised at
     1854x1011:

       the toolbar is 66 px, and ScreenTools says toolbarHeight =
       defaultFontPixelHeight * 3            -> fh = 22
       the tool strip is 56 px, and ToolStrip.qml says width =
       defaultFontPixelWidth * 7             -> fw = 8

     Those two cross-check: _toolsMargin is defaultFontPixelWidth * 0.75 =
     6 px, and the tool strip's left edge measures 6 px. Everything below
     is expressed in them, as QGC does, so changing the pair rescales the
     console the way changing QGC's font scale rescales QGC. */
  :root {
    --fw: 8px;                      /* defaultFontPixelWidth  */
    --fh: 22px;                     /* defaultFontPixelHeight */
    --margin: 6px;                  /* fw * 0.75              */
    --radius: 4px;                  /* fw / 2                 */
    --toolbar: 66px;                /* fh * 3                 */
    --strip: 56px;                  /* fw * 7                 */

    --window: #222222;
    --window-transparent: rgba(34, 34, 34, 0.80);   /* #cc222222 */
    --window-shade: #333333;
    --window-shade-dark: #282828;
    --window-shade-light: #626262;
    --ink: #ffffff;
    --dim: #bfbfbf;                 /* colorGrey */
    --button: #626270;
    --button-border: #adadb8;
    --button-highlight: #3A9BDC;
    --good: #00e04b;                /* colorGreen  */
    --warn: #de8500;                /* colorOrange */
    --stop: #f32836;                /* colorRed    */
    --warning-text: #f85761;

    /* kept so the rest of the sheet reads unchanged */
    --panel: var(--window-transparent);
    --panel-solid: var(--window);
    --edge: rgba(255, 255, 255, 0.13);
  }
  * { box-sizing: border-box; }
  html, body {
    margin: 0; height: 100%; overflow: hidden;
    background: #0b0d11; color: var(--ink);
    font-family: -apple-system, "Segoe UI", Roboto, sans-serif;
    -webkit-font-smoothing: antialiased;
  }
  button { font-family: inherit; }

  /* ---------- the main canvas: map or camera, full bleed ---------- */
  #stage { position: absolute; inset: 0; }
  #stage > .surface { position: absolute; inset: 0; display: none; }
  #stage > .surface.on { display: block; }
  #pip > .surface { position: absolute; inset: 0; display: none; }
  #pip > .surface.on { display: block; }
  #pip .surface canvas, #pip .surface img {
    width: 100%; height: 100%; display: block; object-fit: cover;
  }
  /* The label is drawn over whichever view has just been moved in. */
  #pip .pip-label { z-index: 2; }
  #stage canvas, #stage img {
    width: 100%; height: 100%; display: block; object-fit: cover;
  }
  /* The gauge sits on top of its own camera picture and takes no clicks. */
  #stage .surface canvas.hud {
    position: absolute; inset: 0; pointer-events: none;
  }

  /* ---------- picture in picture, bottom left ---------- */
  #pip {
    position: absolute; left: 14px; bottom: 14px; width: 232px; height: 132px;
    border-radius: 10px; overflow: hidden; cursor: pointer; z-index: 20;
    border: 1px solid var(--edge); background: #000;
    box-shadow: 0 10px 30px rgba(0,0,0,0.55);
  }
  #pip .pip-label {
    position: absolute; left: 0; right: 0; bottom: 0; padding: 4px 8px;
    background: linear-gradient(transparent, rgba(0,0,0,0.75));
    font-size: 11px; letter-spacing: 0.4px; text-transform: uppercase;
  }

  /* ---------- top bar ---------- */
  /* QGC's toolbar is a SOLID band of the window colour, full width, 3 font
     heights tall - not a gradient fading into the map. Measured: rows 0-65
     of a 1011 px window are flat #222222-ish with a variance of 11, and the
     map below jumps to 29. */
  #top {
    position: absolute; top: 0; left: 0; right: 0; height: var(--toolbar);
    z-index: 40; display: flex; align-items: center;
    gap: calc(var(--fw) * 2); padding: 0 var(--margin);
    background: var(--window);
  }
  #brand {
    width: 40px; height: 40px; border-radius: 50%; border: 0; cursor: pointer;
    background: #1b2330 url('/app_icon.png') center/26px no-repeat;
    box-shadow: 0 0 0 1px var(--edge);
  }
  .state { font-size: 21px; font-weight: 600; letter-spacing: 0.2px; }
  .state.armed { color: var(--stop); }
  .state.ready { color: var(--ink); }
  .vtype { font-size: 12px; color: var(--dim); margin-left: -12px; }
  #mode {
    font-size: 19px; font-weight: 500; background: none; border: 0;
    color: var(--ink); cursor: pointer; padding: 0;
  }
  #top .spacer { flex: 1 1 auto; }
  .gauge { display: flex; align-items: center; gap: 7px; font-size: 13px; }
  .gauge .big { font-size: 17px; font-weight: 600; }
  .gauge .sub { font-size: 11px; color: var(--dim); line-height: 1.1; }
  .gauge svg { width: 22px; height: 22px; stroke: currentColor; fill: none;
               stroke-width: 1.7; stroke-linecap: round; }

  /* ---------- the two edge strips ---------- */
  /* ToolStrip.qml: radius fw/2, inner margins fw*0.4, spacing fw*0.25. */
  .strip {
    position: absolute; z-index: 35; display: flex; flex-direction: column;
    gap: calc(var(--fw) * 0.25); padding: calc(var(--fw) * 0.4);
    border-radius: var(--radius); background: var(--panel);
    border: 1px solid var(--edge); backdrop-filter: blur(6px);
  }
  /* Tool strips: width is fw*7 and they sit _toolsMargin from the edge and
     from the toolbar, as FlyViewWidgetLayer.qml anchors them. */
  #tools { left: var(--margin); top: calc(var(--toolbar) + var(--margin));
           width: var(--strip); }
  #cams  { right: var(--margin); top: calc(var(--toolbar) + var(--margin));
           width: var(--strip); }
  .strip button {
    width: 100%; border: 0; background: none; color: var(--ink);
    padding: 8px 2px 6px; border-radius: 9px; cursor: pointer;
    font-size: 10.5px; line-height: 1.15; letter-spacing: 0.2px;
    display: flex; flex-direction: column; align-items: center; gap: 4px;
  }
  .strip button svg { width: 22px; height: 22px; stroke: currentColor;
                      fill: none; stroke-width: 1.8; stroke-linecap: round;
                      stroke-linejoin: round; }
  .strip button:hover { background: rgba(255,255,255,0.1); }
  .strip button.on { background: rgba(53,199,89,0.22); color: #c9f5d6; }
  .strip button.stop { color: #ffb4ae; }
  .strip button.stop:hover { background: rgba(226,71,63,0.26); color: #fff; }
  .strip button:disabled { opacity: 0.35; cursor: default; }
  .strip .rule { height: 1px; background: var(--edge); margin: 4px 2px; }

  /* ---------- telemetry, bottom centre ---------- */
  #bottomright {
    position: absolute; right: var(--margin); bottom: var(--margin);
    z-index: 25; display: flex; align-items: flex-end;
    gap: var(--margin);
  }
  #telem {
    display: grid; grid-template-columns: repeat(4, auto);
    gap: calc(var(--fw) * 0.25) calc(var(--fw) * 2.5);
    padding: calc(var(--fw) * 0.75) calc(var(--fw) * 1.5);
    border-radius: var(--radius);
    background: var(--panel); border: 1px solid var(--edge);
    backdrop-filter: blur(6px); font-variant-numeric: tabular-nums;
  }
  #telem .cell { display: flex; align-items: baseline; gap: 7px; font-size: 15px; }
  #telem .k { font-size: 11px; color: var(--dim); min-width: 34px; }
  #telem .v { font-weight: 600; }
  #telem .u { font-size: 11px; color: var(--dim); }

  /* ---------- compass, bottom right ---------- */
  #gyrobox {
    width: calc(var(--fh) * 6); height: calc(var(--fh) * 6);
    border-radius: 50%; overflow: hidden; flex: 0 0 auto;
    background: var(--panel); border: 1px solid var(--edge);
    backdrop-filter: blur(6px);
  }
  #gyrobox canvas { width: 100%; height: 100%; display: block; }
  #rose {
    width: calc(var(--fh) * 6); height: calc(var(--fh) * 6);
    border-radius: 50%; flex: 0 0 auto;
    background: var(--panel); border: 1px solid var(--edge);
    backdrop-filter: blur(6px);
  }
  #rose canvas { width: 100%; height: 100%; display: block; }

  /* ---------- the instructor drawer ---------- */
  /* QGC has nothing like this, so it is the one place the design departs.
     Shut by default: the resting screen stays QGC's. */
  #drawer {
    position: absolute; top: 0; right: 0; bottom: 0; width: 352px; z-index: 60;
    background: var(--panel-solid); border-left: 1px solid var(--edge);
    transform: translateX(100%); transition: transform 0.16s ease-out;
    display: flex; flex-direction: column;
  }
  #drawer.open { transform: none; }
  /* Clear of the camera strip above it. Both live on the right edge, and
     at QGC's tool-strip width the tab was sitting on top of the strip and
     clipping its labels. */
  #drawer-tab {
    position: absolute; right: 100%; top: 46%; z-index: 61;
    writing-mode: vertical-rl; text-orientation: mixed;
    padding: 14px 7px; border: 1px solid var(--edge); border-right: 0;
    border-radius: 9px 0 0 9px; background: var(--panel-solid);
    color: var(--ink); font-size: 11.5px; letter-spacing: 1.6px; cursor: pointer;
    text-transform: uppercase;
  }
  #drawer .dhead {
    display: flex; align-items: center; justify-content: space-between;
    padding: 12px 14px; border-bottom: 1px solid var(--edge); font-weight: 600;
  }
  #drawer .dbody { flex: 1 1 auto; overflow-y: auto; padding: 10px 12px 18px; }
  #drawer .dclose {
    background: none; border: 0; color: var(--dim); font-size: 20px;
    cursor: pointer; line-height: 1;
  }

  /* ---------- the control buttons, as render_groups writes them ---------- */
  .group { margin-bottom: 12px; }
  .group .head, .group .sethead {
    width: 100%; text-align: left; background: none; border: 0; cursor: pointer;
    color: var(--dim); font-size: 10.5px; letter-spacing: 1.3px;
    text-transform: uppercase; padding: 8px 2px 6px;
    display: flex; justify-content: space-between; align-items: center;
  }
  .group .head.danger { color: #ff9f97; }
  .group.shut .items { display: none; }
  .group .items { display: flex; flex-direction: column; gap: 6px; }
  .items button {
    width: 100%; min-height: 34px; padding: 7px 11px; border-radius: 8px;
    border: 1px solid var(--edge); background: rgba(255,255,255,0.07);
    color: var(--ink); font-size: 13px; cursor: pointer; text-align: left;
    display: flex; align-items: center; gap: 8px;
  }
  .items button:hover { background: rgba(255,255,255,0.14); }
  .items button.danger { border-color: rgba(226,71,63,0.5); color: #ffb4ae; }
  .items button.danger:hover { background: rgba(226,71,63,0.26); color: #fff; }
  .items button.arm { border-color: rgba(53,199,89,0.5); color: #bdf0cb; }
  .items button.on { background: rgba(226,71,63,0.3); color: #fff; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #4a5565;
         flex: 0 0 auto; }
  .dot.on { background: var(--stop); box-shadow: 0 0 7px var(--stop); }
  .stack { display: flex; flex-direction: column; gap: 4px; }
  .stack label, .field label { font-size: 10.5px; color: var(--dim); }
  .field { display: flex; align-items: center; gap: 6px; }
  .param-input, select, input[type="number"], input[type="text"] {
    background: rgba(255,255,255,0.08); border: 1px solid var(--edge);
    color: var(--ink); border-radius: 7px; padding: 5px 7px; font-size: 12.5px;
    min-width: 0; width: 100%;
  }

  /* ---------- settings ---------- */
  #setback {
    position: absolute; inset: 0; z-index: 90; display: none;
    background: rgba(6,9,14,0.66); backdrop-filter: blur(2px);
  }
  #setback.open { display: flex; align-items: center; justify-content: center; }
  #setcard {
    width: min(880px, calc(100vw - 48px)); height: min(620px, calc(100vh - 64px));
    background: var(--panel-solid); border: 1px solid var(--edge);
    border-radius: 14px; display: flex; flex-direction: column; overflow: hidden;
  }
  #setcard .shead {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid var(--edge); font-weight: 600;
  }
  #setcard .sbody { flex: 1 1 auto; display: flex; min-height: 0; }
  #settabs {
    width: 182px; flex: 0 0 auto; border-right: 1px solid var(--edge);
    padding: 10px 8px; overflow-y: auto;
  }
  #settabs button {
    width: 100%; text-align: left; background: none; border: 0; cursor: pointer;
    color: var(--dim); font-size: 13px; padding: 9px 11px; border-radius: 8px;
  }
  #settabs button:hover { background: rgba(255,255,255,0.07); color: var(--ink); }
  #settabs button.on { background: rgba(255,255,255,0.13); color: var(--ink);
                       font-weight: 600; }
  #setpanes { flex: 1 1 auto; padding: 14px 16px; overflow-y: auto; }
  .pane { display: none; } .pane.on { display: block; }
  .srow { display: flex; align-items: center; justify-content: space-between;
          gap: 14px; padding: 7px 0; }
  .srow .lbl { font-size: 13px; }
  .note { font-size: 11px; color: var(--dim); line-height: 1.45; margin: 6px 0 14px; }

  /* ---------- top-bar buttons, checklist, log, exit ---------- */
  .topbtn {
    height: calc(var(--fh) * 1.6); padding: 0 calc(var(--fw) * 1.25);
    border-radius: var(--radius); cursor: pointer; font-size: 13px;
    border: 1px solid var(--button-border); background: var(--button);
    color: var(--ink); display: flex; align-items: center;
  }
  .topbtn:hover { background: var(--button-highlight); }
  .topbtn.close { padding: 0 calc(var(--fw) * 0.75); }
  .topbtn.close svg { width: 18px; height: 18px; }
  .topbtn.close:hover { background: var(--stop); border-color: var(--stop); }

  /* A sheet is a panel over the map: the checklist and the flight log.
     Not draggable on purpose - QGC's checklist is a popup too, and a
     panel an instructor has to find again mid-lesson is worse than one
     that always opens in the same place. */
  .sheet {
    position: absolute; z-index: 70; display: none; flex-direction: column;
    left: calc(var(--strip) + var(--margin) * 3);
    top: calc(var(--toolbar) + var(--margin));
    width: calc(var(--fw) * 54); max-height: 70vh;
    background: var(--window); border: 1px solid var(--edge);
    border-radius: var(--radius);
    box-shadow: 0 24px 64px rgba(0,0,0,0.7);
  }
  .sheet.open { display: flex; }
  .sheethead {
    display: flex; align-items: center; justify-content: space-between;
    padding: calc(var(--fw) * 1.25); border-bottom: 1px solid var(--edge);
    font-weight: 600;
  }
  .sheetbody { padding: calc(var(--fw) * 1.25); overflow-y: auto; }
  .sheetfoot {
    display: flex; align-items: center; justify-content: space-between;
    gap: var(--fw); margin-top: var(--fh);
  }
  .sheetfoot button {
    height: calc(var(--fh) * 1.6); padding: 0 calc(var(--fw) * 1.5);
    border-radius: var(--radius); cursor: pointer; font-size: 13px;
    border: 1px solid var(--button-border); background: var(--button);
    color: var(--ink);
  }
  .pf-item {
    display: flex; align-items: center; gap: var(--fw);
    padding: calc(var(--fw) * 0.6) 0; font-size: 13px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }
  .pf-item .pf-label { flex: 1 1 auto; }
  .pf-item .pf-detail { color: var(--dim); font-size: 11px; text-align: right; }
  .pf-item .mark {
    width: 14px; height: 14px; border-radius: 3px; flex: 0 0 auto;
    border: 1px solid var(--button-border);
  }
  .pf-item.ok .mark { background: var(--good); border-color: var(--good); }
  .pf-item.manual { cursor: pointer; }
  .pf-item.auto .mark { border-radius: 50%; }
  .logrow {
    display: flex; justify-content: space-between; gap: var(--fw);
    padding: calc(var(--fw) * 0.5) 0; font-size: 13px;
    border-bottom: 1px solid rgba(255,255,255,0.06);
  }

  /* ---------- "do you want to exit?" ---------- */
  .askback {
    position: absolute; inset: 0; z-index: 200; display: none;
    align-items: center; justify-content: center;
    background: rgba(6,9,14,0.62); backdrop-filter: blur(2px);
  }
  .askback.open { display: flex; }
  .askcard {
    width: calc(var(--fw) * 42); max-width: calc(100vw - 32px);
    padding: calc(var(--fh)) calc(var(--fw) * 2.5) calc(var(--fh) * 0.8);
    border-radius: var(--radius); background: var(--window);
    border: 1px solid var(--edge);
    box-shadow: 0 30px 80px rgba(0,0,0,0.75); text-align: center;
  }
  .asktitle { font-size: 17px; font-weight: 600; color: var(--ink); }
  .asknote { margin-top: 8px; font-size: 12px; color: var(--dim); line-height: 1.45; }
  .askrow { margin-top: 18px; display: flex; gap: 10px; justify-content: center; }
  .askrow button {
    min-width: calc(var(--fw) * 11); height: calc(var(--fh) * 1.6);
    border-radius: var(--radius); cursor: pointer; font-size: 13px;
    font-weight: 600; border: 1px solid var(--edge);
  }
  .askno { background: var(--button); color: var(--ink); }
  .askyes { background: var(--stop); color: #fff; border-color: var(--stop); }
  .askcard.going .askrow { display: none; }

  /* ---------- messages ---------- */
  #say {
    position: absolute; top: 64px; left: 50%; transform: translateX(-50%);
    z-index: 70; max-width: 620px; padding: 9px 15px; border-radius: 9px;
    background: var(--panel); border: 1px solid var(--edge); font-size: 13px;
    display: none; backdrop-filter: blur(6px);
  }
  #say.on { display: block; }
  #say.bad { border-color: rgba(226,71,63,0.6); color: #ffb4ae; }

  /* The limit strip the existing script writes into. */
  /* Empty until the existing limits script writes into it, and an empty
     rounded box over the map looks like a fault. */
  #limit-banner:empty { display: none; }
  #limit-banner {
    position: absolute; left: 10px; bottom: 156px; z-index: 25;
    padding: 6px 11px; border-radius: 8px; background: var(--panel);
    border: 1px solid var(--edge); font-size: 11.5px; color: var(--dim);
    backdrop-filter: blur(6px);
  }
  /* Kept for the existing scripts, which write into them. Not shown: the
     same figures are in the telemetry block and the backdrop label. */
  .offscreen { position: absolute; left: -9999px; top: -9999px; }
__EXTRA_STYLE__
</style>
</head>
<body>

<!-- the main canvas -->
<!-- THE ATTITUDE GAUGE GOES OVER THE CAMERAS, NOT OVER THE MAP. The first
     build put one canvas across the whole stage, and the gauge then drew
     its heading tape straight through the top bar and its tapes across the
     satellite view. QGC does not put an attitude indicator over its map
     either. So each camera surface carries its own, and the map carries
     none - which is also what the existing console does. -->
<!-- ONE ELEMENT PER VIEW, MOVED. The four views are built once and moved
     between the stage and the picture-in-picture - they are not built twice.
     Each MJPEG feed is an HTTP connection the station has to encode frames
     for, so a second <img> on the same feed doubles the camera work for a
     picture nobody is looking at. The map is the same: there is one
     #flightpath canvas, because the existing script draws into that id and
     a second canvas would simply stay blank. -->
<div id="stage"></div>
<div id="pip" title="Click to swap this with the main picture">
  <div class="pip-label" id="pip-label">Nose</div>
</div>

<div id="viewstore" style="display: none">
  <div class="surface" id="v-map" data-name="Map"><canvas id="flightpath"></canvas></div>
  <div class="surface" id="v-nose" data-name="Nose">
    <img src="/video_feed" alt="Nose camera">
    <canvas class="hud"></canvas>
  </div>
  <div class="surface" id="v-chase" data-name="External">
    <img src="/chase_feed" alt="External view">
    <canvas class="hud"></canvas>
  </div>
  <div class="surface" id="v-payload" data-name="Payload">
    <img src="/payload_feed" alt="Payload camera">
    <canvas class="hud"></canvas>
  </div>
</div>

<div id="top">
  <button id="brand" title="Settings" aria-label="Settings"></button>
  <span class="state ready" id="armstate">&mdash;</span>
  <span class="vtype" id="vtype">VTOL</span>
  <button id="mode" title="Flight mode">&mdash;</button>
  <span class="spacer"></span>

  <span class="gauge" title="GPS satellites and horizontal accuracy">
    <svg viewBox="0 0 24 24"><path d="M5 15 L13 7"></path>
      <rect x="2.5" y="12.5" width="5" height="5" rx="1" transform="rotate(-45 5 15)"></rect>
      <rect x="10.5" y="4.5" width="5" height="5" rx="1" transform="rotate(-45 13 7)"></rect>
      <path d="M14 16a4 4 0 0 0-4-4"></path><path d="M18 18a8 8 0 0 0-8-8"></path></svg>
    <span class="big" id="g-sats">-</span>
  </span>
  <span class="gauge" title="Battery remaining">
    <svg viewBox="0 0 24 24"><rect x="2" y="8" width="17" height="9" rx="2"></rect>
      <path d="M21.5 11.5v2"></path></svg>
    <span class="big" id="g-batt">-</span>
  </span>
  <span class="gauge" title="Telemetry age, camera frame rate and visual response time (CAP 722B 5.2(d))">
    <svg viewBox="0 0 24 24"><path d="M12 7v5l3 2"></path>
      <circle cx="12" cy="12" r="9"></circle></svg>
    <span class="big" id="g-link">-</span>
  </span>
  <span class="gauge" id="t-health" style="display:none"></span>

  <!-- The instructor's own top-bar buttons. QGC has no equivalent for the
       first two; the X is where every application keeps close. -->
  <button class="topbtn" id="open-checklist" title="Pre-flight checklist">Checklist</button>
  <button class="topbtn" id="open-log" title="Flight log">Log</button>
  <button class="topbtn close" id="exit-open" title="Exit the GCS" aria-label="Exit">
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2"
         stroke-linecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18"></path>
    </svg>
  </button>
</div>

<!-- Do you want to exit? Same contract as the other console: No is the
     default in every sense, and only the Yes button sends anything. -->
<div id="exit-ask" class="askback" role="dialog" aria-modal="true">
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

<!-- The checklist and the flight log, as panels over the map. -->
<div class="sheet" id="sheet-checklist">
  <div class="sheethead"><span>Pre-flight checklist</span>
    <button class="dclose" data-sheet="checklist">&times;</button></div>
  <div class="sheetbody">
    <div id="pf-items"></div>
    <div class="sheetfoot">
      <span id="pf-summary" class="note"></span>
      <button id="pf-complete">Start the exercise</button>
    </div>
  </div>
</div>

<div class="sheet" id="sheet-log">
  <div class="sheethead"><span>Flight log</span>
    <button class="dclose" data-sheet="log">&times;</button></div>
  <div class="sheetbody"><div id="log-body"></div></div>
</div>

<div id="say"></div>

<!-- primary flight actions, QGC's left strip -->
<div class="strip" id="tools">
  <button data-send="arm" title="Arm the aircraft">
    <svg viewBox="0 0 24 24"><path d="M12 3v9"></path>
      <path d="M6.5 7.5a7.5 7.5 0 1 0 11 0"></path></svg>Arm</button>
  <button data-send="takeoff" title="Take off to the climb height">
    <svg viewBox="0 0 24 24"><path d="M12 20V6"></path>
      <path d="M7 11l5-5 5 5"></path><path d="M5 21h14"></path></svg>Takeoff</button>
  <button data-send="hold" title="Hold position">
    <svg viewBox="0 0 24 24"><rect x="6" y="5" width="4" height="14" rx="1"></rect>
      <rect x="14" y="5" width="4" height="14" rx="1"></rect></svg>Hold</button>
  <button data-send="rtl" title="Return to launch">
    <svg viewBox="0 0 24 24"><path d="M9 14l-4-4 4-4"></path>
      <path d="M5 10h9a5 5 0 0 1 0 10h-3"></path></svg>Return</button>
  <button data-send="land" title="Land here">
    <svg viewBox="0 0 24 24"><path d="M12 4v14"></path>
      <path d="M7 13l5 5 5-5"></path><path d="M5 21h14"></path></svg>Land</button>
  <div class="rule"></div>
  <button data-send="disarm" class="stop" title="Disarm">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9"></circle>
      <path d="M8 12h8"></path></svg>Disarm</button>
</div>

<!-- cameras and views, QGC's right strip -->
<div class="strip" id="cams">
  <button data-stage="map" title="Satellite map">
    <svg viewBox="0 0 24 24"><path d="M9 4L3 6v14l6-2 6 2 6-2V4l-6 2z"></path>
      <path d="M9 4v14M15 6v14"></path></svg>Map</button>
  <button data-stage="nose" title="Nose camera">
    <svg viewBox="0 0 24 24"><path d="M3 7h13v10H3z"></path>
      <path d="M16 11l5-3v8l-5-3"></path></svg>Nose</button>
  <button data-stage="chase" title="External view">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="3"></circle>
      <path d="M4 7h4l2-2h4l2 2h4v12H4z"></path></svg>External</button>
  <button data-stage="payload" title="Payload gimbal">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="10" r="4"></circle>
      <path d="M5 4h14v16H5z"></path></svg>Payload</button>
  <div class="rule"></div>
  <button id="btn-views" title="Where the external view looks from">
    <svg viewBox="0 0 24 24"><path d="M12 5v14M5 12h14"></path>
      <circle cx="12" cy="12" r="9"></circle></svg>Angles</button>
  <button id="btn-gimbal" title="Point the payload camera">
    <svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="7"></circle>
      <path d="M12 2v3M12 19v3M2 12h3M19 12h3"></path></svg>Gimbal</button>
</div>

<!-- the external view's six angles, shown under the strip when asked for -->
<div class="strip" id="angles" style="right: 90px; top: 68px; width: 92px; display: none">
  <button data-chase="behind" class="on">Behind</button>
  <button data-chase="port">Left</button>
  <button data-chase="starboard">Right</button>
  <button data-chase="nose">Front</button>
  <button data-chase="top">Top</button>
  <button data-chase="low">Low</button>
</div>

<!-- the gimbal, same place -->
<div class="strip" id="gimbal" style="right: 90px; top: 68px; width: 150px; display: none">
  <div class="field"><label>Pan</label>
    <input type="range" id="gb-pan" min="-180" max="180" step="1" value="0"></div>
  <div class="field"><label>Tilt</label>
    <input type="range" id="gb-tilt" min="-30" max="90" step="1" value="30"></div>
  <div class="field"><label>Zoom</label>
    <input type="range" id="gb-zoom" min="1" max="12" step="0.5" value="1"></div>
  <button id="gb-centre">Centre</button>
</div>

<!-- BOTTOM RIGHT, AS ONE ROW. FlyViewBottomRightRowLayout.qml puts the
     TelemetryValuesBar and the FlyViewInstrumentPanel side by side,
     anchored bottom-right - not telemetry in the centre with the compass
     off on its own, which is what this had before the layout was read
     from QGC's source. The attitude gauge is ours, and sits between them
     because attitude and heading are read together. -->
<div id="bottomright">
<div id="telem">
  <div class="cell"><span class="k">ALT</span><span class="v" id="t-alt">0.0</span><span class="u">m</span></div>
  <div class="cell"><span class="k">GS</span><span class="v" id="t-gs">0.0</span><span class="u">m/s</span></div>
  <div class="cell"><span class="k">AIR</span><span class="v" id="t-air">0.0</span><span class="u">m/s</span></div>
  <div class="cell"><span class="k">TIME</span><span class="v" id="t-time">--:--</span></div>
  <div class="cell"><span class="k">VS</span><span class="v" id="t-vs">0.0</span><span class="u">m/s</span></div>
  <div class="cell"><span class="k">HDG</span><span class="v" id="t-hdg">000</span><span class="u">&deg;</span></div>
  <div class="cell"><span class="k">HOME</span><span class="v" id="t-home">0</span><span class="u">m</span></div>
  <div class="cell"><span class="k">THR</span><span class="v" id="t-thr">0</span><span class="u">%</span></div>
</div>

<!-- Attitude beside heading, which is the pairing every panel uses: how
     the aircraft is sitting, and which way it is pointing, read together.
     The gauge itself is attitude_gauge.py - the same one the other console
     draws, not a second copy. -->
<div id="gyrobox"><canvas id="gyro" width="184" height="184"></canvas></div>
<div id="rose"><canvas id="rose-c" width="264" height="264"></canvas></div>
</div>

<div id="limit-banner"></div>

<!-- the instructor's own controls: everything QGC has no equivalent for -->
<div id="drawer">
  <button id="drawer-tab">Instructor</button>
  <div class="dhead"><span>Instructor</span>
    <button class="dclose" id="drawer-close">&times;</button></div>
  <div class="dbody">__INSTRUCTOR__</div>
</div>

<!-- settings: every control, by category, including the ones in the drawer -->
<div id="setback">
  <div id="setcard">
    <div class="shead"><span>Settings</span>
      <button class="dclose" id="set-close">&times;</button></div>
    <div class="sbody">
      <div id="settabs">
        <button data-pane="display" class="on">Display</button>
        <button data-pane="aircraft">Aircraft</button>
        <button data-pane="environment">Environment</button>
        <button data-pane="mission">Mission</button>
        <button data-pane="session">Session</button>
        <button data-pane="all">All controls</button>
      </div>
      <div id="setpanes">
        <div class="pane on" data-pane="display">
          <div class="srow"><span class="lbl">Attitude overlay</span>
            <input type="checkbox" id="hud-on" checked></div>
          <div class="srow"><span class="lbl">Warning sounds</span>
            <input type="checkbox" id="alarm-on" checked></div>
          <div class="srow"><span class="lbl">Spoken callouts</span>
            <input type="checkbox" id="voice-on" checked></div>
          <div class="srow"><span class="lbl">Camera view</span>
            <select id="viewmode">
              <option value="normal">Daylight</option>
              <option value="ir">Infrared (white hot)</option>
              <option value="ir_black">Infrared (black hot)</option>
            </select></div>
          <!-- Fuselage colour. Runtime, no restart - see aircraft_livery.py. -->
          <div class="srow"><span class="lbl">Fuselage</span>
            <span><select id="livery"></select>
              <button id="livery-lock">Lock</button></span></div>
          <div class="note" id="livery-note">Not locked &mdash; this session only.</div>
          <div class="srow"><span class="lbl">External view angle</span>
            <span><button id="angle-down">&#9660;</button>
              <b id="angle-read">17&deg;</b>
              <button id="angle-up">&#9650;</button>
              <button id="angle-lock">Lock</button></span></div>
          <div class="note" id="angle-note">Not locked &mdash; this session only.</div>
        </div>
        <div class="pane" data-pane="aircraft">__SETTINGS_AIRCRAFT__</div>
        <div class="pane" data-pane="environment">__SETTINGS_ENVIRONMENT__</div>
        <div class="pane" data-pane="mission">__SETTINGS_MISSION__</div>
        <div class="pane" data-pane="session">__SETTINGS_SESSION__</div>
        <div class="pane" data-pane="all">__SETTINGS_ALL__</div>
      </div>
    </div>
  </div>
</div>

<!-- The existing map script writes into these. They are real elements with
     real values; this layout simply shows the same figures elsewhere. -->
<div class="offscreen">
  <span id="fp-backdrop"></span><span id="fp-alt"></span><span id="fp-dist"></span>
  <span id="fp-points"></span><span id="fp-range"></span>
  <input id="fp-zoom" type="range" min="1" max="8" value="1">
  <div id="view-map"></div>
</div>

<script>__CONSOLE_SCRIPT__</script>
__EXTRA_SCRIPT__
</body>
</html>
"""


SCRIPT = """
(function () {
  'use strict';
  function el(id) { return document.getElementById(id); }

  // ---------- messages ----------
  var sayTimer = null;
  function say(text, bad) {
    var box = el('say');
    box.textContent = text;
    box.className = 'on' + (bad ? ' bad' : '');
    if (sayTimer) { clearTimeout(sayTimer); }
    sayTimer = setTimeout(function () { box.className = ''; }, bad ? 7000 : 3500);
  }
  window.gcsSay = say;

  // ---------- running a control ----------
  // The same contract the existing console uses, because the buttons are
  // written by the same render_groups() on the station's side: collect any
  // .param-input belonging to this plugin, then GET /action/<id>.
  function send(id) {
    var params = new URLSearchParams();
    document.querySelectorAll('.param-input[data-plugin="' + id + '"]')
      .forEach(function (e) { params.append(e.dataset.param, e.value); });
    var qs = params.toString();
    return fetch('/action/' + id + (qs ? '?' + qs : ''))
      .then(function (r) { return r.text(); })
      .then(function (text) {
        say(text, /not sent|fail|refus|cannot|error/i.test(text));
        refreshFailures();
        return text;
      })
      .catch(function () { say('The station did not answer.', true); });
  }
  window.send = send;

  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-send]') : null;
    if (b) { send(b.dataset.send); }
  });

  // ---------- which picture is on the stage ----------
  // QGC shows one big and one small, and clicking the small one swaps
  // them. The four surfaces exist once each; only their class moves.
  var VIEWS = ['map', 'nose', 'chase', 'payload'];
  var LABEL = { map: 'Map', nose: 'Nose', chase: 'External', payload: 'Payload' };
  var stageView = 'map', pipView = 'nose';

  function applyViews() {
    var stage = el('stage'), pip = el('pip'), store = el('viewstore');
    VIEWS.forEach(function (v) {
      var box = el('v-' + v);
      if (!box) { return; }
      var where = (v === stageView) ? stage : (v === pipView ? pip : store);
      if (box.parentNode !== where) { where.appendChild(box); }
      box.classList.toggle('on', v === stageView || v === pipView);
    });
    // The label has to stay the last child of the pip, or the view that
    // was just moved in covers it.
    pip.appendChild(el('pip-label'));
    el('pip-label').textContent = LABEL[pipView];
    document.querySelectorAll('#cams button[data-stage]').forEach(function (b) {
      b.classList.toggle('on', b.dataset.stage === stageView);
    });
    // The map canvas is sized from the box it is in, and that box has just
    // changed by a factor of six. Without an immediate redraw the track
    // stays drawn at the old scale until the next tick - up to a second of
    // a map that is visibly wrong.
    if (window.gcsRedraw) { window.gcsRedraw(); }
  }
  function setStage(v) {
    if (v === stageView) { return; }
    if (v === pipView) { pipView = stageView; }
    stageView = v;
    applyViews();
  }
  document.querySelectorAll('#cams button[data-stage]').forEach(function (b) {
    b.addEventListener('click', function () { setStage(b.dataset.stage); });
  });
  el('pip').addEventListener('click', function () { setStage(pipView); });

  // ---------- the strips that drop out of the right-hand one ----------
  function toggleStrip(which) {
    ['angles', 'gimbal'].forEach(function (name) {
      var box = el(name);
      box.style.display = (name === which && box.style.display === 'none')
                          ? 'flex' : 'none';
    });
  }
  el('btn-views').addEventListener('click', function () { toggleStrip('angles'); });
  el('btn-gimbal').addEventListener('click', function () { toggleStrip('gimbal'); });

  el('angles').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button[data-chase]') : null;
    if (!b) { return; }
    fetch('/chase_view?preset=' + b.dataset.chase)
      .then(function (r) { return r.json(); })
      .then(function (d) {
        el('angles').querySelectorAll('button').forEach(function (x) {
          x.classList.toggle('on', x.dataset.chase === d.preset);
        });
        say(d.sent ? ('External view: ' + b.textContent + '.')
                   : ('External view ' + b.textContent + ' NOT sent - run '
                      + 'tools/chase_angles_apply.py and restart the simulator.'),
            !d.sent);
      }).catch(function () { say('The station did not answer.', true); });
  });

  // ---------- the gimbal ----------
  var gimbalTimer = null;
  function gimbalSend() {
    if (gimbalTimer) { clearTimeout(gimbalTimer); }
    gimbalTimer = setTimeout(function () {
      gimbalTimer = null;
      fetch('/payload_point?pan=' + el('gb-pan').value
            + '&tilt=' + el('gb-tilt').value)
        .catch(function () { say('The station did not answer.', true); });
    }, 90);
  }
  el('gb-pan').addEventListener('input', gimbalSend);
  el('gb-tilt').addEventListener('input', gimbalSend);
  el('gb-zoom').addEventListener('input', function () {
    fetch('/payload_zoom?to=' + el('gb-zoom').value).catch(function () {});
  });
  el('gb-centre').addEventListener('click', function () {
    el('gb-pan').value = 0; el('gb-tilt').value = 30; gimbalSend();
  });

  // ---------- the drawer ----------
  function drawer(open) { el('drawer').classList.toggle('open', open); }
  el('drawer-tab').addEventListener('click', function () {
    drawer(!el('drawer').classList.contains('open'));
  });
  el('drawer-close').addEventListener('click', function () { drawer(false); });

  // Collapsible sections inside it, as on the existing console.
  el('drawer').addEventListener('click', function (e) {
    var head = e.target.closest ? e.target.closest('.head') : null;
    if (head) { head.parentNode.classList.toggle('shut'); }
  });

  // ---------- settings ----------
  function settings(open) { el('setback').classList.toggle('open', open); }
  el('brand').addEventListener('click', function () { settings(true); });
  el('set-close').addEventListener('click', function () { settings(false); });
  el('setback').addEventListener('mousedown', function (e) {
    if (e.target === el('setback')) { settings(false); }
  });
  el('settabs').addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('button') : null;
    if (!b) { return; }
    el('settabs').querySelectorAll('button').forEach(function (x) {
      x.classList.toggle('on', x === b);
    });
    document.querySelectorAll('.pane').forEach(function (p) {
      p.classList.toggle('on', p.dataset.pane === b.dataset.pane);
    });
  });
  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') { return; }
    // In the order they sit on top of each other, and one per press: a
    // single Escape that shut the dialog AND the panels behind it would
    // leave the console rearranged without the instructor asking.
    if (el('exit-ask').classList.contains('open')) { askExit(false); return; }
    if (el('setback').classList.contains('open')) { settings(false); return; }
    var openSheet = document.querySelector('.sheet.open');
    if (openSheet) { openSheet.classList.remove('open'); return; }
    if (el('drawer').classList.contains('open')) { drawer(false); }
  });

  el('viewmode').addEventListener('change', function () {
    fetch('/view_mode?mode=' + el('viewmode').value)
      .then(function (r) { return r.text(); })
      .then(function (t) { say(t); }).catch(function () {});
  });

  // ---------- the checklist and the flight log ----------
  function sheet(name, open) {
    document.querySelectorAll('.sheet').forEach(function (el2) {
      el2.classList.remove('open');
    });
    if (open) { el('sheet-' + name).classList.add('open'); }
  }
  document.addEventListener('click', function (e) {
    var close = e.target.closest ? e.target.closest('[data-sheet]') : null;
    if (close) { sheet(close.dataset.sheet, false); }
  });

  function drawChecklist(d) {
    var box = el('pf-items');
    box.innerHTML = '';
    // The field names are preflight.state()'s own: key, kind ("auto" or
    // "manual"), label, ok, detail. ok is null while an automatic item has
    // nothing to report yet, which is not the same as false.
    (d.items || []).forEach(function (item) {
      var row = document.createElement('div');
      row.className = 'pf-item ' + (item.kind === 'manual' ? 'manual' : 'auto')
                      + (item.ok ? ' ok' : '');
      row.dataset.item = item.key;
      row.innerHTML = '<span class="mark"></span>'
                    + '<span class="pf-label">' + item.label + '</span>'
                    + '<span class="pf-detail">' + (item.detail || '') + '</span>';
      box.appendChild(row);
    });
    var left = (d.outstanding || []).length;
    el('pf-summary').textContent = left
      ? (left + ' item(s) not green: ' + d.outstanding.join(', '))
      : 'Every item is green.';
  }
  function refreshChecklist() {
    if (!el('sheet-checklist').classList.contains('open')) { return; }
    fetch('/preflight').then(function (r) { return r.json(); })
      .then(drawChecklist).catch(function () {});
  }
  el('open-checklist').addEventListener('click', function () {
    sheet('checklist', true);
    refreshChecklist();
  });
  // A manual item is ticked by clicking it, as on the other console.
  el('pf-items').addEventListener('click', function (e) {
    var row = e.target.closest ? e.target.closest('.pf-item.manual') : null;
    if (!row) { return; }
    var on = row.classList.contains('ok') ? '0' : '1';
    fetch('/preflight_tick?item=' + encodeURIComponent(row.dataset.item)
          + '&on=' + on)
      .then(function (r) { return r.json(); })
      .then(drawChecklist).catch(function () {});
  });
  el('pf-complete').addEventListener('click', function () {
    fetch('/preflight_complete').then(function (r) { return r.json(); })
      .then(function (d) {
        drawChecklist(d);
        sheet('checklist', false);
        say(d.ready
            ? 'Checklist complete - all items green. Written to the record.'
            : 'Exercise started with ' + (d.outstanding || []).length
              + ' item(s) not green. Written to the record.', !d.ready);
      }).catch(function () { say('The station did not answer.', true); });
  });
  setInterval(refreshChecklist, 1000);

  el('open-log').addEventListener('click', function () {
    sheet('log', true);
    fetch('/flight_log').then(function (r) { return r.json(); })
      .then(function (d) {
        var box = el('log-body');
        box.innerHTML = '';
        var now = d.now || {};
        var head = document.createElement('div');
        head.className = 'note';
        head.textContent = now.recording
          ? 'Recording now.' : 'Not recording.';
        box.appendChild(head);
        (d.flights || []).forEach(function (f) {
          var row = document.createElement('div');
          row.className = 'logrow';
          var when = (f.started_utc || '').replace('T', ' ').replace('+00:00', 'Z');
          row.innerHTML = '<span>' + when + '</span><span>'
                        + (f.world || '') + '</span>';
          box.appendChild(row);
        });
        if (!(d.flights || []).length) {
          var none = document.createElement('div');
          none.className = 'note';
          none.textContent = 'No flights recorded yet. Folder: ' + (d.folder || '');
          box.appendChild(none);
        }
      }).catch(function () { say('The station did not answer.', true); });
  });

  // ---------- exit ----------
  var exitBox = el('exit-ask');
  function askExit(show) {
    exitBox.classList.toggle('open', show);
    if (show) { el('exit-no').focus(); }
  }
  el('exit-open').addEventListener('click', function () { askExit(true); });
  el('exit-no').addEventListener('click', function () { askExit(false); });
  exitBox.addEventListener('mousedown', function (e) {
    if (e.target === exitBox) { askExit(false); }
  });
  el('exit-yes').addEventListener('click', function () {
    exitBox.querySelector('.askcard').classList.add('going');
    el('exit-title').textContent = 'Closing down\u2026';
    exitBox.querySelector('.asknote').textContent =
      'Stopping the simulator and the station. This window can be closed.';
    fetch('/exit', { method: 'POST' }).catch(function () {});
    setTimeout(function () {
      el('exit-title').textContent = 'Closed.';
      exitBox.querySelector('.asknote').textContent =
        'Start them again with the UAV Academy GCS Pro icon.';
      try { window.close(); } catch (err) { /* nothing to do */ }
    }, 2500);
  });

  // ---------- the fuselage colour ----------
  var livery = { now: null, locked: null };
  function liveryDraw() {
    var here = (livery.locked && livery.locked === livery.now);
    el('livery-lock').textContent = here ? 'Locked' : 'Lock';
    el('livery-note').textContent = here
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
    livery.now = d.scheme; livery.locked = d.locked || null;
    el('livery').value = d.scheme; liveryDraw();
    if (d.message) { say(d.message, d.ok === false); }
  }
  function liverySend(lock) {
    fetch('/livery?scheme=' + encodeURIComponent(el('livery').value)
          + (lock ? '&lock=1' : ''))
      .then(function (r) { return r.json(); }).then(liveryRead)
      .catch(function () { say('The station did not answer.', true); });
  }
  el('livery').addEventListener('change', function () { liverySend(false); });
  el('livery-lock').addEventListener('click', function () { liverySend(true); });
  fetch('/livery').then(function (r) { return r.json(); })
    .then(liveryRead).catch(function () {});

  // ---------- the external view's angle (same contract as the console) ----------
  var ANGLE_STEP = 2, ANGLE_MIN = -28, ANGLE_MAX = 83;
  var angle = { deg: 17, locked: null, timer: null };
  function angleDraw() {
    el('angle-read').textContent = angle.deg.toFixed(0) + '\\u00b0';
    el('angle-up').disabled = angle.deg >= ANGLE_MAX;
    el('angle-down').disabled = angle.deg <= ANGLE_MIN;
    var here = (angle.locked !== null && Math.abs(angle.locked - angle.deg) < 0.05);
    el('angle-lock').textContent = here ? 'Locked' : 'Lock';
    el('angle-note').textContent = here
      ? ('Locked at ' + angle.deg.toFixed(0) + '\\u00b0. Every session opens at it.')
      : 'Not locked - this session only.';
  }
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
          if (lock) { say('External view angle locked at '
                          + angle.deg.toFixed(0) + '\\u00b0.'); }
        }).catch(function () { say('The station did not answer.', true); });
    }, lock ? 0 : 160);
  }
  el('angle-up').addEventListener('click', function () {
    angle.deg = Math.min(ANGLE_MAX, angle.deg + ANGLE_STEP); angleDraw(); angleSend(false); });
  el('angle-down').addEventListener('click', function () {
    angle.deg = Math.max(ANGLE_MIN, angle.deg - ANGLE_STEP); angleDraw(); angleSend(false); });
  el('angle-lock').addEventListener('click', function () { angleSend(true); });
  fetch('/chase_view?read=1').then(function (r) { return r.json(); })
    .then(function (d) {
      if (typeof d.view_angle_deg === 'number') { angle.deg = d.view_angle_deg; }
      angle.locked = (typeof d.locked_deg === 'number') ? d.locked_deg : null;
      angleDraw();
    }).catch(function () { angleDraw(); });

  // ---------- telemetry ----------
  function pad(n, w) { var s = String(Math.round(n)); while (s.length < w) { s = '0' + s; } return s; }
  function clock(s) {
    if (s == null) { return '--:--'; }
    var m = Math.floor(s / 60), r = Math.floor(s % 60);
    return pad(m, 2) + ':' + pad(r, 2);
  }
  // VERTICAL SPEED is not in the telemetry feed, so it is worked out from
  // the altitude that is - the same way the other console does it. A field
  // that reads 0.0 for ever is worse than no field.
  var armedAt = null, lastAlt = null, lastAltAt = null;
  setInterval(function () {
    var d = window.gcsTelemetry;
    if (!d || d.altitude_m === undefined) { return; }
    var now = Date.now();
    if (lastAlt !== null && now > lastAltAt) {
      var vs = (d.altitude_m - lastAlt) / ((now - lastAltAt) / 1000);
      el('t-vs').textContent = (Math.abs(vs) < 0.05 ? 0 : vs).toFixed(1);
    }
    lastAlt = d.altitude_m; lastAltAt = now;
  }, 500);

  function refreshTelemetry() {
    fetch('/telemetry').then(function (r) { return r.json(); }).then(function (d) {
      window.gcsTelemetry = d;
      var armed = !!d.armed;
      var st = el('armstate');
      st.textContent = armed ? 'Armed'
        : (d.arm_ready === false ? 'Not ready' : 'Ready');
      st.className = 'state ' + (armed ? 'armed' : 'ready');
      el('mode').textContent = d.mode || '-';
      // vtol_state is what the feed carries - there is no vehicle_type.
      // It says which half of a VTOL is flying, which is worth seeing: a
      // transition that has not completed is a common lesson moment.
      el('vtype').textContent = d.vtol_state ? ('VTOL \u00b7 ' + d.vtol_state)
                                             : 'VTOL';

      el('g-sats').textContent = (d.satellites != null) ? d.satellites : '-';
      el('g-batt').textContent = (d.battery_pct != null)
        ? Math.round(d.battery_pct) + '%' : '-';

      el('t-alt').textContent = (d.altitude_m != null) ? d.altitude_m.toFixed(1) : '0.0';
      el('t-gs').textContent = (d.groundspeed_ms != null) ? d.groundspeed_ms.toFixed(1) : '0.0';
      el('t-air').textContent = (d.airspeed_ms != null) ? d.airspeed_ms.toFixed(1) : '0.0';
      el('t-hdg').textContent = pad(d.heading_deg || 0, 3);
      el('t-home').textContent = (d.range_from_home_m != null)
        ? Math.round(d.range_from_home_m) : '0';
      el('t-thr').textContent = (d.throttle_pct != null)
        ? Math.round(d.throttle_pct) : '0';

      // FLIGHT TIME is not in the feed either. Timed from the moment the
      // aircraft arms, which is what an instructor means by it, and reset
      // on disarm so the next exercise starts from zero.
      if (d.armed && armedAt === null) { armedAt = Date.now(); }
      if (!d.armed) { armedAt = null; }
      el('t-time').textContent = armedAt
        ? clock((Date.now() - armedAt) / 1000) : '--:--';
    }).catch(function () {});
  }
  function refreshLink() {
    fetch('/health').then(function (r) { return r.json(); }).then(function (d) {
      var age = (d.telemetry_age_s != null) ? d.telemetry_age_s : null;
      var txt = (age == null) ? '-' : (age < 1 ? '<1s' : Math.round(age) + 's');
      // CAP 722B 5.2(d) wants the frame rate AND the visual response time of
      // any display. They are only shown once a feed is running - a made-up
      // "0 fps / 0 ms" when nothing is streaming would be worse than blank.
      if (d.camera_fps > 0) {
        txt += ' \u00b7 ' + Math.round(d.camera_fps) + 'fps';
        if (d.camera_response_ms > 0) {
          txt += ' \u00b7 ' + Math.round(d.camera_response_ms) + 'ms';
        }
      }
      el('g-link').textContent = txt;
    }).catch(function () { el('g-link').textContent = '-'; });
  }
  function refreshFailures() {
    fetch('/failure_status').then(function (r) { return r.json(); })
      .then(function (d) {
        Object.keys(d).forEach(function (id) {
          var dot = el('dot-' + id);
          if (dot) { dot.classList.toggle('on', !!d[id]); }
          var b = el('btn-' + id);
          if (b) { b.classList.toggle('on', !!d[id]); }
        });
      }).catch(function () {});
  }

  // ---------- the compass rose ----------
  var rose = el('rose-c'), rctx = rose.getContext('2d');
  function drawRose() {
    var w = rose.width, h = rose.height, cx = w / 2, cy = h / 2, R = w / 2 - 16;
    var hdg = (window.gcsTelemetry && window.gcsTelemetry.heading_deg) || 0;
    rctx.clearRect(0, 0, w, h);
    rctx.save();
    rctx.translate(cx, cy);
    // The card turns, the aircraft stays put - which is how QGC's reads,
    // and how every compass on an aircraft reads.
    rctx.rotate(-hdg * Math.PI / 180);
    rctx.strokeStyle = 'rgba(255,255,255,0.35)';
    rctx.lineWidth = 2;
    for (var d = 0; d < 360; d += 15) {
      var major = (d % 90 === 0), a = d * Math.PI / 180;
      var r1 = R - (major ? 16 : 8);
      rctx.beginPath();
      rctx.moveTo(Math.sin(a) * r1, -Math.cos(a) * r1);
      rctx.lineTo(Math.sin(a) * R, -Math.cos(a) * R);
      rctx.stroke();
    }
    rctx.fillStyle = '#fff';
    rctx.font = 'bold 20px -apple-system, sans-serif';
    rctx.textAlign = 'center'; rctx.textBaseline = 'middle';
    [['N', 0], ['E', 90], ['S', 180], ['W', 270]].forEach(function (p) {
      var a = p[1] * Math.PI / 180, r = R - 30;
      rctx.save();
      rctx.translate(Math.sin(a) * r, -Math.cos(a) * r);
      rctx.rotate(hdg * Math.PI / 180);
      rctx.fillText(p[0], 0, 0);
      rctx.restore();
    });
    rctx.restore();

    rctx.fillStyle = '#e2473f';
    rctx.beginPath();
    rctx.moveTo(cx, cy - 34); rctx.lineTo(cx - 17, cy + 24);
    rctx.lineTo(cx, cy + 13); rctx.lineTo(cx + 17, cy + 24);
    rctx.closePath(); rctx.fill();

    rctx.fillStyle = '#fff';
    rctx.font = '600 22px -apple-system, sans-serif';
    rctx.fillText(pad(hdg, 3) + '\\u00b0', cx, cy + 50);
  }

  // ---------- go ----------
  applyViews();
  refreshTelemetry(); refreshLink(); refreshFailures();
  setInterval(refreshTelemetry, 400);
  setInterval(refreshLink, 1000);
  setInterval(refreshFailures, 1500);
  setInterval(drawRose, 120);
  // The attitude gauge, from attitude_gauge.py. It reads window.gcsTelemetry
  // itself, so there is nothing to pass it.
  setInterval(function () {
    if (window.gcsDrawAttitude) { window.gcsDrawAttitude('gyro', 132); }
  }, 120);
})();
"""
