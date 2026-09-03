from simulator_link import start_background_script, log_instructor_action


def start_stabilizer():
    result = start_background_script("stabilizer", ["python3", "/home/uas-sim/PX4-Autopilot/camera_stabilizer.py"])
    log_instructor_action("start_stabilizer")
    return result


PLUGIN = {"id": "start_stabilizer", "label": "Start Camera Stabilizer", "category": "Camera", "style": "normal", "handler": start_stabilizer}
