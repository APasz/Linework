"""Flow layout helper for wrapping widgets horizontally."""

from __future__ import annotations

from typing import cast

from PySide6 import QtCore, QtWidgets


class FlowLayout(QtWidgets.QLayout):
    """Layout that wraps widgets onto multiple rows."""

    def __init__(self, parent: QtWidgets.QWidget | None = None, margin: int = 0, spacing: int = 6) -> None:
        """Create a flow layout.

        Args;
            parent: Optional parent widget.
            margin: Layout margin.
            spacing: Item spacing.
        """
        super().__init__(parent)
        self._items: list[QtWidgets.QLayoutItem] = []
        self.setContentsMargins(margin, margin, margin, margin)
        self.setSpacing(spacing)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        """Add an item to the layout.

        Args;
            item: The layout item to add.
        """
        self._items.append(item)

    def count(self) -> int:
        """Return the number of items in the layout.

        Returns;
            The item count.
        """
        return len(self._items)

    def itemAt(self, index: int) -> QtWidgets.QLayoutItem | None:
        """Return the item at a given index.

        Args;
            index: The item index.

        Returns;
            The layout item, if present.
        """
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index: int) -> QtWidgets.QLayoutItem:
        """Remove and return the item at the index.

        Args;
            index: The item index.

        Returns;
            The layout item, or None for invalid indices.
        """
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        # Qt returns None for invalid indexes, but the stub expects QLayoutItem.
        return cast(QtWidgets.QLayoutItem, None)

    def expandingDirections(self) -> QtCore.Qt.Orientation:
        """Return the layout's expanding directions.

        Returns;
            The supported orientations.
        """
        return QtCore.Qt.Orientation(0)

    def hasHeightForWidth(self) -> bool:
        """Return True if height depends on width."""
        return True

    def heightForWidth(self, width: int) -> int:
        """Calculate height for a given width.

        Args;
            width: The available width.

        Returns;
            The calculated height.
        """
        return self._do_layout(QtCore.QRect(0, 0, width, 0), True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        """Set the layout geometry.

        Args;
            rect: The layout rectangle.
        """
        super().setGeometry(rect)
        self._do_layout(rect, False)

    def sizeHint(self) -> QtCore.QSize:
        """Return a size hint for the layout.

        Returns;
            The suggested size.
        """
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        """Return the minimum size for the layout.

        Returns;
            The minimum size.
        """
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        x = rect.x()
        y = rect.y()
        line_height = 0
        spacing = self.spacing()
        if spacing < 0:
            spacing = 6

        for item in self._items:
            hint = item.sizeHint()
            next_x = x + hint.width() + spacing
            if next_x - spacing > rect.right() and line_height > 0:
                x = rect.x()
                y = y + line_height + spacing
                next_x = x + hint.width() + spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y()
