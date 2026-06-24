from __future__ import annotations

import unittest

from app_text import UiText


class AppTextTests(unittest.TestCase):
    def test_export_summary_includes_failed_total_and_category_rollup(self) -> None:
        summary = UiText.export_summary(
            exported_count=2,
            parsed_total=18,
            expected_total=20,
            warning_count=4,
            failed_total=2,
            missing_problem_warning_count=1,
            page_warning_count=1,
            image_warning_count=2,
        )

        self.assertIn("2 个导出项", summary)
        self.assertIn("18/20 题成功", summary)
        self.assertIn("缺失 2 题", summary)
        self.assertIn("4 条警告", summary)
        self.assertIn("漏题 1 条", summary)
        self.assertIn("页面异常 1 条", summary)
        self.assertIn("图片异常 2 条", summary)

    def test_export_warning_category_lines_skip_zero_categories(self) -> None:
        lines = UiText.export_warning_category_lines(
            missing_problem_warning_count=0,
            page_warning_count=2,
            image_warning_count=0,
            content_warning_count=1,
        )

        self.assertEqual(["页面异常 2 条", "乱码修复提示 1 条"], lines)


if __name__ == "__main__":
    unittest.main()
