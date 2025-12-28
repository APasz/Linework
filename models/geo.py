"""Geometry models for Linework."""

import math
from enum import StrEnum
from pathlib import Path
from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from models.assets import Formats, IconName, probe_wh
from models.styling import Anchor, CapStyle, Colour, LineStyle, Model, scaled_pattern


class Point(Model):
    """2D point with an optional cap style."""

    x: int
    y: int
    capstyle: CapStyle = CapStyle.ROUND

    def clamped_to(self, w: int, h: int, grid: int = 0) -> "Point": ...


class Line(Model):
    """Line segment with styling."""

    a: Point
    b: Point
    col: Colour
    width: int
    capstyle: CapStyle = CapStyle.ROUND
    style: LineStyle = LineStyle.SOLID
    dash_offset: int = 0
    snap: bool = True

    def with_points(self, a: Point, b: Point) -> Self:
        """Return a copy with new endpoints.

        Args;
            a: Start point.
            b: End point.

        Returns;
            The updated line.
        """
        return self.model_copy(update={"a": a, "b": b})

    def with_xy(self, x1: int, y1: int, x2: int, y2: int) -> Self:
        """Return a copy with new endpoints by coordinates.

        Args;
            x1: Start x.
            y1: Start y.
            x2: End x.
            y2: End y.

        Returns;
            The updated line.
        """
        return self.model_copy(update={"a": Point(x=x1, y=y1), "b": Point(x=x2, y=y2)})

    def unit(
        self,
        x1: float | None = None,
        y1: float | None = None,
        x2: float | None = None,
        y2: float | None = None,
    ) -> tuple[float, float, float]:
        """Return the unit direction vector and length.

        Args;
            x1: Optional override start x.
            y1: Optional override start y.
            x2: Optional override end x.
            y2: Optional override end y.

        Returns;
            The unit vector (x, y) and length.
        """
        ax = x1 if x1 is not None else self.a.x
        ay = y1 if y1 is not None else self.a.y
        bx = x2 if x2 is not None else self.b.x
        by = y2 if y2 is not None else self.b.y
        dx, dy = (bx - ax), (by - ay)
        L = math.hypot(dx, dy)
        if L <= 0:
            return 0.0, 0.0, 0.0
        return dx / L, dy / L, L

    def scaled_pattern(self, *, style: LineStyle | None = None, width: int | None = None) -> tuple[int, ...]:
        """Return a scaled dash pattern for this line.

        Args;
            style: Optional override style.
            width: Optional override width.

        Returns;
            The scaled dash pattern.
        """
        return scaled_pattern(style or self.style, width or self.width)


class Label(Model):
    """Text label anchored at a point."""

    p: Point
    text: str
    col: Colour
    anchor: Anchor = Anchor.W
    size: int = 12
    rotation: int = 37  # Intentional
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        """Return a copy with a new point.

        Args;
            p: The new point.

        Returns;
            The updated label.
        """
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        """Return a copy with a new point by coordinates.

        Args;
            x: The new x coordinate.
            y: The new y coordinate.

        Returns;
            The updated label.
        """
        return self.model_copy(update={"p": Point(x=x, y=y)})


class IconType(StrEnum):
    """Icon source kind."""

    builtin = "builtin"
    picture = "picture"


class IconSource(Model):
    """Reference to a builtin or picture icon."""

    kind: IconType
    name: IconName | None = None
    src: Path | None = None

    @model_validator(mode="after")
    def _check(self) -> "IconSource":
        if self.kind is IconType.builtin:
            if self.name is None or self.src is not None:
                raise ValueError("builtin IconSource requires name and forbids src")
        else:
            if self.src is None or self.name is not None:
                raise ValueError("picture IconSource requires src and forbids name")
        return self

    @classmethod
    def builtin(cls, name: IconName | str) -> "IconSource":
        """Create a builtin icon source.

        Args;
            name: The builtin icon name.

        Returns;
            The icon source.
        """
        return cls(kind=IconType.builtin, name=IconName(name))

    @classmethod
    def picture(cls, src: Path | str) -> "IconSource":
        """Create a picture icon source.

        Args;
            src: The image path.

        Returns;
            The icon source.
        """
        return cls(kind=IconType.picture, src=Path(src))

    @classmethod
    def coerce(cls, x: "IconSource | Iconlike | Path | str | IconName") -> "IconSource":
        """Coerce an input into an IconSource.

        Args;
            x: The input value.

        Returns;
            The icon source.
        """
        if isinstance(x, IconSource):
            return x
        if isinstance(x, IconName):
            return cls.builtin(x)
        if isinstance(x, str):
            # try value→enum first, else assume file path
            try:
                return cls.builtin(IconName(x))
            except ValueError:
                return cls.picture(x)
        if isinstance(x, Path):
            return cls.picture(x)
        if isinstance(x, BuiltinIcon):
            return cls.builtin(x.name)
        if isinstance(x, PictureIcon):
            return cls.picture(x.src)
        raise TypeError(f"Cannot coerce {type(x)} to IconSource")


class BaseIcon(Model):
    """Base class for icons."""

    p: Point
    col: Colour
    anchor: Anchor = Anchor.C
    size: int = 48
    rotation: int = 0
    snap: bool = True

    def with_point(self, p: Point) -> Self:
        """Return a copy with a new point.

        Args;
            p: The new point.

        Returns;
            The updated icon.
        """
        return self.model_copy(update={"p": p})

    def with_xy(self, x: int, y: int) -> Self:
        """Return a copy with a new point by coordinates.

        Args;
            x: The new x coordinate.
            y: The new y coordinate.

        Returns;
            The updated icon.
        """
        return self.model_copy(update={"p": Point(x=x, y=y)})

    def bbox_wh(self) -> tuple[int, int]:
        """Return the unrotated bounding box size.

        Returns;
            The width and height.
        """
        raise NotImplementedError


class BuiltinIcon(BaseIcon):
    """Builtin icon definition."""

    kind: Literal["builtin"] = "builtin"
    name: IconName

    def bbox_wh(self) -> tuple[int, int]:
        """Return the unrotated bounding box size.

        Returns;
            The width and height.
        """
        s = self.size
        return (s, s)


class PictureIcon(BaseIcon):
    """Image-based icon definition."""

    kind: Literal["picture"] = "picture"
    src: Path
    size: int = 192
    format: Formats | None = None
    preserve_aspect: bool = True

    def bbox_wh(self) -> tuple[int, int]:
        """Return the unrotated bounding box size.

        Returns;
            The width and height.
        """
        # tiny helper (see below)
        w, h = probe_wh(self.src, self.format)
        if w <= 0 or h <= 0:
            return (self.size, self.size)
        if self.preserve_aspect:
            s = self.size / max(w, h)
            return (max(1, round(w * s)), max(1, round(h * s)))
        return (self.size, self.size)


Iconlike = Annotated[BuiltinIcon | PictureIcon, Field(discriminator="kind")]
