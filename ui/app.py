from __future__ import annotations

import os
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from config import AppConfig
from models import ExportResult, ExportSourceSummary, ProblemSetSummary
from pta.scraper import PTAScraper


class PTAExporterApp:
    TYPE_PLACEHOLDER_TEXT = "展开后加载题型..."

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("PTA 作业导出器")
        self.root.geometry("1040x720")
        self.root.minsize(980, 720)

        self.config = AppConfig.load_default()
        self.scraper = PTAScraper(self.config)
        self.problem_sets: list[ProblemSetSummary] = []
        self.problem_set_by_id: dict[str, ProblemSetSummary] = {}
        self.export_queue: list[ExportSourceSummary] = []
        self.problem_tree_sources: dict[str, ExportSourceSummary] = {}
        self.problem_tree_root_nodes: dict[str, str] = {}
        self.problem_set_type_cache: dict[str, list[ExportSourceSummary]] = {}
        self.busy = False
        self.last_progress_message = ""
        self.logged_warnings: set[str] = set()
        self.last_export_warnings: list[str] = []
        self.current_auth_state: dict[str, Any] | None = None

        self.start_url_var = tk.StringVar(value=self.config.start_url)
        self.output_dir_var = tk.StringVar(value=str(self.config.output_dir))
        self.embed_images_var = tk.BooleanVar(value=self.config.embed_images)
        self.export_mode_var = tk.StringVar(value="merged")
        self.status_var = tk.StringVar(value="准备就绪")
        self.login_state_var = tk.StringVar(value="未登录")
        self.current_account_var = tk.StringVar(value="未识别")
        self.source_var = tk.StringVar(value="")
        self.queue_summary_var = tk.StringVar(value="已选 0 个导出项")
        self.progress_text_var = tk.StringVar(value="当前没有进行中的抓取任务")
        self.progress_value_var = tk.DoubleVar(value=0.0)
        self.warning_text_var = tk.StringVar(value="当前没有完整性警告")
        self.output_dir_hint_var = tk.StringVar(value="")
        self.export_summary_var = tk.StringVar(value="尚未开始导出")

        self._build_layout()
        self.export_mode_var.trace_add("write", lambda *_args: self._update_export_mode_ui())
        self._update_export_mode_ui()
        self._sync_source_label()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(container, text="基础配置", padding=12)
        top.pack(fill=tk.X)

        ttk.Label(top, text="入口 URL").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.start_url_var, width=76).grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(top, text="导出目录").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.output_dir_entry = ttk.Entry(top, textvariable=self.output_dir_var, width=76)
        self.output_dir_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self.output_dir_button = ttk.Button(top, text="选择目录", command=self._choose_output_dir)
        self.output_dir_button.grid(row=1, column=2, padx=(8, 0), pady=4)
        self.output_dir_hint_label = ttk.Label(top, textvariable=self.output_dir_hint_var, foreground="#666666")
        self.output_dir_hint_label.grid(row=2, column=1, sticky=tk.W, pady=(0, 4))

        ttk.Checkbutton(top, text="下载并嵌入题面图片", variable=self.embed_images_var).grid(
            row=3,
            column=1,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(top, text="导出方式").grid(row=4, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        export_mode_frame = ttk.Frame(top)
        export_mode_frame.grid(row=4, column=1, sticky=tk.W, pady=4)
        ttk.Radiobutton(
            export_mode_frame,
            text="合并成一个 Word",
            variable=self.export_mode_var,
            value="merged",
        ).pack(side=tk.LEFT)
        ttk.Radiobutton(
            export_mode_frame,
            text="每个导出项单独一个 Word",
            variable=self.export_mode_var,
            value="separate",
        ).pack(side=tk.LEFT, padx=(16, 0))

        top.columnconfigure(1, weight=1)

        action_bar = ttk.Frame(container, padding=(0, 12, 0, 12))
        action_bar.pack(fill=tk.X)
        self.login_button = ttk.Button(action_bar, text="1. 打开登录页", command=self._handle_login)
        self.login_button.pack(side=tk.LEFT, padx=(0, 8))
        self.switch_account_button = ttk.Button(
            action_bar,
            text="2. 重新登录",
            command=self._handle_switch_account,
        )
        self.switch_account_button.pack(side=tk.LEFT, padx=(0, 8))
        self.confirm_account_button = ttk.Button(
            action_bar,
            text="3. 确认账号",
            command=self._handle_confirm_account,
        )
        self.confirm_account_button.pack(side=tk.LEFT, padx=(0, 8))
        self.load_problem_sets_button = ttk.Button(
            action_bar,
            text="4. 加载题目集",
            command=self._handle_load_problem_sets,
        )
        self.load_problem_sets_button.pack(side=tk.LEFT, padx=(0, 8))
        self.export_button = ttk.Button(action_bar, text="5. 导出 Word", command=self._handle_export)
        self.export_button.pack(side=tk.LEFT)

        info_frame = ttk.LabelFrame(container, text="登录状态 / 抓取来源", padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text="登录状态：").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.login_state_var).grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(info_frame, text="当前账号：").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.current_account_var).grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(info_frame, text="抓取来源：").grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.source_var).grid(row=2, column=1, sticky=tk.W, pady=4)

        progress_frame = ttk.LabelFrame(container, text="抓取进度", padding=10)
        progress_frame.pack(fill=tk.X, pady=(12, 0))
        ttk.Label(progress_frame, textvariable=self.progress_text_var).pack(anchor=tk.W)
        ttk.Progressbar(progress_frame, variable=self.progress_value_var, maximum=100).pack(fill=tk.X, pady=(8, 0))
        ttk.Label(progress_frame, textvariable=self.export_summary_var, foreground="#245A8D", wraplength=980).pack(
            anchor=tk.W,
            pady=(8, 0),
        )
        ttk.Label(progress_frame, textvariable=self.warning_text_var, foreground="#9A4F00", wraplength=980).pack(
            anchor=tk.W,
            pady=(8, 0),
        )

        lists_row = ttk.Frame(container)
        lists_row.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        lists_row.columnconfigure(0, weight=1, uniform="lists")
        lists_row.columnconfigure(1, weight=0, minsize=150)
        lists_row.columnconfigure(2, weight=1, uniform="lists")
        lists_row.rowconfigure(0, weight=1)

        available_frame = ttk.LabelFrame(lists_row, text="题目集 / 题型（左侧展开并加入导出）", padding=10)
        available_frame.grid(row=0, column=0, sticky="nsew")
        available_frame.columnconfigure(0, weight=1)
        available_frame.rowconfigure(0, weight=1)
        self.problem_set_tree = ttk.Treeview(available_frame, selectmode="extended", show="tree")
        available_tree_scroll_y = ttk.Scrollbar(available_frame, orient=tk.VERTICAL, command=self.problem_set_tree.yview)
        available_tree_scroll_x = ttk.Scrollbar(available_frame, orient=tk.HORIZONTAL, command=self.problem_set_tree.xview)
        self.problem_set_tree.configure(
            yscrollcommand=available_tree_scroll_y.set,
            xscrollcommand=available_tree_scroll_x.set,
        )
        self.problem_set_tree.grid(row=0, column=0, sticky="nsew")
        available_tree_scroll_y.grid(row=0, column=1, sticky="ns")
        available_tree_scroll_x.grid(row=1, column=0, sticky="ew")
        self.problem_set_tree.bind("<Double-Button-1>", lambda _event: self._add_selected_problem_sets())
        self.problem_set_tree.bind("<<TreeviewOpen>>", self._handle_problem_set_tree_open)

        control_frame = ttk.Frame(lists_row, padding=(12, 36, 12, 12))
        control_frame.grid(row=0, column=1, sticky="ns")
        control_frame.columnconfigure(0, weight=1)
        ttk.Button(control_frame, text="加入导出 ->", command=self._add_selected_problem_sets).grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(control_frame, text="<- 移出导出", command=self._remove_selected_export_items).grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 16),
        )
        ttk.Button(control_frame, text="上移", command=lambda: self._move_export_item(-1)).grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        ttk.Button(control_frame, text="下移", command=lambda: self._move_export_item(1)).grid(
            row=3,
            column=0,
            sticky="ew",
        )

        queue_frame = ttk.LabelFrame(lists_row, text="已选导出项（导出顺序）", padding=10)
        queue_frame.grid(row=0, column=2, sticky="nsew")
        ttk.Label(queue_frame, textvariable=self.queue_summary_var).pack(anchor=tk.W, pady=(0, 8))
        queue_list_frame = ttk.Frame(queue_frame)
        queue_list_frame.pack(fill=tk.BOTH, expand=True)
        queue_list_frame.columnconfigure(0, weight=1)
        queue_list_frame.rowconfigure(0, weight=1)
        self.export_queue_list = tk.Listbox(
            queue_list_frame,
            exportselection=False,
            selectmode=tk.EXTENDED,
            height=18,
        )
        queue_scroll_y = ttk.Scrollbar(queue_list_frame, orient=tk.VERTICAL, command=self.export_queue_list.yview)
        queue_scroll_x = ttk.Scrollbar(queue_list_frame, orient=tk.HORIZONTAL, command=self.export_queue_list.xview)
        self.export_queue_list.configure(
            yscrollcommand=queue_scroll_y.set,
            xscrollcommand=queue_scroll_x.set,
        )
        self.export_queue_list.grid(row=0, column=0, sticky="nsew")
        queue_scroll_y.grid(row=0, column=1, sticky="ns")
        queue_scroll_x.grid(row=1, column=0, sticky="ew")
        self.export_queue_list.bind("<Double-Button-1>", lambda _event: self._remove_selected_export_items())

        log_frame = ttk.LabelFrame(container, text="运行日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = tk.Text(log_frame, height=12, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Label(container, textvariable=self.status_var, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(8, 0))

    def _handle_login(self) -> None:
        self._run_async(
            "正在打开登录页，请在浏览器中完成 PTA 登录...",
            lambda: self.scraper.open_login_window(self.start_url_var.get().strip()),
            self._after_login_window_opened,
        )

    def _handle_switch_account(self) -> None:
        self._run_async(
            "正在清除当前登录态并打开登录页...",
            lambda: self.scraper.switch_account(self.start_url_var.get().strip()),
            self._after_switch_account_ready,
        )

    def _handle_confirm_account(self) -> None:
        self._run_async(
            "正在确认当前登录账号...",
            self._confirm_account_and_close_browser,
            self._after_confirm_account,
        )

    def _handle_load_problem_sets(self) -> None:
        self._run_authenticated(
            "正在校验登录状态并加载题目集，请稍候...",
            lambda auth: self.scraper.load_problem_sets(
                auth_state=auth,
                progress_callback=self._make_progress_callback(),
            ),
            self._after_load_problem_sets,
        )

    def _handle_export(self) -> None:
        if not self.export_queue:
            messagebox.showwarning("请选择导出项", "请先在左侧树中选择至少一个题目集或题型。")
            return

        output_dir = Path(self.output_dir_var.get().strip())
        export_mode = self.export_mode_var.get()
        merged_filename_stem = None
        if export_mode == "merged":
            default_name = self._build_merged_export_name()
            selected_path = filedialog.asksaveasfilename(
                title="选择合并导出的 Word 文件",
                initialdir=str(output_dir),
                initialfile=f"{default_name}.docx",
                defaultextension=".docx",
                filetypes=[("Word 文档", "*.docx")],
            )
            if not selected_path:
                return
            selected = Path(selected_path)
            output_dir = selected.parent
            merged_filename_stem = selected.stem
            self.output_dir_var.set(str(output_dir))

        if not self._confirm_export(output_dir, export_mode):
            return

        self._run_authenticated(
            "正在校验登录状态并抓取题目生成 Word，请稍候...",
            lambda auth: self.scraper.export_problem_sets(
                list(self.export_queue),
                output_dir=output_dir,
                embed_images=self.embed_images_var.get(),
                export_mode=export_mode,
                merged_filename_stem=merged_filename_stem,
                auth_state=auth,
                progress_callback=self._make_progress_callback(),
            ),
            self._after_export,
        )

    def _run_authenticated(self, status_message: str, job, callback) -> None:
        def wrapped_job():
            auth = self._require_authenticated_session()
            result = job(auth)
            return {"auth": auth, "result": result}

        def wrapped_callback(payload: dict[str, Any]) -> None:
            auth = payload.get("auth") or {}
            self._apply_auth_state(auth)
            callback(payload.get("result"))

        self._run_async(status_message, wrapped_job, wrapped_callback)

    def _confirm_account_and_close_browser(self) -> dict[str, Any]:
        auth = self._require_authenticated_session()
        close_result = self.scraper.close_login_window()
        return {"auth": auth, "result": close_result}

    def _build_merged_export_name(self) -> str:
        titles = [item.export_title().strip() for item in self.export_queue if item.export_title().strip()]
        if not titles:
            return "PTA题目集"
        if len(titles) == 1:
            return titles[0]
        merged_name = "、".join(titles)
        return merged_name if len(merged_name) <= 120 else f"{titles[0]}等{len(titles)}个导出项"

    def _confirm_export(self, output_dir: Path, export_mode: str) -> bool:
        return messagebox.askokcancel("确认导出", self._build_export_request_summary(output_dir, export_mode))

    def _build_export_request_summary(self, output_dir: Path, export_mode: str) -> str:
        mode_label = "合并为一个 Word" if export_mode == "merged" else "每个导出项单独生成 Word"
        image_label = "下载并嵌入图片" if self.embed_images_var.get() else "不下载图片"
        return (
            f"将导出 {len(self.export_queue)} 个项目。\n"
            f"导出方式：{mode_label}\n"
            f"图片处理：{image_label}\n"
            f"输出位置：{output_dir}"
        )

    def _update_export_mode_ui(self) -> None:
        is_merged = self.export_mode_var.get() == "merged"
        self.output_dir_entry.config(state="disabled" if is_merged else "normal")
        self.output_dir_button.config(state="disabled" if is_merged else "normal")
        if is_merged:
            self.output_dir_hint_var.set("合并导出时会弹出“另存为”窗口，这里的目录不会直接使用。")
        else:
            self.output_dir_hint_var.set("单独导出时会把多个 Word 文档生成到这个目录。")

    def _after_login_window_opened(self, result: dict[str, Any]) -> None:
        self.login_state_var.set("等待登录")
        self._set_progress(0, "登录页已打开，请登录后点击“确认账号”", log_message=False)
        self._log(result.get("message", "登录页已打开，请登录后手动确认账号。"))
        if result.get("finalUrl"):
            self.start_url_var.set(str(result["finalUrl"]))
            self._sync_source_label()

    def _after_switch_account_ready(self, result: dict[str, Any]) -> None:
        self._clear_auth_state("等待登录")
        self._set_progress(0, "已清除登录态，请在浏览器中登录要抓取的账号...", log_message=False)
        self._log(result.get("message", "已清除登录态，请重新登录。"))
        if result.get("finalUrl"):
            self.start_url_var.set(str(result["finalUrl"]))
            self._sync_source_label()
 
    def _after_confirm_account(self, payload: dict[str, Any]) -> None:
        auth = payload.get("auth") or {}
        result = payload.get("result") or {}
        self._apply_auth_state(auth)
        self._set_progress(100, "账号确认完成，可以开始加载题目集", log_message=False)
        self._log(result.get("message", "账号确认完成，浏览器已关闭。"))

    def _after_load_problem_sets(self, problem_sets: list[ProblemSetSummary]) -> None:
        self.problem_sets = problem_sets
        self.problem_set_by_id = {item.id: item for item in problem_sets}
        self.problem_set_type_cache = {}
        self.export_queue = []
        self._rebuild_problem_set_tree(problem_sets)
        self._refresh_export_queue_view()
        self._set_progress(100, f"题目集加载完成，共 {len(problem_sets)} 个", log_message=False)
        self._sync_login_state_from_auth()
        if problem_sets:
            first_node = self.problem_tree_root_nodes.get(problem_sets[0].id)
            if first_node:
                self.problem_set_tree.selection_set(first_node)
                self.problem_set_tree.focus(first_node)
            self._log(f"已加载 {len(problem_sets)} 个题目集。")
        else:
            self._log("没有加载到任何题目集。")

    def _handle_problem_set_tree_open(self, _event: tk.Event) -> None:
        item_id = self.problem_set_tree.focus()
        if not item_id:
            return
        source = self.problem_tree_sources.get(item_id)
        if source is None or source.source_kind != "problem_set":
            return
        if source.problem_set_id in self.problem_set_type_cache:
            return
        problem_set = self.problem_set_by_id.get(source.problem_set_id)
        if problem_set is None:
            return
        self._run_authenticated(
            f"正在加载题型：{problem_set.title}",
            lambda auth: self.scraper.load_problem_set_types(
                problem_set,
                auth_state=auth,
                progress_callback=self._make_progress_callback(),
            ),
            lambda items, problem_set_id=problem_set.id: self._after_load_problem_set_types(problem_set_id, items),
        )

    def _after_load_problem_set_types(
        self,
        problem_set_id: str,
        sources: list[ExportSourceSummary] | None,
    ) -> None:
        items = list(sources or [])
        self.problem_set_type_cache[problem_set_id] = items
        parent_id = self.problem_tree_root_nodes.get(problem_set_id)
        if not parent_id:
            return

        for child_id in self.problem_set_tree.get_children(parent_id):
            self.problem_tree_sources.pop(child_id, None)
            self.problem_set_tree.delete(child_id)

        for source in items:
            child_id = self.problem_set_tree.insert(parent_id, tk.END, text=self._tree_item_label(source), open=False)
            self.problem_tree_sources[child_id] = source

        title = self.problem_set_by_id.get(problem_set_id).title if problem_set_id in self.problem_set_by_id else problem_set_id
        if items:
            self._log(f"已加载题型：{title}（{len(items)} 个）")
        else:
            self._log(f"题目集未发现可导出的题型：{title}")

    def _after_export(self, result: ExportResult) -> None:
        self.last_export_warnings = list(result.warnings)
        output_paths = [Path(path) for path in result.output_paths if path]
        if not output_paths and result.output_path:
            output_paths = [Path(result.output_path)]
        output_path = output_paths[0] if output_paths else Path(self.output_dir_var.get().strip())
        summary = result.summary
        self.export_summary_var.set(
            f"导出摘要：{summary.exported_problem_set_count} 个导出项，"
            f"{summary.parsed_problem_total}/{summary.expected_problem_total or summary.parsed_problem_total} 题成功，"
            f"{summary.warning_count} 条警告"
        )

        if result.export_mode == "separate" and len(output_paths) > 1:
            progress_message = f"导出完成，已生成 {len(output_paths)} 个 Word 文档。"
            output_message = "Word 文档已生成：\n" + "\n".join(str(path) for path in output_paths[:8])
            if len(output_paths) > 8:
                output_message += f"\n... 还有 {len(output_paths) - 8} 个文件"
        else:
            progress_message = f"导出完成：{output_path}"
            output_message = f"Word 文档已生成：\n{output_path}"
        dialog_message = f"{output_message}\n\n{self._build_export_result_summary(result)}"

        self._set_progress(100, progress_message, log_message=False)
        self._log(progress_message)
        if result.warnings:
            warning_text = "\n".join(result.warnings[:8])
            if len(result.warnings) > 8:
                warning_text += f"\n... 还有 {len(result.warnings) - 8} 条警告"
            self.warning_text_var.set("当前有完整性警告：" + "；".join(result.warnings[:2]))
            messagebox.showwarning(
                "导出完成，但有警告",
                f"{dialog_message}\n\n以下导出项可能没有抓全：\n{warning_text}",
            )
            self._maybe_open_output_dir(output_path)
            return
        self.warning_text_var.set("当前没有完整性警告")
        messagebox.showinfo("导出完成", dialog_message)
        self._maybe_open_output_dir(output_path)

    def _build_export_result_summary(self, result: ExportResult) -> str:
        summary = result.summary
        lines = [
            f"导出项：{summary.exported_problem_set_count}",
            f"题目：{summary.parsed_problem_total}/{summary.expected_problem_total or summary.parsed_problem_total}",
            f"缺失：{summary.failed_problem_total}",
            f"警告：{summary.warning_count}",
        ]
        if summary.image_warning_count:
            lines.append(f"图片警告：{summary.image_warning_count}")
        return "导出摘要：\n" + "\n".join(lines)

    def _maybe_open_output_dir(self, output_path: Path) -> None:
        target_dir = output_path if output_path.is_dir() else output_path.parent
        if not target_dir.exists():
            return
        if not messagebox.askyesno("打开输出目录", f"是否打开输出目录？\n{target_dir}"):
            return
        try:
            os.startfile(str(target_dir))
        except OSError as error:
            self._log(f"打开输出目录失败：{error}")

    def _require_authenticated_session(self) -> dict[str, Any]:
        auth = self.scraper.get_current_user()
        if auth.get("authenticated"):
            return auth
        message = str(auth.get("message") or "请先登录并确认账号。").strip()
        raise RuntimeError(message)

    def _apply_auth_state(self, auth_state: dict[str, Any]) -> None:
        self.current_auth_state = dict(auth_state)
        account_id = str(auth_state.get("accountId") or "").strip()
        display_name = str(auth_state.get("displayName") or "").strip()
        if display_name and account_id and display_name != account_id:
            self.current_account_var.set(f"{display_name} ({account_id})")
        else:
            self.current_account_var.set(display_name or account_id or "未识别")
        self._sync_login_state_from_auth()

    def _clear_auth_state(self, login_state: str = "未登录") -> None:
        self.current_auth_state = None
        self.current_account_var.set("未识别")
        self.login_state_var.set(login_state)

    def _sync_login_state_from_auth(self) -> None:
        auth_state = self.current_auth_state or {}
        if not auth_state.get("authenticated"):
            self.login_state_var.set("未登录")
            return
        if str(auth_state.get("accountId") or "").strip():
            self.login_state_var.set("已登录，可以加载题目集")
            return
        self.login_state_var.set("已登录，但无法识别账号")

    def _sync_source_label(self) -> None:
        start_url = self.start_url_var.get().strip()
        if start_url:
            self.source_var.set(f"入口：{start_url}")
        else:
            self.source_var.set("固定入口：所有题目集")

    def _run_async(self, status_message: str, job, callback) -> None:
        if self.busy:
            messagebox.showinfo("请稍候", "当前任务尚未完成，请等待。")
            return

        self.busy = True
        self.last_export_warnings = []
        self.logged_warnings.clear()
        self.warning_text_var.set("当前没有完整性警告")
        self.export_summary_var.set("任务进行中，完成后会在这里显示导出摘要")
        self.status_var.set(status_message)
        self._set_button_state("disabled")
        self._set_progress(0, status_message, log_message=True)

        def worker() -> None:
            result = None
            error = None
            details = ""
            try:
                result = job()
            except Exception as exc:  # pragma: no cover - UI path
                error = exc
                details = traceback.format_exc()
            self.root.after(0, lambda: self._finish_async(result, error, details, callback))

        threading.Thread(target=worker, daemon=True).start()

    def _finish_async(self, result, error: Exception | None, details: str, callback) -> None:
        self.busy = False
        self._set_button_state("normal")
        self.status_var.set("准备就绪")
        if error is not None:
            friendly_error = self._format_error_message(error)
            self._log(friendly_error)
            if details:
                self._log(details)
            self.export_summary_var.set("本次任务未完成")
            self._set_progress(self.progress_value_var.get(), f"任务失败：{friendly_error}", log_message=False)
            messagebox.showerror("操作失败", friendly_error)
            return
        callback(result)

    def _format_error_message(self, error: Exception) -> str:
        message = str(error).strip()
        if "Could not locate node.exe" in message:
            return "未找到浏览器桥运行时 node.exe。请使用打包版本，或按 README 配置运行时后再试。"
        if "Could not locate Microsoft Edge or Google Chrome." in message:
            return "未检测到 Microsoft Edge 或 Google Chrome。请先安装浏览器后再试。"
        if "未检测到有效登录状态" in message or "用户不存在" in message:
            return f"{message}\n\n请重新登录 PTA 后重试。"
        return message

    def _set_button_state(self, state: str) -> None:
        for button in (
            self.login_button,
            self.switch_account_button,
            self.confirm_account_button,
            self.load_problem_sets_button,
            self.export_button,
        ):
            button.config(state=state)

    def _add_selected_problem_sets(self) -> None:
        sources = self._selected_tree_sources()
        if not sources:
            messagebox.showinfo("未选择导出项", "请先在左侧树中选中要加入导出的题目集或题型。")
            return

        added_count = 0
        skipped_messages: list[str] = []
        for source in sources:
            conflict = self._queue_conflict_message(self.export_queue, source)
            if conflict:
                skipped_messages.append(conflict)
                continue
            self.export_queue.append(source)
            added_count += 1

        self._refresh_export_queue_view()
        if added_count > 0:
            self._log(f"已加入 {added_count} 个导出项到队列。")
        if skipped_messages:
            detail = "\n".join(skipped_messages[:6])
            if len(skipped_messages) > 6:
                detail += f"\n... 还有 {len(skipped_messages) - 6} 条提示"
            self._log(detail)
            messagebox.showwarning("部分导出项未加入", detail)

    def _remove_selected_export_items(self) -> None:
        selected_indices = list(self.export_queue_list.curselection())
        if not selected_indices:
            messagebox.showinfo("未选择导出项", "请先在右侧列表中选中要移除的导出项。")
            return

        selected_set = set(selected_indices)
        self.export_queue = [item for index, item in enumerate(self.export_queue) if index not in selected_set]
        self._refresh_export_queue_view()
        self._log(f"已从导出队列移除 {len(selected_indices)} 个导出项。")

    def _move_export_item(self, direction: int) -> None:
        selected_indices = list(self.export_queue_list.curselection())
        if len(selected_indices) != 1:
            messagebox.showinfo("请选择单个导出项", "调整顺序时，请先在右侧列表中只选中一个导出项。")
            return

        current_index = selected_indices[0]
        target_index = current_index + direction
        if target_index < 0 or target_index >= len(self.export_queue):
            return

        self.export_queue[current_index], self.export_queue[target_index] = (
            self.export_queue[target_index],
            self.export_queue[current_index],
        )
        self._refresh_export_queue_view(selected_index=target_index)
        self._log("已调整导出顺序。")

    def _refresh_export_queue_view(self, selected_index: int | None = None) -> None:
        self.export_queue_list.delete(0, tk.END)
        for index, item in enumerate(self.export_queue, start=1):
            self.export_queue_list.insert(tk.END, f"{index}. {item.queue_label()}")
        self.queue_summary_var.set(f"已选 {len(self.export_queue)} 个导出项")
        if selected_index is not None and 0 <= selected_index < len(self.export_queue):
            self.export_queue_list.selection_set(selected_index)
            self.export_queue_list.see(selected_index)

    def _rebuild_problem_set_tree(self, problem_sets: list[ProblemSetSummary]) -> None:
        self.problem_set_tree.delete(*self.problem_set_tree.get_children())
        self.problem_tree_sources = {}
        self.problem_tree_root_nodes = {}

        for item in problem_sets:
            source = ExportSourceSummary.from_problem_set(item)
            node_id = self.problem_set_tree.insert("", tk.END, text=self._tree_item_label(source), open=False)
            self.problem_tree_sources[node_id] = source
            self.problem_tree_root_nodes[item.id] = node_id
            self.problem_set_tree.insert(node_id, tk.END, text=self.TYPE_PLACEHOLDER_TEXT, open=False)

    def _selected_tree_sources(self) -> list[ExportSourceSummary]:
        sources: list[ExportSourceSummary] = []
        seen_ids: set[str] = set()
        for item_id in self.problem_set_tree.selection():
            source = self.problem_tree_sources.get(item_id)
            if source is None or source.id in seen_ids:
                continue
            seen_ids.add(source.id)
            sources.append(source)
        return sources

    def _tree_item_label(self, source: ExportSourceSummary) -> str:
        if source.source_kind == "problem_type":
            if source.problem_count > 0:
                return f"{source.type_title} ({source.problem_count})"
            return source.type_title
        suffix = f" | {source.ends_at}" if source.ends_at else ""
        owner = f" | {source.owner}" if source.owner else ""
        return f"{source.title}{suffix}{owner}"

    @staticmethod
    def _queue_conflict_message(
        queue: list[ExportSourceSummary],
        candidate: ExportSourceSummary,
    ) -> str | None:
        for existing in queue:
            if existing.id == candidate.id or existing.url == candidate.url:
                return f"《{candidate.queue_label()}》已在导出队列中。"
            if existing.problem_set_id != candidate.problem_set_id:
                continue
            if candidate.source_kind == "problem_set" and existing.source_kind == "problem_type":
                return f"题目集《{candidate.problem_set_title}》已有题型子项在队列中，不能再加入整套导出。"
            if candidate.source_kind == "problem_type" and existing.source_kind == "problem_set":
                return f"题目集《{candidate.problem_set_title}》整套已在队列中，不能再加入题型《{candidate.type_title}》。"
        return None

    def _choose_output_dir(self) -> None:
        selected = filedialog.askdirectory(initialdir=self.output_dir_var.get() or str(self.config.output_dir))
        if selected:
            self.output_dir_var.set(selected)

    def _make_progress_callback(self):
        def callback(payload: dict[str, Any]) -> None:
            self.root.after(0, lambda data=payload: self._apply_progress(data))

        return callback

    def _apply_progress(self, payload: dict[str, Any]) -> None:
        percent = payload.get("percent")
        message = str(payload.get("message", "")).strip()
        warnings = [str(item).strip() for item in payload.get("warnings", []) if str(item).strip()]
        if warnings:
            self.last_export_warnings = warnings
            self.warning_text_var.set("完整性警告：" + "；".join(warnings[:2]))
            for warning in warnings:
                if warning not in self.logged_warnings:
                    self._log(warning)
                    self.logged_warnings.add(warning)
        self._set_progress(percent if isinstance(percent, (int, float)) else None, message, log_message=True)

    def _set_progress(self, percent: float | None, message: str, *, log_message: bool) -> None:
        if percent is not None:
            self.progress_value_var.set(max(0.0, min(100.0, float(percent))))
        if message:
            self.progress_text_var.set(message)
            if log_message and message != self.last_progress_message:
                self._log(message)
                self.last_progress_message = message

    def _log(self, message: str) -> None:
        self.log_text.configure(state=tk.NORMAL)
        self.log_text.insert(tk.END, f"{message}\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state=tk.DISABLED)

    def _on_close(self) -> None:
        try:
            self.scraper.shutdown()
        finally:
            self.root.destroy()
