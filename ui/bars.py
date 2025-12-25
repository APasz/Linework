"""Toolbar, header, and status bar widgets."""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from enum import StrEnum
from tkinter import ttk
from typing import TypeVar

from PIL import Image, ImageTk

from models.geo import CanvasLW
from models.styling import Colour, Colours, LineStyle
from ui.colour_picker import ask_colour
from ui.composite_spinbox import Composite_Spinbox


class Tool_Name(StrEnum):
    """Tool mode identifiers."""

    draw = "draw"
    label = "label"
    icon = "icon"
    select = "select"


TWidget = TypeVar("TWidget", bound=tk.Widget)


@dataclass
class Palette_Handles:
    """Handles for a colour palette widget."""

    frame: ttk.Frame
    set_selected: Callable[[str], None]
    "call with colour hexa"


def _checker_photo(
    master: tk.Misc,
    w: int = 20,
    h: int = 20,
    tile: int = 4,
    a: str = "#eeeeee",
    b: str = "#cccccc",
) -> ImageTk.PhotoImage:
    img = Image.new("RGB", (w, h), a)
    for y in range(0, h, tile):
        start = ((y // tile) % 2) * tile
        for x in range(start, w, tile * 2):
            Image.Image.paste(img, b, (x, y, x + tile, y + tile))
    return ImageTk.PhotoImage(img, master=master)


def _draw_swatch(canvas: CanvasLW, col: Colour, *, outline: str) -> int:
    if not canvas.cache.checker_ref:
        ph = _checker_photo(canvas, 20, 20)
        canvas.cache.checker_ref = (0, ph)
    canvas.create_image(1, 1, image=canvas.cache.checker_ref[1], anchor="nw")
    if col.alpha == 0:
        return canvas.create_rectangle(1, 1, 21, 21, outline=outline, fill="")
    return canvas.create_rectangle(
        1,
        1,
        21,
        21,
        outline=outline,
        fill=col.hexh,
        stipple=CanvasLW._stipple_for_alpha(col.alpha) or "",
    )


class Colour_Palette(ttk.Frame):
    """Palette button with a popup grid of colours."""

    _open_owner: "Colour_Palette | None" = None

    def __init__(
        self,
        master: tk.Misc,
        colours: Iterable[Colour],
        on_select: Callable[[str], None],
        custom: list[Colour | None] | None = None,
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ) -> None:
        """Create a colour palette widget.

        Args;
            master: The parent widget.
            colours: The palette colours.
            on_select: Callback when a colour is selected.
            custom: Optional custom colours.
            on_update_custom: Optional callback when custom colours change.
        """
        super().__init__(master)
        self._on_select = on_select
        self._colours = list(colours)
        self._swatches: list[tuple[CanvasLW, str]] = []
        self._popup: tk.Toplevel | None = None
        self._custom: list[Colour | None] = custom if custom is not None else [None] * len(Colours.list())
        self._on_update_custom = on_update_custom

        self._canvas = CanvasLW(self, width=22, height=22, highlightthickness=1)
        self._btn = self._canvas
        self._btn.configure(
            highlightbackground=Colours.sys.dark_gray.hexh,
            highlightcolor=Colours.sys.dark_gray.hexh,
        )
        self._rect_id = _draw_swatch(self._btn, Colours.black, outline=Colours.black.hexh)
        self._btn.pack(side="left", padx=4)
        self._btn.bind("<Button-1>", self._toggle_popup)

    # ------- popup -------
    def _toggle_popup(self, _evt: tk.Event | None = None) -> None:
        if self._popup:
            self._close_popup()
        else:
            if Colour_Palette._open_owner and Colour_Palette._open_owner is not self:
                try:
                    Colour_Palette._open_owner._close_popup()
                except Exception:
                    pass
            self._open_popup()

    def _open_popup(self, _evt: tk.Event | None = None) -> None:
        self._close_popup()
        Colour_Palette._open_owner = self
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        top.transient(self.winfo_toplevel())

        bx = self._btn.winfo_rootx()
        by = self._btn.winfo_rooty() + self._btn.winfo_height()
        top.geometry(f"+{bx}+{by}")

        frame = ttk.Frame(top, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)

        left = ttk.Frame(frame)
        left.pack(side="left", padx=6, pady=6)
        right = ttk.Frame(frame)
        right.pack(side="left", padx=(0, 6), pady=6)
        ttk.Label(right, text="Custom").pack(anchor="w", padx=2, pady=(0, 4))

        self._swatches.clear()
        # Built-ins (left)
        for col in self._colours:
            c = CanvasLW(left, width=22, height=22, highlightthickness=0)
            _draw_swatch(c, col, outline=Colours.sys.dark_gray.hexh)
            # c.create_rectangle(1, 1, 21, 21, outline=Colours.sys.dark_gray.hexh, fill=col.hexh)
            c.bind("<Button-1>", lambda _e, hexa=col.hexah: (self._select(hexa), self._close_popup()))
            c.pack(side="top", pady=2)
            self._swatches.append((c, col.hexah))

        # Custom (right)
        for i, val in enumerate(self._custom):
            c = CanvasLW(right, width=22, height=22, highlightthickness=0)
            # fill = Colours.white.hexh if val is None else val.hexh
            # c.create_rectangle(1, 1, 21, 21, outline=Colours.sys.dark_gray.hexh, fill=fill)
            if val is None:
                c.create_rectangle(1, 1, 21, 21, outline=Colours.sys.dark_gray.hexh, fill=Colours.white.hexh)
                c.bind("<Button-1>", lambda _e, i=i: self._edit_custom(i, None))
            else:
                _draw_swatch(c, val, outline=Colours.sys.dark_gray.hexh)
                c.bind("<Button-1>", lambda _e, hexa=val.hexah: (self._select(hexa), self._close_popup()))
                c.bind("<Shift-Button-1>", lambda _e, i=i, init=val: self._edit_custom(i, init))
            c.bind("<Button-3>", lambda _e, i=i: self._clear_custom(i))
            c.pack(side="top", pady=2)
            self._swatches.append((c, val.hexah if val else ""))

        top.focus_force()
        try:
            top.grab_set()
        except Exception:
            pass

        self._popup = top
        top.bind("<Destroy>", self._on_popup_destroy, add="+")
        top.after_idle(self._arm_outside_handlers)

    def _on_popup_destroy(self, _e: tk.Event | None = None) -> None:
        try:
            self.unbind_all("<Escape>")
            self.unbind_all("<ButtonRelease-1>")
        except Exception:
            pass
        self._popup = None
        self._swatches.clear()
        if Colour_Palette._open_owner is self:
            Colour_Palette._open_owner = None

    def _close_popup(self) -> None:
        if self._popup is not None:
            try:
                self.unbind_all("<Escape>")
                self.unbind_all("<ButtonRelease-1>")
                self._popup.grab_release()
            except Exception:
                pass
            try:
                self._popup.destroy()
            except Exception:
                pass
            self._popup = None
            self._swatches.clear()
            if Colour_Palette._open_owner is self:
                Colour_Palette._open_owner = None

    def _arm_outside_handlers(self) -> None:
        if not self._popup:
            return
        self._popup.update_idletasks()
        self.bind_all("<Escape>", lambda _evt: self._close_popup(), add="+")
        self.bind_all("<ButtonRelease-1>", self._maybe_close_on_click, add="+")

    def _ask_custom_colour(self, initial: Colour | None) -> Colour | None:
        return ask_colour(self, initial)

    def _edit_custom(self, idx: int, initial: Colour | None) -> None:
        self._close_popup()
        try:
            col = self._ask_custom_colour(initial)
        except tk.TclError as exc:
            if "application has been destroyed" in str(exc):
                return
            raise
        if not col:
            return
        self._custom[idx] = col
        if self._on_update_custom:
            self._on_update_custom(idx, col)
        self._select(col.hexah)

    def _clear_custom(self, idx: int) -> None:
        self._custom[idx] = None
        if self._on_update_custom:
            self._on_update_custom(idx, None)
        self._close_popup()

    def _maybe_close_on_click(self, evt: tk.Event) -> None:
        if not self._popup or not self._popup.winfo_exists():
            self._popup = None
            return
        x, y = evt.x_root, evt.y_root
        px, py = self._popup.winfo_rootx(), self._popup.winfo_rooty()
        pw, ph = self._popup.winfo_width(), self._popup.winfo_height()
        inside = (px <= x < px + pw) and (py <= y < py + ph)
        if inside:
            return

        bx, by = self._btn.winfo_rootx(), self._btn.winfo_rooty()
        bw, bh = self._btn.winfo_width(), self._btn.winfo_height()
        on_btn = (bx <= x < bx + bw) and (by <= y < by + bh)
        if on_btn:
            return

        self._close_popup()

    # ------- selection -------
    def _select(self, name: str) -> None:
        self._on_select(name)
        self._update_highlight(name)

    def _update_highlight(self, selected: str) -> None:
        try:
            col = next((c for c in self._colours if c.hexah == selected), None) or Colours.parse_colour(selected)
            if col.alpha == 0:
                self._btn.itemconfigure(self._rect_id, fill="", stipple="")
            else:
                self._btn.itemconfigure(
                    self._rect_id,
                    fill=col.hexh,
                    stipple=self._canvas._stipple_for_alpha(col.alpha) or "",
                )
        except Exception:
            pass


@dataclass
class Header_Handles:
    """Handles for the header bar widgets."""

    frame: ttk.Frame


@dataclass
class Toolbar_Handles:
    """Handles for the toolbar widgets."""

    frame: ttk.Frame
    spin_grid: Composite_Spinbox
    spin_brush: Composite_Spinbox
    spin_w: Composite_Spinbox
    spin_h: Composite_Spinbox
    cb_dtd: ttk.Checkbutton
    cb_cardinal: ttk.Checkbutton
    cb_style: ttk.Combobox
    palette_brush: Palette_Handles
    palette_bg: Palette_Handles
    palette_label: Palette_Handles
    palette_icon: Palette_Handles


class Side(StrEnum):
    """Status bar sides."""

    left = "left"
    centre = "centre"
    right = "right"


@dataclass(order=True)
class _Overlay:
    """Overlay entry for the status bar."""

    sort_key: tuple[int, int] = field(init=False, repr=False)
    key: str
    text: str
    priority: int = 0
    side: Side = Side.left
    seq: int = 0

    def __post_init__(self) -> None:
        self.sort_key = (-self.priority, self.seq)


class Status_Handles(ttk.Frame):
    """Status bar widget container."""

    def __init__(self, master: tk.Misc, status: "Bars.Status") -> None:
        super().__init__(master)
        self.frame = self

        # three lanes: left | centre | right
        self.lbl_left = ttk.Label(self, textvariable=status.var_left, anchor="w")
        self.lbl_centre = ttk.Label(self, textvariable=status.var_centre, anchor="center")
        self.lbl_right = ttk.Label(self, textvariable=status.var_right, anchor="e")

        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

        self.lbl_left.grid(row=0, column=0, sticky="w", padx=6)
        self.lbl_right.grid(row=0, column=2, sticky="e", padx=6)
        self.lbl_centre.place(relx=0.5, rely=0.5, anchor="center")
        self.lbl_centre.lower()


class Bars:
    """Factory helpers for UI bars."""

    @classmethod
    def create_status(cls, master: tk.Misc, status: "Bars.Status") -> Status_Handles:
        """Create and pack the status bar.

        Args;
            master: The parent widget.
            status: The status state container.

        Returns;
            The status bar handles.
        """
        strip = Status_Handles(master, status)
        strip.pack(fill="x", side="bottom")
        return strip

    @staticmethod
    def _add_labeled(
        master: ttk.Frame,
        make_widget: Callable[[ttk.Frame], TWidget],
        text: str = "",
        right_label: bool = False,
    ) -> TWidget:
        f = ttk.Frame(master)
        if not right_label and text:
            ttk.Label(f, text=text).pack(side="left")
        w = make_widget(f)
        w.pack(side="left")
        if right_label and text:
            ttk.Label(f, text=text).pack(side="left")
        f.pack(side="left", padx=4)
        return w

    @classmethod
    def create_palette(
        cls,
        master: tk.Misc,
        colours: Iterable[Colour],
        on_select: Callable[[str], None],
    ) -> Palette_Handles:
        """Create a palette button and return its handles.

        Args;
            master: The parent widget.
            colours: The palette colours.
            on_select: Callback on selection.

        Returns;
            The palette handles.
        """
        pal = Colour_Palette(master, colours, on_select)
        pal.pack(side="right", padx=8)
        return Palette_Handles(frame=pal, set_selected=pal._update_highlight)

    @classmethod
    def create_header(
        cls,
        master: tk.Misc,
        mode_var: tk.StringVar,
        on_toggle_grid: Callable[[], None],
        on_undo: Callable[[], None],
        on_redo: Callable[[], None],
        on_save: Callable[[], bool | None],
        on_export: Callable[[], None],
        on_new: Callable[[], None],
        on_open: Callable[[], None],
        on_save_as: Callable[[], bool | None],
        on_settings: Callable[[], None],
        icon_label_var: tk.StringVar | None = None,
    ) -> Header_Handles:
        """Build the header strip and return handles.

        Args;
            master: The parent widget.
            mode_var: The tool mode variable.
            on_toggle_grid: Grid toggle callback.
            on_undo: Undo callback.
            on_redo: Redo callback.
            on_save: Save callback.
            on_export: Export callback.
            on_new: New project callback.
            on_open: Open callback.
            on_save_as: Save-as callback.
            on_settings: Settings callback.
            icon_label_var: Optional icon label variable.

        Returns;
            The header handles.
        """
        frame = ttk.Frame(master)
        frame.pack(fill="x", side="top")

        # Actions
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Grid (G)", command=on_toggle_grid))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Undo (Ctrl+Z)", command=on_undo))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Redo (Ctrl+Y)", command=on_redo))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Export…", command=on_export))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="New", command=on_new))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Open…", command=on_open))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Save", command=on_save))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Save As…", command=on_save_as))
        cls._add_labeled(frame, lambda p: ttk.Button(p, text="Settings…", command=on_settings))

        # Modes
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Select", value=Tool_Name.select, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Draw", value=Tool_Name.draw, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Label", value=Tool_Name.label, variable=mode_var))
        cls._add_labeled(frame, lambda p: ttk.Radiobutton(p, text="Icon", value=Tool_Name.icon, variable=mode_var))

        if icon_label_var is not None:
            cls._add_labeled(frame, lambda p: ttk.Label(p, textvariable=icon_label_var), "")

        return Header_Handles(frame=frame)

    @classmethod
    def create_toolbar(
        cls,
        master: tk.Misc,
        grid_var: tk.IntVar,
        brush_var: tk.IntVar,
        width_var: tk.IntVar,
        height_var: tk.IntVar,
        drag_to_draw_var: tk.BooleanVar,
        cardinal_var: tk.BooleanVar,
        style_var: tk.StringVar,
        on_grid_change: Callable[[], None],
        on_brush_change: Callable[[], None],
        on_canvas_size_change: Callable[[], None],
        on_style_change: Callable[[], None],
        on_palette_select_brush: Callable[[str], None],
        on_palette_select_bg: Callable[[str], None],
        on_palette_select_label: Callable[[str], None],
        on_palette_select_icon: Callable[[str], None],
        custom_palette: list[Colour | None] | None = None,
        on_update_custom: Callable[[int, Colour | None], None] | None = None,
    ) -> Toolbar_Handles:
        """Build the toolbar strip and return widget handles.

        Args;
            master: The parent widget.
            grid_var: Grid size variable.
            brush_var: Brush width variable.
            width_var: Canvas width variable.
            height_var: Canvas height variable.
            drag_to_draw_var: Drag-to-draw toggle variable.
            cardinal_var: Cardinal snap toggle variable.
            style_var: Line style variable.
            on_grid_change: Grid change callback.
            on_brush_change: Brush change callback.
            on_canvas_size_change: Canvas size callback.
            on_style_change: Style change callback.
            on_palette_select_brush: Brush colour selection callback.
            on_palette_select_bg: Background colour selection callback.
            on_palette_select_label: Label colour selection callback.
            on_palette_select_icon: Icon colour selection callback.
            custom_palette: Optional custom palette.
            on_update_custom: Optional custom palette update callback.

        Returns;
            The toolbar handles.
        """
        frame = ttk.Frame(master)
        frame.pack(fill="x", side="top")

        sbox_grid = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=0,
                to=200,
                increment=5,
                width=3,
                textvariable=grid_var,
                command=on_grid_change,
            ),
            "Grid:",
        )
        sbox_brush = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=1,
                to=50,
                increment=1,
                width=3,
                textvariable=brush_var,
                command=on_brush_change,
            ),
            "Line:",
        )
        sbox_w = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=100,
                to=10000,
                increment=50,
                width=4,
                textvariable=width_var,
                command=on_canvas_size_change,
            ),
            "W:",
        )
        sbox_h = cls._add_labeled(
            frame,
            lambda p: Composite_Spinbox(
                p,
                from_=100,
                to=10000,
                increment=50,
                width=4,
                textvariable=height_var,
                command=on_canvas_size_change,
            ),
            "H:",
        )

        cbut_dtd = cls._add_labeled(
            frame,
            lambda p: ttk.Checkbutton(
                p,
                variable=drag_to_draw_var,
            ),
            "Drag to draw:",
        )
        cbut_cardinal = cls._add_labeled(
            frame,
            lambda p: ttk.Checkbutton(
                p,
                variable=cardinal_var,
            ),
            "Cardinal:",
        )
        styles = [s.value for s in LineStyle]
        cb_style = cls._add_labeled(
            frame,
            lambda p: ttk.Combobox(
                p,
                values=sorted(styles, key=str.lower),
                state="readonly",
                width=9,
                textvariable=style_var,
                height=16,
            ),
            "Style:",
        )
        style_var.trace_add("write", lambda *_: on_style_change())

        def _make_brush(p: ttk.Frame) -> Colour_Palette:
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_brush,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        brush_widget = cls._add_labeled(frame, _make_brush, "Brush:")
        pal_brush = Palette_Handles(frame=brush_widget, set_selected=brush_widget._update_highlight)

        def _make_bg(p: ttk.Frame) -> Colour_Palette:
            return Colour_Palette(
                p,
                Colours.list(),
                on_select=on_palette_select_bg,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        bg_widget = cls._add_labeled(frame, _make_bg, "BG:")
        pal_bg = Palette_Handles(frame=bg_widget, set_selected=bg_widget._update_highlight)

        def _make_label(p: ttk.Frame) -> Colour_Palette:
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_label,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        lb_widget = cls._add_labeled(frame, _make_label, "Label:")
        pal_label = Palette_Handles(frame=lb_widget, set_selected=lb_widget._update_highlight)

        def _make_icon(p: ttk.Frame) -> Colour_Palette:
            return Colour_Palette(
                p,
                Colours.list(min_alpha=25),
                on_select=on_palette_select_icon,
                custom=custom_palette,
                on_update_custom=on_update_custom,
            )

        ic_widget = cls._add_labeled(frame, _make_icon, "Icon:")
        pal_icon = Palette_Handles(frame=ic_widget, set_selected=ic_widget._update_highlight)

        sbox_grid.bind("<Return>", lambda _e: on_grid_change())
        sbox_brush.bind("<Return>", lambda _e: on_brush_change())
        sbox_w.bind("<Return>", lambda _e: on_canvas_size_change())
        sbox_h.bind("<Return>", lambda _e: on_canvas_size_change())

        return Toolbar_Handles(
            frame=frame,
            spin_grid=sbox_grid,
            spin_brush=sbox_brush,
            spin_w=sbox_w,
            spin_h=sbox_h,
            cb_dtd=cbut_dtd,
            cb_cardinal=cbut_cardinal,
            cb_style=cb_style,
            palette_brush=pal_brush,
            palette_bg=pal_bg,
            palette_label=pal_label,
            palette_icon=pal_icon,
        )

    class Status:
        """Status bar state and overlay management."""

        def __init__(self, root: tk.Misc) -> None:
            """Create a status manager bound to a Tk root.

            Args;
                root: The Tk root for scheduling callbacks.
            """
            self.var_left = tk.StringVar(value="Ready")
            self.var_centre = tk.StringVar(value="")
            self.var_right = tk.StringVar(value="")
            self._root = root

            self._base_left: str = ""
            self._seq = 0

            self._held: dict[str, _Overlay] = {}
            self._temp_key: str | None = None
            self._temp_after: str | None = None

            self._centre_key = "__centre__"

        # ---- base ----
        def set(self, text: str) -> None:
            """Set the base left status text.

            Args;
                text: The status text.
            """
            self._base_left = text
            self._render()

        # ---- centre sugar ----
        def set_centre(self, text: str) -> None:
            """Set or clear the centre status text.

            Args;
                text: The centre text.
            """
            if text:
                self.hold(self._centre_key, text, priority=-10, side=Side.centre)
            else:
                self.release(self._centre_key)

        def clear_centre(self) -> None:
            """Clear the centre status text."""
            self.release(self._centre_key)

        # ---- held overlays (persistent until release) ----
        def hold(self, key: str, text: str, *, priority: int = 0, side: Side = Side.left) -> None:
            """Hold an overlay until released.

            Args;
                key: Overlay identifier.
                text: Overlay text.
                priority: Higher values win.
                side: Which side to display on.
            """
            self._seq += 1
            self._held[key] = _Overlay(key=key, text=text, priority=priority, side=side, seq=self._seq)
            self._render()

        def release(self, key: str) -> None:
            """Release a held overlay.

            Args;
                key: Overlay identifier.
            """
            if key in self._held:
                del self._held[key]
                if self._temp_key == key:
                    self._temp_key = None
                self._render()

        # ---- temporary overlays (auto-clear) ----
        def temp(self, text: str, ms: int = 1500, *, priority: int = 50, side: Side = Side.centre) -> None:
            """Show a temporary overlay.

            Args;
                text: Overlay text.
                ms: Duration in milliseconds.
                priority: Priority of the overlay.
                side: Which side to display on.
            """
            # cancel previous timer
            if self._temp_after:
                try:
                    self._root.after_cancel(self._temp_after)
                except Exception:
                    pass
                self._temp_after = None

            # temp overlay is just a special held
            key = "__temp__"
            self.hold(key, text, priority=priority, side=side)
            self._temp_key = key
            self._temp_after = self._root.after(ms, self._clear_temp)

        def _clear_temp(self) -> None:
            if self._temp_key:
                self.release(self._temp_key)
            self._temp_after = None

        # ---- clear all ----
        def clear(self) -> None:
            """Clear all status text and overlays."""
            self._base_left = ""
            self._held.clear()
            if self._temp_after:
                try:
                    self._root.after_cancel(self._temp_after)
                except Exception:
                    pass
                self._temp_after = None
            self._temp_key = None
            self._render()

        # ---- render ----
        def _render(self) -> None:
            self.var_left.set(self._pick_side(Side.left) or self._base_left)
            self.var_centre.set(self._pick_side(Side.centre) or "")
            self.var_right.set(self._pick_side(Side.right) or "")

        def _pick_side(self, side: Side) -> str:
            # choose the highest-priority overlay on this side
            items = [ov for ov in self._held.values() if ov.side == side]
            if not items:
                return ""
            top = sorted(items)[0]  # because sort_key is (-priority, seq)
            return top.text
