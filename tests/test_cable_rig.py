"""Headless tests for the Cable Tool rig. Run with Maya's Python:

    /Applications/Autodesk/maya2027/Maya.app/Contents/bin/mayapy tests/test_cable_rig.py

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


LEAD_SAMPLES = 2  # config.LEAD_SAMPLES, imported after the plugin loads


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


# -------------------------------------------------------------------------
@test
def plugin_loads_and_registers_command():
    assert cmds.pluginInfo("cableTool", query=True, loaded=True)
    assert "cableTool" in (cmds.pluginInfo("cableTool", query=True,
                                           command=True) or [])
    assert cmds.pluginInfo("sweep", query=True, loaded=True)


@test
def ends_follow_anchors_live():
    a = locator("A", (0, 5, 0))
    b = locator("B", (10, 5, 0))
    cable = build([a, b], sag=0.2)
    shape, geo = parts(cable)
    last = cmds.getAttr(shape + ".spans") + cmds.getAttr(shape + ".degree") - 1
    assert close(cv(shape, 0), (0, 5, 0))
    assert close(cv(shape, last), (10, 5, 0))
    assert cmds.polyEvaluate(geo, face=True) > 0

    cmds.xform(b, worldSpace=True, translation=(12, 8, 3))
    assert close(cv(shape, last), (12, 8, 3)), cv(shape, last)
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
    cable = build([a, b], sag=0.0, samples=7)
    shape, _geo = parts(cable)
    mid = 4  # anchor + 7 samples: index 4 is t = 0.5
    assert abs(cv(shape, mid)[1]) < 1e-4

    cable.update({"sag": 0.2})
    assert close(cv(shape, mid), (5, -2.0, 0)), cv(shape, mid)

    cmds.xform(b, worldSpace=True, translation=(20, 0, 0))  # double length
    assert close(cv(shape, mid), (10, -4.0, 0)), cv(shape, mid)


@test
def shape_settings_drive_sweep_live():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], sag=0.0, radius=0.1)
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
    cable = build([a, w, b], sag=0.0, samples=6)
    shape, _geo = parts(cable)
    assert close(cv(shape, 7), (5, 0, 5))  # 1 anchor + 6 samples, then W
    # The curve itself passes close to the waypoint (a rounded bend).
    closest = cmds.createNode("nearestPointOnCurve")
    cmds.connectAttr(shape + ".worldSpace[0]", closest + ".inputCurve")
    cmds.setAttr(closest + ".inPosition", 5, 0, 5)
    gap = sum((p - q) ** 2 for p, q in zip(
        cmds.getAttr(closest + ".position")[0], (5, 0, 5))) ** 0.5
    assert gap < 0.25, gap
    cmds.xform(w, worldSpace=True, translation=(5, 4, 5))
    assert close(cv(shape, 7), (5, 4, 5))


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
def rebuild_applies_smoothness_and_keeps_name():
    a = locator("A", (0, 0, 0))
    b = locator("B", (10, 0, 0))
    cable = build([a, b], samples=4)
    name = cable.group.split("|")[-1]
    # Peer run: Smoothness needed a manual Rebuild. update() now rebuilds.
    assert cable.update({"samples": 10}) == ["samples"]
    assert cable.exists()
    shape, _geo = parts(cable)
    assert cable.group.split("|")[-1] == name
    assert cmds.getAttr(shape + ".spans") + 3 == 12  # 2 anchors + 10


@test
def waypoints_turn_smoothly():
    # Peer run: waypoints made sharp, tight corners.
    a = locator("A", (0, 0, 0))
    w = locator("W", (5, 0, 5))
    b = locator("B", (10, 0, 0))

    def tightest_bend(smoothing, sag):
        """Smallest radius of curvature along the cable."""
        cable = build([a, w, b], sag=sag, smoothing=smoothing)
        shape, _geo = parts(cable)
        low = cmds.getAttr(shape + ".minValue")
        high = cmds.getAttr(shape + ".maxValue")
        steps = 400
        radius = min(cmds.pointOnCurve(shape, parameter=low + (high - low)
                                       * k / steps, curvatureRadius=True)
                     for k in range(1, steps))
        cable.delete()
        return radius

    # Taut: straight runs meet in a point; smoothing rounds the corner.
    assert tightest_bend(0.0, 0.0) < 0.1
    assert tightest_bend(1.0, 0.0) > 1.0
    # Sagging: smoothing still opens the tightest bend up clearly.
    sharp, smooth = tightest_bend(0.0, 0.3), tightest_bend(1.0, 0.3)
    assert smooth > sharp * 1.5, (sharp, smooth)


@test
def mesh_ends_sit_on_the_surface_and_lead_out():
    # Peer run: cables ended at each object's pivot, inside it, so several
    # cables met at one point and crossed there.
    cube = cmds.polyCube(width=2, height=2, depth=2, name="box")[0]
    b = locator("B", (10, 0, 0))
    cable = build([cube, b], sag=0.0, leadOut=0.5)
    shape, _geo = parts(cable)
    assert close(cv(shape, 0), (1, 0, 0)), cv(shape, 0)
    lead = 1 + LEAD_SAMPLES  # start, lead span samples, then the lead point
    assert close(cv(shape, lead), (1.5, 0, 0)), cv(shape, lead)

    cmds.xform(cube, worldSpace=True, translation=(0, 5, 0))
    assert close(cv(shape, 0), (1, 4, 0)), cv(shape, 0)
    cmds.setAttr(cube + ".rotateZ", 90)  # normals follow the mesh live
    assert close(cv(shape, 0), (1, 4, 0)), cv(shape, 0)

    cable.update({"attach": 0})
    assert close(cv(shape, 0), (0, 5, 0)), cv(shape, 0)
    assert close(cv(shape, lead), (0, 5, 0)), cv(shape, lead)


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
