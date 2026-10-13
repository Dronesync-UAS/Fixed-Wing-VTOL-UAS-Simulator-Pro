"""
The map, served from QGroundControl's own tile cache.

WHY
---
The station's plan view was one satellite image, fetched once and frozen:
1964 px across 4 km, which is 2.04 metres per pixel, and zooming in just
made those pixels bigger. QGC's map is sharper because it is a TILE
PYRAMID - it fetches 256 px tiles for whatever zoom you are at, down to
zoom 22, which is better than 0.3 m per pixel.

Rather than build a second tile fetcher, this reads the tiles QGC has
already downloaded. The instructor sees the same imagery on both screens,
nothing is downloaded twice, and no new terms apply to the pictures -
they are already on the machine and QGC fetched them under its own.

HOW THE CACHE WORKS, read from QGC v5.1.5's own source rather than guessed
--------------------------------------------------------------------------
~/.cache/QGroundControl/QGroundControl/QGCMapCache/qgcMapCache.db, SQLite,
table Tiles(tileID, hash, format, tile, size, type, date).

src/QtLocationPlugin/QGCMapUrlEngine.cpp:

    QString UrlFactory::getTileHash(QStringView type, int x, int y, int z)
    {
        const int hash = hashFromProviderType(type);
        return QString::asprintf("%010d%08d%08d%03d", hash, x, y, z);
    }

so the hash is provider(10) + x(8) + y(8) + zoom(3), zero padded. Verified
against the cache on this machine: the first row decodes to x=21117,
y=50828, z=17, which is 37.4138 N, 122.0004 W - Mountain View, QGC's
default map position, exactly where a first run would cache tiles.

The provider number is the index of the provider in UrlFactory::_providers,
counting from 1 (MapProvider.cpp: `_mapId(_mapIdIndex++)`, `_mapIdIndex = 1`).
That list begins Google Street, Google Satellite, Google Terrain, Google
Hybrid, Google Labels, Bing Road, Bing Satellite, Bing Hybrid - so Google
Hybrid is 4, which is what this machine's QGC is set to
(QGroundControl.ini: mapProvider=Google, mapType=Hybrid) and which holds
1,230 of the cached tiles.

WHAT IS NOT HERE
----------------
Downloading. This only reads. A training area QGC has never looked at has
no tiles, and the answer is QGC's own Offline Maps download, not a second
fetcher in here - partly because that would double the traffic, and partly
because whose terms the imagery sits under is not a decision for this file.

READ-ONLY, DELIBERATELY. QGC may be running and writing to this database
while we read it. The connection is opened mode=ro so a bug here can never
corrupt an instructor's map cache.
"""

import math
import os
import sqlite3
import threading

CACHE = os.path.expanduser(
    "~/.cache/QGroundControl/QGroundControl/QGCMapCache/qgcMapCache.db")

# UrlFactory::_providers order, from 1. Only the ones worth offering.
PROVIDERS = {
    1: "Google Street Map",
    2: "Google Satellite",
    3: "Google Terrain",
    4: "Google Hybrid",
    5: "Google Labels",
    6: "Bing Road",
    7: "Bing Satellite",
    8: "Bing Hybrid",
}
# What this machine's QGC is set to. Changing QGC's provider changes which
# tiles are cached, so this is a default and not a rule - see available().
DEFAULT_PROVIDER = 4

_local = threading.local()


def _connect():
    """One read-only connection per thread. sqlite3 objects are not safe to
    share across threads and the station is threaded."""
    if getattr(_local, "db", None) is None:
        if not os.path.isfile(CACHE):
            return None
        try:
            _local.db = sqlite3.connect(
                "file:%s?mode=ro" % CACHE, uri=True, timeout=2.0)
        except sqlite3.Error:
            return None
    return _local.db


def tile_hash(provider, x, y, z):
    """QGC's own format: provider(10) + x(8) + y(8) + zoom(3)."""
    return "%010d%08d%08d%03d" % (provider, x, y, z)


def tile(z, x, y, provider=DEFAULT_PROVIDER):
    """One tile as bytes, or None if QGC has not cached it."""
    db = _connect()
    if db is None:
        return None
    try:
        row = db.execute("SELECT tile FROM Tiles WHERE hash=?",
                         (tile_hash(provider, x, y, z),)).fetchone()
    except sqlite3.Error:
        return None
    return bytes(row[0]) if row else None


def available(provider=None):
    """What the cache holds: tiles per provider, and the zooms they cover.

    Used by the console to say "no imagery for this area yet, download it
    in QGC" rather than showing an empty grid and leaving the instructor to
    work out why."""
    db = _connect()
    if db is None:
        return {"cache": CACHE, "present": False, "providers": []}
    out = []
    try:
        rows = db.execute(
            "SELECT type, COUNT(*) FROM Tiles GROUP BY type").fetchall()
        for kind, count in rows:
            if provider is not None and kind != provider:
                continue
            zooms = db.execute(
                "SELECT MIN(CAST(SUBSTR(hash, 27) AS INTEGER)), "
                "       MAX(CAST(SUBSTR(hash, 27) AS INTEGER)) "
                "FROM Tiles WHERE type=?", (kind,)).fetchone()
            out.append({"provider": kind,
                        "name": PROVIDERS.get(kind, "provider %d" % kind),
                        "tiles": count,
                        "min_zoom": zooms[0], "max_zoom": zooms[1]})
    except sqlite3.Error as exc:
        return {"cache": CACHE, "present": True, "error": str(exc),
                "providers": []}
    out.sort(key=lambda p: -p["tiles"])
    return {"cache": CACHE, "present": True, "providers": out}


# ---------------------------------------------------------------------------
# The usual slippy-map arithmetic. Here rather than in the page so the
# station can answer "which tiles cover this training area" for the
# coverage check, and so it is testable without a browser.
# ---------------------------------------------------------------------------

def lonlat_to_tile(lon, lat, z):
    n = 2.0 ** z
    x = int((lon + 180.0) / 360.0 * n)
    lat_r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_r)) / math.pi) / 2.0 * n)
    return x, y


def tile_to_lonlat(x, y, z):
    n = 2.0 ** z
    lon = x / n * 360.0 - 180.0
    lat = math.degrees(math.atan(math.sinh(math.pi * (1.0 - 2.0 * y / n))))
    return lon, lat


def coverage(lat, lon, z, span_tiles=3, provider=DEFAULT_PROVIDER):
    """How many of the tiles around a point are cached, 0.0 to 1.0.

    The console asks this for the training area's centre before it draws,
    so it can say plainly that the area has not been downloaded yet."""
    cx, cy = lonlat_to_tile(lon, lat, z)
    half = span_tiles // 2
    have = total = 0
    for dx in range(-half, half + 1):
        for dy in range(-half, half + 1):
            total += 1
            if tile(z, cx + dx, cy + dy, provider) is not None:
                have += 1
    return (have / total) if total else 0.0
