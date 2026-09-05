from simulator_link import set_mode, log_instructor_action

PX4_MAIN_MODE_POSCTL = 3  # px4_custom_mode.h

# FIXED 3 Sep 2026: was sending (3 << 16) as param2 of MAV_CMD_DO_SET_MODE,
# truncated to 0 by PX4 and ignored. Now uses simulator_link.set_mode().


def mode_position():
    result = set_mode(PX4_MAIN_MODE_POSCTL, name="Position mode")
    log_instructor_action("mode_change", f"mode=position instructor_override=true result={result}")
    return result


PLUGIN = {"id": "mode_position", "label": "Position", "category": "Flight Mode", "style": "normal", "handler": mode_position}
