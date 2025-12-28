"""Icon tool behaviour for the Qt frontend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore

from core.commands import AddIcon
from models.geo import BuiltinIcon, IconType, PictureIcon, Point
from qt.input import MotionEvent
from qt.tools.base import ToolBase, ToolName

if TYPE_CHECKING:
    from qt.app import QtApp


class IconTool(ToolBase):
    """Tool for placing icons."""

    name: ToolName = ToolName.icon
    cursor = QtCore.Qt.CursorShape.CrossCursor
    tool_hints: str = "Ctrl: Picker  |  Shift: Editor  |  Alt: Invert Grid Snap"

    def on_press(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle press events for placing icons.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        base_snap = bool(app.params.icon_snap)
        use_snap = base_snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not use_snap)
        snap = use_snap

        if mods.ctrl:
            src = app.pick_icon_source()
            if src is None:
                return
        else:
            src = app.current_icon or app.params.default_icon

        col = app.params.icon_colour

        if src.kind == IconType.builtin and src.name:
            ico = BuiltinIcon(
                p=p,
                col=col,
                name=src.name,
                size=app.params.icon_size,
                rotation=app.params.icon_rotation,
                anchor=app.params.icon_anchor,
                snap=snap,
            )
        elif src.kind == IconType.picture and src.src:
            ico = PictureIcon(
                p=p,
                col=col,
                src=src.src,
                size=app.params.picture_size,
                rotation=app.params.icon_rotation,
                anchor=app.params.icon_anchor,
                snap=snap,
            )
        else:
            return

        app.editors.apply_icon_defaults(ico)
        if mods.shift and not app.editors.edit(app, ico):
            return

        app.cmd.push_and_do(AddIcon(app.params, ico, on_after=app.redraw))
        app.mark_dirty()

        app.current_icon = src
        app.params.default_icon = src
