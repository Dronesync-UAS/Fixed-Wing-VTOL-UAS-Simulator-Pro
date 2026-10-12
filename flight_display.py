"""
The flight display drawn over the camera views - the gauge an instructor
reads while a student flies.

Built 11 Oct 2026 to the layout of Mission Planner's HUD, which is what the
instructor asked for and what students will meet on real ground stations:
speed tape on the left, altitude tape on the right, heading tape across the
top, pitch ladder and roll arc in the middle, and a strip of system state
along the bottom.

WHAT IS REAL AND WHAT IS NOT

Everything on the display is a field the station already receives over
MAVLink: attitude, airspeed, groundspeed, relative altitude, heading,
battery percentage, satellite count, flight mode, armed state and PX4's own
arming verdict. Mission Planner also shows battery volts and amps and a
vibration bar; this station does not subscribe to those messages, so those
are not drawn rather than drawn as zeroes.

Vertical speed is differentiated from altitude here, the same way the
parameter band does it - the feed carries no climb rate.

THE COLOUR CODE, as asked for:
    red     danger      disarmed, failsafe, flight termination, low altitude
    amber   warning     takeoff, landing, return to launch, not ready to arm
    green   normal      armed and flying, ready to arm

THE LOW-ALTITUDE WARNING is a training aid, not a certified GPWS. The
threshold is a number chosen for this simulator (see LOW_ALT_M below), not
one taken from any standard, and it is deliberately armed only after the
aircraft has climbed well clear of it - otherwise it would sound through
every takeoff. It is suppressed in LAND and in TAKEOFF, because in both the
aircraft is near the ground on purpose.

The display is drawn into every canvas on the page carrying class "hud" or
"fpv-hud", so the nose view, the chase view and the classic page all get the
same gauge from one piece of code.
"""

# Metres AGL below which the low-altitude warning sounds. A figure for this
# simulator: low enough that a student at a sensible training height never
# hears it, high enough to leave room to react. Not from CAP722B or any
# other standard - there is no published minimum height for this.
LOW_ALT_M = 15.0

# The warning only arms once the aircraft has been this far above the
# threshold, so it stays quiet on the ground and through the climb out.
LOW_ALT_ARM_M = 40.0

STYLE = """
<style>
  .hud-toggle, .alarm-toggle {
    position: absolute; bottom: 8px; display: inline-flex; align-items: center;
    gap: 6px; font-size: 11px; color: #ffffff; background: rgba(0,0,0,0.55);
    padding: 4px 8px; border-radius: 6px; z-index: 4;
  }
  .hud-toggle { left: 10px; }
  .alarm-toggle { left: 136px; }
  .tile .alarm-toggle { display: none; }
</style>
"""

SCRIPT = """
<script>
(function () {
  'use strict';

  var LOW_ALT_M = __LOW_ALT_M__;
  var LOW_ALT_ARM_M = __LOW_ALT_ARM_M__;

  var AMBER = '#ffc400', RED = '#ff4b4b', GREEN = '#4ade80', INK = '#ffffff';

  function telemetry() {
    // Each page's own script keeps its telemetry inside its own closure, so
    // the reading is published on window as it arrives. Reading a closure
    // variable from here silently gave an empty object, and the whole gauge
    // drew zeroes while the console beside it showed live figures.
    return window.gcsTelemetry || {};
  }

  function canvases() {
    return document.querySelectorAll('canvas.hud, canvas.fpv-hud');
  }

  function enabled() {
    var box = document.getElementById('hud-on');
    return !box || box.checked;
  }

  // ---------- sound ----------
  // A browser will not make a noise until the page has been clicked, so the
  // context is created on the first click and resumed if it was suspended.
  var audio = null;
  function audioContext() {
    var Ctor = window.AudioContext || window.webkitAudioContext;
    if (!Ctor) { return null; }
    if (!audio) { audio = new Ctor(); }
    if (audio.state === 'suspended') { audio.resume(); }
    return audio;
  }
  document.addEventListener('mousedown', function () { audioContext(); });

  function tone(hz, seconds, volume) {
    var ctx = audio;
    if (!ctx || ctx.state !== 'running') { return; }
    var osc = ctx.createOscillator(), gain = ctx.createGain();
    osc.type = 'square';
    osc.frequency.value = hz;
    gain.gain.setValueAtTime(0.0001, ctx.currentTime);
    gain.gain.exponentialRampToValueAtTime(volume, ctx.currentTime + 0.012);
    gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + seconds);
    osc.connect(gain); gain.connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + seconds + 0.02);
  }

  function alarmAllowed() {
    var box = document.getElementById('alarm-on');
    return !box || box.checked;
  }

  // ---------- the low-altitude warning ----------
  var low = { armed: false, active: false, lastBeep: 0, high: false };

  function updateLowAlt() {
    var t = telemetry();
    var alt = t.altitude_m, mode = (t.mode || '').toLowerCase();
    if (!t.armed || alt == null) {
      low.armed = false; low.active = false; low.high = false;
      return;
    }
    // Arm the warning only after a clear climb, so it does not sound on the
    // ground or through the takeoff it would otherwise interrupt.
    if (alt >= LOW_ALT_ARM_M) { low.armed = true; }
    // Silent in LAND and TAKEOFF: in both the aircraft is near the ground
    // because the instructor told it to be, and an alarm through a commanded
    // takeoff or landing is an alarm nobody will listen to by the third
    // lesson.
    var commanded = mode.indexOf('land') !== -1 || mode.indexOf('takeoff') !== -1;
    low.active = low.armed && !commanded && alt < LOW_ALT_M;

    if (!low.active || !alarmAllowed()) { return; }
    var now = Date.now();
    if (now - low.lastBeep < 420) { return; }
    low.lastBeep = now;
    low.high = !low.high;
    tone(low.high ? 1180 : 760, 0.3, 0.22);
  }

  // ---------- what the banner says ----------
  // Announcements the console raises itself (a command going out) outrank
  // the derived state for a few seconds, so pressing ARM says ARM.
  var announced = { text: null, level: 'ok', until: 0 };
  window.gcsAnnounce = function (text, level, seconds) {
    announced = { text: text, level: level || 'ok',
                  until: Date.now() + (seconds || 4) * 1000 };
  };

  var wasArmed = null;
  function banner() {
    var t = telemetry();
    if (low.active) { return { text: 'LOW ALTITUDE', level: 'danger' }; }
    if (wasArmed !== null && t.armed !== wasArmed && t.armed !== undefined) {
      window.gcsAnnounce(t.armed ? 'ARMED' : 'DISARMED',
                         t.armed ? 'ok' : 'danger', 4);
    }
    if (t.armed !== undefined) { wasArmed = t.armed; }
    if (announced.text && Date.now() < announced.until) {
      return { text: announced.text, level: announced.level };
    }
    var mode = (t.mode || '').toLowerCase();
    if (!t.armed) {
      if (t.arm_ready === false) { return { text: 'NOT READY TO ARM', level: 'warn' }; }
      return { text: 'DISARMED', level: 'danger' };
    }
    if (mode.indexOf('takeoff') !== -1) { return { text: 'TAKE-OFF', level: 'warn' }; }
    if (mode.indexOf('land') !== -1) { return { text: 'LANDING', level: 'warn' }; }
    if (mode.indexOf('return') !== -1 || mode.indexOf('rtl') !== -1) {
      return { text: 'RETURN TO LAUNCH', level: 'warn' };
    }
    if (mode.indexOf('termin') !== -1) { return { text: 'FLIGHT TERMINATED', level: 'danger' }; }
    return { text: 'ARMED', level: 'ok' };
  }

  function levelColour(level) {
    return level === 'danger' ? RED : level === 'warn' ? AMBER : GREEN;
  }

  // ---------- drawing helpers ----------
  function cased(ctx, draw, colour, width) {
    ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.strokeStyle = 'rgba(0,0,0,0.78)'; ctx.lineWidth = width + 3.5;
    draw();
    ctx.strokeStyle = colour; ctx.lineWidth = width;
    draw();
  }

  function label(ctx, txt, x, y, font, colour, align) {
    ctx.font = font;
    ctx.textAlign = align || 'center';
    ctx.textBaseline = 'middle';
    ctx.lineJoin = 'round';
    ctx.strokeStyle = 'rgba(0,0,0,0.85)'; ctx.lineWidth = 3.5;
    ctx.strokeText(txt, x, y);
    ctx.fillStyle = colour;
    ctx.fillText(txt, x, y);
  }

  function plate(ctx, x, y, w, h) {
    ctx.fillStyle = 'rgba(0,0,0,0.72)';
    ctx.fillRect(x, y, w, h);
    ctx.strokeStyle = 'rgba(255,255,255,0.85)';
    ctx.lineWidth = 1.6;
    ctx.strokeRect(x, y, w, h);
  }

  function compassName(deg) {
    var d = ((deg % 360) + 360) % 360;
    var names = { 0: 'N', 45: 'NE', 90: 'E', 135: 'SE',
                  180: 'S', 225: 'SW', 270: 'W', 315: 'NW' };
    return names[d] || null;
  }

  // ---------- a vertical tape ----------
  // side: -1 puts the pointer on the right of the tape (left-hand tape),
  // +1 puts it on the left (right-hand tape).
  function tape(ctx, x, top, w, h, value, span, major, minor, side, limit) {
    var mid = top + h / 2;
    var pxPerUnit = h / span;
    ctx.save();
    ctx.beginPath(); ctx.rect(x, top, w, h); ctx.clip();
    ctx.fillStyle = 'rgba(0,0,0,0.42)';
    ctx.fillRect(x, top, w, h);

    var first = Math.ceil((value - span / 2) / minor) * minor;
    for (var v = first; v <= value + span / 2; v += minor) {
      var y = mid - (v - value) * pxPerUnit;
      var big = Math.abs(v % major) < minor / 4;
      var len = big ? w * 0.42 : w * 0.22;
      var x0 = (side < 0) ? x + w - len : x;
      cased(ctx, function () {
        ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x0 + len, y); ctx.stroke();
      }, INK, big ? 2 : 1.4);
      if (big) {
        label(ctx, String(Math.round(v)),
              (side < 0) ? x + w - len - 5 : x + len + 5, y,
              '600 12px "IBM Plex Mono", monospace', INK,
              (side < 0) ? 'right' : 'left');
      }
    }
    // A limit line, drawn where the tape reaches it - the ceiling on the
    // altitude tape, so the student can see it coming.
    if (limit != null && Math.abs(limit - value) < span / 2) {
      var ly = mid - (limit - value) * pxPerUnit;
      ctx.strokeStyle = RED; ctx.lineWidth = 3;
      ctx.beginPath(); ctx.moveTo(x, ly); ctx.lineTo(x + w, ly); ctx.stroke();
    }
    ctx.restore();
    ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1.4;
    ctx.strokeRect(x, top, w, h);
  }

  function tapeReadout(ctx, x, y, w, text) {
    plate(ctx, x, y - 15, w, 30);
    label(ctx, text, x + w / 2, y, '700 17px "IBM Plex Mono", monospace', INK);
  }

  // ---------- the heading tape ----------
  function headingTape(ctx, cx, y, w, heading) {
    var h = 26, left = cx - w / 2, pxPerDeg = w / 70;
    ctx.save();
    ctx.beginPath(); ctx.rect(left, y, w, h); ctx.clip();
    ctx.fillStyle = 'rgba(0,0,0,0.42)';
    ctx.fillRect(left, y, w, h);
    var first = Math.ceil((heading - 35) / 5) * 5;
    for (var d = first; d <= heading + 35; d += 5) {
      var x = cx + (d - heading) * pxPerDeg;
      var name = compassName(d);
      var big = (d % 15 === 0) || name;
      cased(ctx, function () {
        ctx.beginPath();
        ctx.moveTo(x, y + h); ctx.lineTo(x, y + h - (big ? 9 : 5));
        ctx.stroke();
      }, INK, big ? 2 : 1.4);
      if (big) {
        var txt = name || String(((d % 360) + 360) % 360);
        label(ctx, txt, x, y + 9, '600 12px "IBM Plex Mono", monospace', INK);
      }
    }
    ctx.restore();
    ctx.strokeStyle = 'rgba(255,255,255,0.55)'; ctx.lineWidth = 1.4;
    ctx.strokeRect(left, y, w, h);
    // the fixed index, and the figure under it
    ctx.fillStyle = AMBER;
    ctx.beginPath();
    ctx.moveTo(cx, y + h + 1); ctx.lineTo(cx - 7, y + h + 11);
    ctx.lineTo(cx + 7, y + h + 11); ctx.closePath(); ctx.fill();
    plate(ctx, cx - 30, y + h + 11, 60, 24);
    label(ctx, String(Math.round(((heading % 360) + 360) % 360)).padStart(3, '0') + '°',
          cx, y + h + 23, '700 15px "IBM Plex Mono", monospace', INK);
  }

  // ---------- the whole display ----------
  function draw(cv) {
    var ctx = cv.getContext('2d');
    var w = cv.cssW || cv.width, h = cv.cssH || cv.height;
    var cx = w / 2, cy = h / 2;
    ctx.clearRect(0, 0, w, h);
    if (!w || !h || !enabled()) { return; }

    var t = telemetry();
    var roll = t.roll_deg || 0, pitch = t.pitch_deg || 0;
    var pxPerDeg = h / 46;

    // --- pitch ladder and horizon ---
    ctx.save();
    ctx.translate(cx, cy);
    ctx.rotate(-roll * Math.PI / 180);
    ctx.translate(0, pitch * pxPerDeg);
    cased(ctx, function () {
      ctx.beginPath(); ctx.moveTo(-w, 0); ctx.lineTo(w, 0); ctx.stroke();
    }, INK, 3.5);
    for (var d = -40; d <= 40; d += 5) {
      if (d === 0) { continue; }
      var y = -d * pxPerDeg;
      var ten = (d % 10 === 0);
      var half = ten ? 78 : 36;
      var tick = (d < 0) ? -9 : 9;
      var colour = (d < 0) ? AMBER : INK;
      cased(ctx, function () {
        ctx.beginPath();
        if (ten) {
          ctx.moveTo(-half, y + tick); ctx.lineTo(-half, y);
          ctx.lineTo(half, y); ctx.lineTo(half, y + tick);
        } else {
          ctx.moveTo(-half, y); ctx.lineTo(half, y);
        }
        ctx.stroke();
      }, colour, ten ? 2.6 : 2);
      if (ten) {
        label(ctx, String(Math.abs(d)), half + 9, y,
              '700 14px -apple-system, sans-serif', colour, 'left');
        label(ctx, String(Math.abs(d)), -half - 9, y,
              '700 14px -apple-system, sans-serif', colour, 'right');
      }
    }
    ctx.restore();

    // --- the fixed aircraft symbol ---
    cased(ctx, function () {
      ctx.beginPath();
      ctx.moveTo(cx - 82, cy); ctx.lineTo(cx - 28, cy); ctx.lineTo(cx - 14, cy + 14);
      ctx.moveTo(cx + 82, cy); ctx.lineTo(cx + 28, cy); ctx.lineTo(cx + 14, cy + 14);
      ctx.stroke();
    }, AMBER, 4.5);
    ctx.fillStyle = 'rgba(0,0,0,0.8)';
    ctx.beginPath(); ctx.arc(cx, cy, 5.5, 0, 7); ctx.fill();
    ctx.fillStyle = AMBER;
    ctx.beginPath(); ctx.arc(cx, cy, 3.5, 0, 7); ctx.fill();

    // --- the roll arc ---
    var R = Math.min(w, h) * 0.34;
    cased(ctx, function () {
      ctx.beginPath(); ctx.arc(cx, cy, R, Math.PI * 1.17, Math.PI * 1.83); ctx.stroke();
    }, INK, 2.5);
    [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60].forEach(function (a) {
      var ar = (a - 90) * Math.PI / 180;
      var big = (a % 30 === 0);
      var inr = big ? R - 17 : R - 10;
      cased(ctx, function () {
        ctx.beginPath();
        ctx.moveTo(cx + Math.cos(ar) * R, cy + Math.sin(ar) * R);
        ctx.lineTo(cx + Math.cos(ar) * inr, cy + Math.sin(ar) * inr);
        ctx.stroke();
      }, INK, big ? 3 : 2);
      if (big) {
        label(ctx, String(Math.abs(a)),
              cx + Math.cos(ar) * (R + 14), cy + Math.sin(ar) * (R + 14),
              '600 12px -apple-system, sans-serif', INK);
      }
    });
    var pa = (-roll - 90) * Math.PI / 180;
    ctx.fillStyle = RED;
    ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.lineWidth = 1.6;
    ctx.beginPath();
    ctx.moveTo(cx + Math.cos(pa) * (R - 2), cy + Math.sin(pa) * (R - 2));
    ctx.lineTo(cx + Math.cos(pa - 0.055) * (R - 17), cy + Math.sin(pa - 0.055) * (R - 17));
    ctx.lineTo(cx + Math.cos(pa + 0.055) * (R - 17), cy + Math.sin(pa + 0.055) * (R - 17));
    ctx.closePath(); ctx.fill(); ctx.stroke();

    // --- the tapes ---
    var tapeW = 60, tapeH = Math.min(h * 0.46, 300);
    var speed = (t.airspeed_ms != null && t.airspeed_ms > 0.2)
              ? t.airspeed_ms : (t.groundspeed_ms || 0);
    tape(ctx, 20, cy - tapeH / 2, tapeW, tapeH, speed, 24, 5, 1, -1, null);
    tapeReadout(ctx, 20, cy, tapeW, speed.toFixed(1));
    label(ctx, 'm/s', 20 + tapeW / 2, cy - tapeH / 2 - 11,
          '600 11px -apple-system, sans-serif', INK);

    var alt = (t.altitude_m != null) ? t.altitude_m : 0;
    var ceiling = (window.GCS_LIMITS && window.GCS_LIMITS.ceiling_m) || null;
    tape(ctx, w - 20 - tapeW, cy - tapeH / 2, tapeW, tapeH, alt, 60, 20, 5, 1, ceiling);
    tapeReadout(ctx, w - 20 - tapeW, cy, tapeW, alt.toFixed(1));
    label(ctx, 'm AGL', w - 20 - tapeW / 2, cy - tapeH / 2 - 11,
          '600 11px -apple-system, sans-serif', INK);

    // --- the heading tape ---
    headingTape(ctx, cx, 10, Math.min(w * 0.46, 420), t.heading_deg || 0);

    // --- the message, colour coded ---
    var msg = banner();
    var colour = levelColour(msg.level);
    var flash = (msg.level === 'danger') && (Math.floor(Date.now() / 450) % 2 === 0);
    var font = '800 30px -apple-system, sans-serif';
    ctx.font = font;
    var mw = ctx.measureText(msg.text).width + 34;
    var my = cy - Math.min(h * 0.26, 150);
    ctx.fillStyle = flash ? 'rgba(120,0,0,0.75)' : 'rgba(0,0,0,0.6)';
    ctx.fillRect(cx - mw / 2, my - 23, mw, 46);
    ctx.strokeStyle = colour; ctx.lineWidth = 2.5;
    ctx.strokeRect(cx - mw / 2, my - 23, mw, 46);
    label(ctx, msg.text, cx, my, font, colour);

    // --- the system strip ---
    // Mission Planner runs this along the bottom of the picture. Here the
    // bottom of the picture is taken: the two corner tiles sit in it and the
    // attitude gyro sits across the middle of it, so the same figures run
    // down the two top corners instead, where nothing else is drawn.
    var mono = '600 13px "IBM Plex Mono", monospace';
    label(ctx, 'BANK ' + roll.toFixed(0) + '°  PITCH ' + pitch.toFixed(0) + '°',
          16, 20, '600 12px -apple-system, sans-serif', INK, 'left');
    label(ctx, 'AS ' + (t.airspeed_ms != null ? t.airspeed_ms.toFixed(1) : '--'), 16, 42, mono, INK, 'left');
    label(ctx, 'GS ' + (t.groundspeed_ms != null ? t.groundspeed_ms.toFixed(1) : '--'), 16, 62, mono, INK, 'left');

    var bat = (t.battery_pct != null) ? t.battery_pct + '%' : '--';
    var sats = (t.satellites != null) ? t.satellites : '--';
    var armTxt = t.arm_ready === true ? 'ARM OK'
               : t.arm_ready === false ? 'ARM BLOCKED' : 'ARM ?';
    var armCol = t.arm_ready === true ? GREEN : t.arm_ready === false ? AMBER : INK;
    label(ctx, (t.mode || '-').toUpperCase(), w - 16, 20,
          '700 14px -apple-system, sans-serif', INK, 'right');
    label(ctx, 'BAT ' + bat, w - 16, 42, mono, INK, 'right');
    label(ctx, 'SATS ' + sats, w - 16, 62, mono, INK, 'right');
    label(ctx, armTxt, w - 16, 82, mono, armCol, 'right');
  }

  function fit(cv) {
    var w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) { return false; }
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var bw = Math.round(w * dpr), bh = Math.round(h * dpr);
    cv.cssW = w; cv.cssH = h;
    if (cv.width !== bw || cv.height !== bh) { cv.width = bw; cv.height = bh; }
    cv.getContext('2d').setTransform(cv.width / w, 0, 0, cv.height / h, 0, 0);
    return true;
  }

  // A seam for tools/test_flight_display.py: the banner wording, the colour
  // it is drawn in and the low-altitude state are decisions worth testing,
  // and reading them back off a canvas would prove nothing.
  window.gcsHudState = function () {
    updateLowAlt();
    var b = banner();
    return { text: b.text, level: b.level, colour: levelColour(b.level),
             lowArmed: low.armed, lowActive: low.active };
  };

  window.gcsDrawHud = function () {
    updateLowAlt();
    var list = canvases();
    for (var i = 0; i < list.length; i++) {
      if (fit(list[i])) { draw(list[i]); }
    }
  };

  setInterval(window.gcsDrawHud, 120);
  window.gcsDrawHud();
})();
</script>
"""


def script():
    """The display's JavaScript, with the warning thresholds filled in."""
    return (SCRIPT
            .replace("__LOW_ALT_M__", repr(LOW_ALT_M))
            .replace("__LOW_ALT_ARM_M__", repr(LOW_ALT_ARM_M)))
