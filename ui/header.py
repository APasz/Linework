from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass
class Header_Handles:
    frame: ttk.Frame


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


def create_header(
    master,
    mode_var: tk.StringVar,  # "draw" | "label" | "icon" | "select"
    icon_var: tk.StringVar,  # current icon name
    on_toggle_grid,
    on_undo,
    on_redo,
    on_clear,
    on_save,
    on_export,
    on_new,
    on_open,
    on_save_as,
):
    """Builds the header strip and returns handles."""
    frame = ttk.Frame(master)
    frame.pack(fill="x", side="top")

    # Actions
    _add_labeled(frame, lambda p: ttk.Button(p, text="Grid (G)", command=on_toggle_grid))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Undo (Z)", command=on_undo))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Redo (Y)", command=on_redo))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Clear (C)", command=on_clear))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Export…", command=on_export))
    _add_labeled(frame, lambda p: ttk.Button(p, text="New", command=on_new))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Open…", command=on_open))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Save", command=on_save))
    _add_labeled(frame, lambda p: ttk.Button(p, text="Save As…", command=on_save_as))

    # Modes
    _add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Draw", value="draw", variable=mode_var))
    _add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Label", value="label", variable=mode_var))
    _add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Select", value="select", variable=mode_var))
    _add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Icon:", value="icon", variable=mode_var))

    # Icon picker
    _add_labeled(
        frame,
        lambda p: ttk.Combobox(
            p, textvariable=icon_var, values=["signal", "switch", "buffer", "crossing"], state="readonly", width=10
        ),
        # "Icon:",
    )

    return Header_Handles(frame=frame)
