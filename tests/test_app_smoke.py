from __future__ import annotations

import tkinter as tk
import unittest

from app_text import UiText
from ui.app import PTAExporterApp


class AppSmokeTests(unittest.TestCase):
    def test_app_initializes_without_starting_browser(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            self.assertEqual(UiText.READY, app.status_var.get())
            self.assertEqual(UiText.NO_EXPORT_YET, app.export_summary_var.get())
            app.scraper.shutdown()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
