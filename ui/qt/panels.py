"""Qt panels and sidebars for Linework."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtWidgets

from models.geo import IconSource, IconType
from models.styling import Anchor, Colour, Colours, LineStyle
from ui.qt.palette import ColourPaletteButton

if TYPE_CHECKING:
    from qt.app import QtApp


class SettingsPanel(QtWidgets.QWidget):
    """Basic settings controls for the Qt frontend."""

    def __init__(self, app: QtApp) -> None:
        """Create the settings panel.

        Args;
            app: The parent Qt app.
        """
        super().__init__(app)
        self.app = app

        layout = QtWidgets.QFormLayout(self)
        layout.setLabelAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)
        layout.setFieldGrowthPolicy(QtWidgets.QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)

        layout.addRow(self._section_label("Select"))
        layout.addRow("Grid visible", self._grid_visible_control())
        grid_step = max(1, int(self.app.params.grid_step))
        grid_size = int(self.app.params.grid_size)
        canvas_step = grid_size if grid_size > 0 else 1
        self._grid_size_spin = self._spin_int(
            self.app.params.grid_size, 0, 1000, self._on_grid_size, step=grid_step, tracking=False
        )
        self._canvas_width_spin = self._spin_int(
            self.app.params.width, 64, 10000, self._on_canvas_width, step=canvas_step, tracking=False
        )
        self._canvas_height_spin = self._spin_int(
            self.app.params.height, 64, 10000, self._on_canvas_height, step=canvas_step, tracking=False
        )
        layout.addRow("Grid size", self._grid_size_spin)
        layout.addRow("Width", self._canvas_width_spin)
        layout.addRow("Height", self._canvas_height_spin)

        layout.addRow(self._section_label("Drawing"))
        layout.addRow("Brush width", self._spin_int(self.app.params.brush_width, 1, 200, self._on_brush_width))
        layout.addRow("Line style", self._line_style_control())
        layout.addRow("Dash offset", self._spin_int(self.app.params.line_dash_offset, 0, 2000, self._on_dash_offset))
        layout.addRow("Drag to draw", self._toggle(self.app.params.drag_to_draw, self._on_drag_to_draw))
        layout.addRow("Continuous draw", self._toggle(self.app.params.continuous_draw, self._on_continuous_draw))
        layout.addRow("Cardinal snap", self._toggle(self.app.params.cardinal_snap, self._on_cardinal_snap))

        layout.addRow(self._section_label("Colours"))
        layout.addRow("Brush", self._palette_button(self.app.params.brush_colour, self._on_brush_colour))
        layout.addRow("Background", self._palette_button(self.app.params.bg_colour, self._on_bg_colour))
        layout.addRow("Grid", self._palette_button(self.app.params.grid_colour, self._on_grid_colour))
        layout.addRow("Label", self._palette_button(self.app.params.label_colour, self._on_label_colour))
        layout.addRow("Icon", self._palette_button(self.app.params.icon_colour, self._on_icon_colour))

        layout.addRow(self._section_label("Labels"))
        layout.addRow("Size", self._spin_int(self.app.params.label_size, 6, 200, self._on_label_size))
        layout.addRow("Rotation", self._spin_int(self.app.params.label_rotation, 0, 360, self._on_label_rotation))
        layout.addRow("Anchor", self._anchor_control(self.app.params.label_anchor, self._on_label_anchor))

        layout.addRow(self._section_label("Icons"))
        layout.addRow("Size", self._spin_int(self.app.params.icon_size, 8, 512, self._on_icon_size))
        layout.addRow("Picture size", self._spin_int(self.app.params.picture_size, 16, 1024, self._on_picture_size))
        layout.addRow("Rotation", self._spin_int(self.app.params.icon_rotation, 0, 360, self._on_icon_rotation))
        layout.addRow("Anchor", self._anchor_control(self.app.params.icon_anchor, self._on_icon_anchor))
        layout.addRow("Current icon", self._icon_picker_control())

        layout.addRow(self._section_label("Info"))
        layout.addRow("Project", QtWidgets.QLabel(self.app.project_display_path()))

    # ---------- controls ----------
    @staticmethod
    def _section_label(text: str) -> QtWidgets.QLabel:
        lab = QtWidgets.QLabel(text)
        font = lab.font()
        font.setBold(True)
        lab.setFont(font)
        return lab

    def _toggle(self, value: bool, on_change: Callable[[bool], None]) -> QtWidgets.QCheckBox:
        chk = QtWidgets.QCheckBox()
        chk.setChecked(bool(value))
        chk.toggled.connect(on_change)
        return chk

    def _spin_int(
        self,
        value: int,
        min_v: int,
        max_v: int,
        on_change: Callable[[int], None],
        *,
        step: int | None = None,
        tracking: bool | None = None,
    ) -> QtWidgets.QSpinBox:
        spin = QtWidgets.QSpinBox()
        spin.setRange(min_v, max_v)
        spin.setValue(int(value))
        if step is not None:
            spin.setSingleStep(step)
        if tracking is not None:
            spin.setKeyboardTracking(tracking)
        spin.valueChanged.connect(on_change)
        return spin

    def _line_style_control(self) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        for style in LineStyle:
            combo.addItem(style.value, style)
        self._set_combo_value(combo, self.app.params.line_style)
        combo.currentIndexChanged.connect(lambda _idx: self._on_line_style(combo))
        return combo

    def _anchor_control(self, current: Anchor, on_change: Callable[[QtWidgets.QComboBox], None]) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        for anchor in Anchor:
            combo.addItem(anchor.value, anchor)
        self._set_combo_value(combo, current)
        combo.currentIndexChanged.connect(lambda _idx: on_change(combo))
        return combo

    def _grid_visible_control(self) -> QtWidgets.QWidget:
        box = QtWidgets.QCheckBox()
        box.setChecked(bool(self.app.params.grid_visible))
        box.toggled.connect(self._on_grid_visible)
        return box

    def _palette_button(self, col: Colour, on_pick: Callable[[str], None]) -> ColourPaletteButton:
        btn = ColourPaletteButton(
            self,
            Colours.list(min_alpha=25),
            selected=col,
            on_select=on_pick,
            custom=self.app.params.custom_palette,
            on_update_custom=self._on_update_custom_palette,
        )
        return btn

    def _icon_picker_control(self) -> QtWidgets.QWidget:
        btn = QtWidgets.QPushButton()
        btn.clicked.connect(lambda _checked=False, b=btn: self._on_pick_icon(b))
        self._set_icon_button_text(btn, self.app.params.default_icon)
        return btn

    @staticmethod
    def _sync_spin_value(widget: QtWidgets.QSpinBox | None, value: int) -> None:
        if widget is None or widget.value() == value:
            return
        widget.blockSignals(True)
        widget.setValue(int(value))
        widget.blockSignals(False)

    # ---------- handlers ----------
    def _on_grid_visible(self, checked: bool) -> None:
        self.app.params.grid_visible = bool(checked)
        self.app.redraw()
        self.app.mark_dirty()

    def _on_grid_size(self, value: int) -> None:
        snapped = self.app._snap_grid_size_value(value)
        self._sync_spin_value(self._grid_size_spin, snapped)
        self.app.params.grid_size = int(snapped)
        self._update_canvas_steps()
        width = self.app._snap_canvas_dimension(self.app.params.width, min_value=64, max_value=10000)
        height = self.app._snap_canvas_dimension(self.app.params.height, min_value=64, max_value=10000)
        if width != self.app.params.width or height != self.app.params.height:
            self.app.params.width = int(width)
            self.app.params.height = int(height)
            self._sync_spin_value(self._canvas_width_spin, width)
            self._sync_spin_value(self._canvas_height_spin, height)
            self.app._sync_view_size()
        self.app.redraw()
        self.app.mark_dirty()

    def _on_canvas_width(self, value: int) -> None:
        snapped = self.app._snap_canvas_dimension(value, min_value=64, max_value=10000)
        self._sync_spin_value(self._canvas_width_spin, snapped)
        self.app.params.width = int(snapped)
        self.app._sync_view_size()
        self.app.redraw()
        self.app.mark_dirty()

    def _on_canvas_height(self, value: int) -> None:
        snapped = self.app._snap_canvas_dimension(value, min_value=64, max_value=10000)
        self._sync_spin_value(self._canvas_height_spin, snapped)
        self.app.params.height = int(snapped)
        self.app._sync_view_size()
        self.app.redraw()
        self.app.mark_dirty()

    def _update_canvas_steps(self) -> None:
        step = int(self.app.params.grid_size)
        if step <= 0:
            step = 1
        if self._canvas_width_spin is not None:
            self._canvas_width_spin.setSingleStep(step)
        if self._canvas_height_spin is not None:
            self._canvas_height_spin.setSingleStep(step)

    def _on_brush_width(self, value: int) -> None:
        self.app.params.brush_width = int(value)
        self.app.mark_dirty()

    def _on_line_style(self, combo: QtWidgets.QComboBox) -> None:
        style = combo.currentData()
        if isinstance(style, LineStyle):
            self.app.params.line_style = style
            self.app.mark_dirty()

    def _on_dash_offset(self, value: int) -> None:
        self.app.params.line_dash_offset = int(value)
        self.app.mark_dirty()

    def _on_drag_to_draw(self, checked: bool) -> None:
        self.app.params.drag_to_draw = bool(checked)
        self.app.mark_dirty()

    def _on_continuous_draw(self, checked: bool) -> None:
        self.app.params.continuous_draw = bool(checked)
        self.app.mark_dirty()

    def _on_cardinal_snap(self, checked: bool) -> None:
        self.app.params.cardinal_snap = bool(checked)
        self.app.mark_dirty()

    def _on_brush_colour(self, hexa: str) -> None:
        col = Colours.parse_colour(hexa)
        self.app.params.brush_colour = col
        self.app.mark_dirty()

    def _on_bg_colour(self, hexa: str) -> None:
        col = Colours.parse_colour(hexa)
        self.app.params.bg_colour = col
        self.app.redraw()
        self.app.mark_dirty()

    def _on_grid_colour(self, hexa: str) -> None:
        col = Colours.parse_colour(hexa)
        self.app.params.grid_colour = col
        self.app.redraw()
        self.app.mark_dirty()

    def _on_label_colour(self, hexa: str) -> None:
        col = Colours.parse_colour(hexa)
        self.app.params.label_colour = col
        self.app.mark_dirty()

    def _on_icon_colour(self, hexa: str) -> None:
        col = Colours.parse_colour(hexa)
        self.app.params.icon_colour = col
        self.app.mark_dirty()

    def _on_label_size(self, value: int) -> None:
        self.app.params.label_size = int(value)
        self.app.mark_dirty()

    def _on_label_rotation(self, value: int) -> None:
        self.app.params.label_rotation = int(value)
        self.app.mark_dirty()

    def _on_label_anchor(self, combo: QtWidgets.QComboBox) -> None:
        anchor = combo.currentData()
        if isinstance(anchor, Anchor):
            self.app.params.label_anchor = anchor
            self.app.mark_dirty()

    def _on_icon_anchor(self, combo: QtWidgets.QComboBox) -> None:
        anchor = combo.currentData()
        if isinstance(anchor, Anchor):
            self.app.params.icon_anchor = anchor
            self.app.mark_dirty()

    def _on_icon_size(self, value: int) -> None:
        self.app.params.icon_size = int(value)
        self.app.mark_dirty()

    def _on_picture_size(self, value: int) -> None:
        self.app.params.picture_size = int(value)
        self.app.mark_dirty()

    def _on_icon_rotation(self, value: int) -> None:
        self.app.params.icon_rotation = int(value)
        self.app.mark_dirty()

    def _on_pick_icon(self, btn: QtWidgets.QPushButton) -> None:
        src = self.app.pick_icon_source()
        if src is None:
            return
        self.app.current_icon = src
        self.app.params.default_icon = src
        self._set_icon_button_text(btn, src)
        self.app.mark_dirty()

    # ---------- helpers ----------
    def _on_update_custom_palette(self, idx: int, col: Colour | None) -> None:
        self.app.update_custom_palette(idx, col)

    @staticmethod
    def _set_combo_value(combo: QtWidgets.QComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    @staticmethod
    def _set_icon_button_text(btn: QtWidgets.QPushButton, src: IconSource) -> None:
        if src.kind is IconType.builtin and src.name:
            btn.setText(src.name.value)
        elif src.kind is IconType.picture and src.src:
            btn.setText(src.src.name)
        else:
            btn.setText("Pick icon")
