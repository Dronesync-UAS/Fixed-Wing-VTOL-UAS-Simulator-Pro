#!/usr/bin/env bash
#
# Launches the simulator in any of the training worlds, with the right spawn
# height for that world's ground:
#
#     tools/start_world.sh blackrock      # Black Rock playa, Nevada - flattest
#     tools/start_world.sh nullarbor      # Nullarbor Plain, Australia
#     tools/start_world.sh uyuni          # Salar de Uyuni, Bolivia
#     tools/start_world.sh hoggar         # Hoggar Mountains, Algeria
#     tools/start_world.sh flat           # the plain flat test world
#     tools/start_world.sh                # lists them with their terrain
#
# Why this exists: each world's ground sits at a different height - Hoggar's
# clearing is at 605 m, Black Rock's playa at 1 m - so a single spawn pose
# cannot serve them. Launching a sea-level world with Hoggar's 615.5 m spawn
# drops the aircraft from 600 m; launching Hoggar with a sea-level spawn
# buries it. The heights below were measured from each world's own heightmap.
#
# Start the station pointed at the same world, or its controls talk to a world
# that isn't running - the script prints the exact line to use.

set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PX4_DIR="$HOME/PX4-Autopilot"
PX4_WORLDS="$PX4_DIR/Tools/simulation/gz/worlds"

# key | world file | spawn Z | relief within 500 m | description
WORLDS="
blackrock|training_area_blackrock|1.3|0.6 m|Black Rock playa, Nevada - flattest, best for handling practice
nullarbor|training_area_nullarbor|11.3|7.9 m|Nullarbor Plain, Australia - very gently undulating
uyuni|training_area_uyuni|8.3|9.5 m|Salar de Uyuni, Bolivia - very gently undulating
hoggar|training_area|605.1|0 m|Hoggar Mountains, Algeria - flat to 600 m, mountains beyond
flat|flat_test|0.3|0 m|Plain flat ground, no scenery - for isolating faults
"

usage() {
    echo "Usage: tools/start_world.sh <world>"
    echo
    printf "  %-11s %-26s %-10s %s\n" KEY WORLD "RELIEF" "TERRAIN"
    echo "$WORLDS" | while IFS='|' read -r key file z relief desc; do
        [ -z "$key" ] && continue
        printf "  %-11s %-26s %-10s %s\n" "$key" "$file" "$relief" "$desc"
    done
    echo
    echo "Relief is the height range within the 500 m operating limit. Anything"
    echo "much above 100 m cannot be flown under the 120 m ceiling."
}

if [ $# -lt 1 ]; then
    usage
    exit 0
fi

KEY="$1"
LINE=$(echo "$WORLDS" | grep "^${KEY}|" || true)
if [ -z "$LINE" ]; then
    echo "Unknown world: $KEY"
    echo
    usage
    exit 1
fi

WORLD=$(echo "$LINE" | cut -d'|' -f2)
SPAWN_Z=$(echo "$LINE" | cut -d'|' -f3)
DESC=$(echo "$LINE" | cut -d'|' -f5)

# flat_test lives in this repo rather than PX4's tree, so install it first.
if [ "$WORLD" = "flat_test" ] && [ -f "$REPO/sim/worlds/flat_test.sdf" ]; then
    cp "$REPO/sim/worlds/flat_test.sdf" "$PX4_WORLDS/flat_test.sdf"
fi

if [ ! -f "$PX4_WORLDS/$WORLD.sdf" ]; then
    echo "World file not found: $PX4_WORLDS/$WORLD.sdf"
    exit 1
fi

# Ctrl+C on a previous run leaves PX4 alive, and the next launch then fails
# with "PX4 server already running for instance 0". Clear it rather than
# leaving that confusing error.
if pgrep -f 'bin/px4' >/dev/null 2>&1 || pgrep -f 'gz sim' >/dev/null 2>&1; then
    echo "Stopping the previous simulator..."
    pkill -f 'bin/px4' 2>/dev/null || true
    pkill -f 'gz sim' 2>/dev/null || true
    sleep 2
    rm -rf /tmp/px4* 2>/dev/null || true
fi

echo
echo "World:  $WORLD"
echo "Ground: $DESC"
echo "Spawn:  ${SPAWN_Z} m"
echo
echo "Start the station in another terminal with:"
echo "  GCS_WORLD=$WORLD python3 $REPO/instructor_station.py"
echo

cd "$PX4_DIR"
export PX4_GZ_MODEL_POSE="0,0,${SPAWN_Z},0,0,0"

# Gazebo runs without its own window unless asked for. PX4's SITL makefile
# reads HEADLESS and starts the server only; the camera sensors still
# render, so the console's views are unaffected. UAS_SHOW_GAZEBO=1 brings
# the window back when the world itself needs looking at.
if [ "${UAS_SHOW_GAZEBO:-0}" != "1" ]; then
  export HEADLESS=1
  echo "Gazebo: hidden (UAS_SHOW_GAZEBO=1 to show its window)"
else
  echo "Gazebo: showing its own window"
fi

PX4_GZ_WORLD="$WORLD" make px4_sitl gz_standard_vtol
