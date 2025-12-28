"""Selection tool behaviour for the Qt frontend."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from PySide6 import QtCore

from core.commands import MoveIcon, MoveLabel, MoveLine, MoveLineEnd, Multi
from core.layers import HitKind
from models.geo import Point
from qt.hit_test import hit_test
from qt.input import MotionEvent
from qt.scene_data import DATA_IDX, DATA_KIND
from qt.tools.base import DragAction, ToolBase, ToolName
from qt.tools.draw import DrawTool

if TYPE_CHECKING:
    from qt.app import QtApp

Z_PREVIEW = 60


@dataclass(slots=True)
class DragLineEndpoint(DragAction):
    """Drag action for line endpoints."""

    idx: int
    which: str
    start_other: Point
    start: Point

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update previews for an endpoint drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        ln = app.params.lines[self.idx]
        use_snap = ln.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not use_snap)
        q = DrawTool._maybe_cardinal(app, self.start_other, p, invert=mods.ctrl)
        a, b = (q, self.start_other) if self.which == "a" else (self.start_other, q)

        app.clear_preview()
        item = app.renderer.add_line(ln.with_points(a, b), z=Z_PREVIEW, tag=False)
        app.add_preview_item(item)

        app.selection.update_line_handles(
            self.idx,
            QtCore.QPointF(a.x, a.y),
            QtCore.QPointF(b.x, b.y),
        )

        rect = item.sceneBoundingRect()
        app.selection.set_outline_bbox(rect.left(), rect.top(), rect.right(), rect.bottom())

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Commit an endpoint drag to the model.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        app.clear_preview()
        mods = evt.mods
        ln = app.params.lines[self.idx]
        use_snap = ln.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not use_snap)
        p = DrawTool._maybe_cardinal(app, self.start_other, p, invert=mods.ctrl)
        ln.snap = use_snap

        app.cmd.push_and_do(
            MoveLineEnd(
                app.params,
                self.idx,
                "a" if self.which == "a" else "b",
                old_point=self.start,
                new_point=p,
                on_after=app.redraw,
            )
        )
        app.selection.refresh()
        app._set_selected(HitKind.line, self.idx)
        app.mark_dirty()

    def cancel(self, app: QtApp) -> None:
        """Cancel an endpoint drag.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        app.selection.refresh()


@dataclass(slots=True)
class DragLine(DragAction):
    """Drag action for moving lines."""

    idx: int
    start_mouse: Point
    start_a: Point
    start_b: Point

    def _delta(self, app: QtApp, evt: MotionEvent) -> tuple[int, int, bool]:
        mods = evt.mods
        ln = app.params.lines[self.idx]
        use_snap = ln.snap
        if mods.alt:
            use_snap = not use_snap
        ignore_grid = not use_snap
        cur = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=ignore_grid)
        start = app.snap(self.start_mouse, ignore_grid=ignore_grid)
        return cur.x - start.x, cur.y - start.y, ignore_grid

    def _points(self, app: QtApp, evt: MotionEvent) -> tuple[Point, Point]:
        dx, dy, ignore_grid = self._delta(app, evt)
        a = app.snap(Point(x=self.start_a.x + dx, y=self.start_a.y + dy), ignore_grid=ignore_grid)
        b = app.snap(Point(x=self.start_b.x + dx, y=self.start_b.y + dy), ignore_grid=ignore_grid)
        return a, b

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update previews for a line drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        a, b = self._points(app, evt)
        ln = app.params.lines[self.idx]
        app.clear_preview()
        item = app.renderer.add_line(ln.with_points(a, b), z=Z_PREVIEW, tag=False)
        app.add_preview_item(item)

        app.selection.update_line_handles(
            self.idx,
            QtCore.QPointF(a.x, a.y),
            QtCore.QPointF(b.x, b.y),
        )

        rect = item.sceneBoundingRect()
        app.selection.set_outline_bbox(rect.left(), rect.top(), rect.right(), rect.bottom())

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Commit a line drag to the model.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        a, b = self._points(app, evt)
        app.clear_preview()
        mods = evt.mods
        ln = app.params.lines[self.idx]
        use_snap = ln.snap
        if mods.alt:
            use_snap = not use_snap
        ln.snap = use_snap
        app.cmd.push_and_do(
            MoveLine(
                app.params,
                self.idx,
                old_a=self.start_a,
                old_b=self.start_b,
                new_a=a,
                new_b=b,
                on_after=app.redraw,
            )
        )
        app.selection.refresh()
        app._set_selected(HitKind.line, self.idx)
        app.mark_dirty()

    def cancel(self, app: QtApp) -> None:
        """Cancel a line drag.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        app.selection.refresh()


@dataclass(slots=True)
class DragLabel(DragAction):
    """Drag action for moving a label."""

    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update previews for a label drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        lab = app.params.labels[self.idx]
        use_snap = lab.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=not use_snap,
        )
        lb = app.params.labels[self.idx]
        app.clear_preview()
        item = app.renderer.add_label(lb.with_point(p), z=Z_PREVIEW, tag=False)
        app.add_preview_item(item)

        rect = item.sceneBoundingRect()
        app.selection.set_outline_bbox(rect.left(), rect.top(), rect.right(), rect.bottom())

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Commit a label drag to the model.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        lab = app.params.labels[self.idx]
        use_snap = lab.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=not use_snap,
        )
        lab.snap = use_snap
        app.clear_preview()
        app.cmd.push_and_do(
            MoveLabel(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=app.redraw,
            )
        )
        app.selection.refresh()
        app._set_selected(HitKind.label, self.idx)
        app.mark_dirty()

    def cancel(self, app: QtApp) -> None:
        """Cancel a label drag.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        app.selection.refresh()


@dataclass(slots=True)
class DragIcon(DragAction):
    """Drag action for moving an icon."""

    idx: int
    start: Point
    offset_dx: int
    offset_dy: int

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update previews for an icon drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        ico = app.params.icons[self.idx]
        use_snap = ico.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=not use_snap,
        )
        ic = app.params.icons[self.idx]
        app.clear_preview()
        items = app.renderer.add_icon(ic.with_point(p), z=Z_PREVIEW, tag=False)
        app.add_preview_items(items)

        rect = app.preview_bbox()
        if rect is not None:
            app.selection.set_outline_bbox(rect.left(), rect.top(), rect.right(), rect.bottom())

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Commit an icon drag to the model.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        ico = app.params.icons[self.idx]
        use_snap = ico.snap
        if mods.alt:
            use_snap = not use_snap
        p = app.snap(
            Point(x=evt.x - self.offset_dx, y=evt.y - self.offset_dy),
            ignore_grid=not use_snap,
        )
        ico.snap = use_snap
        app.clear_preview()
        app.cmd.push_and_do(
            MoveIcon(
                app.params,
                self.idx,
                old_point=self.start,
                new_point=p,
                on_after=app.redraw,
            )
        )
        app.selection.refresh()
        app._set_selected(HitKind.icon, self.idx)
        app.mark_dirty()

    def cancel(self, app: QtApp) -> None:
        """Cancel an icon drag.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        app.selection.refresh()


@dataclass(slots=True)
class DragMarquee(DragAction):
    """Drag action for selection marquees."""

    a: Point
    add: bool = False
    base_snap: bool = True

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update the marquee selection preview.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        snap_to_grid = self.base_snap
        if evt.mods.alt:
            snap_to_grid = not snap_to_grid
        b = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not snap_to_grid)
        app.selection.update_marquee(QtCore.QPointF(self.a.x, self.a.y), QtCore.QPointF(b.x, b.y))

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Apply the marquee selection.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        snap_to_grid = self.base_snap
        if evt.mods.alt:
            snap_to_grid = not snap_to_grid
        b = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not snap_to_grid)
        x1, y1 = min(self.a.x, b.x), min(self.a.y, b.y)
        x2, y2 = max(self.a.x, b.x), max(self.a.y, b.y)

        rect = QtCore.QRectF(x1, y1, x2 - x1, y2 - y1)
        hits: list[tuple[HitKind, int]] = []
        seen: set[tuple[str, int]] = set()
        for item in app.scene.items(rect, QtCore.Qt.ItemSelectionMode.IntersectsItemShape):
            kind = item.data(DATA_KIND)
            idx = item.data(DATA_IDX)
            if kind is None or idx is None:
                parent = item.parentItem()
                if parent is not None:
                    kind = parent.data(DATA_KIND)
                    idx = parent.data(DATA_IDX)
            if kind is None or idx is None:
                continue
            key = (str(kind), int(idx))
            if key in seen:
                continue
            try:
                hk = HitKind(str(kind))
            except ValueError:
                continue
            seen.add(key)
            hits.append((hk, int(idx)))

        app.selection.clear_marquee()
        if not hits:
            return
        if self.add:
            app.select_merge(hits)
        else:
            app.select_set(hits)

    def cancel(self, app: QtApp) -> None:
        """Cancel the marquee selection.

        Args;
            app: The parent Qt app.
        """
        app.selection.clear_marquee()


@dataclass(slots=True)
class DragGroup(DragAction):
    """Drag many items together by delta."""

    items: list[tuple[HitKind, int]]
    start_mouse: Point
    labels: list[tuple[int, Point]]
    icons: list[tuple[int, Point]]
    lines: list[tuple[int, Point, Point]]

    def _delta(self, app: QtApp, evt: MotionEvent) -> tuple[int, int, bool]:
        mods = evt.mods
        return (evt.x - self.start_mouse.x, evt.y - self.start_mouse.y, mods.alt)

    def update(self, app: QtApp, evt: MotionEvent) -> None:
        """Update previews for a group drag.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        dx, dy, alt = self._delta(app, evt)
        app.clear_preview()

        for idx, p0 in self.labels:
            lb = app.params.labels[idx]
            use_snap = lb.snap
            if alt:
                use_snap = not use_snap
            p = Point(x=p0.x + dx, y=p0.y + dy)
            p = app.snap(p, ignore_grid=not use_snap)
            item = app.renderer.add_label(lb.with_point(p), z=Z_PREVIEW, tag=False)
            app.add_preview_item(item)
        for idx, p0 in self.icons:
            ic = app.params.icons[idx]
            use_snap = ic.snap
            if alt:
                use_snap = not use_snap
            p = Point(x=p0.x + dx, y=p0.y + dy)
            p = app.snap(p, ignore_grid=not use_snap)
            items = app.renderer.add_icon(ic.with_point(p), z=Z_PREVIEW, tag=False)
            app.add_preview_items(items)
        for idx, a0, b0 in self.lines:
            ln = app.params.lines[idx]
            use_snap = ln.snap
            if alt:
                use_snap = not use_snap
            ignore_grid = not use_snap
            a = app.snap(Point(x=a0.x + dx, y=a0.y + dy), ignore_grid=ignore_grid)
            b = app.snap(Point(x=b0.x + dx, y=b0.y + dy), ignore_grid=ignore_grid)
            item = app.renderer.add_line(ln.with_points(a, b), z=Z_PREVIEW, tag=False)
            app.add_preview_item(item)

        rect = app.preview_bbox()
        if rect is not None:
            app.selection.set_outline_bbox(rect.left(), rect.top(), rect.right(), rect.bottom())

    def commit(self, app: QtApp, evt: MotionEvent) -> None:
        """Commit a group drag to the model.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        dx, dy, alt = self._delta(app, evt)
        app.clear_preview()
        subs = []

        for idx, p0 in self.labels:
            lb = app.params.labels[idx]
            use_snap = lb.snap
            if alt:
                use_snap = not use_snap
            p = app.snap(Point(x=p0.x + dx, y=p0.y + dy), ignore_grid=not use_snap)
            lb.snap = use_snap
            subs.append(MoveLabel(app.params, idx, old_point=p0, new_point=p, on_after=app.redraw))

        for idx, p0 in self.icons:
            ic = app.params.icons[idx]
            use_snap = ic.snap
            if alt:
                use_snap = not use_snap
            p = app.snap(Point(x=p0.x + dx, y=p0.y + dy), ignore_grid=not use_snap)
            ic.snap = use_snap
            subs.append(MoveIcon(app.params, idx, old_point=p0, new_point=p, on_after=app.redraw))

        for idx, a0, b0 in self.lines:
            ln = app.params.lines[idx]
            use_snap = ln.snap
            if alt:
                use_snap = not use_snap
            a = app.snap(Point(x=a0.x + dx, y=a0.y + dy), ignore_grid=not use_snap)
            b = app.snap(Point(x=b0.x + dx, y=b0.y + dy), ignore_grid=not use_snap)
            ln.snap = use_snap
            subs.append(MoveLine(app.params, idx, old_a=ln.a, old_b=ln.b, new_a=a, new_b=b, on_after=app.redraw))

        app.cmd.push_and_do(Multi(subs))
        app.selection.refresh()
        app.mark_dirty()

    def cancel(self, app: QtApp) -> None:
        """Cancel a group drag.

        Args;
            app: The parent Qt app.
        """
        app.clear_preview()
        app.selection.refresh()


class SelectTool(ToolBase):
    """Tool for selection and dragging."""

    name: ToolName = ToolName.select
    cursor = QtCore.Qt.CursorShape.ArrowCursor
    tool_hints: str = "Ctrl: Toggle / Add-Marquee  |  Alt: Invert Grid Snap"

    def __init__(self) -> None:
        """Create the select tool state."""
        self._drag: DragAction | None = None

    @staticmethod
    def _marquee_base_snap(app: QtApp) -> bool:
        if app.multi_sel:
            items = app.multi_sel
        else:
            items = [(HitKind.label, idx) for idx in range(len(app.params.labels))]
            items.extend((HitKind.icon, idx) for idx in range(len(app.params.icons)))
            items.extend((HitKind.line, idx) for idx in range(len(app.params.lines)))
        snap_flags: list[bool] = []
        for kind, idx in items:
            if kind == HitKind.label and 0 <= idx < len(app.params.labels):
                snap_flags.append(app.params.labels[idx].snap)
            elif kind == HitKind.icon and 0 <= idx < len(app.params.icons):
                snap_flags.append(app.params.icons[idx].snap)
            elif kind == HitKind.line and 0 <= idx < len(app.params.lines):
                snap_flags.append(app.params.lines[idx].snap)
        if not snap_flags:
            return True
        return any(snap_flags)

    def on_press(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle press events for selection.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        mods = evt.mods
        hit = hit_test(app.scene, evt.x, evt.y)

        if not hit:
            if not mods.ctrl:
                app.select_clear()
            base_snap = self._marquee_base_snap(app)
            snap_to_grid = base_snap
            if mods.alt:
                snap_to_grid = not snap_to_grid
            start = app.snap(Point(x=evt.x, y=evt.y), ignore_grid=not snap_to_grid)
            self._drag = DragMarquee(a=start, add=mods.ctrl, base_snap=base_snap)
            app.selection.show_marquee(QtCore.QPointF(self._drag.a.x, self._drag.a.y))
            return

        if hit.kind == HitKind.line and hit.point and hit.tag_idx is not None:
            ln = app.params.lines[hit.tag_idx]
            other = ln.b if hit.point == "a" else ln.a
            start = ln.a if hit.point == "a" else ln.b
            self._drag = DragLineEndpoint(idx=hit.tag_idx, which=hit.point, start_other=other, start=start)
            return

        if mods.ctrl and hit.tag_idx is not None:
            if app.is_selected(hit.kind, hit.tag_idx):
                app.select_remove(hit.kind, hit.tag_idx)
            else:
                app.select_add(hit.kind, hit.tag_idx, make_primary=False)
            return

        if hit.tag_idx is not None and app.is_selected(hit.kind, hit.tag_idx) and len(app.multi_sel) > 1:
            labels = [(i, app.params.labels[i].p) for k, i in app.multi_sel if k == HitKind.label]
            icons = [(i, app.params.icons[i].p) for k, i in app.multi_sel if k == HitKind.icon]
            lines = [(i, app.params.lines[i].a, app.params.lines[i].b) for k, i in app.multi_sel if k == HitKind.line]
            self._drag = DragGroup(
                items=list(app.multi_sel),
                start_mouse=Point(x=evt.x, y=evt.y),
                labels=labels,
                icons=icons,
                lines=lines,
            )
            return

        app.select_set([(hit.kind, hit.tag_idx if hit.tag_idx is not None else -1)])

        if hit.kind == HitKind.line and hit.tag_idx is not None:
            ln = app.params.lines[hit.tag_idx]
            self._drag = DragLine(
                idx=hit.tag_idx,
                start_mouse=Point(x=evt.x, y=evt.y),
                start_a=ln.a,
                start_b=ln.b,
            )
            return

        if hit.kind == HitKind.label and hit.tag_idx is not None:
            lb = app.params.labels[hit.tag_idx]
            self._drag = DragLabel(idx=hit.tag_idx, start=lb.p, offset_dx=evt.x - lb.p.x, offset_dy=evt.y - lb.p.y)
            return

        if hit.kind == HitKind.icon and hit.tag_idx is not None:
            ic = app.params.icons[hit.tag_idx]
            self._drag = DragIcon(idx=hit.tag_idx, start=ic.p, offset_dx=evt.x - ic.p.x, offset_dy=evt.y - ic.p.y)
            return

        self._drag = None

    def on_motion(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle motion events for selection.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        if self._drag:
            self._drag.update(app, evt)

    def on_release(self, app: QtApp, evt: MotionEvent) -> None:
        """Handle release events for selection.

        Args;
            app: The parent Qt app.
            evt: The motion event.
        """
        if self._drag:
            self._drag.commit(app, evt)
            self._drag = None

    def on_cancel(self, app: QtApp) -> None:
        """Handle selection cancellation.

        Args;
            app: The parent Qt app.
        """
        if self._drag:
            self._drag.cancel(app)
            self._drag = None
