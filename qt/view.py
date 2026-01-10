"""Qt view wrapper to route input events to tools."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore, QtGui, QtWidgets

from qt.input import MotionEvent, get_mods

if TYPE_CHECKING:
    from qt.app import QtApp


class QtCanvasView(QtWidgets.QGraphicsView):
    """Graphics view that forwards input events to the tool manager."""

    _ZOOM_MIN = 0.1
    _ZOOM_MAX = 8.0
    _ZOOM_STEP = 1.2

    def __init__(self, app: QtApp, scene: QtWidgets.QGraphicsScene) -> None:
        """Create the canvas view wrapper.

        Args;
            app: The parent Qt app.
            scene: The graphics scene to display.
        """
        super().__init__(scene)
        self.app = app
        self.setMouseTracking(True)
        self.setFocusPolicy(QtCore.Qt.FocusPolicy.StrongFocus)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorViewCenter)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)

    def zoom_level(self) -> float:
        """Return the current zoom level.

        Returns;
            The zoom scalar.
        """
        return self.transform().m11()

    def reset_zoom(self) -> None:
        """Reset the zoom level to 100%."""
        self.resetTransform()
        self._notify_zoom()

    def _notify_zoom(self) -> None:
        """Notify the app about zoom changes."""
        self.app.on_zoom_changed(self.zoom_level())

    def _motion_event(self, event: QtGui.QMouseEvent) -> MotionEvent:
        """Build a MotionEvent from a Qt mouse event.

        Args;
            event: The Qt mouse event.

        Returns;
            The derived MotionEvent.
        """
        pos = self.mapToScene(event.position().toPoint())
        mods = get_mods(event)
        return MotionEvent(int(round(pos.x())), int(round(pos.y())), mods)

    def mousePressEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse press events and forward to the tool manager.

        Args;
            event: The Qt mouse event.
        """
        if event.button() == QtCore.Qt.MouseButton.RightButton:
            self.app.tool_mgr.cancel()
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.app.tool_mgr.on_press(self._motion_event(event))
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse move events and update hover callbacks.

        Args;
            event: The Qt mouse event.
        """
        motion = self._motion_event(event)
        self.app.tool_mgr.on_motion(motion)
        if hasattr(self.app, "on_hover_motion"):
            self.app.on_hover_motion(motion)
        elif hasattr(self.app, "on_hover_xy"):
            self.app.on_hover_xy(motion.x, motion.y)
        if event.buttons() & QtCore.Qt.MouseButton.LeftButton:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse release events and forward to the tool manager.

        Args;
            event: The Qt mouse event.
        """
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.app.tool_mgr.on_release(self._motion_event(event))
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QtGui.QMouseEvent) -> None:
        """Handle mouse double-click events for tool activation.

        Args;
            event: The Qt mouse event.
        """
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self.app.on_double_click(self._motion_event(event))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event: QtCore.QEvent) -> None:  # type: ignore[override]
        """Handle mouse-leave events for hover tracking.

        Args;
            event: The Qt leave event.
        """
        self.app.on_hover_leave()
        super().leaveEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        """Handle key press events and forward to the tool manager.

        Args;
            event: The Qt key event.
        """
        self.app.tool_mgr.on_key(event)
        if not event.isAccepted():
            super().keyPressEvent(event)

    def wheelEvent(self, event: QtGui.QWheelEvent) -> None:
        """Handle wheel events for zooming with Ctrl.

        Args;
            event: The Qt wheel event.
        """
        if not get_mods(event).ctrl:
            super().wheelEvent(event)
            return
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        current = self.transform().m11()
        if current <= 0:
            event.ignore()
            return
        factor = self._ZOOM_STEP ** (delta / 120.0)
        target = current * factor
        if target < self._ZOOM_MIN:
            factor = self._ZOOM_MIN / current
        elif target > self._ZOOM_MAX:
            factor = self._ZOOM_MAX / current
        if abs(factor - 1.0) > 1e-3:
            self.scale(factor, factor)
            self._notify_zoom()
        event.accept()
