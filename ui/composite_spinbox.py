"""Composite spinbox widget with increment/decrement buttons."""

import tkinter as tk
from collections.abc import Callable
from enum import StrEnum
from tkinter import ttk
from typing import Any


class Justify(StrEnum):
    """Text justification options for the entry widget."""

    left = "left"
    centre = "center"
    right = "right"


class Composite_Spinbox(ttk.Frame):
    def __init__(
        self,
        master: tk.Misc,
        *,
        from_: int | float = 0,
        to: int | float = 100,
        increment: int | float = 1,
        textvariable: tk.Variable | None = None,
        width: int = 6,
        command: Callable[[], None] | None = None,
        wrap: bool = False,
        state: str = "normal",
        justify: Justify = Justify.right,
        **kwargs: Any,
    ) -> None:
        """Create a composite spinbox widget.

        Args;
            master: The parent widget.
            from_: Minimum value.
            to: Maximum value.
            increment: Step size.
            textvariable: Optional Tk variable for the entry.
            width: Entry width in characters.
            command: Optional callback for value changes.
            wrap: Whether to wrap around at bounds.
            state: Initial widget state.
            justify: Entry text justification.
            **kwargs: Additional ttk.Frame options.
        """
        super().__init__(master, **kwargs)
        self._min = from_
        self._max = to
        self._inc = increment
        self._wrap = wrap
        self._command = command

        self.var = textvariable or tk.StringVar(value=str(self._min))

        self.entry = ttk.Entry(self, textvariable=self.var, width=width, justify=justify.value)
        self.entry.grid(row=0, column=0, sticky="nsew", padx=0, pady=4)
        btncol = ttk.Frame(self)
        btncol.grid(row=0, column=1, sticky="", padx=0, pady=4)
        self.columnconfigure(0, weight=1)

        style = ttk.Style()
        style.configure("SpinButton.TButton", padding=1, font=("TkDefaultFont", 6))
        self.btn_up = ttk.Button(
            btncol, text="▲", width=1, style="SpinButton.TButton", command=self._bump_up, takefocus=0
        )

        self.btn_dn = ttk.Button(
            btncol, text="▼", width=1, style="SpinButton.TButton", command=self._bump_down, takefocus=0
        )
        self.btn_up.pack(side="top", fill="both")
        self.btn_dn.pack(side="bottom", fill="both")

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
        """Return the current value as a string.

        Returns;
            The entry value.
        """
        return self.var.get()

    def set(self, value: int | float | str) -> None:
        """Set the current value.

        Args;
            value: The new value.
        """
        self.var.set(str(value))
        self._validate_and_clamp(call_command=False)

    def set_justify(self, justify: Justify) -> None:
        """Set the entry text justification.

        Args;
            justify: The justification to apply.
        """
        self.entry.configure(justify=justify.value)

    def configure(
        self,
        cnf: str | dict[str, Any] | None = None,  # accept str/dict/None like ttk
        **kw: Any,
    ) -> Any:  # may return a tuple when querying a single option
        """Configure or query options.

        Args;
            cnf: Optional query key or config dict.
            **kw: Option values.

        Returns;
            The queried option tuple, or None.
        """
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
        """Alias for configure."""
        return self.configure(cnf, **kw)

    # --- internals ---
    def _on_mousewheel(self, e: tk.Event) -> str:
        delta = e.delta
        # Windows: +/-120 multiples, macOS: other values; invert if needed
        if delta > 0:
            self._bump_up()
        elif delta < 0:
            self._bump_down()
        return "break"

    def _parse(self) -> int | float:
        s = str(self.var.get()).strip()
        try:
            v = int(s)
        except ValueError:
            try:
                v = float(s)
            except ValueError:
                v = self._min
        return v

    def _format(self, v: int | float) -> str:
        if isinstance(self._inc, int) or (isinstance(self._inc, float) and self._inc.is_integer()):
            return str(round(v))
        return f"{v:.6g}"

    def _validate_and_clamp(self, call_command: bool = True) -> None:
        v = self._parse()
        if not self._wrap:
            v = min(max(v, self._min), self._max)
        self.var.set(self._format(v))
        if call_command and self._command:
            self._command()

    def _validate_event(self, _e: tk.Event | None = None) -> None:
        self._validate_and_clamp(call_command=True)

    def _bump(self, direction: int) -> None:
        v = self._parse()
        step = self._inc * direction
        v_next = v + step
        if self._wrap:
            span = self._max - self._min
            if span > 0:
                v_next = self._min + ((v_next - self._min) % span)
            else:
                v_next = self._min
        else:
            v_next = min(max(v_next, self._min), self._max)
        self.var.set(self._format(v_next))
        if self._command:
            self._command()

    def _bump_up(self) -> None:
        self._bump(+1)

    def _bump_down(self) -> None:
        self._bump(-1)

    def state(self, statespec: str | None = None) -> str | None:
        """Get or set the entry state.

        Args;
            statespec: Optional state name.

        Returns;
            The current state when queried.
        """
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
