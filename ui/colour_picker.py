from __future__ import annotations

import colorsys
import tkinter as tk
from tkinter import ttk

from PIL import Image, ImageTk

from models.geo import CanvasLW
from models.styling import Colour, Colours
from ui.composite_spinbox import Composite_Spinbox


def _checker_photo(master, w=20, h=20, tile=4, a="#eeeeee", b="#cccccc") -> ImageTk.PhotoImage:
    img = Image.new("RGB", (w, h), a)
    for y in range(0, h, tile):
        start = ((y // tile) % 2) * tile
        for x in range(start, w, tile * 2):
            Image.Image.paste(img, b, (x, y, x + tile, y + tile))
    return ImageTk.PhotoImage(img, master=master)


def ask_colour(master: tk.Misc, initial: Colour | None = None) -> Colour | None:
    top = tk.Toplevel(master)
    top.title("Custom Colour")
    top.resizable(False, False)
    top.transient(master.winfo_toplevel())

    base = initial or Colours.white
    h0, s0, v0 = colorsys.rgb_to_hsv(base.red / 255.0, base.green / 255.0, base.blue / 255.0)

    state = {
        "r": base.red,
        "g": base.green,
        "b": base.blue,
        "a": base.alpha,
        "h": h0,
        "s": s0,
        "v": v0,
    }

    updating = False

    hex_var = tk.StringVar(value=base.hexah)
    r_var = tk.StringVar(value=str(base.red))
    g_var = tk.StringVar(value=str(base.green))
    b_var = tk.StringVar(value=str(base.blue))
    a_var = tk.StringVar(value=str(base.alpha))

    result: Colour | None = None

    def _clamp_int(v, low=0, high=255) -> int:
        try:
            iv = int(round(float(v)))
        except Exception:
            iv = low
        if iv < low:
            return low
        if iv > high:
            return high
        return iv

    def _clamp_float(v, low=0.0, high=1.0) -> float:
        try:
            fv = float(v)
        except Exception:
            fv = low
        if fv < low:
            return low
        if fv > high:
            return high
        return fv

    def _rgb_to_hsv(r: int, g: int, b: int) -> tuple[float, float, float]:
        return colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

    def _hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return int(round(r * 255)), int(round(g * 255)), int(round(b * 255))

    def _parse_hex() -> Colour | None:
        raw = hex_var.get().strip()
        if not raw:
            return None
        try:
            col = Colours.parse_colour(raw)
        except Exception:
            return None
        hx = raw.removeprefix("#").replace(" ", "")
        if len(hx) == 6:
            return col.with_alpha(state["a"])
        return col

    def _set_state_from_rgb(r: int, g: int, b: int, a: int | None = None) -> None:
        nonlocal updating
        if updating:
            return
        updating = True
        r = _clamp_int(r)
        g = _clamp_int(g)
        b = _clamp_int(b)
        if a is None:
            a = state["a"]
        a = _clamp_int(a)
        old_h = state["h"]
        old_rgb = (state["r"], state["g"], state["b"])
        h, s, v = _rgb_to_hsv(r, g, b)
        state.update(r=r, g=g, b=b, a=a, h=h, s=s, v=v)
        _sync_ui(update_sv=abs(h - old_h) > 1e-6, update_alpha_strip=(r, g, b) != old_rgb)
        updating = False

    def _set_state_from_hsv(h: float, s: float, v: float) -> None:
        nonlocal updating
        if updating:
            return
        updating = True
        h = _clamp_float(h)
        s = _clamp_float(s)
        v = _clamp_float(v)
        old_h = state["h"]
        old_rgb = (state["r"], state["g"], state["b"])
        r, g, b = _hsv_to_rgb(h, s, v)
        state.update(r=r, g=g, b=b, h=h, s=s, v=v)
        _sync_ui(update_sv=abs(h - old_h) > 1e-6, update_alpha_strip=(r, g, b) != old_rgb)
        updating = False

    def _set_alpha(a: int) -> None:
        nonlocal updating
        if updating:
            return
        updating = True
        state["a"] = _clamp_int(a)
        _sync_ui(update_sv=False, update_alpha_strip=False)
        updating = False

    def _on_rgba_change() -> None:
        _set_state_from_rgb(r_var.get(), g_var.get(), b_var.get(), a_var.get())

    def _commit_hex(_e=None) -> None:
        col = _parse_hex()
        if not col:
            top.bell()
            return
        _set_state_from_rgb(col.red, col.green, col.blue, col.alpha)

    def _on_ok() -> None:
        nonlocal result
        result = Colour(red=state["r"], green=state["g"], blue=state["b"], alpha=state["a"])
        top.destroy()

    def _on_cancel() -> None:
        top.destroy()

    PREVIEW_SIZE = 60
    SV_SIZE = 180
    STRIP_W = 160
    STRIP_H = 14

    frame = ttk.Frame(top, padding=8)
    frame.grid(row=0, column=0, sticky="nsew")

    controls = ttk.Frame(frame)
    controls.grid(row=0, column=0, sticky="nw")
    sv_frame = ttk.Frame(frame)
    sv_frame.grid(row=0, column=1, sticky="nw", padx=(10, 0))

    preview = CanvasLW(controls, width=PREVIEW_SIZE, height=PREVIEW_SIZE, highlightthickness=1)
    preview.configure(
        highlightbackground=Colours.sys.dark_gray.hexh,
        highlightcolor=Colours.sys.dark_gray.hexh,
    )
    preview.grid(row=0, column=0, rowspan=3, padx=(0, 8), pady=2)
    preview_bg = _checker_photo(preview, w=PREVIEW_SIZE, h=PREVIEW_SIZE, tile=6)
    preview.create_image(0, 0, image=preview_bg, anchor="nw")
    preview_rect = preview.create_rectangle(
        1,
        1,
        PREVIEW_SIZE - 1,
        PREVIEW_SIZE - 1,
        outline=Colours.sys.dark_gray.hexh,
    )

    ttk.Label(controls, text="").grid(row=0, column=1, sticky="w")
    hex_entry = ttk.Entry(controls, textvariable=hex_var, width=12)
    hex_entry.grid(row=0, column=2, sticky="w")

    rgba_frame = ttk.Frame(controls)
    rgba_frame.grid(row=1, column=1, columnspan=2, sticky="w", pady=(6, 0))

    ttk.Label(rgba_frame, text="R").grid(row=0, column=0, padx=4)
    ttk.Label(rgba_frame, text="G").grid(row=0, column=1, padx=4)
    ttk.Label(rgba_frame, text="B").grid(row=0, column=2, padx=4)
    ttk.Label(rgba_frame, text="A").grid(row=0, column=3, padx=4)

    spin_r = Composite_Spinbox(
        rgba_frame,
        from_=0,
        to=255,
        increment=1,
        width=4,
        textvariable=r_var,
        command=_on_rgba_change,
    )
    spin_g = Composite_Spinbox(
        rgba_frame,
        from_=0,
        to=255,
        increment=1,
        width=4,
        textvariable=g_var,
        command=_on_rgba_change,
    )
    spin_b = Composite_Spinbox(
        rgba_frame,
        from_=0,
        to=255,
        increment=1,
        width=4,
        textvariable=b_var,
        command=_on_rgba_change,
    )
    spin_a = Composite_Spinbox(
        rgba_frame,
        from_=0,
        to=255,
        increment=1,
        width=4,
        textvariable=a_var,
        command=_on_rgba_change,
    )

    spin_r.grid(row=1, column=0, padx=4)
    spin_g.grid(row=1, column=1, padx=4)
    spin_b.grid(row=1, column=2, padx=4)
    spin_a.grid(row=1, column=3, padx=4)

    strip_frame = ttk.Frame(controls)
    strip_frame.grid(row=2, column=1, columnspan=2, sticky="w", pady=(6, 0))

    ttk.Label(sv_frame, text="Saturation / Value").pack(anchor="w")
    sv_canvas = CanvasLW(sv_frame, width=SV_SIZE, height=SV_SIZE, highlightthickness=1)
    sv_canvas.configure(
        highlightbackground=Colours.sys.dark_gray.hexh,
        highlightcolor=Colours.sys.dark_gray.hexh,
    )
    sv_canvas.pack()
    sv_img_id = sv_canvas.create_image(0, 0, anchor="nw")
    sv_marker_outer = sv_canvas.create_oval(0, 0, 0, 0, outline="black", width=2)
    sv_marker_inner = sv_canvas.create_oval(0, 0, 0, 0, outline="white", width=2)

    hue_frame = ttk.Frame(strip_frame)
    hue_frame.grid(row=0, column=0, padx=(0, 12))
    ttk.Label(hue_frame, text="Hue").pack(anchor="w")
    hue_canvas = CanvasLW(hue_frame, width=STRIP_W, height=STRIP_H, highlightthickness=1)
    hue_canvas.configure(
        highlightbackground=Colours.sys.dark_gray.hexh,
        highlightcolor=Colours.sys.dark_gray.hexh,
    )
    hue_canvas.pack()

    alpha_frame = ttk.Frame(strip_frame)
    alpha_frame.grid(row=0, column=1)
    ttk.Label(alpha_frame, text="Alpha").pack(anchor="w")
    alpha_canvas = CanvasLW(alpha_frame, width=STRIP_W, height=STRIP_H, highlightthickness=1)
    alpha_canvas.configure(
        highlightbackground=Colours.sys.dark_gray.hexh,
        highlightcolor=Colours.sys.dark_gray.hexh,
    )
    alpha_canvas.pack()
    alpha_img_id = alpha_canvas.create_image(0, 0, anchor="nw")
    alpha_marker_outer = alpha_canvas.create_line(0, 0, 0, STRIP_H, fill="white", width=3)
    alpha_marker_inner = alpha_canvas.create_line(0, 0, 0, STRIP_H, fill="black", width=1)

    def _checker_image(w: int, h: int, tile: int = 6) -> Image.Image:
        img = Image.new("RGB", (w, h), "#EEEEEE")
        for y in range(0, h, tile):
            start = ((y // tile) % 2) * tile
            for x in range(start, w, tile * 2):
                Image.Image.paste(img, "#CCCCCC", (x, y, x + tile, y + tile))
        return img

    def _sv_square_photo(hue: float) -> ImageTk.PhotoImage:
        img = Image.new("RGB", (SV_SIZE, SV_SIZE))
        for y in range(SV_SIZE):
            v = 1.0 - (y / (SV_SIZE - 1) if SV_SIZE > 1 else 0.0)
            for x in range(SV_SIZE):
                s = x / (SV_SIZE - 1) if SV_SIZE > 1 else 0.0
                r, g, b = colorsys.hsv_to_rgb(hue, s, v)
                img.putpixel((x, y), (int(round(r * 255)), int(round(g * 255)), int(round(b * 255))))
        return ImageTk.PhotoImage(img, master=top)

    def _hue_strip_photo() -> ImageTk.PhotoImage:
        img = Image.new("RGB", (STRIP_W, STRIP_H))
        for x in range(STRIP_W):
            h = x / (STRIP_W - 1) if STRIP_W > 1 else 0.0
            r, g, b = colorsys.hsv_to_rgb(h, 1.0, 1.0)
            col = (int(round(r * 255)), int(round(g * 255)), int(round(b * 255)))
            for y in range(STRIP_H):
                img.putpixel((x, y), col)
        return ImageTk.PhotoImage(img, master=top)

    def _alpha_strip_photo(col: Colour) -> ImageTk.PhotoImage:
        base_img = _checker_image(STRIP_W, STRIP_H, tile=4).convert("RGBA")
        overlay = Image.new("RGBA", (STRIP_W, STRIP_H))
        for x in range(STRIP_W):
            a = int(round(255 * (x / (STRIP_W - 1) if STRIP_W > 1 else 1.0)))
            for y in range(STRIP_H):
                overlay.putpixel((x, y), (col.red, col.green, col.blue, a))
        comp = Image.alpha_composite(base_img, overlay)
        return ImageTk.PhotoImage(comp, master=top)

    sv_photo: ImageTk.PhotoImage | None = None
    alpha_photo: ImageTk.PhotoImage | None = None

    hue_photo = _hue_strip_photo()
    hue_img_id = hue_canvas.create_image(0, 0, anchor="nw", image=hue_photo)
    hue_marker_outer = hue_canvas.create_line(0, 0, 0, STRIP_H, fill="white", width=3)
    hue_marker_inner = hue_canvas.create_line(0, 0, 0, STRIP_H, fill="black", width=1)

    def _update_preview(col: Colour) -> None:
        if col.alpha == 0:
            preview.itemconfigure(preview_rect, fill="", stipple="")
        else:
            preview.itemconfigure(
                preview_rect,
                fill=col.hexh,
                stipple=CanvasLW._stipple_for_alpha(col.alpha) or "",
            )

    def _update_sv_image(hue: float) -> None:
        nonlocal sv_photo
        sv_photo = _sv_square_photo(hue)
        sv_canvas.itemconfigure(sv_img_id, image=sv_photo)

    def _update_alpha_strip(col: Colour) -> None:
        nonlocal alpha_photo
        alpha_photo = _alpha_strip_photo(col)
        alpha_canvas.itemconfigure(alpha_img_id, image=alpha_photo)

    def _move_sv_marker() -> None:
        x = int(round(state["s"] * (SV_SIZE - 1))) if SV_SIZE > 1 else 0
        y = int(round((1.0 - state["v"]) * (SV_SIZE - 1))) if SV_SIZE > 1 else 0
        x = max(0, min(SV_SIZE - 1, x))
        y = max(0, min(SV_SIZE - 1, y))
        sv_canvas.coords(sv_marker_outer, x - 5, y - 5, x + 5, y + 5)
        sv_canvas.coords(sv_marker_inner, x - 4, y - 4, x + 4, y + 4)

    def _move_hue_marker() -> None:
        x = int(round(state["h"] * (STRIP_W - 1))) if STRIP_W > 1 else 0
        x = max(0, min(STRIP_W - 1, x))
        hue_canvas.coords(hue_marker_outer, x, 0, x, STRIP_H)
        hue_canvas.coords(hue_marker_inner, x, 0, x, STRIP_H)

    def _move_alpha_marker() -> None:
        x = int(round((state["a"] / 255.0) * (STRIP_W - 1))) if STRIP_W > 1 else 0
        x = max(0, min(STRIP_W - 1, x))
        alpha_canvas.coords(alpha_marker_outer, x, 0, x, STRIP_H)
        alpha_canvas.coords(alpha_marker_inner, x, 0, x, STRIP_H)

    def _sync_ui(*, update_sv: bool, update_alpha_strip: bool) -> None:
        col = Colour(red=state["r"], green=state["g"], blue=state["b"], alpha=state["a"])
        _update_preview(col)
        hex_var.set(col.hexah)
        spin_r.set(state["r"])
        spin_g.set(state["g"])
        spin_b.set(state["b"])
        spin_a.set(state["a"])
        _move_sv_marker()
        _move_hue_marker()
        _move_alpha_marker()
        if update_sv:
            _update_sv_image(state["h"])
        if update_alpha_strip:
            _update_alpha_strip(col)

    def _on_sv_event(e) -> None:
        x = max(0, min(SV_SIZE - 1, e.x))
        y = max(0, min(SV_SIZE - 1, e.y))
        s = x / (SV_SIZE - 1) if SV_SIZE > 1 else 0.0
        v = 1.0 - (y / (SV_SIZE - 1) if SV_SIZE > 1 else 0.0)
        _set_state_from_hsv(state["h"], s, v)

    def _on_hue_event(e) -> None:
        x = max(0, min(STRIP_W - 1, e.x))
        h = x / (STRIP_W - 1) if STRIP_W > 1 else 0.0
        _set_state_from_hsv(h, state["s"], state["v"])

    def _on_alpha_event(e) -> None:
        x = max(0, min(STRIP_W - 1, e.x))
        a = int(round(255 * (x / (STRIP_W - 1) if STRIP_W > 1 else 1.0)))
        _set_alpha(a)

    sv_canvas.bind("<Button-1>", _on_sv_event)
    sv_canvas.bind("<B1-Motion>", _on_sv_event)
    hue_canvas.bind("<Button-1>", _on_hue_event)
    hue_canvas.bind("<B1-Motion>", _on_hue_event)
    alpha_canvas.bind("<Button-1>", _on_alpha_event)
    alpha_canvas.bind("<B1-Motion>", _on_alpha_event)

    hex_entry.bind("<Return>", _commit_hex)
    hex_entry.bind("<FocusOut>", _commit_hex)

    _sync_ui(update_sv=True, update_alpha_strip=True)

    btns = ttk.Frame(controls)
    btns.grid(row=3, column=1, columnspan=2, sticky="w", pady=(6, 0))
    ttk.Button(btns, text="Cancel", command=_on_cancel).pack(side="right", padx=(4, 0))
    ttk.Button(btns, text="OK", command=_on_ok).pack(side="right")

    top.protocol("WM_DELETE_WINDOW", _on_cancel)
    top.update_idletasks()
    try:
        top.wait_visibility()
    except tk.TclError:
        pass
    try:
        top.grab_set()
    except tk.TclError:
        pass
    top.wait_window()
    return result
