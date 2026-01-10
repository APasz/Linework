# Linework

Linework is a small Qt app for drawing simple track diagrams and line drawings. It started because I just wanted a dead simple tool and could not find one that was not overkill, broken, paywalled, or missing the basics.

![Example output](example.webp)

## Features
- Draw lines with grid and cardinal snapping, multiple line styles, adjustable widths, and optional continuous mode
- Customize canvas size, background, grid, and colours for lines, labels, and icons
- Labels with size, rotation, colour, and anchor controls
- Built-in icon library (railway and electrical), plus importable picture icons
- Select, move, resize, and multi-select items with undo/redo
- Export to SVG, PNG, WEBP, JPG, and BMP
- Autosave and per-user defaults
- Eraser tool splits lines where you drag, letting you carve away segments without redrawing and toggle it with `E`

## Quick start
Requirements: Python 3.13+ with PySide6.

```bash
python -m pip install -r requirements.txt
python main.py
```

## Usage
- Select tool (V): click items to select; drag to move; drag line endpoints to adjust; drag empty space for marquee (Ctrl toggles/adds, Alt inverts grid snap)
- Draw tool (L): click-drag to draw (or click-click if "Drag to draw" is off); enable "Continuous draw" to chain lines; Ctrl inverts cardinal snap; Shift opens the editor; Alt inverts grid snap
- Label tool (T): click to add text; Shift opens the editor before placing; Alt inverts grid snap
- Icon tool (I): click to place; Ctrl opens the icon picker; Shift opens the editor; Alt inverts grid snap
- Eraser tool (E) [Draw]: drag along a line to split it at the cursor, then continue dragging to carve more segments while the tool stays active
- With Select active, double-click to edit; Ctrl+wheel zooms; Esc or right-click cancels the active tool

## Shortcuts
File and settings
- `Ctrl/Cmd+N`: New
- `Ctrl/Cmd+O`: Open
- `Ctrl/Cmd+S`: Save
- `Ctrl/Cmd+Shift+S`: Save As
- `Ctrl+E`: Export
- `Ctrl+,`: Settings

Edit and selection
- `Ctrl/Cmd+Z`: Undo
- `Ctrl/Cmd+Y` or `Ctrl/Cmd+Shift+Z`: Redo
- `Ctrl/Cmd+A`: Select all
- `Delete` or `Backspace`: Delete selection
- `Esc` or right-click: Cancel active tool

Tools
- `V`: Select tool
- `L`: Draw tool
- `T`: Label tool
- `I`: Icon tool
- `E`: Eraser tool [Draw]

## Files and formats
- Projects are saved as `.linework` (JSON)
- Autosaves live next to the project as `.linework.autosave`
- Export supports: SVG, PNG, WEBP, JPG, BMP
- Imported icons are copied into `assets/icons` next to the project

## Settings and storage
- Settings are stored as `linework.settings` (JSON)
- Default location is the platform config dir; choose Portable in Settings to store alongside the app/script (requires a writable folder)
- Override the settings path with `LINEWORK_SETTINGS_PATH` or `--settings PATH`
- Defaults include the startup project and window sizing preferences

## Command line
```bash
python main.py [--settings PATH] [project.linework]
```
- `--settings` or `--settings-path` accepts a file or directory
- Passing a `.linework` file opens it on launch

## Optional dependencies
- `cairosvg` enables SVG icon import and SVG-based rasterisation. On Linux it requires Cairo/Pango system libraries.
