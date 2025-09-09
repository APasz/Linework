from __future__ import annotations

import tkinter as tk
from typing import Any

from models.geo import Icon, Label, Line
from models.styling import Anchor, CapStyle, Colours, LineStyle
from ui.edit_dialog import GenericEditDialog


def _colour_choices() -> list[str]:
    return Colours.names(min_alpha=25)


def _cap_choices() -> list[str]:
    return [s.value for s in CapStyle]


def _style_choices() -> list[str]:
    return [s.value for s in LineStyle]


def _anchor_choices_tk() -> list[str]:
    # order is nice but any mapping is fine; must match Anchor.parse()
    return [s.value for s in Anchor]


def edit_label(parent: tk.Misc, lab: Label) -> dict[str, Any] | None:
    schema = [
        {"name": "text", "label": "Text", "kind": "text"},
        {"name": "x", "label": "X", "kind": "int", "min": 0},
        {"name": "y", "label": "Y", "kind": "int", "min": 0},
        {"name": "snap_to_grid", "label": "Snap X/Y to grid now", "kind": "bool"},
        {"name": "snap_flag", "label": "Keep snapped when dragging", "kind": "bool"},
        {"name": "size", "label": "Size", "kind": "int", "min": 1},
        {"name": "rotation", "label": "Rotation (deg)", "kind": "int"},
        {"name": "anchor", "label": "Anchor", "kind": "choice", "choices": _anchor_choices_tk()},
        {"name": "colour", "label": "Colour", "kind": "choice", "choices": _colour_choices()},
    ]
    init = {
        "text": lab.text,
        "x": lab.p.x,
        "y": lab.p.y,
        "snap_to_grid": False,
        "snap_flag": getattr(lab, "snap", True),
        "size": lab.size,
        "rotation": getattr(lab, "rotation", 0),
        "anchor": lab.anchor.tk,
        "colour": lab.col.name,
    }
    dlg = GenericEditDialog(parent, "Edit Label", schema, init)
    return getattr(dlg, "result", None)


def edit_icon(parent: tk.Misc, ico: Icon, icon_name_choices: list[str]) -> dict[str, Any] | None:
    schema = [
        {"name": "name", "label": "Icon", "kind": "choice", "choices": icon_name_choices},
        {"name": "x", "label": "X", "kind": "int", "min": 0},
        {"name": "y", "label": "Y", "kind": "int", "min": 0},
        {"name": "snap_to_grid", "label": "Snap X/Y to grid now", "kind": "bool"},
        {"name": "snap_flag", "label": "Keep snapped when dragging", "kind": "bool"},
        {"name": "size", "label": "Size", "kind": "int", "min": 1},
        {"name": "rotation", "label": "Rotation (deg)", "kind": "int"},
        {"name": "anchor", "label": "Anchor", "kind": "choice", "choices": _anchor_choices_tk()},
        {"name": "colour", "label": "Colour", "kind": "choice", "choices": _colour_choices()},
    ]
    init = {
        "name": ico.name,
        "x": ico.p.x,
        "y": ico.p.y,
        "snap_to_grid": False,
        "snap_flag": getattr(ico, "snap", True),
        "size": ico.size,
        "rotation": getattr(ico, "rotation", 0),
        "anchor": ico.anchor.tk,
        "colour": ico.col.name,
    }
    dlg = GenericEditDialog(parent, "Edit Icon", schema, init)
    return getattr(dlg, "result", None)


def edit_line(parent: tk.Misc, ln: Line) -> dict[str, Any] | None:
    schema = [
        {"name": "x1", "label": "X1", "kind": "int", "min": 0},
        {"name": "y1", "label": "Y1", "kind": "int", "min": 0},
        {"name": "x2", "label": "X2", "kind": "int", "min": 0},
        {"name": "y2", "label": "Y2", "kind": "int", "min": 0},
        {"name": "snap_to_grid", "label": "Snap endpoints to grid", "kind": "bool"},
        {"name": "width", "label": "Width", "kind": "int", "min": 1},
        {"name": "capstyle", "label": "Cap", "kind": "choice", "choices": _cap_choices()},
        {"name": "style", "label": "Dash", "kind": "choice", "choices": _style_choices()},
        {"name": "colour", "label": "Colour", "kind": "choice", "choices": _colour_choices()},
        # If reintroduce offset later;
        # {"name": "dash_offset", "label": "Dash offset", "kind": "int", "min": 0},
    ]
    init = {
        "x1": ln.a.x,
        "y1": ln.a.y,
        "x2": ln.b.x,
        "y2": ln.b.y,
        "snap_to_grid": False,
        "width": ln.width,
        "capstyle": ln.capstyle,
        "style": getattr(ln, "style", None) or "solid",
        "colour": ln.col.name,
        # "dash_offset": getattr(ln, "dash_offset", 0),
    }
    dlg = GenericEditDialog(parent, "Edit Line", schema, init)
    return getattr(dlg, "result", None)
