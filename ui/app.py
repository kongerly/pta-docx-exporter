from __future__ import annotations

import os
import threading
import traceback
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import Any

from app_meta import build_window_title
from app_text import UiText
from config import AppConfig
from models import ExportResult, ExportSourceSummary, ExportWarning, ProblemSetSummary
from pta.scraper import PTAScraper


class PTAExporterApp:
    TYPE_PLACEHOLDER_TEXT = UiText.TYPE_PLACEHOLDER

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(build_window_title())
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
        self.status_var = tk.StringVar(value=UiText.READY)
        self.login_state_var = tk.StringVar(value=UiText.NOT_LOGGED_IN)
        self.current_account_var = tk.StringVar(value=UiText.UNKNOWN_ACCOUNT)
        self.source_var = tk.StringVar(value="")
        self.queue_summary_var = tk.StringVar(value=UiText.queue_summary(0))
        self.progress_text_var = tk.StringVar(value=UiText.NO_PROGRESS_TASK)
        self.progress_value_var = tk.DoubleVar(value=0.0)
        self.warning_text_var = tk.StringVar(value=UiText.NO_WARNING)
        self.output_dir_hint_var = tk.StringVar(value="")
        self.export_summary_var = tk.StringVar(value=UiText.NO_EXPORT_YET)

        self._build_layout()
        self.start_url_var.trace_add("write", lambda *_args: self._sync_source_label())
        self.export_mode_var.trace_add("write", lambda *_args: self._update_export_mode_ui())
        self._update_export_mode_ui()
        self._sync_source_label()
        self._refresh_ui_state()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_layout(self) -> None:
        container = ttk.Frame(self.root, padding=16)
        container.pack(fill=tk.BOTH, expand=True)

        top = ttk.LabelFrame(container, text=UiText.GROUP_BASIC, padding=12)
        top.pack(fill=tk.X)

        ttk.Label(top, text=UiText.LABEL_START_URL).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.start_url_entry = ttk.Entry(top, textvariable=self.start_url_var, width=76)
        self.start_url_entry.grid(row=0, column=1, sticky=tk.EW, pady=4)

        ttk.Label(top, text=UiText.LABEL_OUTPUT_DIR).grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        self.output_dir_entry = ttk.Entry(top, textvariable=self.output_dir_var, width=76)
        self.output_dir_entry.grid(row=1, column=1, sticky=tk.EW, pady=4)
        self.output_dir_button = ttk.Button(top, text=UiText.BUTTON_CHOOSE_DIR, command=self._choose_output_dir)
        self.output_dir_button.grid(row=1, column=2, padx=(8, 0), pady=4)
        self.output_dir_hint_label = ttk.Label(top, textvariable=self.output_dir_hint_var, foreground="#666666")
        self.output_dir_hint_label.grid(row=2, column=1, sticky=tk.W, pady=(0, 4))

        self.embed_images_checkbutton = ttk.Checkbutton(top, text=UiText.LABEL_EMBED_IMAGES, variable=self.embed_images_var)
        self.embed_images_checkbutton.grid(
            row=3,
            column=1,
            sticky=tk.W,
            pady=4,
        )

        ttk.Label(top, text=UiText.LABEL_EXPORT_MODE).grid(row=4, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        export_mode_frame = ttk.Frame(top)
        export_mode_frame.grid(row=4, column=1, sticky=tk.W, pady=4)
        self.export_mode_merged_button = ttk.Radiobutton(
            export_mode_frame,
            text=UiText.EXPORT_MODE_MERGED,
            variable=self.export_mode_var,
            value="merged",
        )
        self.export_mode_merged_button.pack(side=tk.LEFT)
        self.export_mode_separate_button = ttk.Radiobutton(
            export_mode_frame,
            text=UiText.EXPORT_MODE_SEPARATE,
            variable=self.export_mode_var,
            value="separate",
        )
        self.export_mode_separate_button.pack(side=tk.LEFT, padx=(16, 0))
        ttk.Label(top, text=UiText.VERSION_LABEL, foreground="#666666").grid(
            row=5,
            column=1,
            sticky=tk.W,
            pady=(8, 0),
        )

        top.columnconfigure(1, weight=1)

        action_bar = ttk.Frame(container, padding=(0, 12, 0, 12))
        action_bar.pack(fill=tk.X)
        self.login_button = ttk.Button(action_bar, text=UiText.BUTTON_LOGIN, command=self._handle_login)
        self.login_button.pack(side=tk.LEFT, padx=(0, 8))
        self.switch_account_button = ttk.Button(
            action_bar,
            text=UiText.BUTTON_SWITCH_ACCOUNT,
            command=self._handle_switch_account,
        )
        self.switch_account_button.pack(side=tk.LEFT, padx=(0, 8))
        self.confirm_account_button = ttk.Button(
            action_bar,
            text=UiText.BUTTON_CONFIRM_ACCOUNT,
            command=self._handle_confirm_account,
        )
        self.confirm_account_button.pack(side=tk.LEFT, padx=(0, 8))
        self.load_problem_sets_button = ttk.Button(
            action_bar,
            text=UiText.BUTTON_LOAD_SETS,
            command=self._handle_load_problem_sets,
        )
        self.load_problem_sets_button.pack(side=tk.LEFT, padx=(0, 8))
        self.export_button = ttk.Button(action_bar, text=UiText.BUTTON_EXPORT, command=self._handle_export)
        self.export_button.pack(side=tk.LEFT)

        info_frame = ttk.LabelFrame(container, text=UiText.GROUP_INFO, padding=10)
        info_frame.pack(fill=tk.X)
        ttk.Label(info_frame, text=UiText.LABEL_LOGIN_STATE).grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.login_state_var).grid(row=0, column=1, sticky=tk.W, pady=4)
        ttk.Label(info_frame, text=UiText.LABEL_CURRENT_ACCOUNT).grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.current_account_var).grid(row=1, column=1, sticky=tk.W, pady=4)
        ttk.Label(info_frame, text=UiText.LABEL_SOURCE).grid(row=2, column=0, sticky=tk.W, padx=(0, 8), pady=4)
        ttk.Label(info_frame, textvariable=self.source_var).grid(row=2, column=1, sticky=tk.W, pady=4)

        progress_frame = ttk.LabelFrame(container, text=UiText.GROUP_PROGRESS, padding=10)
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

        available_frame = ttk.LabelFrame(lists_row, text=UiText.GROUP_AVAILABLE, padding=10)
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
        self.problem_set_tree.bind("<<TreeviewSelect>>", lambda _event: self._refresh_ui_state())

        control_frame = ttk.Frame(lists_row, padding=(12, 36, 12, 12))
        control_frame.grid(row=0, column=1, sticky="ns")
        control_frame.columnconfigure(0, weight=1)
        self.add_to_queue_button = ttk.Button(control_frame, text=UiText.BUTTON_ADD_TO_QUEUE, command=self._add_selected_problem_sets)
        self.add_to_queue_button.grid(
            row=0,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        self.remove_from_queue_button = ttk.Button(control_frame, text=UiText.BUTTON_REMOVE_FROM_QUEUE, command=self._remove_selected_export_items)
        self.remove_from_queue_button.grid(
            row=1,
            column=0,
            sticky="ew",
            pady=(0, 16),
        )
        self.move_up_button = ttk.Button(control_frame, text=UiText.BUTTON_MOVE_UP, command=lambda: self._move_export_item(-1))
        self.move_up_button.grid(
            row=2,
            column=0,
            sticky="ew",
            pady=(0, 8),
        )
        self.move_down_button = ttk.Button(control_frame, text=UiText.BUTTON_MOVE_DOWN, command=lambda: self._move_export_item(1))
        self.move_down_button.grid(
            row=3,
            column=0,
            sticky="ew",
        )

        queue_frame = ttk.LabelFrame(lists_row, text=UiText.GROUP_QUEUE, padding=10)
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
        self.export_queue_list.bind("<<ListboxSelect>>", lambda _event: self._refresh_ui_state())

        log_frame = ttk.LabelFrame(container, text=UiText.GROUP_LOG, padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=(12, 0))
        self.log_text = tk.Text(log_frame, height=12, state=tk.DISABLED)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        status_bar = ttk.Label(container, textvariable=self.status_var, anchor=tk.W)
        status_bar.pack(fill=tk.X, pady=(8, 0))

    def _handle_login(self) -> None:
        self._run_async(
            UiText.login_open_status(),
            lambda: self.scraper.open_login_window(self.start_url_var.get().strip()),
            self._after_login_window_opened,
        )

    def _handle_switch_account(self) -> None:
        self._run_async(
            UiText.switch_account_status(),
            lambda: self.scraper.switch_account(self.start_url_var.get().strip()),
            self._after_switch_account_ready,
        )

    def _handle_confirm_account(self) -> None:
        self._run_async(
            UiText.confirm_account_status(),
            self._confirm_account_and_close_browser,
            self._after_confirm_account,
        )

    def _handle_load_problem_sets(self) -> None:
        self._run_authenticated(
            UiText.load_problem_sets_status(),
            lambda auth: self.scraper.load_problem_sets(
                auth_state=auth,
                progress_callback=self._make_progress_callback(),
            ),
            self._after_load_problem_sets,
        )

    def _handle_export(self) -> None:
        if not self.export_queue:
            messagebox.showwarning(UiText.DIALOG_NEED_EXPORT_ITEM, UiText.need_export_items())
            return

        output_dir = Path(self.output_dir_var.get().strip())
        export_mode = self.export_mode_var.get()
        merged_filename_stem = None
        if export_mode == "merged":
            default_name = self._build_merged_export_name()
            selected_path = filedialog.asksaveasfilename(
                title=UiText.DIALOG_EXPORT_FILE,
                initialdir=str(output_dir),
                initialfile=f"{default_name}.docx",
                defaultextension=".docx",
                filetypes=[(UiText.WORD_FILETYPE_LABEL, "*.docx")],
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
            UiText.export_status(),
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
        return UiText.merged_export_name(titles)

    def _confirm_export(self, output_dir: Path, export_mode: str) -> bool:
        return messagebox.askokcancel(UiText.DIALOG_CONFIRM_EXPORT, self._build_export_request_summary(output_dir, export_mode))

    def _build_export_request_summary(self, output_dir: Path, export_mode: str) -> str:
        queue_labels = [item.queue_label() for item in self.export_queue]
        return UiText.export_request_summary_detailed(
            len(self.export_queue),
            UiText.export_mode_label(export_mode),
            UiText.image_mode_label(self.embed_images_var.get()),
            str(output_dir),
            self.current_account_var.get().strip() or UiText.UNKNOWN_ACCOUNT,
            self.source_var.get().strip() or UiText.source_label(""),
            UiText.export_queue_preview(queue_labels),
        )

    def _update_export_mode_ui(self) -> None:
        if self.export_mode_var.get() == "merged":
            self.output_dir_hint_var.set(UiText.merged_export_hint())
        else:
            self.output_dir_hint_var.set(UiText.separate_export_hint())
        self._refresh_ui_state()

    def _after_login_window_opened(self, result: dict[str, Any]) -> None:
        self.login_state_var.set(UiText.WAITING_FOR_LOGIN)
        self._refresh_ui_state()
        self._set_progress(0, UiText.login_page_opened(), log_message=False)
        self._log(result.get("message", UiText.login_page_opened_log()))
        if result.get("finalUrl"):
            self.start_url_var.set(str(result["finalUrl"]))
            self._sync_source_label()

    def _after_switch_account_ready(self, result: dict[str, Any]) -> None:
        self._clear_auth_state(UiText.WAITING_FOR_LOGIN)
        self._set_progress(0, UiText.account_cleared(), log_message=False)
        self._log(result.get("message", UiText.account_cleared_log()))
        if result.get("finalUrl"):
            self.start_url_var.set(str(result["finalUrl"]))
            self._sync_source_label()
 
    def _after_confirm_account(self, payload: dict[str, Any]) -> None:
        auth = payload.get("auth") or {}
        result = payload.get("result") or {}
        self._apply_auth_state(auth)
        self._set_progress(100, UiText.account_confirmed(), log_message=False)
        self._log(result.get("message", UiText.account_confirmed_log()))

    def _after_load_problem_sets(self, problem_sets: list[ProblemSetSummary]) -> None:
        self.problem_sets = problem_sets
        self.problem_set_by_id = {item.id: item for item in problem_sets}
        self.problem_set_type_cache = {}
        self.export_queue = []
        self._rebuild_problem_set_tree(problem_sets)
        self._refresh_export_queue_view()
        self._set_progress(100, UiText.problem_sets_loaded(len(problem_sets)), log_message=False)
        self._sync_login_state_from_auth()
        if problem_sets:
            first_node = self.problem_tree_root_nodes.get(problem_sets[0].id)
            if first_node:
                self.problem_set_tree.selection_set(first_node)
                self.problem_set_tree.focus(first_node)
            self._log(UiText.problem_sets_loaded_log(len(problem_sets)))
        else:
            self._log(UiText.no_problem_sets_loaded())
        self._refresh_ui_state()

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
            UiText.problem_types_loading(problem_set.title),
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
            self._log(UiText.problem_types_loaded(title, len(items)))
        else:
            self._log(UiText.no_exportable_types(title))

    def _after_export(self, result: ExportResult) -> None:
        self.last_export_warnings = list(result.warnings)
        output_paths = [Path(path) for path in result.output_paths if path]
        if not output_paths and result.output_path:
            output_paths = [Path(result.output_path)]
        output_path = output_paths[0] if output_paths else Path(self.output_dir_var.get().strip())
        summary = result.summary
        self.export_summary_var.set(
            UiText.export_summary(
                summary.exported_problem_set_count,
                summary.parsed_problem_total,
                summary.expected_problem_total,
                summary.warning_count,
            )
        )

        if result.export_mode == "separate" and len(output_paths) > 1:
            progress_message = UiText.separate_export_completed(len(output_paths))
            output_message = UiText.export_document_list([str(path) for path in output_paths[:8]])
            if len(output_paths) > 8:
                output_message += f"\n{UiText.more_files(len(output_paths) - 8)}"
        else:
            progress_message = UiText.export_completed(str(output_path))
            output_message = UiText.export_document_single(str(output_path))
        dialog_message = f"{output_message}\n\n{self._build_export_result_summary(result)}"

        self._set_progress(100, progress_message, log_message=False)
        self._log(progress_message)
        if result.warnings:
            category_lines = self._build_warning_category_lines(result)
            warning_text = self._build_warning_examples_text(result.warning_details)
            self.warning_text_var.set(UiText.warning_banner_summary(category_lines))
            messagebox.showwarning(
                UiText.DIALOG_EXPORT_COMPLETE_WITH_WARNING,
                UiText.export_warning_details(
                    dialog_message,
                    "\n".join(category_lines),
                    warning_text,
                ),
            )
            self._maybe_open_output_dir(output_path)
            return
        self.warning_text_var.set(UiText.NO_WARNING)
        messagebox.showinfo(UiText.DIALOG_EXPORT_COMPLETE, dialog_message)
        self._maybe_open_output_dir(output_path)

    def _build_export_result_summary(self, result: ExportResult) -> str:
        summary = result.summary
        lines = UiText.export_result_summary_lines(
            summary.exported_problem_set_count,
            summary.parsed_problem_total,
            summary.expected_problem_total,
            summary.failed_problem_total,
            summary.warning_count,
            summary.image_warning_count,
            summary.missing_problem_warning_count,
            summary.page_warning_count,
            summary.content_warning_count,
        )
        return UiText.export_result_summary_text(lines)

    def _build_warning_category_lines(self, result: ExportResult) -> list[str]:
        summary = result.summary
        return UiText.export_warning_category_lines(
            summary.missing_problem_warning_count,
            summary.page_warning_count,
            summary.image_warning_count,
            summary.content_warning_count,
        )

    def _build_warning_examples_text(self, warning_details: list[ExportWarning]) -> str:
        if not warning_details:
            return "（无具体告警）"

        grouped: dict[str, list[str]] = {}
        for warning in warning_details:
            grouped.setdefault(warning.category, [])
            if warning.message not in grouped[warning.category]:
                grouped[warning.category].append(warning.message)

        ordered_categories = [
            "problem_missing",
            "page_unavailable",
            "image_asset",
            "content_mojibake",
        ]
        lines: list[str] = []
        for category in ordered_categories:
            messages = grouped.get(category, [])
            if not messages:
                continue
            lines.append(f"{UiText.warning_category_label(category)}：")
            lines.extend(messages[:2])
            if len(messages) > 2:
                lines.append(UiText.more_warnings(len(messages) - 2))
        for category, messages in grouped.items():
            if category in ordered_categories or not messages:
                continue
            lines.append(f"{UiText.warning_category_label(category)}：")
            lines.extend(messages[:2])
            if len(messages) > 2:
                lines.append(UiText.more_warnings(len(messages) - 2))
        return "\n".join(lines)

    def _maybe_open_output_dir(self, output_path: Path) -> None:
        target_dir = output_path if output_path.is_dir() else output_path.parent
        if not target_dir.exists():
            return
        if not messagebox.askyesno(UiText.DIALOG_OPEN_OUTPUT_DIR, UiText.open_output_dir_prompt(str(target_dir))):
            return
        try:
            os.startfile(str(target_dir))
        except OSError as error:
            self._log(UiText.open_output_dir_failed(error))

    def _require_authenticated_session(self) -> dict[str, Any]:
        auth = self.scraper.get_current_user()
        if auth.get("authenticated"):
            return auth
        message = str(auth.get("message") or UiText.login_confirmation_required()).strip()
        raise RuntimeError(message)

    def _apply_auth_state(self, auth_state: dict[str, Any]) -> None:
        self.current_auth_state = dict(auth_state)
        account_id = str(auth_state.get("accountId") or "").strip()
        display_name = str(auth_state.get("displayName") or "").strip()
        if display_name and account_id and display_name != account_id:
            self.current_account_var.set(f"{display_name} ({account_id})")
        else:
            self.current_account_var.set(display_name or account_id or UiText.UNKNOWN_ACCOUNT)
        self._sync_login_state_from_auth()
        self._refresh_ui_state()

    def _clear_auth_state(self, login_state: str = UiText.NOT_LOGGED_IN) -> None:
        self.current_auth_state = None
        self.current_account_var.set(UiText.UNKNOWN_ACCOUNT)
        self.login_state_var.set(login_state)
        self._refresh_ui_state()

    def _sync_login_state_from_auth(self) -> None:
        auth_state = self.current_auth_state or {}
        if not auth_state.get("authenticated"):
            self.login_state_var.set(UiText.NOT_LOGGED_IN)
            return
        if str(auth_state.get("accountId") or "").strip():
            self.login_state_var.set(UiText.ready_to_load_message())
            return
        self.login_state_var.set(UiText.logged_in_but_unknown())

    def _sync_source_label(self) -> None:
        start_url = self.start_url_var.get().strip()
        self.source_var.set(UiText.source_label(start_url))

    def _has_authenticated_account(self) -> bool:
        auth_state = self.current_auth_state or {}
        return bool(auth_state.get("authenticated") and str(auth_state.get("accountId") or "").strip())

    def _can_confirm_account(self) -> bool:
        return self.login_state_var.get() == UiText.WAITING_FOR_LOGIN

    def _refresh_ui_state(self) -> None:
        if not hasattr(self, "login_button"):
            return

        if self.busy:
            state = "disabled"
            self.login_button.config(state=state)
            self.switch_account_button.config(state=state)
            self.confirm_account_button.config(state=state)
            self.load_problem_sets_button.config(state=state)
            self.export_button.config(state=state)
            self.add_to_queue_button.config(state=state)
            self.remove_from_queue_button.config(state=state)
            self.move_up_button.config(state=state)
            self.move_down_button.config(state=state)
            self.start_url_entry.config(state=state)
            self.output_dir_entry.config(state=state)
            self.output_dir_button.config(state=state)
            self.embed_images_checkbutton.config(state=state)
            self.export_mode_merged_button.config(state=state)
            self.export_mode_separate_button.config(state=state)
            self.problem_set_tree.state(["disabled"])
            self.export_queue_list.config(state=state)
            return

        can_load = self._has_authenticated_account()
        can_confirm = self._can_confirm_account()
        tree_selection_exists = bool(self._selected_tree_sources())
        queue_selection = list(self.export_queue_list.curselection())
        single_queue_selection = len(queue_selection) == 1
        has_loaded_problem_sets = bool(self.problem_sets)
        has_queue_items = bool(self.export_queue)
        is_merged = self.export_mode_var.get() == "merged"

        self.login_button.config(state="normal")
        self.switch_account_button.config(state="normal")
        self.confirm_account_button.config(state="normal" if can_confirm else "disabled")
        self.load_problem_sets_button.config(state="normal" if can_load else "disabled")
        self.export_button.config(state="normal" if can_load and has_queue_items else "disabled")
        self.add_to_queue_button.config(state="normal" if has_loaded_problem_sets and tree_selection_exists else "disabled")
        self.remove_from_queue_button.config(state="normal" if queue_selection else "disabled")
        self.move_up_button.config(
            state="normal" if single_queue_selection and queue_selection[0] > 0 else "disabled"
        )
        self.move_down_button.config(
            state="normal"
            if single_queue_selection and queue_selection[0] < len(self.export_queue) - 1
            else "disabled"
        )
        self.start_url_entry.config(state="normal")
        self.output_dir_entry.config(state="disabled" if is_merged else "normal")
        self.output_dir_button.config(state="disabled" if is_merged else "normal")
        self.embed_images_checkbutton.config(state="normal")
        self.export_mode_merged_button.config(state="normal")
        self.export_mode_separate_button.config(state="normal")
        self.problem_set_tree.state(["!disabled"] if has_loaded_problem_sets else ["disabled"])
        self.export_queue_list.config(state="normal" if has_queue_items else "disabled")

    def _run_async(self, status_message: str, job, callback) -> None:
        if self.busy:
            messagebox.showinfo(UiText.DIALOG_WAIT, UiText.wait_message())
            return

        self.busy = True
        self.last_export_warnings = []
        self.logged_warnings.clear()
        self.warning_text_var.set(UiText.NO_WARNING)
        self.export_summary_var.set(UiText.EXPORT_IN_PROGRESS)
        self.status_var.set(status_message)
        self._refresh_ui_state()
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
        self._refresh_ui_state()
        self.status_var.set(UiText.READY)
        if error is not None:
            friendly_error = self._format_error_message(error)
            self._log(friendly_error)
            if details:
                self._log(details)
            self.export_summary_var.set(UiText.TASK_INCOMPLETE)
            self._set_progress(self.progress_value_var.get(), UiText.task_failed(friendly_error), log_message=False)
            messagebox.showerror(UiText.DIALOG_EXPORT_FAILED, friendly_error)
            return
        callback(result)

    def _format_error_message(self, error: Exception) -> str:
        message = str(error).strip()
        if "node.exe" in message:
            return UiText.node_missing()
        if "Microsoft Edge" in message or "Google Chrome" in message:
            return UiText.browser_missing()
        if "未检测到有效登录状态" in message or "用户不存在" in message:
            return UiText.retry_after_login(message)
        if "页面结构已变化" in message or "页面结构变化导致抓取失败" in message:
            return UiText.retry_after_structure_change(message)
        return message

    def _add_selected_problem_sets(self) -> None:
        sources = self._selected_tree_sources()
        if not sources:
            messagebox.showinfo(UiText.DIALOG_NO_SELECTION, UiText.need_add_items())
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
            self._log(UiText.added_to_queue(added_count))
        if skipped_messages:
            detail = "\n".join(skipped_messages[:6])
            if len(skipped_messages) > 6:
                detail += f"\n{UiText.more_tips(len(skipped_messages) - 6)}"
            self._log(detail)
            messagebox.showwarning(UiText.DIALOG_PARTIAL_ITEMS_SKIPPED, detail)

    def _remove_selected_export_items(self) -> None:
        selected_indices = list(self.export_queue_list.curselection())
        if not selected_indices:
            messagebox.showinfo(UiText.DIALOG_NO_SELECTION, UiText.need_remove_items())
            return

        selected_set = set(selected_indices)
        self.export_queue = [item for index, item in enumerate(self.export_queue) if index not in selected_set]
        self._refresh_export_queue_view()
        self._log(UiText.removed_from_queue(len(selected_indices)))

    def _move_export_item(self, direction: int) -> None:
        selected_indices = list(self.export_queue_list.curselection())
        if len(selected_indices) != 1:
            messagebox.showinfo(UiText.DIALOG_NEED_SINGLE_ITEM, UiText.need_single_item())
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
        self._log(UiText.reordered_queue())

    def _refresh_export_queue_view(self, selected_index: int | None = None) -> None:
        self.export_queue_list.config(state="normal")
        self.export_queue_list.delete(0, tk.END)
        for index, item in enumerate(self.export_queue, start=1):
            self.export_queue_list.insert(tk.END, f"{index}. {item.queue_label()}")
        self.queue_summary_var.set(UiText.queue_summary(len(self.export_queue)))
        if selected_index is not None and 0 <= selected_index < len(self.export_queue):
            self.export_queue_list.selection_set(selected_index)
            self.export_queue_list.see(selected_index)
        self._refresh_ui_state()

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
        self._refresh_ui_state()

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
                return UiText.duplicate_queue_item(candidate.queue_label())
            if existing.problem_set_id != candidate.problem_set_id:
                continue
            if candidate.source_kind == "problem_set" and existing.source_kind == "problem_type":
                return UiText.queue_has_problem_type(candidate.problem_set_title)
            if candidate.source_kind == "problem_type" and existing.source_kind == "problem_set":
                return UiText.queue_has_problem_set(candidate.problem_set_title, candidate.type_title)
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
            self.warning_text_var.set(UiText.warning_banner_inline(warnings))
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
