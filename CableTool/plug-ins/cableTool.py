"""Cable Tool plugin entry point.

Kept deliberately thin: it registers the `cableTool` command and the
`cableToolSolver` node, adds the Cable Tool menu and makes sure the
`cable_tool` package can be imported.
All real work lives in scripts/cable_tool.

Load it from Windows > Settings/Preferences > Plug-in Manager.
"""

import os
import sys

import maya.api.OpenMaya as om
import maya.cmds as cmds

VENDOR = "JerryXu52"
VERSION = "0.5.0"
MENU_NAME = "CableToolMenu"
_PLUGIN_DIR = ""


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


def _build_menu():
    if cmds.about(batch=True) or not cmds.window("MayaWindow", exists=True):
        return
    _remove_menu()
    cmds.menu(MENU_NAME, label="Cable Tool", parent="MayaWindow",
              tearOff=True)
    cmds.menuItem(label="Open Cable Tool",
                  command="import maya.cmds; maya.cmds.cableTool()",
                  sourceType="python", image=_icon(),
                  annotation="Open the Cable Tool window.")
    cmds.menuItem(divider=True)
    cmds.menuItem(label="Reload",
                  command="import cable_tool.dev; cable_tool.dev.reload_tool()",
                  sourceType="python",
                  annotation="Reload the tool's Python code (development).")
    cmds.menuItem(label="About",
                  command="import cable_tool.ui; cable_tool.ui.about()",
                  sourceType="python")


def _icon():
    # Next to plug-ins/ in the module; Maya also finds it by name once the
    # module's icons/ folder is on XBMLANGPATH.
    return os.path.normpath(os.path.join(_PLUGIN_DIR, "..", "icons",
                                         "cableTool.png"))


def _remove_menu():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)


def initializePlugin(mobject):
    global _PLUGIN_DIR
    plugin = om.MFnPlugin(mobject, VENDOR, VERSION, "Any")
    _PLUGIN_DIR = plugin.loadPath()
    _add_scripts_path(_PLUGIN_DIR)
    plugin.registerCommand(CableToolCommand.NAME, CableToolCommand.creator)
    from cable_tool import solver
    plugin.registerNode(solver.NODE_NAME, solver.NODE_ID,
                        solver.CableSolverNode.creator,
                        solver.CableSolverNode.initialize)

    # Sweep Mesh is a dependency. If it won't load, the plugin still loads
    # and the window reports a clear error when you try to build.
    try:
        cmds.loadPlugin("sweep", quiet=True)
    except RuntimeError:
        om.MGlobal.displayWarning(
            "Cable Tool: could not load the 'sweep' plugin; cables cannot be "
            "built until it is enabled.")

    _build_menu()


def uninitializePlugin(mobject):
    plugin = om.MFnPlugin(mobject)
    try:
        from cable_tool import ui
        ui.close()
    except Exception:
        pass
    _remove_menu()
    plugin.deregisterCommand(CableToolCommand.NAME)
    from cable_tool import solver
    plugin.deregisterNode(solver.NODE_ID)
