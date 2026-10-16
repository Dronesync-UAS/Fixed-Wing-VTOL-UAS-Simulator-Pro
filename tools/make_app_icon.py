#!/usr/bin/env python3
"""
Turns brand artwork into a desktop icon that sits right among the others.

    python3 tools/make_app_icon.py
    python3 tools/make_app_icon.py --source "/path/to/art.png" --out name.png
    python3 tools/make_app_icon.py --fill 0.82

TWO THINGS HAVE TO BE FIXED, and both were wrong on 13 Oct 2026.

1. THE BACKGROUND. The brand file is a dark rounded tile on WHITE, with a
   soft drop shadow around it. Dropped straight onto a dark desktop that
   is a white box with the icon inside it. The white is removed by filling
   in from the four corners rather than by replacing every white pixel,
   because the lettering inside the tile is white too and a blanket
   replace punches holes through ACADEMY and GCS Pro.

   The threshold matters. The first attempt used 232, which took the white
   but left the drop shadow, and the shadow still read as a pale box. The
   tile itself is around 60, so 140 is clear of it by a mile.

2. THE SIZE. Measured across the icons already on this machine, GNOME's
   own artwork fills about 90 per cent of its canvas - but most of it is
   ROUND. A filled square at 90 per cent has far more ink in it than a
   circle at 90 per cent, and in the Show Apps grid it reads as a bigger
   icon than its neighbours. The rounded-square icons that look right
   there - Claude's is one - come in at about 82 per cent, so that is what
   this uses.

   QGroundControl's own icon is at 100 per cent, which is why it looks
   bigger than everything else too.

WHY THE OUTPUT NAME KEEPS CHANGING. GNOME caches an icon by its path. A
file edited in place goes on showing the old picture until the session is
restarted, which is no use to somebody who just wants to see whether the
change worked. Writing to a new name sidesteps the cache entirely, so
--out is worth using when an icon looks wrong after a change.
"""

import argparse
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICONS = os.path.join(REPO, "sim", "icons")

DEFAULT_SOURCE = "/home/uas-sim/UAS-Academy/Brand/UAV Academy GCS Pro Icon.png"
DEFAULT_OUT = "uas-gcs-app-icon.png"
CANVAS = 512
# How much of the canvas the artwork fills. See the note above: this is a
# square icon, so it is deliberately below the 90 per cent that GNOME's
# mostly-round icons use.
FILL = 0.82
# Anything lighter than this, and reachable from a corner, is background.
# The tile is about 60, so there is a wide gap either side of this figure.
BACKGROUND_ABOVE = 140


def cut_background(rgb):
    """Alpha for `rgb`: 0 on the background, 255 on the artwork."""
    h, w, _ = rgb.shape
    lo = rgb.min(2)
    seen = np.zeros((h, w), bool)
    queue = deque([(0, 0), (0, w - 1), (h - 1, 0), (h - 1, w - 1)])
    while queue:
        y, x = queue.popleft()
        if (y < 0 or x < 0 or y >= h or x >= w or seen[y, x]
                or lo[y, x] <= BACKGROUND_ABOVE):
            continue
        seen[y, x] = True
        queue.extend(((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)))

    alpha = np.where(seen, 0, 255).astype(np.uint8)
    # Feather, or the rounded corners come out as a staircase on a dark
    # desktop. Blurring the mask and keeping the inside solid softens the
    # boundary only.
    soft = np.asarray(Image.fromarray(alpha).filter(ImageFilter.GaussianBlur(0.8)))
    return np.minimum(alpha, soft)


def trim(image):
    """Crop to the artwork, so the margin added next is measured from it."""
    alpha = np.asarray(image)[:, :, 3]
    ys, xs = np.where(alpha > 24)
    if not len(ys):
        return image
    return image.crop((xs.min(), ys.min(), xs.max() + 1, ys.max() + 1))


def build(source, canvas=CANVAS, fill=FILL):
    art = Image.open(source).convert("RGB")
    rgb = np.asarray(art).astype(int)
    rgba = np.dstack([rgb.astype(np.uint8), cut_background(rgb)])
    art = trim(Image.fromarray(rgba, "RGBA"))

    side = int(round(canvas * fill))
    scale = min(side / art.width, side / art.height)
    art = art.resize((max(1, int(round(art.width * scale))),
                      max(1, int(round(art.height * scale)))), Image.LANCZOS)

    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.paste(art, ((canvas - art.width) // 2, (canvas - art.height) // 2))
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", default=DEFAULT_SOURCE,
                        help="brand artwork to start from")
    parser.add_argument("--out", default=DEFAULT_OUT,
                        help="file name to write under sim/icons/")
    parser.add_argument("--fill", type=float, default=FILL,
                        help="how much of the canvas to fill (default %g)" % FILL)
    args = parser.parse_args(argv)

    if not os.path.isfile(args.source):
        print("Not found: %s" % args.source, file=sys.stderr)
        return 1

    os.makedirs(ICONS, exist_ok=True)
    icon = build(args.source, fill=args.fill)
    path = os.path.join(ICONS, args.out)
    icon.save(path, optimize=True)

    alpha = np.asarray(icon)[:, :, 3]
    ys, xs = np.where(alpha > 24)
    print("Wrote %s" % path)
    print("  %dx%d, artwork fills %.0f%% of it, %.0f%% transparent, %.0f kB"
          % (icon.width, icon.height,
             100.0 * (xs.max() - xs.min() + 1) / icon.width,
             100.0 * (alpha == 0).mean(), os.path.getsize(path) / 1024))
    print("\nIf the desktop still shows the old picture, it is GNOME's icon")
    print("cache: write to a new --out name and point the .desktop files at")
    print("it, or restart the shell with Alt+F2, r, Enter.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
