"""Top settings bar with tabbed, wrapping controls."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from models.geo import IconSource, IconType
from models.styling import Anchor, Colour, Colours, LineStyle
from qt.tools.base import ToolName
from ui.qt.flow_layout import FlowLayout
from ui.qt.icon_picker import _builtin_pixmap, _picture_pixmap
from ui.qt.line_style_icons import line_style_icon
from ui.qt.palette import ColourPaletteButton

if TYPE_CHECKING:
    from qt.app import QtApp


class _IconIndicator(QtWidgets.QWidget):
    def __init__(self, app: QtApp, size: int = 18) -> None:
        super().__init__()
        self._app = app
        self._size = size

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self._preview = QtWidgets.QLabel()
        self._preview.setFixedSize(size, size)
        self._preview.setScaledContents(True)
        layout.addWidget(self._preview)

        self._text = QtWidgets.QLabel()
        layout.addWidget(self._text)

        self.set_source(self._app.current_icon or self._app.params.default_icon)

    def set_source(self, src: IconSource | None) -> None:
        if src is None:
            self._text.setText("None")
            self._text.setToolTip("")
            self._preview.clear()
            return

        if src.kind is IconType.builtin:
            name = src.name.value if src.name else "builtin"
            text = f"Built-in: {name}"
            tooltip = text
        else:
            name = Path(src.src).name if src.src else "picture"
            text = f"Picture: {name}"
            tooltip = str(src.src) if src.src else text

        self._text.setText(text)
        self._text.setToolTip(tooltip)

        pixmap = self._pixmap_for_source(src)
        if pixmap is None:
            self._preview.clear()
        else:
            self._preview.setPixmap(pixmap)

    def _pixmap_for_source(self, src: IconSource) -> QtGui.QPixmap | None:
        if src.kind is IconType.builtin and src.name:
            colour = self.palette().color(QtGui.QPalette.ColorRole.Text)
            return _builtin_pixmap(src.name, self._size, colour)
        if src.kind is IconType.picture and src.src:
            return _picture_pixmap(Path(src.src), self._size)
        return None


class QtSettingsBar(QtWidgets.QWidget):
    """Tabbed settings bar for the Qt frontend."""

    def __init__(self, app: QtApp) -> None:
        """Create the settings bar widget.

        Args;
            app: The parent Qt app.
        """
        super().__init__(app)
        self.app = app
        self._tab_index: dict[str, int] = {}
        self._syncing = False
        self._ready = False
        self._canvas_width_spin: QtWidgets.QSpinBox | None = None
        self._canvas_height_spin: QtWidgets.QSpinBox | None = None
        self._grid_size_spin: QtWidgets.QSpinBox | None = None
        self._label_snap_toggle: QtWidgets.QCheckBox | None = None
        self._icon_snap_toggle: QtWidgets.QCheckBox | None = None
        self._icon_indicator: _IconIndicator | None = None

        self._layout = QtWidgets.QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)

        self.tabs = QtWidgets.QTabWidget(self)
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabBar().setDrawBase(False)
        self.tabs.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        self.tabs.tabBar().setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)
        self.tabs.setStyleSheet(
            "QTabWidget::pane { border: 0; margin: 0; }QTabBar::tab { padding: 1px 4px; margin: 0px; }"
        )
        self._layout.addWidget(self.tabs)

        self._build_tabs()
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._ready = True
        self.sync_snap_overrides()

    # ---------- public ----------
    def set_active_tool(self, tool: ToolName) -> None:
        """Select the tab corresponding to the active tool.

        Args;
            tool: The active tool.
        """
        name = tool.value if isinstance(tool, ToolName) else str(tool)
        tab = {
            ToolName.draw.value: "Draw",
            ToolName.erase.value: "Draw",
            ToolName.label.value: "Label",
            ToolName.icon.value: "Icon",
            ToolName.select.value: "Canvas | Select",
        }.get(name)
        if not tab:
            return
        idx = self._tab_index.get(tab)
        if idx is not None:
            self._syncing = True
            self.tabs.blockSignals(True)
            try:
                self.tabs.setCurrentIndex(idx)
            finally:
                self.tabs.blockSignals(False)
                self._syncing = False
            self.updateGeometry()

    def sync_snap_overrides(self, *, alt_down: bool | None = None) -> None:
        """Sync snap toggles to reflect modifier overrides."""
        if alt_down is None:
            alt_down = bool(QtGui.QGuiApplication.keyboardModifiers() & QtCore.Qt.KeyboardModifier.AltModifier)
        label_snap = bool(self.app.params.label_snap) ^ bool(alt_down)
        icon_snap = bool(self.app.params.icon_snap) ^ bool(alt_down)
        self._sync_toggle_value(self._label_snap_toggle, label_snap)
        self._sync_toggle_value(self._icon_snap_toggle, icon_snap)

    def sync_current_icon(self) -> None:
        """Sync the icon indicator to the current selection."""
        if self._icon_indicator is None:
            return
        src = self.app.current_icon or self.app.params.default_icon
        self._icon_indicator.set_source(src)

    def sizeHint(self) -> QtCore.QSize:
        """Return a size hint for the widget.

        Returns;
            The suggested size.
        """
        base_w = max(1, self.tabs.sizeHint().width())
        height = self._calc_size_for_width(self._hint_width(base_w)).height()
        return QtCore.QSize(base_w, height)

    def minimumSizeHint(self) -> QtCore.QSize:
        """Return the minimum size hint for the widget.

        Returns;
            The minimum suggested size.
        """
        base_w = max(1, self.tabs.minimumSizeHint().width())
        height = self._calc_size_for_width(self._hint_width(base_w)).height()
        return QtCore.QSize(base_w, height)

    def hasHeightForWidth(self) -> bool:
        """Return True if height depends on width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Compute the height for a given width.

        Args;
            width: The available width.

        Returns;
            The calculated height.
        """
        return self._calc_size_for_width(max(1, width)).height()

    def resizeEvent(self, event: QtGui.QResizeEvent) -> None:  # type: ignore[override]
        """Handle resize events.

        Args;
            event: The Qt resize event.
        """
        super().resizeEvent(event)
        self.updateGeometry()

    # ---------- builders ----------
    def _build_tabs(self) -> None:
        self._tab_index.clear()
        self._add_canvas_tab()
        self._add_draw_tab()
        self._add_label_tab()
        self._add_icon_tab()

    def _add_canvas_tab(self) -> None:
        tab = self._new_flow_tab("Canvas | Select")
        add = tab.layout().addWidget  # type: ignore[no-any-return]

        grid_size = int(self.app.params.grid_size)
        canvas_step = grid_size if grid_size > 0 else 1
        self._canvas_width_spin = self._spin_int(
            self.app.params.width, 64, 10000, self._on_canvas_width, step=canvas_step, tracking=False
        )
        self._canvas_height_spin = self._spin_int(
            self.app.params.height, 64, 10000, self._on_canvas_height, step=canvas_step, tracking=False
        )
        grid_step = max(1, int(self.app.params.grid_step))
        self._grid_size_spin = self._spin_int(
            self.app.params.grid_size, 0, 1000, self._on_grid_size, step=grid_step, tracking=False
        )
        add(self._row("W", self._canvas_width_spin))
        add(self._row("H", self._canvas_height_spin))
        add(self._row("Grid", self._grid_size_spin))
        add(self._row("Show", self._toggle(self.app.params.grid_visible, self._on_grid_visible)))
        add(self._row("Grid", self._palette_button(self.app.params.grid_colour, self._on_grid_colour)))
        add(self._row("BG", self._palette_button(self.app.params.bg_colour, self._on_bg_colour)))

    def _add_draw_tab(self) -> None:
        tab = self._new_flow_tab("Draw")
        add = tab.layout().addWidget  # type: ignore[no-any-return]

        add(self._row("Drag", self._toggle(self.app.params.drag_to_draw, self._on_drag_to_draw)))
        add(self._row("Cont", self._toggle(self.app.params.continuous_draw, self._on_continuous_draw)))
        add(self._row("Cardinal", self._toggle(self.app.params.cardinal_snap, self._on_cardinal_snap)))
        add(self._row("Line", self._spin_int(self.app.params.brush_width, 1, 200, self._on_brush_width)))
        add(self._row("Style", self._line_style_control(self.app.params.line_style, self._on_line_style)))
        add(self._row("Dash", self._spin_int(self.app.params.line_dash_offset, 0, 2000, self._on_dash_offset)))
        add(self._row("Brush", self._palette_button(self.app.params.brush_colour, self._on_brush_colour)))

    def _add_label_tab(self) -> None:
        tab = self._new_flow_tab("Label")
        add = tab.layout().addWidget  # type: ignore[no-any-return]

        add(self._row("Size", self._spin_int(self.app.params.label_size, 6, 200, self._on_label_size)))
        add(self._row("Rot", self._spin_int(self.app.params.label_rotation, 0, 360, self._on_label_rotation)))
        add(self._row("Anchor", self._anchor_control(self.app.params.label_anchor, self._on_label_anchor)))
        self._label_snap_toggle = self._toggle(self.app.params.label_snap, self._on_label_snap)
        add(self._row("Snap", self._label_snap_toggle))
        add(self._row("Colour", self._palette_button(self.app.params.label_colour, self._on_label_colour)))

    def _add_icon_tab(self) -> None:
        tab = self._new_flow_tab("Icon")
        add = tab.layout().addWidget  # type: ignore[no-any-return]

        self._icon_indicator = _IconIndicator(self.app)
        add(self._row("Current", self._icon_indicator))

        add(self._row("Size", self._spin_int(self.app.params.icon_size, 8, 512, self._on_icon_size)))
        add(
            self._row(
                "Pic size",
                self._spin_int(self.app.params.picture_size, 16, 1024, self._on_picture_size),
            )
        )
        add(self._row("Rot", self._spin_int(self.app.params.icon_rotation, 0, 360, self._on_icon_rotation)))
        add(self._row("Anchor", self._anchor_control(self.app.params.icon_anchor, self._on_icon_anchor)))
        self._icon_snap_toggle = self._toggle(self.app.params.icon_snap, self._on_icon_snap)
        add(self._row("Snap", self._icon_snap_toggle))
        add(self._row("Colour", self._palette_button(self.app.params.icon_colour, self._on_icon_colour)))

    def _new_flow_tab(self, title: str) -> QtWidgets.QWidget:
        tab = QtWidgets.QWidget()
        tab.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Minimum)
        flow = FlowLayout(tab, margin=0, spacing=2)
        tab.setLayout(flow)
        self._tab_index[title] = self.tabs.addTab(tab, title)
        return tab

    def _row(self, label: str, widget: QtWidgets.QWidget) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        row.setSizePolicy(QtWidgets.QSizePolicy.Policy.Fixed, QtWidgets.QSizePolicy.Policy.Minimum)
        lay = QtWidgets.QHBoxLayout(row)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(1)
        lab = QtWidgets.QLabel(label)
        lay.addWidget(lab)
        lay.addWidget(widget)
        return row

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
        spin.setMaximumWidth(60)
        if step is not None:
            spin.setSingleStep(step)
        if tracking is not None:
            spin.setKeyboardTracking(tracking)
        spin.valueChanged.connect(on_change)
        return spin

    def _line_style_control(
        self, current: LineStyle, on_change: Callable[[QtWidgets.QComboBox], None]
    ) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        icon_size = QtCore.QSize(60, 12)
        combo.setIconSize(icon_size)
        colour = combo.palette().color(QtGui.QPalette.ColorRole.Text)
        for style in LineStyle:
            combo.addItem(line_style_icon(style, icon_size, colour), style.value, style.value)
        combo.setMinimumContentsLength(10)
        combo.setMaximumWidth(220)
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._set_combo_value(combo, current)
        combo.view().setMinimumWidth(combo.sizeHint().width())
        combo.currentIndexChanged.connect(lambda _idx: on_change(combo))
        return combo

    def _anchor_control(self, current: Anchor, on_change: Callable[[QtWidgets.QComboBox], None]) -> QtWidgets.QComboBox:
        combo = QtWidgets.QComboBox()
        for anchor in Anchor:
            combo.addItem(anchor.value, anchor)
        combo.setMinimumContentsLength(6)
        combo.setMaximumWidth(120)
        combo.setSizeAdjustPolicy(QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self._set_combo_value(combo, current)
        combo.currentIndexChanged.connect(lambda _idx: on_change(combo))
        return combo

    def _palette_button(self, col: Colour, on_pick: Callable[[str], None]) -> ColourPaletteButton:
        btn = ColourPaletteButton(
            self,
            Colours.list(min_alpha=25),
            selected=col,
            on_select=on_pick,
            custom=self.app.params.custom_palette,
            on_update_custom=self._on_update_custom_palette,
        )
        btn.setIconSize(QtCore.QSize(18, 18))
        btn.setFixedSize(24, 24)
        return btn

    def _hint_width(self, fallback: int) -> int:
        width = self.width()
        if width <= 0:
            width = fallback
        return max(1, width)

    def _on_update_custom_palette(self, idx: int, col: Colour | None) -> None:
        self.app.update_custom_palette(idx, col)

    @staticmethod
    def _set_combo_value(combo: QtWidgets.QComboBox, value: object) -> None:
        for i in range(combo.count()):
            if combo.itemData(i) == value:
                combo.setCurrentIndex(i)
                return

    @staticmethod
    def _sync_spin_value(widget: QtWidgets.QSpinBox | None, value: int) -> None:
        if widget is None or widget.value() == value:
            return
        widget.blockSignals(True)
        widget.setValue(int(value))
        widget.blockSignals(False)

    @staticmethod
    def _sync_toggle_value(widget: QtWidgets.QCheckBox | None, checked: bool) -> None:
        if widget is None or widget.isChecked() == checked:
            return
        widget.blockSignals(True)
        widget.setChecked(bool(checked))
        widget.blockSignals(False)

    def _update_canvas_steps(self) -> None:
        step = int(self.app.params.grid_size)
        if step <= 0:
            step = 1
        if self._canvas_width_spin is not None:
            self._canvas_width_spin.setSingleStep(step)
        if self._canvas_height_spin is not None:
            self._canvas_height_spin.setSingleStep(step)

    def _calc_size_for_width(self, width: int) -> QtCore.QSize:
        tab_bar_h = self.tabs.tabBar().sizeHint().height()
        body_w = max(1, width)
        if self.tabs.count() == 0:
            body_h = self.tabs.sizeHint().height()
        else:
            # Reserve space for the tallest tab to avoid canvas scrollbars on tab changes.
            body_h = 0
            for idx in range(self.tabs.count()):
                body_h = max(body_h, self._tab_body_height(self.tabs.widget(idx), body_w))
        margins = self._layout.contentsMargins()
        return QtCore.QSize(width, tab_bar_h + body_h + margins.top() + margins.bottom())

    @staticmethod
    def _tab_body_height(tab: QtWidgets.QWidget | None, body_w: int) -> int:
        if tab is None:
            return 0
        layout = tab.layout()
        if layout and layout.hasHeightForWidth():
            return layout.heightForWidth(body_w)
        return tab.sizeHint().height()

    def _on_tab_changed(self, idx: int) -> None:
        if not self._ready or self._syncing:
            return
        title = self.tabs.tabText(idx)
        mapping = {
            "Select": ToolName.select,
            "Canvas | Select": ToolName.select,
            "Draw": ToolName.draw,
            "Label": ToolName.label,
            "Icon": ToolName.icon,
        }
        tool = mapping.get(title)
        if tool is None:
            return
        if getattr(self.app.tool_mgr.current, "name", None) == tool:
            return
        self.app.tool_mgr.activate(tool)

    # ---------- handlers ----------
    def _on_canvas_width(self, value: int) -> None:
        snapped = self.app._snap_canvas_dimension(value, min_value=64, max_value=10000)
        self._sync_spin_value(self._canvas_width_spin, snapped)
        self.app.params.width = int(snapped)
        self.app._sync_view_size()
        self.app.redraw()
        self.app.mark_dirty()
        self.app.status.temp(f"Canvas {self.app.params.width}x{self.app.params.height}")

    def _on_canvas_height(self, value: int) -> None:
        snapped = self.app._snap_canvas_dimension(value, min_value=64, max_value=10000)
        self._sync_spin_value(self._canvas_height_spin, snapped)
        self.app.params.height = int(snapped)
        self.app._sync_view_size()
        self.app.redraw()
        self.app.mark_dirty()
        self.app.status.temp(f"Canvas {self.app.params.width}x{self.app.params.height}")

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

    def _on_grid_visible(self, checked: bool) -> None:
        self.app.params.grid_visible = bool(checked)
        self.app.redraw()
        self.app.mark_dirty()
        self.app.status.temp("Grid ON" if self.app.params.grid_visible else "Grid OFF")

    def _on_grid_colour(self, hexa: str) -> None:
        self.app.params.grid_colour = Colours.parse_colour(hexa)
        self.app.redraw()
        self.app.mark_dirty()

    def _on_bg_colour(self, hexa: str) -> None:
        self.app.params.bg_colour = Colours.parse_colour(hexa)
        self.app.redraw()
        self.app.mark_dirty()

    def _on_drag_to_draw(self, checked: bool) -> None:
        self.app.params.drag_to_draw = bool(checked)
        self.app.mark_dirty()
        self.app.status.set_centre("Draw: drag to draw" if checked else "Draw: click-click mode")

    def _on_continuous_draw(self, checked: bool) -> None:
        self.app.params.continuous_draw = bool(checked)
        self.app.mark_dirty()
        self.app.status.set_centre("Draw: continuous on" if checked else "Draw: continuous off")

    def _on_cardinal_snap(self, checked: bool) -> None:
        self.app.params.cardinal_snap = bool(checked)
        self.app.mark_dirty()
        self.app.status.set_centre("Draw: Cardinal Snap" if checked else "Draw: Grid Snap")

    def _on_brush_width(self, value: int) -> None:
        self.app.params.brush_width = int(value)
        self.app.mark_dirty()
        self.app.status.temp(f"Line width: {self.app.params.brush_width}")

    def _on_line_style(self, combo: QtWidgets.QComboBox) -> None:
        style = combo.currentData()
        try:
            parsed = LineStyle(str(style))
        except ValueError:
            return
        self.app.params.line_style = parsed
        self.app.mark_dirty()
        self.app.status.temp(f"Line style: {parsed.value}")

    def _on_dash_offset(self, value: int) -> None:
        self.app.params.line_dash_offset = int(value)
        self.app.mark_dirty()

    def _on_brush_colour(self, hexa: str) -> None:
        self.app.params.brush_colour = Colours.parse_colour(hexa)
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

    def _on_label_snap(self, checked: bool) -> None:
        self.app.params.label_snap = bool(checked)
        self.app.mark_dirty()
        self.sync_snap_overrides()

    def _on_label_colour(self, hexa: str) -> None:
        self.app.params.label_colour = Colours.parse_colour(hexa)
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

    def _on_icon_anchor(self, combo: QtWidgets.QComboBox) -> None:
        anchor = combo.currentData()
        if isinstance(anchor, Anchor):
            self.app.params.icon_anchor = anchor
            self.app.mark_dirty()

    def _on_icon_snap(self, checked: bool) -> None:
        self.app.params.icon_snap = bool(checked)
        self.app.mark_dirty()
        self.sync_snap_overrides()

    def _on_icon_colour(self, hexa: str) -> None:
        self.app.params.icon_colour = Colours.parse_colour(hexa)
        self.app.mark_dirty()
