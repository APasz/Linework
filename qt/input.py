"""Input helpers for Qt modifier tracking and motion events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from PySide6 import QtCore, QtGui


@dataclass(frozen=True, slots=True)
class Modifiers:
    """Frozen snapshot of modifier states."""

    shift: bool
    ctrl: bool
    alt: bool


@dataclass(frozen=True, slots=True)
class MotionEvent:
    """Simplified motion event container."""

    x: int
    y: int
    mods: Modifiers


def get_mods(evt: QtGui.QInputEvent | QtCore.Qt.KeyboardModifier) -> Modifiers:
    """Return modifiers for an input event or modifier mask.

    Args;
        evt: The Qt input event or modifier mask.

    Returns;
        The modifier snapshot.
    """
    if isinstance(evt, QtGui.QInputEvent):
        mods = cast(QtCore.Qt.KeyboardModifier, evt.modifiers())
    else:
        mods = evt
    return Modifiers(
        shift=bool(mods & QtCore.Qt.KeyboardModifier.ShiftModifier),
        ctrl=bool(mods & QtCore.Qt.KeyboardModifier.ControlModifier),
        alt=bool(mods & QtCore.Qt.KeyboardModifier.AltModifier),
    )
