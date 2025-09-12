from __future__ import annotations

import tkinter as tk
from pathlib import Path
from typing import TYPE_CHECKING, Any

from models.assets import Icon_Name
from models.geo import Builtin_Icon, Label, Line, Picture_Icon
from models.styling import Anchor, CapStyle, Colours, LineStyle
from ui.edit_dialog import GenericEditDialog

if TYPE_CHECKING:
    from controllers.app import App


class Editors:
    def __init__(self, app: App) -> None:
        self.app = app

    def _colour_choices(self) -> list[str]:
        return Colours.names(min_alpha=25)

    def _cap_choices(self) -> list[str]:
        return [s.value for s in CapStyle]

    def _style_choices(self) -> list[str]:
        return [s.value for s in LineStyle]

    def _anchor_choices_tk(self) -> list[str]:
        # order is nice but any mapping is fine; must match Anchor.parse()
        return [s.value for s in Anchor]

    def _icon_choices(self) -> list[str]:
        return [name.value for name in Icon_Name]

    def _picture_choices(self) -> dict[str, Path]:
        return {p.name: p for p in self.app.asset_lib.list_pictures()}

    def edit_label(self, parent: tk.Misc, lab: Label) -> dict[str, Any] | None:
        schema = [
            {"name": "text", "label": "Text", "kind": "text"},
            {"name": "x", "label": "X", "kind": "int", "min": 0},
            {"name": "y", "label": "Y", "kind": "int", "min": 0},
            {"name": "snap_to_grid", "label": "Snap X/Y to grid now", "kind": "bool"},
            {"name": "snap_flag", "label": "Keep snapped when dragging", "kind": "bool"},
            {"name": "size", "label": "Size", "kind": "int", "min": 1},
            {"name": "rotation", "label": "Rotation (deg)", "kind": "int"},
            {"name": "anchor", "label": "Anchor", "kind": "choice", "choices": self._anchor_choices_tk()},
            {"name": "colour", "label": "Colour", "kind": "choice", "choices": self._colour_choices()},
        ]
        init = {
            "text": lab.text,
            "x": lab.p.x,
            "y": lab.p.y,
            "snap_to_grid": False,
            "snap_flag": lab.snap,
            "size": lab.size,
            "rotation": lab.rotation,
            "anchor": lab.anchor.tk,
            "colour": lab.col.name,
        }
        dlg = GenericEditDialog(parent, "Edit Label", schema, init)

        return getattr(dlg, "result", None)

    def edit_icon(self, parent: tk.Misc, ico: Builtin_Icon, choices: list[str] | None = None) -> dict[str, Any] | None:
        schema = [
            {"name": "name", "label": "Icon", "kind": "choice", "choices": choices or self._icon_choices()},
            {"name": "x", "label": "X", "kind": "int", "min": 0},
            {"name": "y", "label": "Y", "kind": "int", "min": 0},
            {"name": "snap_to_grid", "label": "Snap X/Y to grid now", "kind": "bool"},
            {"name": "snap_flag", "label": "Keep snapped when dragging", "kind": "bool"},
            {"name": "size", "label": "Size", "kind": "int", "min": 1},
            {"name": "rotation", "label": "Rotation (deg)", "kind": "int"},
            {"name": "anchor", "label": "Anchor", "kind": "choice", "choices": self._anchor_choices_tk()},
            {"name": "colour", "label": "Colour", "kind": "choice", "choices": self._colour_choices()},
        ]
        init = {
            "name": ico.name,
            "x": ico.p.x,
            "y": ico.p.y,
            "snap_to_grid": False,
            "snap_flag": ico.snap,
            "size": ico.size,
            "rotation": ico.rotation,
            "anchor": ico.anchor.tk,
            "colour": ico.col.name,
        }
        dlg = GenericEditDialog(parent, "Edit Icon", schema, init)
        return getattr(dlg, "result", None)

    def edit_picture(
        self, parent: tk.Misc, pic: Picture_Icon, choices: list[str] | None = None
    ) -> dict[str, Any] | None:
        schema = [
            {"name": "src", "label": "Picture", "kind": "choice_dict", "choices": choices or self._picture_choices()},
            {"name": "x", "label": "X", "kind": "int", "min": 0},
            {"name": "y", "label": "Y", "kind": "int", "min": 0},
            {"name": "snap_to_grid", "label": "Snap X/Y to grid now", "kind": "bool"},
            {"name": "snap_flag", "label": "Keep snapped when dragging", "kind": "bool"},
            {"name": "size", "label": "Size", "kind": "int", "min": 1},
            {"name": "rotation", "label": "Rotation (deg)", "kind": "int"},
            {"name": "anchor", "label": "Anchor", "kind": "choice", "choices": self._anchor_choices_tk()},
            {"name": "colour", "label": "Colour", "kind": "choice", "choices": self._colour_choices()},
        ]
        init = {
            "src": pic.src.name,
            "x": pic.p.x,
            "y": pic.p.y,
            "snap_to_grid": False,
            "snap_flag": pic.snap,
            "size": pic.size,
            "rotation": pic.rotation,
            "anchor": pic.anchor.tk,
            "colour": pic.col.name,
        }
        dlg = GenericEditDialog(parent, "Edit Picture", schema, init)
        return getattr(dlg, "result", None)

    def edit_line(self, parent: tk.Misc, lin: Line) -> dict[str, Any] | None:
        schema = [
            {"name": "x1", "label": "X1", "kind": "int", "min": 0},
            {"name": "y1", "label": "Y1", "kind": "int", "min": 0},
            {"name": "x2", "label": "X2", "kind": "int", "min": 0},
            {"name": "y2", "label": "Y2", "kind": "int", "min": 0},
            {"name": "snap_to_grid", "label": "Snap endpoints to grid", "kind": "bool"},
            {"name": "width", "label": "Width", "kind": "int", "min": 1},
            {"name": "capstyle", "label": "Cap", "kind": "choice", "choices": self._cap_choices()},
            {"name": "style", "label": "Dash", "kind": "choice", "choices": self._style_choices()},
            {"name": "colour", "label": "Colour", "kind": "choice", "choices": self._colour_choices()},
            {"name": "dash_offset", "label": "Dash offset", "kind": "int", "min": 0},
        ]
        init = {
            "x1": lin.a.x,
            "y1": lin.a.y,
            "x2": lin.b.x,
            "y2": lin.b.y,
            "snap_to_grid": False,
            "width": lin.width,
            "capstyle": lin.capstyle,
            "style": lin.style,
            "colour": lin.col.name,
            "dash_offset": lin.dash_offset,
        }
        dlg = GenericEditDialog(parent, "Edit Line", schema, init)
        return getattr(dlg, "result", None)
