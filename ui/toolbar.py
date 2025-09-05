from __future__ import annotations
from dataclasses import dataclass
from tkinter import ttk
import tkinter as tk

from ui.widgets.composite_spinbox import VerticalSpinbox
from models.colour import Colours as Cols


@dataclass
class ToolbarHandles:
    frame: ttk.Frame
    spin_grid: VerticalSpinbox
    spin_brush: VerticalSpinbox
    spin_w: VerticalSpinbox
    spin_h: VerticalSpinbox
    cb_bg: ttk.Combobox


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
    on_grid_change,
    on_brush_change,
    on_canvas_size_change,
):
    """Builds the toolbar strip and returns widget handles."""
    frame = ttk.Frame(master)
    frame.pack(fill="x", side="top")

    spin_grid = _add_labeled(
        frame,
        lambda p: VerticalSpinbox(
            p, from_=0, to=200, increment=5, width=3, textvariable=grid_var, command=on_grid_change
        ),
        "Grid:",
    )
    spin_brush = _add_labeled(
        frame,
        lambda p: VerticalSpinbox(
            p, from_=1, to=50, increment=1, width=3, textvariable=brush_var, command=on_brush_change
        ),
        "Line:",
    )
    spin_w = _add_labeled(
        frame,
        lambda p: VerticalSpinbox(
            p, from_=100, to=10000, increment=50, width=4, textvariable=width_var, command=on_canvas_size_change
        ),
        "W:",
    )
    spin_h = _add_labeled(
        frame,
        lambda p: VerticalSpinbox(
            p, from_=100, to=10000, increment=50, width=4, textvariable=height_var, command=on_canvas_size_change
        ),
        "H:",
    )

    cb_bg = _add_labeled(
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

    # Enter key triggers
    for sb in (spin_grid, spin_brush, spin_w, spin_h):
        sb.bind("<Return>", lambda _e: (on_grid_change(), on_brush_change(), on_canvas_size_change()))

    return ToolbarHandles(
        frame=frame, spin_grid=spin_grid, spin_brush=spin_brush, spin_w=spin_w, spin_h=spin_h, cb_bg=cb_bg
    )
