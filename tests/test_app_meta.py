from __future__ import annotations

import unittest
from pathlib import Path

from app_meta import APP_DISPLAY_NAME, APP_ID, APP_VERSION, build_window_title
from app_text import UiText


class AppMetaTests(unittest.TestCase):
    def test_version_text_stays_in_sync(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")
        spec_text = Path("build/pta_docx_exporter.spec").read_text(encoding="utf-8")
        build_script = Path("build/build.ps1").read_text(encoding="utf-8")

        self.assertEqual(f"{APP_DISPLAY_NAME} v{APP_VERSION}", build_window_title())
        self.assertEqual(f"当前版本：v{APP_VERSION}", UiText.VERSION_LABEL)
        self.assertIn(f"当前版本：`v{APP_VERSION}`", readme)
        self.assertIn("from app_meta import APP_ID", spec_text)
        self.assertIn("name=APP_ID", spec_text)
        self.assertIn("APP_ID", build_script)
        self.assertIn('"app_id": APP_ID', build_script)
        self.assertIn('$appMeta.app_id', build_script)


if __name__ == "__main__":
    unittest.main()
