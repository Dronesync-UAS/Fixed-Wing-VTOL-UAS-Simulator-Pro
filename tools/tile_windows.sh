#!/usr/bin/env bash
#
# Puts the instructor station and the Gazebo window side by side on one
# screen, so the two look like a single console instead of windows to hunt
# for. Run it once both are open:
#
#     tools/tile_windows.sh              # station 50% left, Gazebo right
#     tools/tile_windows.sh 60           # station 60% of the width
#     tools/tile_windows.sh 50 37        # leave 37px for a top panel
#
# Needs wmctrl (one small package, but it does need sudo to install:
#     sudo apt install wmctrl
# ). Without it, GNOME's own Super+Left / Super+Right tiles the focused
# window to half the screen with nothing to install - this script just
# removes the need to do that by hand every session.
#
# Deliberately a separate script, not folded into start_training_area.sh:
# that launcher lives outside this repo and runs the sim, and a window-
# arranging convenience should not be able to stop the simulator starting.

set -u

STATION_TITLE="UAV Academy GCS Pro"
GAZEBO_TITLE="Gazebo"

STATION_PERCENT="${1:-50}"
TOP_OFFSET="${2:-0}"
WAIT_SECONDS=60

if ! command -v wmctrl >/dev/null 2>&1; then
    echo "wmctrl is not installed, so the windows cannot be positioned automatically."
    echo "  Install it:  sudo apt install wmctrl"
    echo "  Or tile by hand: click a window, then Super+Left / Super+Right."
    exit 1
fi

# Screen size. xdotool is the tidy way; xrandr is almost always present as a
# fallback. If both fail, say so rather than guessing a resolution and
# shoving windows somewhere off screen.
if command -v xdotool >/dev/null 2>&1; then
    read -r SCREEN_W SCREEN_H < <(xdotool getdisplaygeometry)
elif command -v xrandr >/dev/null 2>&1; then
    GEOM=$(xrandr --query | awk '/ connected primary/ {print $4}' | head -1)
    [ -z "$GEOM" ] && GEOM=$(xrandr --query | awk '/ connected/ {print $3}' | head -1)
    SCREEN_W=${GEOM%%x*}
    SCREEN_H=${GEOM#*x}; SCREEN_H=${SCREEN_H%%+*}
else
    echo "Could not read the screen size (no xdotool or xrandr). Tile by hand with"
    echo "Super+Left / Super+Right instead."
    exit 1
fi

case "$SCREEN_W$SCREEN_H" in
    *[!0-9]*|"") echo "Could not read a sensible screen size (got '${SCREEN_W}x${SCREEN_H}')."; exit 1 ;;
esac

echo "Screen: ${SCREEN_W}x${SCREEN_H}"

wait_for_window() {
    local title="$1" waited=0
    while [ "$waited" -lt "$WAIT_SECONDS" ]; do
        if wmctrl -l | grep -qi -- "$title"; then
            return 0
        fi
        sleep 1
        waited=$((waited + 1))
    done
    return 1
}

place() {
    local title="$1" x="$2" y="$3" w="$4" h="$5"
    # Un-maximise first: a maximised window ignores a move/resize request.
    wmctrl -r "$title" -b remove,maximized_vert,maximized_horz 2>/dev/null
    # -e takes gravity,x,y,width,height; gravity 0 means "leave it to the WM".
    wmctrl -r "$title" -e "0,${x},${y},${w},${h}"
}

for title in "$STATION_TITLE" "$GAZEBO_TITLE"; do
    if ! wait_for_window "$title"; then
        echo "Gave up waiting ${WAIT_SECONDS}s for a window matching '$title'."
        echo "Open windows are:"
        wmctrl -l | sed 's/^/  /'
        exit 1
    fi
done

USABLE_H=$((SCREEN_H - TOP_OFFSET))
STATION_W=$((SCREEN_W * STATION_PERCENT / 100))
GAZEBO_W=$((SCREEN_W - STATION_W))

place "$STATION_TITLE" 0 "$TOP_OFFSET" "$STATION_W" "$USABLE_H"
place "$GAZEBO_TITLE" "$STATION_W" "$TOP_OFFSET" "$GAZEBO_W" "$USABLE_H"

echo "Station: ${STATION_W}x${USABLE_H} on the left."
echo "Gazebo:  ${GAZEBO_W}x${USABLE_H} on the right."
echo
echo "The station refits its panels to its new width on reload - press"
echo "Ctrl+Shift+R in it, or click 'Fit to screen'."
