from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol, Callable

from models.params import Params
from models.geo import Line
from models.objects import Label, Icon


# ---- Command infra ----


class Command(Protocol):
    def do(self) -> None: ...
    def undo(self) -> None: ...


class CommandStack:
    """Simple undo/redo stack."""

    def __init__(self):
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def push_and_do(self, cmd: Command) -> None:
        cmd.do()
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self) -> None:
        if not self._undo:
            return
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)

    def redo(self) -> None:
        if not self._redo:
            return
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)


# ---- Concrete commands ----


@dataclass
class AddLine:
    params: Params
    line: Line
    on_after: Callable[[], None]  # e.g., lambda: app.layers.redraw("lines")

    def do(self) -> None:
        self.params.lines.append(self.line)
        self.on_after()

    def undo(self) -> None:
        # pop last occurrence of this exact object (cheap path)
        if self.params.lines and self.params.lines[-1] is self.line:
            self.params.lines.pop()
        else:
            # fall back: remove by value once
            for i in range(len(self.params.lines) - 1, -1, -1):
                if self.params.lines[i] == self.line:
                    del self.params.lines[i]
                    break
        self.on_after()


@dataclass
class AddLabel:
    params: Params
    label: Label
    on_after: Callable[[], None]

    def do(self) -> None:
        self.params.labels.append(self.label)
        self.on_after()

    def undo(self) -> None:
        for i in range(len(self.params.labels) - 1, -1, -1):
            if self.params.labels[i] == self.label:
                del self.params.labels[i]
                break
        self.on_after()


@dataclass
class AddIcon:
    params: Params
    icon: Icon
    on_after: Callable[[], None]

    def do(self) -> None:
        self.params.icons.append(self.icon)
        self.on_after()

    def undo(self) -> None:
        for i in range(len(self.params.icons) - 1, -1, -1):
            if self.params.icons[i] == self.icon:
                del self.params.icons[i]
                break
        self.on_after()


@dataclass
class MoveLabel:
    params: Params
    index: int
    old_xy: tuple[int, int]
    new_xy: tuple[int, int]
    on_after: Callable[[], None]

    def do(self) -> None:
        lab = self.params.labels[self.index]
        self.params.labels[self.index] = Label(
            x=self.new_xy[0], y=self.new_xy[1], text=lab.text, col=lab.col, anchor=lab.anchor, size=lab.size
        )
        self.on_after()

    def undo(self) -> None:
        lab = self.params.labels[self.index]
        self.params.labels[self.index] = Label(
            x=self.old_xy[0], y=self.old_xy[1], text=lab.text, col=lab.col, anchor=lab.anchor, size=lab.size
        )
        self.on_after()


@dataclass
class MoveIcon:
    params: Params
    index: int
    old_xy: tuple[int, int]
    new_xy: tuple[int, int]
    on_after: Callable[[], None]

    def do(self) -> None:
        ico = self.params.icons[self.index]
        self.params.icons[self.index] = Icon(
            x=self.new_xy[0], y=self.new_xy[1], name=ico.name, col=ico.col, size=ico.size, rotation=ico.rotation
        )
        self.on_after()

    def undo(self) -> None:
        ico = self.params.icons[self.index]
        self.params.icons[self.index] = Icon(
            x=self.old_xy[0], y=self.old_xy[1], name=ico.name, col=ico.col, size=ico.size, rotation=ico.rotation
        )
        self.on_after()
