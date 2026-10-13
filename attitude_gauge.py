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
    gctx.fillText(String(Math.round(t.heading_deg || 0)).padStart(3, '0') + '°',
                  c, hy + hh / 2 + 1);
    gctx.font = '600 8px -apple-system, sans-serif';
    gctx.fillStyle = 'rgba(255,255,255,0.65)';
    gctx.fillText('HDG', c, hy - 6);
  }
  drawGyro();
};
'''


def script():
    """The gauge, as a <script> block ready to drop into a page."""
    return "<script>\n(function () {\n" + BODY + "\n})();\n</script>\n"
