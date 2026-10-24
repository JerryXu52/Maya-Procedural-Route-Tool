"""Demo scenes for the Cable Tool. Run inside Maya:

    exec(open("/path/to/tests/demo_scene.py").read())

builds the showcase (utility poles and a cyberpunk alley). For the peer
run's scene (cone, cube, sphere and cylinder), call demo("peer") after.
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


def _start():
    cmds.file(new=True, force=True)
    if not cmds.pluginInfo("cableTool", query=True, loaded=True):
        cmds.loadPlugin(PLUGIN)


def _build(anchors, preset=None, **settings):
    from cable_tool.generators import CableGenerator
    from cable_tool.route import Route
    values = CableGenerator.preset(preset) if preset else {}
    values.update(settings)
    cable = CableGenerator()
    cable.build(Route(anchors[0], anchors[-1], anchors[1:-1]), values)
    return cable


def _locator(name, pos):
    loc = cmds.spaceLocator(name=name)[0]
    cmds.xform(loc, worldSpace=True, translation=pos)
    cmds.setAttr(loc + ".localScale", 0.3, 0.3, 0.3)
    return loc


def _face_near(mesh, point):
    """The mesh face closest to a world point, as an anchor name."""
    probe = cmds.createNode("closestPointOnMesh")
    shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
    # outMesh + worldMatrix: fed worldMesh, the node ignores the transform.
    cmds.connectAttr(shape + ".outMesh", probe + ".inMesh")
    cmds.connectAttr(mesh + ".worldMatrix[0]", probe + ".inputMatrix")
    cmds.setAttr(probe + ".inPosition", *point)
    face = cmds.getAttr(probe + ".closestFaceIndex")
    cmds.delete(probe)
    return "{0}.f[{1}]".format(mesh, face)


def utility_poles(x0=-30.0):
    """Four poles with crossarms; the wires rest on the middle crossarms
    and end on the outer ones."""
    arms = []
    for i, (dx, height, lean) in enumerate(((0, 9.0, 0), (12, 9.4, 2),
                                            (24, 8.8, -1), (36, 9.2, 1))):
        pole = cmds.polyCylinder(name="pole{0}".format(i + 1), radius=0.18,
                                 height=height, subdivisionsX=12)[0]
        cmds.xform(pole, worldSpace=True,
                   translation=(x0 + dx, height / 2.0, lean * 0.3))
        arm = cmds.polyCube(name="crossarm{0}".format(i + 1), width=0.25,
                            height=0.2, depth=3.0)[0]
        cmds.xform(arm, worldSpace=True,
                   translation=(x0 + dx, height - 0.5, lean * 0.3))
        arms.append(arm)
    lines = _build(arms, "Utility Line")
    lower = []
    for i, arm in enumerate(arms):
        pos = cmds.xform(arm, query=True, worldSpace=True, translation=True)
        lower.append(_locator("drop{0}".format(i + 1),
                              (pos[0] + 0.2, pos[1] - 1.6, pos[2])))
    service = _build(lower, "Utility Line", wireCount=2, spread=0.5,
                     radius=0.06, sag=0.08, seed=7)
    return [lines, service]


def cyberpunk_alley(x0=12.0):
    """Two buildings across an alley, strung with tangled bundles plugged
    into wall faces; one bundle is draped over a pipe that spans the
    alley."""
    left = cmds.polyCube(name="buildingA", width=6, height=20, depth=14,
                         subdivisionsHeight=10, subdivisionsDepth=7)[0]
    cmds.xform(left, worldSpace=True, translation=(x0, 10, 0))
    right = cmds.polyCube(name="buildingB", width=6, height=24, depth=14,
                          subdivisionsHeight=12, subdivisionsDepth=7)[0]
    cmds.xform(right, worldSpace=True, translation=(x0 + 14, 12, 0))
    beam = cmds.polyCylinder(name="pipeBeam", radius=0.25, height=8,
                             subdivisionsX=12)[0]
    cmds.xform(beam, worldSpace=True, translation=(x0 + 7, 12.5, 1.0),
               rotation=(0, 0, 90))

    wall_a, wall_b = x0 + 3.0, x0 + 11.0
    runs = (
        (((wall_a, 16.0, -4.0), (wall_b, 15.0, 2.5)), 14, 3),
        (((wall_a, 13.5, 3.5), (wall_b, 17.5, -3.0)), 10, 11),
        (((wall_a, 18.5, 1.0), (wall_b, 19.0, -5.0)), 6, 23),
    )
    cables = []
    for (a, b), wires, seed in runs:
        # Wall faces are ports: the wires plug in and fan out over them.
        cables.append(_build([_face_near(left, a), _face_near(right, b)],
                             "Cyberpunk Tangle", wireCount=wires, seed=seed))
    draped = _build([_face_near(left, (wall_a, 11.0, 0.5)), beam,
                     _face_near(right, (wall_b, 10.5, 1.5))],
                    "Cyberpunk Tangle", wireCount=8, seed=42, sag=0.1)
    cables.append(draped)
    # A service pipe across the alley, held by ring clamps.
    cables.append(_build([_face_near(left, (wall_a, 7.0, -5.0)),
                          _face_near(right, (wall_b, 7.5, -5.0))],
                         "Single Pipe", radius=0.2, clampCount=3,
                         clampSize=1.1, sag=0.03))
    return cables


def peer_run():
    """The peer run's scene: cone, cube, sphere, cylinder."""
    cone = cmds.polyCone(name="cone", radius=1, height=2)[0]
    cmds.xform(cone, worldSpace=True, translation=(-8, 1, 0))
    cube = cmds.polyCube(name="cube", width=2, height=2, depth=2)[0]
    cmds.xform(cube, worldSpace=True, translation=(-3, 4, 4))
    sphere = cmds.polySphere(name="sphere", radius=1)[0]
    cmds.xform(sphere, worldSpace=True, translation=(3, 3, -3))
    cylinder = cmds.polyCylinder(name="cylinder", radius=1, height=2)[0]
    cmds.xform(cylinder, worldSpace=True, translation=(8, 1, 0))

    main = _build([cone, cube, sphere, cylinder], radius=0.15, twist=90.0)
    # More cables sharing the same objects: they used to meet at each
    # object's pivot and cross there.
    _build([cone, cylinder], radius=0.1)
    _build([cube, cylinder], radius=0.1)
    return [main]


def demo(scene="showcase"):
    _start()
    from cable_tool import ui
    if scene == "peer":
        cables = peer_run()
    else:
        cables = utility_poles() + cyberpunk_alley()

    window = ui.show()
    cmds.select(cables[0].group)
    window.on_load_selected()
    cmds.select(clear=True)
    for panel in cmds.getPanel(type="modelPanel") or []:
        cmds.modelEditor(panel, edit=True, displayAppearance="smoothShaded",
                         wireframeOnShaded=False)
    cmds.viewFit(allObjects=True)
    print("[CableTool] Demo ready: move any anchor and the cables follow.")
    return cables


if __name__ in ("__main__", "builtins"):
    demo()
