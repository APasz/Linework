"""Tagging helpers shared across rendering layers."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


class TagNS(StrEnum):
    """Namespace prefixes for canvas tags."""

    layer = "layer"
    ants = "ants"
    hit = "hit"
    handle = "handle"


class HitKind(StrEnum):
    """Kinds of hittable items."""

    line = "line"
    label = "label"
    icon = "icon"


@dataclass
class Hit:
    """Hit-test result for scene items."""

    kind: HitKind
    tag_idx: int | None = None
    point: str | None = None


class LayerType(StrEnum):
    """Canvas layer identifiers."""

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
        """Return True if this layer is protected from clearing."""
        return self in {LayerType.grid}

    def tagns(self) -> TagNS:
        """Return the namespace for this layer."""
        if self == LayerType.handle:
            return TagNS.handle
        if self in {LayerType.lines, LayerType.labels, LayerType.icons}:
            return TagNS.hit
        if self in {LayerType.preview, LayerType.marquee, LayerType.outline, LayerType.selection}:
            return TagNS.ants
        return TagNS.layer


@dataclass(frozen=True)
class Tag:
    """Structured tag helper for canvas items."""

    ns: TagNS
    kind: LayerType | HitKind | None = None
    idx: int | None = None
    meta: str | None = None

    # --- factories ---
    @staticmethod
    def layer(layer: LayerType) -> "Tag":
        """Create a layer tag.

        Args;
            layer: The layer type.

        Returns;
            The tag.
        """
        return Tag(TagNS.layer, layer)

    @staticmethod
    def hit(kind: HitKind, idx: int) -> "Tag":
        """Create a hit tag.

        Args;
            kind: The hit kind.
            idx: The item index.

        Returns;
            The tag.
        """
        return Tag(TagNS.hit, kind, idx)

    @staticmethod
    def handle(which: str, idx: int, *, parent: HitKind = HitKind.line) -> "Tag":
        """Create a handle tag.

        Args;
            which: The handle identifier.
            idx: The item index.
            parent: The parent hit kind.

        Returns;
            The tag.
        """
        return Tag(TagNS.handle, parent, idx, which)

    # --- emission ---
    def to_strings(self) -> tuple[str, ...]:
        """Return string tags for this Tag.

        Returns;
            The tag strings.
        """
        ns = self.ns
        k = self.kind
        i = self.idx
        m = self.meta

        if ns is TagNS.layer and isinstance(k, LayerType):
            return (k.value, f"{TagNS.layer.value}:{k.value}")

        if ns is TagNS.hit and isinstance(k, HitKind) and i is not None:
            return (f"{k.value}:{i}",)

        if ns is TagNS.handle and isinstance(k, HitKind) and i is not None:
            out = [
                TagNS.handle.value,
                LayerType.selection.value,
                f"{TagNS.handle.value}:{m}" if m else f"{TagNS.handle.value}:unknown",
                f"{k.value}:{i}",
            ]
            return tuple(out)

        if ns is TagNS.ants and isinstance(k, LayerType):
            return (
                f"{TagNS.ants.value}:{k.value}",
                f"{TagNS.ants.value}:{LayerType.selection.value}",
                k.value,
                TagNS.ants.value,
            )

        return ()

    def __hash__(self) -> int:
        return hash((self.ns, self.kind, self.idx, self.meta))


def tags(*parts: Iterable[str | Tag] | Tag) -> tuple[str, ...]:
    """Combine tags into a deduplicated tuple.

    Args;
        *parts: Tag parts, strings, or iterables.

    Returns;
        The unique tag strings.
    """
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


PLAIN_LAYERS = {lt.value: lt for lt in LayerType}
HIT_KINDS = {hk.value: hk for hk in HitKind}


def tag_parse(string: str) -> Tag | None:
    """Parse a single tag string.

    Args;
        string: The tag string.

    Returns;
        The parsed Tag, or None.
    """
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
    """Parse multiple tag strings.

    Args;
        strings: Tag strings.

    Returns;
        Parsed tags.
    """
    tags = []
    for string in strings:
        if tag := tag_parse(string):
            tags.append(tag)
    return tags
