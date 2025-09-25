import tkinter as tk
from enum import StrEnum
from tkinter import ttk
from typing import Any


class Justify(StrEnum):
    left = "left"
    centre = "center"
    right = "right"


class Composite_Spinbox(ttk.Frame):
    def __init__(
        self,
        master,
        *,
        from_=0,
        to=100,
        increment=1,
        textvariable: tk.Variable | None = None,
        width=6,
        command=None,
        wrap=False,
        state: str = "normal",
        justify: Justify = Justify.right,
        **kwargs,
    ):
        super().__init__(master, **kwargs)
        self._min = from_
        self._max = to
        self._inc = increment
        self._wrap = wrap
        self._command = command

        self.var = textvariable or tk.StringVar(value=str(self._min))

        self.entry = ttk.Entry(self, textvariable=self.var, width=width, justify=justify.value)
        self.entry.grid(row=0, column=0, sticky="nsew")
        btncol = ttk.Frame(self)
        btncol.grid(row=0, column=1, sticky="ns", padx=(1, 0))
        self.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure("SpinButton.TButton", padding=0, font=("TkDefaultFont", 6))
        self.btn_up = ttk.Button(
            btncol, text="▲", width=1, style="SpinButton.TButton", command=self._bump_up, takefocus=0
        )

        self.btn_dn = ttk.Button(
            btncol, text="▼", width=1, style="SpinButton.TButton", command=self._bump_down, takefocus=0
        )
        self.btn_up.pack(side="top", fill="x")
        self.btn_dn.pack(side="top", fill="x")

        # bindings
        self.entry.bind("<Return>", self._validate_event)
        self.entry.bind("<FocusOut>", self._validate_event)
        self.entry.bind("<Up>", lambda e: (self._bump_up(), "break"))
        self.entry.bind("<Down>", lambda e: (self._bump_down(), "break"))
        # Linux wheel
        self.entry.bind("<Button-4>", lambda e: (self._bump_up(), "break"))
        self.entry.bind("<Button-5>", lambda e: (self._bump_down(), "break"))
        # Other platforms
        self.entry.bind("<MouseWheel>", self._on_mousewheel)

        self.state(state)

    # --- public-ish API parity ---
    def get(self) -> str:
        return self.var.get()

    def set(self, value):
        self.var.set(str(value))
        self._validate_and_clamp(call_command=False)

    def set_justify(self, justify: Justify):
        self.entry.configure(justify=justify.value)

    def configure(
        self,
        cnf: str | dict[str, Any] | None = None,  # accept str/dict/None like ttk
        **kw: Any,
    ) -> Any:  # may return a tuple when querying a single option
        # Query form: spinbox.configure('option')
        if isinstance(cnf, str) and not kw:
            return super().configure(cnf)

        # Merge positional dict into kw (Tk accepts both styles)
        if isinstance(cnf, dict):
            kw = {**cnf, **kw}

        # Intercept our custom keys
        if "from_" in kw:
            self._min = kw.pop("from_")
        if "to" in kw:
            self._max = kw.pop("to")
        if "increment" in kw:
            self._inc = kw.pop("increment")
        if "wrap" in kw:
            self._wrap = kw.pop("wrap")
        if "command" in kw:
            self._command = kw.pop("command")
        if "state" in kw:
            self.state(kw.pop("state"))

        # Forward rest to ttk.Frame
        if kw:
            return super().configure(**kw)
        return None

    # Alias expected by Tk
    def config(self, cnf: str | dict[str, Any] | None = None, **kw: Any) -> Any:
        return self.configure(cnf, **kw)

    # --- internals ---
    def _on_mousewheel(self, e):
        delta = e.delta
        # Windows: +/-120 multiples, macOS: other values; invert if needed
        if delta > 0:
            self._bump_up()
        elif delta < 0:
            self._bump_down()
        return "break"

    def _parse(self):
        s = str(self.var.get()).strip()
        try:
            v = int(s)
        except ValueError:
            try:
                v = float(s)
            except ValueError:
                v = self._min
        return v

    def _format(self, v):
        if isinstance(self._inc, int) or (isinstance(self._inc, float) and self._inc.is_integer()):
            return str(round(v))
        return f"{v:.6g}"

    def _validate_and_clamp(self, call_command=True):
        v = self._parse()
        if not self._wrap:
            v = min(max(v, self._min), self._max)
        self.var.set(self._format(v))
        if call_command and self._command:
            self._command()

    def _validate_event(self, _e=None):
        self._validate_and_clamp(call_command=True)

    def _bump(self, direction: int):
        v = self._parse()
        step = self._inc * direction
        v2 = v + step
        if self._wrap:
            span = (self._max - self._min) + (0 if isinstance(self._inc, int) else 0)
            if span == 0:
                v2 = self._min
            else:
                if isinstance(self._inc, int):
                    rng = self._max - self._min + 1
                    v2 = ((round(v2) - self._min) % rng) + self._min
                else:
                    v2 = min(max(v2, self._min), self._max)
        else:
            v2 = min(max(v2, self._min), self._max)

        self.var.set(self._format(v2))
        if self._command:
            self._command()

    def _bump_up(self):
        self._bump(+1)

    def _bump_down(self):
        self._bump(-1)

    def state(self, statespec: str | None = None):
        if statespec is None:
            return self.entry.cget("state")
        if statespec == "readonly":
            self.entry.state(["readonly"])
            self.btn_up.state(["!disabled"])
            self.btn_dn.state(["!disabled"])
        elif statespec == "disabled":
            self.entry.state(["disabled"])
            self.btn_up.state(["disabled"])
            self.btn_dn.state(["disabled"])
        else:
            self.entry.state(["!readonly", "!disabled"])
            self.btn_up.state(["!disabled"])
            self.btn_dn.state(["!disabled"])
