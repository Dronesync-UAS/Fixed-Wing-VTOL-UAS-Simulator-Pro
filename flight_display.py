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

THE BATTERY WARNING flashes the percentage and raises a message at 20%
and again at 10%, the two figures the instructor asked for. PX4 has its
own low-battery thresholds and those are what make the AIRCRAFT act; these
only decide when the CONSOLE says something.

THE WARNINGS ARE TRAINING AIDS, NOT A CERTIFIED GPWS. There are two:
LOW ALTITUDE, which is about where the aircraft is, and PULL UP, which is
about where it is going - it sounds and repeats when the current rate of
descent would put the aircraft on the ground within a few seconds. Both
sets of figures were chosen for this simulator.

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

# SINK RATE / PULL UP. A real GPWS works the descent rate against the
# height remaining: the faster the ground is coming up, the higher it
# starts shouting. This is the same shape of rule, with figures chosen for
# this simulator - they are NOT from any published GPWS envelope, and the
# module says so out loud rather than implying a certification it has not
# got.
#
# PULL UP sounds when the aircraft would reach the ground in less than
# PULL_UP_SECONDS at its current rate of descent, and it is below
# SINK_WATCH_M. That one rule covers both cases asked for: a fault that
# drops the aircraft, and a student diving at the desert.
SINK_WATCH_M = 100.0        # below this height the sink rate is watched
PULL_UP_SECONDS = 8.0       # ground this close in time and it shouts
SINK_RATE_MIN_MS = 2.0      # ignore the drift of an ordinary descent

# BATTERY. The two figures an instructor asked for. PX4 has its own
# thresholds (COM_LOW_BAT_ACT and the BAT_*_THR parameters) and they are
# what actually make the aircraft do something; these only decide when the
# console starts shouting, so they are kept separate and named here rather
# than implied to be PX4's.
BATTERY_LOW_PCT = 20
BATTERY_CRITICAL_PCT = 10

STYLE = """
<style>
  .hud-toggle, .alarm-toggle {
    position: absolute; bottom: 8px; display: inline-flex; align-items: center;
    gap: 6px; font-size: 11px; color: #ffffff; background: rgba(0,0,0,0.55);
    padding: 4px 8px; border-radius: 6px; z-index: 4;
  }
  .hud-toggle { left: 10px; }
  .alarm-toggle { left: 136px; }
  /* Speaking is off until someone asks for it: a classroom where the
     console talks over the instructor is worse than one that does not. */
  .tile .alarm-toggle { display: none; }
</style>
"""

SCRIPT = """
<script>
(function () {
  'use strict';

  var LOW_ALT_M = __LOW_ALT_M__;
  var LOW_ALT_ARM_M = __LOW_ALT_ARM_M__;
  var SINK_WATCH_M = __SINK_WATCH_M__;
  var PULL_UP_SECONDS = __PULL_UP_SECONDS__;
  var SINK_RATE_MIN_MS = __SINK_RATE_MIN_MS__;
  var BATTERY_LOW_PCT = __BATTERY_LOW_PCT__;
  var BATTERY_CRITICAL_PCT = __BATTERY_CRITICAL_PCT__;

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

  // Shared, because a browser allows only a handful of audio contexts per
  // page and the motor sound (motor_sound.py) needs the same one. It also
  // means one click unlocks both the alarm and the motors.
  window.gcsAudio = audioContext;

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

  // ---------- the voice ----------
  // Spoken by the browser itself, so there is no sound file to ship and no
  // voice to install - every machine that runs a browser has one. It is
  // deliberately terse: an instructor watching a student does not want a
  // sentence read out, just the word for what happened.
  var lastSpoken = { text: null, at: 0 };

  function voiceAllowed() {
    var box = document.getElementById('voice-on');
    return box ? box.checked : false;
  }

  window.gcsSpeak = function (text, force) {
    if (!text || !voiceAllowed() || !window.speechSynthesis) { return; }
    var now = Date.now();
    // The same word twice inside three seconds is a repeat, not news.
    if (!force && text === lastSpoken.text && now - lastSpoken.at < 3000) { return; }
    lastSpoken = { text: text, at: now };
    try {
      var said = new SpeechSynthesisUtterance(text);
      said.rate = 1.05;
      said.volume = 0.9;
      window.speechSynthesis.speak(said);
    } catch (err) { /* a browser without a voice is not a fault */ }
  };

  function alarmAllowed() {
    var box = document.getElementById('alarm-on');
    return !box || box.checked;
  }

  // ---------- sink rate ----------
  // The feed carries no climb rate, so it is differentiated from the
  // altitude, the same way the parameter band does it. Smoothed, because
  // a raw difference between two 0.1 m readings is mostly noise and this
  // one decides whether the console starts shouting.
  var IMPLAUSIBLE_RATE_MS = 40;   // a step this big is data, not a descent
  var SINK_HOLD_MS = 1000;        // and it has to hold this long to count
  var sink = { lastAlt: null, lastT: 0, rate: 0, active: false,
               lastSay: 0, lastBeep: 0, heldSince: 0 };

  function updateSink() {
    var t = telemetry(), alt = t.altitude_m, now = Date.now();
    if (alt == null || !t.armed || t.in_air === false) {
      sink.lastAlt = null; sink.rate = 0; sink.active = false;
      sink.heldSince = 0;
      return;
    }
    if (sink.lastAlt !== null && now > sink.lastT) {
      var per = (sink.lastAlt - alt) / ((now - sink.lastT) / 1000);
      // A step of tens of metres between two readings is the altitude
      // being re-based - a reposition, a GPS glitch, the home point
      // moving - not the aircraft falling. Taking it at face value had the
      // console shouting PULL UP at an aircraft climbing away normally.
      if (Math.abs(per) > IMPLAUSIBLE_RATE_MS) {
        sink.rate = 0; sink.heldSince = 0;
      } else {
        sink.rate = sink.rate * 0.7 + per * 0.3;    // metres per second DOWN
      }
    }
    sink.lastAlt = alt; sink.lastT = now;

    var mode = (t.mode || '').toLowerCase();
    var commanded = mode.indexOf('land') !== -1;
    var seconds = sink.rate > SINK_RATE_MIN_MS ? alt / sink.rate : Infinity;
    var meets = !commanded && alt < SINK_WATCH_M
                && sink.rate > SINK_RATE_MIN_MS && seconds < PULL_UP_SECONDS;
    // Held for a moment before it counts, so one noisy sample cannot start
    // the console shouting.
    if (!meets) { sink.heldSince = 0; }
    else if (!sink.heldSince) { sink.heldSince = now; }
    sink.active = meets && (now - sink.heldSince) >= SINK_HOLD_MS;
    sink.seconds = seconds;

    if (!sink.active) { return; }
    if (alarmAllowed() && now - sink.lastBeep > 300) {
      sink.lastBeep = now;
      tone(1500, 0.18, 0.28);
    }
    // Said on repeat for as long as it holds, which is the point of it.
    if (now - sink.lastSay > 2200) {
      sink.lastSay = now;
      window.gcsSpeak('Pull up. Pull up.', true);
    }
  }

  // ---------- the low-altitude warning ----------
  var low = { armed: false, active: false, lastBeep: 0, high: false };

  function updateLowAlt() {
    var t = telemetry();
    var alt = t.altitude_m, mode = (t.mode || '').toLowerCase();
    if (!t.armed || alt == null || t.in_air === false) {
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
  function batteryLevel() {
    var pct = telemetry().battery_pct;
    if (pct == null) { return null; }
    if (pct <= BATTERY_CRITICAL_PCT) { return 'critical'; }
    if (pct <= BATTERY_LOW_PCT) { return 'low'; }
    return null;
  }

  function banner() {
    var t = telemetry();
    // In the order they have to be dealt with. Sinking onto the ground
    // outranks being near it - one is a thing that is happening, the other
    // a thing that is true - and a battery about to quit outranks both.
    if (sink.active) { return { text: 'PULL UP', level: 'danger' }; }
    var bat = batteryLevel();
    if (bat === 'critical') { return { text: 'BATTERY CRITICAL', level: 'danger' }; }
    if (low.active) { return { text: 'LOW ALTITUDE', level: 'danger' }; }
    if (bat === 'low' && t.armed) { return { text: 'BATTERY LOW', level: 'warn' }; }
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

  // Speaking is driven off the banner rather than off each button, so the
  // aircraft's own state is what is called out: pressing ARM when PX4
  // refuses says nothing, and PX4 disarming itself ten seconds later does.
  // How long a message stays on screen. A warning or a danger holds until
  // the condition clears - that is the point of it. ARMED does not: it is
  // news for a moment and furniture after that.
  var BANNER_HOLD_MS = 6000;
  var bannerShown = { text: null, at: 0 };

  function bannerVisible(msg) {
    if (msg.level !== 'ok') { return true; }
    if (msg.text !== bannerShown.text) {
      bannerShown = { text: msg.text, at: Date.now() };
    }
    return Date.now() - bannerShown.at < BANNER_HOLD_MS;
  }

  var spokenBanner = null;
  function speakBanner(msg) {
    if (msg.text === spokenBanner) { return; }
    spokenBanner = msg.text;
    // A null here means something else says it - PULL UP repeats on its
    // own timer, and saying it once more on the change would double it.
    if (SPOKEN_AS[msg.text] === null) { return; }
    window.gcsSpeak(SPOKEN_AS[msg.text] || msg.text);
  }

  // How each message is said aloud. Left out of this list, a message is
  // read as it is written, which is why they are short words to begin with.
  var SPOKEN_AS = {
    'PULL UP': null,
    'BATTERY LOW': 'Battery low',
    'BATTERY CRITICAL': 'Battery critical. Land now.',
    'TAKE-OFF': 'Take off',
    'LOW ALTITUDE': 'Low altitude. Low altitude.',
    'NOT READY TO ARM': 'Not ready to arm',
    'RETURN TO LAUNCH': 'Returning to launch',
    'FLIGHT TERMINATED': 'Flight terminated'
  };

  function levelColour(level) {
    return level === 'danger' ? RED : level === 'warn' ? AMBER : GREEN;
  }

  // ---------- drawing helpers ----------
  // ---------- where it is safe to draw ----------
  // The main screen runs edge to edge and behind the top bar, so the tapes
  // were printing under the two control columns and the corner figures
  // under the bar itself. Rather than guess at margins that would be wrong
  // the moment a panel is moved, measure what is actually on top of this
  // canvas and keep inside it.
  var OBSTRUCTIONS = ['#topbar', '#rail-left', '#rail-right', '#bottom'];
  var GAP = 12;

  function safeArea(cv) {
    var box = cv.getBoundingClientRect();
    var area = { left: GAP, right: GAP, top: GAP, bottom: GAP };
    var midX = box.left + box.width / 2, midY = box.top + box.height / 2;
    OBSTRUCTIONS.forEach(function (sel) {
      var el = document.querySelector(sel);
      if (!el) { return; }
      var r = el.getBoundingClientRect();
      if (!r.width || !r.height) { return; }
      // Only what actually overlaps this canvas counts.
      if (r.right <= box.left || r.left >= box.right
          || r.bottom <= box.top || r.top >= box.bottom) { return; }
      // Which side it is on, by where it sits rather than by whether it
      // touches the edge: in the Pilot layout the control columns float ten
      // pixels clear of the edge, and an edge test missed them completely.
      var tall = Math.min(r.bottom, box.bottom) - Math.max(r.top, box.top)
                 > box.height * 0.4;
      var wide = Math.min(r.right, box.right) - Math.max(r.left, box.left)
                 > box.width * 0.4;
      if (tall && r.right <= midX) {
        area.left = Math.max(area.left, r.right - box.left + GAP);
      } else if (tall && r.left >= midX) {
        area.right = Math.max(area.right, box.right - r.left + GAP);
      } else if (wide && r.bottom <= midY) {
        area.top = Math.max(area.top, r.bottom - box.top + GAP);
      } else if (wide && r.top >= midY) {
        area.bottom = Math.max(area.bottom, box.bottom - r.top + GAP);
      }
    });
    return area;
  }

  // Where the corner views sit, in this canvas's own coordinates.
  function tiles(cv) {
    var box = cv.getBoundingClientRect();
    var out = [];
    document.querySelectorAll('.tile').forEach(function (t) {
      var r = t.getBoundingClientRect();
      if (!r.width || !r.height) { return; }
      out.push({ left: r.left - box.left, right: r.right - box.left,
                 top: r.top - box.top, bottom: r.bottom - box.top });
    });
    return out;
  }

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
    // Same height and type size as the speed and altitude tapes. It was
    // 26px against their 30px readouts, with 12px type against 17px, which
    // made the one number a pilot checks most the hardest to read.
    var h = 34, left = cx - w / 2, pxPerDeg = w / 70;
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
        ctx.moveTo(x, y + h); ctx.lineTo(x, y + h - (big ? 11 : 6));
        ctx.stroke();
      }, INK, big ? 2.2 : 1.5);
      if (big) {
        var txt = name || String(((d % 360) + 360) % 360);
        label(ctx, txt, x, y + 12, '600 15px "IBM Plex Mono", monospace', INK);
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
    plate(ctx, cx - 36, y + h + 11, 72, 30);
    label(ctx, String(Math.round(((heading % 360) + 360) % 360)).padStart(3, '0') + '°',
          cx, y + h + 26, '700 17px "IBM Plex Mono", monospace', INK);
  }

  // ---------- the home point, seen through the camera ----------
  // DJI's displays keep a marker on the home point wherever the camera is
  // looking, so a student always knows where back is. The same thing here:
  // work out where home is relative to the aircraft, turn that into the
  // camera's own frame using the attitude PX4 reports, and project it.
  //
  // The field of view is NOT written down here. It lives in the world file
  // on the simulator's machine, and a marker projected with the wrong angle
  // is worse than no marker - it points confidently at the wrong patch of
  // desert. The station reads each camera's real angle from the camera_info
  // Gazebo publishes beside the picture, and if that is not available the
  // marker is simply not drawn.
  //
  // The camera's offset from the aircraft (the chase camera sits nine
  // metres back) is ignored: home is hundreds of metres away, so nine
  // metres moves the marker by a fraction of a degree.
  var CAMERA_PITCH_DOWN = { chase: 0.24, nose: 0 };   // radians, from the world file

  function homePoint(cv, w, h, t, safe) {
    var fovs = t.camera_fov || {};
    var which = (cv.closest && cv.closest('#view-chase')) ? 'chase' : 'nose';
    var fov = fovs[which];
    if (!fov || t.home_lat == null || t.latitude == null) { return null; }
    if (t.altitude_m == null) { return null; }

    var latR = t.latitude * Math.PI / 180;
    var north = (t.home_lat - t.latitude) * 110540;
    var east = (t.home_lon - t.longitude) * 111320 * Math.cos(latR);
    var down = t.altitude_m;            // home is on the ground below us
    var ground = Math.sqrt(north * north + east * east);
    if (ground < 3 && down < 3) { return null; }

    // World (north, east, down) into the aircraft's own axes.
    var yaw = (t.yaw_deg != null ? t.yaw_deg : t.heading_deg || 0) * Math.PI / 180;
    var pitch = (t.pitch_deg || 0) * Math.PI / 180;
    var roll = (t.roll_deg || 0) * Math.PI / 180;
    var cy = Math.cos(yaw), sy = Math.sin(yaw);
    var x1 = north * cy + east * sy;        // forward, before pitch and roll
    var y1 = -north * sy + east * cy;       // right
    var z1 = down;
    var cp = Math.cos(pitch), sp = Math.sin(pitch);
    var x2 = x1 * cp - z1 * sp;
    var z2 = x1 * sp + z1 * cp;
    var cr = Math.cos(roll), sr = Math.sin(roll);
    var y3 = y1 * cr + z2 * sr;
    var z3 = -y1 * sr + z2 * cr;
    // The camera's own downward tilt on the airframe.
    var tilt = CAMERA_PITCH_DOWN[which] || 0;
    var ct = Math.cos(tilt), st = Math.sin(tilt);
    var xc = x2 * ct + z3 * st;
    var zc = -x2 * st + z3 * ct;

    var half = Math.tan(fov / 2);
    var vhalf = half * (h / w);
    var inFront = xc > 1;
    var px, py, offscreen = false;
    if (inFront) {
      px = cx(w) + (y3 / xc) / half * (w / 2);
      py = h / 2 + (zc / xc) / vhalf * (h / 2);
      offscreen = px < safe.left || px > w - safe.right
               || py < safe.top || py > h - safe.bottom;
    }

    var dist = Math.round(Math.sqrt(ground * ground + down * down));
    if (!inFront || offscreen) {
      // Behind, or outside the picture: an arrow on the edge pointing the
      // way home, which is the part a pilot actually needs.
      var bearing = Math.atan2(y3, xc);
      var r = Math.min(w, h) * 0.30;
      px = cx(w) + Math.sin(bearing) * r;
      py = h / 2 - Math.cos(bearing) * r * 0.55;
      return { x: px, y: py, dist: dist, bearing: bearing, arrow: true };
    }
    return { x: px, y: py, dist: dist, bearing: 0, arrow: false };
  }

  function cx(w) { return w / 2; }

  function drawHomeGlyph(ctx, x, y, dist, bearing, isArrow) {
    ctx.save();
    if (isArrow) {
      ctx.translate(x, y);
      ctx.rotate(bearing);
      ctx.beginPath();
      ctx.moveTo(0, -14); ctx.lineTo(10, 10); ctx.lineTo(0, 4); ctx.lineTo(-10, 10);
      ctx.closePath();
      ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.lineWidth = 4; ctx.stroke();
      ctx.fillStyle = GREEN; ctx.fill();
      ctx.restore();
      label(ctx, 'HOME ' + dist + ' m', x, y + 26,
            '700 12px -apple-system, sans-serif', GREEN);
      return;
    }
    // A house on a stake, so it reads as a point on the ground.
    ctx.translate(x, y);
    ctx.beginPath();
    ctx.moveTo(0, 0); ctx.lineTo(0, -16);
    ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.lineWidth = 5; ctx.stroke();
    ctx.strokeStyle = GREEN; ctx.lineWidth = 2.5; ctx.stroke();
    ctx.beginPath();
    ctx.moveTo(-9, -16); ctx.lineTo(0, -26); ctx.lineTo(9, -16); ctx.closePath();
    ctx.moveTo(-6, -16); ctx.lineTo(-6, -8); ctx.lineTo(6, -8); ctx.lineTo(6, -16);
    ctx.strokeStyle = 'rgba(0,0,0,0.8)'; ctx.lineWidth = 5; ctx.stroke();
    ctx.strokeStyle = GREEN; ctx.lineWidth = 2.5; ctx.stroke();
    ctx.beginPath(); ctx.arc(0, 0, 3.5, 0, 7);
    ctx.fillStyle = GREEN; ctx.fill();
    ctx.restore();
    label(ctx, 'HOME ' + dist + ' m', x, y + 16,
          '700 12px -apple-system, sans-serif', GREEN);
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

    // The horizon and the ladder belong on the picture's own centre - they
    // have to line up with the real horizon in the camera image, so they
    // ignore the safe area. Everything else lives inside it.
    var safe = safeArea(cv);
    var sL = safe.left, sR = w - safe.right, sT = safe.top, sB = h - safe.bottom;

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
    // Pulled in towards the middle. Sitting them against the safe-area
    // edge put them right up against the control columns, which is not
    // where a real panel has them - speed and height belong either side of
    // the attitude display, close enough to read in the same glance.
    var tapeW = 64, tapeH = Math.min((sB - sT) * 0.56, 300);
    var usable = sR - sL;
    var inset = Math.max(26, Math.min(usable * 0.17, 230));
    var speedX = Math.max(sL, cx - inset - tapeW);
    var altX = Math.min(sR - tapeW, cx + inset);

    // The two corner views are 400px wide now, and at that size the left
    // one reached across the speed tape. Rather than pick an inset that
    // happens to clear them today - the instructor can drag them to any
    // size - measure where they actually are and step the tapes inboard
    // of them, stopping well short of the middle so they never collide
    // with the attitude display.
    var tapeTop = cy - tapeH / 2, tapeBottom = cy + tapeH / 2;
    tiles(cv).forEach(function (r) {
      if (r.bottom <= tapeTop || r.top >= tapeBottom) { return; }
      if (r.right > speedX && r.left < speedX + tapeW) {
        speedX = Math.min(r.right + 10, cx - 96 - tapeW);
      }
      if (r.left < altX + tapeW && r.right > altX) {
        altX = Math.max(r.left - tapeW - 10, cx + 96);
      }
    });

    cv.tapeRects = {
      speed: { left: speedX, right: speedX + tapeW, top: tapeTop, bottom: tapeBottom },
      alt: { left: altX, right: altX + tapeW, top: tapeTop, bottom: tapeBottom }
    };

    var speed = (t.airspeed_ms != null && t.airspeed_ms > 0.2)
              ? t.airspeed_ms : (t.groundspeed_ms || 0);
    tape(ctx, speedX, cy - tapeH / 2, tapeW, tapeH, speed, 24, 5, 1, -1, null);
    tapeReadout(ctx, speedX, cy, tapeW, speed.toFixed(1));
    label(ctx, 'm/s', speedX + tapeW / 2, cy - tapeH / 2 - 12,
          '600 13px -apple-system, sans-serif', INK);

    var alt = (t.altitude_m != null) ? t.altitude_m : 0;
    var ceiling = (window.GCS_LIMITS && window.GCS_LIMITS.ceiling_m) || null;
    tape(ctx, altX, cy - tapeH / 2, tapeW, tapeH, alt, 60, 20, 5, 1, ceiling);
    tapeReadout(ctx, altX, cy, tapeW, alt.toFixed(1));
    label(ctx, 'm AGL', altX + tapeW / 2, cy - tapeH / 2 - 12,
          '600 13px -apple-system, sans-serif', INK);

    // --- the heading tape ---
    headingTape(ctx, cx, sT, Math.min((sR - sL) * 0.46, 440), t.heading_deg || 0);

    // --- the message, colour coded ---
    var msg = banner();
    var showMessage = bannerVisible(msg);
    var colour = levelColour(msg.level);
    var flash = (msg.level === 'danger') && (Math.floor(Date.now() / 450) % 2 === 0);
    var font = '800 30px -apple-system, sans-serif';
    ctx.font = font;
    var mw = ctx.measureText(msg.text).width + 34;
    if (!showMessage) { mw = 0; }
    // BELOW the aircraft symbol, not above it. Up there it printed across
    // the roll arc and the pitch ladder - the part of the gauge being read
    // while the message is still on screen. Down here it is clear of the
    // arc above and of the attitude indicator at the bottom centre.
    var my = Math.min(cy + Math.min(h * 0.17, 115), sB - 120);
    if (showMessage) {
      ctx.fillStyle = flash ? 'rgba(120,0,0,0.75)' : 'rgba(0,0,0,0.6)';
      ctx.fillRect(cx - mw / 2, my - 23, mw, 46);
      ctx.strokeStyle = colour; ctx.lineWidth = 2.5;
      ctx.strokeRect(cx - mw / 2, my - 23, mw, 46);
      label(ctx, msg.text, cx, my, font, colour);
    }

    // --- the home point, where the camera would see it ---
    if (cv.closest && !cv.closest('#view-map')) {
      var home = homePoint(cv, w, h, t, safe);
      if (home) {
        drawHomeGlyph(ctx, home.x, home.y, home.dist, home.bearing, home.arrow);
      }
    }

    // --- what a multi-step manoeuvre is doing, under the message ---
    // FORWARD FLIGHT is a climb, then a transition, then another climb,
    // and it can take a minute. Without this the console says one sentence
    // and then looks idle while the aircraft is still working through it.
    if (t.sequence) {
      ctx.font = '600 15px -apple-system, sans-serif';
      var sw = ctx.measureText(t.sequence).width + 24;
      ctx.fillStyle = 'rgba(0,0,0,0.62)';
      ctx.fillRect(cx - sw / 2, my + 27, sw, 28);
      ctx.strokeStyle = 'rgba(255,255,255,0.4)'; ctx.lineWidth = 1.5;
      ctx.strokeRect(cx - sw / 2, my + 27, sw, 28);
      label(ctx, t.sequence, cx, my + 41,
            '600 15px -apple-system, sans-serif', AMBER);
    }

    // --- the system strip ---
    // Mission Planner runs this along the bottom of the picture. Here the
    // bottom of the picture is taken: the two corner tiles sit in it and the
    // attitude gyro sits across the middle of it, so the same figures run
    // down the two top corners instead, where nothing else is drawn.
    var mono = '600 13px "IBM Plex Mono", monospace';
    var ty = sT + 10;
    label(ctx, 'BANK ' + roll.toFixed(0) + '°  PITCH ' + pitch.toFixed(0) + '°',
          sL, ty, '600 12px -apple-system, sans-serif', INK, 'left');
    // Airspeed and ground speed used to be printed here as well. They are
    // on the speed tape and again on the parameter band, and three copies
    // of one number is exactly the clutter an instructor was asking to be
    // rid of. The tape keeps them.

    var bat = (t.battery_pct != null) ? t.battery_pct + '%' : '--';
    var sats = (t.satellites != null) ? t.satellites : '--';
    var armTxt = t.arm_ready === true ? 'ARM OK'
               : t.arm_ready === false ? 'ARM BLOCKED' : 'ARM ?';
    var armCol = t.arm_ready === true ? GREEN : t.arm_ready === false ? AMBER : INK;
    label(ctx, (t.mode || '-').toUpperCase(), sR, ty,
          '700 14px -apple-system, sans-serif', INK, 'right');
    if (t.vtol_state) {
      label(ctx, t.vtol_state.toUpperCase(), sR, ty + 20,
            '600 11px -apple-system, sans-serif',
            t.vtol_state.indexOf('ransition') !== -1 ? AMBER : INK, 'right');
    }
    var batState = batteryLevel();
    var batCol = INK;
    if (batState) {
      // Flashed rather than merely coloured: a number that changes twice a
      // second is seen out of the corner of an eye, a coloured one is not.
      var on = Math.floor(Date.now() / (batState === 'critical' ? 350 : 600)) % 2 === 0;
      batCol = batState === 'critical'
             ? (on ? RED : '#ffd7d7') : (on ? AMBER : '#fff0c2');
    }
    label(ctx, 'BAT ' + bat, sR, ty + 42, mono, batCol, 'right');
    label(ctx, 'SATS ' + sats, sR, ty + 62, mono, INK, 'right');
    label(ctx, armTxt, sR, ty + 82, mono, armCol, 'right');
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
  // For tools/test_console_browser.py: the margins the gauge worked out
  // for a given canvas, so the test can check them against where the
  // controls actually are instead of hunting for stray pixels - the
  // horizon and pitch ladder run the full width on purpose.
  window.gcsTapes = function (selector) {
    var cv = document.querySelector(selector);
    return cv ? (cv.tapeRects || null) : null;
  };

  window.gcsHudSafe = function (selector) {
    var cv = document.querySelector(selector);
    if (!cv) { return null; }
    var box = cv.getBoundingClientRect();
    var a = safeArea(cv);
    return { left: box.left + a.left, right: box.right - a.right,
             top: box.top + a.top, bottom: box.bottom - a.bottom };
  };

  // For tools/test_flight_display.py: where the home marker lands for a
  // given aircraft state. Reading it off a canvas would prove nothing;
  // whether it points at the right patch of ground is the whole question.
  window.gcsHomePoint = function (selector) {
    var cv = document.querySelector(selector);
    if (!cv) { return null; }
    var w = cv.cssW || cv.clientWidth, h = cv.cssH || cv.clientHeight;
    return homePoint(cv, w, h, telemetry(), safeArea(cv));
  };

  window.gcsHudState = function () {
    updateLowAlt();
    updateSink();
    var b = banner();
    return { text: b.text, level: b.level, colour: levelColour(b.level),
             lowArmed: low.armed, lowActive: low.active,
             sinkActive: sink.active, sinkRate: Math.round(sink.rate * 10) / 10,
             battery: batteryLevel() };
  };

  // ---------- the wheel over the height tape ----------
  // Put the pointer on the m AGL tape and spin the wheel to climb or
  // descend. Asked for 13 Oct 2026, and it is the gesture people try
  // first - the number is right there and the wheel is under the hand.
  //
  // The tape is painted on a canvas, so there is no element to hang a
  // listener on. The rectangle the gauge drew it in is already published
  // as cv.tapeRects for the tests, and the hit test uses the same figures,
  // which means the live area is exactly the tape that is visible rather
  // than a guess at where it probably is.
  //
  // ONE COMMAND PER BURST. A wheel notch is a repeat event; sending per
  // notch would put a dozen altitude changes on the wire for one flick.
  // The target moves immediately on screen and is sent once the wheel
  // stops, which is also what makes it safe to overshoot and come back.
  var ALT_STEP_M = 5;
  var ALT_MIN_M = 5, ALT_MAX_M = 120;     // plugins/climb_to.py's own limits
  var wheelAlt = { target: null, timer: null, until: 0 };

  function altTapeHit(cv, event) {
    var rects = cv.tapeRects;
    if (!rects || !rects.alt) { return false; }
    var box = cv.getBoundingClientRect();
    if (!box.width || !box.height) { return false; }
    // cv.cssW is the width the gauge drew in; the element may be scaled by
    // CSS, so the pointer is converted into that space rather than assumed
    // to be in it.
    var x = (event.clientX - box.left) * ((cv.cssW || box.width) / box.width);
    var y = (event.clientY - box.top) * ((cv.cssH || box.height) / box.height);
    var a = rects.alt;
    return x >= a.left && x <= a.right && y >= a.top && y <= a.bottom;
  }

  function wheelAltSend() {
    var want = wheelAlt.target;
    wheelAlt.target = null;
    if (want === null) { return; }
    fetch('/action/climb_to?altitude_m=' + want)
      .then(function (r) { return r.text(); })
      .then(function (text) {
        // The plugin refuses on the ground and says why; show its own
        // words rather than inventing a second explanation here.
        var bad = /not sent|fail|refus/i.test(text);
        window.gcsAnnounce(bad ? text : ('Climbing to ' + want + ' m'),
                           bad ? 'warn' : 'info', bad ? 6 : 3);
      })
      .catch(function () {
        window.gcsAnnounce('The station did not answer.', 'warn', 5);
      });
  }

  document.addEventListener('wheel', function (event) {
    var cv = event.target;
    if (!cv || cv.tagName !== 'CANVAS' || !cv.tapeRects) { return; }
    if (!altTapeHit(cv, event)) { return; }
    event.preventDefault();

    // Start from where the aircraft actually is, not from zero, unless a
    // burst is already running - then keep counting from the pending
    // figure so a long spin adds up.
    if (wheelAlt.target === null || Date.now() > wheelAlt.until) {
      var now = telemetry().altitude_m;
      wheelAlt.target = Math.round(((now != null ? now : 0)) / ALT_STEP_M)
                        * ALT_STEP_M;
    }
    wheelAlt.target += (event.deltaY < 0) ? ALT_STEP_M : -ALT_STEP_M;
    wheelAlt.target = Math.max(ALT_MIN_M, Math.min(ALT_MAX_M, wheelAlt.target));
    wheelAlt.until = Date.now() + 1500;
    window.gcsAnnounce('Height ' + wheelAlt.target + ' m - release to send',
                       'info', 2);
    if (wheelAlt.timer) { clearTimeout(wheelAlt.timer); }
    wheelAlt.timer = setTimeout(function () {
      wheelAlt.timer = null;
      wheelAltSend();
    }, 450);
  }, { passive: false });

  // For tools/test_flight_display.py: whether a point lands on the height
  // tape, and what the wheel would do from a given state.
  window.gcsAltWheel = function (selector, clientX, clientY) {
    var cv = document.querySelector(selector);
    if (!cv) { return null; }
    return { hit: altTapeHit(cv, { clientX: clientX, clientY: clientY }),
             step: ALT_STEP_M, min: ALT_MIN_M, max: ALT_MAX_M,
             pending: wheelAlt.target };
  };

  window.gcsDrawHud = function () {
    updateLowAlt();
    updateSink();
    speakBanner(banner());
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
            .replace("__LOW_ALT_ARM_M__", repr(LOW_ALT_ARM_M))
            .replace("__SINK_WATCH_M__", repr(SINK_WATCH_M))
            .replace("__PULL_UP_SECONDS__", repr(PULL_UP_SECONDS))
            .replace("__SINK_RATE_MIN_MS__", repr(SINK_RATE_MIN_MS))
            .replace("__BATTERY_LOW_PCT__", repr(BATTERY_LOW_PCT))
            .replace("__BATTERY_CRITICAL_PCT__", repr(BATTERY_CRITICAL_PCT)))
