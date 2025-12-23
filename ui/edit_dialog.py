from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk
from collections.abc import Callable, Iterable, Mapping, Sequence
from enum import Enum, StrEnum
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageTk

from disk.export import _emit_pil_plan
from models.assets import Icon_Name, SVG_SUPPORTED, _builtin_icon_plan, _open_rgba
from models.geo import Icon_Source, Icon_Type, Point
from models.styling import Colours
from ui.bars import Colour_Palette

if TYPE_CHECKING:
    from controllers.app import App

ICON_PICKER_COLUMNS = 6


class Icon_Gallery(tk.Toplevel):
    def __init__(
        self,
        master,
        app: App,
        recent: Iterable[Icon_Source],
        at: Point,
        show_builtins: bool = True,
        show_pictures: bool = True,
        show_recent: bool = True,
    ):
        super().__init__(master)
        self.withdraw()
        self._thumb_size = 40
        self.project_path = app.project_path
        self.app = app
        self.title("Choose icon")
        self.transient(master)
        self.resizable(False, False)
        self.result: Icon_Source | None = None
        self._thumb_cache: dict[tuple, ImageTk.PhotoImage] = {}

        self._grids: list[_ScrollGrid] = []
        self._cols: int | None = ICON_PICKER_COLUMNS
        nb = ttk.Notebook(self)

        if show_builtins:
            self._tab_builtin = ttk.Frame(nb)
            nb.add(self._tab_builtin, text="Built-ins")
        else:
            self._tab_builtin = None
        if show_pictures:
            self._tab_pictures = ttk.Frame(nb)
            nb.add(self._tab_pictures, text="Pictures")
        else:
            self._tab_pictures = None
        if show_recent:
            self._tab_recent = ttk.Frame(nb)
            nb.add(self._tab_recent, text="Recent")
        else:
            self._tab_recent = None
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        if self._tab_builtin:
            self._build_builtins(self._tab_builtin)
        if self._tab_pictures:
            self._build_pictures(self._tab_pictures)
        if self._tab_recent:
            self._build_recent(self._tab_recent, list(recent))

        btns = ttk.Frame(self)
        if self._tab_pictures:
            self._btn_import = ttk.Button(btns, text="Import…", command=self._import_images)
            self._btn_import.pack(side="left", padx=6, pady=6)

        def _bump_cols(d: int):
            n = ICON_PICKER_COLUMNS if self._cols is None else self._cols
            self._cols = max(1, n + d)
            for g in self._grids:
                g.set_columns(self._cols)
            self._resize_to_req()

        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right", padx=(0, 4))
        ttk.Button(btns, text="−", width=3, command=lambda: _bump_cols(-1)).pack(side="left", padx=(2, 4))
        ttk.Button(btns, text="+", width=3, command=lambda: _bump_cols(+1)).pack(side="left", padx=(2, 8))
        btns.pack(fill="x", padx=8, pady=(0, 8))

        self.bind("<Escape>", lambda e: self._cancel())
        self.update_idletasks()
        if at:
            self.geometry(f"+{at.x}+{at.y}")
        else:
            self.center()
        # now show without flicker
        self.deiconify()
        self.grab_set()

    def _resize_to_req(self):
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"{w}x{h}")

    def center(self):
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        self.geometry(f"+{(sw - w) // 2}+{(sh - h) // 2}")

    def _choose(self, src: Icon_Source):
        self.result = src
        self.destroy()

    # ---------- built-ins ----------
    def _build_builtins(self, parent):
        frame = _ScrollGrid(parent, columns=self._cols)
        for name in Icon_Name:
            thumb = self._thumb_for_builtin(name)
            b = ttk.Button(
                frame.body,
                image=thumb,
                text=name.value.replace("_", " ").title(),
                compound="top",
                command=lambda n=name: self._choose(Icon_Source.builtin(n)),
            )
            frame.add(b)
        frame.pack(fill="both", expand=True)
        frame.force_layout()
        self._grids.append(frame)

    def _thumb_for_builtin(self, name: Icon_Name) -> ImageTk.PhotoImage:
        key = (Icon_Type.builtin, name.name)
        if key in self._thumb_cache:
            return self._thumb_cache[key]

        plan = _builtin_icon_plan(name, self._thumb_size - 8, Colours.white.hexh)

        img = Image.new("RGBA", (self._thumb_size, self._thumb_size), (0, 0, 0, 0))

        _emit_pil_plan(img, plan, self._thumb_size // 2, self._thumb_size // 2, 0)

        ph = ImageTk.PhotoImage(img)
        self._thumb_cache[key] = ph
        return ph

    # ---------- pictures ----------
    def _build_pictures(self, parent):
        self._pics_frame = _ScrollGrid(parent, columns=self._cols)
        self._pics_frame.pack(fill="both", expand=True)
        self._refresh_pictures()
        self._pics_frame.force_layout()
        self._grids.append(self._pics_frame)

    def _refresh_pictures(self):
        self._pics_frame.clear()
        for p in self.app.asset_lib.list_pictures():
            thumb = self._thumb_for_picture(p)
            btn = ttk.Button(
                self._pics_frame.body,
                image=thumb,
                text=p.name,
                compound="top",
                command=lambda path=p: self._choose(Icon_Source.picture(path)),
            )
            # btn.image = thumb
            self._pics_frame.add(btn)
        self._pics_frame.body.update_idletasks()

    def _thumb_for_picture(self, path: Path) -> ImageTk.PhotoImage:
        key = ("pic", str(path))
        if key in self._thumb_cache:
            return self._thumb_cache[key]
        im = _open_rgba(path, self._thumb_size, self._thumb_size)
        ph = ImageTk.PhotoImage(im)
        self._thumb_cache[key] = ph
        return ph

    # ---------- recent ----------
    def _build_recent(self, parent, recent: list[Icon_Source]):
        allowed = set()
        if self._tab_builtin is not None:
            allowed.add(Icon_Type.builtin)
        if self._tab_pictures is not None:
            allowed.add(Icon_Type.picture)

        frame = _ScrollGrid(parent, columns=self._cols)
        for src in recent:
            if src.kind not in allowed:
                continue
            if src.kind == Icon_Type.builtin and src.name:
                thumb = self._thumb_for_builtin(src.name)
                txt = src.name.name
            elif src.kind == Icon_Type.picture and src.src:
                thumb = self._thumb_for_picture(src.src)
                txt = src.src.name
            else:
                continue
            b = ttk.Button(frame.body, image=thumb, text=txt, compound="top", command=lambda s=src: self._choose(s))
            frame.add(b)
        frame.pack(fill="both", expand=True)
        frame.force_layout()
        self._grids.append(frame)

    def _import_images(self):
        try:
            exts = ["*.png", "*.jpg", "*.jpeg", "*.webp", "*.bmp"]
            if SVG_SUPPORTED:
                exts.insert(0, "*.svg")
            paths = filedialog.askopenfilenames(
                title="Import icons",
                filetypes=[
                    ("Image files", " ".join(exts)),
                    ("All files", "*.*"),
                ],
            )
        except tk.TclError as exc:
            if "application has been destroyed" in str(exc):
                return
            raise
        if not paths:
            return
        if not SVG_SUPPORTED:
            svg_paths = [p for p in paths if Path(p).suffix.lower() == ".svg"]
            if svg_paths:
                messagebox.showwarning(
                    "SVG import unavailable",
                    "SVG import requires cairosvg; install it to enable SVG icons.",
                )
            paths = [p for p in paths if Path(p).suffix.lower() != ".svg"]
        if not paths:
            return
        self.app.asset_lib.import_files([Path(p) for p in paths])
        self._refresh_pictures()

    def _cancel(self):
        self.result = None
        self.destroy()


class _ScrollGrid(ttk.Frame):
    def __init__(self, master, columns: int | None = ICON_PICKER_COLUMNS, cell_pad: int = 8):
        super().__init__(master)
        canvas = tk.Canvas(self, width=480, height=320, highlightthickness=0)
        vs = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)

        self._win = canvas.create_window((0, 0), window=self.body, anchor="nw")
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", self._on_canvas_resize)

        self.canvas = canvas
        self.columns = columns
        self.pad = cell_pad
        self.widgets: list[tk.Widget] = []
        self._cell_w = 0
        self._cell_h = 0
        self._vs = vs
        self._layout_pending = False

        def _on_wheel(ev):
            try:
                x, y = ev.x_root, ev.y_root
                rx, ry = canvas.winfo_rootx(), canvas.winfo_rooty()
                if not (rx <= x < rx + canvas.winfo_width() and ry <= y < ry + canvas.winfo_height()):
                    return
            except Exception:
                return
            d = getattr(ev, "delta", 0)
            step = (-1 if d > 0 else 1) if d else (-1 if getattr(ev, "num", 0) == 4 else 1)
            canvas.yview_scroll(step, "units")
            return "break"

        for w in (canvas, self.body):
            w.bind("<MouseWheel>", _on_wheel)
            w.bind("<Button-4>", _on_wheel)  # X11
            w.bind("<Button-5>", _on_wheel)  # X11

        canvas.configure(yscrollcommand=vs.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)

    # ---- layout helpers ----
    def _measure(self):
        self.body.update_idletasks()
        if not self.widgets:
            self._cell_w = self._cell_h = 80
            return
        maxw = max(w.winfo_reqwidth() for w in self.widgets)
        maxh = max(w.winfo_reqheight() for w in self.widgets)
        self._cell_w = maxw + self.pad * 2
        self._cell_h = maxh + self.pad * 2

    def _compute_cols(self):
        if self.columns and self.columns > 0:
            return self.columns
        avail = max(1, self.canvas.winfo_width())
        return max(1, avail // max(1, self._cell_w))

    def _relayout(self):
        self._layout_pending = False
        self._measure()
        cols = self._compute_cols()
        n = len(self.widgets)
        rows = max(1, (n + cols - 1) // cols)

        for c in range(cols):
            self.body.grid_columnconfigure(c, minsize=self._cell_w, uniform="tiles")
        for r in range(rows):
            self.body.grid_rowconfigure(r, minsize=self._cell_h, uniform="tiles")

        for i, w in enumerate(self.widgets):
            r, c = divmod(i, cols)
            w.grid_configure(row=r, column=c, padx=self.pad, pady=self.pad, sticky="")

        if self.columns and self.columns > 0 and self._cell_w > 0:
            sbw = self._vs.winfo_reqwidth() or 12
            want = cols * self._cell_w + sbw
            self.canvas.configure(width=want)

        self.body.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_resize(self, e):
        self.canvas.itemconfigure(self._win, width=e.width)
        if not self._layout_pending:
            self._layout_pending = True
            self.after_idle(self._relayout)

    # ---- public API ----
    def add(self, widget):
        widget.grid(row=0, column=0)

        def _forward_wheel(ev, c=self.canvas):
            if hasattr(ev, "delta") and ev.delta:
                c.event_generate("<MouseWheel>", delta=ev.delta)
            else:
                num = getattr(ev, "num", 0)
                if num in (4, 5):
                    c.event_generate(f"<Button-{num}>")
            return "break"

        widget.bind("<MouseWheel>", _forward_wheel)
        widget.bind("<Button-4>", _forward_wheel)  # X11
        widget.bind("<Button-5>", _forward_wheel)  # X11
        self.widgets.append(widget)
        if not self._layout_pending:
            self._layout_pending = True
            self.after_idle(self._relayout)

    def clear(self):
        for c in list(self.body.children.values()):
            c.destroy()
        self.widgets.clear()
        if not self._layout_pending:
            self._layout_pending = True
            self.after_idle(self._relayout)

    def set_columns(self, num: int | None):
        self.columns = num
        if not self._layout_pending:
            self._layout_pending = True
            self.after_idle(self._relayout)

    def force_layout(self):
        self._relayout()


class EKind(StrEnum):
    STR = "str"
    INT = "int"
    FLOAT = "float"
    BOOL = "bool"
    TEXT = "text"
    CHOICE = "choice"
    CHOICE_DICT = "choice_dict"
    COLOUR = "colour"
    ICON_BUILTIN = "icon_builtin"
    ICON_PICTURE = "icon_picture"


@dataclass(frozen=True)
class _FieldSpec:
    name: str
    label: str | None = None
    kind: EKind = EKind.STR
    min: int | float | None = None
    max: int | float | None = None
    choices: Sequence[str] | Callable[[], Sequence[str]] | None = None
    choices_dict: Mapping[str, Any] | Callable[[], Mapping[str, Any]] | None = None


def _coerce_schema_item(item: Any) -> dict[str, Any]:
    """
    Normalizes either a legacy dict schema entry or a typed _FieldSpec
    into the dict shape the dialog uses internally.
    """
    if isinstance(item, _FieldSpec):
        d: dict[str, Any] = {
            "name": item.name,
            "label": item.label or item.name,
            "kind": item.kind.value,
        }
        if item.min is not None:
            d["min"] = item.min
        if item.max is not None:
            d["max"] = item.max
        if item.kind is EKind.CHOICE and item.choices:
            d["choices"] = item.choices() if callable(item.choices) else list(item.choices)
        if item.kind is EKind.CHOICE_DICT and item.choices_dict:
            d["choices"] = item.choices_dict() if callable(item.choices_dict) else dict(item.choices_dict)
        return d

    if not isinstance(item, dict):
        raise TypeError(f"Schema entries must be dict or _FieldSpec, got {type(item)}")
    d = dict(item)
    k = d.get("kind", "str")
    if isinstance(k, EKind):
        d["kind"] = k.value
    else:
        d["kind"] = str(k).lower()
    d.setdefault("label", d.get("label", d.get("name")))
    return d


def _resolve_choices_seq(val: Any) -> list[str]:
    if val is None:
        return []
    if callable(val):
        val = val()
    if isinstance(val, (list, tuple)):
        return [str(x) for x in val]
    raise TypeError("choices must be Sequence[str] or a callable returning Sequence[str]")


def _resolve_choices_map(val: Any) -> dict[str, Any]:
    if val is None:
        return {}
    if callable(val):
        val = val()
    if isinstance(val, Mapping):
        return dict(val)
    raise TypeError("choices must be Mapping[str, Any] or a callable returning Mapping[str, Any]")


class GenericEditDialog(simpledialog.Dialog):
    """
    Compatible with the old dict-based schema, but internally uses a
    clean dispatch table instead of if/else forests. Also accepts typed _FieldSpec.
    """

    def __init__(
        self,
        app: App,
        title: str,
        schema: Sequence[dict[str, Any] | _FieldSpec],
        values: dict[str, Any] | None,
    ):
        self.app: App = app
        self.schema: list[dict[str, Any]] = [_coerce_schema_item(s) for s in list(schema)]
        self.values: dict[str, Any] = dict(values or {})
        self.widgets: dict[str, tk.Widget] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        super().__init__(app.root, title)

    # ---- Dialog hooks ----
    def body(self, master: tk.Frame) -> tk.Widget:
        master.grid_columnconfigure(1, weight=1)

        for r, fld in enumerate(self.schema):
            label = fld.get("label", fld["name"])
            ttk.Label(master, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
            w = self._build_widget(master, fld, self.values.get(fld["name"]))
            w.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
        return next(iter(self.widgets.values()), master)

    def buttonbox(self):
        box = ttk.Frame(self)
        ok = ttk.Button(box, text="OK", command=self.ok)
        cancel = ttk.Button(box, text="Cancel", command=self.cancel)
        ok.pack(side="left", padx=5, pady=5)
        cancel.pack(side="left", padx=5, pady=5)
        box.pack(fill="x")
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())

    def validate(self) -> bool:
        out: dict[str, Any] = {}
        try:
            for fld in self.schema:
                name = fld["name"]
                kind = str(fld.get("kind", "str")).lower()
                raw = self._read_value(name, kind, fld)
                # central numeric validation
                if kind in ("int", "float"):
                    if "min" in fld and raw < fld["min"]:
                        raise ValueError(f"{fld.get('label', name)} must be ≥ {fld['min']}")
                    if "max" in fld and raw > fld["max"]:
                        raise ValueError(f"{fld.get('label', name)} must be ≤ {fld['max']}")
                out[name] = raw
        except Exception as e:
            try:
                messagebox.showerror("Invalid input", str(e), parent=self)
            except tk.TclError as exc:
                if "application has been destroyed" not in str(exc):
                    raise
            return False
        self._result = out
        return True

    def apply(self):
        self.result = getattr(self, "_result", None)

    # ---- builders (per kind) ----
    def _build_widget(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        kind = str(fld.get("kind", "str")).lower()
        name = fld["name"]
        self._meta[name] = {}

        BUILDERS: dict[str, Callable[[tk.Widget, dict, Any], tk.Widget]] = {
            "bool": self._build_bool,
            "int": self._build_entry,
            "float": self._build_entry,
            "str": self._build_entry,
            "text": self._build_text,
            "choice": self._build_choice,
            "choice_dict": self._build_choice_dict,
            "colour": self._build_colour,
            "icon_builtin": self._build_icon_builtin,
            "icon_picture": self._build_icon_picture,
        }
        builder = BUILDERS.get(kind, self._build_entry)
        w = builder(parent, fld, init_val)
        self.widgets[name] = w
        return w

    def _build_bool(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        var = tk.BooleanVar(value=bool(init_val))
        self._meta[fld["name"]]["var"] = var
        return ttk.Checkbutton(parent, variable=var)

    def _build_entry(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        var = tk.StringVar(value=self._stringify_init(init_val))
        self._meta[fld["name"]]["var"] = var
        return ttk.Entry(parent, textvariable=var)

    def _build_text(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        txt = tk.Text(parent, height=4, width=40)
        if init_val:
            txt.insert("1.0", str(init_val))
        return txt

    def _build_choice(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        keys = _resolve_choices_seq(fld.get("choices"))
        if fld.get("sort", True):
            keys = sorted(keys, key=str.casefold)
        init_key = str(init_val) if init_val is not None else (keys[0] if keys else "")
        var = tk.StringVar(value=init_key)
        self._meta[fld["name"]]["var"] = var
        return ttk.Combobox(parent, values=keys, textvariable=var, state="readonly")

    def _build_choice_dict(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        mapping = _resolve_choices_map(fld.get("choices"))
        keys = list(mapping.keys())
        if fld.get("sort", True):
            keys = sorted(keys, key=str.casefold)
        init_key = keys[0] if keys else ""
        for k, v in mapping.items():
            if v == init_val or (isinstance(v, Path) and str(v) == str(init_val)):
                init_key = k
                break
        var = tk.StringVar(value=init_key)
        meta = self._meta[fld["name"]]
        meta["var"] = var
        meta["map"] = mapping
        return ttk.Combobox(parent, values=keys, textvariable=var, state="readonly")

    def _build_colour(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        init = str(init_val) if init_val is not None else ""
        var = tk.StringVar(value=init)
        self._meta[fld["name"]]["var"] = var
        pal = Colour_Palette(
            parent,
            Colours.list(min_alpha=25),
            custom=self.app.params.custom_palette,
            on_select=lambda hexa: var.set(hexa),
        )
        try:
            pal._update_highlight(var.get())
        except Exception:
            pass
        return pal

    # --- icon pickers ---
    def _build_icon_builtin(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        frm = ttk.Frame(parent)
        var = tk.StringVar(value=self._stringify_init(init_val))
        self._meta[fld["name"]]["var"] = var
        shown = tk.StringVar(value=var.get())
        ttk.Label(frm, textvariable=shown).pack(side="left", padx=(0, 6))

        def _choose():
            dlg = Icon_Gallery(
                self,
                self.app,
                getattr(getattr(self.app, "params", None), "recent_icons", []),
                Point(x=parent.winfo_rootx(), y=parent.winfo_rooty()),
                show_builtins=True,
                show_pictures=False,
                show_recent=True,
            )
            self.wait_window(dlg)
            src = getattr(dlg, "result", None)
            if src and getattr(src, "name", None):
                var.set(getattr(src.name, "value", ""))
                shown.set(var.get())

        ttk.Button(frm, text="Choose…", command=_choose).pack(side="right")
        return frm

    def _build_icon_picture(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        frm = ttk.Frame(parent)
        init = self._stringify_init(init_val)
        var = tk.StringVar(value=init)
        self._meta[fld["name"]]["var"] = var
        shown = tk.StringVar(value=Path(init).name if init else "")
        ttk.Label(frm, textvariable=shown).pack(side="left", padx=(0, 6))

        def _choose():
            dlg = Icon_Gallery(
                self,
                self.app,
                getattr(getattr(self.app, "params", None), "recent_icons", []),
                Point(x=parent.winfo_rootx(), y=parent.winfo_rooty()),
                show_builtins=False,
                show_pictures=True,
                show_recent=True,
            )
            self.wait_window(dlg)
            src = getattr(dlg, "result", None)
            p = getattr(src, "src", None)
            if p:
                var.set(str(p))
                shown.set(Path(p).name)

        ttk.Button(frm, text="Choose…", command=_choose).pack(side="right")
        return frm

    # ---- readers (per kind) ----
    def _read_value(self, name: str, kind: str, fld: dict) -> Any:
        READERS: dict[str, Callable[[str, dict], Any]] = {
            "bool": self._read_bool,
            "text": self._read_text,
            "choice": self._read_choice,
            "choice_dict": self._read_choice_dict,
            "int": self._read_int,
            "float": self._read_float,
            "str": self._read_str,
            "colour": self._read_str,
        }
        reader = READERS.get(kind, self._read_str)
        return reader(name, fld)

    def _read_bool(self, name: str, fld: dict) -> bool:
        return bool(self._meta[name]["var"].get())

    def _read_text(self, name: str, fld: dict) -> str:
        w = self.widgets[name]
        return w.get("1.0", "end-1c")  # pyright: ignore

    def _read_choice(self, name: str, fld: dict) -> str:
        return str(self._meta[name]["var"].get()).strip()

    def _read_choice_dict(self, name: str, fld: dict) -> Any:
        key = str(self._meta[name]["var"].get())
        mapping: dict[str, Any] = self._meta[name].get("map", {})
        if key not in mapping:
            raise ValueError(f"{fld.get('label', name)}: unknown option '{key}'")
        return mapping[key]

    def _read_str(self, name: str, fld: dict) -> str:
        return str(self._meta[name]["var"].get()).strip()

    def _read_int(self, name: str, fld: dict) -> int:
        s = self._read_str(name, fld)
        try:
            return int(float(s))
        except Exception:
            raise ValueError(f"{fld.get('label', name)} must be an integer")

    def _read_float(self, name: str, fld: dict) -> float:
        s = self._read_str(name, fld)
        try:
            return float(s)
        except Exception:
            raise ValueError(f"{fld.get('label', name)} must be a number")

    # ---- helpers ----
    @staticmethod
    def _stringify_init(v: Any) -> str:
        if isinstance(v, Enum):
            return str(getattr(v, "value", str(v)))
        if isinstance(v, Path):
            return v.name
        return "" if v is None else str(v)

    def _close_popdowns(self):
        for w in self.widgets.values():
            if isinstance(w, ttk.Combobox):
                try:
                    w.event_generate("<Escape>")
                except Exception:
                    pass
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _hide_combobox_popdowns(self):
        for w in self.widgets.values():
            if isinstance(w, ttk.Combobox):
                try:
                    pop = w.tk.call("ttk::combobox::PopdownWindow", str(w))
                    if pop:
                        w.tk.call("place", "forget", pop)
                except tk.TclError:
                    pass
        try:
            self.update_idletasks()
        except tk.TclError:
            pass

    def destroy(self):
        self._hide_combobox_popdowns()
        super().destroy()
