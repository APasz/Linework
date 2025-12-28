"""Qt colour palette widgets for quick swatch selection."""

from __future__ import annotations

from collections.abc import Callable

from PySide6 import QtCore, QtGui, QtWidgets

from models.styling import Colour, Colours

SWATCH_SIZE = 22
SWATCH_BORDER = QtGui.QColor(60, 60, 60)
CHECKER_LIGHT = QtGui.QColor(235, 235, 235)
CHECKER_DARK = QtGui.QColor(200, 200, 200)


def _as_colour(value: Colour | str | None) -> Colour | None:
    if value is None:
        return None
    if isinstance(value, Colour):
        return value
    try:
        return Colours.parse_colour(value)
    except ValueError:
        return None


def _draw_checker(painter: QtGui.QPainter, rect: QtCore.QRect, tile: int) -> None:
    for y in range(rect.top(), rect.bottom() + 1, tile):
        for x in range(rect.left(), rect.right() + 1, tile):
            if ((x // tile) + (y // tile)) % 2:
                painter.fillRect(QtCore.QRect(x, y, tile, tile), CHECKER_DARK)
            else:
                painter.fillRect(QtCore.QRect(x, y, tile, tile), CHECKER_LIGHT)


def _swatch_pixmap(col: Colour | None, size: int = SWATCH_SIZE) -> QtGui.QPixmap:
    pixmap = QtGui.QPixmap(size, size)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    rect = QtCore.QRect(0, 0, size, size)
    tile = max(2, size // 4)

    if col is None:
        painter.fillRect(rect, QtGui.QColor(255, 255, 255))
    elif col.alpha < 255:
        _draw_checker(painter, rect, tile)
    if col is not None:
        painter.fillRect(rect, QtGui.QColor(col.red, col.green, col.blue, col.alpha))

    pen = QtGui.QPen(SWATCH_BORDER)
    pen.setWidth(1)
    painter.setPen(pen)
    painter.drawRect(0, 0, size - 1, size - 1)
    painter.end()
    return pixmap


class _SwatchButton(QtWidgets.QToolButton):
    def __init__(
        self,
        parent: QtWidgets.QWidget,
        col: Colour | None,
        *,
        is_custom: bool,
        idx: int | None,
        on_pick: Callable[[Colour], None],
        on_edit: Callable[[int, Colour | None], None],
        on_clear: Callable[[int], None],
    ) -> None:
        super().__init__(parent)
        self._col = col
        self._is_custom = is_custom
        self._idx = idx
        self._on_pick = on_pick
        self._on_edit = on_edit
        self._on_clear = on_clear

        self.setIcon(QtGui.QIcon(_swatch_pixmap(col)))
        self.setIconSize(QtCore.QSize(SWATCH_SIZE, SWATCH_SIZE))
        self.setFixedSize(SWATCH_SIZE + 6, SWATCH_SIZE + 6)
        self.setAutoRaise(True)

    def set_colour(self, col: Colour | None) -> None:
        self._col = col
        self.setIcon(QtGui.QIcon(_swatch_pixmap(col)))

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        if self._is_custom and self._idx is not None:
            if event.button() == QtCore.Qt.MouseButton.RightButton:
                self._on_clear(self._idx)
                return
            if event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier or self._col is None:
                self._on_edit(self._idx, self._col)
                return
        if event.button() == QtCore.Qt.MouseButton.LeftButton and self._col is not None:
            self._on_pick(self._col)
            return
        super().mousePressEvent(event)


class ColourPalettePopup(QtWidgets.QFrame):
    """Popup palette for picking colours."""

    def __init__(
        self,
        owner: QtWidgets.QWidget,
        colours: list[Colour],
        custom: list[Colour | None],
        *,
        on_pick: Callable[[Colour], None],
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ) -> None:
        """Create the palette popup.

        Args;
            owner: The owning widget.
            colours: The predefined colours.
            custom: The custom colour slots.
            on_pick: Callback when a colour is picked.
            on_update_custom: Optional callback when custom colours change.
        """
        super().__init__(owner, QtCore.Qt.WindowType.Popup)
        self._owner = owner
        self._on_pick = on_pick
        self._custom = custom
        self._on_update_custom = on_update_custom
        self._custom_buttons: list[_SwatchButton] = []

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(8)

        left = QtWidgets.QVBoxLayout()
        right = QtWidgets.QVBoxLayout()
        right.addWidget(QtWidgets.QLabel("Custom"))
        layout.addLayout(left)
        layout.addLayout(right)

        for col in colours:
            btn = _SwatchButton(
                self,
                col,
                is_custom=False,
                idx=None,
                on_pick=self._handle_pick,
                on_edit=self._noop,
                on_clear=self._noop,
            )
            left.addWidget(btn)

        for i, col in enumerate(custom):
            btn = _SwatchButton(
                self,
                col,
                is_custom=True,
                idx=i,
                on_pick=self._handle_pick,
                on_edit=self._handle_edit_custom,
                on_clear=self._handle_clear_custom,
            )
            right.addWidget(btn)
            self._custom_buttons.append(btn)

        left.addStretch(1)
        right.addStretch(1)

    def _noop(self, *_args: object) -> None:
        return

    def _handle_pick(self, col: Colour) -> None:
        self._on_pick(col)
        self.close()

    def _handle_edit_custom(self, idx: int, initial: Colour | None) -> None:
        parent = self._dialog_parent()
        self.close()
        col = self._pick_colour(initial or Colours.white, parent)
        if col is None:
            return
        if 0 <= idx < len(self._custom):
            self._custom[idx] = col
            if self._on_update_custom:
                self._on_update_custom(idx, col)
        self._on_pick(col)

    def _handle_clear_custom(self, idx: int) -> None:
        if 0 <= idx < len(self._custom):
            self._custom[idx] = None
            if idx < len(self._custom_buttons):
                self._custom_buttons[idx].set_colour(None)
            if self._on_update_custom:
                self._on_update_custom(idx, None)
        self.close()

    def _dialog_parent(self) -> QtWidgets.QWidget:
        if self._owner is not None:
            return self._owner.window() or self._owner
        return self

    def _pick_colour(self, current: Colour, parent: QtWidgets.QWidget) -> Colour | None:
        start = QtGui.QColor(current.red, current.green, current.blue, current.alpha)
        col = QtWidgets.QColorDialog.getColor(
            start,
            parent,
            "Choose colour",
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not col.isValid():
            return None
        return Colour(red=col.red(), green=col.green(), blue=col.blue(), alpha=col.alpha())

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key presses for popup dismissal.

        Args;
            event: The Qt key event.
        """
        if event.key() == QtCore.Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)


class ColourPaletteButton(QtWidgets.QToolButton):
    """Tool button that opens a colour palette popup."""

    _open_popup: ColourPalettePopup | None = None

    def __init__(
        self,
        parent: QtWidgets.QWidget,
        colours: list[Colour],
        *,
        selected: Colour | str | None = None,
        on_select: Callable[[str], None] | None = None,
        custom: list[Colour | None] | None = None,
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ) -> None:
        """Create a palette button.

        Args;
            parent: The parent widget.
            colours: The available colours.
            selected: Optional initial selection.
            on_select: Callback when a colour is selected.
            custom: Optional custom palette entries.
            on_update_custom: Callback when custom entries change.
        """
        super().__init__(parent)
        self._colours = list(colours)
        self._custom: list[Colour | None]
        if custom is None:
            self._custom = [None for _ in self._colours]
        else:
            self._custom = list(custom)
        self._on_select = on_select
        self._on_update_custom = on_update_custom
        self._popup: ColourPalettePopup | None = None
        self._selected: Colour | None = None

        self.setToolButtonStyle(QtCore.Qt.ToolButtonStyle.ToolButtonIconOnly)
        self.setAutoRaise(True)
        self.setIconSize(QtCore.QSize(SWATCH_SIZE, SWATCH_SIZE))
        self.setFixedSize(SWATCH_SIZE + 8, SWATCH_SIZE + 8)

        if selected is not None:
            self.set_selected(selected)

    def set_selected(self, value: Colour | str) -> None:
        """Set the selected colour.

        Args;
            value: The colour to select.
        """
        col = _as_colour(value)
        if col is None:
            return
        self._selected = col
        self.setIcon(QtGui.QIcon(_swatch_pixmap(col)))
        self.setToolTip(col.hexah)

    def selected_hex(self) -> str:
        """Return the selected colour as hex.

        Returns;
            The selected colour in RGBA hex, or empty string.
        """
        return self._selected.hexah if self._selected is not None else ""

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press events for palette control.

        Args;
            event: The Qt mouse event.
        """
        if event.button() == QtCore.Qt.MouseButton.RightButton or (
            event.modifiers() & QtCore.Qt.KeyboardModifier.ShiftModifier
        ):
            self._pick_custom_colour()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._toggle_popup()
            return
        super().mousePressEvent(event)

    def _toggle_popup(self) -> None:
        if self._popup and self._popup.isVisible():
            self._popup.close()
            return

        if ColourPaletteButton._open_popup and ColourPaletteButton._open_popup is not self._popup:
            try:
                ColourPaletteButton._open_popup.close()
            except RuntimeError:
                # Ignore stale Qt objects during teardown.
                pass

        popup = ColourPalettePopup(
            self,
            self._colours,
            self._custom,
            on_pick=self._apply_pick,
            on_update_custom=self._on_update_custom,
        )
        ColourPaletteButton._open_popup = popup
        self._popup = popup
        popup.destroyed.connect(self._clear_popup)
        pos = self.mapToGlobal(QtCore.QPoint(0, self.height()))
        popup.move(pos)
        popup.show()
        popup.setFocus(QtCore.Qt.FocusReason.PopupFocusReason)

    def _clear_popup(self, _obj: QtCore.QObject | None = None) -> None:
        if ColourPaletteButton._open_popup is self._popup:
            ColourPaletteButton._open_popup = None
        self._popup = None

    def _apply_pick(self, col: Colour) -> None:
        self.set_selected(col)
        if self._on_select:
            self._on_select(col.hexah)

    def _pick_custom_colour(self) -> None:
        start = self._selected or Colours.white
        col = QtWidgets.QColorDialog.getColor(
            QtGui.QColor(start.red, start.green, start.blue, start.alpha),
            self,
            "Choose colour",
            QtWidgets.QColorDialog.ColorDialogOption.ShowAlphaChannel,
        )
        if not col.isValid():
            return
        self._apply_pick(Colour(red=col.red(), green=col.green(), blue=col.blue(), alpha=col.alpha()))
