from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk

from models.colour import Colours as Cols
from models.linestyle import LineStyle
from ui.palette import Palette_Handles, create_palette
from ui.widgets.composite_spinbox import Composite_Spinbox


@dataclass
class Toolbar_Handles:
    frame: ttk.Frame
    spin_grid: Composite_Spinbox
    spin_brush: Composite_Spinbox
    spin_w: Composite_Spinbox
    spin_h: Composite_Spinbox
    cb_bg: ttk.Combobox
    cb_dtd: ttk.Checkbutton
    cb_snap: ttk.Checkbutton
    cb_style: ttk.Combobox
    # spin_offset: Composite_Spinbox
    palette: Palette_Handles


def _add_labeled(master: ttk.Frame, make_widget, text: str = "", right_label: bool = False):
    f = ttk.Frame(master)
    if not right_label and text:
        ttk.Label(f, text=text).pack(side="left")
    w = make_widget(f)
    w.pack(side="left")
    if right_label and text:
        ttk.Label(f, text=text).pack(side="left")
    f.pack(side="left", padx=4)
    return w


def create_toolbar(
    master,
    grid_var: tk.IntVar,
    brush_var: tk.IntVar,
    width_var: tk.IntVar,
    height_var: tk.IntVar,
    bg_var: tk.StringVar,
    drag_to_draw_var: tk.BooleanVar,
    snapping_var: tk.BooleanVar,
    style_var: tk.StringVar,
    offset_var: tk.IntVar,
    on_grid_change,
    on_brush_change,
    on_canvas_size_change,
    on_palette_select,
    on_palette_set_bg,
    on_style_change,
    selected_colour_name: str,
):
    """Builds the toolbar strip and returns widget handles."""
    frame = ttk.Frame(master)
    frame.pack(fill="x", side="top")

    sbox_grid = _add_labeled(
        frame,
        lambda p: Composite_Spinbox(
            p, from_=0, to=200, increment=5, width=3, textvariable=grid_var, command=on_grid_change
        ),
        "Grid:",
    )
    sbox_brush = _add_labeled(
        frame,
        lambda p: Composite_Spinbox(
            p, from_=1, to=50, increment=1, width=3, textvariable=brush_var, command=on_brush_change
        ),
        "Line:",
    )
    sbox_w = _add_labeled(
        frame,
        lambda p: Composite_Spinbox(
            p, from_=100, to=10000, increment=50, width=4, textvariable=width_var, command=on_canvas_size_change
        ),
        "W:",
    )
    sbox_h = _add_labeled(
        frame,
        lambda p: Composite_Spinbox(
            p, from_=100, to=10000, increment=50, width=4, textvariable=height_var, command=on_canvas_size_change
        ),
        "H:",
    )

    cbox_bg = _add_labeled(
        frame,
        lambda p: ttk.Combobox(
            p,
            textvariable=bg_var,
            values=Cols.option_str(min_trans=0),  # include transparent
            state="readonly",
            width=10,
        ),
        "BG:",
    )
    cbut_dtd = _add_labeled(
        frame,
        lambda p: ttk.Checkbutton(
            p,
            variable=drag_to_draw_var,
        ),
        "Drag to draw:",
    )
    cbut_snap = _add_labeled(
        frame,
        lambda p: ttk.Checkbutton(
            p,
            variable=snapping_var,
        ),
        "Snap:",
    )
    styles = [s.value for s in LineStyle]
    cb_style = _add_labeled(
        frame,
        lambda p: ttk.Combobox(p, values=styles, state="readonly", width=9, textvariable=style_var),
        "Style:",
    )
    cb_style.bind("<<ComboboxSelected>>", lambda _e: on_style_change())
    # spin_off = _add_labeled(
    #    frame,
    #    lambda p: Composite_Spinbox(
    #        p, from_=0, to=999, increment=1, width=3, textvariable=offset_var, command=on_style_change
    #    ),
    #    "Offset:",
    # )

    pal = create_palette(
        frame,
        colours=Cols.option_col(min_trans=255),
        on_select=on_palette_select,
        on_set_bg=on_palette_set_bg,
        selected_name=selected_colour_name,
    )

    # Enter key triggers
    for sb in (sbox_grid, sbox_brush, sbox_w, sbox_h):
        sb.bind("<Return>", lambda _e: (on_grid_change(), on_brush_change(), on_canvas_size_change()))

    return Toolbar_Handles(
        frame=frame,
        spin_grid=sbox_grid,
        spin_brush=sbox_brush,
        spin_w=sbox_w,
        spin_h=sbox_h,
        cb_bg=cbox_bg,
        cb_dtd=cbut_dtd,
        cb_snap=cbut_snap,
        cb_style=cb_style,
        # spin_offset=spin_off,
        palette=pal,
    )
