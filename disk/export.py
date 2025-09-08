from __future__ import annotations

from collections.abc import Callable
from math import hypot
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from disk.formats import Formats
from models.geo import Line
from models.linestyle import CapStyle, scaled_pattern, svg_dasharray
from models.objects import Icon, Label
from models.params import Params


# ------------------------- Low-level helpers (shared) ------------------------- #


def _unit(x1: float, y1: float, x2: float, y2: float) -> tuple[float, float, float]:
    dx, dy = (x2 - x1), (y2 - y1)
    L = hypot(dx, dy)
    if L <= 0:
        return 0.0, 0.0, 0.0
    return dx / L, dy / L, L


def _col_and_opacity(col) -> tuple[str, str]:
    """
    Return (svg_hex, extra_opacity_attr) for SVG. For PIL, you already have RGBA on the Colour object.
    """
    hex_rgb = col.hex  # "#rrggbb"
    if getattr(col, "alpha", 255) < 255:
        op = f' opacity="{col.alpha / 255:.3f}"'
    else:
        op = ""
    return hex_rgb, op


# ----------------------------- PIL dashed stroker ---------------------------- #


def _stroke_dashed_line(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: int,
    rgba: tuple[int, int, int, int],
    dash: tuple[int, ...],
    offset: int = 0,
    capstyle: CapStyle = CapStyle.ROUND,  # "butt" | "round" | "projecting"
) -> None:
    """
    Draw a (possibly dashed) line with cap emulation for PIL:
        - butt: plain segments
        - round: circles at ends of each on-segment (and ends of solid)
        - projecting: extend each on-segment by r at both ends along the tangent
    """
    ux, uy, L = _unit(x1, y1, x2, y2)
    if L <= 0:
        return

    r = width / 2.0

    # SOLID fast-path
    if not dash:
        if capstyle == CapStyle.PROJECTING:
            xa, ya = x1 - ux * r, y1 - uy * r
            xb, yb = x2 + ux * r, y2 + uy * r
            draw.line([(xa, ya), (xb, yb)], fill=rgba, width=width)
        else:
            draw.line([(x1, y1), (x2, y2)], fill=rgba, width=width)
            if capstyle == CapStyle.ROUND:
                draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=rgba)
                draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=rgba)
        return

    # DASHPATH
    pat = list(dash)
    if len(pat) % 2 == 1:
        pat *= 2
    total = sum(pat) or 1
    off = offset % total

    # advance into pattern by offset
    i = 0
    while off > 0 and pat:
        step = min(off, pat[0])
        pat[0] -= step
        off -= step
        if pat[0] == 0:
            pat.pop(0)
            i += 1

    seq = pat if pat else list(dash)
    if len(seq) % 2 == 1:
        seq *= 2

    pos = 0.0
    on = i % 2 == 0
    idx = 0
    max_iters = 200000

    while pos < L and idx < max_iters:
        seg_len = min(seq[idx % len(seq)], int(L - pos + 0.5))
        if seg_len <= 0:
            break

        a = pos
        b = pos + seg_len
        xA, yA = x1 + ux * a, y1 + uy * a
        xB, yB = x1 + ux * b, y1 + uy * b

        if on:
            # very short dash → draw a dot
            if seg_len <= width * 0.8:
                cx = (xA + xB) * 0.5
                cy = (yA + yB) * 0.5
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba)
            else:
                if capstyle == CapStyle.PROJECTING:
                    a_ext = max(0.0, a - r)
                    b_ext = min(L, b + r)
                    xA2, yA2 = x1 + ux * a_ext, y1 + uy * a_ext
                    xB2, yB2 = x1 + ux * b_ext, y1 + uy * b_ext
                    draw.line([(xA2, yA2), (xB2, yB2)], fill=rgba, width=width)
                else:
                    draw.line([(xA, yA), (xB, yB)], fill=rgba, width=width)
                    if capstyle == CapStyle.ROUND:
                        draw.ellipse([xA - r, yA - r, xA + r, yA + r], fill=rgba)
                        draw.ellipse([xB - r, yB - r, xB + r, yB + r], fill=rgba)

        pos += seg_len
        idx += 1
        on = not on


# ------------------------------- Exporter class ------------------------------ #


class Exporter:
    """
    Public API:
        - Exporter.output(params) → Path
            Dispatches based on params.output_file suffix
    """

    # Keep a Formats-keyed dispatch for simplicity: "png" | "webp" | "svg"
    supported: dict[Formats, Callable[[Params], Path]] = {}

    @classmethod
    def output(cls, params: Params) -> Path:
        fmt = Formats.check(params.output_file)
        func = cls.supported.get(fmt) if fmt else None
        if not fmt or not func:
            raise ValueError(f"Unsupported output type: {params.output_file.suffix}")
        return func(params)

    @classmethod
    def match_supported(cls) -> dict[Formats, Callable[[Params], Path]]:
        """
        Build the string-keyed dispatch: {"png": png, "webp": webp, "svg": svg}
        """
        sups: dict[Formats, Callable[[Params], Path]] = {}
        for fmt in Formats:
            handler = getattr(cls, fmt.name, None)
            if not callable(handler):
                raise NotImplementedError(f"Exporter missing handler for '{fmt.name}'")
            sups[fmt] = handler  # pyright: ignore[reportArgumentType]
        cls.supported = sups
        return sups

    # ---------- Raster draw (PIL) ---------- #

    @staticmethod
    def _draw(params: Params) -> Image.Image:
        img = Image.new("RGBA", (params.width, params.height), params.bg_mode.rgba)
        draw = ImageDraw.Draw(img)

        _draw_grid(draw, params)
        _draw_lines(draw, params)
        _draw_labels(img, params)
        _draw_icons(img, params)

        return img

    @classmethod
    def webp(cls, params: Params) -> Path:
        frame = cls._draw(params)
        frame.save(params.output_file, format="WEBP", lossless=True, method=6)
        return params.output_file

    @classmethod
    def png(cls, params: Params) -> Path:
        frame = cls._draw(params)
        frame.save(params.output_file, format="PNG")
        return params.output_file

    # ---------- SVG ---------- #

    @staticmethod
    def svg(params: Params) -> Path:
        W, H = params.width, params.height
        parts: list[str] = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']

        # background
        if params.bg_mode.alpha != 0:
            fill, op = _col_and_opacity(params.bg_mode)
            parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{fill}"{op}/>')

        # grid (behind)
        if params.grid_visible and params.grid_size > 0:
            gc, gop = _col_and_opacity(params.grid_colour)
            parts.append('<g shape-rendering="crispEdges">')
            for x in range(0, W + 1, params.grid_size):
                parts.append(f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{gc}" stroke-width="1"{gop}/>')
            for y in range(0, H + 1, params.grid_size):
                parts.append(f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{gc}" stroke-width="1"{gop}/>')
            parts.append("</g>")

        # lines
        for lin in getattr(params, "lines", []):
            lin: Line
            stroke, sop = _col_and_opacity(lin.col)
            arr = svg_dasharray(getattr(lin, "style", None), lin.width)  # "6,3" or ""
            dash_attr = f' stroke-dasharray="{arr}"' if arr else ""
            off = getattr(lin, "dash_offset", 0)
            off_attr = f' stroke-dashoffset="{off}"' if arr and off else ""

            parts.append(
                f'<line x1="{lin.a.x}" y1="{lin.a.y}" x2="{lin.b.x}" y2="{lin.b.y}" '
                f'stroke="{stroke}" stroke-width="{lin.width}" stroke-linecap="{_svg_cap(lin.capstyle)}" '
                f'stroke-linejoin="round"{sop}{dash_attr}{off_attr}/>'
            )

        # labels (rotated around their (x,y))
        for lab in getattr(params, "labels", []):
            lab: Label
            fill, fop = _col_and_opacity(lab.col)
            ta, db = lab.anchor.svg  # ("start"/"middle"/"end", baseline)
            rot = -int(getattr(lab, "rotation", 0) or 0)
            parts.append(
                f'<text x="{lab.x}" y="{lab.y}" fill="{fill}" font-size="{lab.size}" '
                f'text-anchor="{ta}" dominant-baseline="{db}" transform="rotate({rot} {lab.x} {lab.y})"{fop}>'
                f"{_escape(lab.text)}</text>"
            )

        # icons (draw in local space at origin, rotate, then translate)
        for ico in getattr(params, "icons", []):
            ico: Icon
            col, cop = _col_and_opacity(ico.col)
            x, y, s = ico.x, ico.y, ico.size
            rot = int(getattr(ico, "rotation", 0) or 0)

            parts.append(f'<g transform="translate({x} {y}) rotate({rot})">')
            if ico.name == "signal":
                r = s // 2
                parts.append(f'<circle cx="0" cy="0" r="{r}" fill="{col}"{cop}/>')
                parts.append(f'<rect x="{-r // 3}" y="{r}" width="{2 * (r // 3)}" height="{s}" fill="{col}"{cop}/>')
            elif ico.name == "buffer":
                w = s
                h = s // 2
                parts.append(
                    f'<rect x="{-w // 2}" y="{-h // 2}" width="{w}" height="{h}" '
                    f'fill="none" stroke="{col}" stroke-width="2"{cop}/>'
                )
            elif ico.name == "crossing":
                Ls = s
                parts.append(f'<line x1="{-Ls}" y1="{-Ls}" x2="{Ls}" y2="{Ls}" stroke="{col}" stroke-width="2"{cop}/>')
                parts.append(f'<line x1="{-Ls}" y1="{Ls}" x2="{Ls}" y2="{-Ls}" stroke="{col}" stroke-width="2"{cop}/>')
            elif ico.name == "switch":
                Ls = s
                parts.append(f'<line x1="0" y1="0" x2="{Ls}" y2="0" stroke="{col}" stroke-width="2"{cop}/>')
                parts.append(f'<line x1="0" y1="0" x2="{Ls}" y2="{Ls // 2}" stroke="{col}" stroke-width="2"{cop}/>')
            else:
                r = s // 3
                parts.append(f'<circle cx="0" cy="0" r="{r}" fill="{col}"{cop}/>')
            parts.append("</g>")

        parts.append("</svg>")
        with open(params.output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return params.output_file


# -------------------------- Raster sub-painters (PIL) ------------------------- #


def _draw_grid(draw: ImageDraw.ImageDraw, params: Params) -> None:
    if not (params.grid_visible and params.grid_size > 0):
        return
    for x in range(0, params.width + 1, params.grid_size):
        draw.line([(x, 0), (x, params.height)], fill=params.grid_colour.rgba, width=1)
    for y in range(0, params.height + 1, params.grid_size):
        draw.line([(0, y), (params.width, y)], fill=params.grid_colour.rgba, width=1)


def _draw_lines(draw: ImageDraw.ImageDraw, params: Params) -> None:
    for lin in getattr(params, "lines", []):
        lin: Line
        w = lin.width
        dash = scaled_pattern(getattr(lin, "style", None), w)
        if dash:
            # dashed path with per-cap emulation
            # extend endpoints if projecting, but KEEP dashed
            ux, uy, L = _unit(lin.a.x, lin.a.y, lin.b.x, lin.b.y)
            if lin.capstyle == CapStyle.PROJECTING and L > 0:
                r = w / 2.0
                x1e, y1e = lin.a.x - ux * r, lin.a.y - uy * r
                x2e, y2e = lin.b.x + ux * r, lin.b.y + uy * r
            else:
                x1e, y1e, x2e, y2e = lin.b.x, lin.b.y, lin.b.x, lin.b.y

            _stroke_dashed_line(
                draw,
                x1e,
                y1e,
                x2e,
                y2e,
                w,
                lin.col.rgba,
                dash,
                getattr(lin, "dash_offset", 0),
                lin.capstyle,
            )
        else:
            # solid path + cap emulation
            ux, uy, L = _unit(lin.a.x, lin.a.y, lin.b.x, lin.b.y)
            r = w / 2.0
            if lin.capstyle == CapStyle.PROJECTING and L > 0:
                xa, ya = lin.a.x - ux * r, lin.a.y - uy * r
                xb, yb = lin.b.x + ux * r, lin.b.y + uy * r
                draw.line([(xa, ya), (xb, yb)], fill=lin.col.rgba, width=w)
            elif lin.capstyle == CapStyle.ROUND:
                draw.line([(lin.a.x, lin.a.y), (lin.b.x, lin.b.y)], fill=lin.col.rgba, width=w)
                draw.ellipse([lin.a.x - r, lin.a.y - r, lin.a.x + r, lin.a.y + r], fill=lin.col.rgba)
                draw.ellipse([lin.b.x - r, lin.b.y - r, lin.b.x + r, lin.b.y + r], fill=lin.col.rgba)
            else:
                draw.line([(lin.a.x, lin.a.y), (lin.b.x, lin.b.y)], fill=lin.col.rgba, width=w)


def _font_cache_factory() -> tuple[dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont | None], Any]:
    _TTF_CANDIDATES = ("DejaVuSans.ttf", "DejaVuSansMono.ttf")
    cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont | None] = {}

    def _font(sz: int):
        f = cache.get(sz)
        if f is not None:
            return f
        got = None
        if hasattr(ImageFont, "truetype"):
            for name in _TTF_CANDIDATES:
                try:
                    got = ImageFont.truetype(name, sz)
                    break
                except Exception:
                    pass
        if got is None:
            try:
                got = ImageFont.load_default()
            except Exception:
                got = None
        cache[sz] = got
        return got

    return cache, _font


def _draw_labels(img: Image.Image, params: Params) -> None:
    _, _font = _font_cache_factory()
    for lab in getattr(params, "labels", []):
        lab: Label
        txt = lab.text
        if not txt:
            continue
        font = _font(lab.size)
        temp = Image.new("RGBA", (params.width, params.height), (0, 0, 0, 0))
        ImageDraw.Draw(temp).text((lab.x, lab.y), txt, fill=lab.col.rgba, font=font, anchor=lab.anchor.pil)
        temp = temp.rotate(
            int(getattr(lab, "rotation", 0) or 0),
            resample=Image.Resampling.BICUBIC,
            center=(lab.x, lab.y),
            expand=False,
        )
        img.alpha_composite(temp)


def _draw_icons(img: Image.Image, params: Params) -> None:
    draw = ImageDraw.Draw(img)
    for ico in getattr(params, "icons", []):
        ico: Icon
        rot = int(getattr(ico, "rotation", 0) or 0)
        s, x, y, col = ico.size, ico.x, ico.y, ico.col.rgba

        if rot % 360 != 0:
            # Draw into a local layer centered at (0,0), rotate, then paste at (x,y)
            box = max(s * 3, 64)
            layer = Image.new("RGBA", (box, box), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            cx = cy = box // 2

            def P(px: int, py: int) -> tuple[int, int]:
                return (cx + px, cy + py)

            if ico.name == "signal":
                r = s // 2
                ld.ellipse([P(-r, -r), P(r, r)], fill=col)
                ld.rectangle([P(-r // 3, r), P(r // 3, r + s)], fill=col)
            elif ico.name == "buffer":
                w, h = s, s // 2
                ld.rectangle([P(-w // 2, -h // 2), P(w // 2, h // 2)], outline=col, width=2)
            elif ico.name == "crossing":
                Ls = s
                ld.line([P(-Ls, -Ls), P(Ls, Ls)], fill=col, width=2)
                ld.line([P(-Ls, Ls), P(Ls, -Ls)], fill=col, width=2)
            elif ico.name == "switch":
                Ls = s
                ld.line([P(0, 0), P(Ls, 0)], fill=col, width=2)
                ld.line([P(0, 0), P(Ls, Ls // 2)], fill=col, width=2)
            else:
                r = s // 3
                ld.ellipse([P(-r, -r), P(r, r)], fill=col)

            layer = layer.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
            lw, lh = layer.size
            img.alpha_composite(layer, (int(x - lw // 2), int(y - lh // 2)))
        else:
            if ico.name == "signal":
                r = s // 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=col)
                draw.rectangle([x - r // 3, y + r, x + r // 3, y + s], fill=col)
            elif ico.name == "buffer":
                w = s
                h = s // 2
                draw.rectangle([x - w // 2, y - h // 2, x + w // 2, y + h // 2], outline=col, width=2)
            elif ico.name == "crossing":
                Ls = s
                draw.line([x - Ls, y - Ls, x + Ls, y + Ls], fill=col, width=2)
                draw.line([x - Ls, y + Ls, x + Ls, y - Ls], fill=col, width=2)
            elif ico.name == "switch":
                Ls = s
                draw.line([x, y, x + Ls, y], fill=col, width=2)
                draw.line([x, y, x + Ls, y + Ls // 2], fill=col, width=2)
            else:
                r = s // 3
                draw.ellipse([x - r, y - r, x + r, y + r], fill=col)


# ------------------------------- SVG helpers -------------------------------- #


def _svg_cap(cap: CapStyle) -> str:
    # Tk: "butt" | "round" | "projecting"
    # SVG: "butt" | "round" | "square"
    return "square" if cap == CapStyle.PROJECTING else cap.value


def _escape(string: str) -> str:
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


# initialize dispatch map
Exporter.match_supported()
