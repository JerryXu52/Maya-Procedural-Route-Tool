"""Mode registry. The UI builds its Mode dropdown and panels from
GENERATORS, and Load / Delete Selected find a build's generator by the
mode stored on its group, so adding a mode means adding it here."""

import maya.cmds as cmds

from cable_tool import nodes
from cable_tool.config import MODE_ATTR
from cable_tool.generators.cable import CableGenerator
from cable_tool.generators.fence import FenceGenerator
from cable_tool.generators.planned import RoadGenerator

# Dropdown order.
GENERATORS = (CableGenerator, FenceGenerator, RoadGenerator)


def get(mode):
    for generator in GENERATORS:
        if generator.mode == mode:
            return generator
    raise KeyError(mode)


def from_node(node):
    """The generator for whichever build owns node, in any mode, or
    None if node isn't part of one."""
    group = nodes.cable_group_from(node)
    if group is None:
        return None
    try:
        return get(cmds.getAttr(group + "." + MODE_ATTR))(group)
    except KeyError:  # built by a newer version with more modes
        return None
