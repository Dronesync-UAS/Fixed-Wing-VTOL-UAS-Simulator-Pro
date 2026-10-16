"""
Photographs and video from the payload camera, written to disk.

Added 12 Oct 2026 with the payload screen.

WHERE THINGS GO
---------------
    ~/uas_sim_logs/payload/
        photo_20261012_143201.jpg      the picture as the operator saw it
        photo_20261012_143201.json     where the aircraft and gimbal were
        rec_20261012_143310/           one folder per recording
            frame_000001.jpg ...
            recording.json             the same facts, for the whole run
            recording.mp4              only if ffmpeg was available

WHY FRAMES ON DISK AND NOT STRAIGHT TO MP4
-------------------------------------------
Writing an MP4 needs an encoder. OpenCV and imageio both can, and neither
is a dependency of this project; ffmpeg usually is on a machine that runs
Gazebo, but "usually" is not something to build a recording button on. So
every frame is written as the JPEG it already is - no re-encoding, no
dependency, and nothing can be lost by an encoder that turns out not to
be installed. When the recording stops, ffmpeg is tried; if it is there
the MP4 appears beside the frames, and if it is not, the frames are still
there and the console says exactly what to run.

That also means a recording survives the station being killed mid-flight,
which a half-written MP4 would not.

THE SIDECAR JSON IS THE POINT, NOT AN EXTRA. A picture with no position,
no time and no gimbal angles is a holiday snap. With them it is evidence,
and it is what makes a debrief possible: the instructor can say where the
aircraft was when the student took it.
"""
import json
import os
import shutil
import subprocess
import threading
import time
from datetime import datetime

MEDIA_DIR = os.path.expanduser("~/uas_sim_logs/payload")

# Recording at the feed's own rate would fill a disk during a long
# exercise. 8 frames a second is enough to review a manoeuvre and is a
# third of the data.
RECORD_FPS = 8.0


def _stamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def _ensure_dir(path):
    os.makedirs(path, exist_ok=True)
    return path


def save_photo(jpeg, meta):
    """Write one frame and its sidecar. Returns a short report."""
    if not jpeg:
        return "No picture to save - the payload camera has sent no frames."
    try:
        _ensure_dir(MEDIA_DIR)
        name = "photo_%s" % _stamp()
        path = os.path.join(MEDIA_DIR, name + ".jpg")
        with open(path, "wb") as handle:
            handle.write(jpeg)
        with open(os.path.join(MEDIA_DIR, name + ".json"), "w") as handle:
            json.dump(meta, handle, indent=2, sort_keys=True)
        return "Photo saved: %s" % path
    except OSError as exc:
        return "Photo not saved - %s" % exc.strerror


class Recording:
    """One run of the record button."""

    def __init__(self):
        self._lock = threading.Lock()
        self.folder = None
        self.frames = 0
        self.started_at = None
        self._last_frame_at = 0.0
        self.meta = {}

    def running(self):
        return self.folder is not None

    def start(self, meta):
        with self._lock:
            if self.folder is not None:
                return "Already recording."
            try:
                folder = os.path.join(MEDIA_DIR, "rec_%s" % _stamp())
                _ensure_dir(folder)
            except OSError as exc:
                return "Recording not started - %s" % exc.strerror
            self.folder = folder
            self.frames = 0
            self.started_at = time.time()
            self._last_frame_at = 0.0
            self.meta = {"started": datetime.now().isoformat(timespec="seconds"),
                         "fps": RECORD_FPS, "start_state": meta}
            return "Recording to %s" % folder

    def add_frame(self, jpeg):
        """Called from the camera's own thread for every rendered frame."""
        if jpeg is None:
            return
        with self._lock:
            if self.folder is None:
                return
            now = time.monotonic()
            if now - self._last_frame_at < 1.0 / RECORD_FPS:
                return
            self._last_frame_at = now
            self.frames += 1
            path = os.path.join(self.folder, "frame_%06d.jpg" % self.frames)
        try:
            with open(path, "wb") as handle:
                handle.write(jpeg)
        except OSError:
            # A disk that filled up stops the recording rather than
            # throwing on every frame from here to the end of the flight.
            self.stop()

    def stop(self, meta=None):
        with self._lock:
            folder, frames = self.folder, self.frames
            started = self.started_at
            info = dict(self.meta)
            self.folder = None
        if folder is None:
            return "Not recording."
        info["frames"] = frames
        info["seconds"] = round(time.time() - started, 1) if started else None
        info["stop_state"] = meta
        try:
            with open(os.path.join(folder, "recording.json"), "w") as handle:
                json.dump(info, handle, indent=2, sort_keys=True)
        except OSError:
            pass
        if frames == 0:
            return ("Recording stopped with no frames - the payload camera "
                    "sent nothing. Has tools/gimbal_apply.py been run?")
        made = _try_mp4(folder)
        return "Recording stopped: %d frames in %s. %s" % (frames, folder, made)


def _try_mp4(folder):
    """Turn the frames into an MP4 if ffmpeg is here. Never raises."""
    ffmpeg = shutil.which("ffmpeg")
    target = os.path.join(folder, "recording.mp4")
    if not ffmpeg:
        return ("No MP4 - ffmpeg is not installed. To make one later: "
                "ffmpeg -framerate %g -i %s/frame_%%06d.jpg -c:v libx264 "
                "-pix_fmt yuv420p %s" % (RECORD_FPS, folder, target))
    try:
        result = subprocess.run(
            [ffmpeg, "-y", "-framerate", str(RECORD_FPS),
             "-i", os.path.join(folder, "frame_%06d.jpg"),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", target],
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180)
    except (OSError, subprocess.SubprocessError) as exc:
        return "No MP4 - ffmpeg would not run (%s). The frames are still there." % exc
    if result.returncode != 0:
        return ("No MP4 - ffmpeg failed. The frames are still there. "
                "Last line: %s"
                % (result.stderr or b"").decode("utf-8", "replace").strip().splitlines()[-1:])
    return "MP4 written: %s" % target


recording = Recording()
