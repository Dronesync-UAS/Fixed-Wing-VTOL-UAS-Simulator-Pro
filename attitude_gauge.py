"""
The round attitude indicator - the "gyro" - as one implementation.

Written 13 Oct 2026. It had lived inside the console page, and the
QGC-shaped console needed the same gauge beside its compass. Two copies of
a hundred and sixty lines of canvas drawing would have drifted apart
within a week, and the one that drifted would be the one nobody happened
to be looking at.

WHAT IT DRAWS, and why it is this rather than an airliner's PFD: a roll
scale round the top, glass showing sky over ground with a LABELLED pitch
ladder, and a fixed yellow aircraft symbol. The heading sits in a window
in the lower half, where an EFIS puts it, rather than on a needle - a
needle on an attitude indicator is not a thing real panels have.

The ladder spans plus and minus 30 degrees, which is what a real attitude
indicator shows. It was plus and minus 26 once: a figure chosen to make
the numbers fit rather than to match anything.

USE: put a <canvas> on the page and call

    window.gcsDrawAttitude('<canvas id>')

on a timer. It reads window.gcsTelemetry, which every page here keeps up
to date, so nothing has to be passed to it.
"""

BODY = r'''
window.gcsDrawAttitude = function (id, size) {
  var t = window.gcsTelemetry || {};
  var GY = size || 184;
  var gy = document.getElementById(id);
  if (!gy) { return; }
  var gctx = gy.getContext('2d');

  function gyroFit() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var px = Math.round(GY * dpr);
    if (gy.width !== px) { gy.width = px; gy.height = px; }
    gctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  }

  // The classic instrument colours, flattened to one tone each. The sky
  // and ground of an attitude indicator are the one thing about it nobody
  // should restyle - a blue-over-brown horizon is how it is read at a
  // glance - so they stay, without the gradients.
  var SKY = '#3c7fb1';
  var GND = '#6b4b2a';
  // The compass needle's red, so the moving part of both gauges matches.
  var ROSE_RED = '#e2473f';

  function drawGyro() {
    gyroFit();
    var S = GY, c = S / 2, R = c - 13;
    var roll = t.roll_deg || 0, pitch = t.pitch_deg || 0;
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

    // FLAT COLOUR, NOT A GRADIENT. The compass beside this one is drawn
    // flat - thin white ticks on the panel colour, one weight of line, no
    // shading - and this was drawn as a moulded instrument: gradient sky
    // and ground, a gloss highlight over the glass, a gradient bezel and
    // black outlines behind every number. Side by side they read as two
    // instruments from two different aircraft. Asked for on 14 Oct 2026:
    // "align design style as the compass maintaining classic
    // representation of the gyroscope gauge design".
    //
    // So the TREATMENT changes and the INSTRUMENT does not. Sky over
    // ground, a horizon that rolls and pitches, a numbered pitch ladder, a
    // fixed bank scale with a rolling pointer and a fixed aircraft symbol
    // are what an attitude indicator is, and all of them stay.
    gctx.fillStyle = SKY; gctx.fillRect(-S, -S * 2, S * 2, S * 2);
    gctx.fillStyle = GND; gctx.fillRect(-S, 0, S * 2, S * 2);

    gctx.strokeStyle = '#ffffff'; gctx.lineWidth = 2;
    gctx.beginPath(); gctx.moveTo(-S, 0); gctx.lineTo(S, 0); gctx.stroke();

    // A real pitch ladder is read by its numbers, not by counting rungs.
    // The compass's own type: sans-serif, and no black outline behind it -
    // the rose has none, and on flat fill nothing needs one.
    gctx.font = 'bold 11px -apple-system, sans-serif';
    gctx.textAlign = 'center'; gctx.textBaseline = 'middle';
    for (var d = -30; d <= 30; d += 5) {
      if (d === 0) { continue; }
      var y = -d * pxPerDeg, ten = (d % 10 === 0), half = ten ? 26 : 13;
      gctx.lineWidth = ten ? 2 : 1.5;
      // The rose draws its minor ticks at 0.35 and its cardinals solid.
      gctx.strokeStyle = ten ? 'rgba(255,255,255,0.9)'
                             : 'rgba(255,255,255,0.45)';
      gctx.beginPath(); gctx.moveTo(-half, y); gctx.lineTo(half, y); gctx.stroke();
      if (ten) {
        gctx.fillStyle = 'rgba(255,255,255,0.9)';
        gctx.fillText(Math.abs(d), -half - 12, y);
        gctx.fillText(Math.abs(d), half + 12, y);
      }
    }
    gctx.restore();
    gctx.restore();

    // --- the bank scale -----------------------------------------------
    // No bezel ring is drawn any more. #gyrobox and #rose already carry
    // the same disc - var(--panel), a 1 px var(--edge) border and the same
    // blur - so the gauge painted a second, heavier rim inside the one the
    // page had already drawn. Removing it is what makes the pair match.
    gctx.strokeStyle = 'rgba(255,255,255,0.45)'; gctx.lineCap = 'butt';
    [-60, -45, -30, -20, -10, 10, 20, 30, 45, 60].forEach(function (a) {
      var ar = (a - 90) * Math.PI / 180;
      var big = (a % 30 === 0), r2 = R + (c - R) * (big ? 0.92 : 0.6);
      gctx.lineWidth = big ? 2 : 1.5;
      gctx.strokeStyle = big ? 'rgba(255,255,255,0.9)'
                             : 'rgba(255,255,255,0.45)';
      gctx.beginPath();
      gctx.moveTo(c + Math.cos(ar) * R, c + Math.sin(ar) * R);
      gctx.lineTo(c + Math.cos(ar) * r2, c + Math.sin(ar) * r2);
      gctx.stroke();
    });
    // Wings level, at the top. The rose's own index is a plain filled
    // triangle, so this is one too.
    gctx.fillStyle = 'rgba(255,255,255,0.9)';
    gctx.beginPath();
    gctx.moveTo(c, c - R); gctx.lineTo(c - 6, c - R - 9); gctx.lineTo(c + 6, c - R - 9);
    gctx.closePath(); gctx.fill();

    // The bank pointer, which rolls with the aircraft. Red, the same red
    // the compass needle uses, so the one moving part of each gauge is the
    // same colour on both.
    var pa = (-roll - 90) * Math.PI / 180;
    gctx.fillStyle = ROSE_RED;
    gctx.beginPath();
    gctx.moveTo(c + Math.cos(pa) * (R - 2), c + Math.sin(pa) * (R - 2));
    gctx.lineTo(c + Math.cos(pa - 0.085) * (R - 16), c + Math.sin(pa - 0.085) * (R - 16));
    gctx.lineTo(c + Math.cos(pa + 0.085) * (R - 16), c + Math.sin(pa + 0.085) * (R - 16));
    gctx.closePath(); gctx.fill();

    // --- the fixed aircraft symbol ------------------------------------
    function wings() {
      gctx.beginPath();
      gctx.moveTo(c - 54, c); gctx.lineTo(c - 20, c); gctx.lineTo(c - 20, c + 10);
      gctx.moveTo(c + 54, c); gctx.lineTo(c + 20, c); gctx.lineTo(c + 20, c + 10);
      gctx.stroke();
    }
    gctx.lineCap = 'round'; gctx.lineJoin = 'round';
    gctx.strokeStyle = '#ffffff'; gctx.lineWidth = 3; wings();
    gctx.fillStyle = '#ffffff';
    gctx.beginPath(); gctx.arc(c, c, 3, 0, 7); gctx.fill();

    // --- bank in figures ----------------------------------------------
    // Where the rose puts its heading: beneath the centre, plain white
    // sans-serif, no box and no outline. The heading window this gauge
    // used to carry is gone - the compass sits immediately beside it and
    // shows the heading in large type, so the gyro was repeating its
    // neighbour inside a bordered box that was the most moulded-looking
    // thing on it. Bank angle is this instrument's own number.
    var bankTxt = Math.abs(roll) < 1 ? '0\u00b0'
                : Math.abs(Math.round(roll)) + '\u00b0 '
                  + (roll > 0 ? 'R' : 'L');
    gctx.font = '600 18px -apple-system, sans-serif';
    gctx.textAlign = 'center'; gctx.textBaseline = 'middle';
    gctx.fillStyle = Math.abs(roll) > 45 ? ROSE_RED : '#ffffff';
    gctx.fillText(bankTxt, c, c + R * 0.62);
  }
  drawGyro();
};
'''


def script():
    """The gauge, as a <script> block ready to drop into a page."""
    return "<script>\n(function () {\n" + BODY + "\n})();\n</script>\n"
