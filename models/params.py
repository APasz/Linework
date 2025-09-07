from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from disk.formats import Formats
from models.colour import Colour, Colours
from models.geo import Line
from models.linestyle import LineStyle
from models.objects import Icon, Label


class Params(BaseModel):
    width: int = 600
    height: int = 600
    bg_mode: Colour = Colours.white
    brush_width: int = 5
    brush_colour: Colour = Colours.black
    line_style: LineStyle = LineStyle.SOLID
    line_dash_offset: int = 0
    grid_size: int = 40
    grid_colour: Colour = Colours.gray
    grid_visible: bool = True
    grid_lines_ids: list[int] = Field(default_factory=list)
    output_file: Path = Path("output")
    output_type: Formats = Formats.webp
    lines: list[Line] = Field(default_factory=list)
    labels: list[Label] = Field(default_factory=list)
    icons: list[Icon] = Field(default_factory=list)

    model_config = ConfigDict(arbitrary_types_allowed=True)
