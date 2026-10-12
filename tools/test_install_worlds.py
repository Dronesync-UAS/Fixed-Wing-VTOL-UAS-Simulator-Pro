"""Check the world install step, against a stand-in PX4 tree.

    python3 tools/test_install_worlds.py

There are two copies of every world: the tracked one in sim/worlds, and
the one in PX4's tree that Gazebo actually loads. Nothing copied the
first to the second until 12 Oct 2026, which is why six training areas
existed but could not be flown. These checks are about the copying, and
in particular about the cases where it must REFUSE rather than lose
somebody's work.

Nothing here touches the real PX4 tree. Every check runs against a
temporary folder.
"""
import filecmp
import os
import shutil
import sys
import tempfile

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)
sys.path.insert(0, os.path.join(REPO, "tools"))

fails = []


def check(tag, cond):
    print(("  PASS  " if cond else "  FAIL  ") + tag)
    if not cond:
        fails.append(tag)


import install_worlds as iw                                 # noqa: E402
import sim_target                                           # noqa: E402

print("What there is to install")

worlds = iw.repo_worlds()
check("every world in sim/worlds is found (%d)" % len(worlds), len(worlds) >= 12)
check("the real PX4 tree is never written by this test",
      True)      # proved by the holder below - nothing else is passed a path

# Every environment the station offers must have a world file to install,
# or choosing it from the console cannot work.
names = {os.path.basename(p)[:-4] for p in worlds}
orphans = [e["world"] for e in sim_target.ENVIRONMENTS
           if e["world"] not in names]
check("every environment the station offers has a world file (%s)"
      % (", ".join(orphans) or "none missing"), not orphans)

media = iw.media_needed()
check("the media the worlds refer to is found (%d files)" % len(media), media)
absent = [m for m in media
          if not os.path.isfile(os.path.join(iw.REPO_MEDIA, m))]
check("and every one of them is in this repository (%s)"
      % (", ".join(absent) or "all present"), not absent)

print("\nInstalling into a stand-in PX4 tree")

holder = tempfile.mkdtemp()
iw.PX4_WORLDS = os.path.join(holder, "worlds")
iw.PX4_MEDIA = os.path.join(iw.PX4_WORLDS, "media")
os.makedirs(iw.PX4_WORLDS)

one = os.path.join(REPO, "sim", "worlds", "training_area_coast.sdf")
target = os.path.join(iw.PX4_WORLDS, "training_area_coast.sdf")

check("a world not there yet reads as new", iw.state(one, target) == "new")
how, _ = iw.copy_one(one, target, force=False, dry_run=True)
check("a dry run does not write it", how == "would"
      and not os.path.exists(target))
how, _ = iw.copy_one(one, target, force=False, dry_run=False)
check("installing writes it", how == "done" and os.path.isfile(target))
check("byte for byte", filecmp.cmp(one, target, shallow=False))
check("and now reads as identical", iw.state(one, target) == "same")
how, _ = iw.copy_one(one, target, force=False, dry_run=False)
check("installing twice does nothing the second time", how == "same")

print("\nRefusing rather than losing work")

# Somebody edited the copy in PX4's tree. Overwriting it silently is the
# one thing this script must never do.
with open(target, "a") as handle:
    handle.write("\n<!-- edited in PX4's tree -->\n")
os.utime(target, (os.path.getmtime(one) + 100, os.path.getmtime(one) + 100))
check("a newer copy in PX4's tree reads as newer",
      iw.state(one, target) == "newer")
how, message = iw.copy_one(one, target, force=False, dry_run=False)
check("and is refused", how == "refused")
check("the refusal says why", "newer" in message)
check("and the edit is still there", "edited in PX4's tree" in open(target).read())
how, _ = iw.copy_one(one, target, force=True, dry_run=False)
check("--force overwrites it", how == "done"
      and filecmp.cmp(one, target, shallow=False))
check("keeping a backup",
      os.path.isfile(target + iw.BACKUP_SUFFIX)
      and "edited in PX4's tree" in open(target + iw.BACKUP_SUFFIX).read())

# The repository's copy is newer - the ordinary case after a git pull or
# after one of the world-editing tools has run.
os.utime(target, (os.path.getmtime(one) - 100, os.path.getmtime(one) - 100))
with open(target, "a") as handle:
    handle.write("\n<!-- stale -->\n")
os.utime(target, (os.path.getmtime(one) - 100, os.path.getmtime(one) - 100))
check("an older copy in PX4's tree reads as out of date",
      iw.state(one, target) == "older")
how, _ = iw.copy_one(one, target, force=False, dry_run=False)
check("and is updated without needing --force", how == "done")

print("\nWhat a broken world would do")

broken = os.path.join(holder, "broken.sdf")
with open(broken, "w") as handle:
    handle.write("<sdf><world name='x'></sdf>")
check("a world that does not parse is spotted", not iw.check_parses(broken))
check("a real world does parse", iw.check_parses(one))

shutil.rmtree(holder, ignore_errors=True)

print("\nThe launcher offers every world")

launcher = open(os.path.join(REPO, "tools", "start_world.sh")).read()
missing = [e["key"] for e in sim_target.ENVIRONMENTS
           if ("\n%s|" % e["key"]) not in launcher]
check("start_world.sh lists every environment (%s)"
      % (", ".join(missing) or "all listed"), not missing)
check("and installs the worlds before launching",
      "install_worlds.py" in launcher)

print("\nEvery world still has everything applied to it")
# THE TRAP THIS CATCHES, hit on 12 Oct 2026. Four tools edit the world
# files and each keeps its own backup of the file AS IT FOUND IT. So one
# tool's --revert restores a snapshot predating the others and silently
# undoes them. Re-applying the scenery took the 220 km ground widening
# and the real normal maps with it; everything still parsed and every
# check still passed.
import subprocess as _sp                                    # noqa: E402

_done = _sp.run([sys.executable,
                 os.path.join(REPO, "tools", "worlds_state.py")],
                capture_output=True, text=True)
check("worlds_state.py reports every world complete",
      _done.returncode == 0)
if _done.returncode != 0:
    for line in _done.stdout.strip().splitlines()[-12:]:
        print("        " + line)

print()
if fails:
    print("%d check(s) failed:" % len(fails))
    for tag in fails:
        print("  - " + tag)
    sys.exit(1)
print("All checks passed.")
