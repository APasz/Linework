from __future__ import annotations

from collections.abc import Callable
from math import hypot
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from disk.formats import Formats
from models.linestyle import scaled_pattern, svg_dasharray
from models.objects import Icon, Label
from models.params import Params


def _stroke_dashed_line(
    draw: ImageDraw.ImageDraw,
    x1: float,
    y1: float,
    x2: float,
    y2: float,
    width: int,
    rgba,
    dash: tuple[int, ...],
    offset: int = 0,
    capstyle: str = "butt",  # "butt" | "round" | "projecting"
):
    """
    Draw a dashed line with cap emulation for PIL:
        - butt: plain segments
        - round: circles at ends of each on-segment (and ends of solid)
        - projecting: extend each on-segment by r at both ends along the tangent
    """
    # quick solid path (no dash):
    dx, dy = x2 - x1, y2 - y1
    L = hypot(dx, dy)
    if L <= 0:
        return

    ux, uy = dx / L, dy / L
    r = width / 2.0

    if not dash:  # solid
        if capstyle == "projecting":
            xa, ya = x1 - ux * r, y1 - uy * r
            xb, yb = x2 + ux * r, y2 + uy * r
            draw.line([(xa, ya), (xb, yb)], fill=rgba, width=width)
        else:
            draw.line([(x1, y1), (x2, y2)], fill=rgba, width=width)
            if capstyle == "round":
                draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=rgba)
                draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=rgba)
        return

    # dashed path
    pat = list(dash)
    if len(pat) % 2 == 1:
        pat *= 2
    total = sum(pat) or 1
    off = offset % total

    # advance into the pattern by offset
    i = 0
    while off > 0 and pat:
        step = min(off, pat[0])
        pat[0] -= step
        off -= step
        if pat[0] == 0:
            pat.pop(0)
            i += 1

    pos = 0.0
    on = i % 2 == 0
    seq = pat if pat else list(dash)
    if len(seq) % 2 == 1:
        seq *= 2

    idx = 0
    max_iters = 200000  # safety

    while pos < L and idx < max_iters:
        seg_len = min(seq[idx % len(seq)], int(L - pos + 0.5))
        if seg_len <= 0:
            break

        a = pos
        b = pos + seg_len
        xA, yA = x1 + ux * a, y1 + uy * a
        xB, yB = x1 + ux * b, y1 + uy * b

        if on:
            # heuristic: if on-length is smaller than stroke width → draw a dot
            if seg_len <= width * 0.8:
                cx = (xA + xB) * 0.5
                cy = (yA + yB) * 0.5
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=rgba)
            else:
                if capstyle == "projecting":
                    # extend along the direction, but clip to [0, L]
                    a_ext = max(0.0, a - r)
                    b_ext = min(L, b + r)
                    xA2, yA2 = x1 + ux * a_ext, y1 + uy * a_ext
                    xB2, yB2 = x1 + ux * b_ext, y1 + uy * b_ext
                    draw.line([(xA2, yA2), (xB2, yB2)], fill=rgba, width=width)
                else:
                    draw.line([(xA, yA), (xB, yB)], fill=rgba, width=width)
                    if capstyle == "round":
                        draw.ellipse([xA - r, yA - r, xA + r, yA + r], fill=rgba)
                        draw.ellipse([xB - r, yB - r, xB + r, yB + r], fill=rgba)

        pos += seg_len
        idx += 1
        on = not on


class Exporter:
    @classmethod
    def output(cls, params: Params) -> Path:
        func = cls.supported.get(params.output_type)
        if not func:
            raise ValueError(f"Unsupported output type: {params.output_type}")
        return func(params)

    @staticmethod
    def _draw(params: Params) -> Image.Image:
        img = Image.new("RGBA", (params.width, params.height), params.bg_mode.rgba)
        draw = ImageDraw.Draw(img)

        def _unit(dx, dy) -> tuple[float, float]:
            L = hypot(dx, dy)
            return (dx / L, dy / L) if L else (0.0, 0.0)

        # grid
        if params.grid_visible and params.grid_size > 0:
            for x in range(0, params.width + 1, params.grid_size):
                draw.line([(x, 0), (x, params.height)], fill=params.grid_colour.rgba, width=1)
            for y in range(0, params.height + 1, params.grid_size):
                draw.line([(0, y), (params.width, y)], fill=params.grid_colour.rgba, width=1)

        # lines with capstyle emulation
        for line in getattr(params, "lines", []):
            x1, y1, x2, y2, w = line.x1, line.y1, line.x2, line.y2, line.width
            fill = line.col.rgba
            r = w / 2.0

            dash = scaled_pattern(getattr(line, "style", None), line.width)

            if dash:
                # --- dashed branch ---
                # For "projecting" (square) caps, extend endpoints by half width, but KEEP it dashed.
                if line.capstyle == "projecting":
                    ux = uy = 0.0
                    dx, dy = (x2 - x1), (y2 - y1)
                    L = hypot(dx, dy)
                    if L > 0:
                        ux, uy = dx / L, dy / L
                    x1e, y1e = x1 - ux * r, y1 - uy * r
                    x2e, y2e = x2 + ux * r, y2 + uy * r
                else:
                    x1e, y1e, x2e, y2e = x1, y1, x2, y2

                _stroke_dashed_line(
                    draw,
                    line.x1,
                    line.y1,
                    line.x2,
                    line.y2,
                    line.width,
                    line.col.rgba,
                    dash or (),
                    getattr(line, "dash_offset", 0),
                    line.capstyle,
                )
                # Note: we do NOT draw a second solid stroke here,
                # otherwise we’d obliterate the dash pattern.
                # (Per-dash round caps are non-trivial to emulate; Tk/SVG handle that natively.)
            else:
                # --- solid branch (keep your original cap emulation) ---
                if line.capstyle == "projecting":
                    ux = uy = 0.0
                    dx, dy = (x2 - x1), (y2 - y1)
                    L = hypot(dx, dy)
                    if L > 0:
                        ux, uy = dx / L, dy / L
                    x1e, y1e = x1 - ux * r, y1 - uy * r
                    x2e, y2e = x2 + ux * r, y2 + uy * r
                    draw.line([(x1e, y1e), (x2e, y2e)], fill=fill, width=w)
                elif line.capstyle == "round":
                    draw.line([(x1, y1), (x2, y2)], fill=fill, width=w)
                    draw.ellipse([x1 - r, y1 - r, x1 + r, y1 + r], fill=fill)
                    draw.ellipse([x2 - r, y2 - r, x2 + r, y2 + r], fill=fill)
                else:  # butt
                    draw.line([(x1, y1), (x2, y2)], fill=fill, width=w)

        # labels (default font)
        _TTF_CANDIDATES = ("DejaVuSans.ttf", "DejaVuSansMono.ttf")
        _font_cache: dict[int, "ImageFont.FreeTypeFont | ImageFont.ImageFont | None"] = {}

        def _font(sz: int):
            """Return a cached PIL ImageFont (TTF if available, else default bitmap)."""
            f = _font_cache.get(sz)
            if f is not None:
                return f

            # Try TrueType faces first
            got = None
            if hasattr(ImageFont, "truetype"):
                for name in _TTF_CANDIDATES:
                    try:
                        got = ImageFont.truetype(name, sz)
                        break
                    except Exception:
                        pass

            # Fallback to the default bitmap font (fixed size)
            if got is None:
                try:
                    got = ImageFont.load_default()
                except Exception:
                    got = None

            _font_cache[sz] = got
            return got

        for lab in getattr(params, "labels", []):
            lab: Label
            draw.text(
                (lab.x, lab.y),
                lab.text,
                fill=lab.col.rgba,
                font=_font(lab.size),
                anchor=lab.anchor.pil,
            )

        # icons (simple raster equivalents of your SVG primitives)
        for ico in getattr(params, "icons", []):
            ico: Icon
            s = ico.size
            x, y = ico.x, ico.y
            col = ico.col.rgba
            if ico.name == "signal":
                r = s // 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=col)
                draw.rectangle([x - r // 3, y + r, x + r // 3, y + s], fill=col)
            elif ico.name == "buffer":
                w = s
                h = s // 2
                draw.rectangle([x - w // 2, y - h // 2, x + w // 2, y + h // 2], outline=col, width=2)
            elif ico.name == "crossing":
                L = s
                draw.line([x - L, y - L, x + L, y + L], fill=col, width=2)
                draw.line([x - L, y + L, x + L, y - L], fill=col, width=2)
            elif ico.name == "switch":
                L = s
                draw.line([x, y, x + L, y], fill=col, width=2)
                draw.line([x, y, x + L, y + L // 2], fill=col, width=2)
            else:
                r = s // 3
                draw.ellipse([x - r, y - r, x + r, y + r], fill=col)

        return img

    @classmethod
    def _generic(cls, params: Params, save_kwargs: dict[str, Any] | None = None) -> Path:
        frame = cls._draw(params)
        frame.save(params.output_file, format=str(params.output_type).upper(), **(save_kwargs or {}))
        return params.output_file

    @classmethod
    def webp(cls, params: Params) -> Path:
        return cls._generic(params, {"lossless": True, "method": 6})

    @classmethod
    def png(cls, params: Params) -> Path:
        return cls._generic(params)

    @staticmethod
    def svg(params: Params) -> Path:
        def _svg_cap(cap: str) -> str:
            # Tk: "butt" | "round" | "projecting"
            # SVG: "butt" | "round" | "square"
            return "square" if cap == "projecting" else cap

        W, H = params.width, params.height
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">']

        if params.bg_mode.alpha != 0:
            parts.append(f'<rect x="0" y="0" width="{W}" height="{H}" fill="{params.bg_mode.hex}"/>')

        if params.grid_visible and params.grid_size > 0:
            for x in range(0, W + 1, params.grid_size):
                parts.append(
                    f'<line x1="{x}" y1="0" x2="{x}" y2="{H}" stroke="{params.grid_colour.hex}" stroke-width="1"/>'
                )
            for y in range(0, H + 1, params.grid_size):
                parts.append(
                    f'<line x1="0" y1="{y}" x2="{W}" y2="{y}" stroke="{params.grid_colour.hex}" stroke-width="1"/>'
                )

        # lines
        for line in getattr(params, "lines", []):
            dash_attr = ""
            arr = svg_dasharray(getattr(line, "style", None), line.width)
            if arr:
                dash_attr = f' stroke-dasharray="{arr}"'
                # (optional) include dash offset if you keep it in the model:
                off = getattr(line, "dash_offset", 0)
                if off:
                    dash_attr += f' stroke-dashoffset="{off}"'

            parts.append(
                f'<line x1="{line.x1}" y1="{line.y1}" x2="{line.x2}" y2="{line.y2}" '
                f'stroke="{line.col.hex}" stroke-linecap="{line.capstyle}" stroke-width="{line.width}"{dash_attr}/>'
            )

        # labels
        for lab in getattr(params, "labels", []):
            lab: Label
            ta, db = lab.anchor.svg
            parts.append(
                f'<text x="{lab.x}" y="{lab.y}" fill="{lab.col.hex}" font-size="{lab.size}" '
                f'text-anchor="{ta}" dominant-baseline="{db}">{_escape(lab.text)}</text>'
            )

        # icons
        for ico in getattr(params, "icons", []):
            ico: Icon
            x, y, s, col = ico.x, ico.y, ico.size, ico.col.hex
            if ico.name == "signal":
                r = s // 2
                parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}"/>')
                parts.append(f'<rect x="{x - r // 3}" y="{y + r}" width="{2 * (r // 3)}" height="{s}" fill="{col}"/>')
            elif ico.name == "buffer":
                w = s
                h = s // 2
                parts.append(
                    f'<rect x="{x - w // 2}" y="{y - h // 2}" width="{w}" height="{h}" fill="none" stroke="{col}" stroke-width="2"/>'
                )
            elif ico.name == "crossing":
                L = s
                parts.append(
                    f'<line x1="{x - L}" y1="{y - L}" x2="{x + L}" y2="{y + L}" stroke="{col}" stroke-width="2"/>'
                )
                parts.append(
                    f'<line x1="{x - L}" y1="{y + L}" x2="{x + L}" y2="{y - L}" stroke="{col}" stroke-width="2"/>'
                )
            elif ico.name == "switch":
                L = s
                parts.append(f'<line x1="{x}" y1="{y}" x2="{x + L}" y2="{y}" stroke="{col}" stroke-width="2"/>')
                parts.append(
                    f'<line x1="{x}" y1="{y}" x2="{x + L}" y2="{y + L // 2}" stroke="{col}" stroke-width="2"/>'
                )
            else:
                r = s // 3
                parts.append(f'<circle cx="{x}" cy="{y}" r="{r}" fill="{col}"/>')

        parts.append("</svg>")
        with open(params.output_file, "w", encoding="utf-8") as f:
            f.write("\n".join(parts))
        return params.output_file

    @classmethod
    def match_supported(cls) -> dict[str, Callable[[Params], Path]]:
        sups = {}
        for fmt in Formats:
            func = getattr(cls, fmt, None)
            if not func:
                raise AttributeError(f"Output format handler '{fmt}' not implemented in Exporter")
            if not callable(func):
                raise TypeError(f"Handler for '{fmt}' is not callable")
            sups[fmt] = func
        cls.supported = sups
        return sups

    supported: dict[str, Callable[[Params], Path]] = {}


def _escape(string: str) -> str:
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


Exporter.match_supported()
