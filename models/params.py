from pathlib import Path

from pydantic import Field

from models.geo import Icon_Source, Iconlike, Label, Line
from models.styling import Colour, Colours, LineStyle, Model

SCHEMA_VERSION = 1


class Params(Model):
    width: int = 1200
    height: int = 600
    grid_colour: Colour = Colours.gray
    brush_colour: Colour = Colours.black
    bg_colour: Colour = Colours.white
    icon_colour: Colour = Colours.black
    label_colour: Colour = Colours.black
    custom_palette: list[Colour | None] = Colours.custom_palette  # Shared across all Params instances
    brush_width: int = 10
    line_style: LineStyle = LineStyle.SOLID
    line_dash_offset: int = 0
    grid_size: int = 40
    grid_visible: bool = True
    output_file: Path = Path("output.webp")
    lines: list[Line] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    icons: list[Iconlike] = Field(default_factory=list)
    recent_icons: list[Icon_Source] = Field(default_factory=list)
    version: int = Field(default=SCHEMA_VERSION)
