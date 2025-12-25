"""Schema helpers for settings dialogs."""

from typing import Any

from models.geo import Icon_Type
from models.styling import Anchor, LineStyle


def settings_schema() -> list[dict[str, Any]]:
    """Return the settings schema for the UI dialog."""
    styles = [s.value for s in LineStyle]
    anchors = [a.value for a in Anchor]
    return [
        {
            "name": "width",
            "label": "Canvas width",
            "kind": "int",
            "min": 1,
            "section": "Canvas",
            "multiple_of": "grid_size",
        },
        {
            "name": "height",
            "label": "Canvas height",
            "kind": "int",
            "min": 1,
            "section": "Canvas",
            "multiple_of": "grid_size",
        },
        {
            "name": "grid_size",
            "label": "Grid size",
            "kind": "int",
            "min": 0,
            "section": "Canvas",
        },
        {
            "name": "grid_visible",
            "label": "Show grid",
            "kind": "bool",
            "section": "Canvas",
        },
        {
            "name": "grid_colour",
            "label": "Grid colour",
            "kind": "colour",
            "section": "Canvas",
        },
        {
            "name": "bg_colour",
            "label": "Background",
            "kind": "colour",
            "section": "Canvas",
        },
        {
            "name": "drag_to_draw",
            "label": "Drag to draw",
            "kind": "bool",
            "section": "Draw",
        },
        {
            "name": "cardinal_snap",
            "label": "Cardinal snap",
            "kind": "bool",
            "section": "Draw",
        },
        {
            "name": "brush_width",
            "label": "Line width",
            "kind": "int",
            "min": 1,
            "section": "Draw",
        },
        {
            "name": "line_style",
            "label": "Line style",
            "kind": "choice",
            "choices": styles,
            "section": "Draw",
        },
        {
            "name": "line_dash_offset",
            "label": "Dash offset",
            "kind": "int",
            "min": 0,
            "section": "Draw",
        },
        {
            "name": "brush_colour",
            "label": "Brush colour",
            "kind": "colour",
            "section": "Draw",
        },
        {
            "name": "label_size",
            "label": "Label size",
            "kind": "int",
            "min": 1,
            "section": "Labels",
        },
        {
            "name": "label_rotation",
            "label": "Label rotation (deg)",
            "kind": "int",
            "section": "Labels",
        },
        {
            "name": "label_anchor",
            "label": "Label anchor",
            "kind": "choice",
            "choices": anchors,
            "sort": False,
            "section": "Labels",
        },
        {
            "name": "label_snap",
            "label": "Label snap",
            "kind": "bool",
            "section": "Labels",
        },
        {
            "name": "label_colour",
            "label": "Label colour",
            "kind": "colour",
            "section": "Labels",
        },
        {
            "name": "default_icon_kind",
            "label": "Default icon kind",
            "kind": "choice",
            "choices": [Icon_Type.builtin.value, Icon_Type.picture.value],
            "section": "Icons",
        },
        {
            "name": "default_icon_builtin",
            "label": "Default icon",
            "kind": "icon_builtin",
            "section": "Icons",
        },
        {
            "name": "default_icon_picture",
            "label": "Default icon",
            "kind": "icon_picture",
            "section": "Icons",
        },
        {
            "name": "icon_size",
            "label": "Icon size (builtin)",
            "kind": "int",
            "min": 1,
            "section": "Icons",
        },
        {
            "name": "picture_size",
            "label": "Icon size (picture)",
            "kind": "int",
            "min": 1,
            "section": "Icons",
        },
        {
            "name": "icon_rotation",
            "label": "Icon rotation (deg)",
            "kind": "int",
            "section": "Icons",
        },
        {
            "name": "icon_anchor",
            "label": "Icon anchor",
            "kind": "choice",
            "choices": anchors,
            "sort": False,
            "section": "Icons",
        },
        {
            "name": "icon_snap",
            "label": "Icon snap",
            "kind": "bool",
            "section": "Icons",
        },
        {
            "name": "icon_colour",
            "label": "Icon colour",
            "kind": "colour",
            "section": "Icons",
        },
    ]
