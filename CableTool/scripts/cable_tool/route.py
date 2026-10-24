"""Shared route core: the ordered list of anchors a curve runs through.

Every mode (cable now, fence and road later) builds on a Route, so this
module knows nothing about tubes.

An anchor is a transform (an object, locator or joint) or a single mesh
component on one: "pCube1.vtx[12]" (a vertex) or "pCube1.f[3]" (a face).
"""

import re

import maya.cmds as cmds

from cable_tool.config import CableToolError, EPSILON
from cable_tool.i18n import tr

# Component kinds the tool can anchor to, and the code the solver uses.
COMPONENT_KINDS = {"vtx": 1, "f": 2}
_COMPONENT = re.compile(r"^(?P<node>[^.]+)\.(?P<kind>vtx|f)\[(?P<index>\d+)\]$")


class Route(object):
    """Start, optional waypoints, end."""

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
            raise CableToolError(tr("Set both a Start and an End anchor "
                                    "(select an object, then Get "
                                    "Selected)."))

        resolved = [_resolve(anchor) for anchor in self.anchors]
        for a, b in zip(resolved, resolved[1:]):
            if a == b:
                raise CableToolError(tr(
                    "'{0}' is used twice in a row; a span needs two "
                    "different anchors.").format(short_name(a)))
        return resolved

    def overlapping_spans(self):
        """Spans whose anchors currently sit on the same spot. Allowed (the
        rig stays live and they may move apart), but worth a warning."""
        positions = [world_position(a) for a in self.validate()]
        return sum(1 for p, q in zip(positions, positions[1:])
                   if distance(p, q) < EPSILON)


def _resolve(anchor):
    """The anchor as a long name, or a CableToolError saying what's wrong."""
    node, kind, index = split(anchor)
    matches = cmds.ls(node, long=True, type="transform")
    if not matches:
        raise CableToolError(tr(
            "'{0}' is not an object or locator in the scene. Pick it again "
            "with Get Selected.").format(anchor))
    if len(matches) > 1:
        raise CableToolError(tr(
            "'{0}' matches more than one object; rename one so the name is "
            "unique.").format(node))
    if kind is None:
        return matches[0]
    mesh = mesh_shape(matches[0])
    if mesh is None:
        raise CableToolError((
            tr("'{0}' is a vertex anchor, but '{1}' has no mesh.")
            if kind == "vtx" else
            tr("'{0}' is a face anchor, but '{1}' has no mesh.")).format(
                anchor, short_name(matches[0])))
    count = (cmds.polyEvaluate(mesh, vertex=True) if kind == "vtx"
             else cmds.polyEvaluate(mesh, face=True))
    if index >= count:
        raise CableToolError((
            tr("'{0}' doesn't exist: the mesh only has {1} vertices. Pick "
               "it again with Get Selected.") if kind == "vtx" else
            tr("'{0}' doesn't exist: the mesh only has {1} faces. Pick it "
               "again with Get Selected.")).format(anchor, count))
    return "{0}.{1}[{2}]".format(matches[0], kind, index)


def split(anchor):
    """("pCube1", "vtx", 12) for "pCube1.vtx[12]"; (anchor, None, -1) for
    a plain transform."""
    match = _COMPONENT.match(anchor)
    if match is None:
        return anchor, None, -1
    return match.group("node"), match.group("kind"), int(match.group("index"))


def node_of(anchor):
    """The transform an anchor belongs to."""
    return split(anchor)[0]


def short_name(node):
    node, kind, index = split(node)
    name = node.split("|")[-1]
    return name if kind is None else "{0}.{1}[{2}]".format(name, kind, index)


def world_position(anchor):
    node, kind, _index = split(anchor)
    if kind is None:
        return tuple(cmds.xform(node, query=True, worldSpace=True,
                                translation=True))
    flat = cmds.xform(anchor, query=True, worldSpace=True, translation=True)
    points = [flat[i:i + 3] for i in range(0, len(flat), 3)]
    return tuple(sum(p[axis] for p in points) / len(points)
                 for axis in range(3))


def distance(p, q):
    return sum((a - b) ** 2 for a, b in zip(p, q)) ** 0.5


def selected_anchors():
    """The selection in the order it was clicked: transforms, and single
    vertices or faces. Returns (anchors, ignored)."""
    if not cmds.selectPref(query=True, trackSelectionOrder=True):
        cmds.selectPref(trackSelectionOrder=True)
    selection = cmds.ls(orderedSelection=True, long=True, flatten=True) or []
    anchors, ignored = [], []
    for item in selection:
        if "." in item:
            node, kind, index = split(item)
            if kind is None:  # edges, UVs and so on
                ignored.append(item)
                continue
            if not cmds.objectType(node, isAType="transform"):
                node = cmds.listRelatives(node, parent=True, fullPath=True)[0]
            anchors.append("{0}.{1}[{2}]".format(node, kind, index))
        elif cmds.objectType(item, isAType="transform"):
            anchors.append(item)
        else:
            parents = cmds.listRelatives(item, parent=True, fullPath=True)
            if parents:
                anchors.append(parents[0])
            else:
                ignored.append(item)
    return anchors, ignored


def mesh_shape(anchor):
    """The anchor's own visible mesh shape, or None for locators, joints,
    groups and other non-mesh anchors."""
    for shape in cmds.listRelatives(node_of(anchor), shapes=True,
                                    fullPath=True, noIntermediate=True) or []:
        if cmds.objectType(shape) == "mesh":
            return shape
    return None
