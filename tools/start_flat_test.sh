#!/usr/bin/env bash
#
# Launches the simulator in the flat test world: clear, genuinely flat ground
# at Z=0, nothing to fly into, no terrain alignment to doubt.
#
#     tools/start_flat_test.sh
#
# Mirrors start_training_area.sh, with the world and the spawn height changed.
# It installs sim/worlds/flat_test.sdf into PX4's worlds directory first, since
# that is where PX4 resolves PX4_GZ_WORLD from - the world needs no media
# files, so that is the only thing to copy.
#
# Start the station pointed at the same world, or its controls will talk to a
# world that isn't running:
#
#     GCS_WORLD=flat_test python3 instructor_station.py

set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="$HOME/PX4-Autopilot"
PX4_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"
WORLD_SRC="$REPO/sim/worlds/flat_test.sdf"

if [ ! -f "$WORLD_SRC" ]; then
    echo "Not found: $WORLD_SRC"
    exit 1
fi
if [ ! -d "$PX4_WORLDS" ]; then
    echo "Not found: $PX4_WORLDS"
    exit 1
fi

cp "$WORLD_SRC" "$PX4_WORLDS/flat_test.sdf"
echo "Installed flat_test.sdf into $PX4_WORLDS"

# A previous run left running would make this one fail with "PX4 server already
# running for instance 0", so clear it rather than leaving a confusing error.
if pgrep -f 'bin/px4' >/dev/null 2>&1 || pgrep -f 'gz sim' >/dev/null 2>&1; then
    echo "Stopping the previous simulator..."
    pkill -f 'bin/px4' 2>/dev/null || true
    pkill -f 'gz sim' 2>/dev/null || true
    sleep 2
    rm -rf /tmp/px4* 2>/dev/null || true
fi

echo
echo "Starting in the flat test world. Spawn height 0.3 m (ground is Z=0)."
echo "Start the station with:  GCS_WORLD=flat_test python3 $REPO/instructor_station.py"
echo

cd "$PX4_DIR"
export PX4_GZ_MODEL_POSE="0,0,0.3,0,0,0"
PX4_GZ_WORLD=flat_test make px4_sitl gz_standard_vtol
