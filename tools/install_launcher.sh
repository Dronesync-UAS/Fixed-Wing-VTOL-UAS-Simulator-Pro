#!/usr/bin/env bash
#
# Puts "UAV Academy Simulator" in the applications menu, so starting a
# session is a double-click instead of two terminals and a browser.
#
#     tools/install_launcher.sh            # install / update the icons
#     tools/install_launcher.sh --desktop  # also drop them on the Desktop
#     tools/install_launcher.sh --remove   # take them away again
#
# Installs two entries into ~/.local/share/applications:
#
#     UAV Academy Simulator        -> starts Gazebo + PX4 + the station
#     Stop UAV Academy Simulator   -> stops both
#
# Needs no sudo: ~/.local/share/applications is the per-user half of the
# desktop-entry spec, and GNOME picks entries up from there automatically.
#
# Both entries run in a terminal window on purpose. The launcher reports what
# it is doing - clearing an old run, building PX4, waiting for the station -
# and the first build of PX4 can take minutes. A silent icon that may or may
# not be working is worse than a window that says so.

set -eu

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LAUNCHER="$REPO/tools/uas_launcher.py"
APPS="$HOME/.local/share/applications"
# ONE ICON, not two. Until 13 Oct 2026 there was a green "start" and a red
# "stop". They are merged into a single UAV Academy GCS Pro that starts the
# simulator if it is down and ASKS before stopping one that is up - see
# toggle() in uas_launcher.py for why it asks. The two old files are
# removed on install so an upgraded machine is not left with three icons,
# two of which are stale.
APP_FILE="$APPS/uav-academy-gcs-pro.desktop"
OLD_START="uas-academy-simulator.desktop"
OLD_STOP="uas-academy-simulator-stop.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"

MODE="${1:-install}"

if [ "$MODE" = "--remove" ]; then
    rm -f "$APP_FILE" "$APPS/$OLD_START" "$APPS/$OLD_STOP"
    rm -f "$DESKTOP_DIR/uav-academy-gcs-pro.desktop" \
          "$DESKTOP_DIR/$OLD_START" "$DESKTOP_DIR/$OLD_STOP"
    command -v update-desktop-database >/dev/null 2>&1 \
        && update-desktop-database "$APPS" 2>/dev/null || true
    echo "Removed the UAV Academy launcher icons."
    exit 0
fi

if [ ! -f "$LAUNCHER" ]; then
    echo "Not found: $LAUNCHER" >&2
    exit 1
fi

mkdir -p "$APPS"

write_entry() {
    # $1 file, $2 name, $3 comment, $4 icon, $5 extra launcher arguments
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$2
Comment=$3
Exec=python3 "$LAUNCHER" $5 --hold
Icon=$4
Terminal=true
Categories=Education;Science;Engineering;
Keywords=UAV;drone;PX4;Gazebo;simulator;GCS;
StartupNotify=false
EOF
    chmod +x "$1"
}

write_entry "$APP_FILE" "UAV Academy GCS Pro" \
    "Start the simulator, or stop the one that is running" \
    "$REPO/sim/icons/uas-gcs-app-icon.png" "--toggle"

# The separate start and stop icons this replaces.
rm -f "$APPS/$OLD_START" "$APPS/$OLD_STOP" \
      "$DESKTOP_DIR/$OLD_START" "$DESKTOP_DIR/$OLD_STOP"

command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed:"
echo "  $APP_FILE"

if [ "$MODE" = "--desktop" ]; then
    if [ -d "$DESKTOP_DIR" ]; then
        cp "$APP_FILE" "$DESKTOP_DIR/"
        chmod +x "$DESKTOP_DIR/uav-academy-gcs-pro.desktop"
        # GNOME ignores a desktop file it does not trust, and shows the
        # filename instead of the icon until it is marked trusted.
        if command -v gio >/dev/null 2>&1; then
            gio set "$DESKTOP_DIR/uav-academy-gcs-pro.desktop" \
                metadata::trusted true 2>/dev/null || true
        fi
        echo "  copies on $DESKTOP_DIR"
        echo
        echo "If the Desktop copies show as a filename rather than an icon,"
        echo "right-click one and choose 'Allow Launching'."
    else
        echo "No Desktop folder at $DESKTOP_DIR - menu entries installed only."
    fi
fi

echo
echo "Press the Super key and type 'UAV' to find them."
