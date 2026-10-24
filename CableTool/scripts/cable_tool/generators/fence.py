"""Fence mode: posts, rails and pickets along the route, made by the
fence builder node and kept live by Maya's dependency graph.

Network:

    anchor.worldMatrix (+ mesh for a vertex or face anchor) --+
    ground mesh.outMesh + worldMatrix, post / picket meshes --+
    fence group settings -------------------------------------+
        --> fenceToolBuilder --> outPosts   -> <name>_posts_geo
                             --> outRails   -> <name>_rails_geo
                             --> outPickets -> <name>_pickets_geo

Posts, rails and pickets are separate meshes so each can get its own
material. The layout itself is in cable_tool.fence.
"""

import maya.cmds as cmds

from cable_tool import fence, nodes, route as route_mod
from cable_tool.config import CableToolError
from cable_tool.generators.base import BaseGenerator
from cable_tool.i18n import tr

# Starting points for the Preset menu. Anything not listed keeps its
# default.
PRESETS = (
    ("Picket Fence", {
        "postSpacing": 2.0, "postHeight": 1.1, "postWidth": 0.1,
        "railCount": 2, "railBottom": 0.25, "railTop": 0.85,
        "railSize": 0.08, "railDepth": 0.035, "pickets": 1,
        "picketHeight": 1.0, "picketWidth": 0.08, "picketGap": 0.06,
        "picketPoint": 0.8, "postCap": 1.0}),
    ("Ranch Rail", {
        "postSpacing": 2.5, "postHeight": 1.3, "postWidth": 0.15,
        "railCount": 3, "railBottom": 0.35, "railTop": 1.15,
        "railSize": 0.15, "railDepth": 0.05, "pickets": 0}),
    ("Privacy Fence", {
        "postSpacing": 2.4, "postHeight": 1.85, "postWidth": 0.1,
        "railCount": 2, "railBottom": 0.3, "railTop": 1.55,
        "railSize": 0.09, "railDepth": 0.04, "pickets": 1,
        "picketHeight": 1.8, "picketWidth": 0.14, "picketGap": 0.005,
        "picketPoint": 0.0}),
    ("Wire Fence", {
        "postSpacing": 3.0, "postHeight": 1.25, "postWidth": 0.1,
        "roundPosts": 1, "railCount": 4, "railBottom": 0.3, "railTop": 1.15,
        "railSize": 0.008, "roundRails": 1, "railSag": 0.012, "pickets": 0,
        "wear": 0.4}),
    ("Pipe Railing", {
        "postSpacing": 1.5, "postHeight": 1.05, "postWidth": 0.05,
        "roundPosts": 1, "railCount": 2, "railBottom": 0.5, "railTop": 1.0,
        "railSize": 0.045, "roundRails": 1, "railInline": 1, "railSag": 0.0,
        "pickets": 0}),
)


class FenceGenerator(BaseGenerator):
    mode = "fence"
    label = "Fence"
    noun = "fence"
    available = True
    summary = ("Posts along the route joined by rails, with optional "
               "pickets. Steps over the ground if you pick one.")
    sections = (
        ("Layout", ("postSpacing", "cornerPosts", "fenceCurve",
                    "fenceFlip")),
        ("Posts", ("postHeight", "postWidth", "roundPosts", "postCap")),
        ("Rails", ("railCount", "railBottom", "railTop", "railSize",
                   "railDepth", "roundRails", "railInline", "railSag")),
        ("Pickets", ("pickets", "picketHeight", "picketWidth", "picketGap",
                     "picketThickness", "picketPoint")),
        ("Surface", ("wear", "fenceSeed", "fenceUvRepeat")),
    )
    presets = PRESETS
    extras = (
        ("ground", "Ground",
         "A mesh for the fence to stand on: each post and picket is "
         "dropped onto it. Empty: the fence runs at the anchors' height.",
         "Layout"),
        ("postSource", "Post Mesh",
         "Your own post, modelled standing on the origin with its front "
         "facing +X. It's scaled to Post Height. Empty: a plain post.",
         "Posts"),
        ("picketSource", "Picket Mesh",
         "Your own picket, modelled standing on the origin with its face "
         "toward +Z. It's scaled to Picket Height. Empty: a plain board.",
         "Pickets"),
    )
    # Mesh output -> the part it becomes.
    PARTS = (("outPosts", "posts"), ("outRails", "rails"),
             ("outPickets", "pickets"))

    def _check_dependencies(self):
        if not cmds.pluginInfo("cableTool", query=True, loaded=True):
            raise CableToolError(tr(
                "The cableTool plugin isn't loaded, and the fence builder "
                "lives in it. Load cableTool.py in the Plug-in Manager."))

    def _build_network(self, name, anchors, settings):
        cable_id = self.cable_id
        builder = nodes.create(fence.NODE_NAME, name + "_builder", cable_id)
        for i, anchor in enumerate(anchors):
            element = "{0}.anchor[{1}]".format(builder, i)
            node, kind, index = route_mod.split(anchor)
            cmds.connectAttr(node + ".worldMatrix[0]",
                             element + ".anchorMatrix")
            if kind is not None:
                cmds.setAttr(element + ".anchorKind",
                             route_mod.COMPONENT_KINDS[kind])
                cmds.setAttr(element + ".anchorIndex", index)
                cmds.connectAttr(route_mod.mesh_shape(anchor) + ".outMesh",
                                 element + ".anchorMesh")
        for key in fence.FenceBuilderNode.SETTINGS:
            cmds.connectAttr(self.group + "." + key, builder + "." + key)

        extras = self.read_extras()
        for key, plug in (("ground", "groundMesh"), ("postSource", "postMesh"),
                          ("picketSource", "picketMesh")):
            if not extras.get(key):
                continue
            mesh = route_mod.mesh_shape(extras[key])
            if mesh is None:
                raise CableToolError(tr("'{0}' has no mesh, so it can't be "
                                        "used as {1}.").format(
                                            route_mod.short_name(extras[key]),
                                            tr(dict((k, label) for k, label, _t,
                                                    _s in self.extras)[key])))
            cmds.connectAttr(mesh + ".outMesh", builder + "." + plug)
            if key == "ground":
                cmds.connectAttr(extras[key] + ".worldMatrix[0]",
                                 builder + ".groundMatrix")

        for output, part in self.PARTS:
            geo = nodes.create("transform", "{0}_{1}_geo".format(name, part),
                               cable_id, parent=self.group)
            geo = cmds.ls(geo, long=True)[0]
            # The builder works in world space, so the meshes ignore parents.
            cmds.setAttr(geo + ".inheritsTransform", 0)
            shape = nodes.create("mesh", "{0}_{1}_geoShape".format(name, part),
                                 cable_id, parent=geo)
            cmds.connectAttr(builder + "." + output, shape + ".inMesh")
            cmds.sets(shape, edit=True, forceElement="initialShadingGroup")

    def builder(self):
        """The fenceToolBuilder node of this fence."""
        found = [node for node in nodes.tagged_nodes(self.cable_id)
                 if cmds.nodeType(node) == fence.NODE_NAME]
        return found[0] if found else None
