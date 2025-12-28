"""Tool manager for the Qt frontend."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui

from qt.input import MotionEvent
from qt.tools.base import Tool, ToolName

if TYPE_CHECKING:
    from qt.app import QtApp


class QtToolManager:
    """Owns the current tool, routes events, handles activation/deactivation."""

    def __init__(self, app: QtApp, tools: Mapping[ToolName, Tool]) -> None:
        """Create a tool manager instance.

        Args;
            app: The parent Qt app.
            tools: Mapping of tool names to tool instances.
        """
        self.app = app
        self.tools: Mapping[ToolName, Tool] = tools
        self.current: Tool = next(iter(tools.values()))

    def activate(self, name: ToolName) -> None:
        """Activate a tool by name.

        Args;
            name: The tool identifier.
        """
        self.current.on_deactivate(self.app)

        self.app.select_clear()
        self.app.selection.clear_marquee()

        self.current = self.tools[name]
        if hasattr(self.current, "on_activate"):
            self.current.on_activate(self.app)
        if hasattr(self.app, "on_tool_changed"):
            self.app.on_tool_changed(name)

        cursor = getattr(self.current, "cursor", None)
        if cursor is None:
            self.app.view.unsetCursor()
        else:
            self.app.view.setCursor(QtGui.QCursor(cursor))

    def on_press(self, evt: MotionEvent) -> None:
        """Dispatch a press event to the active tool.

        Args;
            evt: The motion event.
        """
        self.current.on_press(self.app, evt)

    def on_motion(self, evt: MotionEvent) -> None:
        """Dispatch a motion event to the active tool.

        Args;
            evt: The motion event.
        """
        self.current.on_motion(self.app, evt)

    def on_release(self, evt: MotionEvent) -> None:
        """Dispatch a release event to the active tool.

        Args;
            evt: The motion event.
        """
        self.current.on_release(self.app, evt)

    def on_key(self, evt: QtGui.QKeyEvent) -> None:
        """Dispatch a key event to the active tool.

        Args;
            evt: The key event.
        """
        if evt.key() == QtCore.Qt.Key.Key_Escape:
            self.cancel()
            return
        self.current.on_key(self.app, evt)

    def cancel(self) -> None:
        """Cancel the active tool."""
        self.current.on_cancel(self.app)
