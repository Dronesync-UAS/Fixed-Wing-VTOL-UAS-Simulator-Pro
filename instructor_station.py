#!/usr/bin/env python3
"""
UAV Academy GCS Pro

The instructor-only desktop ground control station (renamed from
"UAS Academy Instructor Station" on 5 Sep 2026). A plainer "UAV Academy
GCS" for students is planned for later, once this one is tested and
working.

Built around a plugin system so new scenarios can be added later by just
dropping a new file into the plugins/ folder - nothing else needs to change.

Run this AFTER the simulator is already running.
"""

import http.server
import socketserver
import json
import math
import time
import threading
import sys
import errno
import os
import re
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, os.path.dirname(__file__))

from simulator_link import telemetry, connection_status, flight_path, home_latlon, link_health
from plugin_loader import load_plugins
import video_feed
from video_feed import start_video_capture, mjpeg_generator, camera_fps, FEEDS
import console_page
import event_logger
import flight_display
import terrain_backdrop

PORT = 8080

# Instructor-arranged panel layout. Stored on the machine rather than in the
# browser so it survives a browser reset or reinstall, is the same for whoever
# opens the station, and gets picked up by the same backup as the event log.
LAYOUT_FILE = os.path.join(os.path.expanduser("~/uas_sim_logs"), "gcs_layout.json")

# Panels an instructor must not be able to drag away or shrink to nothing:
# the CAP722B limit banner and the feeds/health row live in the top bar, which
# is outside the grid entirely and so is already fixed. Listed here as the
# record of that decision.
PINNED_OUTSIDE_GRID = ("limit-banner", "t-health")

# A panel may span 2-12 of the grid's 12 columns and be 120-2000 px tall.
# Anything outside that is rejected rather than saved, so a bad layout cannot
# make a panel unreachable or push the rest off screen.
LAYOUT_MIN_COLS, LAYOUT_MAX_COLS = 2, 12
LAYOUT_MIN_H, LAYOUT_MAX_H = 120, 2000


def read_layout():
    """Saved layout, or {} if there isn't one / it's unreadable. A corrupt
    layout file must not stop the station starting, so failures fall back to
    the default arrangement."""
    try:
        with open(LAYOUT_FILE) as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def write_layout(data):
    """Validates and saves a layout. Returns a message for the console."""
    panels = data.get("panels")
    if not isinstance(panels, list) or not panels:
        return "Layout not saved - no panels in the request."

    clean = []
    for item in panels:
        if not isinstance(item, dict):
            continue
        pid = str(item.get("id", ""))
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", pid):
            continue
        try:
            cols = int(item.get("cols", 4))
        except (TypeError, ValueError):
            continue
        cols = max(LAYOUT_MIN_COLS, min(LAYOUT_MAX_COLS, cols))
        height = item.get("h")
        if height is not None:
            try:
                height = max(LAYOUT_MIN_H, min(LAYOUT_MAX_H, int(height)))
            except (TypeError, ValueError):
                height = None
        clean.append({"id": pid, "cols": cols, "h": height})

    if not clean:
        return "Layout not saved - nothing in the request was usable."

    os.makedirs(os.path.dirname(LAYOUT_FILE), exist_ok=True)
    with open(LAYOUT_FILE, "w") as f:
        json.dump({"panels": clean}, f, indent=2)
    return f"Layout saved ({len(clean)} panels)."


# The rebuilt console keeps its own small piece of state in the same file:
# which view is on the main screen, which of the two layouts is in use, and
# where the instructor has dragged the two corner tiles. Separate key, so a
# saved panel layout from the classic page is untouched and either page can
# be used without destroying the other's arrangement.
CONSOLE_DEFAULT = {"hero": "chase", "layout": "pilot", "tiles": {},
                   "rails": {}, "shut": None}
CONSOLE_HEROES = ("chase", "nose", "map")
CONSOLE_LAYOUTS = ("pilot", "station")
TILE_MIN_W, TILE_MAX_W = 150, 520
TILE_MIN_H, TILE_MAX_H = 96, 300
RAIL_MIN_W, RAIL_MAX_W = 96, 760
RAIL_MIN_H, RAIL_MAX_H = 90, 2000


def read_console_layout():
    saved = read_layout().get("console")
    if not isinstance(saved, dict):
        return dict(CONSOLE_DEFAULT)
    out = dict(CONSOLE_DEFAULT)
    if saved.get("hero") in CONSOLE_HEROES:
        out["hero"] = saved["hero"]
    if saved.get("layout") in CONSOLE_LAYOUTS:
        out["layout"] = saved["layout"]
    tiles = saved.get("tiles")
    if isinstance(tiles, dict):
        out["tiles"] = {k: v for k, v in tiles.items()
                        if k in ("left", "right") and isinstance(v, dict)}
    rails = saved.get("rails")
    if isinstance(rails, dict):
        out["rails"] = {k: v for k, v in rails.items()
                        if k in ("left", "right") and isinstance(v, dict)}
    shut = saved.get("shut")
    out["shut"] = [str(x)[:60] for x in shut] if isinstance(shut, list) else None
    return out


def console_state_for_page():
    """The saved console state, with the first-run defaults filled in.

    A console that has never been arranged starts with the occasional
    sections collapsed, so the right rail fits a laptop screen without
    scrolling to find Freeze."""
    state = read_console_layout()
    if state["shut"] is None:
        state["shut"] = list(RAIL_SHUT_BY_DEFAULT)
    return state


def write_console_layout(data):
    """Validates and saves the console's own state. Returns a message.

    Clamped rather than trusted: a tile saved at a negative size or off the
    screen would be unreachable on the next load, with no way back except
    deleting the file by hand.
    """
    clean = dict(CONSOLE_DEFAULT)
    if data.get("hero") in CONSOLE_HEROES:
        clean["hero"] = data["hero"]
    if data.get("layout") in CONSOLE_LAYOUTS:
        clean["layout"] = data["layout"]

    tiles = {}
    for side in ("left", "right"):
        box = (data.get("tiles") or {}).get(side)
        if not isinstance(box, dict):
            continue
        try:
            x, y = int(box["x"]), int(box["y"])
            w = max(TILE_MIN_W, min(TILE_MAX_W, int(box["w"])))
            h = max(TILE_MIN_H, min(TILE_MAX_H, int(box["h"])))
        except (KeyError, TypeError, ValueError):
            continue
        tiles[side] = {"x": max(0, x), "y": max(0, y), "w": w, "h": h}
    clean["tiles"] = tiles

    # The rails are panels now: an instructor can drag one off its edge,
    # resize it, or turn it into a horizontal bar. Clamped for the same
    # reason the tiles are - a panel saved off-screen or at zero size would
    # be unreachable on the next load.
    rails = {}
    for side in ("left", "right"):
        box = (data.get("rails") or {}).get(side)
        if not isinstance(box, dict):
            continue
        try:
            x, y = int(box["x"]), int(box["y"])
            w = max(RAIL_MIN_W, min(RAIL_MAX_W, int(box["w"])))
            h = max(RAIL_MIN_H, min(RAIL_MAX_H, int(box["h"])))
        except (KeyError, TypeError, ValueError):
            continue
        rails[side] = {"x": max(0, x), "y": max(0, y), "w": w, "h": h,
                       "horizontal": bool(box.get("horizontal"))}
    clean["rails"] = rails

    shut = data.get("shut")
    clean["shut"] = ([str(x)[:60] for x in shut if isinstance(x, str)][:40]
                     if isinstance(shut, list) else [])

    existing = read_layout()
    existing["console"] = clean
    try:
        os.makedirs(os.path.dirname(LAYOUT_FILE), exist_ok=True)
        with open(LAYOUT_FILE, "w") as handle:
            json.dump(existing, handle, indent=2)
    except OSError as exc:
        return f"Console layout not saved - {exc.strerror}."
    return "Console layout saved."


def clear_layout():
    try:
        os.remove(LAYOUT_FILE)
        return "Layout reset to the default arrangement."
    except FileNotFoundError:
        return "Already using the default arrangement."
    except OSError as exc:
        return f"Could not reset the layout - {exc.strerror}."

# ---------------------------------------------------------------------------
# CAP722B 5.3(c) - operational-limit envelope. The instructor gets an
# on-screen warning as the aircraft approaches (amber) or exceeds (red)
# any of these, and every state change is written to the event log.
# Edit these per training area / airframe - or later, drive them from the
# environment_selector once that's wired in.
# ---------------------------------------------------------------------------
LIMITS = {
    "ceiling_m": 120.0,          # height above the home/launch point
    "range_m": 500.0,            # lateral distance from home
    "groundspeed_ms": 30.0,      # ground speed
    "battery_warn_pct": 30,      # amber below this
    "battery_critical_pct": 15,  # red below this
}
# "Approaching" a max-type limit = within this fraction of it.
LIMIT_WARN_FRACTION = 0.9

# Remembered so a transition (ok->warn->breach and back) is logged once,
# not every poll. metric name -> "ok" | "warn" | "breach".
_limit_state = {}
_limit_lock = threading.Lock()
_video_node = start_video_capture()  # starts listening for camera frames immediately
plugins = load_plugins()
plugins_by_id = {p["id"]: p for p in plugins}

# Group plugins by category, in a sensible fixed order
CATEGORY_ORDER = ["Flight Ops", "Flight Mode", "Function Test", "Failure Injection", "Simulation Control", "Camera", "Experimental - In Development"]

# The rebuilt console has two rails rather than a grid. The split is by who
# the control is for: the left rail is what a pilot does, the right rail is
# what only an instructor does to them.
LEFT_CATEGORIES = ["Flight Ops", "Flight Mode", "Emergency"]
RIGHT_CATEGORIES = ["Failure Injection", "Simulation Control", "Camera",
                    "Function Test", "Experimental - In Development"]

# Plugins load in filename order, which put TERMINATE FLIGHT third in the
# left rail - between DISARM and HOLD, where a mis-click lives. Order the
# rails by what a pilot reaches for, not by what the files are called;
# anything not listed keeps its loaded order, after the ones that are.
RAIL_ORDER = {
    "Flight Ops": ["arm", "disarm", "takeoff", "climb_to", "land", "rtl",
                   "hold", "set_home"],
    "Flight Mode": ["hover_flight", "forward_flight", "loiter", "mode_position",
                    "mode_manual"],
    "Failure Injection": ["gps_failure", "data_link_loss", "rc_signal_loss",
                          "engine_failure", "motor_failure"],
    # NEW SESSION first: it is the one an instructor reaches for between
    # students, and alphabetical order buried it under the environment
    # selector.
    "Simulation Control": ["new_session", "environment", "freeze_resume",
                           "reset_scenario", "reset_spawn", "set_home"],
}


# Labels written for a wide panel do not fit a 120px rail. These are the
# rail's own shorter names; the plugin's own label is used for anything not
# listed, and the classic page is untouched.
RAIL_LABELS = {
    "rtl": "Return to launch",
    "climb_to": "Climb / descend",
    "set_home": "Set home here",
    "hover_flight": "Hover (MC)",
    "forward_flight": "Forward (FW)",
    "mode_manual": "Manual",
    "mode_position": "Position",
    "flight_termination": "TERMINATE",
    "gps_failure": "GPS failure",
    "data_link_loss": "Data link (C2)",
    "rc_signal_loss": "RC signal loss",
    "engine_failure": "Engine failure",
    "motor_failure": "Motor failure",
    "reset_spawn": "Reset to spawn",
    "reset_scenario": "Reset scenario",
    "freeze": "Freeze / resume",
    "environment": "Load area",
    "external_view": "Set view",
    "start_stabilizer": "Stabiliser",
    "start_video": "FPV video",
    "motor_test_5": "Motor 5 (pusher)",
    "motor_test_1": "Motor 1",
    "motor_test_2": "Motor 2",
    "motor_test_3": "Motor 3",
    "motor_test_4": "Motor 4",
    "weather": "Set weather",
    "wind_gust": "Wind on / off",
}

# Sections that start collapsed on a console that has never been arranged:
# the ones an instructor opens occasionally rather than every lesson.
RAIL_SHUT_BY_DEFAULT = ["function-test", "experimental-in-development"]


def _rail_sorted(cat, items):
    order = RAIL_ORDER.get(cat)
    if not order:
        return items
    rank = {pid: n for n, pid in enumerate(order)}
    return sorted(items, key=lambda p: rank.get(p["id"], len(rank)))
categories = {cat: [] for cat in CATEGORY_ORDER}
for p in plugins:
    categories.setdefault(p["category"], []).append(p)


def failure_status():
    """Which plugins are currently in their "active/failed" state, so the
    button can show a live on/off light. Only plugins that expose a
    module-level `state` dict with an "active" key are included (the
    toggle-style failure plugins) - added 23 Aug 2026, directly prompted
    by a live test where a motor/engine/GPS/RC failure was left switched
    on without anyone noticing, because there was no visual reminder."""
    status = {}
    for p in plugins:
        state = getattr(p.get("_module"), "state", None)
        if isinstance(state, dict) and "active" in state:
            status[p["id"]] = bool(state["active"])
    return status


def _check_one(name, value, limit, kind, label, unit):
    """Classify one metric as ok / warn / breach against its limit.
    kind='max' -> high is bad; kind='min' -> low is bad. Returns
    (level, human_text_or_None)."""
    if value is None:
        return "ok", None
    if kind == "max":
        if value > limit:
            return "breach", f"{label} {value:g}{unit} — over the {limit:g}{unit} limit"
        if value >= limit * LIMIT_WARN_FRACTION:
            return "warn", f"{label} {value:g}{unit} — approaching the {limit:g}{unit} limit"
    else:  # min
        if value < limit:
            return "breach", f"{label} {value:g}{unit} — below {limit:g}{unit}"
    return "ok", None


def limit_status():
    """CAP722B 5.3(c) - where the aircraft sits against its operational
    limits right now. Returns {"level": ok|warn|breach, "items": [text,...]}
    and logs each metric's transitions to the event log."""
    checks = [
        _check_one("ceiling", telemetry.get("altitude_m"), LIMITS["ceiling_m"], "max", "Altitude", " m"),
        _check_one("range", telemetry.get("range_from_home_m"), LIMITS["range_m"], "max", "Range from home", " m"),
        _check_one("speed", telemetry.get("groundspeed_ms"), LIMITS["groundspeed_ms"], "max", "Ground speed", " m/s"),
    ]
    batt = telemetry.get("battery_pct")
    if batt is not None:
        if batt < LIMITS["battery_critical_pct"]:
            checks.append(("breach", f"Battery {batt}% — below the {LIMITS['battery_critical_pct']}% critical level"))
        elif batt < LIMITS["battery_warn_pct"]:
            checks.append(("warn", f"Battery {batt}% — below the {LIMITS['battery_warn_pct']}% warning level"))
        else:
            checks.append(("ok", None))

    metric_names = ["ceiling", "range", "speed", "battery"]
    items, worst = [], "ok"
    with _limit_lock:
        for metric, (level, text) in zip(metric_names, checks):
            if text:
                items.append(text)
            if level == "breach" or (level == "warn" and worst != "breach"):
                worst = level
            prev = _limit_state.get(metric, "ok")
            if level != prev:
                _limit_state[metric] = level
                if level == "ok":
                    event_logger.log_event("limit_cleared", f"metric={metric}")
                else:
                    event_logger.log_event(
                        "limit_breach" if level == "breach" else "limit_warning",
                        f"metric={metric} detail={text}")
    return {"level": worst, "items": items}


def health_status():
    """CAP722B 5.2(d) - a visible indication of how fresh/responsive the
    data feeds are: telemetry age and measured camera frame rate."""
    last = link_health.get("last_msg_t")
    age = round(time.monotonic() - last, 1) if last is not None else None
    return {"telemetry_age_s": age, "camera_fps": camera_fps()}


def _panel_id(category):
    """Stable, URL-safe id for a category panel, so a saved layout keeps
    referring to the same panel across restarts."""
    return re.sub(r"[^a-z0-9]+", "-", category.lower()).strip("-")


def _render_inputs(p):
    """The number boxes and drop-downs a plugin declares, as HTML."""
    fields = ""
    for inp in p.get("inputs", []):
        fid = f'in-{p["id"]}-{inp["name"]}'
        common = (f'id="{fid}" class="param-input" data-plugin="{p["id"]}" '
                  f'data-param="{inp["name"]}"')

        # A number box unless the plugin asks for a drop-down. Added
        # 11 Oct 2026 for the external-view plugin, where the choice
        # is one of a fixed set of viewpoints rather than a quantity.
        if inp.get("type") == "select":
            options = ""
            for opt in inp.get("options", []):
                selected = " selected" if opt["value"] == inp.get("default") else ""
                options += f'<option value="{opt["value"]}"{selected}>{opt["label"]}</option>'
            control = f'<select {common}>{options}</select>'
        else:
            attrs = f'value="{inp.get("default", "")}"'
            if "min" in inp:
                attrs += f' min="{inp["min"]}"'
            if "max" in inp:
                attrs += f' max="{inp["max"]}"'
            attrs += f' step="{inp.get("step", "any")}"'
            control = f'<input type="number" {common} {attrs}>'

        fields += (f'<label class="field"><span>{inp["label"]}</span>'
                   f'{control}</label>')
    return fields


def render_rail(category_names):
    """One rail of the rebuilt console: the plugins of these categories, in
    order, under their headings.

    Toggle-style plugins carry a light (#dot-<id>) that the page updates from
    /failure_status, because a failure left switched on with no visible
    reminder is the fault that prompted the lights in the first place."""
    status = failure_status()
    html = ""
    for cat in category_names:
        items = categories.get(cat, [])
        if not items:
            continue
        short = cat.replace(" - In Development", "")
        danger = " danger" if cat in ("Failure Injection", "Emergency") else ""
        section = _panel_id(cat)
        html += (f'<div class="group" data-section="{section}">'
                 f'<button class="head{danger}">{short}<span class="chev">&#9660;</span></button>'
                 f'<div class="items">')
        for p in _rail_sorted(cat, items):
            dot = ""
            klass = p["style"]
            if p["id"] in status:
                dot = f'<span class="dot{" on" if status[p["id"]] else ""}" id="dot-{p["id"]}"></span>'
                klass += " has-dot"
                klass += " on" if status[p["id"]] else ""
            if p["id"] == "arm":
                klass += " arm"
            elif p["id"] == "disarm":
                klass += " disarm"
            label = RAIL_LABELS.get(p["id"], p["label"])
            button = (f'<button id="btn-{p["id"]}" class="{klass}" '
                      f'onclick="send(\'{p["id"]}\')">{dot}{label}</button>')
            fields = _render_inputs(p)
            html += f'<div class="stack">{fields}{button}</div>' if fields else button
        html += "</div></div>"
    return html


def _limits_script():
    """The operational limits, handed to the page so the flight display can
    mark the ceiling on its altitude tape instead of carrying its own copy."""
    return ("<script>window.GCS_LIMITS = %s;</script>"
            % json.dumps({"range_m": LIMITS["range_m"],
                          "ceiling_m": LIMITS["ceiling_m"],
                          "groundspeed_ms": LIMITS["groundspeed_ms"]}))


def render_console():
    """The rebuilt console page, assembled from the plugins and the saved
    arrangement. The classic page is still built by render_buttons below and
    served at /classic."""
    page = console_page.TEMPLATE
    page = page.replace("__LEFT_RAIL__", render_rail(LEFT_CATEGORIES))
    page = page.replace("__RIGHT_RAIL__", render_rail(RIGHT_CATEGORIES))
    script = console_page.SCRIPT
    script = script.replace("__SAVED__", json.dumps(console_state_for_page()))
    script = script.replace("__LIMITS__", json.dumps({
        "range_m": LIMITS["range_m"],
        "ceiling_m": LIMITS["ceiling_m"],
        "groundspeed_ms": LIMITS["groundspeed_ms"],
    }))
    page = page.replace("__CONSOLE_SCRIPT__", script)
    page = page.replace("__EXTRA_STYLE__", EXTRA_STYLE)
    page = page.replace("__EXTRA_SCRIPT__", EXTRA_SCRIPT
                        + _limits_script()
                        + flight_display.STYLE + flight_display.script())
    return page


def render_buttons():
    html = ""
    status = failure_status()
    for cat in CATEGORY_ORDER:
        items = categories.get(cat, [])
        if not items:
            continue
        html += (f'<div class="panel" id="panel-{_panel_id(cat)}">'
                 f'<div class="panel-title">{cat}</div><div class="row">')
        for p in items:
            dot = ""
            if p["id"] in status:
                dot_class = "dot-active" if status[p["id"]] else "dot-inactive"
                dot = f'<span class="status-dot {dot_class}" id="dot-{p["id"]}"></span>'
            button = f'<button class="{p["style"]}" onclick="send(\'{p["id"]}\')">{dot}{p["label"]}</button>'

            # Plugins may declare an "inputs" list - number boxes the
            # instructor fills in before pressing the button (e.g. LOITER
            # radius). Their values are sent as query parameters and passed
            # to the plugin's handler as keyword arguments.
            fields = ""
            for inp in p.get("inputs", []):
                fid = f'in-{p["id"]}-{inp["name"]}'
                common = (f'id="{fid}" class="param-input" data-plugin="{p["id"]}" '
                          f'data-param="{inp["name"]}"')

                # A number box unless the plugin asks for a drop-down. Added
                # 11 Oct 2026 for the external-view plugin, where the choice
                # is one of a fixed set of viewpoints rather than a quantity.
                if inp.get("type") == "select":
                    options = ""
                    for opt in inp.get("options", []):
                        selected = " selected" if opt["value"] == inp.get("default") else ""
                        options += f'<option value="{opt["value"]}"{selected}>{opt["label"]}</option>'
                    control = f'<select {common}>{options}</select>'
                else:
                    attrs = f'value="{inp.get("default", "")}"'
                    if "min" in inp:
                        attrs += f' min="{inp["min"]}"'
                    if "max" in inp:
                        attrs += f' max="{inp["max"]}"'
                    attrs += f' step="{inp.get("step", "any")}"'
                    control = f'<input type="number" {common} {attrs}>'

                fields += (f'<label class="field"><span>{inp["label"]}</span>'
                           f'{control}</label>')
            if fields:
                html += f'<div class="btn-stack">{fields}{button}</div>'
            else:
                html += button
        html += '</div></div>'
    return html


# Shown immediately when the app window opens, before PX4 has answered.
# Polls /connection_status and reloads itself once connected, at which
# point the server below starts handing out PAGE_TEMPLATE instead.
CONNECTING_PAGE = """
<!DOCTYPE html>
<html>
<head>
<title>UAV Academy GCS Pro</title>
<style>
  body {
    font-family: -apple-system, 'Segoe UI', sans-serif;
    background: #0a0e14; color: #eee; margin: 0; height: 100vh;
    display: flex; flex-direction: column; align-items: center; justify-content: center;
  }
  .brand { font-weight: 700; font-size: 15px; letter-spacing: 1px; color: #4a90d9; margin-bottom: 26px; }
  .spinner {
    width: 34px; height: 34px; border-radius: 50%;
    border: 3px solid #232f40; border-top-color: #4a90d9;
    animation: spin 0.9s linear infinite; margin-bottom: 22px;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  #msg { font-size: 14px; color: #9aa7bd; max-width: 440px; text-align: center; line-height: 1.5; }
</style>
</head>
<body>
  <div class="brand">UAV ACADEMY GCS PRO</div>
  <div class="spinner"></div>
  <div id="msg">Connecting to the simulator...</div>
<script>
function poll() {
  fetch('/connection_status').then(r => r.json()).then(d => {
    document.getElementById('msg').innerText = d.message;
    if (d.connected) {
      location.reload();
    } else {
      setTimeout(poll, 700);
    }
  }).catch(() => setTimeout(poll, 700));
}
poll();
</script>
</body>
</html>
"""


PAGE_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<title>UAV Academy GCS Pro</title>
<style>
  * {{ box-sizing: border-box; }}
  body {{
    font-family: -apple-system, 'Segoe UI', sans-serif;
    background: #0a0e14; color: #eee; margin: 0; height: 100vh; overflow: hidden;
    display: flex; flex-direction: column;
  }}

  /* ===== Top status bar ===== */
  .topbar {{
    background: #10151d; border-bottom: 1px solid #1f2733;
    display: flex; align-items: center; padding: 0 20px; height: 56px; flex-shrink: 0;
    gap: 28px;
  }}
  .brand {{ font-weight: 700; font-size: 15px; letter-spacing: 1px; color: #4a90d9; margin-right: 10px; }}
  .status-item {{ display: flex; flex-direction: column; }}
  .status-item .k {{ font-size: 9px; color: #62708a; text-transform: uppercase; letter-spacing: 0.5px; }}
  .status-item .v {{ font-size: 14px; font-weight: 600; margin-top: 1px; }}
  .armed-yes {{ color: #ff5252; }}
  .armed-no {{ color: #4caf50; }}
  /* Arming readiness (added 11 Oct 2026). Green means PX4 has said its
     preflight checks pass, so TAKEOFF will be accepted; red means it will
     be refused and the text says what PX4 is unhappy about. */
  .arm-ready {{ color: #4caf50; }}
  .arm-wait {{ color: #ffb300; }}
  .arm-block {{ color: #ff8a8a; }}

  /* ===== Body: sidebar + main ===== */
  .body-row {{ display: flex; flex: 1; overflow: hidden; }}

  .sidebar {{
    width: 200px; background: #0d1219; border-right: 1px solid #1f2733;
    padding: 14px 0; overflow-y: auto; flex-shrink: 0;
  }}
  .nav-item {{
    padding: 10px 20px; font-size: 13px; color: #62708a; cursor: default;
    border-left: 3px solid transparent;
  }}
  .nav-item.active {{ color: #eee; border-left-color: #4a90d9; background: #131a24; }}

  .main {{ flex: 1; padding: 20px; overflow-y: auto; }}

  /* A 12-column tiling grid holding every panel. Panels declare how many
     columns they span rather than a pixel width, so a layout an instructor
     saves still fits when the station runs on a different screen. */
  /* align-items: start stops each panel stretching to the height of the
     tallest one in its row - which is what made the console look
     stretched and forced scrolling even after a fit. */
  .grid {{
    display: grid; grid-template-columns: repeat(12, 1fr); gap: 14px;
    align-content: start; align-items: start;
  }}
  .panel {{
    background: #131c28; border: 1px solid #232f40; border-radius: 14px; padding: 16px;
    grid-column: span 4; position: relative; min-width: 0; overflow: auto;
  }}
  .panel-title {{ font-size: 11px; text-transform: uppercase; letter-spacing: 1px; color: #62708a; margin-bottom: 10px; }}
  .row {{ display: flex; gap: 8px; flex-wrap: wrap; }}

  button {{
    position: relative;
    font-size: 13px; font-weight: 600; padding: 11px 14px;
    border-radius: 9px; border: none; cursor: pointer; flex: 1; min-width: 110px;
    transition: transform 0.08s ease;
  }}
  button:active {{ transform: scale(0.96); }}
  .arm {{ background: #2e7d32; color: white; }}
  .disarm {{ background: #c62828; color: white; }}
  .normal {{ background: #1565c0; color: white; }}
  .highlight {{ background: #ef6c00; color: white; }}
  .warning {{ background: #ad1457; color: white; }}
  .experimental {{ background: #1a1a1a; color: #666; border: 1px dashed #333; cursor: not-allowed; }}

  /* Buttons that take an instructor-entered value before firing (e.g.
     LOITER radius) - the number box(es) sit directly above the button. */
  .btn-stack {{ display: flex; flex-direction: column; gap: 6px; flex: 1; min-width: 110px; }}
  .btn-stack button {{ width: 100%; flex: none; }}
  .field {{ display: flex; flex-direction: column; gap: 2px; }}
  .field span {{ font-size: 9px; text-transform: uppercase; letter-spacing: 0.5px; color: #62708a; }}
  .param-input {{
    background: #0d1219; border: 1px solid #2c3a4d; border-radius: 7px;
    color: #eee; font-size: 13px; font-weight: 600; padding: 8px 10px; width: 100%;
  }}
  .param-input:focus {{ outline: none; border-color: #4a90d9; }}
  select.param-input {{ cursor: pointer; }}

  /* Small on/off status light for toggle-style failure buttons (GPS, RC
     Signal, Data Link, Motor, Engine) - added 23 Aug 2026 so a failure
     left switched on is impossible to miss, after a live test where
     exactly that happened. Red+pulsing = currently active/failed,
     matching the standard aviation convention that red means a fault
     needs attention; green = normal/restored. */
  .status-dot {{
    position: absolute; top: 6px; right: 6px;
    width: 10px; height: 10px; border-radius: 50%;
    border: 1.5px solid rgba(0,0,0,0.35);
  }}
  .dot-inactive {{ background: #4caf50; }}
  .dot-active {{
    background: #ff1744;
    box-shadow: 0 0 6px 2px rgba(255,23,68,0.6);
    animation: dotpulse 1.1s ease-in-out infinite;
  }}
  @keyframes dotpulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.45; }} }}

  .video-placeholder {{
    background: #0d1219; border: 1px dashed #2c3a4d; border-radius: 14px;
    padding: 40px 20px; text-align: center; color: #4a5568; font-size: 12px;
    max-width: 900px; margin-top: 14px;
  }}

  #status {{ margin-top: 16px; font-size: 12px; color: #62708a; }}

  /* CAP722B 5.3(c) - operational-limit warning strip. Sits between the
     top status bar and the main area so it's impossible to miss. */
  .limit-banner {{
    padding: 8px 20px; font-size: 13px; font-weight: 600; flex-shrink: 0;
    display: flex; gap: 16px; flex-wrap: wrap; align-items: center;
  }}
  .limit-banner.warn {{ background: #4a3a12; color: #ffca6b; border-bottom: 1px solid #6b551f; }}
  .limit-banner.breach {{
    background: #4a1414; color: #ff8a8a; border-bottom: 1px solid #7a2020;
    animation: limitpulse 1.1s ease-in-out infinite;
  }}
  @keyframes limitpulse {{ 0%, 100% {{ opacity: 1; }} 50% {{ opacity: 0.55; }} }}
  .limit-banner .tag {{
    text-transform: uppercase; letter-spacing: 1px; font-size: 11px;
    padding: 2px 7px; border-radius: 4px; background: rgba(0,0,0,0.3);
  }}
  #t-health.stale {{ color: #ff8a8a; }}
</style>
</head>
<body>
  <div class="topbar">
    <div class="brand">UAV ACADEMY GCS PRO</div>
    <div class="status-item"><div class="k">Vehicle</div><div class="v">STANDARD_VTOL-01</div></div>
    <div class="status-item"><div class="k">Mode</div><div class="v" id="t-mode">-</div></div>
    <div class="status-item"><div class="k">Status</div><div class="v" id="t-armed">-</div></div>
    <div class="status-item"><div class="k">Arming</div><div class="v" id="t-armcheck" title="Whether PX4 will accept ARM / TAKEOFF right now">-</div></div>
    <div class="status-item"><div class="k">Altitude</div><div class="v" id="t-alt">-</div></div>
    <div class="status-item"><div class="k">Speed</div><div class="v" id="t-speed">-</div></div>
    <div class="status-item"><div class="k">Heading</div><div class="v" id="t-heading">-</div></div>
    <div class="status-item"><div class="k">GPS</div><div class="v" id="t-gps">-</div></div>
    <div class="status-item"><div class="k">Battery</div><div class="v" id="t-batt">-</div></div>
    <div class="status-item"><div class="k">Feeds</div><div class="v" id="t-health" title="Telemetry age / camera frame rate">-</div></div>
  </div>

  <div id="limit-banner" class="limit-banner" style="display:none;"></div>

  <div class="body-row">
    <div class="sidebar">
      <div class="nav-item active">INSTRUCTOR<br><span style="font-size:11px;color:#4a5568;">Simulator Controls</span></div>
      <div class="nav-item">FLY (coming soon)</div>
      <div class="nav-item">PLAN / MISSION (coming soon)</div>
      <div class="nav-item">PAYLOAD / CAMERA (coming soon)</div>
      <div class="nav-item">LOGS (coming soon)</div>
    </div>

    <div class="main">
      <div class="layout-controls" id="layout-controls">
        <button id="layout-fit" class="layout-btn" title="Shrink the panels until the whole console fits this screen without scrolling">⇲ Fit to screen</button>
        <button id="layout-lock" class="layout-btn locked" title="Unlock to move and resize panels">■ Layout locked</button>
        <button id="layout-reset" class="layout-btn" title="Discard the saved layout and go back to the default arrangement">Reset</button>
        <span id="layout-hint" class="layout-hint"></span>
      </div>
      <div class="grid" id="panel-grid">
        {buttons}
      <div class="panel" id="panel-fpv">
        <div class="panel-title">Live Nose Camera (FPV) &mdash; Forward View + Attitude</div>
        <div class="fpv-wrap">
          <img src="/video_feed" class="fpv-video"
               onerror="this.style.display='none'; document.getElementById('video-fallback').style.display='block';">
          <canvas id="hud" class="fpv-hud" width="960" height="540"></canvas>
        </div>
        <div id="video-fallback" style="display:none; color:#62708a; font-size:12px; padding:20px; text-align:center;">
          No video signal yet - camera stream starts once the simulator is running.
        </div>
        <label class="hud-toggle"><input type="checkbox" id="hud-on" checked> Attitude overlay</label>
      </div>
      <div class="panel" id="panel-chase">
        <div class="panel-title">Chase Camera &mdash; Behind and Above the Aircraft</div>
        <img src="/chase_feed" class="fpv-video"
             onerror="this.style.display='none'; document.getElementById('chase-fallback').style.display='block';">
        <div id="chase-fallback" style="display:none; color:#62708a; font-size:12px; padding:20px; text-align:center;">
          No chase camera. Add it with tools/chase_camera_apply.py, then restart the simulator.
        </div>
      </div>
      <!--EXTRA_PANELS-->
      </div>
      <div id="status">Ready.</div>
    </div>
  </div>

<script>
function send(id) {{
  document.getElementById('status').innerText = 'Sending...';
  const params = new URLSearchParams();
  document.querySelectorAll('.param-input[data-plugin="' + id + '"]').forEach(el => {{
    params.append(el.dataset.param, el.value);
  }});
  const qs = params.toString();
  fetch('/action/' + id + (qs ? '?' + qs : '')).then(r => r.text()).then(t => {{
    document.getElementById('status').innerText = t;
    refreshFailureStatus();
  }});
}}
function refreshTelemetry() {{
  fetch('/telemetry').then(r => r.json()).then(d => {{
    const armedEl = document.getElementById('t-armed');
    armedEl.innerText = d.armed ? 'ARMED' : 'Disarmed';
    armedEl.className = 'v ' + (d.armed ? 'armed-yes' : 'armed-no');
    const armChk = document.getElementById('t-armcheck');
    // PX4 prefixes its reason with "Preflight Fail:" / "Preflight:", which is
    // redundant next to a label that already says "Not ready".
    const why = d.arm_blocker
      ? d.arm_blocker.replace(/^Preflight( Fail)?: */i, '') : '';
    armChk.innerText = why ? (d.arm_state + ' - ' + why.slice(0, 48)) : d.arm_state;
    armChk.title = d.arm_blocker
      ? ('PX4 says: ' + d.arm_blocker)
      : 'PX4 reports no blocking preflight check.';
    armChk.className = 'v ' + (d.arm_ready === null ? 'arm-wait'
                               : d.arm_ready ? 'arm-ready' : 'arm-block');
    document.getElementById('t-mode').innerText = d.mode;
    document.getElementById('t-alt').innerText = d.altitude_m + ' m';
    document.getElementById('t-speed').innerText = d.groundspeed_ms + ' m/s';
    document.getElementById('t-heading').innerText = d.heading_deg + '\\u00b0';
    document.getElementById('t-gps').innerText = d.satellites !== null ? d.satellites + ' sats' : '-';
    document.getElementById('t-batt').innerText = d.battery_pct !== null ? d.battery_pct + '%' : '-';
  }});
}}
function refreshFailureStatus() {{
  fetch('/failure_status').then(r => r.json()).then(d => {{
    for (const id in d) {{
      const dot = document.getElementById('dot-' + id);
      if (dot) {{
        dot.className = 'status-dot ' + (d[id] ? 'dot-active' : 'dot-inactive');
      }}
    }}
  }});
}}
setInterval(refreshTelemetry, 1000);
setInterval(refreshFailureStatus, 1000);
refreshTelemetry();
refreshFailureStatus();
</script>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# Extra views bolted onto the page after PAGE_TEMPLATE.format() - kept as
# plain strings (not format templates) so the JS below doesn't need every
# brace doubled. Added 3 Sep 2026:
#   * Flight Path  - a north-up plan view of where the aircraft has flown,
#                    from GLOBAL_POSITION_INT history (/flight_path).
#   * FPV overlay  - an artificial-horizon / attitude ("gyro") HUD drawn
#                    on top of the nose-camera stream, from ATTITUDE.
# ---------------------------------------------------------------------------
EXTRA_PANELS = """
<div class="panel" id="panel-flightpath">
  <div class="panel-title">Flight Path &mdash; Plan View (North Up)</div>
  <canvas id="flightpath"></canvas>
  <div class="fp-legend">
    <span><b id="fp-range">-</b> across</span>
    <span><b id="fp-dist">-</b> from home</span>
    <span><b id="fp-alt">-</b> altitude</span>
    <span><b id="fp-points">0</b> track points</span>
    <span>map: <b id="fp-backdrop">-</b></span>
    <span style="color:#ff3b30">&#9650;</span> aircraft
    <span style="color:#4caf50">&#9679;</span> home
  </div>
</div>
"""

EXTRA_STYLE = """
<style>
  .fpv-wrap { position: relative; width: 100%; border-radius: 10px; overflow: hidden; background: #000; }
  .fpv-video { width: 100%; display: block; }
  .fpv-hud { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; }
  .hud-toggle { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: #62708a; margin-top: 8px; }
  #flightpath { width: 100%; height: 420px; display: block; background: #0d1219; border-radius: 10px; }
  .fp-legend { display: flex; gap: 16px; font-size: 11px; color: #62708a; margin-top: 8px; flex-wrap: wrap; align-items: center; }
  .fp-legend b { color: #eee; font-weight: 600; }
</style>
"""

EXTRA_SCRIPT = """
<script>
(function () {
  var telem = {};
  function poll() {
    fetch('/telemetry').then(function (r) { return r.json(); })
      .then(function (d) { telem = d; window.gcsTelemetry = d; })
      .catch(function () {});
  }
  setInterval(poll, 200); poll();

  // REVISED 11 Oct 2026: a canvas sized in CSS pixels is drawn at one
  // device pixel per CSS pixel and then scaled up by the display, which is
  // why the map and the attitude overlay looked soft. Size the backing
  // store by devicePixelRatio and scale the context to match, so the
  // drawing code below can keep working in CSS pixels through cv.cssW/cssH.
  function fit(cv) {
    var w = cv.clientWidth, h = cv.clientHeight;
    if (!w || !h) { return; }
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var bw = Math.round(w * dpr), bh = Math.round(h * dpr);
    cv.cssW = w; cv.cssH = h;
    if (cv.width !== bw || cv.height !== bh) {
      cv.width = bw; cv.height = bh;
    }
    var ctx = cv.getContext('2d');
    ctx.setTransform(cv.width / w, 0, 0, cv.height / h, 0, 0);
  }

  // The attitude display moved to flight_display.py on 11 Oct 2026, where
  // it is drawn into every canvas on the page carrying class "hud" or
  // "fpv-hud" - the nose view, the chase view and this page - instead of
  // into one canvas looked up by id. See that module for the layout and
  // for the low-altitude warning it also drives.

  // ---------- Flight path plan view ----------
  var fp = document.getElementById('flightpath');
  var fctx = fp.getContext('2d');

  // Smallest the plan view ever shows, in metres across. The station's range
  // limit is 500 m, so 300 m keeps the whole working area in sight from the
  // moment the aircraft is on the pad.
  var MAP_MIN_SPAN_M = 300;
  var mapZoom = 1;
  function setMapZoom(z) {
    mapZoom = Math.max(0.25, Math.min(16, z));
    var out = document.getElementById('fp-zoom');
    if (out) { out.innerText = (mapZoom < 1 ? mapZoom.toFixed(2) : mapZoom.toFixed(1)) + 'x'; }
    drawPath();
  }
  document.addEventListener('click', function (e) {
    var b = e.target.closest ? e.target.closest('[data-mapzoom]') : null;
    if (!b) { return; }
    var how = b.dataset.mapzoom;
    setMapZoom(how === 'in' ? mapZoom * 1.5 : how === 'out' ? mapZoom / 1.5 : 1);
  });

  // Shaded relief of the world's own terrain, under the track. Loaded once;
  // a world with no heightmap (flat_test) reports available:false and the
  // plan view stays as it was.
  var terrainInfo = null, terrainImg = null;
  // Say which backdrop is under the track. "Is the satellite view working?"
  // was being answered by squinting at a pale square of playa, which looks
  // the same whether the imagery loaded or not.
  function showBackdrop(text) {
    var out = document.getElementById('fp-backdrop');
    if (out) { out.innerText = text; }
  }
  showBackdrop('loading...');
  fetch('/terrain_info').then(function (r) { return r.json(); }).then(function (d) {
    terrainInfo = d;
    if (!d.available) { showBackdrop('none for this world'); return; }
    var img = new Image();
    img.onload = function () {
      terrainImg = img;
      showBackdrop(d.source === 'satellite'
                   ? (d.credit || 'satellite imagery')
                   : 'shaded relief');
    };
    img.onerror = function () { showBackdrop('failed to load'); };
    img.src = '/terrain.png';
  }).catch(function () { showBackdrop('unavailable'); });
  function niceStep(x) {
    if (x <= 0) return 100;
    var p = Math.pow(10, Math.floor(Math.log(x) / Math.LN10));
    var n = x / p;
    return (n < 1.5 ? 1 : n < 3.5 ? 2 : n < 7.5 ? 5 : 10) * p;
  }
  function fmt(m) { return m >= 1000 ? (m / 1000).toFixed(m >= 10000 ? 0 : 1) + ' km' : m.toFixed(0) + ' m'; }
  function drawPath() {
    fetch('/flight_path').then(function (r) { return r.json(); }).then(function (data) {
      var W = fp.cssW || fp.width, H = fp.cssH || fp.height;
      fctx.clearRect(0, 0, W, H);
      if (!W || !H) return;
      var pts = data.points || [];
      document.getElementById('fp-points').innerText = pts.length;
      var home = (data.home && data.home.lat != null) ? data.home
               : (pts.length ? { lat: pts[0][0], lon: pts[0][1] } : null);
      if (!home || !pts.length) return;

      var latR = home.lat * Math.PI / 180;
      var mx = [], my = [], maxAbs = 25;
      for (var i = 0; i < pts.length; i++) {
        var ex = (pts[i][1] - home.lon) * Math.cos(latR) * 111320;
        var ny = (pts[i][0] - home.lat) * 110540;
        mx.push(ex); my.push(ny);
        maxAbs = Math.max(maxAbs, Math.abs(ex), Math.abs(ny));
      }
      maxAbs *= 1.15;
      // A parked aircraft has a track a few metres across, so auto-fit alone
      // zoomed to a 50 m square of blank ground with the aircraft and home on
      // top of each other and nothing around them to read. Never show less
      // than MAP_MIN_SPAN_M across, and let the instructor zoom from there.
      maxAbs = Math.max(maxAbs, MAP_MIN_SPAN_M / 2);
      maxAbs /= mapZoom;
      var scale = Math.min(W, H) / (2 * maxAbs);
      var ox = W / 2, oy = H / 2;

      if (terrainImg && terrainInfo && terrainInfo.available) {
        // The backdrop is positioned in the same metres-from-home axes the
        // track uses, so it stays registered to the track at every zoom.
        var bx = ox + terrainInfo.east_min * scale;
        var by = oy - terrainInfo.north_max * scale;
        var bw = (terrainInfo.east_max - terrainInfo.east_min) * scale;
        var bh = (terrainInfo.north_max - terrainInfo.north_min) * scale;
        fctx.drawImage(terrainImg, bx, by, bw, bh);
      }

      // REVISED 11 Oct 2026: the concentric range rings went. They were
      // drawn over the satellite imagery and they are not what a ground
      // station map shows - aircraft, home and the track it has flown are.
      // Range and ceiling against their limits are read from the CAP722B
      // strip along the bottom of the console, which is always on screen,
      // so nothing was lost by taking them off the picture.
      //
      // A scale bar stays, because a map with no scale cannot be read.
      // Under the legend at the top left, for the same reason the legend
      // moved there: the bottom corners belong to the two small views.
      var step = niceStep(maxAbs / 2.2);
      var barPx = step * scale;
      var by2 = (H > 300) ? 96 : H - 16;
      fctx.strokeStyle = 'rgba(255,255,255,0.85)'; fctx.lineWidth = 2;
      fctx.beginPath();
      fctx.moveTo(14, by2); fctx.lineTo(14 + barPx, by2);
      fctx.moveTo(14, by2 - 5); fctx.lineTo(14, by2 + 5);
      fctx.moveTo(14 + barPx, by2 - 5); fctx.lineTo(14 + barPx, by2 + 5);
      fctx.stroke();
      fctx.fillStyle = '#ffffff';
      fctx.font = '11px -apple-system, sans-serif'; fctx.textAlign = 'left';
      fctx.shadowColor = 'rgba(0,0,0,0.85)'; fctx.shadowBlur = 3;
      fctx.fillText(fmt(step), 14, by2 + 18);
      fctx.textAlign = 'center';
      fctx.fillText('N', ox, (H > 300) ? 60 : 14);
      fctx.shadowBlur = 0;

      // Drawn twice: a dark casing under a bright line, so the track stays
      // readable over both pale playa and dark terrain.
      fctx.beginPath();
      for (var j = 0; j < pts.length; j++) {
        var X = ox + mx[j] * scale, Y = oy - my[j] * scale;
        if (j) fctx.lineTo(X, Y); else fctx.moveTo(X, Y);
      }
      fctx.strokeStyle = 'rgba(0,0,0,0.65)'; fctx.lineWidth = 5.5; fctx.stroke();
      fctx.strokeStyle = '#ffffff'; fctx.lineWidth = 2.5; fctx.stroke();

      var last = pts.length - 1;
      var hx = ox + mx[last] * scale, hy = oy - my[last] * scale;

      // The leg from home to the aircraft, so the two are read as a pair
      // rather than as two unrelated marks on an empty field.
      var apart = Math.hypot(hx - ox, hy - oy);
      if (apart > 18) {
        fctx.save();
        fctx.setLineDash([7, 6]);
        fctx.strokeStyle = 'rgba(255,255,255,0.5)'; fctx.lineWidth = 1.5;
        fctx.beginPath(); fctx.moveTo(ox, oy); fctx.lineTo(hx, hy); fctx.stroke();
        fctx.restore();
      }

      // Home: a ringed marker, labelled. Drawn larger than it was - at the
      // old 6px radius it disappeared into a 1600px picture.
      fctx.strokeStyle = 'rgba(0,0,0,0.75)'; fctx.lineWidth = 5;
      fctx.beginPath(); fctx.arc(ox, oy, 10, 0, 7); fctx.stroke();
      fctx.strokeStyle = '#4ade80'; fctx.lineWidth = 2.5;
      fctx.beginPath(); fctx.arc(ox, oy, 10, 0, 7); fctx.stroke();
      fctx.beginPath(); fctx.moveTo(ox - 14, oy); fctx.lineTo(ox + 14, oy);
      fctx.moveTo(ox, oy - 14); fctx.lineTo(ox, oy + 14); fctx.stroke();
      fctx.fillStyle = '#4ade80';
      fctx.beginPath(); fctx.arc(ox, oy, 3.5, 0, 7); fctx.fill();
      fctx.font = '700 11px -apple-system, sans-serif'; fctx.textAlign = 'left';
      fctx.lineJoin = 'round';
      fctx.strokeStyle = 'rgba(0,0,0,0.85)'; fctx.lineWidth = 3.5;
      fctx.strokeText('HOME', ox + 17, oy + 4);
      fctx.fillText('HOME', ox + 17, oy + 4);

      // The aircraft, pointing where it is heading, at twice its old size.
      var hdg = (telem.heading_deg || 0) * Math.PI / 180;
      fctx.save(); fctx.translate(hx, hy); fctx.rotate(hdg);
      fctx.beginPath();
      fctx.moveTo(0, -19); fctx.lineTo(13, 15); fctx.lineTo(0, 7); fctx.lineTo(-13, 15);
      fctx.closePath();
      fctx.strokeStyle = 'rgba(0,0,0,0.8)'; fctx.lineWidth = 4; fctx.stroke();
      fctx.fillStyle = '#ff3b30'; fctx.fill();
      fctx.restore();

      var dist = Math.sqrt(mx[last] * mx[last] + my[last] * my[last]);
      document.getElementById('fp-range').innerText = fmt(maxAbs * 2);
      document.getElementById('fp-dist').innerText = fmt(dist);
      document.getElementById('fp-alt').innerText = pts[last][2].toFixed(0) + ' m';
    }).catch(function () {});
  }

  // ---------- CAP722B 5.3(c): operational-limit warning banner ----------
  var banner = document.getElementById('limit-banner');
  function refreshLimits() {
    fetch('/limit_status').then(function (r) { return r.json(); }).then(function (d) {
      if (!d || d.level === 'ok' || !d.items || !d.items.length) {
        banner.style.display = 'none';
        banner.className = 'limit-banner';
        return;
      }
      var tag = d.level === 'breach' ? 'LIMIT EXCEEDED' : 'APPROACHING LIMIT';
      banner.className = 'limit-banner ' + d.level;
      banner.innerHTML = '<span class="tag">' + tag + '</span>' +
        d.items.map(function (t) { return '<span>' + t + '</span>'; }).join('');
      banner.style.display = 'flex';
    }).catch(function () {});
  }

  // ---------- CAP722B 5.2(d): feed freshness readout ----------
  var healthEl = document.getElementById('t-health');
  function refreshHealth() {
    fetch('/health').then(function (r) { return r.json(); }).then(function (d) {
      if (!d) return;
      var age = d.telemetry_age_s;
      var ageTxt = (age == null) ? '--' : (age < 1 ? '<1s' : age.toFixed(0) + 's');
      var fps = (d.camera_fps != null && d.camera_fps > 0) ? d.camera_fps.toFixed(0) : '--';
      healthEl.innerText = ageTxt + ' \\u00b7 ' + fps + ' fps';
      healthEl.className = 'v' + ((age != null && age > 2) ? ' stale' : '');
    }).catch(function () {});
  }

  // The rebuilt console moves these canvases between the hero and a corner
  // tile. Their size only gets corrected on the next tick - up to a second
  // for the map - so a swap showed a 208px map stretched across the screen
  // until then. Let the page ask for an immediate resize and redraw.
  window.gcsRedraw = function () {
    if (window.gcsDrawHud) { window.gcsDrawHud(); }
    fit(fp); drawPath();
  };
  setInterval(function () { fit(fp); drawPath(); }, 1000);
  setInterval(refreshLimits, 1000);
  setInterval(refreshHealth, 1000);
  fit(fp); drawPath(); refreshLimits(); refreshHealth();
})();
</script>
"""


# ---------------------------------------------------------------------------
# Instructor-arranged layout (added 11 Oct 2026, on request: everything
# visible at once on the station screen instead of scrolling, panels movable
# and resizable, and a lock so a set layout cannot be nudged by accident
# mid-session).
#
# Locked on every page load, deliberately - an instructor opts in to editing,
# so a stray drag during a session cannot rearrange the console. The lock is
# an accident guard, not access control: anyone at the keyboard can unlock it.
# A PIN was considered and rejected as a thing to lose rather than real
# security on a local app with no accounts.
#
# Panels span whole columns of a 12-column grid rather than pixel widths, so
# a saved layout still tiles sensibly on a different screen.
# ---------------------------------------------------------------------------
LAYOUT_STYLE = """
<style>
  /* Sits at the top of the main area, not in the top bar - the top bar
     already carries the brand and nine readouts, so controls appended there
     get pushed off the edge on a narrower screen. */
  .layout-controls {
    display: flex; gap: 8px; align-items: center; margin-bottom: 12px; flex-wrap: wrap;
  }
  .layout-hint { font-size: 11px; color: #62708a; }
  .layout-btn {
    background: #182230; color: #8b9bb4; border: 1px solid #2c3a4d; border-radius: 7px;
    padding: 7px 12px; font-size: 11px; font-weight: 600; letter-spacing: 0.5px;
    cursor: pointer; font-family: inherit;
  }
  .layout-btn:hover { color: #eee; border-color: #4a90d9; }
  .layout-btn.unlocked { background: #2b3a18; color: #c6e68a; border-color: #4a6b1f; }
  #layout-reset { display: none; }
  body.layout-unlocked #layout-reset { display: inline-block; }

  /* Edit mode: panels get a grab-handle title and a resize corner. */
  body.layout-unlocked .panel { outline: 1px dashed #4a6b8a; outline-offset: 2px; }
  body.layout-unlocked .panel-title { cursor: grab; }
  body.layout-unlocked .panel-title::before { content: "\\2630  "; color: #4a90d9; }
  .panel.drag-source { opacity: 0.4; }
  .panel.drop-before { box-shadow: inset 3px 0 0 #4a90d9; }
  .panel.drop-after { box-shadow: inset -3px 0 0 #4a90d9; }

  .resize-grip {
    position: absolute; right: 2px; bottom: 2px; width: 16px; height: 16px;
    cursor: nwse-resize; display: none; border-radius: 3px;
    background: linear-gradient(135deg, transparent 50%, #4a90d9 50%);
  }
  body.layout-unlocked .resize-grip { display: block; }

  /* The plan view's canvas was a fixed 420px tall, so making its panel
     taller or shorter did nothing. Letting it fill the panel means the
     resize grip actually resizes the drawing - fit() in the script above
     re-reads the canvas size each second and redraws at the new size. */
  #panel-flightpath { display: flex; flex-direction: column; }
  #panel-flightpath .panel-title, #panel-flightpath .fp-legend { flex-shrink: 0; }
  #flightpath { flex: 1; height: auto; min-height: 300px; }

  /* The grid scrolls only if an instructor makes the panels taller than the
     screen; the default arrangement is meant to fit without it. */
  .main { overflow-y: auto; }
</style>
"""

LAYOUT_SCRIPT = """
<script>
(function () {
  var grid = document.getElementById('panel-grid');
  var main = document.querySelector('.main');
  var toolbar = document.getElementById('layout-controls');
  var lockBtn = document.getElementById('layout-lock');
  var resetBtn = document.getElementById('layout-reset');
  var fitBtn = document.getElementById('layout-fit');
  var hint = document.getElementById('layout-hint');
  if (!grid || !lockBtn) return;

  // Default spans, aimed at fitting the whole console on one screen: the two
  // picture panels take half the width each (one row), the seven button
  // panels a quarter each (two rows). Whether that fits exactly depends on
  // the station's screen - which is the point of making it adjustable.
  var DEFAULT_COLS = { 'panel-fpv': 6, 'panel-flightpath': 6 };
  var FALLBACK_COLS = 3;
  var MIN_COLS = 2, MAX_COLS = 12, MIN_H = 120;
  var status = document.getElementById('status');

  function panels() {
    return Array.prototype.filter.call(grid.children, function (el) {
      return el.classList.contains('panel');
    });
  }

  function colsOf(el) {
    return parseInt(el.dataset.cols, 10) || DEFAULT_COLS[el.id] || FALLBACK_COLS;
  }

  function setCols(el, cols) {
    cols = Math.max(MIN_COLS, Math.min(MAX_COLS, Math.round(cols)));
    el.dataset.cols = cols;
    el.style.gridColumn = 'span ' + cols;
  }

  function currentLayout() {
    return { panels: panels().map(function (el) {
      var h = parseInt(el.style.height, 10);
      return { id: el.id, cols: colsOf(el), h: isNaN(h) ? null : h };
    }) };
  }

  function save() {
    fetch('/layout', { method: 'POST', body: JSON.stringify(currentLayout()) })
      .then(function (r) { return r.text(); })
      .then(function (t) { if (status) status.innerText = t; });
  }

  function applyLayout(saved) {
    var wanted = (saved && saved.panels) || [];
    var byId = {};
    wanted.forEach(function (p) { byId[p.id] = p; });
    // Re-append in the saved order. Panels that no longer exist are ignored;
    // panels added since the layout was saved keep their place at the end.
    wanted.forEach(function (p) {
      var el = document.getElementById(p.id);
      if (el && el.parentNode === grid) grid.appendChild(el);
    });
    panels().forEach(function (el) {
      var p = byId[el.id];
      setCols(el, p ? p.cols : (DEFAULT_COLS[el.id] || FALLBACK_COLS));
      el.style.height = (p && p.h) ? p.h + 'px' : '';
    });
  }

  // ---------- fit to screen ----------
  // The default spans are a guess at the station's screen; this measures the
  // real one. Narrowing a panel shortens it too - the camera feed is a 16:9
  // stream, so half the width is half the height - which is why this shrinks
  // spans rather than forcing heights and cropping the picture.
  function spaceAvailable() {
    var used = toolbar ? toolbar.offsetHeight + 12 : 0;
    var statusH = status ? status.offsetHeight + 16 : 0;
    return main.clientHeight - used - statusH - 8;
  }

  function gridHeight() { return grid.getBoundingClientRect().height; }

  function fitToScreen(announce) {
    panels().forEach(function (el) { el.style.height = ''; });
    var guard = 0;
    while (gridHeight() > spaceAvailable() && guard++ < 60) {
      // Shrink whichever panel is currently tallest and still above the
      // minimum span. Tallest first, so the picture panels give way before
      // the button panels get squeezed into unusable columns.
      var worst = null;
      panels().forEach(function (el) {
        if (colsOf(el) <= MIN_COLS) return;
        var h = el.getBoundingClientRect().height;
        if (!worst || h > worst.h) worst = { el: el, h: h };
      });
      if (!worst) break;
      setCols(worst.el, colsOf(worst.el) - 1);
    }
    var fits = gridHeight() <= spaceAvailable();
    if (hint && announce) {
      hint.innerText = fits
        ? 'Fitted to this screen.'
        : 'Still taller than the screen - resize the camera or plan view down by hand.';
    }
    save();
    return fits;
  }

  if (fitBtn) fitBtn.addEventListener('click', function () { fitToScreen(true); });

  // Re-fit when the window changes size. Tiling the station beside the Gazebo
  // window makes it narrower, and a layout fitted to the old width then
  // scrolls - which would otherwise mean clicking Fit to screen by hand every
  // time. Only acts when the content actually overflows, so a hand-arranged
  // layout that still fits is never rearranged underneath the instructor.
  var refitTimer = null;
  window.addEventListener('resize', function () {
    clearTimeout(refitTimer);
    refitTimer = setTimeout(function () {
      if (gridHeight() > spaceAvailable()) fitToScreen(false);
    }, 400);
  });

  // ---------- move: drag a panel by its title ----------
  var dragging = null;

  function clearMarks() {
    panels().forEach(function (el) {
      el.classList.remove('drop-before', 'drop-after');
    });
  }

  function wireMove(el) {
    var title = el.querySelector('.panel-title');
    if (!title) return;
    title.addEventListener('dragstart', function (ev) {
      if (!document.body.classList.contains('layout-unlocked')) return;
      dragging = el;
      el.classList.add('drag-source');
      ev.dataTransfer.effectAllowed = 'move';
      // Firefox will not start a drag without some payload set.
      ev.dataTransfer.setData('text/plain', el.id);
    });
    title.addEventListener('dragend', function () {
      if (dragging) dragging.classList.remove('drag-source');
      dragging = null;
      clearMarks();
    });
    el.addEventListener('dragover', function (ev) {
      if (!dragging || el === dragging) return;
      ev.preventDefault();
      var box = el.getBoundingClientRect();
      var after = ev.clientX > box.left + box.width / 2;
      clearMarks();
      el.classList.add(after ? 'drop-after' : 'drop-before');
    });
    el.addEventListener('drop', function (ev) {
      if (!dragging || el === dragging) return;
      ev.preventDefault();
      var box = el.getBoundingClientRect();
      var after = ev.clientX > box.left + box.width / 2;
      grid.insertBefore(dragging, after ? el.nextSibling : el);
      clearMarks();
      save();
    });
  }

  // ---------- resize: drag the corner grip ----------
  function wireResize(el) {
    var grip = document.createElement('div');
    grip.className = 'resize-grip';
    grip.title = 'Drag to resize';
    el.appendChild(grip);

    grip.addEventListener('pointerdown', function (ev) {
      if (!document.body.classList.contains('layout-unlocked')) return;
      ev.preventDefault();
      grip.setPointerCapture(ev.pointerId);
      var startX = ev.clientX, startY = ev.clientY;
      var startCols = colsOf(el);
      var startH = el.getBoundingClientRect().height;
      // One column of the 12, including its share of the gap.
      var colWidth = grid.clientWidth / 12;

      function move(e) {
        setCols(el, startCols + (e.clientX - startX) / colWidth);
        el.style.height = Math.max(MIN_H, startH + (e.clientY - startY)) + 'px';
      }
      function up(e) {
        grip.releasePointerCapture(ev.pointerId);
        grip.removeEventListener('pointermove', move);
        grip.removeEventListener('pointerup', up);
        save();
      }
      grip.addEventListener('pointermove', move);
      grip.addEventListener('pointerup', up);
    });
  }

  // ---------- lock ----------
  function setUnlocked(on) {
    document.body.classList.toggle('layout-unlocked', on);
    lockBtn.classList.toggle('unlocked', on);
    lockBtn.classList.toggle('locked', !on);
    lockBtn.innerHTML = on ? '\\u270e Editing layout' : '\\u25a0 Layout locked';
    lockBtn.title = on ? 'Lock the layout so it cannot be changed by accident'
                       : 'Unlock to move and resize panels';
    panels().forEach(function (el) {
      var title = el.querySelector('.panel-title');
      if (title) title.draggable = on;
    });
    if (status) {
      status.innerText = on
        ? 'Layout unlocked - drag a panel heading to move it, drag the corner to resize. Lock when done.'
        : 'Layout locked.';
    }
  }

  lockBtn.addEventListener('click', function () {
    setUnlocked(!document.body.classList.contains('layout-unlocked'));
  });

  resetBtn.addEventListener('click', function () {
    fetch('/layout', { method: 'POST', body: JSON.stringify({ reset: true }) })
      .then(function (r) { return r.text(); })
      .then(function () { location.reload(); });
  });

  panels().forEach(function (el) { wireMove(el); wireResize(el); });

  fetch('/layout').then(function (r) { return r.json(); })
    .then(function (saved) {
      var haveSaved = saved && saved.panels && saved.panels.length;
      applyLayout(saved);
      setUnlocked(false);
      if (!haveSaved) {
        // No saved layout: fit this screen rather than leave the instructor
        // scrolling. Run again once the camera image has arrived, since an
        // unloaded image measures short and would under-shrink the rest.
        fitToScreen(false);
        setTimeout(function () { fitToScreen(false); }, 2000);
      }
    })
    .catch(function () { applyLayout(null); setUnlocked(false); });
})();
</script>
"""


class Handler(http.server.BaseHTTPRequestHandler):
    def _respond(self, text, code=200):
        self.send_response(code)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(text.encode())

    def do_GET(self):
        if self.path in ("/", "/classic"):
            self.send_response(200)
            self.send_header("Content-type", "text/html; charset=utf-8")
            self.end_headers()
            if not connection_status["connected"]:
                self.wfile.write(CONNECTING_PAGE.encode("utf-8"))
            elif self.path == "/classic":
                # The panel grid, kept while the rebuilt console earns its
                # place in a lesson. Nothing in the rebuild removed it.
                page = PAGE_TEMPLATE.format(buttons=render_buttons())
                page = page.replace("<!--EXTRA_PANELS-->", EXTRA_PANELS)
                page = page.replace("</body>", EXTRA_STYLE + EXTRA_SCRIPT
                                    + _limits_script()
                                    + flight_display.STYLE + flight_display.script()
                                    + LAYOUT_STYLE + LAYOUT_SCRIPT + "</body>")
                self.wfile.write(page.encode("utf-8"))
            else:
                self.wfile.write(render_console().encode("utf-8"))
        elif self.path == "/connection_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(connection_status).encode("utf-8"))
        elif self.path == "/telemetry":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            # NaN / inf are not valid JSON and make JSON.parse() throw in
            # the browser, taking the whole telemetry panel down with them.
            safe = {k: (None if isinstance(v, float) and not math.isfinite(v) else v)
                    for k, v in telemetry.items()}
            # Home, and the cameras' own fields of view, so the gauge can
            # draw the home point where the camera would actually see it.
            safe["home_lat"] = home_latlon.get("lat")
            safe["home_lon"] = home_latlon.get("lon")
            safe["camera_fov"] = {name: feed.fov_rad()
                                  for name, feed in video_feed.FEEDS.items()}
            self.wfile.write(json.dumps(safe).encode("utf-8"))
        elif self.path == "/failure_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(failure_status()).encode("utf-8"))
        elif self.path == "/limit_status":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(limit_status()).encode("utf-8"))
        elif self.path == "/terrain_info":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(terrain_backdrop.info()).encode("utf-8"))
        elif self.path == "/terrain.png":
            data = terrain_backdrop.png()
            if data is None:
                self.send_response(404)
                self.end_headers()
                return
            self.send_response(200)
            self.send_header("Content-type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            # The terrain does not change while the sim runs, and the image is
            # ~400 KB - let the browser keep it rather than refetch on reload.
            self.send_header("Cache-Control", "max-age=3600")
            self.end_headers()
            self.wfile.write(data)
        elif self.path == "/layout":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(read_layout()).encode("utf-8"))
        elif self.path == "/health":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps(health_status()).encode("utf-8"))
        elif self.path == "/flight_path":
            self.send_response(200)
            self.send_header("Content-type", "application/json; charset=utf-8")
            self.end_headers()
            payload = {
                "home": home_latlon,
                "points": [[round(p[0], 7), round(p[1], 7), p[2]] for p in flight_path],
            }
            self.wfile.write(json.dumps(payload).encode("utf-8"))
        elif self.path in ("/video_feed", "/chase_feed"):
            feed = FEEDS["nose" if self.path == "/video_feed" else "chase"]
            self.send_response(200)
            self.send_header("Content-type", "multipart/x-mixed-replace; boundary=frame")
            self.end_headers()
            try:
                for chunk in feed.mjpeg_generator():
                    self.wfile.write(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
        elif self.path.startswith("/action/"):
            parsed = urlparse(self.path)
            action_id = parsed.path.split("/action/")[1]
            plugin = plugins_by_id.get(action_id)
            if plugin is None:
                self._respond("Unknown action.", 404)
                return
            # Any query parameters (from a plugin's "inputs" boxes) are
            # passed straight through to the handler as keyword arguments,
            # e.g. /action/loiter?radius_m=200 -> loiter(radius_m="200").
            kwargs = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
            try:
                result = plugin["handler"](**kwargs)
                self._respond(result)
            except Exception as e:
                self._respond(f"Error: {e}", 500)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path not in ("/layout", "/console_layout"):
            self.send_response(404)
            self.end_headers()
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
            data = json.loads(self.rfile.read(length) or "{}")
        except (TypeError, ValueError):
            self._respond("Layout not saved - request was not valid JSON.", 400)
            return
        if not isinstance(data, dict):
            self._respond("Layout not saved - unexpected request.", 400)
            return
        if self.path == "/console_layout":
            self._respond(write_console_layout(data))
            return
        self._respond(clear_layout() if data.get("reset") else write_layout(data))

    def log_message(self, format, *args):
        pass


class ThreadedServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True


def run_server():
    try:
        server = ThreadedServer(("", PORT), Handler)
    except OSError as exc:
        if exc.errno != errno.EADDRINUSE:
            raise
        # Another station already holds the port. Until 11 Oct 2026 this threw
        # inside the server thread while the main process carried on printing
        # "Connected." - so the browser kept talking to the OLD station, with
        # the old code and the old world, and its buttons appeared to
        # misbehave for no visible reason. Twice. Say so plainly and stop.
        print(f"\nPort {PORT} is already in use - another instructor station is"
              f" running.\nThe browser would keep talking to that one, not this."
              f"\n\nStop it and start again:\n"
              f"    pkill -f instructor_station.py; sleep 2; python3 instructor_station.py\n")
        os._exit(1)
    with server as httpd:
        httpd.serve_forever()


if __name__ == "__main__":
    print(f"Loaded {len(plugins)} controls across {len([c for c in categories.values() if c])} categories.")
    threading.Thread(target=run_server, daemon=True).start()
    print(f"UAV Academy GCS Pro running - open a browser to: http://localhost:{PORT}")

    # The instructor window is just a convenience wrapper around the local
    # web server - it is NOT the station itself. Closing it (or a WebKit
    # backend crash, or pywebview not being installed) must not take the
    # server down with it, or the instructor silently loses live telemetry,
    # the camera feed and - most importantly - event logging mid-session.
    # Added 3 Sep 2026 after the window disappearing was repeatedly
    # mistaken for the whole station crashing. Whatever happens to the
    # window, we fall through to the keep-alive loop below and the station
    # stays reachable in a browser at http://localhost:PORT until Ctrl+C.
    try:
        import webview
    except ImportError:
        webview = None
        print("\n(pywebview not installed - running in browser mode instead.")
        print(f"Open a browser to http://localhost:{PORT} manually.)\n")

    if webview is not None:
        try:
            webview.create_window("UAV Academy GCS Pro", f"http://localhost:{PORT}",
                                   width=1000, height=850, background_color="#0b1017")
            webview.start()
        except Exception as e:
            print(f"\n(Instructor window unavailable: {e} - running in browser mode instead.)")
        print(f"\nInstructor window closed - station still running at http://localhost:{PORT}")
        print("Press Ctrl+C in this terminal to shut the station down.\n")

    import time
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down UAV Academy GCS Pro.")
        # Exit without running interpreter teardown. The Gazebo transport node
        # in video_feed is a pybind11 extension holding a background thread;
        # tearing it down from a signal handler aborts with
        # "pybind11::handle::dec_ref() PyGILState_Check() failure" and dumps
        # core, which also leaves port 8080 held so the next start fails with
        # "Address already in use". Nothing here needs flushing - the event log
        # is written on each action, not buffered - so leaving immediately is
        # clean as well as quiet.
        os._exit(0)
