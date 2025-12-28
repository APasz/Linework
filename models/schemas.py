"""Schema helpers for settings dialogs."""

from typing import Any

from models.geo import IconType
from models.styling import Anchor, LineStyle


def settings_schema() -> list[dict[str, Any]]:
    """Return the settings schema for the UI dialog."""
    styles = [s.value for s in LineStyle]
    anchors = [a.value for a in Anchor]
    return [
        {
            "name": "default_project",
            "label": "Default project (startup)",
            "kind": "project_path",
            "section": "General",
        },
        {
            "name": "storage_mode",
            "label": "Storage mode",
            "kind": "choice",
            "choices": ["Portable", "Standard"],
            "section": "General",
        },
        {
            "name": "custom_palette_shared",
            "label": "Share custom palette across projects",
            "kind": "bool",
            "section": "General",
        },
        {
            "name": "window_width",
            "label": "Initial window width (0 = auto)",
            "kind": "int",
            "min": 0,
            "section": "General",
        },
        {
            "name": "window_height",
            "label": "Initial window height (0 = auto)",
            "kind": "int",
            "min": 0,
            "section": "General",
        },
        {
            "name": "remember_window_size",
            "label": "Remember window size",
            "kind": "bool",
            "section": "General",
        },
        {
            "name": "auto_expand_window",
            "label": "Auto-expand fit canvas",
            "kind": "bool",
            "section": "General",
        },
        {
            "name": "auto_shrink_window",
            "label": "Auto-shrink fit canvas",
            "kind": "bool",
            "section": "General",
        },
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
            "multiple_of": "grid_step",
        },
        {
            "name": "grid_step",
            "label": "Grid step",
            "kind": "int",
            "min": 1,
            "max": 1000,
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
            "name": "continuous_draw",
            "label": "Continuous draw",
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
            "section": "Label",
        },
        {
            "name": "label_rotation",
            "label": "Label rotation (deg)",
            "kind": "int",
            "section": "Label",
        },
        {
            "name": "label_anchor",
            "label": "Label anchor",
            "kind": "choice",
            "choices": anchors,
            "sort": False,
            "section": "Label",
        },
        {
            "name": "label_snap",
            "label": "Label snap",
            "kind": "bool",
            "section": "Label",
        },
        {
            "name": "label_colour",
            "label": "Label colour",
            "kind": "colour",
            "section": "Label",
        },
        {
            "name": "default_icon_kind",
            "label": "Default icon kind",
            "kind": "choice",
            "choices": [IconType.builtin.value, IconType.picture.value],
            "section": "Icon",
        },
        {
            "name": "default_icon_builtin",
            "label": "Default icon",
            "kind": "icon_builtin",
            "section": "Icon",
        },
        {
            "name": "default_icon_picture",
            "label": "Default icon",
            "kind": "icon_picture",
            "section": "Icon",
        },
        {
            "name": "icon_size",
            "label": "Icon size (builtin)",
            "kind": "int",
            "min": 1,
            "section": "Icon",
        },
        {
            "name": "picture_size",
            "label": "Icon size (picture)",
            "kind": "int",
            "min": 1,
            "section": "Icon",
        },
        {
            "name": "icon_rotation",
            "label": "Icon rotation (deg)",
            "kind": "int",
            "section": "Icon",
        },
        {
            "name": "icon_anchor",
            "label": "Icon anchor",
            "kind": "choice",
            "choices": anchors,
            "sort": False,
            "section": "Icon",
        },
        {
            "name": "icon_snap",
            "label": "Icon snap",
            "kind": "bool",
            "section": "Icon",
        },
        {
            "name": "icon_colour",
            "label": "Icon colour",
            "kind": "colour",
            "section": "Icon",
        },
    ]
