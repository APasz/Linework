from __future__ import annotations

from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from models.geo import Icon_Name, Line
from models.params import Params
from models.styling import CapStyle, svg_dasharray

DOT_FACTOR = 0.8  # short dash threshold as a multiple of width
SVG_STRICT_PARITY = False


class RASTERISERS(StrEnum):
    pil = "pil"
    cairosvg = "cairosvg"
    resvg = "resvg"


RASTER_BACKEND = RASTERISERS.cairosvg  # "pil" | "cairosvg" | "resvg"


class Formats(StrEnum):
    webp = "webp"
    png = "png"
    svg = "svg"

    @classmethod
    def check(cls, path: Path) -> "Formats | None":
        suf = path.suffix[1:].lower()
        return Formats(suf) if suf in Formats else None


def _rasterize_via_svg(params: Params, fmt: Formats) -> bytes | None:
    # reuse your existing SVG generator
    svg_path = params.output_file.with_suffix(".tmp.svg")
    Exporter.svg(params.__class__(**(params.model_dump() | {"output_file": svg_path})))  # or factor out to get string
    svg_bytes = Path(svg_path).read_bytes()
    Path(svg_path).unlink(missing_ok=True)

    if RASTER_BACKEND == "cairosvg":
        import cairosvg  # pyright: ignore[reportMissingImports]

        if fmt == Formats.png:
            png = cairosvg.svg2png(bytestring=svg_bytes, output_width=params.width, output_height=params.height)
            return png if isinstance(png, bytes) else None
        if fmt == Formats.webp:
            # cairosvg -> PNG, then transcode with PIL
            import io

            import PIL.Image as Image

            png = cairosvg.svg2png(bytestring=svg_bytes, output_width=params.width, output_height=params.height)
            if not isinstance(png, bytes):
                return None
            img = Image.open(io.BytesIO(png)).convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format=fmt.upper(), lossless=True, method=6)
            return buf.getvalue()

    if RASTER_BACKEND == "resvg":
        # requires `resvg` on PATH
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(suffix="." + fmt.lower(), delete=False) as out:
            out_path = Path(out.name)
        subprocess.run(
            ["resvg", "-w", str(params.width), "-h", str(params.height), "-", str(out_path)],
            input=svg_bytes,
            check=True,
        )
        data = out_path.read_bytes()
        out_path.unlink(missing_ok=True)
        return data

    raise RuntimeError("Unknown or unavailable SVG raster backend")


# ------------------------- Low-level helpers (shared) ------------------------- #
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


def dash_seq(dash: Sequence[int] | None, offset: int) -> tuple[list[int], bool]:
    """
    Normalize a dash pattern and apply offset.
    Returns (sequence, start_on) where sequence has even length and no zeros.
    If dash is None or degenerate → return ([], True) meaning 'solid'.
    """
    if not dash:
        return ([], True)  # solid

    seq = [int(p) for p in dash if p > 0]
    if not seq:
        return ([], True)  # solid

    if len(seq) % 2 == 1:
        seq *= 2

    total = sum(seq)
    off = int(offset) % total

    i = 0
    # consume offset into the sequence
    while off > 0 and seq:
        step = min(off, seq[0])
        seq[0] -= step
        off -= step
        if seq[0] == 0:
            seq.pop(0)
            i += 1

    if not seq:
        # offset landed exactly on a boundary → restart from canonical
        seq = [int(p) for p in dash if p > 0]
        if len(seq) % 2 == 1:
            seq *= 2

    start_on = i % 2 == 0
    return (seq, start_on)


def iter_dash_spans(L: float, dash: Sequence[int] | None, offset: int):
    """
    Yield (a, b, on) arc-length spans along [0, L] after applying dash+offset.
    a and b are distances from the start point along the line.
    """
    if L <= 0:
        return
    seq, on = dash_seq(dash, offset)
    if not seq:  # solid
        yield 0.0, L, True
        return

    pos = 0.0
    idx = 0
    max_iters = 200000

    while pos < L and idx < max_iters:
        seg_len = min(seq[idx % len(seq)], int(L - pos + 0.5))
        if seg_len <= 0:
            break
        a = pos
        b = pos + seg_len
        yield a, b, on
        pos = b
        idx += 1
        on = not on


def extend_span_for_projecting(a: float, b: float, r: float, L: float) -> tuple[float, float]:
    """
    Extend an on-span by r at both ends, clamped to [0, L].
    """
    return max(0.0, a - r), min(L, b + r)


# ------------------------------- SVG helpers -------------------------------- #
def _svg_cap(cap: CapStyle) -> str:
    # Tk: "butt" | "round" | "projecting"
    # SVG: "butt" | "round" | "square"
    return "square" if cap == CapStyle.PROJECTING else cap.value


def _escape(string: str) -> str:
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _svg_line_fast(lin) -> str:
    """Native SVG: one <line>, rely on stroke-linecap + dasharray + dashoffset."""
    stroke, sop = _col_and_opacity(lin.col)
    arr = svg_dasharray(getattr(lin, "style", None), lin.width)  # "6,3" or ""
    dash_attr = f' stroke-dasharray="{arr}"' if arr else ""
    off = getattr(lin, "dash_offset", 0)
    off_attr = f' stroke-dashoffset="{off}"' if arr and off else ""
    return (
        f'<line x1="{lin.a.x}" y1="{lin.a.y}" x2="{lin.b.x}" y2="{lin.b.y}" '
        f'stroke="{stroke}" stroke-width="{lin.width}" '
        f'stroke-linecap="{_svg_cap(lin.capstyle)}" stroke-linejoin="round"{sop}{dash_attr}{off_attr}/>'
    )


def _svg_line_strict(lin) -> list[str]:
    """
    Strict parity with PIL: emit per-dash <line> segments (and dots), doing our own projecting extensions.
    We draw segments with stroke-linecap="butt" because we already extend/round ourselves.
    """
    ux, uy, L = lin.unit()
    if L <= 0 or int(lin.width) <= 0:
        return []

    width = int(lin.width)
    r = width / 2.0
    stroke, sop = _col_and_opacity(lin.col)
    x1, y1 = float(lin.a.x), float(lin.a.y)
    out: list[str] = []

    dash = lin.scaled_pattern()  # None or tuple
    # Solid path → one line (with native cap for ends).
    if not dash:
        out.append(
            f'<line x1="{lin.a.x}" y1="{lin.a.y}" x2="{lin.b.x}" y2="{lin.b.y}" '
            f'stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linecap="{_svg_cap(lin.capstyle)}" stroke-linejoin="round"{sop}/>'
        )
        return out

    # Dashed path → explicit segments for exact parity (dot threshold and projecting)
    for a, b, on in iter_dash_spans(L, dash, lin.dash_offset):
        if not on:
            continue
        seg_len = b - a
        if seg_len <= width * DOT_FACTOR:
            # dot = circle at mid
            cx = x1 + ux * ((a + b) * 0.5)
            cy = y1 + uy * ((a + b) * 0.5)
            out.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{stroke}"{sop}/>')
            continue

        a0, b0 = (a, b)
        if lin.capstyle == CapStyle.PROJECTING:
            a0, b0 = extend_span_for_projecting(a, b, r, L)

        xA, yA = x1 + ux * a0, y1 + uy * a0
        xB, yB = x1 + ux * b0, y1 + uy * b0
        # butt caps: we already extended if needed
        out.append(
            f'<line x1="{xA}" y1="{yA}" x2="{xB}" y2="{yB}" '
            f'stroke="{stroke}" stroke-width="{width}" stroke-linecap="butt" stroke-linejoin="round"{sop}/>'
        )

        # Optional: if you want round caps on each dash like PIL’s “large dash” path, add circles at xA/yA and xB/yB when ROUND:
        if lin.capstyle == CapStyle.ROUND:
            out.append(f'<circle cx="{xA}" cy="{yA}" r="{r}" fill="{stroke}"{sop}/>')
            out.append(f'<circle cx="{xB}" cy="{yB}" r="{r}" fill="{stroke}"{sop}/>')
    return out


# ----------------------------- PIL dashed stroker ---------------------------- #
def _stroke_dashed_line(draw: ImageDraw.ImageDraw, line: Line) -> None:
    ux, uy, L = line.unit()
    if L <= 0 or int(line.width) <= 0:
        return

    width = int(line.width)
    rgba = line.col.rgba
    capstyle = line.capstyle
    x1, y1 = float(line.a.x), float(line.a.y)

    # Detect axis-aligned segments (horizontal or vertical)
    axis_aligned = abs(ux) < 1e-9 or abs(uy) < 1e-9

    # r used for *mathematical* half-width (extensions)
    r_line = width / 2.0
    # r used for *drawing* cap circles (matches Pillow’s pixel-centre behavior)
    r_cap = r_line - (0.5 if axis_aligned and (width % 2 == 0) else 0.0)

    dash = line.scaled_pattern()

    for a, b, on in iter_dash_spans(L, dash, line.dash_offset):
        if not on:
            continue

        seg_len = b - a

        # short dash → dot
        if seg_len <= width * DOT_FACTOR:
            cx = x1 + ux * ((a + b) * 0.5)
            cy = y1 + uy * ((a + b) * 0.5)
            draw.ellipse([cx - r_cap, cy - r_cap, cx + r_cap, cy + r_cap], fill=rgba)
            continue

        a0, b0 = a, b
        if capstyle == CapStyle.PROJECTING:
            a0, b0 = extend_span_for_projecting(a, b, r_line, L)

        xA, yA = x1 + ux * a0, y1 + uy * a0
        xB, yB = x1 + ux * b0, y1 + uy * b0
        draw.line([(xA, yA), (xB, yB)], fill=rgba, width=width)

        if capstyle == CapStyle.ROUND:
            # draw caps at the *unextended* endpoints
            cxA, cyA = x1 + ux * a, y1 + uy * a
            cxB, cyB = x1 + ux * b, y1 + uy * b
            draw.ellipse([cxA - r_cap, cyA - r_cap, cxA + r_cap, cyA + r_cap], fill=rgba)
            draw.ellipse([cxB - r_cap, cyB - r_cap, cxB + r_cap, cyB + r_cap], fill=rgba)


# ------------------------------- Exporter class ------------------------------ #
class Exporter:
    """
    Public API:
        - Exporter.output(params) → Path
            Dispatches based on params.output_file suffix
    """

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
        if RASTER_BACKEND == RASTERISERS.pil:
            frame = cls._draw(params)
            frame.save(params.output_file, format=Formats.webp.upper(), lossless=True, method=6)
        else:
            if raster := _rasterize_via_svg(params, Formats.webp):
                params.output_file.write_bytes(raster)
        return params.output_file

    @classmethod
    def png(cls, params: Params) -> Path:
        if RASTER_BACKEND == RASTERISERS.pil:
            frame = cls._draw(params)
            frame.save(params.output_file, format=Formats.png.upper())
        else:
            if raster := _rasterize_via_svg(params, Formats.png):
                params.output_file.write_bytes(raster)
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
        for lin in params.lines:
            if SVG_STRICT_PARITY:
                parts.extend(_svg_line_strict(lin))
            else:
                parts.append(_svg_line_fast(lin))

        # labels
        for lab in params.labels:
            fill, fop = _col_and_opacity(lab.col)
            ta, db = lab.anchor.svg  # ("start"/"middle"/"end", baseline)
            parts.append(
                f'<text x="{lab.p.x}" y="{lab.p.y}" fill="{fill}" font-size="{lab.size}" '
                f'text-anchor="{ta}" dominant-baseline="{db}" transform="rotate({-lab.rotation} {lab.p.x} {lab.p.y})"{fop}>'
                f"{_escape(lab.text)}</text>"
            )

        # icons
        for ico in params.icons:
            col, cop = _col_and_opacity(ico.col)
            bw, bh = ico.bbox_wh()
            cx, cy = ico.anchor._centre(ico.p.x, ico.p.y, bw, bh)

            # One transform. Rotate sign matches your PIL (-ico.rotation)
            parts.append(f'<g transform="translate({cx} {cy}) rotate({-ico.rotation})">')

            if ico.name == Icon_Name.SIGNAL:
                r = ico.size // 2
                parts.append(f'<circle cx="0" cy="0" r="{r}" fill="{col}"{cop}/>')
                parts.append(
                    f'<rect x="{-r // 3}" y="{r}" width="{2 * (r // 3)}" height="{ico.size}" fill="{col}"{cop}/>'
                )
            elif ico.name == Icon_Name.BUFFER:
                w = ico.size
                h = ico.size // 2
                parts.append(
                    f'<rect x="{-w // 2}" y="{-h // 2}" width="{w}" height="{h}" '
                    f'fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"{cop}/>'
                )
            elif ico.name == Icon_Name.CROSSING:
                Ls = ico.size
                parts.append(
                    f'<line x1="{-Ls}" y1="{-Ls}" x2="{Ls}" y2="{Ls}" stroke="{col}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{cop}/>'
                )
                parts.append(
                    f'<line x1="{-Ls}" y1="{Ls}" x2="{Ls}" y2="{-Ls}" stroke="{col}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{cop}/>'
                )
            elif ico.name == Icon_Name.SWITCH:
                Ls = ico.size
                parts.append(
                    f'<line x1="0" y1="0" x2="{Ls}" y2="0" stroke="{col}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{cop}/>'
                )
                parts.append(
                    f'<line x1="0" y1="0" x2="{Ls}" y2="{Ls // 2}" stroke="{col}" stroke-width="2" '
                    f'stroke-linecap="round" stroke-linejoin="round"{cop}/>'
                )
            else:
                r = ico.size // 3
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
    for lin in params.lines:
        _stroke_dashed_line(draw, lin)


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
    for lab in params.labels:
        if not lab.text:
            continue
        temp = Image.new("RGBA", (params.width, params.height), (0, 0, 0, 0))
        ImageDraw.Draw(temp).text(
            (lab.p.x, lab.p.y),
            lab.text,
            fill=lab.col.rgba,
            font=_font(lab.size),
            anchor=lab.anchor.pil,
        )
        temp = temp.rotate(
            int(getattr(lab, "rotation", 0) or 0),
            resample=Image.Resampling.BICUBIC,
            center=(lab.p.x, lab.p.y),
            expand=False,
        )
        img.alpha_composite(temp)


def _draw_icons(img: Image.Image, params: Params) -> None:
    draw = ImageDraw.Draw(img)
    for ico in params.icons:
        size = ico.size
        # compute centre from anchor
        bw, bh = ico.bbox_wh()
        cx, cy = ico.anchor._centre(ico.p.x, ico.p.y, bw, bh)
        col = ico.col.rgba

        if ico.rotation % 360 != 0:
            box = max(size * 3, 64)
            layer = Image.new("RGBA", (box, box), (0, 0, 0, 0))
            ld = ImageDraw.Draw(layer)
            cx = cy = box // 2

            def P(px: int, py: int) -> tuple[int, int]:
                return (cx + px, cy + py)

            if ico.name == Icon_Name.SIGNAL:
                r = size // 2
                ld.ellipse([P(-r, -r), P(r, r)], fill=col)
                ld.rectangle([P(-r // 3, r), P(r // 3, r + size)], fill=col)
            elif ico.name == Icon_Name.BUFFER:
                w, h = size, size // 2
                ld.rectangle([P(-w // 2, -h // 2), P(w // 2, h // 2)], outline=col, width=2)
            elif ico.name == Icon_Name.CROSSING:
                Ls = size
                ld.line([P(-Ls, -Ls), P(Ls, Ls)], fill=col, width=2)
                ld.line([P(-Ls, Ls), P(Ls, -Ls)], fill=col, width=2)
            elif ico.name == Icon_Name.SWITCH:
                Ls = size
                ld.line([P(0, 0), P(Ls, 0)], fill=col, width=2)
                ld.line([P(0, 0), P(Ls, Ls // 2)], fill=col, width=2)
            else:
                r = size // 3
                ld.ellipse([P(-r, -r), P(r, r)], fill=col)

            layer = layer.rotate(-ico.rotation, resample=Image.Resampling.BICUBIC, expand=True)
            lw, lh = layer.size
            img.alpha_composite(layer, (int(cx - lw // 2), int(cy - lh // 2)))
        else:
            if ico.name == Icon_Name.SIGNAL:
                r = size // 2
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)
                draw.rectangle([cx - r // 3, cy + r, cx + r // 3, cy + size], fill=col)
            elif ico.name == Icon_Name.BUFFER:
                w = size
                h = size // 2
                draw.rectangle([cx - w // 2, cy - h // 2, cx + w // 2, cy + h // 2], outline=col, width=2)
            elif ico.name == Icon_Name.CROSSING:
                Ls = size
                draw.line([cx - Ls, cy - Ls, cx + Ls, cy + Ls], fill=col, width=2)
                draw.line([cx - Ls, cy + Ls, cx + Ls, cy - Ls], fill=col, width=2)
            elif ico.name == Icon_Name.SWITCH:
                Ls = size
                draw.line([cx, cy, cx + Ls, cy], fill=col, width=2)
                draw.line([cx, cy, cx + Ls, cy + Ls // 2], fill=col, width=2)
            else:
                r = size // 3
                draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=col)


Exporter.match_supported()
