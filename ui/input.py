from __future__ import annotations

from dataclasses import dataclass
import tkinter as tk

_SHIFT_KEYS = {"Shift_L", "Shift_R"}
_CTRL_KEYS = {"Control_L", "Control_R"}
_ALT_KEYS = {"Alt_L", "Alt_R", "Alt", "ISO_Level3_Shift", "Option_L", "Option_R"}
_META_KEYS = {"Meta_L", "Meta_R", "Super_L", "Super_R", "Command"}

_EVENTTYPE = getattr(tk, "EventType", None)
_KEYPRESS_EVENT_TYPES = {"KeyPress", str(getattr(_EVENTTYPE, "KeyPress", "2"))}
_KEYRELEASE_EVENT_TYPES = {"KeyRelease", str(getattr(_EVENTTYPE, "KeyRelease", "3"))}

_SHIFT_MASK = 0x0001
_CTRL_MASK = 0x0004
_ALT_MASK = 0x0008
_ALT_MASK_WIN32 = 0x20000


class ModifierTracker:
    def __init__(self) -> None:
        self.shift = False
        self.ctrl = False
        self.alt = False
        self.meta = False
        self.windowing: str | None = None

    def update(self, evt: tk.Event) -> None:
        evt_type = str(getattr(evt, "type", ""))
        if evt_type in _KEYPRESS_EVENT_TYPES:
            down = True
        elif evt_type in _KEYRELEASE_EVENT_TYPES:
            down = False
        else:
            return
        keysym = getattr(evt, "keysym", "")
        if keysym in _SHIFT_KEYS:
            self.shift = down
        elif keysym in _CTRL_KEYS:
            self.ctrl = down
        elif keysym in _ALT_KEYS:
            self.alt = down
        elif keysym in _META_KEYS:
            self.meta = down

    def snapshot(self, state: int = 0) -> "Modifiers":
        # Prefer tracked keys for cross-platform correctness; masks are fallback for mouse events.
        shift = bool(state & _SHIFT_MASK) or self.shift
        ctrl = bool(state & _CTRL_MASK) or self.ctrl
        alt = bool(state & (_ALT_MASK | _ALT_MASK_WIN32)) or self.alt
        if self.windowing == "aqua":
            ctrl = ctrl or self.meta
        return Modifiers(shift=shift, ctrl=ctrl, alt=alt)

    def reset(self) -> None:
        self.shift = False
        self.ctrl = False
        self.alt = False
        self.meta = False


_mods = ModifierTracker()


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
        if _mods.windowing is None and getattr(evt, "widget", None) is not None:
            try:
                _mods.windowing = evt.widget.tk.call("tk", "windowingsystem")
            except Exception:
                _mods.windowing = None
        _mods.update(evt)
        state = int(getattr(evt, "state", 0))
    elif isinstance(evt, MotionEvent):
        state = int(evt.state)
    elif isinstance(evt, int):
        state = evt
    elif evt is None:
        state = 0
    else:
        raise TypeError(f"Unsupported event type: {type(evt)}")
    return _mods.snapshot(state)


def handle_key_event(evt: tk.Event) -> None:
    if _mods.windowing is None and getattr(evt, "widget", None) is not None:
        try:
            _mods.windowing = evt.widget.tk.call("tk", "windowingsystem")
        except Exception:
            _mods.windowing = None
    _mods.update(evt)


def reset_mods() -> None:
    _mods.reset()
