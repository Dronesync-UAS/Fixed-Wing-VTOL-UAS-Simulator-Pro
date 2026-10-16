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
import io
import os
import urllib.request
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


# ---------------------------------------------------------------------------
# Our own tiles, from Mapbox, cached on disk.
#
# WHY THIS EXISTS. Reading QGroundControl's cache gets the map for free and
# costs no extra traffic, but it only has what QGC has already looked at.
# Measured on the coast area, 14 Oct 2026: the canvas wanted zoom 20 and 34
# of its 54 tiles had to be drawn by blowing up an ancestor, so two thirds
# of the picture was an upscaled lower-zoom tile. That is what "the
# satellite map is of poor quality" was looking at, and no amount of
# drawing cleverness fixes a tile that was never downloaded.
#
# This project ALREADY fetches Mapbox satellite imagery for the world
# ground textures - tools/fetch_satellite.py, same token, same terms - so
# fetching map tiles the same way is not a new decision about imagery
# rights, it is the one already taken.
#
# @2x asks for 512 px tiles, which is twice the detail per tile that QGC's
# 256 px Google tiles carry.
#
# ORDER OF PREFERENCE, and it matters:
#   1. our own disk cache  - instant, works offline
#   2. Mapbox             - only when a token exists and the network is up
#   3. QGC's cache        - the old behaviour, so nothing got worse for
#                           anyone without a token
TILE_DIR = os.path.expanduser("~/.cache/uav_academy_gcs/tiles")
TOKEN_FILE = os.path.expanduser("~/.mapbox_token")

# WHERE OUR OWN TILES COME FROM.
#
# Esri World Imagery, which is what tools/fetch_satellite.py already uses
# for the world ground textures when no token is set. It needs NO token,
# serves every zoom everywhere, and returns ordinary 256 px tiles - which
# is exactly what the map draws in.
#
# NOTE THE URL ORDER: ArcGIS puts the ROW before the COLUMN, so it is
# {z}/{y}/{x}, not {z}/{x}/{y}. Getting that the wrong way round returns
# a perfectly valid tile of entirely the wrong place, which is the sort of
# wrong that looks like a map until somebody checks it against a coastline.
ESRI_URL = ("https://server.arcgisonline.com/ArcGIS/rest/services/"
            "World_Imagery/MapServer/tile/{z}/{y}/{x}")
ESRI_CREDIT = "Esri World Imagery - check Esri's terms of use"
ESRI_MAX_ZOOM = 21

# HYBRID, because that is what QGroundControl is showing.
# ~/.config/QGroundControl/QGroundControl.ini on this machine reads
# mapProvider=Google and mapType=Hybrid - satellite imagery with roads and
# place names drawn over it, not bare imagery. Asked for on 14 Oct 2026:
# "use same type of map".
#
# Google's own hybrid tiles are not ours to fetch - QGC has a key
# arrangement and this does not - so the same thing is built from Esri's
# own reference layers, which are transparent overlays meant for exactly
# this. Boundaries and places carries the labels; transportation carries
# the roads. Both return 200 at the zooms this uses, checked the same day.
ESRI_OVERLAYS = (
    ("https://server.arcgisonline.com/ArcGIS/rest/services/"
     "Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}"),
    ("https://server.arcgisonline.com/ArcGIS/rest/services/"
     "Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}"),
)
HYBRID_CREDIT = ("Esri World Imagery with Esri reference layers - "
                 "check Esri's terms of use")

# Set GCS_MAP_PLAIN=1 to get bare imagery with nothing drawn over it.
def _hybrid_wanted():
    return os.environ.get("GCS_MAP_PLAIN", "") not in ("1", "true", "yes")

# Mapbox is better again where it is licensed, but needs a working token.
# The one on this machine returned 401 Not Authorized when this was built
# on 14 Oct 2026, which is why it is not the default - and why anything
# relying on it should check rather than assume a token file means a
# working token.
MAPBOX_URL = ("https://api.mapbox.com/v4/mapbox.satellite/"
              "{z}/{x}/{y}@2x.jpg90?access_token={token}")
MAPBOX_MAX_ZOOM = 22

_token_cache = {"read": False, "value": None}


def mapbox_token():
    """The token, from the environment or ~/.mapbox_token. None if absent.

    Present is not the same as valid - see MAPBOX_URL above.
    """
    if _token_cache["read"]:
        return _token_cache["value"]
    value = os.environ.get("MAPBOX_TOKEN")
    if not value:
        try:
            with open(TOKEN_FILE) as handle:
                value = handle.read().strip()
        except OSError:
            value = None
    _token_cache["read"] = True
    _token_cache["value"] = value or None
    return _token_cache["value"]


def _disk_path(z, x, y):
    return os.path.join(TILE_DIR, str(z), str(x), "%d.jpg" % y)


def _from_disk(z, x, y):
    try:
        with open(_disk_path(z, x, y), "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _to_disk(z, x, y, blob):
    path = _disk_path(z, x, y)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Written under a temporary name first: a half-written tile that a
        # later run reads as complete is a corrupt picture nobody can
        # explain afterwards.
        temporary = path + ".part"
        with open(temporary, "wb") as handle:
            handle.write(blob)
        os.replace(temporary, path)
    except OSError:
        pass


def _download(url, timeout):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            if response.status != 200:
                return None
            return response.read() or None
    except Exception:
        # Offline, rate-limited, bad token, 404 over the sea - all the same
        # answer here, and none of them should take the console down.
        return None


def _overlay(base_blob, z, x, y, timeout):
    """Draw the reference layers over the imagery. None if it cannot be done.

    Returns JPEG bytes. Falling back to the bare imagery on any problem is
    deliberate: a map with no road names is a great deal better than no map,
    and Pillow not being importable should not cost the instructor a
    backdrop.
    """
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        base = Image.open(io.BytesIO(base_blob)).convert("RGBA")
    except Exception:
        return None
    drew = False
    for template in ESRI_OVERLAYS:
        blob = _download(template.format(z=z, y=y, x=x), timeout)
        if not blob:
            continue
        try:
            layer = Image.open(io.BytesIO(blob)).convert("RGBA")
        except Exception:
            continue
        if layer.size != base.size:
            layer = layer.resize(base.size)
        base = Image.alpha_composite(base, layer)
        drew = True
    if not drew:
        return None
    out = io.BytesIO()
    base.convert("RGB").save(out, format="JPEG", quality=88)
    return out.getvalue()


def fetch_tile(z, x, y, timeout=8.0):
    """One satellite tile for (z, x, y) from our own source, or None.

    Disk first, so a tile is fetched once and then costs nothing and works
    offline. Then Esri. Then Mapbox, but only if a token is set - and a
    401 simply means None, same as being offline.
    """
    if z < 0 or z > MAPBOX_MAX_ZOOM:
        return None
    blob = _from_disk(z, x, y)
    if blob is not None:
        return blob
    if z <= ESRI_MAX_ZOOM:
        blob = _download(ESRI_URL.format(z=z, y=y, x=x), timeout)
        if blob is not None and _hybrid_wanted():
            blob = _overlay(blob, z, x, y, timeout) or blob
    if blob is None and mapbox_token():
        blob = _download(
            MAPBOX_URL.format(z=z, x=x, y=y, token=mapbox_token()), timeout)
    if blob is not None:
        _to_disk(z, x, y, blob)
    return blob


def best_tile(z, x, y, provider=DEFAULT_PROVIDER):
    """The sharpest tile available for (z, x, y), or None.

    Ours first, because it has every zoom everywhere; QGroundControl's
    cache second, so a machine with no network behaves as it did before
    this was added. Reading QGC's cache alone was the whole supply until
    14 Oct 2026, and it only ever held what QGC had happened to look at -
    measured on the coast area, 34 of the 54 tiles the map wanted had to
    be drawn by blowing up an ancestor, so two thirds of the picture was
    an upscaled lower-zoom tile. No amount of drawing cleverness fixes a
    tile that was never downloaded.
    """
    return fetch_tile(z, x, y) or tile(z, x, y, provider)


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
