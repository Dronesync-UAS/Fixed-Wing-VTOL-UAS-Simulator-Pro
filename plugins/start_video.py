from simulator_link import start_background_script, log_instructor_action


def start_video():
    result = start_background_script("video", ["python3", "/home/uas-sim/PX4-Autopilot/fpv_stream.py"])
    log_instructor_action("start_video")
    return result


PLUGIN = {"id": "start_video", "label": "Start FPV Video", "category": "Camera", "style": "normal", "handler": start_video}
