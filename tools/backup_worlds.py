"""Copies the custom training worlds into this repo so they are versioned and
off-machine:

    python3 tools/backup_worlds.py            # show what would be copied
    python3 tools/backup_worlds.py --apply    # copy it in

Why: the four training_area*.sdf worlds live in ~/PX4-Autopilot/Tools/simulation/gz,
which is a git SUBMODULE of PX4. They show as local modifications inside it, which
means a `git submodule update --force`, a branch switch or a deep clean in PX4 can
delete them without warning. They are hours of SRTM terrain work (22 Aug entry) and
exist in exactly one place.

A world file on its own is not enough - it references a heightmap and other media by
path, and the terrain is in those files, not the SDF. So this follows every <uri> and
heightmap reference in each world and copies what it actually needs, rather than
guessing or copying the whole media folder.

Copies land in sim/worlds/ in this repo, keeping the paths the worlds use, so the set
can be dropped back into a fresh PX4 checkout. Nothing in PX4 is moved or changed -
this only reads from there.
"""
import os
import re
import shutil
import sys

PX4_WORLDS = os.path.expanduser("~/PX4-Autopilot/Tools/simulation/gz/worlds")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(REPO, "sim", "worlds")

# GitHub warns above 50 MB per file and refuses above 100 MB.
WARN_BYTES = 50 * 1024 * 1024

# Anything that names a file: <uri>, plus the heightmap/material elements that
# carry a bare filename. <diffuse> and <normal> are included because a
# heightmap's textures use them - a material colour in the same elements is
# several space-separated numbers, which this cannot match, so colours are
# excluded naturally rather than by a special case.
REF_PATTERN = re.compile(
    r"<(?:uri|filename|albedo_map|normal_map|diffuse_map|texture|diffuse|normal)>"
    r"\s*([^<>\s]+)\s*</",
    re.IGNORECASE)


def human(size):
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0


def referenced_files(world_path):
    """Local files a world needs, as paths relative to the worlds directory.

    file:// is a local path, not a library lookup - these worlds reference
    their heightmap as file://media/... - so the scheme is stripped and the
    rest resolved against the worlds directory. model:// and package:// are
    library lookups into installed models and are reported separately rather
    than copied.
    """
    with open(world_path, errors="replace") as fh:
        text = fh.read()

    found, skipped = {}, []
    for raw in REF_PATTERN.findall(text):
        path = raw
        if path.lower().startswith("file://"):
            path = path[len("file://"):]
        elif "://" in path:
            skipped.append(raw)
            continue
        candidate = os.path.normpath(os.path.join(PX4_WORLDS, path))
        # Don't follow a reference that climbs out of the worlds directory.
        if not candidate.startswith(os.path.realpath(PX4_WORLDS) + os.sep) and \
           not candidate.startswith(PX4_WORLDS + os.sep):
            found[raw] = None
            continue
        found[raw] = candidate if os.path.isfile(candidate) else None
    return found, skipped


def main(apply):
    if not os.path.isdir(PX4_WORLDS):
        print(f"Not found: {PX4_WORLDS}")
        return 1

    worlds = sorted(f for f in os.listdir(PX4_WORLDS)
                    if f.startswith("training_area") and f.endswith(".sdf"))
    if not worlds:
        print(f"No training_area*.sdf in {PX4_WORLDS}")
        return 1

    to_copy = {}      # relative path -> absolute source
    missing = []      # references that could not be resolved
    libraries = set() # model:// style lookups, not ours to copy
    for name in worlds:
        src = os.path.join(PX4_WORLDS, name)
        to_copy[name] = src
        refs, skipped = referenced_files(src)
        libraries.update(skipped)
        for raw, resolved in refs.items():
            if resolved:
                rel = os.path.relpath(resolved, PX4_WORLDS)
                to_copy[rel] = resolved
            else:
                missing.append((name, raw))

    total = 0
    print(f"From {PX4_WORLDS}")
    print(f"To   {DEST}\n")
    for rel in sorted(to_copy):
        size = os.path.getsize(to_copy[rel])
        total += size
        flag = "  << over 50 MB, GitHub will warn" if size > WARN_BYTES else ""
        print(f"  {human(size):>9}  {rel}{flag}")
    print(f"\n  {human(total):>9}  total, {len(to_copy)} files")

    if libraries:
        print("\nLibrary lookups, not copied (these resolve to installed models,")
        print("not to files belonging to these worlds):")
        for raw in sorted(libraries):
            print(f"  {raw}")

    if missing:
        print("\nReferenced but NOT FOUND on disk - check these before relying on")
        print("the backup, since the worlds expect them:")
        for name, raw in missing:
            print(f"  {name}: {raw}")

    if not apply:
        print("\nNothing copied. Re-run with --apply to copy it in.")
        return 0

    for rel in sorted(to_copy):
        target = os.path.join(DEST, rel)
        os.makedirs(os.path.dirname(target), exist_ok=True)
        existed = os.path.exists(target)
        shutil.copy2(to_copy[rel], target)
        print(f"{'updated' if existed else 'copied '}  {rel}")

    print(f"""
Copied into sim/worlds/. Now commit and push so it is off this machine:

  cd {REPO}
  git add sim/worlds
  git commit -m "Back up the custom training_area worlds"
  git push -u origin claude/pensive-lamport-af8mkq

If any file above is over 50 MB, tell me before pushing - large binaries need
handling differently and are awkward to remove from history afterwards.""")
    return 0


if __name__ == "__main__":
    sys.exit(main("--apply" in sys.argv))
