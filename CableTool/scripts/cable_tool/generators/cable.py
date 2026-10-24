"""Cable / Pipe mode: a Sweep Mesh along a curve that the node network
keeps live.

The route's anchors become a list of *path points*:

    start [-> lead-out] -> waypoints... -> [lead-out ->] end

Network per cable:

    anchor.worldMatrix -> decomposeMatrix               = anchor pivot
    mesh end:  closestPointOnMesh(mesh, next anchor)     = surface point
               surface + normal * leadOut                = lead-out point
    per span:  distanceBetween(A, B) * sag               = span sag
    per point: blend(straight A->B, Catmull-Rom spline, smoothing)
               + (0, -w(t) * span sag, 0)                -> curve CV
    curve.worldSpace -> sweepMeshCreator -> mesh

The spline and sag weights are computed once at build time, so the
cable keeps its shape with no Python running when things move.
"""

import math

import maya.cmds as cmds

from cable_tool import nodes, route as route_mod
from cable_tool.config import (CATENARY_TENSION, DEGREES_PER_TURN, EPSILON,
                               LEAD_SAMPLES, SWEEP_PROFILE_POLY)
from cable_tool.generators.base import BaseGenerator

# Group attribute -> sweepMeshCreator attribute, connected directly.
# Twist is connected through a unit conversion (see _build_sweep).
SWEEP_LINKS = {
    "radius": "scaleProfileX",
    "sides": "profilePolySides",
    "taper": "taper",
}


def catenary_weight(t, tension=CATENARY_TENSION):
    """0 at both anchors, 1 at mid-span: the shape of a hanging chain."""
    if tension < EPSILON:
        return 4.0 * t * (1.0 - t)
    return ((math.cosh(tension) - math.cosh(tension * (2.0 * t - 1.0)))
            / (math.cosh(tension) - 1.0))


def _eased(t, ease_start, ease_end):
    weight = catenary_weight(t)
    if ease_start:
        weight *= t * (2.0 - t)
    if ease_end:
        weight *= 1.0 - t * t
    return weight


def sag_weight(t, ease_start=False, ease_end=False):
    """Catenary drop at t, peaking at 1. An eased end leaves its point
    level instead of at the chain's angle, so where two spans meet at a
    waypoint the cable turns smoothly instead of forming a V."""
    if not (ease_start or ease_end):
        return catenary_weight(t)
    peak = max(_eased(k / 200.0, ease_start, ease_end) for k in range(201))
    return _eased(t, ease_start, ease_end) / peak


def catmull_rom_weights(t):
    """Weights of P0..P3 for a point at t on the P1->P2 segment of a
    uniform Catmull-Rom spline, which passes through every point."""
    t2, t3 = t * t, t * t * t
    return (0.5 * (-t3 + 2.0 * t2 - t),
            0.5 * (3.0 * t3 - 5.0 * t2 + 2.0),
            0.5 * (-3.0 * t3 + 4.0 * t2 + t),
            0.5 * (t3 - t2))


def spline_terms(span, count, t):
    """{path point index: weight} for t on span (span -> span + 1) of a
    path with `count` points. Beyond either end the path is extended by
    mirroring, which keeps the end tangent pointing at its neighbour."""
    terms = {}

    def add(index, weight):
        terms[index] = terms.get(index, 0.0) + weight

    w0, w1, w2, w3 = catmull_rom_weights(t)
    add(span, w1)
    add(span + 1, w2)
    if span > 0:
        add(span - 1, w0)
    else:  # phantom = 2 * P0 - P1
        add(0, 2.0 * w0)
        add(1, -w0)
    if span + 2 < count:
        add(span + 2, w3)
    else:  # phantom = 2 * Plast - Plast-1
        add(count - 1, 2.0 * w3)
        add(count - 2, -w3)
    return terms


def sample_parameters(samples):
    """Interior t values for one span, ends excluded."""
    return [float(k) / (samples + 1) for k in range(1, samples + 1)]


class PathPoint(object):
    """A point the curve passes through, as a live float3 plug."""

    def __init__(self, plug, kind):
        self.plug = plug
        self.kind = kind  # "end", "lead" or "waypoint"


class CableGenerator(BaseGenerator):
    mode = "cable"
    label = "Cable / Pipe"
    noun = "cable"
    available = True
    summary = "A live tube along the route, built with Sweep Mesh."
    sections = (
        ("Shape", ("radius", "sides", "twist", "taper")),
        ("Path", ("sag", "smoothing", "samples")),
        ("Ends", ("attach", "leadOut")),
    )

    def _check_dependencies(self):
        nodes.ensure_sweep_plugin()

    def _build_network(self, name, anchors, settings):
        cable_id = self.cable_id
        pivots = [route_mod.anchor_driver(
            a, "{0}_anchor{1:02d}_dm".format(name, i), cable_id)
            for i, a in enumerate(anchors)]

        start, start_lead = self._end_point(name + "_start", anchors[0],
                                            pivots[0], pivots[1], cable_id)
        end, end_lead = self._end_point(name + "_end", anchors[-1],
                                        pivots[-1], pivots[-2], cable_id)
        path = [start]
        if start_lead:
            path.append(start_lead)
        path.extend(PathPoint(p, "waypoint") for p in pivots[1:-1])
        if end_lead:
            path.append(end_lead)
        path.append(end)

        curve_shape = self._build_curve(name, path, settings["samples"])
        self._wire_curve(name, curve_shape, path, settings["samples"],
                         cable_id)
        self._build_sweep(name, curve_shape, cable_id)

    # -- build steps ------------------------------------------------------
    def _end_point(self, prefix, anchor, pivot, neighbour, cable_id):
        """The Start or End path point, plus its lead-out point when the
        anchor is a mesh. A mesh end sits on the surface point closest to
        the next anchor, and the cable leaves along that point's normal."""
        mesh = route_mod.mesh_shape(anchor)
        if mesh is None:
            return PathPoint(pivot, "end"), None

        closest = nodes.create("closestPointOnMesh", prefix + "_cpom",
                               cable_id)
        # Object-space mesh plus the world matrix: fed .worldMesh instead,
        # the node never re-evaluates when the object is moved.
        cmds.connectAttr(mesh + ".outMesh", closest + ".inMesh")
        cmds.connectAttr(anchor + ".worldMatrix[0]",
                         closest + ".inputMatrix")
        cmds.connectAttr(neighbour, closest + ".inPosition")

        # Attach off -> the pivot, and no lead-out.
        on_surface = nodes.create("blendColors", prefix + "_attach",
                                  cable_id)
        cmds.connectAttr(closest + ".position", on_surface + ".color1")
        cmds.connectAttr(pivot, on_surface + ".color2")
        cmds.connectAttr(self.group + ".attach", on_surface + ".blender")

        reach = nodes.create("multDL", prefix + "_reach", cable_id)
        cmds.connectAttr(self.group + ".leadOut", reach + ".input1")
        cmds.connectAttr(self.group + ".attach", reach + ".input2")
        offset = nodes.create("multiplyDivide", prefix + "_leadOffset",
                              cable_id)
        cmds.connectAttr(closest + ".normal", offset + ".input1")
        for axis in "XYZ":
            cmds.connectAttr(reach + ".output", offset + ".input2" + axis)
        lead = nodes.create("plusMinusAverage", prefix + "_lead", cable_id)
        cmds.connectAttr(on_surface + ".output", lead + ".input3D[0]")
        cmds.connectAttr(offset + ".output", lead + ".input3D[1]")

        return (PathPoint(on_surface + ".output", "end"),
                PathPoint(lead + ".output3D", "lead"))

    @staticmethod
    def _spans(path, samples):
        """(index, sample count, sags, eases start, eases end) per span.
        Spans touching a lead-out point are short and straight: no sag."""
        spans = []
        for i, (a, b) in enumerate(zip(path, path[1:])):
            is_lead_span = (a.kind, b.kind) in (("end", "lead"),
                                                ("lead", "end"))
            spans.append((i, LEAD_SAMPLES if is_lead_span else samples,
                          not is_lead_span, a.kind != "end",
                          b.kind != "end"))
        return spans

    def _build_curve(self, name, path, samples):
        count = len(path) + sum(span[1] for span in self._spans(path,
                                                                 samples))
        # Placeholder positions; the network sets every CV once connected.
        points = [(float(i), 0.0, 0.0) for i in range(count)]
        curve = cmds.curve(degree=3, point=points, name=name + "_crv")
        curve = cmds.parent(curve, self.group)[0]
        # CVs are world positions, so the curve must ignore its parents.
        cmds.setAttr(curve + ".inheritsTransform", 0)
        shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
        nodes.tag(curve, self.cable_id)
        nodes.tag(shape, self.cable_id)
        return shape

    def _weighted_sum(self, prefix, terms, path, cable_id):
        total = nodes.create("plusMinusAverage", prefix + "_spline", cable_id)
        slot = 0
        for index, weight in sorted(terms.items()):
            if abs(weight) < EPSILON:
                continue
            scaled = nodes.create("multiplyDivide",
                                  "{0}_w{1:02d}".format(prefix, index),
                                  cable_id)
            cmds.connectAttr(path[index].plug, scaled + ".input1")
            cmds.setAttr(scaled + ".input2", weight, weight, weight)
            cmds.connectAttr(scaled + ".output",
                             "{0}.input3D[{1}]".format(total, slot))
            slot += 1
        return total + ".output3D"

    def _wire_curve(self, name, curve_shape, path, samples, cable_id):
        def set_cv(index, plug):
            cmds.connectAttr(plug, "{0}.controlPoints[{1}]".format(
                curve_shape, index))

        cv = 0
        for span, count, sags, ease_start, ease_end in self._spans(path,
                                                                    samples):
            a, b = path[span].plug, path[span + 1].plug
            prefix = "{0}_span{1:02d}".format(name, span)
            set_cv(cv, a)
            cv += 1

            if sags:
                dist = nodes.create("distanceBetween", prefix + "_dist",
                                    cable_id)
                cmds.connectAttr(a, dist + ".point1")
                cmds.connectAttr(b, dist + ".point2")
                span_sag = nodes.create("multDL", prefix + "_sag", cable_id)
                cmds.connectAttr(dist + ".distance", span_sag + ".input1")
                cmds.connectAttr(self.group + ".sag", span_sag + ".input2")

            for k, t in enumerate(sample_parameters(count)):
                point = "{0}_pt{1:02d}".format(prefix, k)
                straight = nodes.create("blendColors", point + "_lerp",
                                        cable_id)
                cmds.connectAttr(b, straight + ".color1")
                cmds.connectAttr(a, straight + ".color2")
                cmds.setAttr(straight + ".blender", t)

                if not sags:
                    # A lead-out span stays straight along the normal: it
                    # is much shorter than its neighbours, and a uniform
                    # spline loops on a short span next to a long one.
                    set_cv(cv, straight + ".output")
                    cv += 1
                    continue

                spline = self._weighted_sum(
                    point, spline_terms(span, len(path), t), path, cable_id)
                base = nodes.create("blendColors", point + "_smooth",
                                    cable_id)
                cmds.connectAttr(spline, base + ".color1")
                cmds.connectAttr(straight + ".output", base + ".color2")
                cmds.connectAttr(self.group + ".smoothing",
                                 base + ".blender")

                drop = nodes.create("multDL", point + "_drop", cable_id)
                cmds.connectAttr(span_sag + ".output", drop + ".input1")
                cmds.setAttr(drop + ".input2",
                             -sag_weight(t, ease_start, ease_end))
                total = nodes.create("plusMinusAverage", point + "_pos",
                                     cable_id)
                cmds.connectAttr(base + ".output", total + ".input3D[0]")
                cmds.connectAttr(drop + ".output",
                                 total + ".input3D[1].input3Dy")
                set_cv(cv, total + ".output3D")
                cv += 1

        set_cv(cv, path[-1].plug)

    def _build_sweep(self, name, curve_shape, cable_id):
        sweep = nodes.create("sweepMeshCreator", name + "_sweep", cable_id)
        cmds.setAttr(sweep + ".sweepProfileType", SWEEP_PROFILE_POLY)
        cmds.setAttr(sweep + ".scaleProfileUniform", True)
        for group_attr, sweep_attr in SWEEP_LINKS.items():
            cmds.connectAttr(self.group + "." + group_attr,
                             sweep + "." + sweep_attr)
        # Sweep Mesh counts Twist in whole turns; the tool shows degrees.
        # (Connecting degrees straight in turned 90 into 90 full turns,
        # which wrung the tube into pinched segments.)
        turns = nodes.create("multDL", name + "_twistTurns", cable_id)
        cmds.connectAttr(self.group + ".twist", turns + ".input1")
        cmds.setAttr(turns + ".input2", 1.0 / DEGREES_PER_TURN)
        cmds.connectAttr(turns + ".output", sweep + ".twist")
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
