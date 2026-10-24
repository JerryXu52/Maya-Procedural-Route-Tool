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
    from cable_tool import i18n
    i18n.set_language("en", remember=False)  # messages are checked in English
    from cable_tool import ui
    from cable_tool.config import DEFAULTS
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

    # Only Cable / Pipe can be picked; Fence and Road are listed greyed out.
    items = [win.mode_box.model().item(i)
             for i in range(win.mode_box.count())]
    assert [item.isEnabled() for item in items] == [True, False, False]
    assert win.generate_button.text() == "Generate Cable"
    assert win.mode_stack.count() == 3

    win.on_use_selection_order()
    assert win.start_field.text() == "A" and win.end_field.text() == "B"
    assert win.waypoint_list.count() == 1

    win.on_generate()
    status = win.status.toPlainText()
    assert win.current and win.current.exists(), status
    assert status.startswith("[OK]"), status

    # Live edit through the UI, as a slider drag in one undo chunk.
    fields = win.fields["cable"]
    fields["radius"].dragStarted.emit()
    fields["radius"].field.setValue(0.4)
    fields["radius"].dragFinished.emit()
    assert abs(cmds.getAttr(win.current.group + ".radius") - 0.4) < 1e-6

    # Smoothness is live (peer run: it needed a manual Rebuild).
    fields["samples"].field.setValue(10)
    assert cmds.getAttr(win.current.group + ".samples") == 10

    def wires():
        return len(cmds.ls(win.current.group + "|*_crv"))

    # Wire Count changes the node network, so the run rebuilds itself.
    fields["wireCount"].field.setValue(3)
    assert "rebuilt" in win.status.toPlainText(), win.status.toPlainText()
    assert wires() == 3
    # During a drag it waits for the release.
    fields["wireCount"].dragStarted.emit()
    fields["wireCount"].field.setValue(5)
    assert wires() == 3
    fields["wireCount"].dragFinished.emit()
    assert wires() == 5
    assert abs(cmds.getAttr(win.current.group + ".radius") - 0.4) < 1e-6

    # On/off settings use a checkbox.
    fields["attach"].box.setChecked(False)
    assert cmds.getAttr(win.current.group + ".attach") is False

    win.on_rebuild()
    assert win.status.toPlainText().startswith("[OK]")

    # Load Selected from the mesh restores settings and route.
    geo = cmds.ls(win.current.group + "|*_geo")[0]
    for field in fields.values():  # scramble the UI only (no signals)
        field.set_value(DEFAULTS[field.key]["field"][0])
    win.waypoint_list.clear()
    cmds.select(geo)
    win.on_load_selected()
    assert fields["samples"].value() == 10  # read back from the cable
    assert fields["wireCount"].value() == 5
    assert fields["attach"].value() == 0
    assert win.waypoint_list.count() == 1

    # A preset fills every field and applies to the current run.
    win.on_apply_preset("Utility Line")
    assert fields["wireCount"].value() == 4 and wires() == 4
    assert fields["spreadRow"].value() == 1
    assert cmds.getAttr(win.current.group + ".spreadRow") is True

    # Reset applies the defaults to the cable, rebuilding for Wire Count.
    win.on_reset()
    assert cmds.getAttr(win.current.group + ".samples") == 6
    assert cmds.getAttr(win.current.group + ".attach") is True
    assert wires() == 1
    geo = cmds.ls(win.current.group + "|*_geo")[0]

    # Language: the window rebuilds in the new language and keeps the
    # route, the settings and the cable being edited.
    editing = win.current.group
    expected = {"zh": u"\u751f\u6210\u7ebf\u7f06",      # 生成线缆
                "yue": u"\u751f\u6210\u96fb\u7e9c",     # 生成電纜
                "es": u"Generar cable", "fr": u"G\u00e9n\u00e9rer le c\u00e2ble"}
    for code, label in expected.items():
        win = ui.switch_language(code)
        assert win.generate_button.text() == label, (code,
                                                     win.generate_button.text())
        assert win.language_actions[code].isChecked()
        assert win.current and win.current.group == editing
        assert win.start_field.text() == "A" and win.waypoint_list.count() == 1
        assert win.fields["cable"]["samples"].value() == 6
        win.on_rebuild()  # still works, and reports in that language
        assert win.status.toPlainText().startswith(i18n.tr("[OK]")), code
    win = ui.switch_language("en")
    assert win.generate_button.text() == "Generate Cable"
    assert win.status.toPlainText().startswith("[OK]")

    # A bad route is a warning in the status box, not an exception.
    win.start_field.set_text("")
    win.on_generate()
    assert win.status.toPlainText().startswith("[WARNING]")

    # Deleting the current cable is noticed.
    cmds.select(geo)
    win.on_delete_selected()
    assert win.current is None or not win.current.exists()
    assert not win.rebuild_button.isEnabled()

    # Maya won't unload a plugin while its nodes (the cable solvers)
    # exist, even in the undo queue, so start a fresh scene first.
    cmds.file(new=True, force=True)
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
