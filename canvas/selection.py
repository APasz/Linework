# selection.py
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from canvas.layers import Hit_Kind, Layer_Name
from models.geo import CanvasLW, Point
from models.params import Params
from models.styling import Colours

if TYPE_CHECKING:
    from controllers.app import App

HANDLE_R = 5
OUTLINE_COLOUR = Colours.sys.sky
HANDLE_FILL = Colours.white
HANDLE_OUTLINE = Colours.sys.ocean
MARQUEE_DASH = (2, 10)


@dataclass(slots=True)
class _SelIds:
    outline: int | None = None
    hilite: int | None = None
    handle_a: int | None = None
    handle_b: int | None = None
    marquee: int | None = None


class SelectionOverlay:
    def __init__(self, app: App) -> None:
        self.app = app
        self.canvas: CanvasLW = app.canvas
        self.ids = _SelIds()
        self.kind: Hit_Kind = Hit_Kind.miss
        self.idx: int | None = None

    # ---------- public API used by App / Select_Tool ----------

    def show(self, kind: Hit_Kind, idx: int) -> None:
        self.kind, self.idx = kind, idx
        self.clear(keep_marquee=True)

        if kind == Hit_Kind.miss or idx is None:
            return

        tag = self._tag(kind, idx)
        bbox = self._bbox_for_tag(tag)

        if not bbox:
            bbox = self._bbox_from_model(kind, idx)

        if not bbox:
            return

        x1, y1, x2, y2 = bbox
        self.ids.outline = self._create_rect(x1, y1, x2, y2, dash=(3, 6))
        self.canvas.itemconfigure(self.ids.outline, outline=OUTLINE_COLOUR.hex, width=1)

        if kind == Hit_Kind.line:
            a, b = self._line_endpoints_from_canvas_or_model(idx, tag)
            if a and b:
                self.ids.hilite = self._create_line(a.x, a.y, b.x, b.y, width=2)
                self.canvas.itemconfigure(self.ids.hilite, fill=OUTLINE_COLOUR.hex)
                self.ids.handle_a = self._create_handle(a.x, a.y, which="a", idx=idx)
                self.ids.handle_b = self._create_handle(b.x, b.y, which="b", idx=idx)
        else:
            cx = (x1 + x2) / 2
            cy = (y1 + y2) / 2
            self.ids.handle_a = self._create_handle(cx, cy)

        self.canvas.tag_raise_l(Layer_Name.selection)

    def clear(self, keep_marquee: bool = False) -> None:
        try:
            for name in ("outline", "hilite", "handle_a", "handle_b"):
                iid = getattr(self.ids, name)
                if iid and self.canvas.type(iid):
                    self.canvas.delete(iid)
                    setattr(self.ids, name, None)

            if not keep_marquee and self.ids.marquee and self.canvas.type(self.ids.marquee):
                self.canvas.delete(self.ids.marquee)
                self.ids.marquee = None
        except Exception as xcp:
            print(f"SelectionOverlay.clear;\n{xcp}")

    def update_bbox(self) -> None:
        if self.kind and self.idx is not None and self.kind != Hit_Kind.miss:
            self.show(self.kind, self.idx)

    def update_line_handles(self, idx: int, a: Point, b: Point) -> None:
        try:
            if self.kind != Hit_Kind.line or self.idx != idx:
                return
            if self.ids.handle_a and self.canvas.type(self.ids.handle_a):
                self._move_handle(self.ids.handle_a, a.x, a.y)
            if self.ids.handle_b and self.canvas.type(self.ids.handle_b):
                self._move_handle(self.ids.handle_b, b.x, b.y)
            if self.ids.hilite and self.canvas.type(self.ids.hilite):
                self.canvas.coords(self.ids.hilite, a.x, a.y, b.x, b.y)
        except Exception as xcp:
            print(f"SelectionOverlay.update_line_handles;\n{xcp}")

    # ----- marquee helpers (for Select_Tool to manage drag-select) -----

    def show_marquee(self, a: Point) -> None:
        try:
            if self.ids.marquee and self.canvas.type(self.ids.marquee):
                self.canvas.delete(self.ids.marquee)
            self.ids.marquee = self._create_rect(a.x, a.y, a.x, a.y, dash=MARQUEE_DASH)
            self.canvas.itemconfigure(self.ids.marquee, outline=OUTLINE_COLOUR.hex, width=1)
        except Exception as xcp:
            print(f"SelectionOverlay.show_marquee;\n{xcp}")

    def update_marquee(self, a: Point, b: Point) -> None:
        try:
            if not self.ids.marquee or not self.canvas.type(self.ids.marquee):
                self.show_marquee(a)
            self.canvas.coords(self.ids.marquee or 0, a.x, a.y, b.x, b.y)
        except Exception as xcp:
            print(f"SelectionOverlay.update_marquee;\n{xcp}")

    def clear_marquee(self) -> None:
        try:
            if self.ids.marquee and self.canvas.type(self.ids.marquee):
                self.canvas.delete(self.ids.marquee)
            self.ids.marquee = None
        except Exception as xcp:
            print(f"SelectionOverlay.clear_marquee;\n{xcp}")

    # ---------- internals ----------

    def _tag(self, kind: Hit_Kind, idx: int) -> str:
        return f"{kind.value}:{idx}"

    def _bbox_for_tag(self, tag: str) -> tuple[float, float, float, float] | None:
        try:
            bb = self.canvas.bbox(tag)
        except Exception:
            bb = None
        if bb and all(v is not None for v in bb):
            x1, y1, x2, y2 = bb
            return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
        return None

    def _bbox_from_model(self, kind: Hit_Kind, idx: int) -> tuple[float, float, float, float] | None:
        p: Params = self.app.params
        try:
            if kind == Hit_Kind.line:
                ln = p.lines[idx]
                x1, y1, x2, y2 = ln.a.x, ln.a.y, ln.b.x, ln.b.y
                return (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2))
            if kind == Hit_Kind.label:
                lb = p.labels[idx]
                return (lb.p.x - 4, lb.p.y - 4, lb.p.x + 4, lb.p.y + 4)
            if kind == Hit_Kind.icon:
                ic = p.icons[idx]
                s = getattr(ic, "size", 48)
                r = max(4, s * 0.6 / 2)  # approx icon glyph box
                return (ic.p.x - r, ic.p.y - r, ic.p.x + r, ic.p.y + r)
        except Exception:
            return None
        return None

    def _line_endpoints_from_canvas_or_model(self, idx: int, tag: str) -> tuple[Point | None, Point | None]:
        try:
            item_ids = list(self.canvas.find_withtag(tag))
        except Exception:
            item_ids = []
        try:
            for iid in item_ids:
                if self.canvas.type(iid) == "line":
                    coords = self.canvas.coords(iid)
                    if len(coords) >= 4:
                        return Point(x=int(coords[0]), y=int(coords[1])), Point(x=int(coords[2]), y=int(coords[3]))
        except Exception as xcp:
            print(f"SelectionOverlay._line_endpoints_from_canvas_or_model\n{xcp}")

        try:
            ln = self.app.params.lines[idx]
            return ln.a, ln.b
        except Exception:
            return None, None

    # ---------- canvas helpers that tag into the selection layer ----------

    def _create_line(self, x1: float, y1: float, x2: float, y2: float, **opts) -> int:
        tags = opts.pop("tags", ())
        return self.canvas.create_line(
            x1,
            y1,
            x2,
            y2,
            tags=(*tags, str(Layer_Name.selection), "selection"),
            **opts,
        )

    def _create_rect(self, x1: float, y1: float, x2: float, y2: float, **opts) -> int:
        tags = opts.pop("tags", ())
        return self.canvas.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            tags=(*tags, str(Layer_Name.selection), "selection"),
            fill="",
            **opts,
        )

    def _create_handle(self, cx: float, cy: float, which: str | None = None, idx: int | None = None) -> int:
        r = HANDLE_R
        tags = [str(Layer_Name.selection), "selection", "handle"]
        if which is not None and idx is not None:
            tags.append(f"handle:{which}:{idx}")
        return self.canvas.create_oval(
            cx - r,
            cy - r,
            cx + r,
            cy + r,
            tags=tuple(tags),
            outline=HANDLE_OUTLINE.hex,
            fill=HANDLE_FILL.hex,
            width=1,
        )

    def _move_handle(self, iid: int, cx: float, cy: float) -> None:
        r = HANDLE_R
        self.canvas.coords(iid, cx - r, cy - r, cx + r, cy + r)
