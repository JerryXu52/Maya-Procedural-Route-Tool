"""Cable / Pipe mode: a Sweep Mesh along the curve the cable solver
computes, kept live by Maya's dependency graph.

Network per cable:

    anchor.worldMatrix, anchor mesh.outMesh --+
    cable group settings ---------------------+--> cableToolSolver
    cableToolSolver.outCurve -> curve shape -> sweepMeshCreator -> mesh

The solver (cable_tool.solver) works out where a real cable would hang:
ends on the surfaces they attach to, draped over mesh waypoints, sagging
under gravity, bending only so tightly and never passing through the
objects it is attached to.
"""

import maya.cmds as cmds

from cable_tool import nodes, route as route_mod, solver
from cable_tool.config import (DEGREES_PER_TURN, SWEEP_INTERP_DISTANCE,
                               SWEEP_PROFILE_POLY, SWEEP_UVS_UNFOLD,
                               CableToolError)
from cable_tool.generators.base import BaseGenerator

# Group attribute -> sweepMeshCreator attribute, connected directly.
# The radius comes from each wire's solver (after Thickness Variation);
# twist and ring spacing are converted first (see _build_sweep).
SWEEP_LINKS = {
    "sides": "profilePolySides",
    "taper": "taper",
}

# Starting points for the Preset menu. Anything not listed keeps its
# default.
PRESETS = (
    ("Single Pipe", {
        "radius": 0.15, "sides": 12, "sag": 0.05, "stiffness": 0.8,
        "wireCount": 1, "leadOut": 0.4}),
    ("Utility Line", {
        "radius": 0.04, "sides": 8, "sag": 0.05, "stiffness": 0.05,
        "wireCount": 4, "spread": 2.0, "spreadRow": 1,
        "slackVariation": 0.15, "thicknessVariation": 0.1, "leadOut": 0.0}),
    ("Cyberpunk Tangle", {
        "radius": 0.05, "sides": 8, "sag": 0.15, "stiffness": 0.1,
        "wireCount": 14, "spread": 1.5, "spreadRow": 0,
        "slackVariation": 1.0, "thicknessVariation": 0.7, "leadOut": 0.1}),
)


class CableGenerator(BaseGenerator):
    mode = "cable"
    label = "Cable / Pipe"
    noun = "cable"
    available = True
    summary = "A live tube along the route, built with Sweep Mesh."
    sections = (
        ("Shape", ("radius", "sides", "lengthDetail", "twist", "taper")),
        ("Path", ("sag", "stiffness", "smoothing", "samples", "drape")),
        ("Wires", ("wireCount", "spread", "spreadRow", "slackVariation",
                   "thicknessVariation", "seed")),
        ("Ends", ("attach", "leadOut")),
        ("Surface", ("endCaps", "uvRepeat")),
    )
    presets = PRESETS

    def _check_dependencies(self):
        nodes.ensure_sweep_plugin()
        if not cmds.pluginInfo("cableTool", query=True, loaded=True):
            raise CableToolError(
                "The cableTool plugin isn't loaded, and the cable solver "
                "lives in it. Load cableTool.py in the Plug-in Manager.")

    def _build_network(self, name, anchors, settings):
        for wire in range(settings["wireCount"]):
            self._build_wire("{0}_w{1:02d}".format(name, wire), wire,
                             anchors)

    def _build_wire(self, name, wire, anchors):
        """One wire: its own solver, curve and Sweep Mesh."""
        cable_id = self.cable_id
        solve = nodes.create(solver.NODE_NAME, name + "_solver", cable_id)
        cmds.setAttr(solve + ".wireIndex", wire)
        for i, anchor in enumerate(anchors):
            element = "{0}.anchor[{1}]".format(solve, i)
            node, kind, index = route_mod.split(anchor)
            cmds.connectAttr(node + ".worldMatrix[0]",
                             element + ".anchorMatrix")
            if kind is not None:
                cmds.setAttr(element + ".anchorKind",
                             route_mod.COMPONENT_KINDS[kind])
                cmds.setAttr(element + ".anchorIndex", index)
            mesh = route_mod.mesh_shape(anchor)
            if mesh:
                cmds.connectAttr(mesh + ".outMesh", element + ".anchorMesh")
        for key in solver.CableSolverNode.SETTINGS:
            cmds.connectAttr(self.group + "." + key, solve + "." + key)

        curve = nodes.create("transform", name + "_crv", cable_id,
                             parent=self.group)
        curve = cmds.ls(curve, long=True)[0]
        # The solver works in world space, so the curve ignores parents.
        cmds.setAttr(curve + ".inheritsTransform", 0)
        shape = nodes.create("nurbsCurve", name + "_crvShape", cable_id,
                             parent=curve)
        cmds.connectAttr(solve + ".outCurve", shape + ".create")
        self._build_sweep(name, shape, solve + ".outRadius", cable_id)

    def _build_sweep(self, name, curve_shape, radius, cable_id):
        sweep = nodes.create("sweepMeshCreator", name + "_sweep", cable_id)
        cmds.setAttr(sweep + ".sweepProfileType", SWEEP_PROFILE_POLY)
        cmds.setAttr(sweep + ".scaleProfileUniform", True)
        cmds.connectAttr(radius, sweep + ".scaleProfileX")
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
        # A ring every so often along the length, spaced by the tube's
        # diameter / Length Detail. The default (Precision) put rings only
        # at a few points, so the tube was a chain of straight, creased
        # pieces. Tied to the radius, it suits any scene scale.
        cmds.setAttr(sweep + ".interpolationMode", SWEEP_INTERP_DISTANCE)
        diameter = nodes.create("multDL", name + "_diameter", cable_id)
        cmds.connectAttr(radius, diameter + ".input1")
        cmds.setAttr(diameter + ".input2", 2.0)
        spacing = nodes.create("multiplyDivide", name + "_ringSpacing",
                               cable_id)
        cmds.setAttr(spacing + ".operation", 2)  # divide
        cmds.connectAttr(diameter + ".output", spacing + ".input1X")
        cmds.connectAttr(self.group + ".lengthDetail", spacing + ".input2X")
        cmds.connectAttr(spacing + ".outputX",
                         sweep + ".interpolationDistance")
        cmds.connectAttr(curve_shape + ".worldSpace[0]",
                         sweep + ".inCurveArray[0]")
        cmds.connectAttr(self.group + ".endCaps", sweep + ".capsEnable")

        geo = nodes.create("transform", name + "_geo", cable_id,
                           parent=self.group)
        geo = cmds.ls(geo, long=True)[0]
        cmds.setAttr(geo + ".inheritsTransform", 0)
        shape = nodes.create("mesh", name + "_geoShape", cable_id, parent=geo)
        cmds.connectAttr(self._uvs_along_length(name, sweep, curve_shape,
                                                cable_id),
                         shape + ".inMesh")
        cmds.sets(shape, edit=True, forceElement="initialShadingGroup")
        return geo

    def _uvs_along_length(self, name, sweep, curve_shape, cable_id):
        """Sweep Mesh's Unfold UVs run V 0-1 along the cable and U around
        it with square texels. Scaling both by length x repeat-per-unit
        makes a texture tile at the same density on every cable, live as
        the cable stretches. Returns the mesh plug to feed the shape."""
        cmds.setAttr(sweep + ".createUVs", SWEEP_UVS_UNFOLD)
        info = nodes.create("curveInfo", name + "_length", cable_id)
        cmds.connectAttr(curve_shape + ".worldSpace[0]",
                         info + ".inputCurve")
        tiles = nodes.create("multDL", name + "_uvTiles", cable_id)
        cmds.connectAttr(info + ".arcLength", tiles + ".input1")
        cmds.connectAttr(self.group + ".uvRepeat", tiles + ".input2")
        scale = nodes.create("polyMoveUV", name + "_uvScale", cable_id)
        # Every UV, however many the tube has as it changes.
        cmds.setAttr(scale + ".inputComponents", 1, "map[*]",
                     type="componentList")
        cmds.setAttr(scale + ".pivotU", 0.0)
        cmds.setAttr(scale + ".pivotV", 0.0)
        cmds.connectAttr(tiles + ".output", scale + ".scaleU")
        cmds.connectAttr(tiles + ".output", scale + ".scaleV")
        cmds.connectAttr(sweep + ".outMeshArray[0]",
                         scale + ".inputPolymesh")
        return scale + ".output"
