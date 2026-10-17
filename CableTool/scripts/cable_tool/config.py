"""Shared constants, defaults and input sanitising.

DEFAULTS is the single source of truth for every setting: the UI builds
its controls from it and Reset Settings reads it back, so the two can
never disagree.
"""

import math

TOOL_NAME = "Cable Tool"
VERSION = "0.2.0"

# Attribute added to every node the tool creates. Its value is the UUID
# of the cable's group, so cleanup finds nodes by tag, never by name.
TAG_ATTR = "cableToolId"
MODE_ATTR = "cableToolMode"
ROOT_GROUP = "CableTool_GRP"

# Catenary tension: higher is more rope-like, lower is more parabolic.
CATENARY_TENSION = 2.2
EPSILON = 1e-6

# sweepMeshCreator enum indices. Indices, not names, because enum names
# are localised (they come back translated in non-English Maya).
SWEEP_PROFILE_POLY = 0


# Each setting: default, slider range (comfortable), field range (hard
# cap), whether it is an int, and whether it updates live or needs a
# rebuild.
DEFAULTS = {
    "radius":  {"default": 0.1, "slider": (0.01, 1.0), "field": (0.001, 50.0),
                "int": False, "live": True, "label": "Radius",
                "tip": "Tube radius in scene units."},
    "sides":   {"default": 8, "slider": (3, 32), "field": (3, 64),
                "int": True, "live": True, "label": "Profile Sides",
                "tip": "Number of sides around the tube."},
    "twist":   {"default": 0.0, "slider": (-360.0, 360.0),
                "field": (-3600.0, 3600.0), "int": False, "live": True,
                "label": "Twist", "tip": "Degrees the profile rotates from "
                                         "start to end."},
    "taper":   {"default": 1.0, "slider": (0.0, 2.0), "field": (0.0, 10.0),
                "int": False, "live": True, "label": "Taper",
                "tip": "End radius as a multiple of the start radius."},
    "sag":     {"default": 0.15, "slider": (0.0, 1.0), "field": (0.0, 3.0),
                "int": False, "live": True, "label": "Sag",
                "tip": "Droop of each span as a fraction of its length. "
                       "0 = taut."},
    "samples": {"default": 6, "slider": (2, 16), "field": (2, 32),
                "int": True, "live": False, "label": "Smoothness",
                "tip": "Curve points per span. Applies on Generate."},
}

# Order the settings appear in the UI and on the cable group.
SETTING_ORDER = ("radius", "sides", "twist", "taper", "sag", "samples")


class CableToolError(Exception):
    """A condition the tool refuses to build. Always caught by the UI and
    shown in the status box."""


def default_settings():
    return {key: spec["default"] for key, spec in DEFAULTS.items()}


def clamp(value, low, high):
    """Force a UI value into range. None, text, NaN and infinity fall back
    to the lower bound instead of raising."""
    try:
        value = float(value)
    except (TypeError, ValueError):
        return low
    if math.isnan(value) or math.isinf(value):
        return low
    return max(low, min(high, value))


def sanitize_settings(settings):
    """Return a complete, clamped copy of settings."""
    clean = default_settings()
    for key, spec in DEFAULTS.items():
        if key not in settings:
            continue
        low, high = spec["field"]
        value = clamp(settings[key], low, high)
        clean[key] = int(round(value)) if spec["int"] else value
    return clean
