from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from canvas.painters import Painters
    from models.geo import CanvasLW


class TagNS(StrEnum):
    layer = "layer"
    ants = "ants"
    hit = "hit"
    handle = "handle"


class Hit_Kind(StrEnum):
    line = "line"
    label = "label"
    icon = "icon"


class Layer_Type(StrEnum):
    lines = "lines"
    labels = "labels"
    icons = "icons"
    grid = "grid"
    selection = "selection"
    preview = "preview"
    outline = "outline"
    marquee = "marquee"
    handle = TagNS.handle.value

    def is_protected(self) -> bool:
        return self in {Layer_Type.grid}

    def tagns(self) -> TagNS:
        if self == Layer_Type.handle:
            return TagNS.handle
        if self in {Layer_Type.lines, Layer_Type.labels, Layer_Type.icons}:
            return TagNS.hit
        if self in {Layer_Type.preview, Layer_Type.marquee, Layer_Type.outline, Layer_Type.selection}:
            return TagNS.ants
        return TagNS.layer


@dataclass(frozen=True)
class Tag:
    ns: TagNS
    kind: Layer_Type | Hit_Kind | None = None
    idx: int | None = None
    meta: str | None = None

    # --- factories ---
    @staticmethod
    def layer(layer: Layer_Type) -> "Tag":
        return Tag(TagNS.layer, layer)

    @staticmethod
    def hit(kind: Hit_Kind, idx: int) -> "Tag":
        return Tag(TagNS.hit, kind, idx)

    @staticmethod
    def handle(which: str, idx: int, *, parent: Hit_Kind = Hit_Kind.line) -> "Tag":
        return Tag(TagNS.handle, parent, idx, which)

    # --- emission ---
    def to_strings(self) -> tuple[str, ...]:
        ns = self.ns
        k = self.kind
        i = self.idx
        m = self.meta

        if ns is TagNS.layer and isinstance(k, Layer_Type):
            return (k.value, f"{TagNS.layer.value}:{k.value}")

        if ns is TagNS.hit and isinstance(k, Hit_Kind) and i is not None:
            return (f"{k.value}:{i}",)

        if ns is TagNS.handle and isinstance(k, Hit_Kind) and i is not None:
            out = [
                TagNS.handle.value,
                Layer_Type.selection.value,
                f"{TagNS.handle.value}:{m}" if m else f"{TagNS.handle.value}:unknown",
                f"{k.value}:{i}",
            ]
            return tuple(out)

        if ns is TagNS.ants and isinstance(k, Layer_Type):
            return (
                f"{TagNS.ants.value}:{k.value}",
                f"{TagNS.ants.value}:{Layer_Type.selection.value}",
                k.value,
                TagNS.ants.value,
            )

        return ()

    def __hash__(self) -> int:
        return hash((self.ns, self.kind, self.idx, self.meta))


def tags(*parts: Iterable[str | Tag] | Tag) -> tuple[str, ...]:
    out, seen = [], set()
    for p in parts:
        if isinstance(p, Tag):
            strings = p.to_strings()
        elif isinstance(p, str):
            strings = (p,)
        elif isinstance(p, Iterable):
            strings = tuple(x for x in p if isinstance(x, str))
        else:
            strings = ()
        for s in strings:
            if s not in seen:
                seen.add(s)
                out.append(s)
    return tuple(out)


PLAIN_LAYERS = {lt.value: lt for lt in Layer_Type}
HIT_KINDS = {hk.value: hk for hk in Hit_Kind}


def tag_parse(string: str) -> Tag | None:
    # layer:<name>
    if string.startswith(f"{TagNS.layer.value}:"):
        name = string.split(":", 1)[1]
        lt = PLAIN_LAYERS.get(name)
        return Tag.layer(lt) if lt else None
    # plain layer name for back-compat
    if string in PLAIN_LAYERS:
        return Tag.layer(PLAIN_LAYERS[string])
    # hit: "<kind>:<idx>"
    if ":" in string:
        k, v = string.split(":", 1)
        hk = HIT_KINDS.get(k)
        if hk is not None and v.isdigit():
            return Tag.hit(hk, int(v))
        # handle:<which>
        if k == TagNS.handle.value:
            which = v or "unknown"
            # kind/idx resolved at item level
            return Tag(TagNS.handle, None, None, which)
    # bare handle
    if string == TagNS.handle.value:
        return Tag(TagNS.handle, None, None, "unknown")
    return None


def tag_parse_multi(strings: Iterable[str]) -> list[Tag]:
    tags = []
    for string in strings:
        if tag := tag_parse(string):
            tags.append(tag)
    return tags


@dataclass
class Hit:
    kind: Hit_Kind
    tag_idx: int | None = None
    point: str | None = None


def test_hit(canvas, x, y):
    """Pick the nearest valid hit in a small window around (x, y).
    Ties prefer the topmost item by z-order among overlaps."""
    over = list(canvas.find_overlapping(x - 3, y - 3, x + 3, y + 3))
    best: Hit | None = None
    best_key: tuple[int, int] | None = None  # (dist2, -z_in_over)
    for z, iid in enumerate(over):  # z increases with stacking
        toks = tag_parse_multi(canvas.gettags(iid))
        hit = next((t for t in toks if t.ns is TagNS.hit and t.idx is not None), None)
        if not hit or not isinstance(hit.kind, Hit_Kind):
            continue
        which = next((t.meta for t in toks if t.ns is TagNS.handle and t.meta), None)
        bbox = canvas.bbox(iid)
        if not bbox:
            continue
        x1, y1, x2, y2 = bbox
        dx = 0 if x1 <= x <= x2 else min((x - x1) ** 2, (x - x2) ** 2)
        dy = 0 if y1 <= y <= y2 else min((y - y1) ** 2, (y - y2) ** 2)
        key = (dx + dy, -z)  # nearest, then true topmost
        if best_key is None or key < best_key:
            best_key = key
            best = Hit(kind=hit.kind, tag_idx=hit.idx, point=which)
    return best


class Layer_Manager:
    def __init__(self, canvas: CanvasLW, painters: Painters):
        self.canvas = canvas
        self.painters = painters
        self.canvas.tag_raise_l(Layer_Type.selection)

    def _enforce_z(self):
        self.canvas.tag_lower_l(Layer_Type.grid)
        self.canvas.tag_raise_l(Layer_Type.lines)
        self.canvas.tag_raise_l(Layer_Type.icons)
        self.canvas.tag_raise_l(Layer_Type.labels)
        self.canvas.tag_raise_l(Layer_Type.preview)
        self.canvas.tag_raise_l(Layer_Type.selection)
        self.canvas.tag_raise_l(Layer_Type.outline)
        self.canvas.tag_raise_l(Layer_Type.marquee)

    # --- clears ---
    def clear(self, layer: Layer_Type, force: bool = False):
        if not layer:
            return
        if layer.is_protected() and not force:
            return
        self.canvas.delete_lw(layer)

    def clear_many(self, layers: Iterable[Layer_Type]):
        for layer in layers:
            self.clear(layer)

    def clear_all(self):
        for layer in Layer_Type:
            self.clear(layer, force=True)
        known = {lt.value for lt in Layer_Type}
        for iid in self.canvas.find_all():
            tags = set(self.canvas.gettags(iid))
            if not tags.intersection(known):
                self.canvas.delete_lw(iid)

    def clear_preview(self):
        self.clear(Layer_Type.preview)

    # --- redraws ---
    def redraw(self, layer: Layer_Type, /, force: bool = False):
        if not layer:
            return
        self.clear(layer, force)
        self._paint(layer)
        self._enforce_z()

    def redraw_many(self, layers: Iterable[Layer_Type]):
        for layer in layers:
            self.redraw(layer)

    def redraw_all(self):
        self.clear_all()
        for layer in Layer_Type:
            self._paint(layer)
        self._enforce_z()

    # --- internals ---
    def _paint(self, layer: Layer_Type):
        if layer == Layer_Type.lines:
            self.painters.paint_lines()
        elif layer == Layer_Type.labels:
            self.painters.paint_labels()
        elif layer == Layer_Type.icons:
            self.painters.paint_icons()
        elif layer == Layer_Type.grid:
            self.painters.paint_grid()
        self._enforce_z()
