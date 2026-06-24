from __future__ import annotations

import unittest
from pathlib import Path


class RepoHygieneTests(unittest.TestCase):
    def test_gitignore_keeps_private_local_data_out_of_repo(self) -> None:
        gitignore = Path(".gitignore").read_text(encoding="utf-8")

        self.assertIn("AGENTS.md", gitignore)
        self.assertIn("1234html/", gitignore)
        self.assertIn("private/", gitignore)
        self.assertIn(".appdata/", gitignore)
        self.assertIn("dist/", gitignore)
        self.assertIn("runtime/", gitignore)
        self.assertNotIn("PTADocxExporter/", gitignore)

    def test_readme_mentions_windows_and_local_private_samples(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("面向 Windows", readme)
        self.assertIn("1234html/", readme)
        self.assertIn("浏览器配置目录与会话数据应仅保留在本地", readme)
        self.assertIn("当前账号、入口 URL、已选导出项数量", readme)


if __name__ == "__main__":
    unittest.main()
