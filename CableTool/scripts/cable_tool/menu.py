"""The Cable Tool menu in Maya's main menu bar. Built by the plugin on
load and again when the interface language changes."""

import os

import maya.cmds as cmds

from cable_tool.i18n import tr

MENU_NAME = "CableToolMenu"
# scripts/cable_tool/ -> the module's icons/ folder.
ICON = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(
    __file__)), "..", "..", "icons", "cableTool.png"))


def build():
    if cmds.about(batch=True) or not cmds.window("MayaWindow", exists=True):
        return
    remove()
    cmds.menu(MENU_NAME, label=tr("Cable Tool"), parent="MayaWindow",
              tearOff=True)
    cmds.menuItem(label=tr("Open Cable Tool"),
                  command="import maya.cmds; maya.cmds.cableTool()",
                  sourceType="python", image=ICON,
                  annotation=tr("Open the Cable Tool window."))
    cmds.menuItem(divider=True)
    cmds.menuItem(label=tr("Reload"),
                  command="import cable_tool.dev; cable_tool.dev.reload_tool()",
                  sourceType="python",
                  annotation=tr("Reload the tool's Python code "
                                "(development)."))
    cmds.menuItem(label=tr("About"),
                  command="import cable_tool.ui; cable_tool.ui.about()",
                  sourceType="python")


def remove():
    if cmds.menu(MENU_NAME, exists=True):
        cmds.deleteUI(MENU_NAME, menu=True)
