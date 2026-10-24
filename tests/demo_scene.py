"""Demo scene that recreates the peer run: a cone, cube, sphere and
cylinder picked as start, waypoints and end, with Twist turned up and
several cables sharing the same objects. Run it inside Maya:

    exec(open("/path/to/tests/demo_scene.py").read())

or launch Maya with it (see README, Try it).
"""

import os

import maya.cmds as cmds

try:
    HERE = os.path.dirname(os.path.abspath(__file__))
except NameError:  # exec'd from the Script Editor
    HERE = os.path.join(os.path.expanduser("~"), "Claude",
                        "Maya-Procedural-Route-Tool", "tests")
PLUGIN = os.path.normpath(os.path.join(HERE, "..", "CableTool", "plug-ins",
                                       "cableTool.py"))


def demo():
    cmds.file(new=True, force=True)
    if not cmds.pluginInfo("cableTool", query=True, loaded=True):
        cmds.loadPlugin(PLUGIN)
    from cable_tool import ui
    from cable_tool.generators import CableGenerator
    from cable_tool.route import Route

    cone = cmds.polyCone(name="cone", radius=1, height=2)[0]
    cmds.xform(cone, worldSpace=True, translation=(-8, 1, 0))
    cube = cmds.polyCube(name="cube", width=2, height=2, depth=2)[0]
    cmds.xform(cube, worldSpace=True, translation=(-3, 4, 4))
    sphere = cmds.polySphere(name="sphere", radius=1)[0]
    cmds.xform(sphere, worldSpace=True, translation=(3, 3, -3))
    cylinder = cmds.polyCylinder(name="cylinder", radius=1, height=2)[0]
    cmds.xform(cylinder, worldSpace=True, translation=(8, 1, 0))

    main = CableGenerator()
    main.build(Route(cone, cylinder, [cube, sphere]),
               {"radius": 0.15, "twist": 90.0, "sides": 8})
    # More cables sharing the same objects: they used to meet at each
    # object's pivot and cross there.
    CableGenerator().build(Route(cone, cylinder), {"radius": 0.1})
    CableGenerator().build(Route(cube, cylinder), {"radius": 0.1})

    window = ui.show()
    cmds.select(main.group)
    window.on_load_selected()
    cmds.select(clear=True)
    for panel in cmds.getPanel(type="modelPanel") or []:
        cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded",
                         wireframeOnShaded=True)
    cmds.viewFit(allObjects=True)
    print("[CableTool] Demo ready: move the cone, cube, sphere or cylinder "
          "and the cables follow.")


demo()
