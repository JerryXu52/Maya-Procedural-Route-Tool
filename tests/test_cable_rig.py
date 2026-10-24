"""Headless tests for the Cable Tool rig. Run with Maya's Python:

    /Applications/Autodesk/maya2026/Maya.app/Contents/bin/mayapy tests/test_cable_rig.py

Each test starts from a new scene. Exits non-zero if anything fails.
The window is tested separately in test_ui.py.
"""

import os
import sys
import traceback

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "..", "CableTool", "plug-ins", "cableTool.py")

import maya.standalone  # noqa: E402
maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

TESTS = []


def test(func):
    TESTS.append(func)
    return func


def close(a, b, tol=1e-3):
    return all(abs(x - y) <= tol for x, y in zip(a, b))


def locator(name, pos):
    loc = cmds.spaceLocator(name=name)[0]
    cmds.xform(loc, worldSpace=True, translation=pos)
    return loc


def cv(shape, index):
    return cmds.pointPosition("{0}.cv[{1}]".format(shape, index), world=True)


def build(anchors, **settings):
    from cable_tool.route import Route
    from cable_tool.generators import CableGenerator
    cable = CableGenerator()
    cable.build(Route(anchors[0], anchors[-1], anchors[1:-1]), settings)
    return cable


def parts(cable):
    curve = cmds.ls(cable.group + "|*_crv", long=True)[0]
    curve_shape = cmds.listRelatives(curve, shapes=True, fullPath=True)[0]
    geo = cmds.ls(cable.group + "|*_geo", long=True)[0]
    return curve_shape, geo


def bbox(node):
    return cmds.exactWorldBoundingBox(node)


def curve_points(shape, steps=400):
    low = cmds.getAttr(shape + ".minValue")
    high = cmds.getAttr(shape + ".maxValue")
    return [cmds.pointOnCurve(shape, parameter=low + (high - low) * k / steps,
                              position=True) for k in range(steps + 1)]


def tightest_bend(shape, steps=400):
    """Smallest radius of curvature along the curve (0 = straight, which
    is skipped)."""
    low = cmds.getAttr(shape + ".minValue")
    high = cmds.getAttr(shape + ".maxValue")
    radii = [cmds.pointOnCurve(shape, parameter=low + (high - low) * k
                               / steps, curvatureRadius=True)
             for k in range(1, steps)]
    return min(r for r in radii if r > 1e-9)


def solver_of(cable, wire=0):
    """The Python object behind a wire's solver node."""
    import maya.api.OpenMaya as om
    name = cmds.ls("{0}_w{1:02d}_solver".format(cable.name, wire))[0]
    selection = om.MSelectionList()
    selection.add(name)
    return om.MFnDependencyNode(selection.getDependNode(0)).userNode()


# -------------------------------------------------------------------------
@test
def plugin_loads_and_registers_command():
    assert cmds.pluginInfo("cableTool", query=True, loaded=True)
    assert "cableTool" in (cmds.pluginInfo("cableTool", query=True,
                                           command=True) or [])
    assert "cableToolSolver" in (cmds.pluginInfo(
        "cableTool", query=True, dependNode=True) or [])
    assert cmds.pluginInfo("sweep", query=True, loaded=True)


@test
def ends_follow_anchors_live():
    a = locator("A", (0, 5, 0))
    b = locator("B", (10, 5, 0))
    cable = build([a, b], sag=0.2)
    shape, geo = parts(cable)

    def last():  # the solver's point count follows the cable's length
        return cv(shape, cmds.getAttr(shape + ".spans")
                  + cmds.getAttr(shape + ".degree") - 1)

    assert close(cv(shape, 0), (0, 5, 0))
    assert close(last(), (10, 5, 0))
    assert cmds.polyEvaluate(geo, face=True) > 0

    cmds.xform(b, worldSpace=True, translation=(12, 8, 3))
    assert close(last(), (12, 8, 3)), last()
    box = bbox(geo)
    assert box[3] > 11.8 and box[5] > 2.8, box


@test
def anchors_inside_moving_groups_still_follow():
    a = locator("A", (0, 0, 0))
    b = locator("B", (4, 0, 0))
    parent = cmds.group(b, name="mover")
    cable = build([a, b])
    shape, _geo = parts(cable)
    cmds.xform(parent, worldSpace=True, translation=(0, 3, 0))
    last = cmds.getAttr(shape + ".spans") + 2
    assert close(cv(shape, last), (4, 3, 0)), cv(shape, last)


@test
def sag_is_live_and_scales_with_length():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.0)
    shape, _geo = parts(cable)
    # Taut, but a real cable under its own weight never hangs dead
    # straight: the solver allows well under 0.1% stretch.
    assert min(p[1] for p in curve_points(shape)) > -0.2

    cable.update({"sag": 0.2})
    drop = -min(p[1] for p in curve_points(shape))
    assert abs(drop - 2.0) < 0.3, drop  # sag x horizontal length

    cmds.xform(b, worldSpace=True, translation=(20, 0, 0))  # double length
    longer = -min(p[1] for p in curve_points(shape))
    assert abs(longer / drop - 2.0) < 0.2, (drop, longer)


@test
def vertical_run_hangs_straight():
    # Sag follows horizontal reach: a vertical cable has none to sag.
    a = locator("A", (0, 10, 0))
    b = locator("B", (0, 0, 0))
    cable = build([a, b], sag=0.3)
    shape, _geo = parts(cable)
    worst = max(abs(p[0]) + abs(p[2]) for p in curve_points(shape))
    assert worst < 0.05, worst


@test
def lowest_point_sits_toward_the_lower_end():
    # A hanging cable between ends at different heights is lowest nearer
    # the lower end.
    a = locator("A", (0, 4, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.4)
    shape, _geo = parts(cable)
    points = curve_points(shape)
    lowest = min(points, key=lambda p: p[1])
    assert lowest[0] > 5.0, lowest


@test
def cable_keeps_its_length():
    # The solver may not stretch the cable to satisfy gravity or contact.
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    cmds.xform(cube, worldSpace=True, translation=(5, 0, 0))
    a = locator("A", (0, 1, 0))
    b = locator("B", (10, 1, 0))
    cable = build([a, cube, b], sag=0.2)
    parts(cable)  # evaluate
    node = solver_of(cable)
    import numpy as np
    actual = float(np.sum(np.linalg.norm(np.diff(node._last, axis=0),
                                         axis=1)))
    assert abs(actual / node._rest_len - 1.0) < 0.02, (actual,
                                                        node._rest_len)


@test
def shape_settings_drive_sweep_live():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.0, radius=0.1, sides=8, endCaps=0)
    _shape, geo = parts(cable)
    assert abs(bbox(geo)[5] - 0.1) < 0.01
    cable.update({"radius": 0.5})
    assert abs(bbox(geo)[5] - 0.5) < 0.05, bbox(geo)

    faces = cmds.polyEvaluate(geo, face=True)
    cable.update({"sides": 16})
    assert cmds.polyEvaluate(geo, face=True) == faces * 2

    # Group attributes are what the Channel Box shows, and they are wired.
    cmds.setAttr(cable.group + ".taper", 0.0)
    sweep = cmds.listConnections(cable.group + ".taper", destination=True)[0]
    assert cmds.getAttr(sweep + ".taper") == 0.0


@test
def tube_is_smooth_along_its_length():
    # Live check: Sweep Mesh's default put rings only at a few points, so
    # the tube was a chain of straight, creased pieces.
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], radius=0.1, sides=8, sag=0.2)
    _shape, geo = parts(cable)
    rings = cmds.polyEvaluate(geo, face=True) / 8
    assert rings > 40, rings  # a ring at least every diameter


@test
def uvs_tile_along_the_length_at_a_set_rate():
    # Instructor: UVs along the length, so a striped or ribbed texture
    # tiles correctly without hand fixing.
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.0, radius=0.1, uvRepeat=2.0)
    shape, geo = parts(cable)
    length = cmds.arclen(shape)
    (u_low, u_high), (v_low, v_high) = cmds.polyEvaluate(geo,
                                                         boundingBox2d=True)
    assert abs(v_high - 2.0 * length) < 0.05 * length, (v_high, length)
    # Square texels: around the tube U spans its circumference x repeat.
    circumference = 2 * 3.14159 * 0.1
    assert abs(u_high - 2.0 * circumference) < 0.1, u_high
    cmds.xform(b, worldSpace=True, translation=(20, 0, 0))  # live
    v_high = cmds.polyEvaluate(geo, boundingBox2d=True)[1][1]
    assert abs(v_high - 2.0 * cmds.arclen(shape)) < 1.0, v_high


@test
def end_caps_close_the_tube():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], endCaps=0, sides=8)
    _shape, geo = parts(cable)
    open_faces = cmds.polyEvaluate(geo, face=True)
    cable.update({"endCaps": 1})
    assert cmds.polyEvaluate(geo, face=True) > open_faces


@test
def twist_is_degrees_not_turns():
    # Peer run: Twist wrung the tube into pinched segments, because the
    # degrees from the UI went straight into Sweep Mesh, which counts
    # whole turns (90 became 90 full turns).
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.0, radius=0.5)
    _shape, geo = parts(cable)
    sweep = cmds.ls(cmds.listHistory(geo), type="sweepMeshCreator")[0]
    cable.update({"twist": 90.0})
    assert abs(cmds.getAttr(sweep + ".twist") - 0.25) < 1e-6, \
        cmds.getAttr(sweep + ".twist")
    cable.update({"twist": 360.0})
    assert abs(cmds.getAttr(sweep + ".twist") - 1.0) < 1e-6
    # A round tube stays round: no pinched, narrowed sections.
    box = bbox(geo)
    assert box[4] - box[1] > 0.9 and box[5] - box[2] > 0.9, box


@test
def waypoints_route_the_curve():
    a = locator("A", (0, 0, 0))
    w = locator("W", (5, 0, 5))
    b = locator("B", (10, 0, 0))
    cable = build([a, w, b], sag=0.0)
    shape, _geo = parts(cable)

    def gap():
        target = cmds.xform(w, query=True, worldSpace=True, translation=True)
        return min(sum((p - q) ** 2 for p, q in zip(point, target)) ** 0.5
                   for point in curve_points(shape, 800))

    assert gap() < 0.05, gap()
    cmds.xform(w, worldSpace=True, translation=(5, 4, 5))
    assert gap() < 0.05, gap()


@test
def draped_waypoint_is_wrapped_not_cut_through():
    # Live check: a cable routed through a box ran through its middle,
    # then cut through its walls; it now rests on top and wraps the edges.
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    cmds.xform(cube, worldSpace=True, translation=(0, 4, 0))
    a = locator("A", (-6, 1, 0))
    b = locator("B", (6, 2, 0))
    cable = build([a, cube, b], radius=0.15, sag=0.1)
    shape, _geo = parts(cable)
    points = curve_points(shape, 800)

    def clear_of_box(p):  # distance from the tube's center to the box
        return sum(max(abs(c - o) - 1.0, 0.0) ** 2
                   for c, o in zip(p, (0, 4, 0))) ** 0.5

    # The tube may graze a sharp edge (the curve between two simulated
    # points cuts the corner a little) but never cut into the box.
    nearest = min(clear_of_box(p) for p in points)
    assert nearest > 0.6 * 0.15, nearest
    top = max(points, key=lambda p: p[1])
    assert abs(top[1] - (5.0 + 0.15)) < 0.05, top  # resting on the top

    cable.update({"drape": 0})  # straight through the middle again
    assert any(abs(p[0]) < 0.05 and abs(p[1] - 4.0) < 0.05
               for p in curve_points(shape, 800))


@test
def mesh_ends_sit_on_the_surface_and_leave_outward():
    # Peer run: cables ended at each object's pivot, inside it, so several
    # cables met at one point and crossed there.
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    b = locator("B", (10, 0, 0))
    cable = build([cube, b], sag=0.1, leadOut=0.5)
    shape, _geo = parts(cable)
    assert close(cv(shape, 0), (1, 0, 0)), cv(shape, 0)
    low = cmds.getAttr(shape + ".minValue")
    tangent = cmds.pointOnCurve(shape, parameter=low, normalizedTangent=True)
    assert tangent[0] > 0.99, tangent  # straight out along the normal

    cmds.xform(cube, worldSpace=True, translation=(0, 5, 0))
    assert close(cv(shape, 0), (1, 4, 0)), cv(shape, 0)
    cmds.setAttr(cube + ".rotateZ", 90)  # normals follow the mesh live
    assert close(cv(shape, 0), (1, 4, 0)), cv(shape, 0)

    cable.update({"attach": 0})
    assert close(cv(shape, 0), (0, 5, 0)), cv(shape, 0)


@test
def cable_leaves_a_surface_without_folding():
    # Live checks: off a cone's side the cable first folded over itself,
    # then kinked where the straight lead-out met the hanging part. A
    # real cable can't bend much tighter than a few times its radius.
    cone = cmds.polyCone(radius=1, height=2, name="cone")[0]
    cmds.xform(cone, worldSpace=True, translation=(-8, 1, 0))
    w = locator("W", (-3, 4, 4))
    b = locator("B", (8, 1, 0))
    cable = build([cone, w, b], radius=0.15)
    shape, _geo = parts(cable)
    assert tightest_bend(shape) > 2 * 0.15, tightest_bend(shape)


@test
def vertex_end_is_a_port_that_follows_the_vertex():
    # A vertex is a port: the cable plugs in there and leaves along the
    # vertex normal, and stays on it when the mesh is edited.
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    b = locator("B", (10, 0, 0))
    corner = cube + ".vtx[1]"  # (1, -1, 1)
    cable = build([corner, b], sag=0.1, leadOut=0.5)
    shape, _geo = parts(cable)
    assert close(cv(shape, 0), (1, -1, 1)), cv(shape, 0)
    low = cmds.getAttr(shape + ".minValue")
    tangent = cmds.pointOnCurve(shape, parameter=low, normalizedTangent=True)
    normal = [c / 3 ** 0.5 for c in (1, -1, 1)]  # the corner's normal
    assert close(tangent, normal, 0.02), tangent

    cmds.move(0, -2, 0, corner, relative=True)  # edit the mesh
    assert close(cv(shape, 0), (1, -3, 1)), cv(shape, 0)


@test
def face_end_sits_at_its_center_along_its_normal():
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    cmds.xform(cube, worldSpace=True, translation=(0, 5, 0))
    b = locator("B", (10, 0, 0))
    cable = build([cube + ".f[1]", b], sag=0.1, leadOut=0.5)  # the top
    shape, _geo = parts(cable)
    assert close(cv(shape, 0), (0, 6, 0)), cv(shape, 0)
    low = cmds.getAttr(shape + ".minValue")
    tangent = cmds.pointOnCurve(shape, parameter=low, normalizedTangent=True)
    assert tangent[1] > 0.99, tangent  # straight up out of the top
    cmds.setAttr(cube + ".rotateZ", -90)  # the top now faces +x
    assert close(cv(shape, 0), (1, 5, 0)), cv(shape, 0)


@test
def face_waypoint_passes_just_off_the_face():
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    a = locator("A", (-6, 3, 0))
    b = locator("B", (6, 3, 0))
    cable = build([a, cube + ".f[1]", b], radius=0.1, sag=0.0)  # the top
    shape, _geo = parts(cable)
    target = (0, 1.1, 0)
    gap = min(sum((p - q) ** 2 for p, q in zip(point, target)) ** 0.5
              for point in curve_points(shape, 800))
    assert gap < 0.05, gap


@test
def bad_components_raise_friendly_errors():
    from cable_tool.config import CableToolError
    from cable_tool.route import Route
    cube = cmds.polyCube(name="box")[0]
    a = locator("A", (0, 0, 0))
    for bad in (cube + ".vtx[99]", cube + ".f[6]", a + ".vtx[0]"):
        try:
            Route(bad, cube).validate()
        except CableToolError:
            continue
        raise AssertionError("no error for " + bad)


@test
def components_survive_load_and_rebuild():
    from cable_tool.generators import CableGenerator
    cube = cmds.polyCube(name="box")[0]
    b = locator("B", (10, 0, 0))
    cable = build([cube + ".f[4]", b])
    found = CableGenerator.from_node(parts(cable)[1])
    route = found.read_route()
    assert route.start == "box.f[4]", route.start
    found.update({"wireCount": 2})  # rebuilds from the stored route
    shape = cmds.listRelatives(cmds.ls(found.group + "|*_crv",
                                       long=True)[0], shapes=True,
                               fullPath=True)[0]
    assert abs(cv(shape, 0)[0] - 0.5) < 1e-3, cv(shape, 0)  # still on +x


@test
def selection_order_includes_components():
    from cable_tool.route import selected_anchors
    cube = cmds.polyCube(name="box")[0]
    b = locator("B", (10, 0, 0))
    cmds.selectPref(trackSelectionOrder=True)
    cmds.select(clear=True)
    cmds.select(cube + ".f[4]")
    cmds.select(b, add=True)
    cmds.select(cube + ".e[0]", add=True)  # edges are not anchors
    anchors, ignored = selected_anchors()
    assert [a.split("|")[-1] for a in anchors] == ["box.f[4]", "B"], anchors
    assert len(ignored) == 1, ignored


@test
def wires_fan_out_across_a_face():
    # Several wires plugged into one wall face spread over the wall
    # instead of sticking out of it.
    wall = cmds.polyCube(width=1, height=10, depth=10, name="wall")[0]
    b = locator("B", (10, 5, 0))
    run = build([wall + ".f[4]", b], wireCount=6, spread=3.0,
                spreadRow=0, seed=2)
    starts = [cv(cmds.listRelatives(c, shapes=True, fullPath=True)[0], 0)
              for c in cmds.ls(run.group + "|*_crv", long=True)]
    assert all(abs(p[0] - 0.5) < 1e-3 for p in starts), starts  # on it
    spread = max(p[1] for p in starts) - min(p[1] for p in starts)
    assert spread > 0.5, starts  # and spread over it


@test
def several_wires_spread_and_repeat():
    a = locator("A", (0, 5, 0))
    b = locator("B", (10, 5, 0))
    run = build([a, b], wireCount=4, spread=2.0, spreadRow=1,
                slackVariation=0.0, thicknessVariation=0.0)
    curves = sorted(cmds.ls(run.group + "|*_crv", long=True))
    assert len(curves) == 4, curves
    starts = sorted(cv(cmds.listRelatives(c, shapes=True,
                                          fullPath=True)[0], 0)[2]
                    for c in curves)
    expected = [-1.0, -1.0 / 3, 1.0 / 3, 1.0]  # a row across Spread
    assert all(abs(z - e) < 1e-3 for z, e in zip(starts, expected)), starts

    # A cluster: random, but the same Seed always gives the same wires.
    run.update({"spreadRow": 0, "seed": 5})
    shape = cmds.listRelatives(curves[0], shapes=True, fullPath=True)[0]
    first = cv(shape, 0)
    run.update({"seed": 6})
    assert not close(cv(shape, 0), first)
    run.update({"seed": 5})
    assert close(cv(shape, 0), first)


@test
def wire_count_rebuilds_and_keeps_name():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b])
    name = cable.group.split("|")[-1]
    assert cable.update({"wireCount": 3}) == ["wireCount"]
    assert cable.exists()
    assert cable.group.split("|")[-1] == name
    assert len(cmds.ls(cable.group + "|*_crv")) == 3
    # Smoothness is live now (the solver re-samples), no rebuild needed.
    assert cable.update({"samples": 10}) == []


@test
def bake_leaves_plain_meshes_and_removes_the_rig():
    from cable_tool import nodes
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], wireCount=3, clampCount=2)
    cmds.flushUndo()
    baked = cable.bake()
    meshes = cmds.listRelatives(baked, children=True, fullPath=True)
    assert len(meshes) == 3 + 6, meshes  # wires and their clamps
    for mesh in meshes:
        shape = cmds.listRelatives(mesh, shapes=True, fullPath=True)[0]
        assert not cmds.listConnections(shape + ".inMesh")  # no history
        assert cmds.polyEvaluate(mesh, face=True) > 0
    assert not cmds.ls(type="cableToolSolver")  # the live rig is gone
    nodes.delete_all()  # and Clear All leaves the baked meshes alone
    assert all(cmds.objExists(m) for m in meshes)
    cmds.undo()  # Ctrl+Z gives the live run back
    cmds.undo()
    assert len(cmds.ls(type="cableToolSolver")) == 3


def clamps_of(cable):
    return sorted(c for c in cmds.ls(cable.group + "|*_clamp*", long=True)
                  if not c.endswith("_clampRing"))


@test
def clamps_ride_the_cable():
    # Instructor: hardware instanced along the length, following live.
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.2, radius=0.1, clampCount=3, clampSize=1.0)
    shape, _geo = parts(cable)
    clamps = clamps_of(cable)
    assert len(clamps) == 3, clamps

    def check():
        low = cmds.getAttr(shape + ".minValue")
        high = cmds.getAttr(shape + ".maxValue")
        params = [low + (high - low) * k / 800.0 for k in range(801)]
        for clamp in clamps:
            pos = cmds.xform(clamp, query=True, worldSpace=True,
                             translation=True)
            gap, param = min(
                (sum((p - q) ** 2 for p, q in zip(pos, cmds.pointOnCurve(
                    shape, parameter=u, position=True))) ** 0.5, u)
                for u in params)
            assert gap < 0.02, (clamp, gap)  # on the cable
            x_axis = cmds.xform(clamp, query=True, worldSpace=True,
                                matrix=True)[0:3]
            length = sum(v * v for v in x_axis) ** 0.5
            assert abs(length - 0.1) < 1e-3, length  # radius x size
            tangent = cmds.pointOnCurve(shape, parameter=param,
                                        normalizedTangent=True)
            along = sum(v / length * t for v, t in zip(x_axis, tangent))
            assert along > 0.99, (clamp, along)  # +X along the cable

    check()
    cmds.xform(b, worldSpace=True, translation=(12, 3, 2))  # live
    check()
    cable.update({"clampSize": 2.0})
    scale = cmds.getAttr(clamps[0] + ".scaleX")
    assert abs(scale - 0.2) < 1e-6, scale


@test
def custom_clamp_mesh_is_instanced_and_survives_rebuild():
    bracket = cmds.polyCube(name="bracket", width=0.3, height=3, depth=3)[0]
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    from cable_tool.route import Route
    from cable_tool.generators import CableGenerator
    cable = CableGenerator()
    cable.build(Route(a, b), {"clampCount": 2, "wireCount": 2},
                extras={"clampSource": bracket})
    clamps = clamps_of(cable)
    assert len(clamps) == 4, clamps  # 2 per wire
    shape = cmds.listRelatives(clamps[0], shapes=True, fullPath=True)[0]
    assert shape.split("|")[-1] == "bracketShape", shape  # an instance
    assert not cmds.ls(cable.group + "|*_clampRing")
    cable.update({"wireCount": 3})  # rebuild keeps the picked mesh
    assert cable.read_extras()["clampSource"].endswith("bracket")
    assert len(clamps_of(cable)) == 6
    cable.delete()
    assert cmds.objExists(bracket)  # the artist's mesh is never deleted


@test
def presets_fill_in_defaults():
    from cable_tool.generators import CableGenerator
    tangle = CableGenerator.preset("Cyberpunk Tangle")
    assert tangle["wireCount"] == 14 and tangle["spreadRow"] == 0
    assert set(tangle) == set(CableGenerator.setting_keys())
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], **CableGenerator.preset("Utility Line"))
    assert len(cmds.ls(cable.group + "|*_crv")) == 4


@test
def delete_removes_every_tool_node_and_nothing_else():
    from cable_tool import nodes
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    before = set(cmds.ls())
    first = build([a, b])
    second = build([a, b])
    first.delete()
    assert second.exists()
    second.delete()
    left = set(cmds.ls()) - before
    # Only the empty root group may remain.
    assert all(n.startswith("CableTool_GRP") for n in left), left
    assert cmds.objExists(a) and cmds.objExists(b)
    nodes.delete_all()
    assert set(cmds.ls()) == before, set(cmds.ls()) ^ before


@test
def clear_all_spares_similarly_named_user_nodes():
    from cable_tool import nodes
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    impostor = cmds.group(empty=True, name="cable_01_geo")
    build([a, b])
    nodes.delete_all()
    assert cmds.objExists(impostor)
    assert not cmds.objExists("CableTool_GRP")


@test
def build_is_one_undo_step():
    cmds.undoInfo(state=True, infinity=True)
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cmds.flushUndo()
    before = set(cmds.ls())
    build([a, b])
    assert len(set(cmds.ls()) - before) > 10
    cmds.undo()
    assert set(cmds.ls()) == before, set(cmds.ls()) ^ before


@test
def modes_share_one_interface():
    from cable_tool import generators
    from cable_tool.config import CableToolError
    from cable_tool.route import Route
    modes = [g.mode for g in generators.GENERATORS]
    assert modes == ["cable", "fence", "road"], modes
    assert [g.available for g in generators.GENERATORS] == [True, False,
                                                             False]
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    for mode in ("fence", "road"):
        try:
            generators.get(mode)().build(Route(a, b), {})
        except CableToolError:
            continue
        raise AssertionError(mode + " mode built something")
    assert not cmds.ls("*_GRP", type="transform") or \
        cmds.ls("*_GRP", type="transform") == ["CableTool_GRP"]

    cable = build([a, b])
    found = generators.from_node(parts(cable)[1])
    assert type(found).__name__ == "CableGenerator"
    assert found.cable_id == cable.cable_id


@test
def load_finds_cable_from_its_mesh():
    from cable_tool.generators import CableGenerator
    a = locator("A", (0, 0, 0))
    w = locator("W", (5, 2, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, w, b], radius=0.3)
    _shape, geo = parts(cable)
    found = CableGenerator.from_node(geo)
    assert found and found.cable_id == cable.cable_id
    assert abs(found.read_settings()["radius"] - 0.3) < 1e-6
    route = found.read_route()
    assert (route.start, route.waypoints, route.end) == ("A", ["W"], "B")


@test
def bad_routes_raise_friendly_errors():
    from cable_tool.config import CableToolError
    from cable_tool.route import Route
    a = locator("A", (0, 0, 0))
    for route in (Route(a, None), Route(a, "missing"), Route(a, a)):
        try:
            route.validate()
        except CableToolError:
            continue
        raise AssertionError("no error for {0}".format(route.anchors))


@test
def settings_are_sanitised():
    from cable_tool.config import sanitize_settings
    clean = sanitize_settings({"radius": "abc", "sides": 1.6,
                               "sag": float("nan"), "taper": 1e9})
    assert clean["radius"] == 0.001
    assert clean["sides"] == 3
    assert clean["sag"] == 0.0
    assert clean["taper"] == 10.0


@test
def installer_writes_a_module_file():
    # Simulates dragging install.py in, into a scratch modules folder.
    import importlib.util
    import tempfile
    root = os.path.normpath(os.path.join(HERE, "..", "CableTool"))
    spec = importlib.util.spec_from_file_location(
        "cable_installer", os.path.join(root, "install.py"))
    installer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(installer)
    modules = tempfile.mkdtemp()
    mod_file = installer.install(root=root, modules=modules)
    text = open(mod_file).read()
    from cable_tool.config import VERSION
    assert text == "+ CableTool {0} {1}\n".format(VERSION, root), text
    assert cmds.pluginInfo("cableTool", query=True, loaded=True)
    assert os.path.isfile(os.path.join(root, "icons", "cableTool.png"))


@test
def plugin_unloads_cleanly():
    cmds.unloadPlugin("cableTool")
    assert not cmds.pluginInfo("cableTool", query=True, loaded=True)
    cmds.loadPlugin(PLUGIN)  # and loads again without restarting
    assert hasattr(cmds, "cableTool")


# -------------------------------------------------------------------------
def main():
    cmds.loadPlugin(os.path.abspath(PLUGIN))
    failures = 0
    for func in TESTS:
        cmds.file(new=True, force=True)
        try:
            func()
            print("PASS  " + func.__name__)
        except Exception:
            failures += 1
            print("FAIL  " + func.__name__)
            traceback.print_exc()
    print("\n{0} passed, {1} failed".format(len(TESTS) - failures, failures))
    return failures


if __name__ == "__main__":
    code = main()
    maya.standalone.uninitialize()
    os._exit(1 if code else 0)
