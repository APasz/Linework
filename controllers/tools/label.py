"""Label tool behaviour."""

from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Type
from controllers.commands import Add_Label
from controllers.tools_base import DragAction, ToolBase
from models.geo import Label, Point
from models.styling import Colours, TkCursor
from ui.bars import Tool_Name
from ui.input import MotionEvent, get_mods

if TYPE_CHECKING:
    from controllers.app import App


class Label_Tool(ToolBase):
    """Tool for placing and editing labels."""

    name: Tool_Name = Tool_Name.label
    kind: Hit_Kind | None = Hit_Kind.label
    cursor: TkCursor = TkCursor.XTERM
    tool_hints: str = "Shift: Editor  |  Alt: Ignore Grid"

    def __init__(self) -> None:
        """Initialise the label tool."""
        super().__init__()
        self._drag: DragAction | None = None

    def on_press(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle press events for label placement.

        Args;
            app: The application instance.
            evt: The event.
        """
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        col = Colours.parse_colour(app.var_label_colour.get()) if app.var_label_colour else app.params.brush_colour
        snap = bool(app.params.label_snap) and not mods.alt
        if mods.shift:
            lab = Label(p=p, text="", col=col, snap=snap)
            app.editors.apply_label_defaults(lab)
            if app.editors.edit(app, lab):
                app.cmd.push_and_do(Add_Label(app.params, lab, on_after=lambda: app.layers.redraw(Layer_Type.labels)))
                app.mark_dirty()
            return

        text = app.prompt_text("New label", "Text:")
        if not text:
            return
        lab = Label(p=p, text=text, col=col, snap=snap)
        app.editors.apply_label_defaults(lab)
        app.cmd.push_and_do(Add_Label(app.params, lab, on_after=lambda: app.layers.redraw(Layer_Type.labels)))
        app.mark_dirty()

    def on_motion(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle motion events for label dragging.

        Args;
            app: The application instance.
            evt: The event.
        """
        if self._drag:
            self._drag.update(app, evt)

    def on_release(self, app: App, evt: MotionEvent | tk.Event) -> None:
        """Handle release events for label dragging.

        Args;
            app: The application instance.
            evt: The event.
        """
        if self._drag:
            self._drag.commit(app, evt)
            self._drag = None

    def on_cancel(self, app: App) -> None:
        """Cancel any active label drag.

        Args;
            app: The application instance.
        """
        if self._drag:
            self._drag.cancel(app)
            self._drag = None
