"""
Serves the aircraft's cameras as browser-friendly MJPEG streams, so they can
be embedded directly in the console with a plain <img> tag - no separate
video player needed, unlike the QGroundControl bridge.

Two feeds:

  nose     the forward (FPV) view, with the attitude overlay drawn on top
  chase    behind and above the aircraft, looking forward - the view that used
           to mean switching to the Gazebo window to see the aircraft at all
  payload  the gimbal ball under the belly: steerable, zoomable, and the one
           the sensor operator works from. Added 12 Oct 2026 with gimbal.py.

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
import math
import time
import threading
from collections import deque
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage

# The camera's own field of view, read from Gazebo rather than written down
# here. The home-point marker drawn over these pictures is only in the right
# place if the angle used to project it is the angle the camera actually has,
# and that lives in the world file on the simulator's machine - not in this
# repository. Gazebo publishes it on <image topic>/camera_info.
try:
    from gz.msgs10.camera_info_pb2 import CameraInfo as GzCameraInfo
except ImportError:                                        # pragma: no cover
    GzCameraInfo = None
from PIL import Image, ImageOps

import sim_target

# How long with no frames before assuming the subscription is stale.
# A world switch re-subscribes immediately, but the simulator takes 15-30
# seconds to come up, so that subscription is made to a topic nothing is
# publishing on yet. Rather than rely on gz-transport picking it up when the
# publisher appears, check and re-subscribe.
STALE_AFTER_S = 8.0


# ---------------------------------------------------------------------
# NIGHT AND INFRARED VIEWS
#
# Added 12 Oct 2026 for night operations training.
#
# BE CLEAR ABOUT WHAT THIS IS. These are renderings of the ordinary colour
# camera, not the output of an infrared sensor. Nothing in the simulation
# knows anything about temperature: a warm body and a cold rock of the same
# brightness come out the same here, and on a real thermal camera they
# would not. Gazebo can carry a genuine thermal_camera sensor, but it only
# says anything useful once every object in the world has been given a
# temperature, and nothing in these worlds has.
#
# So this trains the HALF of night flying that is about reading a
# monochrome picture and flying from it - framing, orientation, judging
# height and closure with no colour and little contrast. It does not train
# interpreting a heat signature, and the console says so on screen rather
# than letting a student believe otherwise.
#
# WHITE HOT and BLACK HOT are the two polarities every thermal camera
# offers, and switching between them is a real habit worth building.
# NIGHT VISION is the green of an image intensifier.

def _luminance(image):
    """Perceived brightness, which is what every one of these starts from."""
    return image.convert("L")


def _white_hot(image):
    return _luminance(image).convert("RGB")


def _black_hot(image):
    return ImageOps.invert(_luminance(image)).convert("RGB")


def _night_vision(image):
    """Green, and lifted out of the shadows, like an intensifier."""
    grey = ImageOps.autocontrast(_luminance(image), cutoff=1)
    return ImageOps.colorize(grey, black=(2, 14, 4), white=(176, 255, 176)).convert("RGB")


def _crop_zoom(image, zoom):
    """Digital zoom: take the middle 1/zoom and scale it back to full size.

    BICUBIC rather than NEAREST because a payload picture at 8x should
    look soft, which is honest, rather than blocky, which looks like a
    fault in the simulator.
    """
    width, height = image.size
    keep_w = max(16, int(width / zoom))
    keep_h = max(16, int(height / zoom))
    left = (width - keep_w) // 2
    top = (height - keep_h) // 2
    return image.crop((left, top, left + keep_w, top + keep_h)).resize(
        (width, height), Image.BICUBIC)


VIEW_MODES = {
    "normal": None,
    "white_hot": _white_hot,
    "black_hot": _black_hot,
    "night_vision": _night_vision,
}


class CameraFeed:
    """One Gazebo camera, re-encoded as MJPEG for the browser."""

    def __init__(self, name, topic_source, width, height, quality=88,
                 frame_interval_s=1 / 25.0, zoomable=False):
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
        # How long each frame took to get through this station, in seconds:
        # from the Gazebo image message arriving to the JPEG being ready to
        # serve. Feeds latency_ms() - see there for what it does and does
        # not include. Added 14 Oct 2026 for CAP 722B 5.2(d).
        self._frame_latencies = deque(maxlen=30)
        # The node holding the live subscription. Held because a Node that
        # goes out of scope stops delivering.
        self._node = None
        self._topic = None
        self._watchdog_on = False
        # Horizontal field of view in radians, once Gazebo has told us.
        self._fov_rad = None
        # How the picture is rendered: see VIEW_MODES above.
        self.view_mode = "normal"
        # DIGITAL zoom, for the payload camera. gz-sim 8 has no documented
        # way to change a camera's field of view while it is running, so
        # zooming is done by cropping the middle of the frame and scaling
        # it back up - which is exactly what the digital zoom on a real
        # payload does, and is labelled as digital on screen. The frame is
        # scaled back to its original size on purpose: an MJPEG stream
        # whose frames change size makes the browser re-layout the picture
        # on every zoom step.
        self.zoomable = zoomable
        self.zoom = 1.0
        # Set to a payload_media.Recording while the record button is on.
        self.recorder = None


    # -- incoming frames ------------------------------------------------
    def _on_image(self, msg):
        started = time.monotonic()
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
        if self.zoomable and self.zoom > 1.0:
            image = _crop_zoom(image, self.zoom)
        render = VIEW_MODES.get(self.view_mode)
        if render is not None:
            try:
                image = render(image)
            except (ValueError, OSError):
                # A rendering that fails must not stop the feed: show the
                # picture as it came rather than dropping the frame.
                pass
        buffer = io.BytesIO()
        image.save(buffer, format="JPEG", quality=self.quality)
        frame = buffer.getvalue()
        finished = time.monotonic()
        with self._lock:
            self._latest = frame
            self._frame_times.append(finished)
            self._frame_latencies.append(finished - started)
        # Outside the lock: writing a file must not hold up the next frame.
        recorder = self.recorder
        if recorder is not None and recorder.running():
            recorder.add_frame(frame)

    def snapshot(self):
        """The most recent frame as JPEG bytes, or None."""
        with self._lock:
            return self._latest

    def _on_camera_info(self, msg):
        """Work the horizontal field of view out of the camera intrinsics.

        For a pinhole camera fx is the focal length in pixels, so half the
        sensor width subtends atan(width / 2fx). Gazebo fills both the
        intrinsic and the projection matrix; either will do, and a camera
        that reports neither is left alone rather than given a made-up angle.
        """
        try:
            width = msg.width
            fx = msg.intrinsics.k[0] or msg.projection.p[0]
        except (AttributeError, IndexError):
            return
        if not width or not fx:
            return
        self._fov_rad = 2.0 * math.atan(width / (2.0 * fx))

    def fov_rad(self):
        return self._fov_rad

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

    def latency_ms(self):
        """Visual response time, in milliseconds. 0 if nothing is arriving.

        CAP 722B 5.2(d) requires an FSTD to be able to display "the visual
        response time (ms) and frame rate (fps) of any display". fps() is
        the second half; this is the first.

        WHAT IT MEASURES: the whole of this station's contribution to the
        delay - decoding Gazebo's raw frame, any infrared or zoom
        rendering, and the JPEG encode - plus the frame period, because a
        picture is on average half a frame old before it is sent and a
        change can wait a whole frame to appear at all.

        WHAT IT DOES NOT MEASURE, and an instructor should know this
        before quoting the number: Gazebo's own render time before the
        frame reached us, the network hop, and the browser's decode and
        paint. So it is a floor on the true glass-to-glass figure, not the
        figure itself. Measuring the real one needs a camera pointed at
        the screen, which is how it is done for a qualified FSTD.
        """
        now = time.monotonic()
        with self._lock:
            times = [t for t in self._frame_times if now - t < 2.0]
            work = list(self._frame_latencies)
        if len(times) < 2 or not work:
            return 0.0
        span = times[-1] - times[0]
        frame_period = span / (len(times) - 1) if span > 0 else 0.0
        # The median, not the mean: one slow frame (a garbage collection,
        # a recording flush) should not be reported as the response time.
        work.sort()
        median = work[len(work) // 2]
        return round((median + frame_period) * 1000.0, 1)

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
        # A feed may have more than one place to look. The chase camera
        # does: it sits on base_link until tools/chase_angles_apply.py
        # moves it onto the boom, and a camera's topic has its link name
        # in it. Subscribing to both costs nothing - only one of them ever
        # has a publisher - and saves making that tool compulsory.
        wanted = list(topic) if isinstance(topic, (list, tuple)) else [topic]
        node = Node()
        for one in wanted:
            node.subscribe(GzImage, one, self._on_image)
            if GzCameraInfo is not None:
                # Best effort: an older gz-msgs without this type, or a
                # camera that does not publish it, simply leaves the field
                # of view unknown and the marker is not drawn.
                try:
                    node.subscribe(GzCameraInfo, one + "/camera_info",
                                   self._on_camera_info)
                except Exception:                          # noqa: BLE001
                    pass
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


# Quality 88 and 25 frames a second, both raised on 11 Oct 2026. At 70 the
# JPEG artefacts were visible on the horizon, and serving 10 frames a second
# from a camera publishing 30 threw two out of every three away for no
# saving anyone asked for - this is a loopback connection, not a radio link.
nose = CameraFeed("nose", sim_target.camera_topic, 1280, 960)
# Smaller, lower quality and slower than the nose camera on purpose: it is a
# situational view of where the aircraft is, not an instrument.
# RAISED 11 Oct 2026 from 640x360. At that size it was being stretched
# across a 1400px hero and looked it. 1600x900 matches the hero on this
# machine's screen, and at 15 Hz it is 21.6 megapixels a second against the
# nose camera's 36.9 - the cheaper of the two cameras already running. If the
# simulator slows, the <image> block in the aircraft model is where to turn
# it back down.
chase = CameraFeed("chase", sim_target.chase_camera_topics, 1600, 900,
                   frame_interval_s=1 / 15.0)

# The payload gimbal's camera. Only publishes once tools/gimbal_apply.py
# has added the gimbal, so before that it costs nothing and the panel shows
# its "no signal" message. 1024x576 at 15 Hz is 8.8 megapixels a second -
# the smallest of the three, deliberately, because it is the third camera
# this machine has been asked to render and the payload view is mostly
# watched zoomed in, where frame rate matters more than pixel count.
payload = CameraFeed("payload", sim_target.gimbal_camera_topic, 1024, 576,
                     frame_interval_s=1 / 15.0, zoomable=True)

FEEDS = {"nose": nose, "chase": chase, "payload": payload}


# --- module-level API, unchanged for existing callers -------------------

def camera_fps():
    """The nose camera's frame rate - what the console's Feeds readout shows."""
    return nose.fps()


def camera_latency_ms():
    """The nose camera's visual response time, in ms. See Feed.latency_ms."""
    return nose.latency_ms()


def current_topic():
    return nose.current_topic()


def mjpeg_generator():
    return nose.mjpeg_generator()


def start_video_capture():
    """Start every feed. Returns the nose camera's node, as before."""
    node = nose.start()
    for feed in FEEDS.values():
        if feed is not nose:
            feed.start()
    return node


def resubscribe():
    """Re-point every feed at the current world. Called on a world switch."""
    node = nose.resubscribe()
    for feed in FEEDS.values():
        if feed is not nose:
            feed.resubscribe()
    return node


def start_watchdog():
    for feed in FEEDS.values():
        feed.start()
