from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from typing import Protocol

from models.geo import Line
from models.objects import Icon, Label
from models.params import Params


# ---- Command infra ----
class Command(Protocol):
    def do(self): ...
    def undo(self): ...


class Command_Stack:
    """Simple undo/redo stack."""

    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def push_and_do(self, cmd: Command):
        cmd.do()
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self):
        if not self._undo:
            return
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)

    def redo(self):
        if not self._redo:
            return
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)


# ---- Concrete commands ----
@dataclass
class Add_Line:
    params: Params
    line: Line
    on_after: Callable[[], None]  # e.g., lambda: app.layers.redraw("lines")

    def do(self):
        self.params.lines.append(self.line)
        self.on_after()

    def undo(self):
        # pop last occurrence of this exact object (cheap path)
        if self.params.lines and self.params.lines[-1] is self.line:
            self.params.lines.pop()
        else:
            # fall back: remove by value once
            for idx in range(len(self.params.lines) - 1, -1, -1):
                if self.params.lines[idx] == self.line:
                    del self.params.lines[idx]
                    break
        self.on_after()

    @classmethod
    def from_points(cls, params: Params, x1, y1, x2, y2, col, width, capstyle, on_after):
        return cls(params, Line(x1, y1, x2, y2, col, width, capstyle), on_after=on_after)


@dataclass
class Add_Label:
    params: Params
    label: Label
    on_after: Callable[[], None]

    def do(self):
        self.params.labels.append(self.label)
        self.on_after()

    def undo(self):
        for idx in range(len(self.params.labels) - 1, -1, -1):
            if self.params.labels[idx] == self.label:
                del self.params.labels[idx]
                break
        self.on_after()


@dataclass
class Add_Icon:
    params: Params
    icon: Icon
    on_after: Callable[[], None]

    def do(self):
        self.params.icons.append(self.icon)
        self.on_after()

    def undo(self):
        for idx in range(len(self.params.icons) - 1, -1, -1):
            if self.params.icons[idx] == self.icon:
                del self.params.icons[idx]
                break
        self.on_after()


@dataclass
class Move_Label:
    params: Params
    index: int
    old_xy: tuple[int, int]
    new_xy: tuple[int, int]
    on_after: Callable[[], None]

    def do(self):
        lab = self.params.labels[self.index]
        self.params.labels[self.index] = replace(lab, x=self.new_xy[0], y=self.new_xy[1])
        self.on_after()

    def undo(self):
        lab = self.params.labels[self.index]
        self.params.labels[self.index] = replace(lab, x=self.old_xy[0], y=self.old_xy[1])
        self.on_after()


@dataclass
class Move_Icon:
    params: Params
    index: int
    old_xy: tuple[int, int]
    new_xy: tuple[int, int]
    on_after: Callable[[], None]

    def do(self):
        ico = self.params.icons[self.index]
        self.params.icons[self.index] = replace(ico, x=self.new_xy[0], y=self.new_xy[1])
        self.on_after()

    def undo(self):
        ico = self.params.icons[self.index]
        self.params.icons[self.index] = replace(ico, x=self.old_xy[0], y=self.old_xy[1])
        self.on_after()
