#!/usr/bin/env python3
"""
Puts one of the aircraft's camera views into QGroundControl's video window.

    python3 tools/stream_to_qgc.py                 # the nose camera
    python3 tools/stream_to_qgc.py chase
    python3 tools/stream_to_qgc.py payload
    python3 tools/stream_to_qgc.py --list
    python3 tools/stream_to_qgc.py --stop

WHY IT IS NEEDED AT ALL. QGroundControl connects to this simulator on its
own MAVLink link and shows telemetry, the map and the mission without
being asked - but its video panel sits on "Waiting for Video", because
the station serves its cameras as MJPEG over HTTP and QGC does not read
MJPEG. QGC reads RTSP, or RTP over UDP. So the picture has to be
re-wrapped, and that is all this does.

WHAT IT DOES. Reads the station's own MJPEG feed, decodes it, encodes
H.264 and sends RTP to 127.0.0.1:5600 - which is the port QGC's "UDP
h.264 Video Stream" source listens on, and the default it ships with.
Nothing in the simulator changes: this is a reader of the same feed the
console uses, so the console and QGC can show the same camera at once.

IN QGROUNDCONTROL, once: Application Settings > Video, Source "UDP h.264
Video Stream", Port 5600. If its window already says "Waiting for Video"
then it is already set that way and there is nothing to do.

WHAT IT COSTS. Decoding JPEG and encoding H.264 is done on the CPU, and
this machine's graphics were already called marginal. Measured 13 Oct
2026: about 3900 UDP datagrams in ten seconds at 1280x720. Use --width to
drop it if the console's own frame rate suffers - 960 or 640 are both
perfectly readable on a projector.

NOT A RECORDING. QGC can record what it receives; this only sends. The
station's own recorder is the one that writes files.
"""

import argparse
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request

STATION = "http://127.0.0.1:8080"
# QGC's default for "UDP h.264 Video Stream". Changing it here means
# changing it in QGC's settings too.
QGC_HOST, QGC_PORT = "127.0.0.1", 5600

# The station's MJPEG endpoints, by the name an instructor would use.
VIEWS = {
    "nose": ("/video_feed", "the nose camera, looking forward"),
    "chase": ("/chase_feed", "the external view, from the boom"),
    "payload": ("/payload_feed", "the payload gimbal"),
}
DEFAULT_VIEW = "nose"

# Enough to look right on a projector without asking much of the CPU.
WIDTH, HEIGHT, BITRATE_KBPS = 1280, 720, 2500

# So --stop can find a stream started by an earlier run, or by the icon.
MARKER = "uas-stream-to-qgc"


def _running():
    out = subprocess.run(["pgrep", "-fa", MARKER], capture_output=True,
                         text=True).stdout.strip()
    return [line for line in out.splitlines() if line]


def _station_up():
    try:
        urllib.request.urlopen(STATION + "/health", timeout=2).read()
        return True
    except (urllib.error.URLError, OSError):
        return False


def pipeline(view, width, height, bitrate):
    path = VIEWS[view][0]
    return [
        "gst-launch-1.0",
        # The marker is a property nothing reads, carried only so --stop can
        # find this process among any other gstreamer on the machine.
        "-q",
        "souphttpsrc", "location=%s%s" % (STATION, path),
        "is-live=true", "user-agent=%s" % MARKER,
        "!", "multipartdemux",
        "!", "jpegdec",
        # QUEUES, PLURAL. Without one before the encoder gstreamer warns
        # that it cannot meet the sink's deadline and shortens the latency
        # to zero, which shows up as stutter rather than as an error.
        "!", "queue", "max-size-buffers=3", "leaky=downstream",
        "!", "videoconvert",
        "!", "videoscale",
        "!", "video/x-raw,width=%d,height=%d" % (width, height),
        "!", "x264enc", "tune=zerolatency", "speed-preset=ultrafast",
        "bitrate=%d" % bitrate,
        # A keyframe every second, or QGC shows nothing until the next one
        # - which is what "connected but black" usually is.
        "key-int-max=30",
        "!", "queue", "max-size-buffers=3", "leaky=downstream",
        "!", "rtph264pay", "config-interval=1", "pt=96",
        "!", "udpsink", "host=%s" % QGC_HOST, "port=%d" % QGC_PORT,
        "sync=false",
    ]


def main(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("view", nargs="?", default=DEFAULT_VIEW,
                        help="which camera (%s)" % ", ".join(VIEWS))
    parser.add_argument("--width", type=int, default=WIDTH)
    parser.add_argument("--height", type=int, default=HEIGHT)
    parser.add_argument("--bitrate", type=int, default=BITRATE_KBPS,
                        help="kbit/s (default %d)" % BITRATE_KBPS)
    parser.add_argument("--stop", action="store_true",
                        help="stop a stream started earlier")
    parser.add_argument("--list", action="store_true",
                        help="the views, and whether one is being sent")
    parser.add_argument("--foreground", action="store_true",
                        help="stay attached instead of running in the "
                             "background (Ctrl+C stops it)")
    args = parser.parse_args(argv)

    if args.list:
        for name, (path, what) in VIEWS.items():
            print("  %-8s %-16s %s" % (name, path, what))
        live = _running()
        print("\n%s" % ("Sending now: %d stream(s)." % len(live) if live
                        else "Nothing is being sent to QGroundControl."))
        return 0

    if args.stop:
        if not _running():
            print("Nothing was being sent.")
            return 0
        subprocess.run(["pkill", "-f", MARKER], capture_output=True)
        print("Stopped sending to QGroundControl.")
        return 0

    if args.view not in VIEWS:
        print("'%s' is not one of: %s" % (args.view, ", ".join(VIEWS)),
              file=sys.stderr)
        return 1
    if shutil.which("gst-launch-1.0") is None:
        print("gstreamer is not installed. Install it with:\n"
              "    sudo apt install gstreamer1.0-tools gstreamer1.0-plugins-good "
              "gstreamer1.0-plugins-ugly", file=sys.stderr)
        return 1
    if not _station_up():
        print("The instructor station is not answering on %s.\n"
              "Start the simulator first - the camera feeds come from it."
              % STATION, file=sys.stderr)
        return 1

    # One at a time. Two streams on one port is a picture that flickers
    # between two cameras, which looks like a fault rather than a mistake.
    if _running():
        subprocess.run(["pkill", "-f", MARKER], capture_output=True)

    command = pipeline(args.view, args.width, args.height, args.bitrate)
    print("Sending %s to QGroundControl (%s) at %dx%d."
          % (VIEWS[args.view][1], "udp://%s:%d" % (QGC_HOST, QGC_PORT),
             args.width, args.height))
    print("In QGC: Application Settings > Video > UDP h.264 Video Stream, "
          "port %d." % QGC_PORT)

    if args.foreground:
        return subprocess.call(command)

    with open(os.devnull, "w") as quiet:
        subprocess.Popen(command, stdout=quiet, stderr=quiet,
                         start_new_session=True)
    print("\nRunning in the background. Stop it with:")
    print("    python3 tools/stream_to_qgc.py --stop")
    return 0


if __name__ == "__main__":
    sys.exit(main())
