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

    def test_readme_keeps_public_user_facing_scope(self) -> None:
        readme = Path("README.md").read_text(encoding="utf-8")

        self.assertIn("面向 Windows", readme)
        self.assertIn("当前账号、入口 URL、已选导出项数量", readme)
        self.assertNotIn("## 隐私说明", readme)
        self.assertNotIn("1234html/", readme)
        self.assertNotIn("浏览器配置目录与会话数据", readme)
        self.assertNotIn("private/", readme)


if __name__ == "__main__":
    unittest.main()
