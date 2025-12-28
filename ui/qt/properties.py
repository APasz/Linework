"""Property editor panel for selected items in the Qt frontend."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, cast

from PySide6 import QtCore, QtGui, QtWidgets

from core.layers import HitKind
from models.assets import IconName
from models.geo import BuiltinIcon, PictureIcon, Point
from models.styling import Anchor, CapStyle, Colour, LineStyle
from ui.qt.line_style_icons import line_style_icon

if TYPE_CHECKING:
    from qt.app import QtApp

TCombo = TypeVar("TCombo")
TGuard = TypeVar("TGuard")

class PropertiesPanel(QtWidgets.QWidget):
    """Dockable property editor for the current selection."""

    def __init__(self, app: QtApp) -> None:
        """Create the properties panel.

        Args;
            app: The parent Qt app.
        """
        super().__init__(app)
        self.app = app
        self._current_kind: HitKind | None = None
        self._current_idx: int | None = None
        self._syncing = False
        self._widgets: dict[str, QtWidgets.QWidget] = {}

        layout = QtWidgets.QVBoxLayout(self)
        self._header = QtWidgets.QLabel("No selection")
        layout.addWidget(self._header)

        self._form_widget = QtWidgets.QWidget(self)
        self._form_layout = QtWidgets.QFormLayout(self._form_widget)
        self._form_layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self._form_layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        layout.addWidget(self._form_widget)
        layout.addStretch(1)

    def set_target(self, kind: HitKind | None, idx: int | None, *, force: bool = False) -> None:
        """Update the editor to show a new selection.

        Args;
            kind: The hit kind for the selection.
            idx: The selected item index.
            force: Whether to force a refresh even if unchanged.
        """
        if not force and kind == self._current_kind and idx == self._current_idx:
            return
        self._current_kind = kind
        self._current_idx = idx
        self._syncing = True
        self._clear_form()
        self._widgets.clear()

        if kind is None or idx is None:
            self._header.setText("No selection")
            self._syncing = False
            return

        if kind == HitKind.line:
            self._build_line(idx)
        elif kind == HitKind.label:
            self._build_label(idx)
        elif kind == HitKind.icon:
            self._build_icon(idx)
        else:
            self._header.setText("No selection")

        self._syncing = False

    def refresh(self) -> None:
        """Refresh widget values from the current selection."""
        if self._current_kind is None or self._current_idx is None:
            return
        idx = self._current_idx
        self._syncing = True

        if self._current_kind == HitKind.line and 0 <= idx < len(self.app.params.lines):
            line = self.app.params.lines[idx]
            self._set_spin_value("line_x1", line.a.x)
            self._set_spin_value("line_y1", line.a.y)
            self._set_spin_value("line_x2", line.b.x)
            self._set_spin_value("line_y2", line.b.y)
            self._set_spin_value("line_width", line.width)
            self._set_spin_value("line_dash_offset", line.dash_offset)
            self._set_combo_value("line_capstyle", line.capstyle)
            self._set_combo_value("line_style", line.style)
            self._set_check_value("line_snap", line.snap)
            self._set_button_colour_for_key("line_colour", line.col)

        if self._current_kind == HitKind.label and 0 <= idx < len(self.app.params.labels):
            lab = self.app.params.labels[idx]
            self._set_line_text("label_text", lab.text)
            self._set_spin_value("label_x", lab.p.x)
            self._set_spin_value("label_y", lab.p.y)
            self._set_spin_value("label_size", lab.size)
            self._set_spin_value("label_rotation", lab.rotation)
            self._set_combo_value("label_anchor", lab.anchor)
            self._set_check_value("label_snap", lab.snap)
            self._set_button_colour_for_key("label_colour", lab.col)

        if self._current_kind == HitKind.icon and 0 <= idx < len(self.app.params.icons):
            ico = self.app.params.icons[idx]
            self._set_spin_value("icon_x", ico.p.x)
            self._set_spin_value("icon_y", ico.p.y)
            self._set_spin_value("icon_size", ico.size)
            self._set_spin_value("icon_rotation", ico.rotation)
            self._set_combo_value("icon_anchor", ico.anchor)
            self._set_check_value("icon_snap", ico.snap)
            if isinstance(ico, BuiltinIcon):
                self._set_combo_value("icon_name", ico.name)
                self._set_button_colour_for_key("icon_colour", ico.col)
            elif isinstance(ico, PictureIcon):
                self._set_line_text("icon_src", str(ico.src))

        self._syncing = False

    # ---------- builders ----------
    def _build_line(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.app.params.lines):
            self._header.setText("Line")
            return
        line = self.app.params.lines[idx]
        self._header.setText(f"Line {idx}")
        max_x = max(1, self.app.params.width)
        max_y = max(1, self.app.params.height)

        x1 = self._spin_int(line.a.x, 0, max_x, lambda v: self._update_line_coords(idx, x1=v))
        y1 = self._spin_int(line.a.y, 0, max_y, lambda v: self._update_line_coords(idx, y1=v))
        x2 = self._spin_int(line.b.x, 0, max_x, lambda v: self._update_line_coords(idx, x2=v))
        y2 = self._spin_int(line.b.y, 0, max_y, lambda v: self._update_line_coords(idx, y2=v))
        self._form_layout.addRow("X1", x1)
        self._form_layout.addRow("Y1", y1)
        self._form_layout.addRow("X2", x2)
        self._form_layout.addRow("Y2", y2)
        self._widgets.update({"line_x1": x1, "line_y1": y1, "line_x2": x2, "line_y2": y2})

        snap_btn = QtWidgets.QPushButton("Snap endpoints to grid")
        snap_btn.clicked.connect(lambda _checked=False: self._snap_line(idx))
        self._form_layout.addRow("Snap", snap_btn)

        snap_flag = QtWidgets.QCheckBox()
        snap_flag.setChecked(line.snap)
        snap_flag.toggled.connect(lambda v: self._update_line(idx, snap=v))
        self._form_layout.addRow("Keep snapped", snap_flag)
        self._widgets["line_snap"] = snap_flag

        width = self._spin_int(line.width, 1, 200, lambda v: self._update_line(idx, width=v))
        self._form_layout.addRow("Width", width)
        self._widgets["line_width"] = width

        cap = self._combo([c for c in CapStyle], line.capstyle, lambda v: self._update_line(idx, capstyle=v))
        self._form_layout.addRow("Cap", cap)
        self._widgets["line_capstyle"] = cap

        style = self._line_style_combo(line.style, lambda v: self._update_line(idx, style=v))
        self._form_layout.addRow("Dash", style)
        self._widgets["line_style"] = style

        dash = self._spin_int(line.dash_offset, 0, 2000, lambda v: self._update_line(idx, dash_offset=v))
        self._form_layout.addRow("Dash offset", dash)
        self._widgets["line_dash_offset"] = dash

        colour_btn = self._colour_button(
            lambda: self.app.params.lines[idx].col,
            lambda c: self._update_line(idx, colour=c),
        )
        self._form_layout.addRow("Colour", colour_btn)
        self._widgets["line_colour"] = colour_btn

    def _build_label(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.app.params.labels):
            self._header.setText("Label")
            return
        lab = self.app.params.labels[idx]
        self._header.setText(f"Label {idx}")
        max_x = max(1, self.app.params.width)
        max_y = max(1, self.app.params.height)

        text = QtWidgets.QLineEdit(lab.text)
        text.editingFinished.connect(lambda: self._update_label_text(idx, text.text()))
        self._form_layout.addRow("Text", text)
        self._widgets["label_text"] = text

        x = self._spin_int(lab.p.x, 0, max_x, lambda v: self._update_label_coords(idx, x=v))
        y = self._spin_int(lab.p.y, 0, max_y, lambda v: self._update_label_coords(idx, y=v))
        self._form_layout.addRow("X", x)
        self._form_layout.addRow("Y", y)
        self._widgets.update({"label_x": x, "label_y": y})

        snap_btn = QtWidgets.QPushButton("Snap to grid")
        snap_btn.clicked.connect(lambda _checked=False: self._snap_label(idx))
        self._form_layout.addRow("Snap", snap_btn)

        snap_flag = QtWidgets.QCheckBox()
        snap_flag.setChecked(lab.snap)
        snap_flag.toggled.connect(lambda v: self._update_label(idx, snap=v))
        self._form_layout.addRow("Keep snapped", snap_flag)
        self._widgets["label_snap"] = snap_flag

        size = self._spin_int(lab.size, 1, 200, lambda v: self._update_label(idx, size=v))
        self._form_layout.addRow("Size", size)
        self._widgets["label_size"] = size

        rotation = self._spin_int(lab.rotation, -360, 360, lambda v: self._update_label(idx, rotation=v))
        self._form_layout.addRow("Rotation", rotation)
        self._widgets["label_rotation"] = rotation

        anchor = self._combo([a for a in Anchor], lab.anchor, lambda v: self._update_label(idx, anchor=v))
        self._form_layout.addRow("Anchor", anchor)
        self._widgets["label_anchor"] = anchor

        colour_btn = self._colour_button(
            lambda: self.app.params.labels[idx].col,
            lambda c: self._update_label(idx, colour=c),
        )
        self._form_layout.addRow("Colour", colour_btn)
        self._widgets["label_colour"] = colour_btn

    def _build_icon(self, idx: int) -> None:
        if idx < 0 or idx >= len(self.app.params.icons):
            self._header.setText("Icon")
            return
        ico = self.app.params.icons[idx]
        self._header.setText(f"Icon {idx}")
        max_x = max(1, self.app.params.width)
        max_y = max(1, self.app.params.height)

        if isinstance(ico, BuiltinIcon):
            name = self._combo([n for n in IconName], ico.name, lambda v: self._update_icon(idx, name=v))
            self._form_layout.addRow("Icon", name)
            self._widgets["icon_name"] = name

            colour_btn = self._colour_button(
                lambda: self.app.params.icons[idx].col,
                lambda c: self._update_icon(idx, colour=c),
            )
            self._form_layout.addRow("Colour", colour_btn)
            self._widgets["icon_colour"] = colour_btn

        elif isinstance(ico, PictureIcon):
            src = QtWidgets.QLineEdit(str(ico.src))
            src.setReadOnly(True)
            browse = QtWidgets.QPushButton("Browse...")
            browse.clicked.connect(lambda _checked=False: self._pick_icon_picture(idx, src))
            src_row = QtWidgets.QHBoxLayout()
            src_row.addWidget(src)
            src_row.addWidget(browse)
            src_widget = QtWidgets.QWidget()
            src_widget.setLayout(src_row)
            self._form_layout.addRow("Picture", src_widget)
            self._widgets["icon_src"] = src

        x = self._spin_int(ico.p.x, 0, max_x, lambda v: self._update_icon_coords(idx, x=v))
        y = self._spin_int(ico.p.y, 0, max_y, lambda v: self._update_icon_coords(idx, y=v))
        self._form_layout.addRow("X", x)
        self._form_layout.addRow("Y", y)
        self._widgets.update({"icon_x": x, "icon_y": y})

        snap_btn = QtWidgets.QPushButton("Snap to grid")
        snap_btn.clicked.connect(lambda _checked=False: self._snap_icon(idx))
        self._form_layout.addRow("Snap", snap_btn)

        snap_flag = QtWidgets.QCheckBox()
        snap_flag.setChecked(ico.snap)
        snap_flag.toggled.connect(lambda v: self._update_icon(idx, snap=v))
        self._form_layout.addRow("Keep snapped", snap_flag)
        self._widgets["icon_snap"] = snap_flag

        size = self._spin_int(ico.size, 1, 1024, lambda v: self._update_icon(idx, size=v))
        self._form_layout.addRow("Size", size)
        self._widgets["icon_size"] = size

        rotation = self._spin_int(ico.rotation, -360, 360, lambda v: self._update_icon(idx, rotation=v))
        self._form_layout.addRow("Rotation", rotation)
        self._widgets["icon_rotation"] = rotation

        anchor = self._combo([a for a in Anchor], ico.anchor, lambda v: self._update_icon(idx, anchor=v))
        self._form_layout.addRow("Anchor", anchor)
        self._widgets["icon_anchor"] = anchor

    # ---------- updates ----------
    def _update_line_coords(
        self, idx: int, *, x1: int | None = None, y1: int | None = None, x2: int | None = None, y2: int | None = None
    ) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.lines):
                return
            line = self.app.params.lines[idx]
            a = Point(x=x1 if x1 is not None else line.a.x, y=y1 if y1 is not None else line.a.y)
            b = Point(x=x2 if x2 is not None else line.b.x, y=y2 if y2 is not None else line.b.y)
            line.a = a
            line.b = b
            self.app.params.lines[idx] = line

        self._apply_change(_do)

    def _update_line(
        self,
        idx: int,
        *,
        width: int | None = None,
        capstyle: CapStyle | None = None,
        style: LineStyle | None = None,
        colour: Colour | None = None,
        snap: bool | None = None,
        dash_offset: int | None = None,
    ) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.lines):
                return
            line = self.app.params.lines[idx]
            if width is not None:
                line.width = int(width)
            if capstyle is not None:
                line.capstyle = capstyle
            if style is not None:
                line.style = style
            if colour is not None:
                line.col = colour
            if snap is not None:
                line.snap = bool(snap)
            if dash_offset is not None:
                line.dash_offset = int(dash_offset)
            self.app.params.lines[idx] = line

        self._apply_change(_do)

    def _snap_line(self, idx: int) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.lines):
                return
            line = self.app.params.lines[idx]
            line.a = self.app.snap(line.a)
            line.b = self.app.snap(line.b)
            self.app.params.lines[idx] = line

        self._apply_change(_do)
        self.set_target(HitKind.line, idx, force=True)

    def _update_label_coords(self, idx: int, *, x: int | None = None, y: int | None = None) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.labels):
                return
            lab = self.app.params.labels[idx]
            p = Point(x=x if x is not None else lab.p.x, y=y if y is not None else lab.p.y)
            lab.p = p
            self.app.params.labels[idx] = lab

        self._apply_change(_do)

    def _update_label(
        self,
        idx: int,
        *,
        size: int | None = None,
        rotation: int | None = None,
        anchor: Anchor | None = None,
        colour: Colour | None = None,
        snap: bool | None = None,
    ) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.labels):
                return
            lab = self.app.params.labels[idx]
            if size is not None:
                lab.size = int(size)
            if rotation is not None:
                lab.rotation = int(rotation)
            if anchor is not None:
                lab.anchor = anchor
            if colour is not None:
                lab.col = colour
            if snap is not None:
                lab.snap = bool(snap)
            self.app.params.labels[idx] = lab

        self._apply_change(_do)

    def _update_label_text(self, idx: int, text: str) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.labels):
                return
            lab = self.app.params.labels[idx]
            lab.text = text
            self.app.params.labels[idx] = lab

        self._apply_change(_do)

    def _snap_label(self, idx: int) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.labels):
                return
            lab = self.app.params.labels[idx]
            lab.p = self.app.snap(lab.p)
            self.app.params.labels[idx] = lab

        self._apply_change(_do)
        self.set_target(HitKind.label, idx, force=True)

    def _update_icon_coords(self, idx: int, *, x: int | None = None, y: int | None = None) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.icons):
                return
            ico = self.app.params.icons[idx]
            p = Point(x=x if x is not None else ico.p.x, y=y if y is not None else ico.p.y)
            ico.p = p
            self.app.params.icons[idx] = ico

        self._apply_change(_do)

    def _update_icon(
        self,
        idx: int,
        *,
        name: IconName | None = None,
        size: int | None = None,
        rotation: int | None = None,
        anchor: Anchor | None = None,
        colour: Colour | None = None,
        snap: bool | None = None,
    ) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.icons):
                return
            ico = self.app.params.icons[idx]
            if isinstance(ico, BuiltinIcon) and name is not None:
                ico.name = name
            if size is not None:
                ico.size = int(size)
            if rotation is not None:
                ico.rotation = int(rotation)
            if anchor is not None:
                ico.anchor = anchor
            if colour is not None and isinstance(ico, BuiltinIcon):
                ico.col = colour
            if snap is not None:
                ico.snap = bool(snap)
            self.app.params.icons[idx] = ico

        self._apply_change(_do)

    def _snap_icon(self, idx: int) -> None:
        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.icons):
                return
            ico = self.app.params.icons[idx]
            ico.p = self.app.snap(ico.p)
            self.app.params.icons[idx] = ico

        self._apply_change(_do)
        self.set_target(HitKind.icon, idx, force=True)

    def _pick_icon_picture(self, idx: int, edit: QtWidgets.QLineEdit) -> None:
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Choose picture icon",
            str(self.app.project_dir()),
            "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)",
        )
        if not path:
            return

        def _do() -> None:
            if idx < 0 or idx >= len(self.app.params.icons):
                return
            ico = self.app.params.icons[idx]
            if isinstance(ico, PictureIcon):
                ico.src = Path(path)
                self.app.params.icons[idx] = ico

        self._apply_change(_do)
        edit.setText(path)

    # ---------- helpers ----------
    def _apply_change(self, updater: Callable[[], None]) -> None:
        if self._syncing:
            return
        updater()
        self.app.redraw()
        self.app.mark_dirty()

    def _spin_int(
        self, value: int, min_v: int, max_v: int, on_change: Callable[[int], None]
    ) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(int(value))
        spin.valueChanged.connect(lambda v: self._guarded(on_change, v))
        return spin

    def _combo(
        self, values: list[TCombo], current: TCombo, on_change: Callable[[TCombo], None]
    ) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        for v in values:
            label = getattr(v, "value", None)
            label_text = str(label) if label is not None else str(v)
            combo.addItem(label_text, v)
        self._set_combo(combo, current)
        combo.currentIndexChanged.connect(
            lambda _idx: self._guarded(on_change, cast(TCombo, combo.currentData()))
        )
        return combo

    def _line_style_combo(
        self, current: LineStyle, on_change: Callable[[LineStyle], None]
    ) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        icon_size = QtCore.QSize(60, 12)
        combo.setIconSize(icon_size)
        combo.setMinimumContentsLength(10)
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        colour = combo.palette().color(QtGui.QPalette.ColorRole.Text)
        for style in LineStyle:
            combo.addItem(line_style_icon(style, icon_size, colour), style.value, style.value)
        self._set_combo(combo, current)
        combo.view().setMinimumWidth(combo.sizeHint().width())

        def _apply_style() -> None:
            raw = combo.currentData()
            try:
                parsed = LineStyle(str(raw))
            except ValueError:
                return
            self._guarded(on_change, parsed)

        combo.currentIndexChanged.connect(lambda _idx: _apply_style())
        return combo

    def _colour_button(
        self, get_colour: Callable[[], Colour], on_change: Callable[[Colour], None]
    ) -> QtWidgets.QPushButton:
        btn = QtWidgets.QPushButton()
        btn.setFixedWidth(90)
        self._set_button_colour(btn, get_colour())

        def _pick() -> None:
            col = self._pick_colour(get_colour())
            if col is None:
                return
            on_change(col)
            self._set_button_colour(btn, col)

        btn.clicked.connect(_pick)
        return btn

    def _pick_colour(self, current: Colour) -> Colour | None:
        start = QtGui.QColor(current.red, current.green, current.blue, current.alpha)
        col = QtWidgets.QColorDialog.getColor(
            start,
            self,
            "Choose colour",
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not col.isValid():
            return None
        return Colour(red=col.red(), green=col.green(), blue=col.blue(), alpha=col.alpha())

    @staticmethod
    def _set_button_colour(btn: QtWidgets.QPushButton, col: Colour) -> None:
        btn.setStyleSheet(f"QPushButton {{background-color: rgba({col.red}, {col.green}, {col.blue}, {col.alpha});}}")
        btn.setText(col.hexh)

    def _set_combo(self, combo: QtWidgets.QComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    def _guarded(self, fn: Callable[[TGuard], None], value: TGuard) -> None:
        if self._syncing:
            return
        fn(value)

    def _clear_form(self) -> None:
        while self._form_layout.count():
            item = self._form_layout.takeAt(0)
            widget = item.widget()
            layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if layout is not None:
                self._clear_layout(layout)

    def _clear_layout(self, layout: QtWidgets.QLayout) -> None:
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            child_layout = item.layout()
            if widget is not None:
                widget.deleteLater()
            if child_layout is not None:
                self._clear_layout(child_layout)

    def _set_spin_value(self, key: str, value: int) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QtWidgets.QSpinBox) and not widget.hasFocus():
            widget.setValue(int(value))

    def _set_combo_value(self, key: str, value: object) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QtWidgets.QComboBox) and not widget.hasFocus():
            self._set_combo(widget, value)

    def _set_check_value(self, key: str, value: bool) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QtWidgets.QCheckBox) and not widget.hasFocus():
            widget.setChecked(bool(value))

    def _set_line_text(self, key: str, value: str) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QtWidgets.QLineEdit) and not widget.hasFocus():
            widget.setText(value)

    def _set_button_colour_for_key(self, key: str, col: Colour) -> None:
        widget = self._widgets.get(key)
        if isinstance(widget, QtWidgets.QPushButton):
            self._set_button_colour(widget, col)
