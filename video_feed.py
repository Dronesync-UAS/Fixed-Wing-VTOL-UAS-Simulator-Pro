"""
Serves the aircraft's nose camera as a browser-friendly MJPEG stream,
so it can be embedded directly in the app with a plain <img> tag -
no separate video player needed, unlike the QGroundControl bridge.
"""

import io
import threading
from gz.transport13 import Node
from gz.msgs10.image_pb2 import Image as GzImage
from PIL import Image

CAMERA_TOPIC = "/world/training_area/model/standard_vtol_0/link/camera_pitch_link/sensor/fpv_camera/image"
CAM_WIDTH = 1280
CAM_HEIGHT = 960

latest_jpeg = {"data": None}
lock = threading.Lock()


def _on_image(msg: GzImage):
    img = Image.frombytes("RGB", (CAM_WIDTH, CAM_HEIGHT), msg.data)
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=70)
    with lock:
        latest_jpeg["data"] = buf.getvalue()


def start_video_capture():
    node = Node()
    node.subscribe(GzImage, CAMERA_TOPIC, _on_image)
    return node  # keep a reference alive


def mjpeg_generator():
    """Yields multipart JPEG frames for an HTTP MJPEG stream."""
    import time
    while True:
        with lock:
            frame = latest_jpeg["data"]
        if frame is not None:
            yield (b"--frame\r\n"
                   b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n")
        time.sleep(0.1)  # ~10 fps, kept light for a smooth embedded view
