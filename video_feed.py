"""
Serves the aircraft's cameras as browser-friendly MJPEG streams, so they can
be embedded directly in the console with a plain <img> tag - no separate
video player needed, unlike the QGroundControl bridge.

Two feeds:

  nose   the forward (FPV) view, with the attitude overlay drawn on top
  chase  behind and above the aircraft, looking forward - the view that used
         to mean switching to the Gazebo window to see the aircraft at all

REVISED 11 Oct 2026. This was a single camera's worth of module-level state:
one topic, one latest frame, one watchdog. Adding a second camera by copying
the file would have meant two watchdogs drifting apart, so the state moved
into a CameraFeed instance and the module-level functions became thin
wrappers that keep the station and the environment plugin working unchanged.

The chase feed costs a second rendered camera, on a machine whose
performance is already marginal (12 July entry). It is therefore deliberately
small and slow - 640x360 at 15 Hz against the nose camera's 1280x960 - and it
only renders at all once tools/chase_camera_apply.py has added the sensor to
the aircraft model. Before that its topic has no publisher and the panel
shows its "no signal" message, costing nothing.
"""

import io
import time
import threading
from collections import deque
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage
from PIL import Image

import sim_target

# How long with no frames before assuming the subscription is stale.
# A world switch re-subscribes immediately, but the simulator takes 15-30
# seconds to come up, so that subscription is made to a topic nothing is
# publishing on yet. Rather than rely on gz-transport picking it up when the
# publisher appears, check and re-subscribe.
STALE_AFTER_S = 8.0


class CameraFeed:
    """One Gazebo camera, re-encoded as MJPEG for the browser."""

    def __init__(self, name, topic_source, width, height, quality=70,
                 frame_interval_s=0.1):
        self.name = name
        self._topic_source = topic_source
        self.width = width
        self.height = height
        self.quality = quality
        self.frame_interval_s = frame_interval_s
        self._lock = threading.Lock()
        self._latest = None
        # Arrival times of the last few frames, so the console can show an
        # actual frames-per-second figure (CAP722B 5.2(d) - a visible
        # indication of video responsiveness).
        self._frame_times = deque(maxlen=30)
        # The node holding the live subscription. Held because a Node that
        # goes out of scope stops delivering.
        self._node = None
        self._topic = None
        self._watchdog_on = False

    # -- incoming frames ------------------------------------------------
    def _on_image(self, msg):
        # A frame whose size does not match what this feed expects would be
        # decoded as garbage by frombytes, so trust the message over the
        # configuration - the model file is edited by hand and can disagree.
        width = msg.width or self.width
        height = msg.height or self.height
        try:
            image = Image.frombytes("RGB", (width, height), msg.data)
        except ValueError:
            # Wrong-sized buffer: drop the frame rather than take down the
            # subscriber thread for every later frame too.
            return
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.quality)
        with self._lock:
            self._latest = buffer.getvalue()
            self._frame_times.append(time.monotonic())

    # -- status ----------------------------------------------------------
    def fps(self):
        """Measured frame rate, or 0 if nothing has arrived in ~2 seconds."""
        now = time.monotonic()
        with self._lock:
            times = [t for t in self._frame_times if now - t < 2.0]
        if len(times) < 2:
            return 0.0
        span = times[-1] - times[0]
        return round((len(times) - 1) / span, 1) if span > 0 else 0.0

    def current_topic(self):
        return self._topic

    # -- subscription ------------------------------------------------------
    def resubscribe(self):
        """(Re)subscribe to this camera in whichever world is current.

        Called at start-up, and again when the Environment panel switches
        world - the topic has the world name in it, so a switch leaves the
        old subscription pointed at a world that no longer exists.
        gz-transport has no unsubscribe here, so the previous node is simply
        dropped; its world is gone, so it delivers nothing.
        """
        topic = self._topic_source()
        node = Node()
        node.subscribe(GzImage, topic, self._on_image)
        self._node = node
        self._topic = topic
        with self._lock:
            self._latest = None
            self._frame_times.clear()
        return node

    def _watchdog(self):
        while True:
            time.sleep(STALE_AFTER_S / 2)
            with self._lock:
                last = self._frame_times[-1] if self._frame_times else None
                topic = self._topic
            stale = last is None or (time.monotonic() - last) > STALE_AFTER_S
            wrong = topic != self._topic_source()
            if stale or wrong:
                try:
                    self.resubscribe()
                except Exception:
                    # A camera that cannot be reconnected must not take the
                    # station down - the rest of the console works without it.
                    pass

    def start(self):
        node = self.resubscribe()
        if not self._watchdog_on:
            self._watchdog_on = True
            threading.Thread(target=self._watchdog, daemon=True).start()
        return node

    # -- output ------------------------------------------------------------
    def mjpeg_generator(self):
        """Yields multipart JPEG frames for an HTTP MJPEG stream."""
        while True:
            with self._lock:
                frame = self._latest
            if frame is not None:
                yield (b"--frame\r\n"
                       b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
            time.sleep(self.frame_interval_s)


nose = CameraFeed("nose", sim_target.camera_topic, 1280, 960)
# Smaller, lower quality and slower than the nose camera on purpose: it is a
# situational view of where the aircraft is, not an instrument.
# RAISED 11 Oct 2026 from 640x360. At that size it was being stretched
# across a 1400px hero and looked it - "chase view resolution is very poor".
# 1280x720 is the hero's own scale, and the station reported 30 fps with the
# smaller camera already running, so there is headroom. If the simulator
# slows after this, the camera's <image> block in the aircraft model is where
# to turn it back down.
chase = CameraFeed("chase", sim_target.chase_camera_topic, 1280, 720,
                   quality=72, frame_interval_s=1 / 15.0)

FEEDS = {"nose": nose, "chase": chase}


# --- module-level API, unchanged for existing callers -------------------

def camera_fps():
    """The nose camera's frame rate - what the console's Feeds readout shows."""
    return nose.fps()


def current_topic():
    return nose.current_topic()


def mjpeg_generator():
    return nose.mjpeg_generator()


def start_video_capture():
    """Start every feed. Returns the nose camera's node, as before."""
    node = nose.start()
    chase.start()
    return node


def resubscribe():
    """Re-point every feed at the current world. Called on a world switch."""
    node = nose.resubscribe()
    chase.resubscribe()
    return node


def start_watchdog():
    for feed in FEEDS.values():
        feed.start()
