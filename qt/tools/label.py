"""Label tool behaviour for the Qt frontend."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PySide6 import QtCore

from core.commands import AddLabel
from models.geo import Label, Point
from qt.input import MotionEvent
from qt.tools.base import ToolBase, ToolName

if TYPE_CHECKING:
    from qt.app import QtApp


class LabelTool(ToolBase):
    """Tool for placing labels."""

    name: ToolName = ToolName.label
    cursor = QtCore.Qt.CursorShape.IBeamCursor
    tool_hints: str = "Shift: Editor  |  Alt: Invert Grid Snap"

    def on_press(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle press events for placing labels.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        base_snap = bool(app.params.label_snap)
        use_snap = base_snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not use_snap)
        col = app.params.label_colour
        snap = use_snap

        if mods.shift:
            lab = Label(
                p=p,
                text="",
                col=col,
                snap=snap,
                size=app.params.label_size,
                rotation=app.params.label_rotation,
                anchor=app.params.label_anchor,
            )
            app.editors.apply_label_defaults(lab)
            if app.editors.edit(app, lab):
                app.cmd.push_and_do(AddLabel(app.params, lab, on_after=app.redraw))
                app.mark_dirty()
            return

        text = app.prompt_text("New label", "Text:")
        if not text:
            return

        lab = Label(
            p=p,
            text=text,
            col=col,
            snap=snap,
            size=app.params.label_size,
            rotation=app.params.label_rotation,
            anchor=app.params.label_anchor,
        )
        app.editors.apply_label_defaults(lab)
        app.cmd.push_and_do(AddLabel(app.params, lab, on_after=app.redraw))
        app.mark_dirty()
