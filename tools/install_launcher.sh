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
# EVERY earlier entry, not just the two this replaced directly. On
# 14 Oct 2026 a machine still carried three things called "UAV Academy GCS
# Pro" because the list below only knew about the pair from 13 Oct:
#
#   uas-instructor-station  ran instructor_station.py on its own, with no
#                           PX4 and no Gazebo, so it sat on "Connecting to
#                           the simulator" for ever - in a terminal window
#   uas-control-deck        opened firefox at localhost:8080 and started
#                           nothing, so it was blank unless the station
#                           happened to be running already
#
# Both predate the launcher and neither can work. Anything added here is
# deleted on install, so an upgraded machine ends with exactly one icon.
STALE_ENTRIES="uas-academy-simulator.desktop
uas-academy-simulator-stop.desktop
uas-instructor-station.desktop
uas-control-deck.desktop"
DESKTOP_DIR="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"

MODE="${1:-install}"

if [ "$MODE" = "--remove" ]; then
    rm -f "$APP_FILE" "$DESKTOP_DIR/uav-academy-gcs-pro.desktop"
    echo "$STALE_ENTRIES" | while read -r stale; do
        [ -n "$stale" ] && rm -f "$APPS/$stale" "$DESKTOP_DIR/$stale"
    done
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

# Terminal=false since 14 Oct 2026 - "do not show terminal window
# activating the app". The terminal was not decoration: it carried the
# progress messages through the minute PX4 and Gazebo take to start, and
# the "already running" question needs somewhere to be asked. The launcher
# detects having no terminal and sends progress to desktop notifications
# and the question to a zenity dialog, so nothing was lost with it.
# StartupNotify=true so the dock shows the launch is under way.
# ONE main category. desktop-file-validate warns that more than one makes
# the application "appear more than once in the application menu", and this
# carried three - Education, Science and Engineering. A machine that
# already had three things called UAV Academy GCS Pro did not need help
# showing a fourth. Keywords below still find it by drone, PX4 and so on.
write_entry() {
    # $1 file, $2 name, $3 comment, $4 icon, $5 extra launcher arguments
    cat > "$1" <<EOF
[Desktop Entry]
Type=Application
Version=1.0
Name=$2
Comment=$3
Exec=python3 "$LAUNCHER" $5
Icon=$4
Terminal=false
Categories=Education;
Keywords=UAV;drone;PX4;Gazebo;simulator;GCS;
StartupNotify=true
EOF
    chmod +x "$1"
}

write_entry "$APP_FILE" "UAV Academy GCS Pro" \
    "Start the simulator, or stop the one that is running" \
    "$REPO/sim/icons/uas-gcs-app-icon.png" "--toggle"

# The separate start and stop icons this replaces.
echo "$STALE_ENTRIES" | while read -r stale; do
    [ -n "$stale" ] && rm -f "$APPS/$stale" "$DESKTOP_DIR/$stale"
done

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
