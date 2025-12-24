# Linework

Linework is a small Tkinter app for drawing simple track diagrams and line drawings. It started because I just wanted a dead simple tool and could not find one that was not overkill, broken, paywalled, or missing the basics.

![Example output](signals.webp)

## Features
- Draw lines with grid and cardinal snapping, multiple line styles, and adjustable widths
- Labels with size, rotation, color, and anchor controls
- Built-in icon library (railway and electrical), plus importable picture icons
- Select, move, resize, and multi-select items with undo/redo
- Export to SVG, PNG, WEBP, JPG, and BMP
- Autosave and per-user defaults

## Quick start
Requirements: Python 3.13+ with Tkinter. On Linux you may need `python3-tk`.

```bash
python -m pip install -r requirements.txt
python main.py
```

## Usage
- Draw tool: click-drag to draw (or click-click if "Drag to draw" is off)
- Select tool: drag items to move, drag handles to adjust, drag empty space for marquee select
- Icon tool: Ctrl-click to open the icon picker, Shift-click to edit on placement
- Label tool: click to add text, Shift-click to edit before placing
- Double-click any item to edit its properties

## Shortcuts
- `Ctrl/Cmd+S`: Save
- `Ctrl/Cmd+Shift+S`: Save As
- `Ctrl/Cmd+Z`: Undo
- `Ctrl/Cmd+Y` or `Ctrl/Cmd+Shift+Z`: Redo
- `Ctrl/Cmd+A`: Select all
- `G`: Toggle grid
- `Delete` or `Backspace`: Delete selection

## Files and formats
- Projects are saved as `.linework` (JSON)
- Autosaves live next to the project as `.linework.autosave`
- Export supports: SVG, PNG, WEBP, JPG, BMP
- Imported icons are copied into `assets/icons` next to the project

## Optional dependencies
- `cairosvg` enables SVG icon import and SVG-based rasterization. On Linux it requires Cairo/Pango system libraries.