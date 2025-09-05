from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from pathlib import Path

import sv_ttk

from models.params import Params
from models.colour import Colours as Cols
from canvas.layers import LayerManager, LayerName
from canvas.painters import PaintersImpl
from controllers.commands import CommandStack
from controllers.tools import DrawTool, IconTool, LabelTool, SelectTool
from ui.header import create_header
from ui.toolbar import create_toolbar
from disk.storage import IO
from canvas.layers import L_GRID


class App:
    def __init__(self, root: tk.Tk, config_path: Path | None = None) -> None:
        self.root = root
        self.root.title("Linework")

        # ---- theme ----
        try:
            sv_ttk.set_theme("dark")
        except Exception:
            style = ttk.Style()
            print(f"Currently installed themes: {', '.join(style.theme_names())} | Defaulting to Alt")
            style.theme_use("Alt")

        # ---- params (load or defaults) ----
        self.config_path = config_path or Path("config.json")
        self.params = IO.load_params(self.config_path) if self.config_path.exists() else Params()

        # ---- UI state vars ----
        self.var_drag_to_draw = tk.BooleanVar(value=True)
        self.var_grid = tk.IntVar(value=self.params.grid_size)
        self.var_width_px = tk.IntVar(value=self.params.width)
        self.var_height_px = tk.IntVar(value=self.params.height)
        self.var_brush_w = tk.IntVar(value=self.params.brush_width)
        self.var_bg = tk.StringVar(value=self.params.bg_mode.name)
        self.var_color = tk.StringVar(value=self.params.brush_color.name)
        self.var_color.trace_add("write", self.apply_color)

        self.mode = tk.StringVar(value="draw")
        self.var_icon = tk.StringVar(value="signal")

        self.var_drag_to_draw.trace_add(
            "write", lambda *_: self.status.set("Mode: drag to draw" if self.drag_to_draw() else "Mode: click-click")
        )

        # ---- header & toolbar ----
        hdr = create_header(
            self.root,
            mode_var=self.mode,
            icon_var=self.var_icon,
            on_toggle_grid=self.toggle_grid,
            on_undo=self.on_undo,
            on_redo=self.on_redo,
            on_clear=self.on_clear,
            on_save=self.save_project,
            on_palette_select=lambda name: self.var_color.set(name),
            on_palette_set_bg=lambda name: self.var_bg.set(name),
            selected_colour_name=self.var_color.get(),
        )
        tbar = create_toolbar(
            self.root,
            grid_var=self.var_grid,
            brush_var=self.var_brush_w,
            width_var=self.var_width_px,
            height_var=self.var_height_px,
            bg_var=self.var_bg,
            drag_to_draw_var=self.var_drag_to_draw,
            on_grid_change=self.on_grid_change,
            on_brush_change=self.on_brush_change,
            on_canvas_size_change=self.on_canvas_size_change,
        )

        # ---- canvas ----
        display_bg = Cols.sys.dark_gray.hex if self.params.bg_mode.alpha == 0 else self.params.bg_mode.hex
        self.canvas = tk.Canvas(self.root, width=self.params.width, height=self.params.height, bg=display_bg)
        self.canvas.pack(fill="both", expand=False)

        # ---- status bar ----
        self.status = tk.StringVar(value="Ready")
        ttk.Label(self.root, textvariable=self.status, anchor="w").pack(fill="x")

        self.apply_color()

        # keep palette highlight in sync when brush colour changes
        self.var_color.trace_add("write", lambda *_: hdr.palette.set_selected(self.var_color.get()))
        self.var_bg.trace_add("write", self.apply_bg)

        # ---- scene/layers/painters ----
        class _SceneAdapter:
            def __init__(self, params: Params):
                self.params = params

            def lines(self):
                return self.params.lines

            def labels(self):
                return self.params.labels

            def icons(self):
                return self.params.icons

        self.scene = _SceneAdapter(self.params)
        self.painters = PaintersImpl(self.scene)
        self.layers = LayerManager(self.canvas, self.painters)

        # ---- commands & tools ----
        self.cmd = CommandStack()
        self.tools = {
            "draw": DrawTool(),
            "label": LabelTool(),
            "icon": IconTool(get_icon_name=lambda: self.var_icon.get()),
            "select": SelectTool(),
        }
        self.current_tool = self.tools[self.mode.get()]
        self.canvas.config(cursor=self.current_tool.cursor or "")

        # Make sure Canvas gets events before item-specific bindings
        tags = list(self.canvas.bindtags())
        # default order is (item, 'Canvas', 'all'); put Canvas first
        if "Canvas" in tags:
            tags.remove("Canvas")
            tags.insert(0, "Canvas")
        self.canvas.bindtags(tuple(tags))

        # bindings for tools
        self.canvas.bind("<ButtonPress-1>", lambda e: (self.current_tool.on_press(self, e), "break")[-1])
        self.canvas.bind("<B1-Motion>", lambda e: (self.current_tool.on_motion(self, e), "break")[-1])
        self.canvas.bind("<ButtonRelease-1>", lambda e: (self.current_tool.on_release(self, e), "break")[-1])
        self.canvas.bind(
            "<Motion>", lambda e: (getattr(self.current_tool, "on_hover", lambda *_: None)(self, e), "break")[-1]
        )
        self.root.bind("<Escape>", lambda _e: self.current_tool.on_cancel(self))

        # shortcuts
        self.root.bind("<KeyPress-g>", self.on_toggle_grid)
        self.root.bind("<KeyPress-G>", self.on_toggle_grid)
        self.root.bind("<KeyPress-z>", self.on_undo)
        self.root.bind("<KeyPress-Z>", self.on_undo)
        self.root.bind("<KeyPress-y>", self.on_redo)
        self.root.bind("<KeyPress-Y>", self.on_redo)
        self.root.bind("<KeyPress-c>", self.on_clear)
        self.root.bind("<KeyPress-C>", self.on_clear)

        # watch mode changes
        self.mode.trace_add("write", self._on_mode_change)

        # initial draw
        self._apply_size_increments(self.params.grid_size, tbar)
        self.layers.redraw_all()

    # --------- small app API used by tools ---------
    def prompt_text(self, title: str, prompt: str) -> str | None:
        import tkinter.simpledialog as sd

        return sd.askstring(title, prompt, parent=self.root)

    def layers_redraw(self, *layers: LayerName) -> None:
        if layers:
            for name in layers:
                self.layers.redraw(name)
        else:
            self.layers.redraw_all()

    def snap(self, x: int, y: int) -> tuple[int, int]:
        grid = self.params.grid_size
        if grid <= 0:
            return x, y
        return round(x / grid) * grid, round(y / grid) * grid

    # --------- UI callbacks ---------
    def _on_mode_change(self, *_):
        self.current_tool = self.tools[self.mode.get()]
        self.canvas.config(cursor=self.current_tool.cursor or "")
        self.status.set(self.mode.get().title())

    def on_toggle_grid(self, _evt=None):
        self.toggle_grid()

    def toggle_grid(self):
        self.params.grid_visible = not self.params.grid_visible
        if self.params.grid_visible:
            self.layers.redraw("grid")
            self.canvas.tag_lower(L_GRID)
        else:
            self.layers.clear("grid")
        self.status.set("Grid ON" if self.params.grid_visible else "Grid OFF")

    def on_grid_change(self, *_):
        try:
            self.params.grid_size = max(0, int(self.var_grid.get()))
        except ValueError:
            return
        self.params.grid_visible = self.params.grid_size > 0
        # update size step to match grid
        # (toolbar instance is passed at init to _apply_size_increments)
        self._apply_size_increments(self.params.grid_size)
        self.layers.redraw_all()

    def on_brush_change(self, *_):
        try:
            self.params.brush_width = max(1, int(self.var_brush_w.get()))
        except ValueError:
            return
        self.status.set(f"Line width: {self.params.brush_width}")

    def on_canvas_size_change(self, *_):
        try:
            w = max(self.params.grid_size, int(self.var_width_px.get()))
            h = max(self.params.grid_size, int(self.var_height_px.get()))
        except ValueError:
            return
        self.params.width, self.params.height = w, h
        self.canvas.config(width=w, height=h)
        self.layers.redraw_all()
        self.status.set(f"Canvas {w}×{h}")

    def apply_bg(self, *_):
        col = Cols.get(self.var_bg.get()) or Cols.white
        self.params.bg_mode = col
        display_bg = Cols.sys.dark_gray if col.alpha == 0 else col
        self.canvas.config(bg=display_bg.hex)
        self.layers.redraw("grid")  # grid color may need contrast

    def apply_color(self, *_):
        col = Cols.get(self.var_color.get()) or Cols.black
        self.params.brush_color = col
        self.status.set(f"Brush: {col.name}")

    def on_undo(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.cmd.undo()
        self.layers.redraw_all()
        self.status.set("Undo")

    def on_redo(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.cmd.redo()
        self.layers.redraw_all()
        self.status.set("Redo")

    def on_clear(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.params.lines.clear()
        self.params.labels.clear()
        self.params.icons.clear()
        self.layers.redraw_all()
        self.status.set("Cleared")

    # --------- persistence ---------
    def save_project(self):
        IO.save_params(self.params, self.config_path)
        self.status.set(f"Saved {self.config_path}")

    def load_project(self):
        if self.config_path.exists():
            self.params = IO.load_params(self.config_path)
            # refresh UI vars
            self.var_grid.set(self.params.grid_size)
            self.var_width_px.set(self.params.width)
            self.var_height_px.set(self.params.height)
            self.var_brush_w.set(self.params.brush_width)
            self.var_bg.set(self.params.bg_mode.name)
            self.var_color.set(self.params.brush_color.name)
            self.canvas.config(width=self.params.width, height=self.params.height)
            self.layers.redraw_all()
            self.status.set(f"Loaded {self.config_path}")

    # --------- helpers ---------
    def _nearest_multiple(self, n: int, m: int) -> int:
        return n if m <= 0 else round(n / m) * m

    def _apply_size_increments(self, g: int, tbar=None):
        """Align W/H spinbox steps to grid size and optionally snap current canvas."""
        step = max(1, int(g))
        # when called at init we can receive tbar; later calls can find spins by name
        if tbar:
            tbar.spin_w.configure(increment=step, from_=step)
            tbar.spin_h.configure(increment=step, from_=step)
        # also snap current size to new grid
        if g > 0:
            new_w = max(step, self._nearest_multiple(self.params.width, g))
            new_h = max(step, self._nearest_multiple(self.params.height, g))
            if new_w != self.params.width:
                self.params.width = new_w
                self.var_width_px.set(new_w)
            if new_h != self.params.height:
                self.params.height = new_h
                self.var_height_px.set(new_h)
            self.canvas.config(width=self.params.width, height=self.params.height)

    def drag_to_draw(self) -> bool:
        return bool(self.var_drag_to_draw.get())
