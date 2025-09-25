from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from models.geo import Iconlike, Label, Line, Point
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
class Multi:
    items: list[Command]
    on_after: Callable[[], None] | None = None

    def do(self):
        for c in self.items:
            c.do()
        if self.on_after:
            self.on_after()

    def undo(self):
        for c in reversed(self.items):
            c.undo()
        if self.on_after:
            self.on_after()


@dataclass
class Add_Line:
    params: Params
    line: Line
    on_after: Callable[[], None]

    def do(self):
        if (self.line.a.x, self.line.a.y) == (self.line.b.x, self.line.b.y):
            return
        self.params.lines.append(self.line)
        self.on_after()

    def undo(self):
        if self.params.lines and self.params.lines[-1] is self.line:
            self.params.lines.pop()
        else:
            for idx in range(len(self.params.lines) - 1, -1, -1):
                if self.params.lines[idx] == self.line:
                    del self.params.lines[idx]
                    break
        self.on_after()


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
    icon: Iconlike
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
class Move_Line_End:
    params: Params
    index: int
    end: Literal["a", "b"]
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self):
        lin = self.params.lines[self.index]
        if self.end == "a":
            lin.a = self.new_point
        else:
            lin.b = self.new_point
        self.params.lines[self.index] = lin
        self.on_after()

    def undo(self):
        lin = self.params.lines[self.index]
        if self.end == "a":
            lin.a = self.old_point
        else:
            lin.b = self.old_point
        self.params.lines[self.index] = lin
        self.on_after()


@dataclass
class Move_Label:
    params: Params
    index: int
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self):
        lab = self.params.labels[self.index]
        lab.p = self.new_point
        self.params.labels[self.index] = lab
        self.on_after()

    def undo(self):
        lab = self.params.labels[self.index]
        lab.p = self.old_point
        self.params.labels[self.index] = lab
        self.on_after()


@dataclass
class Move_Icon:
    params: Params
    index: int
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self):
        ico = self.params.icons[self.index]
        ico.p = self.new_point
        self.params.icons[self.index] = ico
        self.on_after()

    def undo(self):
        ico = self.params.icons[self.index]
        ico.p = self.old_point
        self.params.icons[self.index] = ico
        self.on_after()


@dataclass
class Delete_Line:
    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Line | None = None

    def do(self):
        if 0 <= self.index < len(self.params.lines):
            self._removed = self.params.lines.pop(self.index)
            self.on_after()

    def undo(self):
        if self._removed is not None:
            self.params.lines.insert(self.index, self._removed)
            self.on_after()


@dataclass
class Delete_Label:
    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Label | None = None

    def do(self):
        if 0 <= self.index < len(self.params.labels):
            self._removed = self.params.labels.pop(self.index)
            self.on_after()

    def undo(self):
        if self._removed is not None:
            self.params.labels.insert(self.index, self._removed)
            self.on_after()


@dataclass
class Delete_Icon:
    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Iconlike | None = None

    def do(self):
        if 0 <= self.index < len(self.params.icons):
            self._removed = self.params.icons.pop(self.index)
            self.on_after()

    def undo(self):
        if self._removed is not None:
            self.params.icons.insert(self.index, self._removed)
            self.on_after()
