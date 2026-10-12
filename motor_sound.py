"""
The aircraft's motors, as sound.

Added 12 Oct 2026, on request: "very realistic sound from the aircraft
motors both 4 motors as VTOL and specific sound of forward motor when
activated", with an on/off switch.

WHERE THE SOUND COMES FROM
--------------------------
It is synthesised in the browser with WebAudio. There is no sound file,
which matters for two reasons: nothing extra has to be installed or
copied onto a teaching machine, and the note can follow the throttle
continuously instead of being a loop that is obviously a loop.

WHAT MAKES A ROTOR SOUND LIKE A ROTOR
-------------------------------------
Three things, layered per rotor:

  * the BLADE-PASS tone - one blade going past per revolution per blade,
    so two blades at N revolutions a second give a tone at 2N. This is the
    pitch you hear;
  * its HARMONICS, which is what makes it a rotor rather than a flute. A
    plain sine reads as a test signal;
  * BROADBAND AIR NOISE, band-passed around the blade frequency. This is
    most of the actual loudness of a real rotor, and leaving it out was the
    single biggest reason an early version sounded like a synthesiser.

The four hover rotors are run as four separate voices, slightly detuned
from each other. That detuning is the point: real rotors are never exactly
in step, and the slow throb you hear from a hovering multirotor is the
beating between them. One voice for all four does not produce it.

WHY THE PUSHER SOUNDS DIFFERENT
-------------------------------
It is a different motor in the model, and it is given a different voice:
a lower fundamental, stronger upper harmonics and an added electrical
whine well above the blade tone. That combination is what makes a
fixed-wing pusher sound hard and buzzy next to the softer beating of the
hover rotors.

WHICH FIGURES ARE REAL AND WHICH WERE CHOSEN BY EAR
---------------------------------------------------
Real, read out of the aircraft model (PX4-gazebo-models
models/standard_vtol/model.sdf):

  * four hover rotors, maxRotVelocity 1500 rad/s, motorConstant 2e-05
    (lines 762-763 and the three repeats);
  * one pusher, rotor_puller, maxRotVelocity 3500 rad/s, motorConstant
    8.54858e-06 (lines 833-834);
  * rotors 0 and 1 turn CCW, rotors 2 and 3 CW (lines 759-812) - the same
    directions the motor-test diagram draws.

So the model does treat the pusher as a different, faster-spinning motor,
and that difference is honoured here. The audible FREQUENCIES below,
however, were chosen by ear. They are NOT the model's rotor speeds
converted to a pitch, and they are not presented as such: 1500 rad/s is
about 14,300 rpm and 3500 rad/s about 33,400 rpm, which are simulation
tuning values rather than propeller speeds - taken literally the pusher
would sing at over a kilohertz. Nothing in the simulator publishes a real
propeller RPM, so there is nothing truer available to drive this from.

WHAT DRIVES IT
--------------
Only telemetry the station already has:

  * throttle_pct - PX4's own operator-feedback throttle out of VFR_HUD
    (streams/VFR_HUD.hpp lines 92-110: 100 * max of the two thrust
    setpoint magnitudes while armed, 0 while disarmed). PX4's comment
    there says a VTOL has no single throttle during a transition, so this
    is a heuristic. It is fine for driving a sound and is not a number to
    teach from;
  * armed - nothing turns until the aircraft is armed;
  * vtol_state - which half of the aircraft is flying, out of
    EXTENDED_SYS_STATE.

The hover rotors are audible in hover and through both transitions, and
go quiet in fixed-wing flight, because that is when PX4 stops them. The
pusher is audible in fixed-wing flight and spins up during the forward
transition; it is stopped again for the back-transition to hover, so it
goes quiet then.

NO DISTANCE MODELLING. The listener is treated as being on the aircraft,
which is where both camera views are. There is no doppler and no fall-off
with range, so the sound does not change when the map view is showing.

WHAT HAS BEEN TESTED. tools/test_motor_sound.py drives the state machine
in a real browser against fake telemetry and checks which voices come up,
whether the pitch follows the throttle, and that the switch silences it.
Whether it SOUNDS right is a judgement nobody has made yet - no one has
listened to it with Gazebo and PX4 running.

A BROWSER WILL NOT MAKE A NOISE UNTIL THE PAGE HAS BEEN CLICKED. That is
the browser's autoplay rule, not a fault here. The console shares one
audio context with the warning tones (window.gcsAudio in
flight_display.py), so the first click anywhere on the page unlocks both.
"""

# Two-blade propellers, so the blade-pass tone is twice the revolution
# rate. Only used to keep the comments honest - the frequencies below are
# already blade-pass frequencies.
BLADES = 2

# The audible band for the four hover rotors, idle to full throttle.
# Chosen by ear for a large multirotor: a throb you feel rather than a
# whine. See the docstring for why these are not derived from the model.
HOVER_IDLE_HZ = 95.0
HOVER_FULL_HZ = 255.0

# The pusher. Lower at the bottom end and reaching higher, with the
# harmonics and the whine below doing the work of making it sound harder.
PUSHER_IDLE_HZ = 120.0
PUSHER_FULL_HZ = 310.0

# How far apart the four hover rotors are detuned, as a fraction. These
# produce the beating; without them four voices sum into one. Kept under
# 2% so it reads as throb rather than as four aircraft.
ROTOR_DETUNE = [-0.017, -0.006, 0.007, 0.018]

# An armed aircraft's rotors are turning even with the stick down, so the
# throttle is floored before it becomes a pitch. Without this, arming is
# silent and the first sound is the takeoff, which is wrong.
IDLE_FLOOR = 0.12

# Seconds for a voice to fade in or out. PX4 ramps its motors; a hard cut
# sounds like a fault.
FADE_S = 0.45

# Per-voice loudness before the volume slider. Five voices sum, so these
# are small on purpose; the compressor in the chain catches the rest.
HOVER_VOICE_GAIN = 0.20
PUSHER_VOICE_GAIN = 0.34


STYLE = """
<style>
  /* The motor-sound row in the settings window. The volume slider is
     narrow deliberately - it sits beside the switch, not under it. */
  #motor-volume { width: 104px; }
  .set-inline { display: flex; align-items: center; gap: 10px; }
</style>
"""


SCRIPT = """
<script>
(function () {
  'use strict';

  var DETUNE = __DETUNE__;
  var HOVER_IDLE = __HOVER_IDLE_HZ__, HOVER_FULL = __HOVER_FULL_HZ__;
  var PUSHER_IDLE = __PUSHER_IDLE_HZ__, PUSHER_FULL = __PUSHER_FULL_HZ__;
  var IDLE_FLOOR = __IDLE_FLOOR__;
  var FADE = __FADE_S__;
  var HOVER_GAIN = __HOVER_VOICE_GAIN__, PUSHER_GAIN = __PUSHER_VOICE_GAIN__;

  function telemetry() {
    return (window.gcsTelemetry && typeof window.gcsTelemetry === 'object')
      ? window.gcsTelemetry : {};
  }

  function soundOn() {
    var box = document.getElementById('motor-sound-on');
    return box ? box.checked : false;
  }

  function volume() {
    var slider = document.getElementById('motor-volume');
    var v = slider ? Number(slider.value) : 60;
    if (!isFinite(v)) { v = 60; }
    return Math.max(0, Math.min(100, v)) / 100;
  }

  // ---------- the noise bed ----------
  // Two seconds of noise, looped. One-pole filtered on the way in so it
  // leans low - white noise straight out of Math.random() is all treble
  // and sounds like radio hiss, not like air off a blade.
  var noise = null;
  function noiseBuffer(ctx) {
    if (noise) { return noise; }
    var frames = Math.floor(ctx.sampleRate * 2);
    noise = ctx.createBuffer(1, frames, ctx.sampleRate);
    var data = noise.getChannelData(0), last = 0;
    for (var i = 0; i < frames; i++) {
      var white = Math.random() * 2 - 1;
      last = last * 0.86 + white * 0.14;
      data[i] = last * 3.2;
    }
    return noise;
  }

  // ---------- one motor ----------
  // harmonics: multiples of the blade-pass frequency, with the waveform
  // and relative level of each. noiseMul/noiseQ place the air noise.
  function makeVoice(ctx, dest, spec) {
    var out = ctx.createGain();
    out.gain.value = 0;
    out.connect(dest);

    var parts = [];
    for (var i = 0; i < spec.harmonics.length; i++) {
      var h = spec.harmonics[i];
      var osc = ctx.createOscillator();
      osc.type = h.type;
      osc.frequency.value = HOVER_IDLE * h.mul;
      var g = ctx.createGain();
      g.gain.value = h.gain;
      osc.connect(g);
      g.connect(out);
      osc.start();
      parts.push({ osc: osc, mul: h.mul });
    }

    var src = ctx.createBufferSource();
    src.buffer = noiseBuffer(ctx);
    src.loop = true;
    var band = ctx.createBiquadFilter();
    band.type = 'bandpass';
    band.Q.value = spec.noiseQ;
    band.frequency.value = HOVER_IDLE * spec.noiseMul;
    var ng = ctx.createGain();
    ng.gain.value = spec.noise;
    src.connect(band);
    band.connect(ng);
    ng.connect(out);
    src.start();

    return {
      hz: 0,
      level: 0,
      set: function (hz, level) {
        var now = ctx.currentTime;
        if (hz !== this.hz) {
          for (var j = 0; j < parts.length; j++) {
            // setTargetAtTime rather than a step: a motor changes speed,
            // it does not teleport between two pitches.
            parts[j].osc.frequency.setTargetAtTime(
              Math.min(hz * parts[j].mul, 14000), now, 0.09);
          }
          band.frequency.setTargetAtTime(
            Math.min(hz * spec.noiseMul, 12000), now, 0.09);
          this.hz = hz;
        }
        if (level !== this.level) {
          out.gain.setTargetAtTime(level, now, FADE / 3);
          this.level = level;
        }
      }
    };
  }

  // A hover rotor: blade tone, two harmonics, and a wide noise bed.
  function hoverSpec() {
    return {
      harmonics: [
        { type: 'sawtooth', mul: 1, gain: 0.52 },
        { type: 'sine', mul: 2, gain: 0.26 },
        { type: 'sine', mul: 3, gain: 0.11 }
      ],
      noise: 0.42, noiseMul: 3.1, noiseQ: 0.9
    };
  }

  // The pusher. A square at the fundamental and a hard fifth-ish harmonic
  // give it the buzz; the 9x sine is the motor whine that tells an
  // instructor by ear, without looking, that the forward motor has come
  // in during a transition.
  function pusherSpec() {
    return {
      harmonics: [
        { type: 'square', mul: 1, gain: 0.34 },
        { type: 'sawtooth', mul: 2, gain: 0.30 },
        { type: 'sawtooth', mul: 3, gain: 0.17 },
        { type: 'sine', mul: 9, gain: 0.07 }
      ],
      noise: 0.30, noiseMul: 4.6, noiseQ: 1.5
    };
  }

  // ---------- the rig ----------
  var rig = null;
  function build(ctx) {
    if (rig && rig.ctx === ctx) { return rig; }
    var master = ctx.createGain();
    master.gain.value = 0;
    // Five voices summing will clip on a laptop's own speakers. The
    // compressor is here to stop that, not for effect.
    var squash = ctx.createDynamicsCompressor();
    squash.threshold.value = -16;
    squash.ratio.value = 5;
    // Takes the fizz off the top so it is bearable for a whole lesson.
    var tame = ctx.createBiquadFilter();
    tame.type = 'lowpass';
    tame.frequency.value = 5200;
    master.connect(squash);
    squash.connect(tame);
    tame.connect(ctx.destination);

    var rotors = [];
    for (var i = 0; i < DETUNE.length; i++) {
      rotors.push(makeVoice(ctx, master, hoverSpec()));
    }
    rig = { ctx: ctx, master: master, rotors: rotors,
            pusher: makeVoice(ctx, master, pusherSpec()) };
    return rig;
  }

  function silence() {
    if (!rig) { return; }
    rig.master.gain.setTargetAtTime(0, rig.ctx.currentTime, FADE / 3);
  }

  // ---------- what is running, and how hard ----------
  // Split out so the test can drive it without an audio context.
  window.gcsMotorDemand = function (t) {
    var thr = Number(t.throttle_pct);
    if (!isFinite(thr)) { thr = 0; }
    thr = Math.max(0, Math.min(100, thr)) / 100;

    var armed = !!t.armed;
    var vs = t.vtol_state || '';
    var fixedWing = (vs === 'Fixed wing');
    var toFixedWing = (vs === 'Transitioning to fixed wing');

    // PX4 stops the four hover motors once the standard_vtol is in
    // fixed-wing flight, and runs them through both transitions.
    var hover = (armed && !fixedWing) ? 1 : 0;
    // The pusher runs in fixed wing, and spins up during the forward
    // transition. The back-transition to hover is flown without it.
    var pusher = (armed && (fixedWing || toFixedWing)) ? 1 : 0;

    var effort = armed ? Math.max(thr, IDLE_FLOOR) : 0;
    return {
      hover: hover,
      pusher: pusher,
      effort: effort,
      hoverHz: HOVER_IDLE + (HOVER_FULL - HOVER_IDLE) * effort,
      pusherHz: PUSHER_IDLE + (PUSHER_FULL - PUSHER_IDLE) * effort
    };
  };

  function tick() {
    if (!soundOn() || !window.gcsAudio) { silence(); return; }
    var ctx = window.gcsAudio();
    // Still suspended means the page has not been clicked yet. Nothing to
    // report and nothing to fix - the first click starts it.
    if (!ctx || ctx.state !== 'running') { return; }
    var r = build(ctx);
    var d = window.gcsMotorDemand(telemetry());
    var vol = volume();

    r.master.gain.setTargetAtTime(vol, ctx.currentTime, FADE / 3);
    for (var i = 0; i < r.rotors.length; i++) {
      r.rotors[i].set(d.hoverHz * (1 + DETUNE[i]),
                      d.hover * HOVER_GAIN * (0.45 + 0.55 * d.effort));
    }
    r.pusher.set(d.pusherHz,
                 d.pusher * PUSHER_GAIN * (0.45 + 0.55 * d.effort));
  }

  // A test seam, and the answer to "is it actually doing anything?".
  window.gcsMotorSound = function () {
    var ctx = window.gcsAudio ? window.gcsAudio() : null;
    return {
      on: soundOn(),
      volume: volume(),
      waitingForClick: !!(ctx && ctx.state !== 'running'),
      built: !!rig,
      demand: window.gcsMotorDemand(telemetry()),
      rotorHz: rig ? rig.rotors.map(function (v) { return Math.round(v.hz); }) : [],
      rotorLevel: rig ? rig.rotors.map(function (v) { return v.level; }) : [],
      pusherHz: rig ? Math.round(rig.pusher.hz) : 0,
      pusherLevel: rig ? rig.pusher.level : 0
    };
  };

  // Switching it off should go quiet at once, not at the next tick.
  document.addEventListener('change', function (e) {
    if (e.target && e.target.id === 'motor-sound-on' && !e.target.checked) {
      silence();
    }
  });

  setInterval(tick, 80);
})();
</script>
"""


def script():
    """The motor sound's JavaScript, with the tuning figures filled in."""
    import json
    return (SCRIPT
            .replace("__DETUNE__", json.dumps(ROTOR_DETUNE))
            .replace("__HOVER_IDLE_HZ__", repr(HOVER_IDLE_HZ))
            .replace("__HOVER_FULL_HZ__", repr(HOVER_FULL_HZ))
            .replace("__PUSHER_IDLE_HZ__", repr(PUSHER_IDLE_HZ))
            .replace("__PUSHER_FULL_HZ__", repr(PUSHER_FULL_HZ))
            .replace("__IDLE_FLOOR__", repr(IDLE_FLOOR))
            .replace("__FADE_S__", repr(FADE_S))
            .replace("__HOVER_VOICE_GAIN__", repr(HOVER_VOICE_GAIN))
            .replace("__PUSHER_VOICE_GAIN__", repr(PUSHER_VOICE_GAIN)))
