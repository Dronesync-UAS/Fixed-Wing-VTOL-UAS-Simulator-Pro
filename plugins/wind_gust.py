"""
Wind speed / gust control. NOT YET CONFIRMED WORKING.

Live wind control in this version of Gazebo has been flagged in this
project's own notes as unreliable based on community reports. This
needs real-world testing before being presented as a working feature,
per that earlier caution - left as a placeholder rather than risk
giving false confidence in an untested control.
"""


def not_ready():
    return "Not yet confirmed working - needs real-world testing first, see project notes."


PLUGIN = {
    "id": "wind_gust", "label": "Wind / Gust (unconfirmed)",
    "category": "Experimental - In Development", "style": "experimental", "handler": not_ready,
}
