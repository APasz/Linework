from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

SHIFT_MASK = 0x0001
CONTROL_MASK = 0x0004
ALT_MASK = 0x0008


@dataclass(frozen=True, slots=True)
class Modifiers:
    shift: bool
    ctrl: bool
    alt: bool


def get_mods(evt: tk.Event) -> Modifiers:
    state = evt.state if isinstance(evt.state, int) else 0
    return Modifiers(
        shift=bool(state & SHIFT_MASK),
        ctrl=bool(state & CONTROL_MASK),
        alt=bool(state & ALT_MASK),
    )
