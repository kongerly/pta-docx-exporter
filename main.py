from __future__ import annotations

import tkinter as tk

from ui.app import PTAExporterApp


def main() -> None:
    root = tk.Tk()
    PTAExporterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
