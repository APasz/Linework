"""Application entry point for Linework"""

import sys
import tkinter as tk

from controllers.app import App

MIN_PYTHON: tuple[int, int] = (3, 13)


def main() -> None:
    """Run Linework"""
    if sys.version_info < MIN_PYTHON:
        raise RuntimeError("Linework requires Python 3.13+")
    root = tk.Tk()
    App(root)
    try:
        root.mainloop()
    except tk.TclError as xcp:
        if "application has been destroyed" not in str(xcp):
            raise


if __name__ == "__main__":
    main()
