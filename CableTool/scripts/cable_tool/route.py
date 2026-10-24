"""Shared route core: the ordered list of anchors a curve runs through.

Every mode (cable now, fence and road later) builds on a Route, so this
module knows nothing about tubes.
"""

import maya.cmds as cmds

from cable_tool.config import CableToolError, EPSILON
from cable_tool import nodes


class Route(object):
    """Start, optional waypoints, end. Anchors are transforms (objects,
    locators, joints); vertex/face anchors arrive in week 3."""

    def __init__(self, start=None, end=None, waypoints=None):
        self.start = start
        self.end = end
        self.waypoints = list(waypoints or [])

    @property
    def anchors(self):
        return [self.start] + self.waypoints + [self.end]

    def validate(self):
        """Raise CableToolError with a fix-it message if the route can't be
        built. Returns the anchors as long names."""
        if not self.start or not self.end:
            raise CableToolError("Set both a Start and an End anchor "
                                 "(select an object, then Get Selected).")

        resolved = []
        for anchor in self.anchors:
            matches = cmds.ls(anchor, long=True, type="transform")
            if not matches:
                raise CableToolError(
                    "'{0}' is not an object or locator in the scene. Pick "
                    "it again with Get Selected.".format(anchor))
            if len(matches) > 1:
                raise CableToolError(
                    "'{0}' matches more than one object; rename one so the "
                    "name is unique.".format(anchor))
            resolved.append(matches[0])

        for a, b in zip(resolved, resolved[1:]):
            if a == b:
                raise CableToolError(
                    "'{0}' is used twice in a row; a span needs two "
                    "different anchors.".format(short_name(a)))
        return resolved

    def overlapping_spans(self):
        """Spans whose anchors currently sit on the same spot. Allowed (the
        rig stays live and they may move apart), but worth a warning."""
        positions = [world_position(a) for a in self.validate()]
        return sum(1 for p, q in zip(positions, positions[1:])
                   if distance(p, q) < EPSILON)


def short_name(node):
    return node.split("|")[-1]


def world_position(node):
    return tuple(cmds.xform(node, query=True, worldSpace=True,
                            translation=True))


def distance(p, q):
    return sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5


def selected_transforms():
    """The selection in the order it was clicked, transforms only.
    Returns (anchors, ignored)."""
    if not cmds.selectPref(query=True, trackSelectionOrder=True):
        cmds.selectPref(trackSelectionOrder=True)
    selection = cmds.ls(orderedSelection=True, long=True) or []
    anchors, ignored = [], []
    for item in selection:
        if "." in item:
            # Components (vertices, faces) are supported from week 3.
            ignored.append(item)
        elif cmds.objectType(item, isAType="transform"):
            anchors.append(item)
        else:
            parents = cmds.listRelatives(item, parent=True, fullPath=True)
            if parents:
                anchors.append(parents[0])
            else:
                ignored.append(item)
    return anchors, ignored


def anchor_driver(anchor, name, cable_id):
    """A decomposeMatrix reading the anchor's world matrix. Its
    outputTranslate follows the anchor live, with no constraint."""
    driver = nodes.create("decomposeMatrix", name, cable_id)
    cmds.connectAttr(anchor + ".worldMatrix[0]", driver + ".inputMatrix")
    return driver + ".outputTranslate"


def mesh_shape(anchor):
    """The anchor's own visible mesh shape, or None for locators, joints,
    groups and other non-mesh anchors."""
    for shape in cmds.listRelatives(anchor, shapes=True, fullPath=True,
                                    noIntermediate=True) or []:
        if cmds.objectType(shape) == "mesh":
            return shape
    return None
