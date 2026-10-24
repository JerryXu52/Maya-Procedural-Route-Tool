"""The interface every mode's generator follows, so the UI can drive a
cable, fence or road the same way.

BaseGenerator owns everything that is not specific to one mode: the
tagged output group, the settings stored on it, the anchors it records,
Load / Rebuild / Delete. A mode only says what its settings are and
builds its own node network in _build_network().
"""

import maya.cmds as cmds

from cable_tool import nodes, route as route_mod
from cable_tool.i18n import tr
from cable_tool.config import (DEFAULTS, MODE_ATTR, CableToolError,
                               sanitize_settings)

ANCHORS_ATTR = "anchors"
# Per anchor, the component part of its name ("vtx[12]", "f[3]" or ""):
# a message connection can only point at the object.
COMPONENTS_ATTR = "anchorComponents"


class BaseGenerator(object):
    # Overridden by each mode.
    mode = None            # stored on the group in MODE_ATTR
    label = None           # dropdown text
    noun = "build"         # "Generate Cable", "cable_01_GRP", ...
    available = False      # False = shown greyed out in the dropdown
    summary = ""           # one line for the mode's panel / tooltip
    sections = ()          # (("Shape", ("radius", ...)), ...) for the UI
    presets = ()           # (("Name", {setting: value}), ...)
    # Inputs that are scene nodes, not numbers, e.g. a custom clamp mesh:
    # (("key", "Label", "tooltip", "Section shown in"), ...). Stored on the
    # group as message connections so Rebuild keeps them.
    extras = ()

    def __init__(self, group=None):
        self.group = group

    # -- settings ---------------------------------------------------------
    @classmethod
    def setting_keys(cls):
        return tuple(key for _title, keys in cls.sections for key in keys)

    @classmethod
    def default_settings(cls):
        return {key: DEFAULTS[key]["default"] for key in cls.setting_keys()}

    @classmethod
    def preset(cls, name):
        """Full settings for a preset: its values over the defaults."""
        values = cls.default_settings()
        values.update(dict(cls.presets)[name])
        return values

    @classmethod
    def sanitize(cls, settings):
        clean = sanitize_settings(settings)
        return {key: clean[key] for key in cls.setting_keys()}

    # -- lookup -----------------------------------------------------------
    @classmethod
    def from_node(cls, node):
        """The generator for the build that owns any selected node, if it
        was built by this mode."""
        group = nodes.cable_group_from(node)
        if group is None:
            return None
        if cmds.getAttr(group + "." + MODE_ATTR) != cls.mode:
            return None
        return cls(group)

    @property
    def cable_id(self):
        return cmds.ls(self.group, uuid=True)[0]

    @property
    def name(self):
        return self.group.split("|")[-1].rsplit("_GRP", 1)[0]

    def exists(self):
        return bool(self.group) and nodes.is_cable_group(self.group)

    def read_settings(self):
        return {key: cmds.getAttr(self.group + "." + key)
                for key in self.setting_keys()}

    def read_route(self):
        plug = self.group + "." + ANCHORS_ATTR
        anchors = []
        for index in cmds.getAttr(plug, multiIndices=True) or []:
            source = cmds.listConnections("{0}[{1}]".format(plug, index),
                                          source=True, destination=False)
            if not source:
                continue
            part = cmds.getAttr("{0}.{1}[{2}]".format(
                self.group, COMPONENTS_ATTR, index)) or ""
            anchors.append(source[0] + ("." + part if part else ""))
        if len(anchors) < 2:
            raise CableToolError(tr("This {0} has lost its anchors (were "
                                    "they deleted?). Pick new ones and "
                                    "Rebuild.").format(tr(self.noun)))
        return route_mod.Route(anchors[0], anchors[-1], anchors[1:-1])

    # -- interface --------------------------------------------------------
    def read_extras(self):
        """{key: node or None} for this build's extras."""
        values = {}
        for key, _label, _tip, _section in self.extras:
            plug = self.group + "." + key
            source = (cmds.listConnections(plug, source=True,
                                           destination=False)
                      if cmds.attributeQuery(key, node=self.group,
                                             exists=True) else None)
            values[key] = cmds.ls(source[0], long=True)[0] if source else None
        return values

    def build(self, route, settings, name=None, extras=None):
        """Create the live setup for a route. Returns the group node."""
        if not self.available:
            raise CableToolError(tr("{0} mode isn't built yet; switch the "
                                    "Mode dropdown to Cable / Pipe.").format(
                                        tr(self.label)))
        self._check_dependencies()
        anchors = route.validate()
        settings = self.sanitize(settings)
        name = name or self._next_name()

        with nodes.undo_chunk("CableTool_Build"):
            group = cmds.createNode("transform", name=name + "_GRP",
                                    parent=nodes.root_group())
            self.group = cmds.ls(group, long=True)[0]
            nodes.tag(self.group, self.cable_id)
            cmds.addAttr(self.group, longName=MODE_ATTR, dataType="string")
            cmds.setAttr(self.group + "." + MODE_ATTR, self.mode,
                         type="string", lock=True)
            self._add_setting_attrs(settings)
            self._record_anchors(anchors)
            self._record_extras(extras or {})
            self._build_network(name, anchors, settings)
            for xform in cmds.listRelatives(self.group, children=True,
                                            fullPath=True) or []:
                for channel in ("t", "r", "s"):
                    cmds.setAttr(xform + "." + channel, lock=True)
        return self.group

    def update(self, settings):
        """Apply settings to an existing build. Live settings are set on
        the group; settings that change the network's structure rebuild it
        in place. Returns the keys that caused a rebuild."""
        clean = self.sanitize(settings)
        changed = {key: clean[key] for key in settings if key in clean
                   and cmds.getAttr(self.group + "." + key) != clean[key]}
        structural = [key for key in changed if DEFAULTS[key]["rebuild"]]
        if structural:
            route = self.read_route()
            merged = dict(self.read_settings(), **changed)
            self.rebuild(route, merged, self.read_extras())
            return structural
        for key, value in changed.items():
            cmds.setAttr(self.group + "." + key, value)
        return []

    def rebuild(self, route, settings, extras=None):
        """Rebuild in place, keeping the build's name."""
        name = self.name
        with nodes.undo_chunk("CableTool_Rebuild"):
            self.delete()
            return self.build(route, settings, name=name, extras=extras)

    def bake(self):
        """Freeze the build into plain meshes with no history, then remove
        the live build. Returns the group holding the baked meshes."""
        meshes = [geo for geo in cmds.listRelatives(
            self.group, children=True, fullPath=True, type="transform") or []
            if geo.endswith("_geo") or "_clamp" in geo.split("|")[-1]
            and not geo.endswith("_clampRing")]
        # A part that is switched off (a fence with no pickets) is empty.
        meshes = [geo for geo in meshes if cmds.polyEvaluate(geo, face=True)]
        if not meshes:
            raise CableToolError(tr("{0} has no geometry to bake.").format(
                route_mod.short_name(self.group)))
        name = self.name
        with nodes.undo_chunk("CableTool_Bake"):
            baked = cmds.group(empty=True, world=True,
                               name=name + "_baked_GRP")
            for geo in meshes:
                copy = cmds.duplicate(geo, name=route_mod.short_name(geo)
                                      .replace("_geo", "_baked"))[0]
                copy = cmds.parent(copy, baked)[0]
                for channel in ("t", "r", "s"):  # locked on the live rig
                    cmds.setAttr(copy + "." + channel, lock=False)
                for node in [copy] + (cmds.listRelatives(
                        copy, shapes=True, fullPath=True) or []):
                    nodes.untag(node)
            self.delete()
        return cmds.ls(baked, long=True)[0]

    def delete(self):
        """Remove every node this build created."""
        count = nodes.delete_cable(self.cable_id)
        self.group = None
        return count

    # -- for subclasses -----------------------------------------------------
    def _check_dependencies(self):
        """Raise CableToolError if a plugin the mode needs is missing."""

    def _build_network(self, name, anchors, settings):
        """Create the mode's nodes under self.group."""
        raise NotImplementedError

    # -- shared build steps ---------------------------------------------------
    def _next_name(self):
        index = 1
        while cmds.objExists("{0}_{1:02d}_GRP".format(self.noun, index)):
            index += 1
        return "{0}_{1:02d}".format(self.noun, index)

    def _add_setting_attrs(self, settings):
        for key in self.setting_keys():
            spec = DEFAULTS[key]
            plug = self.group + "." + key
            if spec["type"] == "bool":
                cmds.addAttr(self.group, longName=key, niceName=spec["label"],
                             attributeType="bool",
                             defaultValue=spec["default"])
            else:
                low, high = spec["field"]
                cmds.addAttr(self.group, longName=key, niceName=spec["label"],
                             attributeType=("long" if spec["type"] == "int"
                                            else "double"),
                             minValue=low, maxValue=high,
                             defaultValue=spec["default"])
            cmds.setAttr(plug, settings[key])
            if spec["rebuild"]:
                # Stored for Load / Rebuild but kept out of the Channel
                # Box: changing it there would not rebuild the network.
                cmds.setAttr(plug, keyable=False, channelBox=False)
            else:
                cmds.setAttr(plug, keyable=True)

    def _record_extras(self, extras):
        for key, _label, _tip, _section in self.extras:
            cmds.addAttr(self.group, longName=key, attributeType="message")
            node = extras.get(key)
            if node:
                if not cmds.objExists(node):
                    raise CableToolError(tr(
                        "'{0}' is not in the scene; pick it again.").format(
                            node))
                cmds.connectAttr(node + ".message",
                                 self.group + "." + key)

    def _record_anchors(self, anchors):
        cmds.addAttr(self.group, longName=ANCHORS_ATTR,
                     attributeType="message", multi=True)
        cmds.addAttr(self.group, longName=COMPONENTS_ATTR, dataType="string",
                     multi=True)
        for i, anchor in enumerate(anchors):
            node, kind, index = route_mod.split(anchor)
            cmds.connectAttr(node + ".message",
                             "{0}.{1}[{2}]".format(self.group, ANCHORS_ATTR,
                                                   i))
            cmds.setAttr("{0}.{1}[{2}]".format(self.group, COMPONENTS_ATTR, i),
                         "" if kind is None else "{0}[{1}]".format(kind,
                                                                   index),
                         type="string")


class PlannedGenerator(BaseGenerator):
    """A mode that is listed in the dropdown but not built yet. Building
    raises a friendly error instead of doing anything."""

    available = False

    def _build_network(self, name, anchors, settings):
        raise CableToolError(tr("{0} mode isn't built yet.").format(
            tr(self.label)))
