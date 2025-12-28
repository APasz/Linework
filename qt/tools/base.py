"""Base tool behaviours for the Qt frontend."""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from PySide6 import QtGui

from qt.input import MotionEvent

if TYPE_CHECKING:
    from models.geo import Point
    from qt.app import QtApp


class ToolName(StrEnum):
    """Tool mode identifiers."""

    draw = "draw"
    label = "label"
    icon = "icon"
    select = "select"


class Tool(Protocol):
    """Protocol for tool implementations."""

    name: ToolName
    tool_hints: str

    def on_activate(self, app: QtApp) -> None: ...
    def on_deactivate(self, app: QtApp) -> None: ...

    def on_press(self, app: QtApp, evt: MotionEvent) -> None: ...
    def on_motion(self, app: QtApp, evt: MotionEvent) -> None: ...
    def on_release(self, app: QtApp, evt: MotionEvent) -> None: ...
    def on_key(self, app: QtApp, evt: QtGui.QKeyEvent) -> None: ...
    def on_cancel(self, app: QtApp) -> None: ...


class ToolBase:
    """Common helpers for all tools."""

    name: ToolName
    tool_hints: str = ""

    def on_activate(self, app: QtApp) -> None:
        """Handle tool activation.

        Args;
            app: The parent Qt app.
        """
        pass

    def on_deactivate(self, app: QtApp) -> None:
        """Handle tool deactivation.

        Args;
            app: The parent Qt app.
        """
        self.clear_preview(app)

    def on_press(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle press events.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        pass

    def on_motion(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle motion events.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        pass

    def on_release(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle release events.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        pass

    def on_key(self, app: QtApp, evt: QtGui.QKeyEvent) -> None:
        """Handle key events.

        Args;
            app: The parent Qt app.
            evt: The key event.
        """
        pass

    def on_cancel(self, app: QtApp) -> None:
        """Handle tool cancellation.

        Args;
            app: The parent Qt app.
        """
        pass

    @staticmethod
    def moved_enough(a: Point, b: Point, tol: int = 1) -> bool:
        """Return True if the distance exceeds the tolerance.

        Args;
            a: The first point.
            b: The second point.
            tol: The minimum distance in pixels.

        Returns;
            True if the distance exceeds the tolerance.
        """
        dx, dy = a.x - b.x, a.y - b.y
        return (dx * dx + dy * dy) >= (tol * tol)

    @staticmethod
    def clear_preview(app: QtApp) -> None:
        """Clear preview drawings for this tool.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()


class DragAction(Protocol):
    """Tiny state objects for Select_Tool drags: update/commit/cancel."""

    def update(self, app: QtApp, evt: MotionEvent) -> None: ...
    def commit(self, app: QtApp, evt: MotionEvent) -> None: ...
    def cancel(self, app: QtApp) -> None: ...
