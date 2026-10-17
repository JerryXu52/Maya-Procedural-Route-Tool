"""Cable / Pipe mode: a Sweep Mesh along a curve that the node network
keeps live.

Network per cable:

    anchor.worldMatrix -> decomposeMatrix -> curve CV at the anchor
    per span:  distanceBetween(A, B) * sag            = span sag
    per point: blendColors(A, B, t) + (0, -w(t) * span sag, 0) -> curve CV
    curve.worldSpace -> sweepMeshCreator -> mesh

w(t) is a catenary weight computed once at build time, so the cable
keeps a hanging-chain shape with no Python running when things move.
"""

import math

import maya.cmds as cmds

from cable_tool import nodes, route as route_mod
from cable_tool.config import (DEFAULTS, SETTING_ORDER, MODE_ATTR,
                               CATENARY_TENSION, EPSILON,
                               SWEEP_PROFILE_POLY, CableToolError,
                               sanitize_settings)
from cable_tool.generators.base import BaseGenerator

ANCHORS_ATTR = "anchors"

# Group attribute -> sweepMeshCreator attribute.
SWEEP_LINKS = {
    "radius": "scaleProfileX",
    "sides": "profilePolySides",
    "twist": "twist",
    "taper": "taper",
}


def catenary_weight(t, tension=CATENARY_TENSION):
    """0 at both anchors, 1 at mid-span: the shape of a hanging chain."""
    if tension < EPSILON:
        return 4.0 * t * (1.0 - t)
    return ((math.cosh(tension) - math.cosh(tension * (2.0 * t - 1.0)))
            / (math.cosh(tension) - 1.0))


def sample_parameters(samples):
    """Interior t values for one span, ends excluded."""
    return [float(k) / (samples + 1) for k in range(1, samples + 1)]


def _next_name():
    index = 1
    while cmds.objExists("cable_{0:02d}_GRP".format(index)):
        index += 1
    return "cable_{0:02d}".format(index)


class CableGenerator(BaseGenerator):
    mode = "cable"

    def __init__(self, group=None):
        self.group = group

    # -- lookup -----------------------------------------------------------
    @classmethod
    def from_node(cls, node):
        """The generator for the cable that owns any selected node."""
        group = nodes.cable_group_from(node)
        if group is None:
            return None
        if cmds.getAttr(group + "." + MODE_ATTR) != cls.mode:
            return None
        return cls(group)

    @property
    def cable_id(self):
        return cmds.ls(self.group, uuid=True)[0]

    def exists(self):
        return bool(self.group) and nodes.is_cable_group(self.group)

    def read_settings(self):
        return {key: cmds.getAttr(self.group + "." + key)
                for key in SETTING_ORDER}

    def read_route(self):
        plug = self.group + "." + ANCHORS_ATTR
        anchors = []
        for index in cmds.getAttr(plug, multiIndices=True) or []:
            source = cmds.listConnections("{0}[{1}]".format(plug, index),
                                          source=True, destination=False)
            if source:
                anchors.append(source[0])
        if len(anchors) < 2:
            raise CableToolError("This cable has lost its anchors (were they "
                                 "deleted?). Pick new ones and Rebuild.")
        return route_mod.Route(anchors[0], anchors[-1], anchors[1:-1])

    # -- interface --------------------------------------------------------
    def build(self, route, settings, name=None):
        nodes.ensure_sweep_plugin()
        anchors = route.validate()
        settings = sanitize_settings(settings)
        name = name or _next_name()

        with nodes.undo_chunk("CableTool_Build"):
            group = cmds.createNode("transform", name=name + "_GRP",
                                    parent=nodes.root_group())
            group = cmds.ls(group, long=True)[0]
            self.group = group
            cable_id = self.cable_id
            nodes.tag(group, cable_id)
            cmds.addAttr(group, longName=MODE_ATTR, dataType="string")
            cmds.setAttr(group + "." + MODE_ATTR, self.mode, type="string",
                         lock=True)
            self._add_setting_attrs(settings)
            self._record_anchors(anchors)

            drivers = [route_mod.anchor_driver(
                a, "{0}_anchor{1:02d}_dm".format(name, i), cable_id)
                for i, a in enumerate(anchors)]

            curve_shape = self._build_curve(name, anchors, settings, cable_id)
            self._wire_curve(name, curve_shape, drivers, settings["samples"],
                             cable_id)
            self._build_sweep(name, curve_shape, cable_id)
            for xform in cmds.listRelatives(group, children=True,
                                            fullPath=True) or []:
                for channel in ("t", "r", "s"):
                    cmds.setAttr(xform + "." + channel, lock=True)
        return self.group

    def update(self, settings):
        """Set live attributes. Returns the keys that need a Rebuild."""
        pending = []
        for key, value in sanitize_settings(settings).items():
            if key not in settings:
                continue
            plug = self.group + "." + key
            if DEFAULTS[key]["live"]:
                if cmds.getAttr(plug) != value:
                    cmds.setAttr(plug, value)
            elif cmds.getAttr(plug) != value:
                pending.append(key)
        return pending

    def rebuild(self, route, settings):
        """Rebuild in place, keeping the cable's name."""
        name = self.group.split("|")[-1].rsplit("_GRP", 1)[0]
        with nodes.undo_chunk("CableTool_Rebuild"):
            self.delete()
            return self.build(route, settings, name=name)

    def delete(self):
        count = nodes.delete_cable(self.cable_id)
        self.group = None
        return count

    # -- build steps ------------------------------------------------------
    def _add_setting_attrs(self, settings):
        for key in SETTING_ORDER:
            spec = DEFAULTS[key]
            low, high = spec["field"]
            cmds.addAttr(self.group, longName=key, niceName=spec["label"],
                         attributeType="long" if spec["int"] else "double",
                         minValue=low, maxValue=high,
                         defaultValue=spec["default"])
            plug = self.group + "." + key
            cmds.setAttr(plug, settings[key])
            if spec["live"]:
                cmds.setAttr(plug, keyable=True)
            else:
                # Visible but not keyable: changing it needs a Rebuild.
                cmds.setAttr(plug, channelBox=True)

    def _record_anchors(self, anchors):
        cmds.addAttr(self.group, longName=ANCHORS_ATTR,
                     attributeType="message", multi=True)
        for i, anchor in enumerate(anchors):
            cmds.connectAttr(anchor + ".message",
                             "{0}.{1}[{2}]".format(self.group, ANCHORS_ATTR,
                                                   i))

    def _build_curve(self, name, anchors, settings, cable_id):
        # Starting positions only; the network takes over as soon as it
        # is connected.
        positions = [route_mod.world_position(a) for a in anchors]
        points = []
        for a, b in zip(positions, positions[1:]):
            points.append(a)
            length = route_mod.distance(a, b)
            for t in sample_parameters(settings["samples"]):
                drop = settings["sag"] * length * catenary_weight(t)
                points.append(tuple(a[i] + (b[i] - a[i]) * t
                                    - (drop if i == 1 else 0.0)
                                    for i in range(3)))
        points.append(positions[-1])

        curve = cmds.curve(degree=3, point=points, name=name + "_crv")
        curve = cmds.parent(curve, self.group)[0]
        # CVs are world positions, so the curve must ignore its parents.
        cmds.setAttr(curve + ".inheritsTransform", 0)
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        nodes.tag(curve, cable_id)
        nodes.tag(shape, cable_id)
        return shape

    def _wire_curve(self, name, curve_shape, drivers, samples, cable_id):
        cv = 0
        params = sample_parameters(samples)
        for span, (a, b) in enumerate(zip(drivers, drivers[1:])):
            prefix = "{0}_span{1:02d}".format(name, span)
            cmds.connectAttr(a, "{0}.controlPoints[{1}]".format(curve_shape,
                                                                cv))
            cv += 1

            dist = nodes.create("distanceBetween", prefix + "_dist", cable_id)
            cmds.connectAttr(a, dist + ".point1")
            cmds.connectAttr(b, dist + ".point2")
            span_sag = nodes.create("multDL", prefix + "_sag", cable_id)
            cmds.connectAttr(dist + ".distance", span_sag + ".input1")
            cmds.connectAttr(self.group + ".sag", span_sag + ".input2")

            for k, t in enumerate(params):
                point = "{0}_pt{1:02d}".format(prefix, k)
                blend = nodes.create("blendColors", point + "_lerp", cable_id)
                cmds.connectAttr(b, blend + ".color1")
                cmds.connectAttr(a, blend + ".color2")
                cmds.setAttr(blend + ".blender", t)

                drop = nodes.create("multDL", point + "_drop", cable_id)
                cmds.connectAttr(span_sag + ".output", drop + ".input1")
                cmds.setAttr(drop + ".input2", -catenary_weight(t))

                total = nodes.create("plusMinusAverage", point + "_pos",
                                     cable_id)
                cmds.connectAttr(blend + ".output", total + ".input3D[0]")
                cmds.connectAttr(drop + ".output", total + ".input3D[1].input3Dy")
                cmds.connectAttr(total + ".output3D",
                                 "{0}.controlPoints[{1}]".format(curve_shape,
                                                                 cv))
                cv += 1

        cmds.connectAttr(drivers[-1], "{0}.controlPoints[{1}]".format(
            curve_shape, cv))

    def _build_sweep(self, name, curve_shape, cable_id):
        sweep = nodes.create("sweepMeshCreator", name + "_sweep", cable_id)
        cmds.setAttr(sweep + ".sweepProfileType", SWEEP_PROFILE_POLY)
        cmds.setAttr(sweep + ".scaleProfileUniform", True)
        for group_attr, sweep_attr in SWEEP_LINKS.items():
            cmds.connectAttr(self.group + "." + group_attr,
                             sweep + "." + sweep_attr)
        cmds.connectAttr(curve_shape + ".worldSpace[0]",
                         sweep + ".inCurveArray[0]")

        geo = nodes.create("transform", name + "_geo", cable_id,
                           parent=self.group)
        geo = cmds.ls(geo, long=True)[0]
        cmds.setAttr(geo + ".inheritsTransform", 0)
        shape = nodes.create("mesh", name + "_geoShape", cable_id, parent=geo)
        cmds.connectAttr(sweep + ".outMeshArray[0]", shape + ".inMesh")
        cmds.sets(shape, edit=True, forceElement="initialShadingGroup")
        return geo
