# ui/status.py
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from typing import Literal

Side = Literal["left", "right"]


@dataclass(order=True)
class _Overlay:
    # sort by (-priority, seq) so higher priority appears first,
    # and among equals, earlier seq wins
    sort_key: tuple[int, int] = field(init=False, repr=False)
    key: str
    text: str
    priority: int = 0
    side: Side = "left"
    seq: int = 0  # insertion order

    def __post_init__(self):
        # negative priority to get descending in sorted()
        self.sort_key = (-self.priority, self.seq)


class Status:
    """
    Weighted, ordered status:
        - set(text) -> base left text
        - hold(key, text, priority=0, side='left')
        - release(key)
        - temp(text, ms=1200, priority=50, side='left')
        - set_suffix(text) -> sugar for hold('suffix', text, side='right', priority=-10)
    Render rule:
        For each side (left/right), show the highest-priority overlay if any,
        else the base (left) + optional right overlay.
        If both sides have overlays, left | right are joined with an em dash.
    """

    def __init__(self, root: tk.Misc):
        self.var = tk.StringVar(value="")
        self._root = root

        self._base_left: str = ""
        self._seq = 0

        self._held: dict[str, _Overlay] = {}
        self._temp_key: str | None = None
        self._temp_after: str | None = None

        # default “suffix” slot (right channel)
        self._suffix_key = "__suffix__"

    # ---- base ----
    def set(self, text: str):
        self._base_left = text
        self._render()

    # ---- suffix sugar ----
    def set_suffix(self, text: str):
        if text:
            self.hold(self._suffix_key, text, priority=-10, side="right")
        else:
            self.release(self._suffix_key)

    def clear_suffix(self):
        self.release(self._suffix_key)

    # ---- held overlays (persistent until release) ----
    def hold(self, key: str, text: str, *, priority: int = 0, side: Side = "left"):
        self._seq += 1
        self._held[key] = _Overlay(key=key, text=text, priority=priority, side=side, seq=self._seq)
        self._render()

    def release(self, key: str):
        if key in self._held:
            del self._held[key]
            if self._temp_key == key:
                self._temp_key = None
            self._render()

    # ---- temporary overlays (auto-clear) ----
    def temp(self, text: str, ms: int = 1200, *, priority: int = 50, side: Side = "left"):
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

    def _clear_temp(self):
        if self._temp_key:
            self.release(self._temp_key)
        self._temp_after = None

    # ---- clear all ----
    def clear(self):
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
    def _render(self):
        left = self._pick_side("left") or self._base_left
        right = self._pick_side("right") or ""

        if left and right:
            self.var.set(f"{left} | {right}")
        else:
            self.var.set(left or right or "")

    def _pick_side(self, side: Side) -> str:
        # choose the highest-priority overlay on this side
        items = [ov for ov in self._held.values() if ov.side == side]
        if not items:
            return ""
        top = sorted(items)[0]  # because sort_key is (-priority, seq)
        return top.text
