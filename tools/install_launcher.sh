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
START_FILE="$APPS/uas-academy-simulator.desktop"
STOP_FILE="$APPS/uas-academy-simulator-stop.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"

MODE="${1:-install}"

if [ "$MODE" = "--remove" ]; then
    rm -f "$START_FILE" "$STOP_FILE"
    rm -f "$DESKTOP_DIR/uas-academy-simulator.desktop" \
          "$DESKTOP_DIR/uas-academy-simulator-stop.desktop"
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

write_entry "$START_FILE" "UAV Academy Simulator" \
    "Start Gazebo, PX4 and the instructor station together" \
    "$REPO/sim/icons/uas-gcs.svg" ""
write_entry "$STOP_FILE" "Stop UAV Academy Simulator" \
    "Stop Gazebo, PX4 and the instructor station" \
    "$REPO/sim/icons/uas-gcs-stop.svg" "--stop"

command -v update-desktop-database >/dev/null 2>&1 \
    && update-desktop-database "$APPS" 2>/dev/null || true

echo "Installed:"
echo "  $START_FILE"
echo "  $STOP_FILE"

if [ "$MODE" = "--desktop" ]; then
    if [ -d "$DESKTOP_DIR" ]; then
        cp "$START_FILE" "$STOP_FILE" "$DESKTOP_DIR/"
        chmod +x "$DESKTOP_DIR/uas-academy-simulator.desktop" \
                 "$DESKTOP_DIR/uas-academy-simulator-stop.desktop"
        # GNOME ignores a desktop file it does not trust, and shows the
        # filename instead of the icon until it is marked trusted.
        if command -v gio >/dev/null 2>&1; then
            gio set "$DESKTOP_DIR/uas-academy-simulator.desktop" \
                metadata::trusted true 2>/dev/null || true
            gio set "$DESKTOP_DIR/uas-academy-simulator-stop.desktop" \
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
