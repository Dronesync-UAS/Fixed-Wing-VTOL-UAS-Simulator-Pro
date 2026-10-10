from simulator_link import set_mode, log_instructor_action

PX4_MAIN_MODE_MANUAL = 1  # px4_custom_mode.h

# FIXED 3 Sep 2026: was sending (1 << 16) = 65536 as param2 of
# MAV_CMD_DO_SET_MODE, which PX4 reads as an 8-bit number -> 0 -> ignored.
# Now uses simulator_link.set_mode(), which also reports PX4's answer.


def mode_manual():
    result = set_mode(PX4_MAIN_MODE_MANUAL, name="Manual mode")
    log_instructor_action("mode_change", f"mode=manual instructor_override=true result={result}")
    return result


PLUGIN = {"id": "mode_manual", "label": "Manual (reliable)", "category": "Flight Mode", "style": "highlight", "handler": mode_manual}
