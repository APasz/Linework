import tkinter as tk

from controllers.app import App


def main():
    root = tk.Tk()
    App(root)
    try:
        root.mainloop()
    except tk.TclError as xcp:
        if "application has been destroyed" not in str(xcp):
            raise


if __name__ == "__main__":
    main()
