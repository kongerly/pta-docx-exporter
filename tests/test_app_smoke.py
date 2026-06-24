from __future__ import annotations

import tkinter as tk
import unittest
from pathlib import Path

from app_text import UiText
from models import ExportResult, ExportSourceSummary, ExportSummary, ExportWarning, ProblemSetSummary
from ui.app import PTAExporterApp


class AppSmokeTests(unittest.TestCase):
    @staticmethod
    def _ttk_state(widget) -> str:
        return "disabled" if widget.instate(["disabled"]) else "normal"

    def test_app_initializes_without_starting_browser(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            self.assertEqual(UiText.READY, app.status_var.get())
            self.assertEqual(UiText.NO_EXPORT_YET, app.export_summary_var.get())
            self.assertEqual("normal", self._ttk_state(app.login_button))
            self.assertEqual("normal", self._ttk_state(app.switch_account_button))
            self.assertEqual("disabled", self._ttk_state(app.confirm_account_button))
            self.assertEqual("disabled", self._ttk_state(app.load_problem_sets_button))
            self.assertEqual("disabled", self._ttk_state(app.export_button))
            self.assertEqual("disabled", self._ttk_state(app.add_to_queue_button))
            self.assertEqual("disabled", self._ttk_state(app.remove_from_queue_button))
            self.assertEqual("disabled", self._ttk_state(app.move_up_button))
            self.assertEqual("disabled", self._ttk_state(app.move_down_button))
            app.scraper.shutdown()
        finally:
            root.destroy()

    def test_buttons_follow_login_loaded_data_and_queue_state(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            app._after_login_window_opened({})
            self.assertEqual("disabled", self._ttk_state(app.load_problem_sets_button))
            self.assertEqual("normal", self._ttk_state(app.confirm_account_button))

            app._apply_auth_state(
                {
                    "authenticated": True,
                    "accountId": "demo-user",
                    "displayName": "Demo User",
                }
            )
            self.assertEqual("disabled", self._ttk_state(app.confirm_account_button))
            self.assertEqual("normal", self._ttk_state(app.load_problem_sets_button))

            first = ProblemSetSummary(id="set-1", title="题目集一", url="https://pintia.cn/problem-sets/set-1/overview")
            second = ProblemSetSummary(id="set-2", title="题目集二", url="https://pintia.cn/problem-sets/set-2/overview")
            app._after_load_problem_sets([first, second])
            self.assertEqual("normal", self._ttk_state(app.add_to_queue_button))

            app.export_queue = [
                ExportSourceSummary.from_problem_set(first),
                ExportSourceSummary.from_problem_set(second),
            ]
            app._refresh_export_queue_view()
            app.export_queue_list.selection_set(0)
            root.update_idletasks()
            app._refresh_ui_state()
            self.assertEqual("normal", self._ttk_state(app.export_button))
            self.assertEqual("normal", self._ttk_state(app.remove_from_queue_button))
            self.assertEqual("disabled", self._ttk_state(app.move_up_button))
            self.assertEqual("normal", self._ttk_state(app.move_down_button))

            app.export_queue_list.selection_clear(0, tk.END)
            app.export_queue_list.selection_set(1)
            root.update_idletasks()
            app._refresh_ui_state()
            self.assertEqual("normal", self._ttk_state(app.move_up_button))
            self.assertEqual("disabled", self._ttk_state(app.move_down_button))
            app.scraper.shutdown()
        finally:
            root.destroy()

    def test_structure_change_error_is_rewritten_with_actionable_hint(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            message = app._format_error_message(RuntimeError("未发现可导出的题型：网络课程。可能是 PTA 页面结构已变化。"))
            self.assertIn("页面结构变化导致抓取失败", message)
            self.assertIn("请先确认当前页面已经正常打开", message)
            app.scraper.shutdown()
        finally:
            root.destroy()

    def test_account_mismatch_error_is_rewritten_with_actionable_hint(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            message = app._format_error_message(
                RuntimeError("当前登录账号“Account A”与目标账号“account-b”不一致，请切换账号后重试。")
            )
            self.assertIn("与目标账号", message)
            self.assertIn("请点击“重新登录”", message)
            self.assertIn("重新确认账号", message)
            app.scraper.shutdown()
        finally:
            root.destroy()

    def test_export_request_summary_includes_account_source_and_queue_preview(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            app._apply_auth_state(
                {
                    "authenticated": True,
                    "accountId": "demo-user",
                    "displayName": "Demo User",
                }
            )
            first = ProblemSetSummary(id="set-1", title="题目集一", url="https://pintia.cn/problem-sets/set-1/overview")
            second = ProblemSetSummary(id="set-2", title="题目集二", url="https://pintia.cn/problem-sets/set-2/overview")
            app.export_queue = [
                ExportSourceSummary.from_problem_set(first),
                ExportSourceSummary.from_problem_set(second),
            ]

            summary = app._build_export_request_summary(Path("D:/exports"), "separate")

            self.assertIn("当前账号：Demo User (demo-user)", summary)
            self.assertIn("抓取来源：入口：", summary)
            self.assertIn("导出项预览：", summary)
            self.assertIn("1. 题目集一", summary)
            self.assertIn("2. 题目集二", summary)
            app.scraper.shutdown()
        finally:
            root.destroy()

    def test_export_warning_details_are_grouped_by_category(self) -> None:
        root = tk.Tk()
        root.withdraw()
        try:
            app = PTAExporterApp(root)
            result = ExportResult(
                output_path="D:/exports/out.docx",
                warnings=[
                    "题目集《A》可能漏题：预期 3 题，实际抓到 2 题。",
                    "题目《B》页面暂不可用：用户不存在",
                    "题目《C》的图片下载失败：timeout",
                ],
                warning_details=[
                    ExportWarning(code="missing_problem_total", category="problem_missing", message="题目集《A》可能漏题：预期 3 题，实际抓到 2 题。"),
                    ExportWarning(code="page_unavailable", category="page_unavailable", message="题目《B》页面暂不可用：用户不存在"),
                    ExportWarning(code="image_download_failed", category="image_asset", message="题目《C》的图片下载失败：timeout"),
                ],
                summary=ExportSummary(
                    warning_count=3,
                    missing_problem_warning_count=1,
                    page_warning_count=1,
                    image_warning_count=1,
                ),
            )

            category_lines = app._build_warning_category_lines(result)
            detail_text = app._build_warning_examples_text(result.warning_details)

            self.assertEqual(["漏题 1 条", "页面异常 1 条", "图片异常 1 条"], category_lines)
            self.assertIn("漏题：", detail_text)
            self.assertIn("页面异常：", detail_text)
            self.assertIn("图片异常：", detail_text)
            app.scraper.shutdown()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
