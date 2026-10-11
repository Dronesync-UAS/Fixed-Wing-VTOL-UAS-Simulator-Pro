"""
Serves the aircraft's nose camera as a browser-friendly MJPEG stream,
so it can be embedded directly in the app with a plain <img> tag -
no separate video player needed, unlike the QGroundControl bridge.
"""

import io
import time
import threading
from collections import deque
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage
from PIL import Image

from sim_target import MODEL, WORLD

CAMERA_TOPIC = (f"/world/{WORLD}/model/{MODEL}"
                "/link/camera_pitch_link/sensor/fpv_camera/image")
CAM_WIDTH = 1280
CAM_HEIGHT = 960

latest_jpeg = {"data": None}
lock = threading.Lock()

# Arrival times of the last few camera frames, so the instructor station
# can show an actual frames-per-second figure for the feed (CAP722B
# 5.2(d) - a visible indication of video responsiveness).
_frame_times = deque(maxlen=30)


def camera_fps():
    """Measured frame rate of the incoming Gazebo camera feed, or 0 if no
    frames have arrived in the last ~2 seconds."""
    now = time.monotonic()
    with lock:
        times = [t for t in _frame_times if now - t < 2.0]
    if len(times) < 2:
        return 0.0
    span = times[-1] - times[0]
    return round((len(times) - 1) / span, 1) if span > 0 else 0.0


def _on_image(msg: GzImage):
    img = Image.frombytes("RGB", (CAM_WIDTH, CAM_HEIGHT), msg.data)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    with lock:
        latest_jpeg["data"] = buf.getvalue()
        _frame_times.append(time.monotonic())


def start_video_capture():
    node = Node()
    node.subscribe(GzImage, CAMERA_TOPIC, _on_image)
    return node  # keep a reference alive


def mjpeg_generator():
    """Yields multipart JPEG frames for an HTTP MJPEG stream."""
    while True:
        with lock:
            frame = latest_jpeg["data"]
        if frame is not None:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.1)  # ~10 fps, kept light for a smooth embedded view
