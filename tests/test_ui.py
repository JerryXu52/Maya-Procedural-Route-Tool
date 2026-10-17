"""Headless smoke test for the Cable Tool window. Run with Maya's Python:

    QT_QPA_PLATFORM=offscreen \\
    /Applications/Autodesk/maya2027/Maya.app/Contents/bin/mayapy tests/test_ui.py

Separate from test_cable_rig.py because a widget test needs a
QApplication created *before* maya.standalone starts.
"""

import os
import sys
import traceback

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
try:
    from PySide6 import QtWidgets
except ImportError:
    from PySide2 import QtWidgets
app = QtWidgets.QApplication(sys.argv)

import maya.standalone  # noqa: E402
maya.standalone.initialize(name="python")
import maya.cmds as cmds  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.join(HERE, "..", "CableTool", "plug-ins", "cableTool.py")


def locator(name, pos):
    loc = cmds.spaceLocator(name=name)[0]
    cmds.xform(loc, worldSpace=True, translation=pos)
    return loc


def run():
    cmds.loadPlugin(os.path.abspath(PLUGIN))
    from cable_tool import ui
    cmds.selectPref(trackSelectionOrder=True)

    a = locator("A", (0, 0, 0))
    w = locator("W", (5, 2, 0))
    b = locator("B", (10, 0, 0))
    cmds.select(clear=True)
    cmds.select(a, w, b)

    cmds.cableTool()  # the plugin command opens the window
    win = ui._window
    assert win is not None and win.isVisible()
    assert ui.show() is win  # a second call raises the same window

    win.on_use_selection_order()
    assert win.start_field.text() == "A" and win.end_field.text() == "B"
    assert win.waypoint_list.count() == 1

    win.on_generate()
    status = win.status.toPlainText()
    assert win.current and win.current.exists(), status
    assert status.startswith("[OK]"), status

    # Live edit through the UI, as a slider drag in one undo chunk.
    win.fields["radius"].dragStarted.emit()
    win.fields["radius"].field.setValue(0.4)
    win.fields["radius"].dragFinished.emit()
    assert abs(cmds.getAttr(win.current.group + ".radius") - 0.4) < 1e-6

    # Smoothness is build-time: the UI says so instead of failing.
    win.fields["samples"].field.setValue(10)
    assert "Rebuild" in win.status.toPlainText()
    win.on_rebuild()
    assert win.status.toPlainText().startswith("[OK]")

    # Load Selected from the mesh restores settings and route.
    geo = cmds.ls(win.current.group + "|*_geo")[0]
    win.on_reset()
    cmds.select(geo)
    win.on_load_selected()
    assert win.fields["samples"].value() == 10  # read back from the cable
    assert win.waypoint_list.count() == 1

    # A bad route is a warning in the status box, not an exception.
    win.start_field.set_text("")
    win.on_generate()
    assert win.status.toPlainText().startswith("[WARNING]")

    # Deleting the current cable is noticed.
    cmds.select(geo)
    win.on_delete_selected()
    assert win.current is None or not win.current.exists()
    assert not win.rebuild_button.isEnabled()

    cmds.unloadPlugin("cableTool")  # closes the window
    assert ui._window is None
    app.processEvents()


if __name__ == "__main__":
    failed = 0
    try:
        run()
        print("PASS  window smoke test")
    except Exception:
        failed = 1
        print("FAIL  window smoke test")
        traceback.print_exc()
    maya.standalone.uninitialize()
    os._exit(failed)
