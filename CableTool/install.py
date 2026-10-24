"""Cable Tool installer. Drag this file into Maya's viewport.

It writes CableTool.mod into your Maya modules folder, pointing at this
folder, so Maya finds the plugin, scripts and icons from now on; loads
the plugin and sets it to auto-load; and adds a Cable Tool button to the
current shelf. Nothing is copied: keep this folder where it is (or drag
the installer in again after moving it).
"""

import os
import sys

import maya.cmds as cmds
import maya.mel as mel

MODULE_NAME = "CableTool"
PLUGIN_NAME = "cableTool"


def module_text(root, version):
    """The .mod file: one module, rooted at this folder."""
    return "+ {0} {1} {2}\n".format(MODULE_NAME, version, root)


def modules_folder():
    """The user's modules folder for this Maya version."""
    app_dir = os.environ.get("MAYA_APP_DIR") or cmds.internalVar(
        userAppDir=True)
    return os.path.join(app_dir, "modules")


def install(root=None, modules=None):
    """Install the module rooted at root (this file's folder). Returns the
    .mod file's path."""
    root = os.path.abspath(root or os.path.dirname(__file__))
    scripts = os.path.join(root, "scripts")
    if scripts not in sys.path:  # for this session; the .mod does it after
        sys.path.insert(0, scripts)
    from cable_tool.config import VERSION

    modules = modules or modules_folder()
    if not os.path.isdir(modules):
        os.makedirs(modules)
    mod_file = os.path.join(modules, MODULE_NAME + ".mod")
    with open(mod_file, "w") as handle:
        handle.write(module_text(root, VERSION))

    plugin = os.path.join(root, "plug-ins", PLUGIN_NAME + ".py")
    if not cmds.pluginInfo(PLUGIN_NAME, query=True, loaded=True):
        cmds.loadPlugin(plugin)
    cmds.pluginInfo(plugin, edit=True, autoload=True)
    if not cmds.about(batch=True):
        add_shelf_button(os.path.join(root, "icons", "cableTool.png"))
    return mod_file


def add_shelf_button(icon):
    """A Cable Tool button on the current shelf (once)."""
    top = mel.eval("$tmp = $gShelfTopLevel")
    shelf = cmds.tabLayout(top, query=True, selectTab=True)
    for button in cmds.shelfLayout(shelf, query=True, childArray=True) or []:
        if cmds.shelfButton(button, query=True, exists=True) and \
                cmds.shelfButton(button, query=True,
                                 label=True) == "Cable Tool":
            return button
    return cmds.shelfButton(parent=shelf, label="Cable Tool",
                            annotation="Open the Cable Tool window.",
                            image=icon, imageOverlayLabel="",
                            sourceType="python",
                            command="import maya.cmds; maya.cmds.cableTool()")


def onMayaDroppedPythonFile(*_args):
    """Maya calls this when the file is dragged into the viewport."""
    try:
        mod_file = install()
    except Exception as err:  # tell the artist, don't leave a traceback
        cmds.confirmDialog(title="Cable Tool", button=["OK"],
                           message="Install failed: {0}".format(err))
        raise
    cmds.confirmDialog(
        title="Cable Tool", button=["OK"],
        message="Cable Tool is installed.\n\nOpen it from the Cable Tool "
                "menu or the new shelf button. It loads automatically from "
                "now on.\n\nModule file: {0}".format(mod_file))
    cmds.cableTool()
