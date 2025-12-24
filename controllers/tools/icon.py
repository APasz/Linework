from __future__ import annotations

import tkinter as tk
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Type
from controllers.commands import Add_Icon
from controllers.tools_base import DragAction, ToolBase
from models.assets import Icon_Name
from models.geo import Builtin_Icon, Icon_Source, Icon_Type, Picture_Icon, Point
from models.styling import Colours, TkCursor
from ui.bars import Tool_Name
from ui.edit_dialog import Icon_Gallery
from ui.input import MotionEvent, get_mods

if TYPE_CHECKING:
    from controllers.app import App


def _describe_icon(src: Icon_Source) -> str:
    if src.kind == Icon_Type.builtin and src.name:
        return f"🖥️ {src.name.value}"
    if src.kind == Icon_Type.picture and src.src:
        return f"📷 {src.src.name}"
    return "?"


class Icon_Tool(ToolBase):
    name: Tool_Name = Tool_Name.icon
    kind: Hit_Kind | None = Hit_Kind.icon
    cursor: TkCursor = TkCursor.CROSSHAIR
    tool_hints: str = "Ctrl: Picker  |  Shift: Editor  |  Alt: Ignore Grid"

    def __init__(self):
        super().__init__()
        self._drag: DragAction | None = None

    def on_press(self, app: App, evt: MotionEvent | tk.Event):
        if not isinstance(evt, tk.Event):
            return
        mods = get_mods(evt)
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=mods.alt)
        snap = bool(app.params.icon_snap) and not mods.alt

        if mods.ctrl:
            dlg = Icon_Gallery(app.root, app, app.params.recent_icons, at=Point(x=evt.x_root, y=evt.y_root))
            app.root.wait_window(dlg)
            src = getattr(dlg, "result", None)
            if not src:
                return
        else:
            src = getattr(app, "current_icon", None)
            if src is None:
                try:
                    src = Icon_Source.builtin(Icon_Name(app.var_icon.get()))
                except Exception:
                    src = Icon_Source.builtin(Icon_Name.SIGNAL)

        col = Colours.parse_colour(app.var_icon_colour.get()) if app.var_icon_colour else app.params.brush_colour

        if src.kind == Icon_Type.builtin and src.name:
            ico = Builtin_Icon(p=p, col=col, name=src.name, size=app.params.icon_size, snap=snap)
        elif src.kind == Icon_Type.picture and src.src:
            ico = Picture_Icon(p=p, col=col, src=src.src, size=app.params.picture_size, snap=snap)
        else:
            return
        app.editors.apply_icon_defaults(ico)

        if mods.shift:
            if not app.editors.edit(app, ico):
                return

        app.cmd.push_and_do(Add_Icon(app.params, ico, on_after=lambda: app.layers.redraw(Layer_Type.icons)))
        app.mark_dirty()

        def _src_key(s):
            return (s.kind.value, getattr(s, "name", None), str(getattr(s, "src", "")))

        rec = []
        seen = set()
        for s in [src, *app.params.recent_icons]:
            k = _src_key(s)
            if k not in seen:
                seen.add(k)
                rec.append(s)
        app.params.recent_icons = rec[:24]

        app.current_icon = src
        if hasattr(app, "var_icon_label"):
            app.var_icon_label.set(_describe_icon(src))
        if src.kind == Icon_Type.builtin and src.name:
            app.var_icon.set(src.name.value)
        if getattr(app.params, "default_icon", None) != src:
            app.params.default_icon = src

    def on_motion(self, app: App, evt: MotionEvent | tk.Event):
        if self._drag:
            self._drag.update(app, evt)

    def on_release(self, app: App, evt: MotionEvent | tk.Event):
        if self._drag:
            self._drag.commit(app, evt)
            self._drag = None

    def on_cancel(self, app: App):
        if self._drag:
            self._drag.cancel(app)
            self._drag = None
