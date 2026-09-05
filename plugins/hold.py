from simulator_link import set_mode, log_instructor_action

# PX4 custom mode numbers (px4_custom_mode.h): AUTO main mode, LOITER sub.
PX4_MAIN_MODE_AUTO = 4
PX4_SUB_MODE_AUTO_LOITER = 3

# FIXED 3 Sep 2026: this button did nothing. It packed the mode as
# (4 << 16) | (3 << 24) into param2 of MAV_CMD_DO_SET_MODE - that packing
# is only correct for the separate SET_MODE *message*; for the DO_SET_MODE
# *command* PX4 reads param2/param3 as plain 8-bit numbers, so it got
# "main mode 0" and ignored it. Now goes through simulator_link.set_mode(),
# which sends the numbers correctly AND reports whether PX4 accepted it.


def hold():
    result = set_mode(PX4_MAIN_MODE_AUTO, PX4_SUB_MODE_AUTO_LOITER, name="HOLD (AUTO loiter)")
    log_instructor_action("hold", result)
    return result


PLUGIN = {"id": "hold", "label": "HOLD", "category": "Flight Ops", "style": "normal", "handler": hold}
