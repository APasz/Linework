from pathlib import Path

from pydantic import Field

from models.geo import Icon, Label, Line
from models.styling import Colour, Colours, LineStyle, Model

SCHEMA_VERSION = 1


class Params(Model):
    width: int = 1200
    height: int = 600
    bg_mode: Colour = Colours.white
    brush_width: int = 10
    brush_colour: Colour = Colours.black
    line_style: LineStyle = LineStyle.SOLID
    line_dash_offset: int = 0
    grid_size: int = 40
    grid_colour: Colour = Colours.gray
    grid_visible: bool = True
    output_file: Path = Path("output.webp")
    lines: list[Line] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    icons: list[Icon] = Field(default_factory=list)
    version: int = Field(default=SCHEMA_VERSION)
