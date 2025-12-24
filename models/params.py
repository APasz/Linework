from pathlib import Path

from pydantic import Field

from models.geo import Icon_Source, Iconlike, Label, Line
from models.styling import Anchor, Colour, Colours, LineStyle, Model

SCHEMA_VERSION = 1
PROFILE_EXCLUDE: set[str] = {"lines", "labels", "icons", "recent_icons"}


class Params(Model):
    width: int = 1200
    height: int = 600
    grid_colour: Colour = Colours.gray
    brush_colour: Colour = Colours.black
    bg_colour: Colour = Colours.white
    icon_colour: Colour = Colours.red
    label_colour: Colour = Colours.black
    custom_palette: list[Colour | None] = Colours.custom_palette  # Shared across all Params instances
    brush_width: int = 10
    line_style: LineStyle = LineStyle.SOLID
    line_dash_offset: int = 0
    grid_size: int = 40
    grid_visible: bool = True
    drag_to_draw: bool = True
    cardinal_snap: bool = True
    output_file: Path = Path("output.webp")
    default_icon: Icon_Source = Field(default_factory=lambda: Icon_Source.builtin("signal"))
    label_size: int = 12
    label_rotation: int = 37
    label_anchor: Anchor = Anchor.W
    label_snap: bool = True
    icon_size: int = 48
    picture_size: int = 192
    icon_rotation: int = 0
    icon_anchor: Anchor = Anchor.C
    icon_snap: bool = True
    lines: list[Line] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    icons: list[Iconlike] = Field(default_factory=list)
    recent_icons: list[Icon_Source] = Field(default_factory=list)
    version: int = Field(default=SCHEMA_VERSION)

    def profile_dict(self) -> dict:
        return self.model_dump(exclude=PROFILE_EXCLUDE, exclude_none=True)

    def profile_dump_json(self, *, indent: int = 4) -> str:
        return self.model_dump_json(indent=indent, exclude=PROFILE_EXCLUDE, exclude_none=True)

    def apply_profile(self, profile: "Params", *, inplace_palette: bool = False) -> None:
        for name in self.model_fields:
            if name in PROFILE_EXCLUDE:
                continue
            if name == "custom_palette":
                if inplace_palette and hasattr(self, "custom_palette"):
                    if len(self.custom_palette) == len(profile.custom_palette):
                        self.custom_palette[:] = profile.custom_palette
                    else:
                        self.custom_palette = list(profile.custom_palette)
                else:
                    self.custom_palette = list(profile.custom_palette)
                continue
            setattr(self, name, getattr(profile, name))
