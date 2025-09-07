import enum
from pathlib import Path


class Formats(enum.StrEnum):
    webp = enum.auto()
    png = enum.auto()
    svg = enum.auto()

    @classmethod
    def check(cls, path: Path) -> "Formats | None":
        suf = path.suffix[1:].lower()
        return Formats(suf) if suf in Formats else None
