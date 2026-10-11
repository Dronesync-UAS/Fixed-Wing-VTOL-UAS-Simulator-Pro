"""Collects the PX4 state needed to diagnose the attitude and EKF problems:

    python3 tools/px4_health_report.py

Run it with the simulator running. It connects over MAVLink alongside the
station (on a different port, so both can run), reads the parameters that
govern the estimator and the simulated sensors, listens for a while to capture
PX4's own warnings and the live estimator status, and writes a report to
~/uas_sim_logs/px4_health_report.txt.

Why this exists. Three separate theories about the VTOL attitude problem were
each disproved by one measurement that could have been taken first. This
gathers the measurements up front so the next attempt starts from data.

It reads only - no parameter is written and no command is sent.

PORTS: the station holds udpin:localhost:14540. PX4's 4004 airframe also
streams to 14550 (QGroundControl's port) and 14580, so this uses 14550 by
default. If QGroundControl is running it will already have that port; close it
first, or pass another port as the first argument.
"""
import os
import sys
import time
from collections import defaultdict

try:
    from pymavlink import mavutil
except ImportError:
    print("pymavlink is not installed - run this on the simulator machine.")
    sys.exit(1)

REPORT = os.path.expanduser("~/uas_sim_logs/px4_health_report.txt")
LISTEN_SECONDS = 25

# Parameters that decide how the estimator behaves and where its sensor data
# comes from. The SENS_EN_*SIM group matters most: on this PX4 version the
# simulated magnetometer, GPS and airspeed are generated inside PX4 itself,
# not read from Gazebo.
WANTED_PREFIXES = (
    "EKF2_MAG", "EKF2_GPS", "EKF2_HGT", "EKF2_AID", "EKF2_DECL", "EKF2_REQ",
    "SENS_EN_", "SIM_GZ_EN", "COM_ARM", "COM_PREARM", "FD_", "CA_AIRFRAME",
    "VT_", "MPC_", "MC_",
)


def main():
    port = sys.argv[1] if len(sys.argv) > 1 else "14550"
    print(f"Connecting on udpin:localhost:{port} ...")
    link = mavutil.mavlink_connection(f"udpin:localhost:{port}")
    if not link.wait_heartbeat(timeout=20):
        print("No heartbeat. Is the simulator running, and is this port free?")
        print("The station holds 14540; QGroundControl usually holds 14550.")
        return 1
    print(f"Connected to system {link.target_system}. Listening {LISTEN_SECONDS}s ...")

    link.mav.param_request_list_send(link.target_system, link.target_component)

    params, texts = {}, []
    status = defaultdict(list)
    deadline = time.time() + LISTEN_SECONDS
    while time.time() < deadline:
        msg = link.recv_match(blocking=True, timeout=1)
        if msg is None:
            continue
        kind = msg.get_type()
        if kind == "PARAM_VALUE":
            params[msg.param_id] = msg.param_value
        elif kind == "STATUSTEXT":
            line = msg.text.strip()
            if line not in texts:
                texts.append(line)
        elif kind == "ESTIMATOR_STATUS_FLAGS":
            status["flags"].append(msg)
        elif kind == "EKF_STATUS_REPORT":
            status["ekf"].append(
                f"vel={msg.velocity_variance:.3f} pos={msg.pos_horiz_variance:.3f} "
                f"hgt={msg.pos_vert_variance:.3f} mag={msg.compass_variance:.3f} "
                f"terrain={msg.terrain_alt_variance:.3f} flags=0x{msg.flags:x}")
        elif kind == "VIBRATION":
            status["vibe"].append(f"{msg.vibration_x:.2f} {msg.vibration_y:.2f} {msg.vibration_z:.2f}")
        elif kind == "GPS_RAW_INT":
            status["gps"].append(
                f"fix={msg.fix_type} sats={msg.satellites_visible} "
                f"eph={msg.eph} epv={msg.epv} alt={msg.alt/1000.0:.1f}")
        elif kind == "ATTITUDE":
            status["att"].append(f"{msg.roll:+.3f} {msg.pitch:+.3f} {msg.yaw:+.3f}")

    lines = [f"PX4 health report - {time.strftime('%Y-%m-%d %H:%M:%S')}",
             f"port udpin:localhost:{port}, system {link.target_system}",
             "", "=== PX4 messages seen while listening ===" ]
    lines += [f"  {t}" for t in texts] or ["  (none)"]

    lines += ["", "=== Parameters ==="]
    if not params:
        lines.append("  (none received - PX4 may not have answered the parameter request)")
    for name in sorted(params):
        if name.startswith(WANTED_PREFIXES):
            lines.append(f"  {name:22} {params[name]:g}")
    lines.append(f"  ({len(params)} parameters received in total)")

    for key, title in (("ekf", "EKF status (last few)"), ("gps", "GPS (last few)"),
                       ("vibe", "Vibration (last few)"), ("att", "Attitude rad (last few)")):
        if status[key]:
            lines += ["", f"=== {title} ==="] + [f"  {v}" for v in status[key][-5:]]

    text = "\n".join(lines)
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as handle:
        handle.write(text + "\n")
    print("\n" + text)
    print(f"\n[saved to {REPORT}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
