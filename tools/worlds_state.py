#!/usr/bin/env python3
"""
What has been applied to every world, in one table.

    python3 tools/worlds_state.py

WHY THIS EXISTS. Four tools edit the world files - far_ground_apply,
ground_texture_apply, plane_ground_texture and scenery_apply - and each
keeps its own backup of the file as it found it. So running one tool's
--revert puts back a snapshot that PREDATES the others, and silently
undoes them.

That happened on 12 Oct 2026: re-applying the scenery meant reverting it
first, and the revert took the 220 km ground widening and the real
normal maps with it. Nothing said so. The world files parsed, the checks
passed, and two features had quietly vanished.

So: this prints what is actually in each world, and says plainly what to
run if something is missing. Run it after any --revert.

THE ORDER TO RE-APPLY, if this shows gaps:

    python3 tools/far_ground_apply.py --all
    python3 tools/ground_texture_apply.py --all
    python3 tools/plane_ground_texture.py --all
    python3 tools/scenery_apply.py
    python3 tools/install_worlds.py

All four are idempotent - running one twice does nothing the second
time - so re-running the lot is always safe.
"""

import glob
import os
import re
import sys
import xml.etree.ElementTree as ET

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORLDS = os.path.join(REPO, "sim", "worlds")

# flat_test carries no scenery ON PURPOSE - scenery_apply.py's own note
# says it is "deliberately left bare so there is always one world to
# fall back to" when the graphics are struggling. So it is not missing
# anything.
BARE_BY_DESIGN = {"flat_test.sdf": {"scenery"}}

PLANE_SIZE = re.compile(
    r"<plane>\s*(?:<normal>[^<]*</normal>\s*)?<size>\s*([0-9.eE+-]+)")

# Each feature: how to see it, and the command that puts it back.
FEATURES = [
    ("far ground 220 km",
     lambda t: (PLANE_SIZE.search(t) is None
                or float(PLANE_SIZE.search(t).group(1)) >= 200000),
     "python3 tools/far_ground_apply.py --all"),
    ("real normal map",
     lambda t: "flat_normal.png" not in t,
     "python3 tools/ground_texture_apply.py --all"),
    ("textured ground",
     lambda t: "<heightmap>" in t and "<texture>" in t,
     "python3 tools/plane_ground_texture.py --all"),
    ("scenery",
     lambda t: "SCENERY: added by" in t,
     "python3 tools/scenery_apply.py"),
    ("PBR materials",
     lambda t: "<pbr>" in t,
     "python3 tools/scenery_apply.py --revert then again (see the note above)"),
]


def main():
    paths = sorted(glob.glob(os.path.join(WORLDS, "*.sdf")))
    if not paths:
        print("No world files in %s" % WORLDS)
        return 1

    names = [name for name, _, _ in FEATURES]
    print("%-34s %s" % ("WORLD", "  ".join("%-18s" % n for n in names)))
    print("-" * (34 + 20 * len(names)))

    missing = {}
    unparsed = []
    for path in paths:
        text = open(path).read()
        try:
            ET.parse(path)
        except ET.ParseError:
            unparsed.append(os.path.basename(path))
        base = os.path.basename(path)
        exempt = BARE_BY_DESIGN.get(base, set())
        cells = []
        for name, present, fix in FEATURES:
            ok = present(text)
            if not ok and name in exempt:
                cells.append("%-18s" % "bare on purpose")
                continue
            cells.append("%-18s" % ("yes" if ok else "NO"))
            if not ok:
                missing.setdefault(fix, []).append(base)
        print("%-34s %s" % (os.path.basename(path), "  ".join(cells)))

    print()
    if unparsed:
        print("THESE DO NOT PARSE and will not load: %s"
              % ", ".join(unparsed))
        print("  git checkout sim/worlds   (discards local edits to them)")
        return 1

    if not missing:
        print("Every world has everything. After any change, remember:")
        print("    python3 tools/install_worlds.py")
        return 0

    print("Missing. Run these in this order:\n")
    for name, _, fix in FEATURES:
        if fix in missing:
            print("  %s" % fix)
            print("      for: %s\n" % ", ".join(missing[fix]))
    print("Then: python3 tools/install_worlds.py")
    return 1


if __name__ == "__main__":
    sys.exit(main())
