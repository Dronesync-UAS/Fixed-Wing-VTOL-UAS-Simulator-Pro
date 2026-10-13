"""
The slippy-map backdrop: Google Hybrid tiles, drawn under the flight track.

WHAT IT REPLACES
----------------
One satellite image, fetched once, 2.04 metres per pixel, stretched to
whatever zoom the instructor had chosen. Tiles are fetched per zoom level
and go to better than 0.3 m/px, which is what makes QGC's map readable
when you zoom in and ours was not.

WHERE IT DRAWS
--------------
Into the SAME canvas and the SAME axes the track already uses:
instructor_station's drawPath works in metres from home, with east as +x
and north as -y, and hands this function the home pixel (ox, oy) and the
scale in pixels per metre. So the tiles land registered to the track at
every zoom, for the same reason the single image did.

OPT-IN. The page sets window.gcsTileMap = true before this is of any use.
The existing console does not, so it keeps the single image and nothing
about it changes; the QGC-shaped console does.

WHY THE ZOOM IS CHOSEN, NOT SET
-------------------------------
A tile at zoom z covers 156543.03 * cos(lat) / 2^z metres per pixel. The
zoom picked is the one whose metres-per-pixel is closest to the canvas's
own, so a tile pixel is about a screen pixel: lower and it is blurry,
higher and the station fetches four times the tiles for no visible gain.

MISSES ARE COUNTED, NOT HIDDEN. A tile QGC has never cached comes back
404. Drawing nothing and saying nothing would leave an instructor staring
at an empty grid wondering what broke, so the misses are counted and the
page can say "this area has not been downloaded in QGroundControl yet".
"""


def script():
    """The tile drawing, as a <script> block."""
    return "<script>\n(function () {\n" + BODY + "\n})();\n</script>\n"


BODY = r"""
// Tiles already fetched, by "z/x/y". Images are kept rather than re-asked
// for: the browser would cache them anyway, but an Image object avoids the
// decode on every frame, and the map redraws once a second.
var tileCache = {};
var tileStats = { want: 0, have: 0, missing: 0 };
var TILE_PX = 256;
var EARTH_C = 40075016.686;      // equator, metres

function tileMetresPerPixel(lat, z) {
  return EARTH_C * Math.cos(lat * Math.PI / 180) / (TILE_PX * Math.pow(2, z));
}

// Web Mercator, the same arithmetic map_tiles.py uses on the other side.
function lonToTileX(lon, z) { return (lon + 180) / 360 * Math.pow(2, z); }
function latToTileY(lat, z) {
  var r = lat * Math.PI / 180;
  return (1 - Math.asinh(Math.tan(r)) / Math.PI) / 2 * Math.pow(2, z);
}

function pickZoom(lat, metresPerPixel) {
  // The zoom whose tile resolution is nearest the canvas's own, clamped to
  // what Google serves.
  var best = 17, bestErr = Infinity;
  for (var z = 3; z <= 21; z++) {
    var err = Math.abs(Math.log(tileMetresPerPixel(lat, z) / metresPerPixel));
    if (err < bestErr) { bestErr = err; best = z; }
  }
  return best;
}

function getTile(z, x, y, onLoad) {
  var key = z + '/' + x + '/' + y;
  var hit = tileCache[key];
  if (hit) { return hit.ok ? hit.img : null; }
  var img = new Image();
  var entry = { img: img, ok: false };
  tileCache[key] = entry;
  img.onload = function () { entry.ok = true; if (onLoad) { onLoad(); } };
  img.onerror = function () { entry.ok = false; entry.missing = true; };
  img.src = '/tile/' + z + '/' + x + '/' + y;
  return null;
}

// Draw the backdrop. (ox, oy) is where HOME sits on the canvas and scale is
// pixels per metre - exactly what drawPath already worked out.
window.gcsDrawTiles = function (ctx, W, H, ox, oy, scale, homeLat, homeLon,
                                onLoad) {
  if (!window.gcsTileMap || homeLat == null || homeLon == null) { return false; }
  var metresPerPixel = 1 / scale;
  var z = pickZoom(homeLat, metresPerPixel);
  var n = Math.pow(2, z);

  // Home's position in fractional tile space, and how many metres one tile
  // covers at this latitude. Everything else follows from those two.
  var hx = lonToTileX(homeLon, z), hy = latToTileY(homeLat, z);
  var tileMetres = tileMetresPerPixel(homeLat, z) * TILE_PX;
  var tilePx = tileMetres * scale;              // one tile, in canvas pixels
  if (!isFinite(tilePx) || tilePx <= 0) { return false; }

  // Which tiles touch the canvas. The canvas spans (0,0)-(W,H), and home is
  // at (ox, oy), so the left edge is (0 - ox) / tilePx tiles west of home.
  var x0 = Math.floor(hx + (0 - ox) / tilePx);
  var x1 = Math.ceil(hx + (W - ox) / tilePx);
  var y0 = Math.floor(hy + (0 - oy) / tilePx);
  var y1 = Math.ceil(hy + (H - oy) / tilePx);

  // A sane ceiling. A deep zoom over a large canvas could otherwise ask for
  // thousands of tiles in one frame and lock the browser up.
  if ((x1 - x0) * (y1 - y0) > 400) { return false; }

  tileStats = { want: 0, have: 0, missing: 0, zoom: z };
  for (var tx = x0; tx <= x1; tx++) {
    for (var ty = y0; ty <= y1; ty++) {
      if (tx < 0 || ty < 0 || tx >= n || ty >= n) { continue; }
      tileStats.want++;
      var px = ox + (tx - hx) * tilePx;
      var py = oy + (ty - hy) * tilePx;
      var img = getTile(z, tx, ty, onLoad);
      if (img) {
        tileStats.have++;
        // +1 on the size closes the hairline seams that rounding leaves
        // between neighbouring tiles.
        ctx.drawImage(img, px, py, tilePx + 1, tilePx + 1);
        continue;
      }

      // FALL BACK TO A PARENT TILE. QGC caches whatever zoom it happened
      // to be looking at, so asking for the zoom that best fits this
      // canvas usually misses: measured on 14 Oct 2026, the Nullarbor had
      // full coverage at zoom 17 and none at the zoom 20 this picked.
      // Every map does this - draw the quarter of the parent that covers
      // the same ground, blurred but present, rather than a hole.
      var drew = false;
      for (var up = 1; up <= 5 && !drew; up++) {
        var pz = z - up;
        if (pz < 3) { break; }
        var step = Math.pow(2, up);
        var ax = Math.floor(tx / step), ay = Math.floor(ty / step);
        var parent = getTile(pz, ax, ay, onLoad);
        if (!parent) { continue; }
        // Which part of the ancestor covers this tile.
        var sub = TILE_PX / step;
        var sx = (tx - ax * step) * sub;
        var sy = (ty - ay * step) * sub;
        ctx.drawImage(parent, sx, sy, sub, sub, px, py, tilePx + 1, tilePx + 1);
        drew = true;
        tileStats.have++;
        tileStats.fromParent = (tileStats.fromParent || 0) + 1;
      }
      if (!drew) {
        var entry = tileCache[z + '/' + tx + '/' + ty];
        if (entry && entry.missing) { tileStats.missing++; }
      }
    }
  }
  return tileStats.have > 0;
};

window.gcsTileStats = function () { return tileStats; };
"""
