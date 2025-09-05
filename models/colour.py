from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Colour:
    name: str
    red: int
    green: int
    blue: int
    alpha: int = 255

    def __post_init__(self):
        def clamp(v: int) -> int:
            return 0 if v < 0 else 255 if v > 255 else v

        object.__setattr__(self, "red", clamp(self.red))
        object.__setattr__(self, "green", clamp(self.green))
        object.__setattr__(self, "blue", clamp(self.blue))
        object.__setattr__(self, "alpha", clamp(self.alpha))
        object.__setattr__(self, "name", self.name.lower())

    @property
    def rgb(self) -> tuple[int, int, int]:
        return self.red, self.green, self.blue

    @property
    def rgba(self) -> tuple[int, int, int, int]:
        return self.red, self.green, self.blue, self.alpha

    @property
    def hex(self) -> str:
        # "#RRGGBB" for Tk/SVG
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}"

    @property
    def hexa(self) -> str:
        # "#RRGGBBAA" (SVG doesn’t really use A, but handy)
        return f"#{self.red:02X}{self.green:02X}{self.blue:02X}{self.alpha:02X}"

    def __str__(self) -> str:
        r, g, b, a = self.rgba
        return f"<Colour; {self.name or 'Unknown'}: {r}, {g}, {b}, {a}>"

    def __repr__(self) -> str:
        return self.__str__()

    def lower(self) -> str:
        return self.name.lower()

    def upper(self) -> str:
        return self.name.upper()


class Colours:
    white = Colour("white", 255, 255, 255)
    black = Colour("black", 0, 0, 0)
    transparent = Colour("transparent", 0, 0, 0, 0)
    red = Colour("red", 255, 0, 0)
    green = Colour("green", 0, 255, 0)
    blue = Colour("blue", 0, 0, 255)
    cyan = Colour("cyan", 0, 255, 255)
    magenta = Colour("magenta", 255, 0, 255)
    yellow = Colour("yellow", 255, 255, 0)
    gray = Colour("gray", 128, 128, 128)

    class sys:
        light_gray = Colour("light_gray", 200, 200, 200)
        dark_gray = Colour("dark_gray", 60, 60, 60)

    @classmethod
    def get(cls, value: str) -> Colour | None:
        return getattr(cls, value.lower(), None)

    @classmethod
    def getor(cls, value: str, fallback: Colour = Colour("white", 255, 255, 255)) -> Colour:
        return cls.get(value) or fallback

    def __class_getitem__(cls, value: str) -> Colour | None:
        return cls.get(value)

    @classmethod
    def option_col(cls, first: str | Colour | None = None, min_trans: int = 255) -> list[Colour]:
        if isinstance(first, str):
            first = cls.get(first)
        cols = [c for c in cls.__dict__.values() if isinstance(c, Colour)]
        if first:
            cols.remove(first)
            cols.insert(0, first)
        return [c for c in cols if c.alpha >= min_trans]

    @classmethod
    def option_str(cls, first: str | Colour | None = None, min_trans: int = 255) -> list[str]:
        cols = cls.option_col(first, min_trans)
        return [c.name for c in cols]
