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
from models.assets import _builtin_icon_plan, _open_rgba
from models.geo import Icon_Name, Icon_Source, Icon_Type, Point
from models.styling import Colours

if TYPE_CHECKING:
    from controllers.app import App


class Icon_Gallery(tk.Toplevel):
    def __init__(self, master, app: App, recent: Iterable[Icon_Source], at: Point | None = None):
        super().__init__(master)
        self._thumb_size = 40
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
            self.geometry(f"+{at.x}+{at.y}")
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

        plan = _builtin_icon_plan(name, self._thumb_size - 8, Colours.white.hex)

        img = Image.new("RGBA", (self._thumb_size, self._thumb_size), (0, 0, 0, 0))

        _emit_pil_plan(img, plan, self._thumb_size // 2, self._thumb_size // 2, 0)

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
        im = _open_rgba(path, self._thumb_size, self._thumb_size)
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


class ED_Kind(StrEnum):
    str = "str"
    int = "int"
    float = "float"
    bool = "bool"
    text = "text"
    choice = "choice"
    choice_dict = "choice_dict"


@dataclass(frozen=True)
class _FieldSpec:
    name: str
    label: str | None = None
    kind: ED_Kind = ED_Kind.str
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
        if item.kind is ED_Kind.choice and item.choices:
            d["choices"] = item.choices() if callable(item.choices) else list(item.choices)
        if item.kind is ED_Kind.choice_dict and item.choices_dict:
            d["choices"] = item.choices_dict() if callable(item.choices_dict) else dict(item.choices_dict)
        return d

    if not isinstance(item, dict):
        raise TypeError(f"Schema entries must be dict or _FieldSpec, got {type(item)}")
    d = dict(item)
    k = d.get("kind", "str")
    if isinstance(k, ED_Kind):
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
        parent: tk.Misc,
        title: str,
        schema: Sequence[dict[str, Any] | _FieldSpec],
        values: dict[str, Any] | None,
    ):
        self.schema: list[dict[str, Any]] = [_coerce_schema_item(s) for s in list(schema)]
        self.values = dict(values or {})
        self.widgets: dict[str, tk.Widget] = {}
        self._meta: dict[str, dict[str, Any]] = {}
        super().__init__(parent, title)

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
            messagebox.showerror("Invalid input", str(e), parent=self)
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
        init_key = str(init_val) if init_val is not None else (keys[0] if keys else "")
        var = tk.StringVar(value=init_key)
        self._meta[fld["name"]]["var"] = var
        return ttk.Combobox(parent, values=keys, textvariable=var, state="readonly")

    def _build_choice_dict(self, parent: tk.Widget, fld: dict, init_val: Any) -> tk.Widget:
        mapping = _resolve_choices_map(fld.get("choices"))
        keys = list(mapping.keys())
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
            # lenient: allow "12.0"
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
        # Close any open ttk combobox popdowns to avoid X BadWindow on X11
        for w in self.widgets.values():
            if isinstance(w, ttk.Combobox):
                try:
                    w.event_generate("<Escape>")  # closes the popdown if open
                except Exception:
                    pass
        try:
            self.update_idletasks()
        except Exception:
            pass

    def _hide_combobox_popdowns(self):
        # Close any open ttk.Combobox popdown without triggering dialog bindings
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
