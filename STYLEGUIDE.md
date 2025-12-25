# Project Style Guide

This is the **style contract** for this repo. Tools (Ruff, Pylance, etc.) handle the mechanical stuff; this guide covers the judgment calls and project-specific conventions

## Python baseline

* Target Python: **3.13+** (type syntax uses `X | None`, `list[T]`, etc)
* Prefer `pathlib.Path` over `os.path`
* Prefer `collections.abc` over `typing`

## Formatting

* Use Ruff formatter as the single formatter
* Indentation: 4 spaces
* Line length: **120**
* One statement per line

## Naming

### General

* Functions, methods, variables: **snake_case**
* Classes, exceptions, enums: **PascalCase**
* Constants: **UPPER_SNAKE_CASE**

### Spelling and vocabulary

* Prefer **British spelling**: `colour`, not `color`
* Use descriptive names over single-letter names

  * Single-letter names allowed only for tiny scopes (≈10 lines) or strong conventions (i/j/k indices, x/y/z coordinates). Otherwise, use descriptive names (e.g. colour over c)

### Domain types

Match domain vocabulary in names:

* `colour: Colour` not `color_hex: str` when you mean a `Colour` object
* Use `path: Path` for filesystem paths
* Use `event: tk.Event` for tkinter events

## Imports

Order imports in these blocks, separated by one blank line:

1. `__future__`
2. Standard library
3. Third-party
4. Local application imports

Example:

```py
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import tkinter as tk

try:
    import sv_ttk
except Exception:
    sv_ttk = None

from mypkg.widgets import Widget
```

### Optional dependencies

* Optional imports should default to catching ImportError with `try/except`
* If you catch `Exception`, it must be **deliberate** (dependency may not exist). Prefer `ImportError` when possible

## Type hints

### Required

* All public functions/methods must have complete type hints.
* Internal helpers should be typed too unless trivially obvious.
* Use `X | None` rather than `Optional[X]`.
* Use built-in generics: `list[T]`, `dict[K, V]`, `tuple[...]`.
* Use `collections.abc` for protocols like `Callable`, `Iterator`, etc.

### Any

* `Any` is allowed only when:

  * it’s genuinely dynamic boundary code (UI widgets, JSON, external IO), or
  * typing it correctly would require ugly contortions.
* If `Any` leaks, contain it (cast locally or convert at the boundary).

### Return types

* Prefer explicit return types (`-> None` for procedures).
* Use `-> bool` and return a meaningful result when it helps control flow.

## Docstrings

Docstrings are written in **Google style**, matching the project’s `autodocstring.mustache` template

### When to write docstrings

* Required for:

  * public modules
  * public classes
  * public methods/functions
  * anything non-obvious that another contributor will touch
* Optional for:

  * small private helpers where the name + types make intent obvious

### Template rules

* **Do not** include type declarations in docstring sections (types belong in type hints).
* Section headings end with a **semicolon**, exactly:

  * `Args;`
  * `Raises;`
  * `Returns;`
  * `Yields;`

### Example

```py
def snap(point: Point, *, ignore_grid: bool = False) -> Point:
    """Clamp or snap a point to the current grid.

    Snaps to the nearest grid intersection when grid snapping is enabled.

    Args;
        point: The input point.
        ignore_grid: If true, only clamp to canvas bounds.

    Returns;
        The clamped or snapped point.
    """
```

## Comments and sectioning

* Prefer readable code over comments
* Use section headers sparingly; when used, keep them consistent:

  * short UI/structure separators (e.g. `# ---------- theme ----------`)
  * big region separators (e.g. `# ========= selection =========`)
* Avoid commentary like “obviously” or emotional outbursts in comments

## Error handling

* Prefer narrow exception types when feasible
* If you catch `Exception`, either:

  * handle it meaningfully (show message, fallback), or
  * document why ignoring it is safe.
* Never silently discard errors in core logic without at least a comment.

## UI / Tkinter specifics

* Use `tk` alias: `import tkinter as tk`
* Prefer a single “safe UI call” helper for operations that may fail during shutdown
* Event handlers:

  * accept `event: tk.Event | None = None` when they can be called both by UI and by code
  * if returning `"break"` is needed to stop propagation, do it consistently

## Data and mutation

* Make mutation obvious

  * Use `inplace_*` naming or `inplace=True` keyword when it matters
* Keep state grouped logically (UI vars vs model params vs caches)

## “Don’ts” (the stuff that bloats diffs)

* Don’t rename variables/classes just to match personal taste
* Don’t reorder imports manually; run the tool
* Don’t reflow docstrings unless you’re changing meaning
* Don’t change public API names during a style pass
* Don’t introduce new patterns unless you’re also migrating old ones
