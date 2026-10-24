"""Shared constants, defaults and input sanitising.

DEFAULTS is the single source of truth for every setting: the UI builds
its controls from it and Reset Settings reads it back, so the two can
never disagree.
"""

import math

TOOL_NAME = "Cable Tool"
VERSION = "0.4.0"

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
SWEEP_INTERP_DISTANCE = 3  # Precision, Start to End, EP to EP, Distance

# A draped waypoint rests on the surface point closest to a probe this
# far above the waypoint's pivot: the top of the object.
DRAPE_PROBE_HEIGHT = 1000.0

# Spline tangent at a mesh end, per unit of span length (a plain
# Catmull-Rom point gets about 1). Below ~0.5 the cable bends tighter
# than a real cable can right off the surface; above ~1 it overshoots.
EXIT_TANGENT = 0.6

# Extra spline tangent at a mesh end per unit of Lead-out Length. A Hermite
# curve stays close to its tangent line for about a third of the tangent
# length, so 3 makes the cable hold its exit direction for roughly the
# lead-out length longer before it turns and hangs.
LEAD_TANGENT = 3.0


# Sweep Mesh measures Twist in whole turns (1 = 360 degrees); the tool
# shows degrees, so the network divides by this.
DEGREES_PER_TURN = 360.0

# Each setting: default, slider range (comfortable), field range (hard
# cap), its type (float, int or bool), and whether changing it needs the
# network rebuilt (the tool then rebuilds automatically).
DEFAULTS = {
    "radius":  {"default": 0.1, "slider": (0.01, 1.0), "field": (0.001, 50.0),
                "type": "float", "rebuild": False, "label": "Radius",
                "tip": "Tube radius in scene units."},
    "sides":   {"default": 12, "slider": (3, 32), "field": (3, 64),
                "type": "int", "rebuild": False, "label": "Profile Sides",
                "tip": "Number of sides around the tube."},
    "lengthDetail": {"default": 2.0, "slider": (0.5, 6.0),
                     "field": (0.1, 20.0), "type": "float",
                     "rebuild": False, "label": "Length Detail",
                     "tip": "Rings along the tube per tube diameter. Higher "
                            "is smoother in bends, and heavier."},
    "twist":   {"default": 0.0, "slider": (-360.0, 360.0),
                "field": (-3600.0, 3600.0), "type": "float",
                "rebuild": False, "label": "Twist",
                "tip": "Degrees the profile rotates from start to end. "
                       "360 = one full turn."},
    "taper":   {"default": 1.0, "slider": (0.0, 2.0), "field": (0.0, 10.0),
                "type": "float", "rebuild": False, "label": "Taper",
                "tip": "End radius as a multiple of the start radius."},
    "sag":     {"default": 0.15, "slider": (0.0, 1.0), "field": (0.0, 3.0),
                "type": "float", "rebuild": False, "label": "Sag",
                "tip": "Slack: how far each span would droop, as a "
                       "fraction of its horizontal length. 0 = taut; a "
                       "vertical run hangs straight."},
    "smoothing": {"default": 1.0, "slider": (0.0, 1.0), "field": (0.0, 1.0),
                  "type": "float", "rebuild": False,
                  "label": "Corner Smoothing",
                  "tip": "How smoothly the cable turns at waypoints. 0 = "
                         "straight runs with tight corners, 1 = a smooth "
                         "curve through every waypoint."},
    "samples": {"default": 6, "slider": (2, 16), "field": (2, 32),
                "type": "int", "rebuild": False, "label": "Smoothness",
                "tip": "How finely the cable is simulated: points per "
                       "span, in threes. Higher follows contact and bends "
                       "more closely, and is slower."},
    "stiffness": {"default": 0.3, "slider": (0.0, 1.0), "field": (0.0, 1.0),
                  "type": "float", "rebuild": False, "label": "Stiffness",
                  "tip": "How much the cable resists bending. 0 = a limp "
                         "rope, 1 = a stiff hose that bends in wide "
                         "curves."},
    "drape":   {"default": 1, "slider": (0, 1), "field": (0, 1),
                "type": "bool", "rebuild": False,
                "label": "Drape Over Mesh Waypoints",
                "tip": "When a waypoint is a mesh, the cable rests on top "
                       "of it like a cable over a support, instead of "
                       "running through its middle. Locators are always "
                       "passed through."},
    "wireCount": {"default": 1, "slider": (1, 24), "field": (1, 64),
                  "type": "int", "rebuild": True, "label": "Wire Count",
                  "tip": "How many wires run along the route. Each is "
                         "simulated on its own. Changing it rebuilds the "
                         "run (applied when you release the slider)."},
    "spread":  {"default": 0.6, "slider": (0.0, 3.0), "field": (0.0, 100.0),
                "type": "float", "rebuild": False, "label": "Spread",
                "tip": "How far apart the wires meet each anchor, in scene "
                       "units, across the direction of travel."},
    "spreadRow": {"default": 0, "slider": (0, 1), "field": (0, 1),
                  "type": "bool", "rebuild": False,
                  "label": "Spread In A Row",
                  "tip": "On: wires sit side by side and stay parallel, "
                         "like power lines on a crossarm. Off: each wire "
                         "lands at a random spot at every anchor, so they "
                         "cross and tangle."},
    "slackVariation": {"default": 0.4, "slider": (0.0, 1.0),
                       "field": (0.0, 3.0), "type": "float",
                       "rebuild": False, "label": "Slack Variation",
                       "tip": "How much each wire's sag differs from the "
                              "others. 0 = all hang alike."},
    "thicknessVariation": {"default": 0.3, "slider": (0.0, 1.0),
                           "field": (0.0, 1.0), "type": "float",
                           "rebuild": False,
                           "label": "Thickness Variation",
                           "tip": "How much each wire's radius differs "
                                  "from Radius."},
    "seed":    {"default": 1, "slider": (0, 100), "field": (0, 99999),
                "type": "int", "rebuild": False, "label": "Seed",
                "tip": "Picks a different random arrangement of the "
                       "wires."},
    "attach":  {"default": 1, "slider": (0, 1), "field": (0, 1),
                "type": "bool", "rebuild": False,
                "label": "Attach Ends to Surface",
                "tip": "When Start or End is a mesh, the cable ends on its "
                       "surface (the point facing the next anchor) instead "
                       "of at its pivot, so cables don't meet inside it."},
    "leadOut": {"default": 0.3, "slider": (0.0, 2.0), "field": (0.0, 100.0),
                "type": "float", "rebuild": False, "label": "Lead-out Length",
                "tip": "Roughly how far the cable keeps heading out of a "
                       "surface (between its normal and the next anchor) "
                       "before it turns and hangs. 0 = it hangs straight "
                       "from the attach point."},
}


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
        clean[key] = value if spec["type"] == "float" else int(round(value))
    return clean
