# ui/edit_dialog.py
from __future__ import annotations
import tkinter as tk
from tkinter import ttk, simpledialog, messagebox
from typing import Any

Number = int | float


class GenericEditDialog(simpledialog.Dialog):
    """Schema-based modal editor. Returns a dict on success via self.result."""

    def __init__(self, parent: tk.Misc, title: str, schema: list[dict[str, Any]], values: dict[str, Any]):
        self.schema = schema
        self.values = dict(values)
        self.widgets: dict[str, tk.Widget] = {}
        super().__init__(parent, title)

    # ---- Dialog overrides ----
    def body(self, master: tk.Frame) -> tk.Widget:
        # Grid form
        for r, fld in enumerate(self.schema):
            label = fld.get("label", fld["name"])
            ttk.Label(master, text=label).grid(row=r, column=0, sticky="w", padx=6, pady=4)
            w = self._make_field(master, fld, self.values.get(fld["name"]))
            w.grid(row=r, column=1, sticky="ew", padx=6, pady=4)
            self.widgets[fld["name"]] = w
        master.columnconfigure(1, weight=1)
        return next(iter(self.widgets.values())) if self.widgets else master

    def validate(self) -> bool:
        # Pull and type-check inputs
        out: dict[str, Any] = {}
        try:
            for fld in self.schema:
                name = fld["name"]
                kind = fld.get("kind", "str")
                raw = self._get_widget_value(self.widgets[name], kind)
                # optional extra validators
                if "min" in fld and isinstance(raw, (int, float)) and raw < fld["min"]:
                    raise ValueError(f"{fld.get('label', name)} must be ≥ {fld['min']}")
                if "max" in fld and isinstance(raw, (int, float)) and raw > fld["max"]:
                    raise ValueError(f"{fld.get('label', name)} must be ≤ {fld['max']}")
                out[name] = raw
        except Exception as e:
            messagebox.showerror("Invalid input", str(e), parent=self)
            return False
        self.result = out
        return True

    # ---- field makers / extractors ----
    def _make_field(self, parent: tk.Misc, fld: dict[str, Any], value: Any) -> tk.Widget:
        kind = fld.get("kind", "str")
        if kind == "int":
            sv = tk.StringVar(value=str(int(value if value is not None else 0)))
            ent = ttk.Entry(parent, textvariable=sv, width=8, justify="right")
            ent._var = sv  # type: ignore[attr-defined]
            return ent
        if kind == "float":
            sv = tk.StringVar(value=str(float(value if value is not None else 0.0)))
            ent = ttk.Entry(parent, textvariable=sv, width=8, justify="right")
            ent._var = sv  # type: ignore[attr-defined]
            return ent
        if kind == "text":
            sv = tk.StringVar(value=str(value if value is not None else ""))
            ent = ttk.Entry(parent, textvariable=sv)
            ent._var = sv  # type: ignore[attr-defined]
            return ent
        if kind == "choice":
            sv = tk.StringVar(value=str(value if value is not None else ""))
            cb = ttk.Combobox(parent, textvariable=sv, values=list(fld.get("choices", [])), state="readonly")
            cb._var = sv  # type: ignore[attr-defined]
            return cb
        if kind == "bool":
            sv = tk.BooleanVar(value=bool(value))
            cb = ttk.Checkbutton(parent, variable=sv)
            cb._var = sv  # type: ignore[attr-defined]
            return cb
        # default string
        sv = tk.StringVar(value=str(value if value is not None else ""))
        ent = ttk.Entry(parent, textvariable=sv)
        ent._var = sv  # type: ignore[attr-defined]
        return ent

    def _get_widget_value(self, w: tk.Widget, kind: str) -> Any:
        sv = getattr(w, "_var", None)
        s = sv.get() if sv is not None else ""  # type: ignore[assignment]
        if kind == "int":
            return int(s)
        if kind == "float":
            return float(s)
        if kind == "choice":
            return str(s)
        if kind == "text":
            return str(s)
        if kind == "bool":
            return bool(s)
        return str(s)
