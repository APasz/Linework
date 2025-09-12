from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import sv_ttk

from canvas.layers import Hit_Kind, Layer_Manager, Layer_Name
from canvas.painters import Painters, Scene
from controllers.commands import Command_Stack, Delete_Line, Delete_Label, Delete_Icon
from controllers.editors import Editors
from controllers.tools import Draw_Tool, Icon_Tool, Label_Tool, Select_Tool
from disk.export import Exporter
from disk.storage import IO
from models.assets import Formats, Icon_Name, get_asset_library
from models.geo import CanvasLW, Point
from models.params import Params
from models.styling import Colours, LineStyle
from ui.bars import Bars, Side, Tool_Name


class App:
    def __init__(self, root: tk.Tk, project_path: Path | None = None):
        self.root = root
        self.root.title("Linework")

        self.project_path: Path = project_path or Path("untitled.linework")
        if self.project_path.exists():
            self.params = IO.load_params(self.project_path)

        else:
            self.params = Params()

        self.asset_lib = get_asset_library(self.project_path)

        self.dirty: bool = False
        self._update_title()

        self.editors = Editors(self)

        # ---- theme ----
        try:
            sv_ttk.set_theme("dark")
        except Exception:
            style = ttk.Style()
            print(f"Currently installed themes: {', '.join(style.theme_names())} | Defaulting to Alt")
            style.theme_use("Alt")

        # ---- UI state vars ----
        self.var_drag_to_draw = tk.BooleanVar(value=True)
        self.var_cardinal = tk.BooleanVar(value=True)
        self.var_grid = tk.IntVar(value=self.params.grid_size)
        self.var_width_px = tk.IntVar(value=self.params.width)
        self.var_height_px = tk.IntVar(value=self.params.height)
        self.var_brush_w = tk.IntVar(value=self.params.brush_width)
        self.var_bg = tk.StringVar(value=self.params.bg_mode.name)
        self.var_colour = tk.StringVar(value=self.params.brush_colour.name)
        self.var_colour.trace_add("write", self.apply_colour)
        self.var_line_style = tk.StringVar(value=self.params.line_style)
        self.var_dash_offset = tk.IntVar(value=self.params.line_dash_offset)
        self.selection_kind: Hit_Kind = Hit_Kind.miss  # "line" | "label" | "icon" | ""
        self.selection_index: int | None = None

        self.mode = tk.StringVar(value="draw")
        self.var_icon = tk.StringVar(value=Icon_Name.SIGNAL.value)

        self.var_drag_to_draw.trace_add(
            "write", lambda *_: self.status.temp("Mode: drag to draw" if self.drag_to_draw() else "Mode: click-click")
        )
        self.var_cardinal.trace_add(
            "write", lambda *_: self.status.temp("Mode: Cardinal" if self.cardinal() else "Mode: No Cardinal")
        )

        # ---- header & toolbar ----
        self.hbar = Bars.create_header(
            self.root,
            mode_var=self.mode,
            icon_var=self.var_icon,
            on_toggle_grid=self.toggle_grid,
            on_undo=self.on_undo,
            on_redo=self.on_redo,
            on_clear=self.on_clear,
            on_new=self.new_project,
            on_open=self.open_project,
            on_save=self.save_project,
            on_save_as=self.save_project_as,
            on_export=self.export_image,
        )
        self.tbar = Bars.create_toolbar(
            self.root,
            grid_var=self.var_grid,
            brush_var=self.var_brush_w,
            width_var=self.var_width_px,
            height_var=self.var_height_px,
            bg_var=self.var_bg,
            drag_to_draw_var=self.var_drag_to_draw,
            cardinal_var=self.var_cardinal,
            style_var=self.var_line_style,
            offset_var=self.var_dash_offset,
            on_style_change=self.on_style_change,
            on_grid_change=self.on_grid_change,
            on_brush_change=self.on_brush_change,
            on_canvas_size_change=self.on_canvas_size_change,
            on_palette_select=lambda name: self.var_colour.set(name),
            on_palette_set_bg=lambda name: self.var_bg.set(name),
            selected_colour_name=self.var_colour.get(),
        )

        # ---- canvas ----
        display_bg = Colours.sys.dark_gray.hex if self.params.bg_mode.alpha == 0 else self.params.bg_mode.hex
        self.canvas = CanvasLW(self.root, width=self.params.width, height=self.params.height, bg=display_bg)
        self.canvas.pack(fill="both", expand=False)

        # ---- status bar ----
        self.status = Bars.Status(self.root)
        ttk.Label(self.root, textvariable=self.status.var, anchor="w").pack(fill="x")
        self.status.set("Ready")

        self.apply_colour()

        # keep palette highlight in sync when brush colour changes
        self.var_colour.trace_add("write", lambda *_: self.tbar.palette.set_selected(self.var_colour.get()))
        self.var_bg.trace_add("write", self.apply_bg)

        # ---- scene/layers/painters ----

        self.scene = Scene(self.params)
        self.painters = Painters(self.scene)
        self.layers = Layer_Manager(self.canvas, self.painters)

        # ---- commands & tools ----
        self.cmd = Command_Stack()
        self.tools = {
            Draw_Tool.name: Draw_Tool(),
            Label_Tool.name: Label_Tool(),
            Icon_Tool.name: Icon_Tool(),  # get_icon_name=lambda: self.var_icon.get()
            Select_Tool.name: Select_Tool(),
        }
        self.current_tool = self.tools[Tool_Name(self.mode.get())]
        self.canvas.config(cursor=self.current_tool.cursor.value if self.current_tool.cursor else "")

        tags = list(self.canvas.bindtags())
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
        self.root.bind("<Control-n>", lambda e: self.new_project())
        self.root.bind("<Control-o>", lambda e: self.open_project())
        self.root.bind("<Control-s>", lambda e: self.save_project())
        self.root.bind("<Control-S>", lambda e: self.save_project_as())
        self.root.bind(
            "<KeyPress-Shift_L>",
            lambda e: self.status.hold(
                "shift",
                f"Cardinal {'OFF' if self.cardinal() else 'ON'}",
                priority=100,
                side=Side.right,
            ),
        )
        self.root.bind("<KeyRelease-Shift_L>", lambda e: self.status.release("shift"))
        self.root.bind(
            "<KeyPress-Shift_R>",
            lambda e: self.status.hold(
                "shift",
                f"Cardinal {'OFF' if self.cardinal() else 'ON'}",
                priority=100,
                side=Side.right,
            ),
        )
        self.root.bind("<KeyRelease-Shift_R>", lambda e: self.status.release("shift"))
        self.root.bind("<bracketleft>", lambda e: self._nudge(False))
        self.root.bind("<bracketright>", lambda e: self._nudge(True))
        self.canvas.bind("<Double-1>", lambda e: (self._edit_selected(), "break")[-1])
        self.root.bind("<Return>", lambda e: self._edit_selected())
        self.root.bind("<Delete>", self.on_delete)
        self.root.bind("<BackSpace>", self.on_delete)
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

        # watch mode changes
        self.mode.trace_add("write", self._on_mode_change)

        # initial draw
        self._apply_size_increments(self.params.grid_size, self.tbar)
        self.layers.redraw_all()

    # --------- small app API used by tools ---------
    def prompt_text(self, title: str, prompt: str) -> str | None:
        import tkinter.simpledialog as sd

        return sd.askstring(title, prompt, parent=self.root)

    def layers_redraw(self, *layers: Layer_Name):
        if layers:
            for name in layers:
                self.layers.redraw(name)
        else:
            self.layers.redraw_all()

    def snap(self, point: Point) -> Point:
        g = self.params.grid_size
        W, H = self.params.width, self.params.height
        X, Y = point.x, point.y
        if g > 0:
            sx, sy = round(X / g) * g, round(Y / g) * g
            max_x, max_y = (W // g) * g, (H // g) * g
            sx = 0 if sx < 0 else max_x if sx > max_x else sx
            sy = 0 if sy < 0 else max_y if sy > max_y else sy
            return Point(x=sx, y=sy)
        # no grid: clamp to canvas
        x = 0 if X < 0 else W if X > W else X
        y = 0 if Y < 0 else H if Y > H else Y
        return Point(x=x, y=y)

    # --------- UI callbacks ---------
    def on_delete(self, _evt=None):
        # cancel any live preview/drag first
        self.current_tool.on_cancel(self)

        kind, idx = self._selected()
        if idx is None or not kind or str(kind) == "" or kind.value == "":
            self.status.temp("Nothing selected to delete", 1500)
            return

        if kind == Hit_Kind.line:
            self.cmd.push_and_do(Delete_Line(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.lines)))
            self.status.temp("Deleted line", 1500)

        elif kind == Hit_Kind.label:
            self.cmd.push_and_do(Delete_Label(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.labels)))
            self.status.temp("Deleted label", 1500)

        elif kind == Hit_Kind.icon:
            self.cmd.push_and_do(Delete_Icon(self.params, idx, on_after=lambda: self.layers_redraw(Layer_Name.icons)))
            self.status.temp("Deleted icon", 1500)

        # clear selection and mark dirty
        self._set_selected(Hit_Kind.miss, None)
        self.mark_dirty()

    def on_style_change(self, *_):
        try:
            self.params.line_style = LineStyle(self.var_line_style.get())
        except Exception:
            self.params.line_style = LineStyle.SOLID
        try:
            self.params.line_dash_offset = max(0, int(self.var_dash_offset.get()))
        except ValueError:
            pass
        # If you want existing lines to stay unchanged, don't redraw them here.
        # But the preview needs the new style, so no-op is fine.
        self.status.set(f"Line style: {self.params.line_style.value}")

    def _on_mode_change(self, *_):
        self.current_tool = self.tools[Tool_Name(self.mode.get())]
        self.canvas.config(cursor=self.current_tool.cursor.value if self.current_tool.cursor else "")
        self.status.temp(self.mode.get().title())
        self.status.clear_suffix()

    def on_toggle_grid(self, _evt=None):
        self.toggle_grid()

    def toggle_grid(self):
        self.params.grid_visible = not self.params.grid_visible
        if self.params.grid_visible:
            self.layers.redraw(Layer_Name.grid)
            self.canvas.tag_lower_l(Layer_Name.grid)
        else:
            self.layers.clear(Layer_Name.grid, force=True)
        self.status.temp("Grid ON" if self.params.grid_visible else "Grid OFF")
        self.mark_dirty()

    def on_grid_change(self, *_):
        try:
            self.params.grid_size = max(0, int(self.var_grid.get()))
        except ValueError:
            return
        self.params.grid_visible = self.params.grid_size > 0
        # update size step to match grid
        # (toolbar instance is passed at init to _apply_size_increments)
        self._apply_size_increments(self.params.grid_size, self.tbar)
        self.layers.redraw(Layer_Name.grid, True)

    def on_brush_change(self, *_):
        try:
            self.params.brush_width = max(1, int(self.var_brush_w.get()))
        except ValueError:
            return
        self.status.temp(f"Line width: {self.params.brush_width}")
        self.mark_dirty()

    def on_canvas_size_change(self, *_):
        try:
            w = max(self.params.grid_size, int(self.var_width_px.get()))
            h = max(self.params.grid_size, int(self.var_height_px.get()))
        except ValueError:
            return
        self.params.width, self.params.height = w, h
        self.canvas.config(width=w, height=h)
        self.layers.redraw_all()
        self.status.temp(f"Canvas {w}×{h}")
        self.mark_dirty()

    def apply_bg(self, *_):
        raw = (self.var_bg.get().strip() if self.var_bg else "") or "white"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.white
        self.params.bg_mode = col
        display_bg = Colours.sys.dark_gray if col.alpha == 0 else col
        self.canvas.config(bg=display_bg.hex)
        self.layers.redraw(Layer_Name.grid)

    def apply_colour(self, *_):
        raw = (self.var_colour.get().strip() if self.var_colour else "") or "black"
        try:
            col = Colours.parse_colour(raw)
        except ValueError:
            col = Colours.black
        self.params.brush_colour = col
        self.status.temp(f"Brush: {Colours.name_for(col) or col.hexa}")

    def on_undo(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.cmd.undo()
        self.layers.redraw_all()
        self.mark_dirty()
        self.status.temp("Undo")

    def on_redo(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.cmd.redo()
        self.layers.redraw_all()
        self.mark_dirty()
        self.status.temp("Redo")

    def on_clear(self, _evt=None):
        self.current_tool.on_cancel(self)
        self.params.lines.clear()
        self.params.labels.clear()
        self.params.icons.clear()
        self.layers.redraw_all()
        self.mark_dirty()
        self.status.temp("Cleared")

    # --------- persistence ---------
    def export_image(self):
        # default file name & type based on params
        initialfile = self.params.output_file.name

        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Export",
            defaultextension=self.params.output_file.suffix,
            filetypes=[(t.upper(), f"*.{t.lower()}") for t in Formats],  # e.g. WEBP/PNG/SVG
            initialdir=self.params.output_file.parent,
            initialfile=initialfile,
        )
        if not path:
            return

        out = Path(path)
        ext = out.suffix.lower().lstrip(".")
        if ext not in Formats:
            messagebox.showerror("Invalid filetype", f"Choose one of: {', '.join(Formats)}")
            return

        # update params & export
        self.params.output_file = out
        try:
            Exporter.output(self.params)
        except Exception as e:
            messagebox.showerror("Export failed", str(e))
            return

        # persist export settings back to the current project
        try:
            IO.save_params(self.params, self.project_path)
        except Exception:
            pass

        self.status.set(f"Exported: {out}")

    # --------- helpers ---------
    def _nudge(self, cw: bool):
        k, i = self._selected()
        if i is None:
            return
        if cw:
            delta_deg = 15
            step = 1
        else:
            delta_deg = -15
            step = -1
        if k == Hit_Kind.icon:
            self.params.icons[i].rotation = round((self.params.icons[i].rotation + delta_deg) % 360)
            self.layers.redraw(Layer_Name.icons)
            self.mark_dirty()
        elif k == Hit_Kind.label:
            self.params.labels[i].rotation = round((self.params.labels[i].rotation + delta_deg) % 360)
            self.layers.redraw(Layer_Name.labels)
            self.mark_dirty()
        elif k == Hit_Kind.line:
            lin = self.params.lines[i]
            order = [
                LineStyle.SOLID,
                LineStyle.SHORT,
                LineStyle.DASH,
                LineStyle.DASH_DOT,
                LineStyle.DASH_DOT_DOT,
                LineStyle.LONG,
                LineStyle.DOT,
            ]
            try:
                j = order.index(lin.style)
            except ValueError:
                j = 0
            lin.style = order[(j + step) % len(order)]
            self.layers.redraw(Layer_Name.lines)
            self.mark_dirty()

    def _selected(self) -> tuple[Hit_Kind, int | None]:
        return self.selection_kind, self.selection_index

    def _set_selected(self, kind: Hit_Kind, idx: int | None):
        self.selection_kind, self.selection_index = kind, idx

    def _edit_selected(self):
        k, i = self._selected()
        if k is None or i is None:
            return

        if k == Hit_Kind.label:
            obj = self.params.labels[i]
            layer = Layer_Name.labels
        elif k == Hit_Kind.icon:
            obj = self.params.icons[i]
            layer = Layer_Name.icons
        elif k == Hit_Kind.line:
            obj = self.params.lines[i]
            layer = Layer_Name.lines
        else:
            return

        if self.editors.edit(self.root, obj):
            self.layers.redraw(layer)
            self.mark_dirty()

    def _nearest_multiple(self, n: int, m: int) -> int:
        return n if m <= 0 else round(n / m) * m

    def _apply_size_increments(self, g: int, tbar=None):
        """Align W/H spinbox steps to grid size and optionally snap current canvas."""
        step = max(1, g)
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

    def _update_title(self):
        name = self.project_path.name if self.project_path else "Untitled"
        star = " *" if self.dirty else ""
        self.root.title(f"Linework — {name}{star}")

    def mark_dirty(self, _reason: str = ""):
        self.dirty = True
        self._update_title()

    def mark_clean(self):
        self.dirty = False
        self._update_title()

    def _maybe_save_changes(self) -> bool:
        """Return True if it's OK to proceed (saved or discarded), False if user cancelled."""
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Save changes?", "Save your changes before continuing?")
        if ans is None:
            return False  # Cancel
        if ans is True:
            return self.save_project()  # True if saved, False if user cancelled dialog
        # No -> discard
        return True

    def _on_close(self):
        if self._maybe_save_changes():
            self.root.destroy()

    # --------- project ---------
    def save_project(self) -> bool:
        """Save to current path; if it's an 'untitled', redirect to Save As. Returns success."""
        if not self.project_path or self.project_path.name.startswith("untitled"):
            return self.save_project_as()
        try:
            IO.save_params(self.params, self.project_path)
        except Exception as e:
            messagebox.showerror("Save failed", str(e))
            return False
        self.mark_clean()
        self.status.set(f"Saved {self.project_path}")
        return True

    def save_project_as(self) -> bool:
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="Save As",
            defaultextension=".linework",
            filetypes=[("Linework Projects", "*.linework"), ("JSON", "*.json")],
            initialdir=self.project_path.parent if self.project_path else None,
            initialfile=(self.project_path.name if self.project_path else "untitled.linework"),
        )
        if not path:
            return False
        self.project_path = Path(path)
        return self.save_project()

    def open_project(self):
        if not self._maybe_save_changes():
            return
        path = filedialog.askopenfilename(
            parent=self.root,
            title="Open Project",
            filetypes=[("Linework Projects", "*.linework"), ("JSON", "*.json"), ("All Files", "*.*")],
            initialdir=self.project_path.parent if self.project_path else None,
        )
        if not path:
            return
        try:
            self.params = IO.load_params(Path(path))
        except Exception as e:
            messagebox.showerror("Open failed", str(e))
            return

        self._sync_ui_from_params(Path(path))
        self._update_title()
        self.status.set(f"Opened {self.project_path}")

    def new_project(self):
        if not self._maybe_save_changes():
            return
        self.params = Params()
        self._sync_ui_from_params()
        self.status.set("New project")

    def _sync_ui_from_params(self, path: Path = Path("untitled.linework")):
        self.project_path = path
        self.asset_lib = get_asset_library(path)
        self.scene.params = self.params
        # refresh UI vars
        self.var_grid.set(self.params.grid_size)
        self.var_width_px.set(self.params.width)
        self.var_height_px.set(self.params.height)
        self.var_brush_w.set(self.params.brush_width)
        self.var_bg.set(self.params.bg_mode.name_str)
        self.var_colour.set(self.params.brush_colour.name_str)
        self.var_line_style.set(self.params.line_style)
        self.var_dash_offset.set(self.params.line_dash_offset)
        self.canvas.config(width=self.params.width, height=self.params.height)
        self._apply_size_increments(self.params.grid_size, self.tbar)
        self.layers.redraw_all()
        self.mark_clean()

    def drag_to_draw(self) -> bool:
        return bool(self.var_drag_to_draw.get())

    def cardinal(self) -> bool:
        return bool(self.var_cardinal.get())
