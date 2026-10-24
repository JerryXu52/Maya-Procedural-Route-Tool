"""Cable Tool plugin entry point.

Kept deliberately thin: it registers the `cableTool` command and the
`cableToolSolver` and `fenceToolBuilder` nodes, adds the Cable Tool menu (cable_tool.menu) and
makes sure the `cable_tool` package can be imported.
All real work lives in scripts/cable_tool.

Load it from Windows > Settings/Preferences > Plug-in Manager.
"""

import os
import sys

import maya.api.OpenMaya as om
import maya.cmds as cmds

VENDOR = "JerryXu52"
VERSION = "0.7.0"


def maya_useNewAPI():
    """Tells Maya this plugin uses Python API 2.0."""


def _add_scripts_path(plugin_dir):
    # When installed as a module, Maya already puts scripts/ on the path.
    # When loaded by browsing to this file in the Plug-in Manager it does
    # not, so add the sibling scripts/ folder ourselves.
    scripts = os.path.normpath(os.path.join(plugin_dir, "..", "scripts"))
    if os.path.isdir(scripts) and scripts not in sys.path:
        sys.path.insert(0, scripts)


class CableToolCommand(om.MPxCommand):
    """`cableTool` opens (or raises) the Cable Tool window."""

    NAME = "cableTool"

    @staticmethod
    def creator():
        return CableToolCommand()

    def doIt(self, args):
        from cable_tool import ui
        ui.show()

    def isUndoable(self):
        return False


def initializePlugin(mobject):
    plugin = om.MFnPlugin(mobject, VENDOR, VERSION, "Any")
    _add_scripts_path(plugin.loadPath())
    plugin.registerCommand(CableToolCommand.NAME, CableToolCommand.creator)
    from cable_tool import solver
    plugin.registerNode(solver.NODE_NAME, solver.NODE_ID,
                        solver.CableSolverNode.creator,
                        solver.CableSolverNode.initialize)
    from cable_tool import fence
    plugin.registerNode(fence.NODE_NAME, fence.NODE_ID,
                        fence.FenceBuilderNode.creator,
                        fence.FenceBuilderNode.initialize)

    # Sweep Mesh is a dependency. If it won't load, the plugin still loads
    # and the window reports a clear error when you try to build.
    try:
        cmds.loadPlugin("sweep", quiet=True)
    except RuntimeError:
        om.MGlobal.displayWarning(
            "Cable Tool: could not load the 'sweep' plugin; cables cannot be "
            "built until it is enabled.")

    from cable_tool import menu
    menu.build()


def uninitializePlugin(mobject):
    plugin = om.MFnPlugin(mobject)
    try:
        from cable_tool import ui
        ui.close()
    except Exception:
        pass
    from cable_tool import menu
    menu.remove()
    plugin.deregisterCommand(CableToolCommand.NAME)
    from cable_tool import fence, solver
    plugin.deregisterNode(solver.NODE_ID)
    plugin.deregisterNode(fence.NODE_ID)
