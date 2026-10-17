"""The Cable Tool window.

Layout: menu bar, mode dropdown, then a scrolling body (Route, then the
current mode's panel) above a pinned footer holding the action buttons
and the status box, so they never scroll out of reach.

The sliders edit the *current cable* live: the last one generated, or
the one picked with Edit > Load Selected Cable.
"""

import traceback

import maya.cmds as cmds
import maya.OpenMayaUI as omui

try:
    from PySide6 import QtCore, QtGui, QtWidgets
    from shiboken6 import wrapInstance
except ImportError:  # Maya 2024 and earlier
    from PySide2 import QtCore, QtGui, QtWidgets
    from shiboken2 import wrapInstance

from cable_tool import nodes, route as route_mod
from cable_tool.config import (DEFAULTS, TOOL_NAME, VERSION, CableToolError,
                               default_settings)
from cable_tool.generators import CableGenerator

WINDOW_OBJECT = "CableToolWindow"
LOG_PREFIX = "[CableTool] "

STATUS_COLOURS = {"info": "#3a3a3a", "ok": "#2a4d31",
                  "warning": "#5c4a1c", "error": "#5c2b29"}
STATUS_TAGS = {"info": "[INFO]", "ok": "[OK]", "warning": "[WARNING]",
               "error": "[ERROR]"}

MODES = (("Cable / Pipe", "cable", True),
         ("Fence (coming later)", "fence", False),
         ("Road (coming later)", "road", False))

_window = None


def maya_main_window():
    pointer = omui.MQtUtil.mainWindow()
    if pointer is None:  # mayapy / batch
        return None
    return wrapInstance(int(pointer), QtWidgets.QWidget)


def show():
    """Open the window, or raise it if it is already open."""
    global _window
    if _window is not None:
        try:
            _window.show()
            _window.raise_()
            _window.activateWindow()
            return _window
        except RuntimeError:  # the C++ widget was already deleted
            _window = None
    _window = CableToolWindow(parent=maya_main_window())
    _window.show()
    return _window


def close():
    global _window
    if _window is not None:
        try:
            _window.close()
            _window.deleteLater()
        except RuntimeError:
            pass
    _window = None


def about():
    QtWidgets.QMessageBox.about(
        maya_main_window(), TOOL_NAME,
        "<b>{0}</b> {1}<br><br>Live procedural pipes and cables built on "
        "Sweep Mesh.<br>Open it from the Cable Tool menu or run "
        "<code>cmds.cableTool()</code>.".format(TOOL_NAME, VERSION))


# -------------------------------------------------------------------------
# Small widgets
# -------------------------------------------------------------------------
class CollapsibleSection(QtWidgets.QWidget):
    """A titled section that folds away with a click."""

    def __init__(self, title, parent=None, expanded=True):
        super(CollapsibleSection, self).__init__(parent)
        self._toggle = QtWidgets.QToolButton(text=title, checkable=True,
                                             checked=expanded)
        self._toggle.setStyleSheet("QToolButton { border: none; "
                                   "font-weight: bold; }")
        self._toggle.setToolButtonStyle(
            QtCore.Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self._toggle.toggled.connect(self._on_toggled)

        self.body = QtWidgets.QWidget()
        self.body_layout = QtWidgets.QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(12, 2, 4, 6)
        self.body_layout.setSpacing(4)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._toggle)
        layout.addWidget(self.body)
        self._on_toggled(expanded)

    def _on_toggled(self, expanded):
        self._toggle.setArrowType(QtCore.Qt.ArrowType.DownArrow if expanded
                                  else QtCore.Qt.ArrowType.RightArrow)
        self.body.setVisible(expanded)


class SliderField(QtWidgets.QWidget):
    """Label + slider + number field. The slider covers a comfortable
    range; the field accepts anything up to the hard cap."""

    valueChanged = QtCore.Signal(object)
    dragStarted = QtCore.Signal()
    dragFinished = QtCore.Signal()

    STEPS = 1000  # slider resolution for float settings

    def __init__(self, key, parent=None):
        super(SliderField, self).__init__(parent)
        spec = DEFAULTS[key]
        self.key = key
        self.is_int = spec["int"]
        self.soft_low, self.soft_high = spec["slider"]

        label = QtWidgets.QLabel(spec["label"])
        label.setMinimumWidth(90)
        self.slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        if self.is_int:
            self.slider.setRange(int(self.soft_low), int(self.soft_high))
            self.field = QtWidgets.QSpinBox()
        else:
            self.slider.setRange(0, self.STEPS)
            self.field = QtWidgets.QDoubleSpinBox()
            self.field.setDecimals(3)
            self.field.setSingleStep((self.soft_high - self.soft_low) / 100.0)
        self.field.setRange(*spec["field"])
        self.field.setKeyboardTracking(False)
        self.field.setMinimumWidth(72)

        for widget in (label, self.slider, self.field):
            widget.setToolTip(spec["tip"])

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addWidget(self.slider, 1)
        layout.addWidget(self.field)

        self.slider.valueChanged.connect(self._from_slider)
        self.field.valueChanged.connect(self._from_field)
        self.slider.sliderPressed.connect(self.dragStarted)
        self.slider.sliderReleased.connect(self.dragFinished)
        self.set_value(spec["default"])

    def value(self):
        return self.field.value()

    def set_value(self, value):
        """Set without emitting valueChanged."""
        for widget in (self.slider, self.field):
            widget.blockSignals(True)
        self.field.setValue(value)
        self._sync_slider(value)
        for widget in (self.slider, self.field):
            widget.blockSignals(False)

    def _sync_slider(self, value):
        if self.is_int:
            self.slider.setValue(int(value))
            return
        span = self.soft_high - self.soft_low
        ratio = (value - self.soft_low) / span if span else 0.0
        self.slider.setValue(int(round(max(0.0, min(1.0, ratio))
                                       * self.STEPS)))

    def _from_slider(self, position):
        if self.is_int:
            value = position
        else:
            value = self.soft_low + (self.soft_high - self.soft_low) * (
                float(position) / self.STEPS)
        self.field.blockSignals(True)
        self.field.setValue(value)
        self.field.blockSignals(False)
        self.valueChanged.emit(self.field.value())

    def _from_field(self, value):
        self.slider.blockSignals(True)
        self._sync_slider(value)
        self.slider.blockSignals(False)
        self.valueChanged.emit(value)


class AnchorField(QtWidgets.QWidget):
    """A read-only anchor name with a Get Selected button."""

    def __init__(self, label, tip, on_pick, parent=None):
        super(AnchorField, self).__init__(parent)
        title = QtWidgets.QLabel(label)
        title.setMinimumWidth(90)
        self.edit = QtWidgets.QLineEdit()
        self.edit.setPlaceholderText("nothing picked")
        self.edit.setToolTip(tip)
        button = QtWidgets.QPushButton("Get Selected")
        button.setToolTip("Use the first selected object or locator.")
        button.clicked.connect(lambda: on_pick(self))
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(title)
        layout.addWidget(self.edit, 1)
        layout.addWidget(button)

    def text(self):
        return self.edit.text().strip()

    def set_text(self, text):
        self.edit.setText(text)


# -------------------------------------------------------------------------
# Main window
# -------------------------------------------------------------------------
def guarded(method):
    """Run a UI handler so that no exception ever reaches Maya: limits we
    enforce become warnings, anything unforeseen becomes an error."""
    def wrapper(self, *args):
        try:
            return method(self)
        except CableToolError as err:
            self.set_status(str(err), "warning")
        except Exception as err:
            print(LOG_PREFIX + traceback.format_exc())
            self.set_status("Unexpected error handled: {0}: {1} (details in "
                            "the Script Editor).".format(type(err).__name__,
                                                         err), "error")
    wrapper.__name__ = method.__name__
    return wrapper


class CableToolWindow(QtWidgets.QWidget):

    def __init__(self, parent=None):
        super(CableToolWindow, self).__init__(parent)
        self.setObjectName(WINDOW_OBJECT)
        self.setWindowFlags(QtCore.Qt.WindowType.Window)
        self.setWindowTitle("{0} {1}".format(TOOL_NAME, VERSION))
        self.resize(460, 640)
        self.setAttribute(QtCore.Qt.WidgetAttribute.WA_DeleteOnClose)

        self.current = None   # CableGenerator being edited
        self._dragging = False
        self.fields = {}

        root = QtWidgets.QVBoxLayout(self)
        root.setContentsMargins(6, 0, 6, 6)
        root.setMenuBar(self._build_menu())
        root.addLayout(self._build_mode_row())

        scroll = QtWidgets.QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        body = QtWidgets.QWidget()
        body_layout = QtWidgets.QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.addWidget(self._build_route_section())
        self.mode_stack = QtWidgets.QStackedWidget()
        self.mode_stack.addWidget(self._build_cable_panel())
        body_layout.addWidget(self.mode_stack)
        body_layout.addStretch(1)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        root.addWidget(self._build_footer())
        self.set_status("Ready. Pick a Start and End (or select them in "
                        "order and press Use Selection Order), then "
                        "Generate.")

    # -- construction -----------------------------------------------------
    def _build_menu(self):
        bar = QtWidgets.QMenuBar(self)
        edit = bar.addMenu("Edit")
        edit.addAction("Reset Settings", self.on_reset)
        edit.addSeparator()
        edit.addAction("Load Selected Cable", self.on_load_selected)
        edit.addAction("Delete Selected Cable", self.on_delete_selected)
        edit.addAction("Clear All Cables", self.on_clear_all)
        help_menu = bar.addMenu("Help")
        help_menu.addAction("About", about)
        return bar

    def _build_mode_row(self):
        row = QtWidgets.QHBoxLayout()
        row.addWidget(QtWidgets.QLabel("Mode"))
        self.mode_box = QtWidgets.QComboBox()
        for label, _mode, enabled in MODES:
            self.mode_box.addItem(label)
            item = self.mode_box.model().item(self.mode_box.count() - 1)
            item.setEnabled(enabled)
        self.mode_box.setToolTip("What to build along the route. Fence and "
                                 "Road modes are planned stretch goals.")
        row.addWidget(self.mode_box, 1)
        return row

    def _build_route_section(self):
        section = CollapsibleSection("Route")
        layout = section.body_layout

        self.start_field = AnchorField("Start", "Where the cable begins.",
                                       self.on_pick_anchor)
        self.end_field = AnchorField("End", "Where the cable ends.",
                                     self.on_pick_anchor)
        layout.addWidget(self.start_field)

        layout.addWidget(QtWidgets.QLabel("Waypoints (in order)"))
        self.waypoint_list = QtWidgets.QListWidget()
        self.waypoint_list.setMaximumHeight(90)
        self.waypoint_list.setToolTip("Objects or locators the cable passes "
                                      "through between Start and End.")
        layout.addWidget(self.waypoint_list)

        buttons = QtWidgets.QHBoxLayout()
        for label, handler, tip in (
                ("Add Selected", self.on_add_waypoints,
                 "Append the selected objects, in the order you clicked."),
                ("Remove", self.on_remove_waypoint, "Remove the highlighted "
                                                    "waypoint."),
                ("Up", lambda: self.on_move_waypoint(-1), "Move earlier."),
                ("Down", lambda: self.on_move_waypoint(1), "Move later.")):
            button = QtWidgets.QPushButton(label)
            button.setToolTip(tip)
            button.clicked.connect(handler)
            buttons.addWidget(button)
        layout.addLayout(buttons)
        layout.addWidget(self.end_field)

        fill = QtWidgets.QPushButton("Use Selection Order")
        fill.setToolTip("Select anchors in order: the first becomes Start, "
                        "the last becomes End, the rest are waypoints.")
        fill.clicked.connect(self.on_use_selection_order)
        layout.addWidget(fill)
        return section

    def _build_cable_panel(self):
        panel = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        section = CollapsibleSection("Shape")
        for key in ("radius", "sides", "twist", "taper", "sag", "samples"):
            field = SliderField(key)
            field.valueChanged.connect(
                lambda value, k=key: self.on_setting_changed(k, value))
            field.dragStarted.connect(self.on_drag_started)
            field.dragFinished.connect(self.on_drag_finished)
            self.fields[key] = field
            section.body_layout.addWidget(field)
        layout.addWidget(section)
        return panel

    def _build_footer(self):
        footer = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(footer)
        layout.setContentsMargins(0, 6, 0, 0)

        self.current_label = QtWidgets.QLabel()
        layout.addWidget(self.current_label)

        row = QtWidgets.QHBoxLayout()
        generate = QtWidgets.QPushButton("Generate Cable")
        generate.setMinimumHeight(34)
        generate.setStyleSheet("background-color: #4d8a5c; color: white;")
        generate.setToolTip("Build a new live cable along the route.")
        generate.clicked.connect(self.on_generate)
        self.rebuild_button = QtWidgets.QPushButton("Rebuild Current")
        self.rebuild_button.setMinimumHeight(34)
        self.rebuild_button.setToolTip("Rebuild the current cable with this "
                                       "route and Smoothness.")
        self.rebuild_button.clicked.connect(self.on_rebuild)
        clear = QtWidgets.QPushButton("Clear All")
        clear.setMinimumHeight(34)
        clear.setStyleSheet("background-color: #944d4d; color: white;")
        clear.setToolTip("Delete every node this tool created.")
        clear.clicked.connect(self.on_clear_all)
        row.addWidget(generate, 3)
        row.addWidget(self.rebuild_button, 2)
        row.addWidget(clear, 2)
        layout.addLayout(row)

        self.status = QtWidgets.QPlainTextEdit()
        self.status.setReadOnly(True)
        self.status.setFixedHeight(64)
        self.status.setToolTip("Result of the last action.")
        layout.addWidget(self.status)
        self._refresh_current()
        return footer

    # -- helpers ----------------------------------------------------------
    def set_status(self, message, level="info"):
        text = "{0} {1}".format(STATUS_TAGS[level], message)
        print(LOG_PREFIX + text)
        self.status.setPlainText(text)
        self.status.setStyleSheet(
            "QPlainTextEdit {{ background-color: {0}; color: #eeeeee; }}"
            .format(STATUS_COLOURS[level]))

    def settings(self):
        return {key: field.value() for key, field in self.fields.items()}

    def route(self):
        waypoints = [self.waypoint_list.item(i).text()
                     for i in range(self.waypoint_list.count())]
        return route_mod.Route(self.start_field.text() or None,
                               self.end_field.text() or None, waypoints)

    def _current_cable(self):
        if self.current is not None and not self.current.exists():
            self.current = None  # deleted or undone
        return self.current

    def _refresh_current(self):
        cable = self._current_cable()
        if cable:
            self.current_label.setText("Editing: <b>{0}</b> (sliders update "
                                       "it live)".format(
                                           route_mod.short_name(cable.group)))
        else:
            self.current_label.setText("Editing: <i>no cable yet</i>")
        self.rebuild_button.setEnabled(cable is not None)

    def _select_anchors(self):
        anchors, ignored = route_mod.selected_transforms()
        if ignored:
            self.set_status("Ignored {0} item(s) that are not objects or "
                            "locators (vertex/face anchors arrive in week "
                            "3).".format(len(ignored)), "warning")
        if not anchors:
            raise CableToolError("Select one or more objects or locators "
                                 "first.")
        return [cmds.ls(a)[0] for a in anchors]

    def _show_route(self, route):
        self.start_field.set_text(cmds.ls(route.start)[0])
        self.end_field.set_text(cmds.ls(route.end)[0])
        self.waypoint_list.clear()
        for waypoint in route.waypoints:
            self.waypoint_list.addItem(cmds.ls(waypoint)[0])

    # -- route handlers ---------------------------------------------------
    def on_pick_anchor(self, field):
        # Not @guarded: it needs the field argument, which the decorator
        # drops (Qt passes a `checked` flag we don't want).
        try:
            field.set_text(self._select_anchors()[0])
        except CableToolError as err:
            self.set_status(str(err), "warning")
        except Exception as err:
            print(LOG_PREFIX + traceback.format_exc())
            self.set_status("Unexpected error handled: {0}: {1}".format(
                type(err).__name__, err), "error")

    @guarded
    def on_add_waypoints(self):
        for anchor in self._select_anchors():
            self.waypoint_list.addItem(anchor)

    @guarded
    def on_remove_waypoint(self):
        row = self.waypoint_list.currentRow()
        if row < 0:
            raise CableToolError("Click a waypoint in the list first.")
        self.waypoint_list.takeItem(row)

    def on_move_waypoint(self, step):
        row = self.waypoint_list.currentRow()
        target = row + step
        if row < 0 or not 0 <= target < self.waypoint_list.count():
            return
        item = self.waypoint_list.takeItem(row)
        self.waypoint_list.insertItem(target, item)
        self.waypoint_list.setCurrentRow(target)

    @guarded
    def on_use_selection_order(self):
        anchors = self._select_anchors()
        if len(anchors) < 2:
            raise CableToolError("Select at least 2 objects or locators, in "
                                 "the order the cable should run.")
        self._show_route(route_mod.Route(anchors[0], anchors[-1],
                                         anchors[1:-1]))
        self.set_status("Route set: {0} anchor(s).".format(len(anchors)),
                        "ok")

    # -- settings handlers ------------------------------------------------
    def on_drag_started(self):
        # One undo chunk per slider drag, so a whole drag is one Ctrl+Z.
        if self._current_cable() and not self._dragging:
            cmds.undoInfo(openChunk=True, chunkName="CableTool_Adjust")
            self._dragging = True

    def on_drag_finished(self):
        if self._dragging:
            cmds.undoInfo(closeChunk=True)
            self._dragging = False

    def on_setting_changed(self, key, value):
        cable = self._current_cable()
        if cable is None:
            return
        try:
            pending = cable.update({key: value})
        except Exception as err:
            self.set_status("Could not update {0}: {1}".format(key, err),
                            "error")
            return
        if pending:
            self.set_status("Smoothness changes the curve's point count; "
                            "press Rebuild Current to apply it.", "info")

    @guarded
    def on_reset(self):
        with nodes.undo_chunk("CableTool_Reset"):
            for key, value in default_settings().items():
                self.fields[key].set_value(value)
            cable = self._current_cable()
            if cable:
                cable.update(self.settings())
        self.set_status("Settings reset to defaults{0}.".format(
            " and applied to the current cable" if self.current else ""))

    # -- build handlers ---------------------------------------------------
    @guarded
    def on_generate(self):
        route = self.route()
        cable = CableGenerator()
        group = cable.build(route, self.settings())
        self.current = cable
        self._refresh_current()
        cmds.select(group, replace=True)

        message = ("Built {0} through {1} anchor(s). Move any anchor and the "
                   "cable follows; its settings are also on the group in the "
                   "Channel Box.").format(route_mod.short_name(group),
                                          len(route.anchors))
        overlapping = route.overlapping_spans()
        if overlapping:
            self.set_status(message + " Note: {0} span(s) have both anchors "
                            "on the same spot, so they are invisible until "
                            "the anchors move apart.".format(overlapping),
                            "warning")
        else:
            self.set_status(message, "ok")

    @guarded
    def on_rebuild(self):
        cable = self._current_cable()
        if cable is None:
            raise CableToolError("No current cable. Generate one, or select "
                                 "a cable and use Edit > Load Selected Cable.")
        group = cable.rebuild(self.route(), self.settings())
        self._refresh_current()
        cmds.select(group, replace=True)
        self.set_status("Rebuilt {0}.".format(route_mod.short_name(group)),
                        "ok")

    @guarded
    def on_load_selected(self):
        selection = cmds.ls(selection=True, long=True) or []
        cable = None
        for node in selection:
            cable = CableGenerator.from_node(node)
            if cable:
                break
        if cable is None:
            raise CableToolError("Select a cable (its mesh, curve or group) "
                                 "first.")
        for key, value in cable.read_settings().items():
            self.fields[key].set_value(value)
        self.current = cable
        self._refresh_current()
        self._show_route(cable.read_route())
        self.set_status("Loaded {0}; the sliders now edit it.".format(
            route_mod.short_name(cable.group)), "ok")

    @guarded
    def on_delete_selected(self):
        selection = cmds.ls(selection=True, long=True) or []
        cables = {}
        for node in selection:
            cable = CableGenerator.from_node(node)
            if cable:
                cables[cable.cable_id] = cable
        if not cables:
            raise CableToolError("Select a cable (its mesh, curve or group) "
                                 "first.")
        with nodes.undo_chunk("CableTool_Delete"):
            for cable in cables.values():
                cable.delete()
        self._refresh_current()
        self.set_status("Deleted {0} cable(s).".format(len(cables)), "ok")

    @guarded
    def on_clear_all(self):
        answer = QtWidgets.QMessageBox.question(
            self, TOOL_NAME, "Delete every cable this tool created? "
                             "(Ctrl+Z undoes it.)")
        if answer != QtWidgets.QMessageBox.StandardButton.Yes:
            return
        with nodes.undo_chunk("CableTool_ClearAll"):
            count = nodes.delete_all()
        self.current = None
        self._refresh_current()
        self.set_status("Cleared {0} node(s) made by the tool.".format(count),
                        "ok")

    def closeEvent(self, event):
        self.on_drag_finished()  # never leave an undo chunk open
        global _window
        _window = None
        super(CableToolWindow, self).closeEvent(event)
