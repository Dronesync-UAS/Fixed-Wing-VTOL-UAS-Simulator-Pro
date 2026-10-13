"""
GPS failure, injected into PX4 itself.

WHAT THIS REPLACES, AND WHY
---------------------------
This control used to start gps_dropout_proxy.py, a prototype that sits
BETWEEN PX4 and QGroundControl and rewrites the GPS fields in the stream
going to QGC. Tested end to end on 14 Oct 2026 with the simulator running,
and it does not work in this setup:

  * it only ever fooled QGroundControl. The instructor station reads PX4
    on its own MAVLink link, so the station's satellite count never moved
    - and neither did PX4's own navigation, which is the thing a student
    is supposed to be learning to handle;
  * it needs PX4 told to send telemetry to the proxy and QGC told to
    connect to the proxy's port instead of to PX4. Neither is done by the
    launcher, so the proxy sat in the middle of nothing;
  * it takes its commands by TYPING "fail" at a prompt. Started as a
    background script it has no stdin, so its command thread died with
    EOFError at once - the measured log line was

        File ".../gps_dropout_proxy.py", line 46, in command_listener
            cmd = input().strip().lower()
        EOFError: EOF when reading a line

    while the station reported "GPS failure injected."

So the button said it had injected a failure, and nothing had happened.
For a training device that is worse than having no button.

WHAT IT DOES NOW
----------------
Sets PX4's own SIM_GPS_USED parameter to 0, and back to 10 to clear.

src/modules/simulation/sensor_gps_sim/SensorGpsSim.cpp:

    if (_sim_gps_used.get() >= 4) {
        sensor_gps.fix_type = 3;    // 3D fix
    } else {
        sensor_gps.fix_type = 0;    // No fix
    }
    ...
    sensor_gps.satellites_used = _sim_gps_used.get();

so 0 means no fix and no satellites, inside PX4's own sensor pipeline.
The EKF loses its GPS, the aircraft behaves as it would, and EVERY ground
station sees it: this console, QGroundControl, and the aircraft's own
GPS status light, which turns red.

MEASURED on 14 Oct 2026 against the running simulator:

    SIM_GPS_USED = 10   GPS_RAW_INT  satellites 10, fix_type 3
    SIM_GPS_USED = 0    GPS_RAW_INT  satellites  0, fix_type 0
    SIM_GPS_USED = 10   GPS_RAW_INT  satellites 10, fix_type 3

WHY NOT MAV_CMD_INJECT_FAILURE, which is the obvious answer: it is
handled by simulator_mavlink, the module used with the OLD jMAVSim and
Gazebo-classic back ends. These worlds run on Gazebo Harmonic through
gz_bridge, which does not handle it. Tried first and measured: PX4 never
acknowledged the command and the satellite count did not move.

PARAMETERS RESET WHEN PX4 RESTARTS, so a NEW SESSION or a change of
training area clears the failure by itself. That is the right behaviour -
a fresh exercise should not start with a hidden failure still in - and
the state here is re-checked from the aircraft rather than remembered.
"""

import struct
import time

from simulator_link import (master, telemetry, mark_failure_injected,
                            mark_failure_cleared)

MAV_PARAM_TYPE_INT32 = 6
PARAM = b"SIM_GPS_USED"
# SensorGpsSim calls it a 3D fix at 4 or more. 10 is PX4's own default,
# which is what the aircraft comes up with.
SATELLITES_OK = 10
SATELLITES_NONE = 0

state = {"active": False}


def _as_int32(value):
    """PX4 reads PARAM_SET's float field as the raw bits of an int32."""
    return struct.unpack("<f", struct.pack("<i", int(value)))[0]


def _set(satellites):
    master.mav.param_set_send(master.target_system, master.target_component,
                              PARAM, _as_int32(satellites), MAV_PARAM_TYPE_INT32)


def toggle_gps_failure():
    want_off = not state["active"]
    _set(SATELLITES_NONE if want_off else SATELLITES_OK)

    # SAY WHAT THE AIRCRAFT ACTUALLY DID, not what was sent. A PARAM_SET is
    # not acknowledged, so the honest check is the satellite count coming
    # back in the telemetry - which is the same number the console and
    # QGroundControl show.
    deadline = time.monotonic() + 4.0
    while time.monotonic() < deadline:
        sats = telemetry.get("satellites")
        if sats is not None:
            if want_off and sats == 0:
                state["active"] = True
                mark_failure_injected("gps")
                return ("GPS failure injected - the aircraft reports 0 "
                        "satellites and no fix. The tail light is red, and "
                        "QGroundControl sees the loss too.")
            if not want_off and sats >= 4:
                state["active"] = False
                mark_failure_cleared("gps")
                return ("GPS failure cleared - the aircraft reports %d "
                        "satellites again." % sats)
        time.sleep(0.25)

    # It may still take effect a moment later, so the state follows the
    # request; the console's own satellite readout is the thing to watch.
    state["active"] = want_off
    return ("GPS %s sent, but the aircraft has not reported the change yet "
            "(satellites: %s). Watch the satellite count."
            % ("failure" if want_off else "restore",
               telemetry.get("satellites")))


PLUGIN = {
    "id": "gps_failure", "label": "Toggle GPS Failure",
    "category": "Failure Injection",
    "style": "warning", "handler": toggle_gps_failure,
}
