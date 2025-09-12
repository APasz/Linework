from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from enum import StrEnum
from pathlib import Path
from typing import Any

import cairosvg
from PIL import Image, ImageDraw, ImageFont

from models.assets import Formats, _builtin_icon_plan, _open_rgba
from models.geo import Line, Picture_Icon
from models.params import Params
from models.styling import CapStyle, Colour, svg_dasharray

# -----------------------------------------------------------------------------
# Tunables
# -----------------------------------------------------------------------------
DOT_FACTOR = 0.8  # short dash threshold as a multiple of width
SVG_STRICT_PARITY = False


class RASTERISERS(StrEnum):
    pil = "pil"
    cairosvg = "cairosvg"
    resvg = "resvg"


# Choose how non-SVG rasters are produced (PIL draw or via SVG rasterisation)
RASTER_BACKEND = RASTERISERS.cairosvg  # pil | cairosvg | resvg


# -----------------------------------------------------------------------------
# Shared helpers
# -----------------------------------------------------------------------------


def _col_and_opacity(col: Colour) -> tuple[str, str]:
    """Return (svg_hex, extra_opacity_attr) for SVG emitters."""
    hex_rgb = col.hex  # "#rrggbb"
    if col.alpha < 255:
        op = f' opacity="{col.alpha / 255:.3f}"'
    else:
        op = ""
    return hex_rgb, op


# --- Dashing math ------------------------------------------------------------


def dash_seq(dash: Sequence[int] | None, offset: int) -> tuple[list[int], bool]:
    """
    Normalize a dash pattern and apply offset.
    Returns (sequence, start_on) where sequence has even length and no zeros.
    If dash is None or degenerate → return ([], True) meaning 'solid'.
    """
    if not dash:
        return ([], True)

    seq = [int(p) for p in dash if p > 0]
    if not seq:
        return ([], True)

    if len(seq) % 2 == 1:
        seq *= 2

    total = sum(seq)
    off = int(offset) % total if total > 0 else 0

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
    """Yield (a, b, on) arc-length spans along [0, L] after applying dash+offset."""
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
    """Extend an on-span by r at both ends, clamped to [0, L]."""
    return max(0.0, a - r), min(L, b + r)


# --- Pictures ---------------------------------------------------------------

_MIME_BY_EXT = {
    "png": "image/png",
    "webp": "image/webp",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "bmp": "image/bmp",
    "gif": "image/gif",
    "svg": "image/svg+xml",
}


def _picture_bytes_and_mime(src: Path) -> tuple[bytes, str]:
    ext = src.suffix[1:].lower()
    data = src.read_bytes()
    return data, _MIME_BY_EXT.get(ext, "application/octet-stream")


# -----------------------------------------------------------------------------
# SVG helpers
# -----------------------------------------------------------------------------


def _svg_cap(cap: CapStyle) -> str:
    # Tk: "butt" | "round" | "projecting"
    # SVG: "butt" | "round" | "square"
    return "square" if cap == CapStyle.PROJECTING else cap.value


def _escape(string: str) -> str:
    return string.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _svg_line_fast(line: Line) -> str:
    """Native SVG: one <line>, rely on stroke-linecap + dasharray + dashoffset."""
    stroke, sop = _col_and_opacity(line.col)
    arr = svg_dasharray(line.style, line.width)  # "6,3" or ""
    dash_attr = f' stroke-dasharray="{arr}"' if arr else ""
    off = line.dash_offset
    off_attr = f' stroke-dashoffset="{off}"' if arr and off else ""
    return (
        f'<line x1="{line.a.x}" y1="{line.a.y}" x2="{line.b.x}" y2="{line.b.y}" '
        f'stroke="{stroke}" stroke-width="{line.width}" '
        f'stroke-linecap="{_svg_cap(line.capstyle)}" stroke-linejoin="round"{sop}{dash_attr}{off_attr}/>'
    )


def _svg_line_strict(lin) -> list[str]:
    """
    Strict parity with PIL: emit per-dash <line> segments (and dots), doing
    our own projecting extensions.
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
    if not dash:
        out.append(
            f'<line x1="{lin.a.x}" y1="{lin.a.y}" x2="{lin.b.x}" y2="{lin.b.y}" '
            f'stroke="{stroke}" stroke-width="{width}" '
            f'stroke-linecap="{_svg_cap(lin.capstyle)}" stroke-linejoin="round"{sop}/>'
        )
        return out

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

        if lin.capstyle == CapStyle.ROUND:
            out.append(f'<circle cx="{xA}" cy="{yA}" r="{r}" fill="{stroke}"{sop}/>')
            out.append(f'<circle cx="{xB}" cy="{yB}" r="{r}" fill="{stroke}"{sop}/>')
    return out


# ---------------- SVG render of plan -----------------


def _emit_svg_plan(parts: list[str], plan: list[tuple[str, dict[str, Any]]]):
    for op, kw in plan:
        if op == "circle":
            cx, cy, r = kw["cx"], kw["cy"], kw["r"]
            fill = kw.get("fill")
            stroke = kw.get("stroke")
            width = kw.get("width")
            if fill:
                parts.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{fill}"/>')
            if stroke:
                parts.append(
                    f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="{stroke}" stroke-width="{width or 1}"/>'
                )
        elif op == "rect":
            x, y, w, h = kw["x"], kw["y"], kw["w"], kw["h"]
            fill = kw.get("fill")
            stroke = kw.get("stroke")
            width = kw.get("width")
            if fill:
                parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>')
            if stroke:
                parts.append(
                    f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="none" stroke="{stroke}" stroke-width="{width or 1}"/>'
                )
        elif op == "line":
            x1, y1, x2, y2 = kw["x1"], kw["y1"], kw["x2"], kw["y2"]
            stroke = kw.get("stroke")
            width = kw.get("width", 1)
            parts.append(f'<line x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}" stroke="{stroke}" stroke-width="{width}"/>')
        elif op == "polyline":
            pts = " ".join(f"{x},{y}" for x, y in kw["points"])
            closed = kw.get("closed", False)
            fill = kw.get("fill")
            stroke = kw.get("stroke")
            width = kw.get("width", 1)
            join = kw.get("join")
            dash = kw.get("dash")
            cap = kw.get("cap")
            if closed:
                tag = f'<polygon points="{pts}"'
            else:
                tag = f'<polyline points="{pts}"'
            attrs = []
            if fill and closed:
                attrs.append(f'fill="{fill}"')
            else:
                attrs.append('fill="none"')
            if stroke:
                attrs.append(f'stroke="{stroke}"')
                attrs.append(f'stroke-width="{width}"')
            if join:
                attrs.append(f'stroke-linejoin="{join}"')
            if cap and not closed:
                attrs.append(f'stroke-linecap="{cap}"')
            if dash:
                attrs.append('stroke-dasharray="' + ",".join(str(int(d)) for d in dash) + '"')
            parts.append(tag + " " + " ".join(attrs) + "/>")


# ---------------- PIL render of plan -----------------


def _emit_pil_plan(draw: ImageDraw.ImageDraw, plan: list[tuple[str, dict[str, Any]]], cx: int, cy: int, rot_deg: int):
    # render onto a temp layer if rotation is non-zero
    needs_rot = (rot_deg % 360) != 0
    if needs_rot:
        # estimate a box big enough for rotation
        box = max(
            64,
            max(
                [abs(int(p[1].get("x2", 0))) for p in plan if p[0] == "line"]
                + [abs(int(p[1].get("x", 0))) + int(p[1].get("w", 0)) for p in plan if p[0] == "rect"]
                + [abs(int(p[1].get("cx", 0))) + int(p[1].get("r", 0)) for p in plan if p[0] == "circle"]
            )
            * 3,
        )
        layer = Image.new("RGBA", (box, box), (0, 0, 0, 0))
        ld = ImageDraw.Draw(layer)
        cxl = cyl = box // 2

        def P(px: int, py: int) -> tuple[int, int]:
            return (cxl + px, cyl + py)

        for op, kw in plan:
            if op == "circle":
                r = int(kw["r"])
                fill = kw.get("fill")
                stroke = kw.get("stroke")
                width = int(kw.get("width", 1))
                cx0, cy0 = P(int(kw["cx"]), int(kw["cy"]))
                if fill:
                    ld.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], fill=_rgba(fill))
                if stroke:
                    # approximate stroked circle by thicker ellipse
                    ld.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], outline=_rgba(stroke), width=width)
            elif op == "rect":
                x, y, w, h = int(kw["x"]), int(kw["y"]), int(kw["w"]), int(kw["h"])
                fill = kw.get("fill")
                stroke = kw.get("stroke")
                width = int(kw.get("width", 1))
                x0, y0 = P(x, y)
                x1, y1 = P(x + w, y + h)
                if fill:
                    ld.rectangle([x0, y0, x1, y1], fill=_rgba(fill))
                if stroke:
                    ld.rectangle([x0, y0, x1, y1], outline=_rgba(stroke), width=width)
            elif op == "line":
                x1, y1, x2, y2 = int(kw["x1"]), int(kw["y1"]), int(kw["x2"]), int(kw["y2"])
                width = int(kw.get("width", 1))
                stroke = kw.get("stroke")
                ld.line([P(x1, y1), P(x2, y2)], fill=_rgba(str(stroke)), width=width)
            elif op == "polyline":
                pts = [P(int(x), int(y)) for (x, y) in kw["points"]]
                width = int(kw.get("width", 1))
                stroke = kw.get("stroke")
                fill = kw.get("fill")
                if kw.get("closed", False):
                    if fill:
                        ld.polygon(pts, fill=_rgba(fill))
                    if stroke:
                        ld.polygon(pts, outline=_rgba(stroke), width=width)
                else:
                    if stroke:
                        ld.line(pts, fill=_rgba(stroke), width=width)

        layer = layer.rotate(-rot_deg, resample=Image.Resampling.BICUBIC, expand=True)
        lw, lh = layer.size
        draw.im.alpha_composite(layer, (round(cx - lw / 2), round(cy - lh / 2)))
    else:
        for op, kw in plan:
            if op == "circle":
                r = int(kw["r"])
                fill = kw.get("fill")
                stroke = kw.get("stroke")
                width = int(kw.get("width", 1))
                cx0, cy0 = cx + int(kw["cx"]), cy + int(kw["cy"])
                if fill:
                    draw.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], fill=_rgba(fill))
                if stroke:
                    draw.ellipse([cx0 - r, cy0 - r, cx0 + r, cy0 + r], outline=_rgba(stroke), width=width)
            elif op == "rect":
                x, y, w, h = int(kw["x"]), int(kw["y"]), int(kw["w"]), int(kw["h"])
                fill = kw.get("fill")
                stroke = kw.get("stroke")
                width = int(kw.get("width", 1))
                x0, y0 = cx + x, cy + y
                x1, y1 = x0 + w, y0 + h
                if fill:
                    draw.rectangle([x0, y0, x1, y1], fill=_rgba(fill))
                if stroke:
                    draw.rectangle([x0, y0, x1, y1], outline=_rgba(stroke), width=width)
            elif op == "line":
                x1, y1, x2, y2 = int(kw["x1"]), int(kw["y1"]), int(kw["x2"]), int(kw["y2"])
                width = int(kw.get("width", 1))
                stroke = kw.get("stroke")
                draw.line([cx + x1, cy + y1, cx + x2, cy + y2], fill=_rgba(str(stroke)), width=width)

            elif op == "polyline":
                pts = [(cx + int(x), cy + int(y)) for (x, y) in kw["points"]]
                width = int(kw.get("width", 1))
                stroke = kw.get("stroke")
                fill = kw.get("fill")
                if kw.get("closed", False):
                    if fill:
                        draw.polygon(pts, fill=_rgba(fill))
                    if stroke:
                        draw.polygon(pts, outline=_rgba(stroke), width=width)
                else:
                    if stroke:
                        draw.line(pts, fill=_rgba(stroke), width=width)


def _rgba(svg_hex: str) -> tuple[int, int, int, int]:
    # svg_hex like "#rrggbb"
    r = int(svg_hex[1:3], 16)
    g = int(svg_hex[3:5], 16)
    b = int(svg_hex[5:7], 16)
    return (r, g, b, 255)


# -----------------------------------------------------------------------------
# PIL dashed stroker for Lines
# -----------------------------------------------------------------------------


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


# -----------------------------------------------------------------------------
# Exporter
# -----------------------------------------------------------------------------


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
        """Build the dispatch table from Formats → handler methods."""
        sups: dict[Formats, Callable[[Params], Path]] = {}
        for fmt in Formats:
            handler = getattr(cls, fmt.name, None)
            if not callable(handler):
                raise NotImplementedError(f"Exporter missing handler for '{fmt.name}'")
            sups[fmt] = handler  # pyright: ignore[reportArgumentType]
        cls.supported = sups
        return sups

    # ---------------- Internal helpers ----------------
    @staticmethod
    def _svg_string(params: Params) -> str:
        """Generate SVG markup as a single string."""
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
            if not lab.text:
                continue
            fill, fop = _col_and_opacity(lab.col)
            ta, db = lab.anchor.svg  # ("start"/"middle"/"end", baseline)
            parts.append(
                f'<text x="{lab.p.x}" y="{lab.p.y}" fill="{fill}" font-size="{lab.size}" '
                f'text-anchor="{ta}" dominant-baseline="{db}" transform="rotate({-lab.rotation} {lab.p.x} {lab.p.y})"{fop}>'
                f"{_escape(lab.text)}</text>"
            )

        # icons
        for ico in params.icons:
            bw, bh = ico.bbox_wh()
            cx, cy = ico.anchor._centre(ico.p.x, ico.p.y, bw, bh)

            # picture-backed
            if isinstance(ico, Picture_Icon):
                data, mime = _picture_bytes_and_mime(Path(ico.src))
                b64 = base64.b64encode(data).decode("ascii")
                parts.append(
                    f'<g transform="translate({cx} {cy}) rotate({-ico.rotation}) translate({-bw / 2} {-bh / 2})">'
                )
                parts.append(f'<image href="data:{mime};base64,{b64}" width="{bw}" height="{bh}"/>')
                parts.append("</g>")
                continue

            # vector built-ins using unified plan
            col_svg, cop = _col_and_opacity(ico.col)
            parts.append(f'<g transform="translate({cx} {cy}) rotate({-ico.rotation})">')
            _emit_svg_plan(parts, _builtin_icon_plan(ico.name, ico.size, col_svg))
            parts.append("</g>")

        parts.append("</svg>")
        return "\n".join(parts)

    # ---------------- Raster draw (PIL) ----------------
    @staticmethod
    def _draw(params: Params) -> Image.Image:
        img = Image.new("RGBA", (params.width, params.height), params.bg_mode.rgba)
        draw = ImageDraw.Draw(img)

        _draw_grid(draw, params)
        _draw_lines(draw, params)
        _draw_labels(img, params)

        # icons
        for ico in params.icons:
            bw, bh = ico.bbox_wh()
            cxw, cyw = ico.anchor._centre(ico.p.x, ico.p.y, bw, bh)

            if isinstance(ico, Picture_Icon):
                im = _open_rgba(Path(ico.src), bw, bh)
                rot = ico.rotation % 360
                if rot:
                    im = im.rotate(-rot, resample=Image.Resampling.BICUBIC, expand=True)
                x0 = round(cxw - im.width / 2)
                y0 = round(cyw - im.height / 2)
                img.alpha_composite(im, (x0, y0))
            else:
                col_svg, _ = _col_and_opacity(ico.col)  # rgb hex, ignore opacity here (we draw with full alpha)
                _emit_pil_plan(
                    draw,
                    _builtin_icon_plan(ico.name, ico.size, col_svg),
                    cxw,
                    cyw,
                    ico.rotation,
                )

        return img

    @staticmethod
    def _save_via_pil_rgb(params: Params, fmt: Formats) -> Path:
        """
        For opaque formats, draw with PIL directly if selected,
        else rasterise SVG then transcode to RGB.
        """
        if RASTER_BACKEND is RASTERISERS.pil:
            frame = Exporter._draw(params)
        else:
            # go via SVG → PNG bytes, then decode for PIL
            png_bytes = _rasterize_via_svg(params, Formats.png, Exporter._svg_string(params))
            if png_bytes is None:
                raise RuntimeError("Failed to rasterise to PNG for RGB export")
            frame = Image.open(io.BytesIO(png_bytes)).convert("RGBA")

        # composite onto solid background if canvas has transparency
        bg = Image.new("RGB", frame.size, params.bg_mode.rgb if params.bg_mode.alpha else (255, 255, 255))
        bg.paste(frame, mask=frame.split()[-1])  # A as mask
        bg.save(params.output_file, format=fmt.upper())
        return params.output_file

    # ---------------- Public handlers ----------------
    @staticmethod
    def svg(params: Params) -> Path:
        params.output_file.write_text(Exporter._svg_string(params), encoding="utf-8")
        return params.output_file

    @classmethod
    def webp(cls, params: Params) -> Path:
        if RASTER_BACKEND is RASTERISERS.pil:
            frame = cls._draw(params)
            frame.save(params.output_file, format=Formats.webp.upper(), lossless=True, method=6)
        else:
            raster = _rasterize_via_svg(params, Formats.webp, cls._svg_string(params))
            if raster is not None:
                params.output_file.write_bytes(raster)
        return params.output_file

    @classmethod
    def png(cls, params: Params) -> Path:
        if RASTER_BACKEND is RASTERISERS.pil:
            frame = cls._draw(params)
            frame.save(params.output_file, format=Formats.png.upper())
        else:
            raster = _rasterize_via_svg(params, Formats.png, cls._svg_string(params))
            if raster is not None:
                params.output_file.write_bytes(raster)
        return params.output_file

    @classmethod
    def jpg(cls, params: Params) -> Path:
        if RASTER_BACKEND is RASTERISERS.pil:
            return cls._save_via_pil_rgb(params, Formats.jpg)
        else:
            raster = _rasterize_via_svg(params, Formats.png, cls._svg_string(params))
            if raster is not None:
                params.output_file.write_bytes(raster)
        return params.output_file

    @classmethod
    def jpeg(cls, params: Params) -> Path:
        if RASTER_BACKEND is RASTERISERS.pil:
            return cls._save_via_pil_rgb(params, Formats.jpeg)
        else:
            raster = _rasterize_via_svg(params, Formats.png, cls._svg_string(params))
            if raster is not None:
                params.output_file.write_bytes(raster)
        return params.output_file

    @classmethod
    def bmp(cls, params: Params) -> Path:
        if RASTER_BACKEND is RASTERISERS.pil:
            return cls._save_via_pil_rgb(params, Formats.bmp)
        else:
            raster = _rasterize_via_svg(params, Formats.png, cls._svg_string(params))
            if raster is not None:
                params.output_file.write_bytes(raster)
        return params.output_file


# -----------------------------------------------------------------------------
# Raster sub-painters (PIL)
# -----------------------------------------------------------------------------


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
            lab.rotation,
            resample=Image.Resampling.BICUBIC,
            center=(lab.p.x, lab.p.y),
            expand=False,
        )
        img.alpha_composite(temp)


# -----------------------------------------------------------------------------
# SVG → raster backends
# -----------------------------------------------------------------------------


def _rasterize_via_svg(params: Params, fmt: Formats, svg_text: str) -> bytes | None:
    svg_bytes = svg_text.encode("utf-8")

    if RASTER_BACKEND is RASTERISERS.cairosvg:
        if fmt == Formats.png:
            png = cairosvg.svg2png(bytestring=svg_bytes, output_width=params.width, output_height=params.height)
            return png if isinstance(png, bytes) else None
        if fmt == Formats.webp:
            # cairosvg → PNG, then transcode with PIL
            png = cairosvg.svg2png(bytestring=svg_bytes, output_width=params.width, output_height=params.height)
            if not isinstance(png, bytes):
                return None
            img = Image.open(io.BytesIO(png)).convert("RGBA")
            buf = io.BytesIO()
            img.save(buf, format=fmt.upper(), lossless=True, method=6)
            return buf.getvalue()

    if RASTER_BACKEND is RASTERISERS.resvg:
        # requires `resvg` CLI on PATH
        with tempfile.NamedTemporaryFile(suffix="." + fmt.value, delete=False) as out:
            out_path = Path(out.name)
        try:
            subprocess.run(
                ["resvg", "-w", str(params.width), "-h", str(params.height), "-o", str(out_path), "-"],
                input=svg_bytes,
                check=True,
            )
            data = out_path.read_bytes()
            return data
        finally:
            out_path.unlink(missing_ok=True)

    raise RuntimeError("Unknown or unavailable SVG raster backend")


# Build the dispatch table immediately on import
Exporter.match_supported()
