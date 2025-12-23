from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

SHIFT_MASK = 0x0001
CONTROL_MASK = 0x0004
ALT_MASK = 0x0008
_ALT_KEYSYMS = {"Alt_L", "Alt_R", "Alt", "ISO_Level3_Shift"}
_alt_held = False


def _update_alt_state(evt: tk.Event) -> None:
    # Track Alt via key events to handle Windows cases where left Alt isn't set in mouse state.
    global _alt_held
    keysym = getattr(evt, "keysym", "")
    if keysym not in _ALT_KEYSYMS:
        return
    evt_type = str(getattr(evt, "type", ""))
    if evt_type == "KeyPress":
        _alt_held = True
    elif evt_type == "KeyRelease":
        _alt_held = False


@dataclass(frozen=True, slots=True)
class Modifiers:
    shift: bool
    ctrl: bool
    alt: bool


@dataclass(slots=True)
class MotionEvent:
    x: int
    y: int
    state: int
    mods: Modifiers | None = None


def get_mods(evt: tk.Event | MotionEvent | int | None) -> Modifiers:
    if isinstance(evt, tk.Event):
        _update_alt_state(evt)
        state = int(evt.state)
    elif isinstance(evt, MotionEvent):
        state = int(evt.state)
    elif isinstance(evt, int):
        state = evt
    elif evt is None:
        state = 0
    else:
        raise TypeError(f"Unsupported event type: {type(evt)}")
    return Modifiers(
        shift=bool(state & SHIFT_MASK),
        ctrl=bool(state & CONTROL_MASK),
        alt=bool(state & ALT_MASK) or _alt_held,
    )
