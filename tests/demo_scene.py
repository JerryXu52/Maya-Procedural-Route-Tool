"""Demo scenes for the Cable Tool. Run inside Maya:

    exec(open("/path/to/tests/demo_scene.py").read())

builds the showcase (utility poles and a cyberpunk alley). Then call
demo("fence") for the fence showcase (a farm on rolling ground),
demo("road") for the road showcase (roads over hilly countryside), or
demo("peer") for the peer run's scene (cone, cube, sphere and cylinder).
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


def _fence(anchors, preset=None, ground=None, **settings):
    from cable_tool.generators import FenceGenerator
    from cable_tool.route import Route
    values = FenceGenerator.preset(preset) if preset else {}
    values.update(settings)
    fence = FenceGenerator()
    fence.build(Route(anchors[0], anchors[-1], anchors[1:-1]), values,
                extras={"ground": ground})
    return fence


def _paint(name, colour, nodes):
    shader = cmds.ls(name)
    if not shader:
        shader = [cmds.shadingNode("lambert", asShader=True, name=name)]
        cmds.setAttr(shader[0] + ".color", *colour, type="double3")
        group = cmds.sets(renderable=True, noSurfaceShader=True, empty=True,
                          name=name + "SG")
        cmds.connectAttr(shader[0] + ".outColor", group + ".surfaceShader")
    group = cmds.listConnections(shader[0] + ".outColor", type="shadingEngine")
    for node in nodes:
        cmds.sets(node, edit=True, forceElement=group[0])


def _parts(fence, *names):
    return [cmds.ls("{0}|*_{1}_geo".format(fence.group, name), long=True)[0]
            for name in names]


def rolling_ground():
    """A 70 x 44 field of gentle hills."""
    import math
    ground = cmds.polyPlane(name="ground", width=70, height=44,
                            subdivisionsX=70, subdivisionsY=44)[0]
    count = cmds.polyEvaluate(ground, vertex=True)
    for i in range(count):
        x, _y, z = cmds.pointPosition("{0}.vtx[{1}]".format(ground, i),
                                      world=True)
        y = (1.3 * math.sin(x * 0.13) + 0.9 * math.cos(z * 0.21 + 0.4)
             + 0.25 * math.sin(x * 0.5 + z * 0.35))
        cmds.xform("{0}.vtx[{1}]".format(ground, i), worldSpace=True,
                   translation=(x, y, z))
    _paint("grassMtl", (0.32, 0.45, 0.22), [ground])
    return ground


def farm():
    """A picket-fenced yard with a gate, a ranch fence curving over the
    hill, a wire fence with a farm gate along the back, a privacy fence
    and a pipe railing on a concrete wall. Every fence stands on the rolling ground except
    the railing, which rides the wall."""
    ground = rolling_ground()
    fences = []

    # The yard: from one gate post round three corners to the other, and
    # a gate back across the gap (Gate After Anchor = the last anchor).
    house = cmds.polyCube(name="house", width=5, height=3.5, depth=4)[0]
    cmds.xform(house, worldSpace=True, translation=(-17, 1.4, 0))
    _paint("houseMtl", (0.75, 0.62, 0.5), [house])
    yard = [_locator("yard{0}".format(i), (x, 3, z)) for i, (x, z) in
            enumerate(((-14, -6), (-9, -6), (-9, 6), (-24, 6), (-24, -6),
                       (-15.3, -6)))]
    picket = _fence(yard, "Picket Fence", ground, fenceFlip=1,
                    gateAnchor=len(yard), gateSwing=-40.0)
    _paint("whitePaintMtl", (0.9, 0.9, 0.86),
           _parts(picket, "posts", "rails", "pickets", "gate"))
    fences.append(picket)

    # A ranch fence curving over the hill.
    ranch = _fence([_locator("ranch{0}".format(i), (x, 3, z)) for i, (x, z)
                    in enumerate(((-4, -14), (4, -9), (12, -13), (22, -8)))],
                   "Ranch Rail", ground, fenceCurve=1.0, wear=0.3)
    _paint("woodMtl", (0.45, 0.3, 0.18), _parts(ranch, "posts", "rails"))
    fences.append(ranch)

    # A sagging wire fence along the back of the field, with a double
    # tubular farm gate between anchors 2 and 3, standing open.
    wire = _fence([_locator("wire{0}".format(i), (x, 3, 15)) for i, x in
                   enumerate((-30, -2, 2, 30))], "Wire Fence", ground,
                  gateAnchor=2, gateDouble=1, gateSwing=-60.0)
    _paint("oldWoodMtl", (0.36, 0.3, 0.24), _parts(wire, "posts"))
    _paint("steelMtl", (0.55, 0.57, 0.6), _parts(wire, "rails", "gate"))
    fences.append(wire)

    # A privacy fence screening the yard's back.
    privacy = _fence([_locator("privacy{0}".format(i), (x, 3, z)) for i, (x, z)
                      in enumerate(((-6, 9), (6, 10)))], "Privacy Fence",
                     ground)
    _paint("cedarMtl", (0.6, 0.4, 0.26),
           _parts(privacy, "posts", "rails", "pickets"))
    fences.append(privacy)

    # A pipe railing on a concrete wall: its anchors ride the wall.
    wall = cmds.polyCube(name="wall", width=10, height=3, depth=1.2)[0]
    cmds.xform(wall, worldSpace=True, translation=(24, 2.2, 2))
    _paint("concreteMtl", (0.6, 0.6, 0.58), [wall])
    ends = [_locator("rail{0}".format(i), (x, 3.7, 2)) for i, x in
            enumerate((19.6, 28.4))]
    for end in ends:
        cmds.parent(end, wall)
    railing = _fence(ends, "Pipe Railing")
    _paint("steelMtl", None, _parts(railing, "posts", "rails"))
    fences.append(railing)
    return fences


def _road(anchors, preset=None, ground=None, material=None, **settings):
    from cable_tool.generators import RoadGenerator
    from cable_tool.route import Route
    values = RoadGenerator.preset(preset) if preset else {}
    values.update(settings)
    road = RoadGenerator()
    road.build(Route(anchors[0], anchors[-1], anchors[1:-1]), values,
               extras={"ground": ground, "roadMaterial": material})
    return road


def hills():
    """A 320 x 240 stretch of countryside: hills up to about 6 m."""
    import math
    ground = cmds.polyPlane(name="hills", width=320, height=240,
                            subdivisionsX=80, subdivisionsY=60)[0]
    points = cmds.xform(ground + ".vtx[*]", query=True, worldSpace=True,
                        translation=True)
    for i in range(len(points) // 3):
        x, z = points[3 * i], points[3 * i + 2]
        y = (3.0 * math.sin(x * 0.03) + 2.5 * math.cos(z * 0.045 + 0.4)
             + 0.6 * math.sin(x * 0.09 + z * 0.07))
        cmds.xform("{0}.vtx[{1}]".format(ground, i), worldSpace=True,
                   translation=(x, y, z))
    _paint("meadowMtl", (0.30, 0.42, 0.18), [ground])
    return ground


def lane_texture(settings, path, size=(512, 1024)):
    """Paint a road texture for the road's UV layout: U across the paved
    width, V one dash cycle along. Shows that a painted texture lines up
    with Road mode's lanes. Returns path."""
    from PySide6 import QtGui
    from cable_tool import road
    _columns, half, bounds = road.road_columns(settings)
    width, height = size
    image = QtGui.QImage(width, height, QtGui.QImage.Format.Format_RGB32)
    image.fill(QtGui.QColor(58, 58, 60))
    painter = QtGui.QPainter(image)
    cycle = settings["dashLength"] + settings["dashGap"]
    for x, line, dashed, centre in road.marking_lines(settings, bounds):
        colour = (QtGui.QColor(222, 160, 20) if centre
                  and settings["yellowCentre"] else QtGui.QColor(235, 235,
                                                                 230))
        left = (x - line * 0.5 + half) / (2 * half) * width
        span = max(line / (2 * half) * width, 2.0)
        # V = 0 is the bottom of the image; a dash starts at V = 0.
        top = height * (1.0 - settings["dashLength"] / cycle) if dashed \
            else 0.0
        painter.fillRect(int(round(left)), int(top), int(round(span)),
                         int(height - top), colour)
    painter.end()
    image.save(path)
    return path


def _textured(name, image):
    shader = cmds.shadingNode("standardSurface", asShader=True, name=name)
    texture = cmds.shadingNode("file", asTexture=True, name=name + "File")
    cmds.setAttr(texture + ".fileTextureName", image, type="string")
    place = cmds.shadingNode("place2dTexture", asUtility=True)
    cmds.connectAttr(place + ".outUV", texture + ".uvCoord")
    cmds.connectAttr(place + ".outUvFilterSize", texture + ".uvFilterSize")
    cmds.connectAttr(texture + ".outColor", shader + ".baseColor")
    cmds.setAttr(shader + ".specularRoughness", 0.7)
    return shader


def countryside():
    """Four roads over the hills: a country road, a highway painted by
    its own texture (Road Material) instead of modelled markings, a city
    street with sidewalks and a gravel track that closes into a loop."""
    from cable_tool.generators import RoadGenerator
    ground = hills()

    def route(prefix, points):
        return [_locator("{0}{1}".format(prefix, i), (x, 0.0, z))
                for i, (x, z) in enumerate(points)]

    country = _road(route("country", [(-150, -70), (-95, -35), (-55, -75),
                                      (-5, -40), (55, -80), (150, -45)]),
                    "Country Road", ground)

    highway = RoadGenerator.preset("Highway")
    highway["markings"] = 0
    image = lane_texture(highway, os.path.join(
        cmds.internalVar(userTmpDir=True), "highway_lanes.png"))
    material = _textured("highwayLanesMtl", image)
    roads = [country,
             _road(route("highway", [(-155, 85), (-60, 100), (40, 70),
                                     (155, 90)]),
                   ground=ground, material=material, **highway)]
    roads.append(_road(route("street", [(10, -10), (70, -2), (140, -14)]),
                       "City Street", ground))
    track = route("track", [(-105, 5), (-70, -8), (-35, 10), (-45, 40),
                            (-90, 38)])
    roads.append(_road(track + [track[0]], "Gravel Track", ground))
    return roads


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
    elif scene == "fence":
        cables = farm()
    elif scene == "road":
        cables = countryside()
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
