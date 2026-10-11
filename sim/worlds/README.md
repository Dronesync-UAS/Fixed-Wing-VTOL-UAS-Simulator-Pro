# Custom training worlds — backup copy

The four `training_area*.sdf` worlds and the heightmaps/textures they reference.
Backed up here 11 October 2026.

**Why these are here.** The live copies are at
`~/PX4-Autopilot/Tools/simulation/gz/worlds/`, which is a **git submodule of
PX4**, where they show as local modifications. A `git submodule update --force`,
a branch switch, or a deep clean in PX4 can delete them without warning. They
are the SRTM-derived terrain work from the 22 August 2026 decision-log entry and
until now existed in exactly one place.

**This copy is self-contained.** Every `file://` reference in the four worlds
resolves to a file in `media/` here — checked, not assumed. The `.sdf` files on
their own would be pointers to terrain you no longer had.

| World | Terrain |
|---|---|
| `training_area.sdf` | Hoggar Mountains, Algeria (23.2667N, 5.6333E) — the one in use |
| `training_area_blackrock.sdf` | Black Rock |
| `training_area_nullarbor.sdf` | Nullarbor |
| `training_area_uyuni.sdf` | Uyuni |

All four include the `<wind>` element and the `WindEffects` plugin added on
11 October 2026, so a restore brings wind support back with them.

## Restoring

Copy the contents back into PX4's worlds directory:

```bash
cp -r sim/worlds/training_area*.sdf sim/worlds/media \
      ~/PX4-Autopilot/Tools/simulation/gz/worlds/
```

Then launch as usual — `PX4_GZ_WORLD=training_area`.

## Refreshing this backup

After editing a world in PX4, re-run the backup so this copy does not go stale:

```bash
python3 tools/backup_worlds.py            # show what would be copied
python3 tools/backup_worlds.py --apply    # copy it in
```

Then commit. The script follows each world's references, so a newly added
heightmap or texture is picked up without this file needing an update.

**This is a backup, not the live copy.** Gazebo reads the PX4 submodule, not
this folder. Editing the files here changes nothing in the simulator.
