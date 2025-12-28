"""Status bar widgets and overlay logic for the Qt frontend."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

from PySide6 import QtCore, QtWidgets


class Side(StrEnum):
    """Status bar sides."""

    left = "left"
    centre = "centre"
    right = "right"


@dataclass(order=True)
class _Overlay:
    """Overlay entry for the status bar."""

    sort_key: tuple[int, int] = field(init=False, repr=False)
    key: str
    text: str
    priority: int = 0
    side: Side = Side.left
    seq: int = 0

    def __post_init__(self) -> None:
        self.sort_key = (-self.priority, self.seq)


class QtStatusStrip(QtWidgets.QWidget):
    """Status bar widget with left/centre/right lanes."""

    def __init__(self, parent: QtWidgets.QWidget | None = None) -> None:
        """Create the status strip widget.

        Args;
            parent: Optional parent widget.
        """
        super().__init__(parent)
        layout = QtWidgets.QGridLayout(self)
        layout.setContentsMargins(6, 2, 6, 2)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(0)

        self.lbl_left = QtWidgets.QLabel("")
        self.lbl_centre = QtWidgets.QLabel("")
        self.lbl_right = QtWidgets.QLabel("")

        self.lbl_left.setAlignment(QtCore.Qt.AlignmentFlag.AlignLeft | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.lbl_centre.setAlignment(QtCore.Qt.AlignmentFlag.AlignHCenter | QtCore.Qt.AlignmentFlag.AlignVCenter)
        self.lbl_right.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight | QtCore.Qt.AlignmentFlag.AlignVCenter)

        layout.addWidget(self.lbl_left, 0, 0)
        layout.addWidget(self.lbl_centre, 0, 1)
        layout.addWidget(self.lbl_right, 0, 2)
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        self.setSizePolicy(QtWidgets.QSizePolicy.Policy.Expanding, QtWidgets.QSizePolicy.Policy.Fixed)

    def set_texts(self, left: str, centre: str, right: str) -> None:
        """Set the displayed status text for each lane.

        Args;
            left: The left lane text.
            centre: The centre lane text.
            right: The right lane text.
        """
        self.lbl_left.setText(left)
        self.lbl_centre.setText(centre)
        self.lbl_right.setText(right)


class QtStatus(QtCore.QObject):
    """Status bar state and overlay management."""

    def __init__(self, strip: QtStatusStrip) -> None:
        """Create a status manager bound to a status strip.

        Args;
            strip: The status strip widget.
        """
        super().__init__(strip)
        self._strip = strip
        self._base_left: str = ""
        self._seq = 0

        self._held: dict[str, _Overlay] = {}
        self._temp_key: str | None = None
        self._centre_key = "__centre__"

        self._temp_timer = QtCore.QTimer(self)
        self._temp_timer.setSingleShot(True)
        self._temp_timer.timeout.connect(self._clear_temp)

    # ---- base ----
    def set(self, text: str) -> None:
        """Set the base left status text.

        Args;
            text: The status text.
        """
        self._base_left = text
        self._render()

    # ---- centre sugar ----
    def set_centre(self, text: str) -> None:
        """Set or clear the centre status text.

        Args;
            text: The centre text.
        """
        if text:
            self.hold(self._centre_key, text, priority=-10, side=Side.centre)
        else:
            self.release(self._centre_key)

    def clear_centre(self) -> None:
        """Clear the centre status text."""
        self.release(self._centre_key)

    # ---- held overlays (persistent until release) ----
    def hold(self, key: str, text: str, *, priority: int = 0, side: Side = Side.left) -> None:
        """Hold an overlay until released.

        Args;
            key: Overlay identifier.
            text: Overlay text.
            priority: Higher values win.
            side: Which side to display on.
        """
        self._seq += 1
        self._held[key] = _Overlay(key=key, text=text, priority=priority, side=side, seq=self._seq)
        self._render()

    def release(self, key: str) -> None:
        """Release a held overlay.

        Args;
            key: Overlay identifier.
        """
        if key in self._held:
            del self._held[key]
            if self._temp_key == key:
                self._temp_key = None
            self._render()

    # ---- temporary overlays (auto-clear) ----
    def temp(self, text: str, ms: int = 1500, *, priority: int = 50, side: Side = Side.centre) -> None:
        """Show a temporary overlay.

        Args;
            text: Overlay text.
            ms: Duration in milliseconds.
            priority: Priority of the overlay.
            side: Which side to display on.
        """
        if self._temp_timer.isActive():
            self._temp_timer.stop()

        key = "__temp__"
        self.hold(key, text, priority=priority, side=side)
        self._temp_key = key
        self._temp_timer.start(ms)

    def _clear_temp(self) -> None:
        if self._temp_key:
            self.release(self._temp_key)
        self._temp_key = None

    # ---- clear all ----
    def clear(self) -> None:
        """Clear all status text and overlays."""
        self._base_left = ""
        self._held.clear()
        if self._temp_timer.isActive():
            self._temp_timer.stop()
        self._temp_key = None
        self._render()

    # ---- render ----
    def _render(self) -> None:
        self._strip.set_texts(
            self._pick_side(Side.left) or self._base_left,
            self._pick_side(Side.centre) or "",
            self._pick_side(Side.right) or "",
        )

    def _pick_side(self, side: Side) -> str:
        items = [ov for ov in self._held.values() if ov.side == side]
        if not items:
            return ""
        top = sorted(items)[0]
        return top.text
