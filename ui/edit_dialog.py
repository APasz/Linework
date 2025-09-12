from __future__ import annotations

import tkinter as tk
from collections.abc import Iterable
from enum import Enum, StrEnum
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import TYPE_CHECKING, Any

from PIL import Image, ImageDraw, ImageTk

from disk.export import _emit_pil_plan
from models.assets import _builtin_icon_plan, _open_rgba
from models.geo import Icon_Name, Icon_Source, Icon_Type
from models.styling import Colours

if TYPE_CHECKING:
    from controllers.app import App

THUMB = 40


class Icon_Gallery(tk.Toplevel):
    def __init__(self, master, app: App, recent: Iterable[Icon_Source], at: tuple[int, int] | None = None):
        super().__init__(master)
        self.project_path = app.project_path
        self.app = app
        self.title("Choose icon")
        self.transient(master)
        self.resizable(False, False)
        self.result: Icon_Source | None = None
        self._thumb_cache: dict[tuple, ImageTk.PhotoImage] = {}

        nb = ttk.Notebook(self)
        self.tab_builtins = ttk.Frame(nb)
        self.tab_pictures = ttk.Frame(nb)
        self.tab_recent = ttk.Frame(nb)
        nb.add(self.tab_builtins, text="Built-ins")
        nb.add(self.tab_pictures, text="Pictures")
        nb.add(self.tab_recent, text="Recent")
        nb.pack(fill="both", expand=True, padx=8, pady=8)

        self._build_builtins(self.tab_builtins)
        self._build_pictures(self.tab_pictures)
        self._build_recent(self.tab_recent, list(recent))

        btns = ttk.Frame(self)
        ttk.Button(btns, text="Import…", command=self._import_images).pack(side="left", padx=4)
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="right", padx=4)
        btns.pack(fill="x", padx=8, pady=(0, 8))

        self.bind("<Escape>", lambda e: self._cancel())
        self.update_idletasks()
        if at:
            self.geometry(f"+{at[0]}+{at[1]}")
        else:
            self.center()

        self.grab_set()

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
        frame = _ScrollGrid(parent)
        for name in Icon_Name:
            thumb = self._thumb_for_builtin(name)
            b = ttk.Button(
                frame.body,
                image=thumb,
                text=name.name,
                compound="top",
                command=lambda n=name: self._choose(Icon_Source.builtin(n)),
            )
            frame.add(b)
        frame.pack(fill="both", expand=True)

    def _thumb_for_builtin(self, name: Icon_Name) -> ImageTk.PhotoImage:
        key = (Icon_Type.builtin, name.name)
        if key in self._thumb_cache:
            return self._thumb_cache[key]

        plan = _builtin_icon_plan(name, THUMB - 8, Colours.white.hex)

        img = Image.new("RGBA", (THUMB, THUMB), (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)

        # render centered in the thumbnail, no rotation
        _emit_pil_plan(draw, plan, THUMB // 2, THUMB // 2, 0)

        ph = ImageTk.PhotoImage(img)
        self._thumb_cache[key] = ph
        return ph

    # ---------- pictures ----------
    def _build_pictures(self, parent):
        self._pics_frame = _ScrollGrid(parent)
        self._pics_frame.pack(fill="both", expand=True)
        self._refresh_pictures()

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
        im = _open_rgba(path, THUMB, THUMB)
        ph = ImageTk.PhotoImage(im)
        self._thumb_cache[key] = ph
        return ph

    # ---------- recent ----------
    def _build_recent(self, parent, recent: list[Icon_Source]):
        frame = _ScrollGrid(parent)
        for src in recent:  # pyright: ignore[reportAssignmentType]
            if src.kind == Icon_Type.builtin and src.name:
                thumb = self._thumb_for_builtin(src.name)
                txt = src.name.name
            elif src.kind == Icon_Type.picture and src.src:
                thumb = self._thumb_for_picture(src.src)
                txt = src.src.name
            else:
                raise ValueError(f"Unknown kind: {src.kind}")
            b = ttk.Button(frame.body, image=thumb, text=txt, compound="top", command=lambda s=src: self._choose(s))
            frame.add(b)
        frame.pack(fill="both", expand=True)

    def _import_images(self):
        paths = filedialog.askopenfilenames(
            title="Import icons",
            filetypes=[
                ("Image files", "*.svg *.png *.jpg *.jpeg *.webp *.bmp"),
                ("All files", "*.*"),
            ],
        )
        if not paths:
            return
        self.app.asset_lib.import_files([Path(p) for p in paths])
        self._refresh_pictures()

    def _cancel(self):
        self.result = None
        self.destroy()


class _ScrollGrid(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        canvas = tk.Canvas(self, width=480, height=320, highlightthickness=0)
        vs = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.body = ttk.Frame(canvas)
        self.body.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=self.body, anchor="nw")
        canvas.configure(yscrollcommand=vs.set)
        canvas.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self._col = 0
        self._row = 0

    def add(self, widget):
        widget.grid(row=self._row, column=self._col, padx=6, pady=6)
        self._col += 1
        if self._col >= 8:
            self._col = 0
            self._row += 1

    def clear(self):
        for c in list(self.body.children.values()):
            c.destroy()
        self._col = 0
        self._row = 0


class EditDialog_Kind(StrEnum):
    str = "str"
    int = "int"
    float = "float"
    list = "list"
    tuple = "tuple"
    set = "set"
    dict = "dict"
    text = "text"
    choice = "choice"
    choice_dict = "choice_dict"


class GenericEditDialog(simpledialog.Dialog):
    """
    Schema-based modal editor.
    schema: list of dicts with keys:
        - name (str)
        - label (str)
        - kind  ("int"|"float"|"str"|"text"|"bool"|"choice"|"choice_dict")
        - choices (list[str] for "choice", or dict[str, Any] for "choice_dict")
        - min/max (optional for numeric kinds)
    values: dict[str, Any] initial values
    Result is a dict on success in self.result, else None.
    """

    def __init__(self, parent: tk.Misc, title: str, schema: list[dict[str, Any]], values: dict[str, Any]):
        self.schema = list(schema)
        self.values = dict(values or {})
        self.widgets: dict[str, tk.Widget] = {}
        # per-field metadata (var, mapping, etc.)
        self._meta: dict[str, dict[str, Any]] = {}
        super().__init__(parent, title)

    # ---- Dialog hooks ----
    def body(self, master: tk.Frame) -> tk.Widget:
        # grid: label | widget
        for r, fld in enumerate(self.schema):
            label = fld.get("label", fld["name"])
            ttk.Label(master, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
            w = self._make_field(master, fld, self.values.get(fld["name"]))
            w.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
            self.widgets[fld["name"]] = w
        master.columnconfigure(1, weight=1)
        # focus first widget if any
        return next(iter(self.widgets.values())) if self.widgets else master

    def buttonbox(self):
        box = ttk.Frame(self)
        ok = ttk.Button(box, text="OK", width=10, command=self.ok)
        ca = ttk.Button(box, text="Cancel", width=10, command=self.cancel)
        ok.pack(side="left", padx=5)
        ca.pack(side="left", padx=5)
        box.pack(pady=8)
        self.bind("<Return>", lambda e: self.ok())
        self.bind("<Escape>", lambda e: self.cancel())

    def validate(self) -> bool:
        out: dict[str, Any] = {}
        try:
            for fld in self.schema:
                name = fld["name"]
                kind = str(fld.get("kind", "str")).lower()
                raw = self._get_widget_value(name, kind, fld)
                # numeric clamps
                if kind in ("int", "float"):
                    if "min" in fld and raw < fld["min"]:
                        raise ValueError(f"{fld.get('label', name)} must be ≥ {fld['min']}")
                    if "max" in fld and raw > fld["max"]:
                        raise ValueError(f"{fld.get('label', name)} must be ≤ {fld['max']}")
                out[name] = raw
        except Exception as e:
            messagebox.showerror("Invalid input", str(e), parent=self)
            return False
        self._result = out
        return True

    def apply(self):
        self.result = getattr(self, "_result", None)

    # ---- builders ----
    def _make_field(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        kind = str(fld.get("kind", "str")).lower()
        name = fld["name"]
        self._meta[name] = meta = {}

        if kind == "bool":
            var = tk.BooleanVar(value=bool(init_val))
            meta["var"] = var
            w = ttk.Checkbutton(parent, variable=var)
            return w

        if kind in ("int", "float", "str"):
            init_str = self._stringify_init(init_val)
            var = tk.StringVar(value=init_str)
            meta["var"] = var
            ent = ttk.Entry(parent, textvariable=var)
            if kind in ("int", "float"):
                ent.configure(width=8)
            return ent

        if kind == "text":
            txt = tk.Text(parent, width=32, height=4, wrap="word")
            if init_val not in (None, ""):
                txt.insert("1.0", self._stringify_init(init_val))
            return txt

        if kind == "choice":
            choices = list(fld.get("choices") or [])
            init_str = self._stringify_init(init_val)
            var = tk.StringVar(value=init_str if init_str in choices else (init_str or (choices[0] if choices else "")))
            meta["var"] = var
            cb = ttk.Combobox(parent, values=choices, textvariable=var, state="readonly")
            return cb

        if kind == "choice_dict":
            mapping: dict[str, Any] = dict(fld.get("choices") or {})
            meta["map"] = mapping
            keys = list(mapping.keys())
            init_key = None
            if isinstance(init_val, str) and init_val in mapping:
                init_key = init_val
            else:
                for k, v in mapping.items():
                    if v == init_val or (isinstance(v, Path) and str(v) == str(init_val)):
                        init_key = k
                        break
            var = tk.StringVar(value=init_key or (keys[0] if keys else ""))
            meta["var"] = var
            cb = ttk.Combobox(parent, values=keys, textvariable=var, state="readonly")
            return cb

        # fallback to plain entry
        var = tk.StringVar(value=self._stringify_init(init_val))
        meta["var"] = var
        return ttk.Entry(parent, textvariable=var)

    # ---- reads ----
    def _get_widget_value(self, name: str, kind: str, fld: dict) -> Any:
        w = self.widgets[name]
        meta = self._meta.get(name, {})

        if kind == "bool":
            return bool(meta["var"].get())

        if kind == "text":
            return w.get("1.0", "end-1c")  # pyright: ignore[reportAttributeAccessIssue]

        if kind == "choice":
            return str(meta["var"].get()).strip()

        if kind == "choice_dict":
            key = str(meta["var"].get())
            mapping: dict[str, Any] = meta.get("map", {})
            # return mapped value if present; else return key
            return mapping.get(key, key)

        # entries
        s = str(meta["var"].get()).strip() if "var" in meta else str(getattr(w, "get")())
        if kind == "int":
            try:
                return int(float(s))
            except Exception:
                raise ValueError(f"{fld.get('label', name)} must be an integer")
        if kind == "float":
            try:
                return float(s)
            except Exception:
                raise ValueError(f"{fld.get('label', name)} must be a number")
        return s

    # ---- helpers ----
    @staticmethod
    def _stringify_init(v: Any) -> str:
        if isinstance(v, Enum):
            return str(getattr(v, "value", str(v)))
        if isinstance(v, Path):
            return v.name
        return "" if v is None else str(v)
