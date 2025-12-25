"""Command stack and undoable operations."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal, Protocol

from models.geo import Iconlike, Label, Line, Point
from models.params import Params


# ---- Command infra ----
class Command(Protocol):
    """Protocol for undoable commands."""

    def do(self) -> None: ...
    def undo(self) -> None: ...


class Command_Stack:
    """Simple undo/redo stack."""

    def __init__(self) -> None:
        self._undo: list[Command] = []
        self._redo: list[Command] = []

    def push_and_do(self, cmd: Command) -> None:
        """Execute a command and push it onto the undo stack.

        Args;
            cmd: The command to execute.
        """
        cmd.do()
        self._undo.append(cmd)
        self._redo.clear()

    def undo(self) -> None:
        """Undo the last command."""
        if not self._undo:
            return
        cmd = self._undo.pop()
        cmd.undo()
        self._redo.append(cmd)

    def redo(self) -> None:
        """Redo the last undone command."""
        if not self._redo:
            return
        cmd = self._redo.pop()
        cmd.do()
        self._undo.append(cmd)


# ---- Concrete commands ----
@dataclass
class Multi:
    """Composite command that runs multiple commands."""

    items: list[Command]
    on_after: Callable[[], None] | None = None

    def do(self) -> None:
        """Execute all commands."""
        for c in self.items:
            c.do()
        if self.on_after:
            self.on_after()

    def undo(self) -> None:
        """Undo all commands in reverse order."""
        for c in reversed(self.items):
            c.undo()
        if self.on_after:
            self.on_after()


@dataclass
class Add_Line:
    """Command to add a line."""

    params: Params
    line: Line
    on_after: Callable[[], None]
    _index: int | None = None

    def do(self) -> None:
        """Execute the add-line command."""
        if (self.line.a.x, self.line.a.y) == (self.line.b.x, self.line.b.y):
            return
        self.params.lines.append(self.line)
        self._index = len(self.params.lines) - 1
        self.on_after()

    def undo(self) -> None:
        """Undo the add-line command."""
        if self._index is None:
            return
        if self._index is not None and 0 <= self._index < len(self.params.lines):
            # prefer surgical removal by the index we appended at
            if self.params.lines[self._index] is self.line or self.params.lines[self._index] == self.line:
                del self.params.lines[self._index]
                self.on_after()
                return
        # ultra-conservative fallback (should rarely run)
        for idx in range(len(self.params.lines) - 1, -1, -1):
            if self.params.lines[idx] == self.line:
                del self.params.lines[idx]
                break
        self.on_after()


@dataclass
class Add_Label:
    """Command to add a label."""

    params: Params
    label: Label
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the add-label command."""
        self.params.labels.append(self.label)
        self.on_after()

    def undo(self) -> None:
        """Undo the add-label command."""
        for idx in range(len(self.params.labels) - 1, -1, -1):
            if self.params.labels[idx] == self.label:
                del self.params.labels[idx]
                break
        self.on_after()


@dataclass
class Add_Icon:
    """Command to add an icon."""

    params: Params
    icon: Iconlike
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the add-icon command."""
        self.params.icons.append(self.icon)
        self.on_after()

    def undo(self) -> None:
        """Undo the add-icon command."""
        for idx in range(len(self.params.icons) - 1, -1, -1):
            if self.params.icons[idx] == self.icon:
                del self.params.icons[idx]
                break
        self.on_after()


@dataclass
class Move_Line_End:
    """Command to move a line endpoint."""

    params: Params
    index: int
    end: Literal["a", "b"]
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the line-end move command."""
        lin = self.params.lines[self.index]
        if self.end == "a":
            lin.a = self.new_point
        else:
            lin.b = self.new_point
        self.params.lines[self.index] = lin
        self.on_after()

    def undo(self) -> None:
        """Undo the line-end move command."""
        lin = self.params.lines[self.index]
        if self.end == "a":
            lin.a = self.old_point
        else:
            lin.b = self.old_point
        self.params.lines[self.index] = lin
        self.on_after()


@dataclass
class Move_Line:
    """Command to move a line."""

    params: Params
    index: int
    old_a: Point
    old_b: Point
    new_a: Point
    new_b: Point
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the line move command."""
        if 0 <= self.index < len(self.params.lines):
            self.params.lines[self.index] = self.params.lines[self.index].with_points(self.new_a, self.new_b)
            self.on_after()

    def undo(self) -> None:
        """Undo the line move command."""
        if 0 <= self.index < len(self.params.lines):
            self.params.lines[self.index] = self.params.lines[self.index].with_points(self.old_a, self.old_b)
            self.on_after()


@dataclass
class Move_Label:
    """Command to move a label."""

    params: Params
    index: int
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the label move command."""
        lab = self.params.labels[self.index]
        lab.p = self.new_point
        self.params.labels[self.index] = lab
        self.on_after()

    def undo(self) -> None:
        """Undo the label move command."""
        lab = self.params.labels[self.index]
        lab.p = self.old_point
        self.params.labels[self.index] = lab
        self.on_after()


@dataclass
class Move_Icon:
    """Command to move an icon."""

    params: Params
    index: int
    old_point: Point
    new_point: Point
    on_after: Callable[[], None]

    def do(self) -> None:
        """Execute the icon move command."""
        ico = self.params.icons[self.index]
        ico.p = self.new_point
        self.params.icons[self.index] = ico
        self.on_after()

    def undo(self) -> None:
        """Undo the icon move command."""
        ico = self.params.icons[self.index]
        ico.p = self.old_point
        self.params.icons[self.index] = ico
        self.on_after()


@dataclass
class Delete_Line:
    """Command to delete a line."""

    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Line | None = None

    def do(self) -> None:
        """Execute the delete-line command."""
        if 0 <= self.index < len(self.params.lines):
            self._removed = self.params.lines.pop(self.index)
            self.on_after()

    def undo(self) -> None:
        """Undo the delete-line command."""
        if self._removed is not None:
            self.params.lines.insert(self.index, self._removed)
            self.on_after()


@dataclass
class Delete_Label:
    """Command to delete a label."""

    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Label | None = None

    def do(self) -> None:
        """Execute the delete-label command."""
        if 0 <= self.index < len(self.params.labels):
            self._removed = self.params.labels.pop(self.index)
            self.on_after()

    def undo(self) -> None:
        """Undo the delete-label command."""
        if self._removed is not None:
            self.params.labels.insert(self.index, self._removed)
            self.on_after()


@dataclass
class Delete_Icon:
    """Command to delete an icon."""

    params: Params
    index: int
    on_after: Callable[[], None]
    _removed: Iconlike | None = None

    def do(self) -> None:
        """Execute the delete-icon command."""
        if 0 <= self.index < len(self.params.icons):
            self._removed = self.params.icons.pop(self.index)
            self.on_after()

    def undo(self) -> None:
        """Undo the delete-icon command."""
        if self._removed is not None:
            self.params.icons.insert(self.index, self._removed)
            self.on_after()
