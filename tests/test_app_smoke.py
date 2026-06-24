from __future__ import annotations

import tkinter as tk
import unittest

from ui.app import PTAExporterApp


class AppSmokeTests(unittest.TestCase):
    def test_app_initializes_without_starting_browser(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            self.assertEqual("准备就绪", app.status_var.get())
            self.assertEqual("尚未开始导出", app.export_summary_var.get())
            app.scraper.shutdown()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
