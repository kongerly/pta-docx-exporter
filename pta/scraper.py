from __future__ import annotations

import re
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

from lxml import html

from app_text import DocxText, ParserText, ScraperText
from config import AppConfig
from export.docx_writer import DocxWriter
from models import (
    Assignment,
    ExportResult,
    ExportSummary,
    ExportSourceSummary,
    Problem,
    ProblemImage,
    ProblemSample,
    ProblemSection,
    ProblemSetSummary,
)
from pta.session import PTASessionManager, PageSnapshot, SessionError


SECTION_LABELS = ParserText.SECTION_LABELS
SECTION_TITLES = tuple(SECTION_LABELS.keys())
LIKELY_MOJIBAKE = (
    "棰樼洰",
    "杈撳叆",
    "杈撳嚭",
    "鏍蜂緥",
    "鐧诲綍",
    "娴忚鍣",
    "瀵煎嚭",
    "鍒嗘暟",
    "婊″垎",
    "浣滀笟",
    "鍏抽棴鏃堕棿",
)
EXPECTED_CHINESE = (
    "题目",
    "输入",
    "输出",
    "样例",
    "登录",
    "浏览器",
    "导出",
    "分数",
    "满分",
    "作业",
    "描述",
    "关闭时间",
)
BLOCK_TAGS = {
    "article",
    "blockquote",
    "div",
    "h1",
    "h2",
    "h3",
    "h4",
    "label",
    "li",
    "main",
    "ol",
    "p",
    "pre",
    "section",
    "table",
    "tbody",
    "td",
    "th",
    "tr",
    "ul",
}
TITLE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_.-]+\.(?:png|jpe?g|gif|webp|svg)$", re.IGNORECASE)
SEQUENCE_RE = re.compile(r"\b(?:[A-Za-z]+\d+-\d+|\d+-\d+)\b")
FORMULA_RE = re.compile(r"(10|2)\s*\^\s*(?:\{\s*(\d+)\s*\}|(\d+))")
COMPACT_FORMULA_WRAPPER_RE = re.compile(r"(?P<base>10|2)(?P<exp>\d{1,4})(?P=base)\^(?P=exp)(?P=base)(?P=exp)")
OPTION_LABEL_PATTERN = r"(?:[A-DFTＡ-ＤＦＴ][.．、])"
OPTION_LABEL_LINE_RE = re.compile(rf"(?m)^({OPTION_LABEL_PATTERN})\s*\n+\s*")
INLINE_OPTION_RE = re.compile(rf"(?<!^)([。？！；）\)])({OPTION_LABEL_PATTERN})\s*")
BLANK_TOKEN_RE = re.compile(r"\{\{BLANK:(\d+)\}\}")
BRACKETED_BLANK_RE = re.compile(r"([(\[（【])([ \t]{2,})([)\]）】])")
INLINE_BLANK_RE = re.compile(r"(?<=\S)([ \t]{3,})(?=\S)")

PUBLISHED_ANSWER_MARKERS = ParserText.PUBLISHED_ANSWER_MARKERS

ProgressCallback = Callable[[dict[str, Any]], None]
ExportSourceInput = ProblemSetSummary | ExportSourceSummary


class PTAScraper:
    def __init__(self, config: AppConfig) -> None:
        self.config = config
        self.session = PTASessionManager(config)
        self.writer = DocxWriter()

    def open_login_window(self, start_url: str) -> dict[str, Any]:
        return self.session.ensure_browser_started(start_url)

    def wait_for_login(self, timeout_seconds: int = 300) -> dict[str, Any]:
        return self.session.wait_for_login(timeout_seconds)

    def is_authenticated(self) -> dict[str, Any]:
        return self.session.is_authenticated()

    def get_current_user(self) -> dict[str, Any]:
        return self.session.get_current_user()

    def switch_account(self, start_url: str) -> dict[str, Any]:
        return self.session.switch_account(start_url)

    def close_login_window(self) -> dict[str, Any]:
        return self.session.close_login_window()

    @staticmethod
    def normalize_account_id(value: str | None) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()

    def ensure_target_account(
        self,
        target_account: str,
        *,
        auth_state: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_target = self.normalize_account_id(target_account)
        if not normalized_target:
            raise SessionError(ScraperText.TARGET_ACCOUNT_REQUIRED)

        state = auth_state or self.get_current_user()
        if not state.get("authenticated"):
            raise SessionError(str(state.get("message") or ScraperText.LOGIN_REQUIRED))

        current_account = self.normalize_account_id(state.get("accountId"))
        if not current_account:
            raise SessionError(ScraperText.ACCOUNT_UNKNOWN)

        if current_account != normalized_target:
            current_display = str(state.get("displayName") or state.get("accountId") or "").strip()
            raise SessionError(ScraperText.account_mismatch(current_display or str(state.get("accountId") or ""), target_account))

        return state

    def load_problem_sets(
        self,
        *,
        target_account: str | None = None,
        auth_state: dict[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ProblemSetSummary]:
        if target_account is not None:
            self.ensure_target_account(target_account, auth_state=auth_state)
        self._emit_progress(progress_callback, percent=0, message=ScraperText.PROBLEM_SET_LIST_LOADING)
        snapshot = self.session.snapshot(self.config.start_url, options=self._problem_set_list_snapshot_options())
        self._assert_snapshot_usable(snapshot)
        items = self._extract_problem_sets_from_dom_snapshot(snapshot)
        if not items:
            raise SessionError(ScraperText.PROBLEM_SET_LIST_EMPTY)
        self._emit_progress(progress_callback, percent=100, message=ScraperText.problem_sets_loaded(len(items)))
        return items

    def load_problem_set_types(
        self,
        problem_set: ProblemSetSummary,
        *,
        target_account: str | None = None,
        auth_state: dict[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> list[ExportSourceSummary]:
        if target_account is not None:
            self.ensure_target_account(target_account, auth_state=auth_state)
        self._emit_progress(progress_callback, percent=0, message=ScraperText.loading_problem_types(problem_set.title))

        for url in self._problem_type_page_candidates(problem_set.url):
            try:
                snapshot = self.session.snapshot(url, options=self._problem_set_snapshot_options())
                self._assert_snapshot_usable(snapshot)
            except SessionError:
                raise
            except Exception:
                continue
            items = self._extract_problem_types_from_snapshot(snapshot, problem_set)
            if items:
                self._emit_progress(
                    progress_callback,
                    percent=100,
                    message=ScraperText.problem_types_loaded(problem_set.title, len(items)),
                )
                return items

        self._emit_progress(progress_callback, percent=100, message=ScraperText.problem_types_not_found(problem_set.title))
        return []

    def export_problem_sets(
        self,
        problem_sets: list[ExportSourceInput],
        output_dir: Path,
        embed_images: bool,
        export_mode: str = "merged",
        merged_filename_stem: str | None = None,
        *,
        target_account: str | None = None,
        auth_state: dict[str, Any] | None = None,
        progress_callback: ProgressCallback | None = None,
    ) -> ExportResult:
        if target_account is not None:
            self.ensure_target_account(target_account, auth_state=auth_state)
        if export_mode not in {"merged", "separate"}:
            raise ValueError(ScraperText.unsupported_export_mode(export_mode))
        export_sources = [self._normalize_export_source(item) for item in problem_sets]
        materialized: list[Assignment] = []
        warnings: list[str] = []
        total_sets = len(export_sources)
        self._emit_progress(progress_callback, percent=0, message=ScraperText.preparing_export(total_sets))

        for set_index, export_source in enumerate(export_sources, start=1):
            source_label = export_source.queue_label()
            self._emit_export_progress(
                progress_callback,
                problem_set_index=set_index,
                problem_set_total=total_sets,
                problem_set_title=source_label,
                message=ScraperText.exporting_problem_set(set_index, total_sets, source_label),
            )
            assignment = self._materialize_export_source(
                export_source,
                embed_images=embed_images,
                progress_callback=progress_callback,
                problem_set_index=set_index,
                problem_set_total=total_sets,
            )
            materialized.append(assignment)
            warnings.extend(assignment.warnings)
            self._emit_export_progress(
                progress_callback,
                problem_set_index=set_index,
                problem_set_total=total_sets,
                problem_set_title=source_label,
                expected_problem_total=assignment.expected_problem_total,
                parsed_problem_total=assignment.parsed_problem_total,
                warnings=list(assignment.warnings),
                finished_set=True,
                message=ScraperText.exported_problem_set(
                    set_index,
                    total_sets,
                    source_label,
                    assignment.parsed_problem_total,
                    assignment.expected_problem_total,
                ),
            )

        self._emit_progress(
            progress_callback,
            percent=100,
            message=ScraperText.EXPORT_GENERATING,
            warnings=list(warnings),
        )
        output_paths = self._write_export_documents(
            materialized,
            output_dir,
            export_mode,
            merged_filename_stem=merged_filename_stem,
        )
        primary_output_path = str(output_paths[0]) if output_paths else ""
        result = ExportResult(
            output_path=primary_output_path,
            output_paths=[str(path) for path in output_paths],
            export_mode=export_mode,
            warnings=warnings,
            summary=self._build_export_summary(materialized, warnings),
        )
        output_path = primary_output_path
        self._emit_progress(
            progress_callback,
            percent=100,
            message=ScraperText.export_completed(output_path),
            warnings=list(warnings),
        )
        return result

    def shutdown(self) -> None:
        self.session.close()

    def _build_export_summary(self, assignments: list[Assignment], warnings: list[str]) -> ExportSummary:
        expected_problem_total = sum(max(assignment.expected_problem_total, 0) for assignment in assignments)
        parsed_problem_total = sum(max(assignment.parsed_problem_total, 0) for assignment in assignments)
        image_warning_count = sum(1 for warning in warnings if "图片" in warning)
        return ExportSummary(
            exported_problem_set_count=len(assignments),
            expected_problem_total=expected_problem_total,
            parsed_problem_total=parsed_problem_total,
            failed_problem_total=max(expected_problem_total - parsed_problem_total, 0),
            warning_count=len(warnings),
            image_warning_count=image_warning_count,
        )

    def _write_export_documents(
        self,
        assignments: list[Assignment],
        output_dir: Path,
        export_mode: str,
        *,
        merged_filename_stem: str | None = None,
    ) -> list[Path]:
        if export_mode == "merged":
            merged_name = merged_filename_stem or self._build_merged_filename(assignments)
            return [self.writer.write_document(merged_name, assignments, output_dir, filename_stem=merged_name)]

        output_paths: list[Path] = []
        for index, assignment in enumerate(assignments, start=1):
            output_paths.append(
                self.writer.write_document(
                    assignment.title,
                    [assignment],
                    output_dir,
                    filename_stem=assignment.title,
                )
            )
        return output_paths

    def _build_merged_filename(self, assignments: list[Assignment]) -> str:
        titles = [assignment.title.strip() for assignment in assignments if assignment.title.strip()]
        return ScraperText.merged_export_name(titles)

    def _normalize_export_source(self, source: ExportSourceInput) -> ExportSourceSummary:
        if isinstance(source, ExportSourceSummary):
            return source
        return ExportSourceSummary.from_problem_set(source)

    def _materialize_export_source(
        self,
        export_source: ExportSourceSummary,
        *,
        embed_images: bool,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
    ) -> Assignment:
        if export_source.source_kind == "problem_type":
            return self._materialize_problem_type_source(
                export_source,
                embed_images=embed_images,
                progress_callback=progress_callback,
                problem_set_index=problem_set_index,
                problem_set_total=problem_set_total,
            )
        return self._materialize_problem_set_source(
            export_source,
            embed_images=embed_images,
            progress_callback=progress_callback,
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
        )

    def _materialize_problem_set(
        self,
        problem_set: ProblemSetSummary,
        *,
        embed_images: bool,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
    ) -> Assignment:
        return self._materialize_problem_set_source(
            ExportSourceSummary.from_problem_set(problem_set),
            embed_images=embed_images,
            progress_callback=progress_callback,
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
        )

    def _materialize_problem_set_source(
        self,
        export_source: ExportSourceSummary,
        *,
        embed_images: bool,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
    ) -> Assignment:
        snapshots = self._load_snapshots(
            self._problem_page_candidates(export_source.url),
            options=self._problem_set_snapshot_options(),
        )
        fallback_snapshot = snapshots[0] if snapshots else self.session.snapshot(
            export_source.url,
            options=self._problem_detail_snapshot_options(),
        )
        self._assert_snapshot_usable(fallback_snapshot)
        return self._build_assignment_from_snapshots(
            export_source,
            snapshots or [fallback_snapshot],
            fallback_snapshot=fallback_snapshot,
            embed_images=embed_images,
            progress_callback=progress_callback,
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
        )

    def _materialize_problem_type_source(
        self,
        export_source: ExportSourceSummary,
        *,
        embed_images: bool,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
    ) -> Assignment:
        snapshots = self._load_snapshots([export_source.url], options=self._problem_set_snapshot_options())
        if not snapshots:
            fallback_snapshot = self.session.snapshot(export_source.url, options=self._problem_detail_snapshot_options())
            self._assert_snapshot_usable(fallback_snapshot)
            snapshots = [fallback_snapshot]
        fallback_snapshot = snapshots[0]
        return self._build_assignment_from_snapshots(
            export_source,
            snapshots,
            fallback_snapshot=fallback_snapshot,
            embed_images=embed_images,
            progress_callback=progress_callback,
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
        )

    def _load_snapshots(self, urls: list[str], *, options: dict[str, Any]) -> list[PageSnapshot]:
        snapshots: list[PageSnapshot] = []
        for url in urls:
            try:
                snapshot = self.session.snapshot(url, options=options)
                self._assert_snapshot_usable(snapshot)
                snapshots.append(snapshot)
            except SessionError:
                raise
            except Exception:
                continue
        return snapshots

    def _build_assignment_from_snapshots(
        self,
        export_source: ExportSourceSummary,
        snapshots: list[PageSnapshot],
        *,
        fallback_snapshot: PageSnapshot,
        embed_images: bool,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
    ) -> Assignment:
        source_label = export_source.queue_label()
        assignment_title = export_source.export_title()

        for snapshot in snapshots:
            inline_problems = self._extract_inline_problems_from_snapshot(snapshot)
            if not inline_problems:
                continue
            warnings: list[str] = []
            if embed_images:
                warnings.extend(
                    self._download_problem_images(
                        inline_problems,
                        progress_callback=progress_callback,
                        problem_set_index=problem_set_index,
                        problem_set_total=problem_set_total,
                        problem_set_title=source_label,
                    )
                )
            expected_total = export_source.problem_count or self._expected_inline_problem_total(snapshot, inline_problems)
            warnings.extend(self._build_problem_total_warnings(source_label, expected_total, len(inline_problems)))
            return Assignment(
                id=export_source.id,
                title=assignment_title,
                url=export_source.url,
                course_name=DocxText.DEFAULT_SET_NAME,
                expected_problem_total=expected_total,
                parsed_problem_total=len(inline_problems),
                warnings=warnings,
                problems=inline_problems,
            )

        for snapshot in snapshots:
            problem_links = self._extract_problem_links(snapshot)
            if not problem_links:
                continue
            expected_total = export_source.problem_count or len(problem_links)
            problems: list[Problem] = []
            warnings: list[str] = []
            seen_urls: set[str] = set()

            for problem_index, item in enumerate(problem_links, start=1):
                if item["url"] in seen_urls:
                    continue
                seen_urls.add(item["url"])
                self._emit_export_progress(
                    progress_callback,
                    problem_set_index=problem_set_index,
                    problem_set_total=problem_set_total,
                    problem_set_title=source_label,
                    problem_index=problem_index,
                    problem_total=expected_total,
                    expected_problem_total=expected_total,
                    parsed_problem_total=len(problems),
                    problem_title=item["name"] or item["sequence_label"] or item["url"],
                    message=ScraperText.exporting_problem(
                        problem_set_index,
                        problem_set_total,
                        source_label,
                        problem_index,
                        expected_total,
                        item["name"] or item["sequence_label"] or item["url"],
                    ),
                )
                try:
                    problem_snapshot = self.session.snapshot(item["url"], options=self._problem_detail_snapshot_options())
                    self._assert_snapshot_usable(problem_snapshot)
                    problem = self._parse_problem_snapshot(
                        problem_snapshot,
                        title_hint=item["name"],
                        sequence_label=item["sequence_label"],
                        title_source="list-link",
                    )
                    if embed_images:
                        warnings.extend(self._download_images(problem))
                    problems.append(problem)
                except Exception as error:
                    title = item["name"] or item["sequence_label"] or item["url"]
                    warnings.append(ScraperText.problem_fetch_failed(title, error))

            warnings.extend(self._build_problem_total_warnings(source_label, expected_total, len(problems)))
            return Assignment(
                id=export_source.id,
                title=assignment_title,
                url=export_source.url,
                course_name=DocxText.DEFAULT_SET_NAME,
                expected_problem_total=expected_total,
                parsed_problem_total=len(problems),
                warnings=warnings,
                problems=problems,
            )

        problem = self._parse_problem_snapshot(
            fallback_snapshot,
            title_hint=assignment_title,
            title_source=export_source.source_kind,
        )
        warnings: list[str] = []
        if embed_images:
            warnings.extend(self._download_images(problem))
        return Assignment(
            id=export_source.id,
            title=assignment_title,
            url=export_source.url,
            course_name=DocxText.DEFAULT_SET_NAME,
            expected_problem_total=1,
            parsed_problem_total=1,
            warnings=warnings,
            problems=[problem],
        )

    def _problem_page_candidates(self, overview_url: str) -> list[str]:
        base = overview_url.rsplit("/overview", 1)[0] if overview_url.endswith("/overview") else overview_url.rstrip("/")
        candidates = [
            f"{base}/exam/problems/type",
            f"{base}/problems/type",
            f"{base}/exam/problems",
            f"{base}/problems",
            overview_url,
        ]
        unique: list[str] = []
        seen: set[str] = set()
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            unique.append(url)
        return unique

    def _problem_type_page_candidates(self, overview_url: str) -> list[str]:
        base = overview_url.rsplit("/overview", 1)[0] if overview_url.endswith("/overview") else overview_url.rstrip("/")
        candidates = [
            f"{base}/exam/problems",
            f"{base}/exam/problems/type/1",
            f"{base}/exam/problems/type",
            f"{base}/problems/type/1",
            f"{base}/problems/type",
        ]
        unique: list[str] = []
        seen: set[str] = set()
        for url in candidates:
            if url in seen:
                continue
            seen.add(url)
            unique.append(url)
        return unique

    def _problem_set_list_snapshot_options(self) -> dict[str, Any]:
        return {
            "autoScroll": True,
            "waitForProblemCountStable": True,
            "problemSelector": 'div.pc-list.space-y-4 a[href*="/problem-sets/"][href*="/overview"]',
        }

    def _problem_set_snapshot_options(self) -> dict[str, Any]:
        return {
            "expandAll": True,
            "autoScroll": True,
            "waitForProblemCountStable": True,
            "problemSelector": '.pc-x[id], a[href*="/problems/"]',
        }

    def _problem_detail_snapshot_options(self) -> dict[str, Any]:
        return {
            "expandAll": True,
            "autoScroll": True,
        }

    def _assert_snapshot_usable(self, snapshot: PageSnapshot) -> None:
        combined = self._normalize_text(f"{snapshot.title}\n{snapshot.body_text or ''}")
        if "用户不存在" in combined:
            raise SessionError(ScraperText.session_expired_user_missing())
        if "错误信息" in combined and "重新加载" in combined:
            raise SessionError(ScraperText.snapshot_error_page())

    def _extract_problem_sets_from_dom_snapshot(self, snapshot: PageSnapshot) -> list[ProblemSetSummary]:
        document = html.fromstring(snapshot.html)
        anchors = document.xpath(
            '//div[contains(@class,"pc-list") and contains(@class,"space-y-4")]'
            '//a[contains(@href,"/problem-sets/") and contains(@href,"/overview")]'
        )
        items: list[ProblemSetSummary] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            url = urljoin(snapshot.url, href)
            if url in seen:
                continue
            title = (
                self._normalize_text((anchor.xpath('.//*[@title][1]/@title') or [""])[0])
                or self._normalize_text("".join(anchor.xpath('.//*[contains(@class,"font-bold")][1]//text()')))
                or self._normalize_text("".join(anchor.xpath('.//*[contains(@class,"text-sm")][1]//text()')))
            )
            if not title:
                continue
            seen.add(url)
            text = self._normalize_text(" ".join(anchor.xpath(".//text()")))
            end_match = re.search(r"关闭时间[:：]?\s*([0-9:\-\s]+)", text)
            owner_candidates = [
                self._normalize_text(text)
                for text in anchor.xpath('.//*[contains(@class,"pc-text-raw")]/text()')
                if self._normalize_text(text)
            ]
            owner = owner_candidates[-1] if owner_candidates else ""
            identifier_match = re.search(r"/problem-sets/([^/]+)/overview", href)
            items.append(
                ProblemSetSummary(
                    id=identifier_match.group(1) if identifier_match else href,
                    title=title,
                    url=url,
                    ends_at=end_match.group(1).strip() if end_match else "",
                    owner=owner,
                )
            )
        return items

    def _extract_problem_types_from_snapshot(
        self,
        snapshot: PageSnapshot,
        problem_set: ProblemSetSummary,
    ) -> list[ExportSourceSummary]:
        document = html.fromstring(snapshot.html)
        anchors = document.xpath('//a[contains(@href,"/problems/type/")]')
        items: list[ExportSourceSummary] = []
        seen: set[str] = set()

        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            url = urljoin(snapshot.url, href)
            parsed = urlparse(url)
            normalized_path = parsed.path.rstrip("/")
            if parsed.query:
                continue
            if not re.search(r"/(?:exam/)?problems/type/\d+$", normalized_path):
                continue
            if url in seen:
                continue

            label = (
                self._normalize_text("".join(anchor.xpath('.//*[contains(@class,"text-sm")][1]//text()')))
                or self._normalize_text("".join(anchor.xpath('.//*[contains(@class,"pc-text-raw")][1]//text()')))
                or self._normalize_text("".join(anchor.xpath(".//text()")))
            )
            if not label:
                continue

            count_tokens = [
                token
                for token in (
                    self._normalize_text(text, preserve_newlines=False)
                    for text in anchor.xpath('.//*[contains(@class,"font-mono")]//text()')
                )
                if token.isdigit()
            ]
            problem_count = int(count_tokens[-1]) if count_tokens else 0
            if problem_count <= 0:
                continue

            type_id = normalized_path.rsplit("/", 1)[-1]
            seen.add(url)
            items.append(
                ExportSourceSummary(
                    id=f"{problem_set.id}:type:{type_id}",
                    title=label,
                    url=url,
                    source_kind="problem_type",
                    parent_problem_set_id=problem_set.id,
                    parent_title=problem_set.title,
                    type_label=label,
                    starts_at=problem_set.starts_at,
                    ends_at=problem_set.ends_at,
                    owner=problem_set.owner,
                    problem_count=problem_count,
                )
            )

        return items

    def _extract_inline_problems_from_snapshot(self, snapshot: PageSnapshot) -> list[Problem]:
        document = html.fromstring(snapshot.html)
        roots = document.xpath(
            '//div[contains(@class,"flex") and contains(@class,"flex-col") and contains(@class,"m-4") and contains(@class,"mb-0") and contains(@class,"flex-1")]'
        )
        problems: list[Problem] = []
        seen_ids: set[str] = set()
        for root in roots:
            nodes = root.xpath('./div[contains(@class,"pc-x")]')
            for index, node in enumerate(nodes, start=1):
                problem = self._parse_inline_problem_node(node, snapshot.url, index)
                if problem.id in seen_ids:
                    continue
                seen_ids.add(problem.id)
                problems.append(problem)
        return problems

    def _parse_inline_problem_node(self, node: html.HtmlElement, base_url: str, index: int) -> Problem:
        problem_id = (node.get("id") or "").strip() or f"inline-{index}"
        sequence_label = self._extract_sequence_label(node)
        title_hint = self._extract_problem_title_hint(node)
        title, title_source = self._choose_problem_title(
            sequence_label=sequence_label,
            title_hint=title_hint,
            title_source="inline-list",
            snapshot_url=f"{base_url}#{problem_id}",
        )
        score = self._extract_score(node, "")
        content_root = self._inline_problem_content_root(node)
        prepared_root = self._prepared_content_root(content_root)
        uses_scoped_content_root = content_root is not node
        sections, samples = self._extract_sections_and_samples(prepared_root)
        images = self._extract_images(prepared_root, base_url)

        problem = Problem(
            id=problem_id,
            title=title,
            url=f"{base_url}#{problem_id}",
            score=score,
            sequence_label=sequence_label,
            title_source=title_source,
            sections=sections
            or [ProblemSection(kind="description", title=DocxText.DESCRIPTION_HEADING, content=self._fallback_problem_content(prepared_root))],
            samples=samples,
            images=images,
        )
        return self._finalize_problem(problem, promote_inline_title=uses_scoped_content_root)

    def _inline_problem_content_root(self, node: html.HtmlElement) -> html.HtmlElement:
        content_nodes = node.xpath('./div[contains(@class,"mt-4")]')
        return content_nodes[0] if content_nodes else node

    def _prepared_content_root(self, root: html.HtmlElement) -> html.HtmlElement:
        prepared = deepcopy(root)
        blank_nodes = prepared.xpath('.//*[@data-blank-index]')
        for blank_node in blank_nodes:
            blank_node.text = "____"
            for child in list(blank_node):
                blank_node.remove(child)
        return prepared

    def _extract_problem_links(self, snapshot: PageSnapshot) -> list[dict[str, str]]:
        document = html.fromstring(snapshot.html)
        anchors = document.xpath('//a[contains(@href,"/problems/")]')
        results: list[dict[str, str]] = []
        seen: set[str] = set()
        for anchor in anchors:
            href = (anchor.get("href") or "").strip()
            if not href:
                continue
            normalized = urljoin(snapshot.url, href)
            if normalized in seen:
                continue
            seen.add(normalized)
            text = self._normalize_text(" ".join(anchor.xpath(".//text()")))
            sequence_label = self._extract_sequence_from_text(text)
            results.append(
                {
                    "id": self._slug(f"{text}-{normalized}"),
                    "name": "" if self._is_bad_title_candidate(text) else text,
                    "sequence_label": sequence_label,
                    "url": normalized,
                }
            )
        return results

    def _download_problem_images(
        self,
        problems: list[Problem],
        *,
        progress_callback: ProgressCallback | None,
        problem_set_index: int,
        problem_set_total: int,
        problem_set_title: str,
    ) -> list[str]:
        warnings: list[str] = []
        total_problems = len(problems)
        for problem_index, problem in enumerate(problems, start=1):
            self._emit_export_progress(
                progress_callback,
                problem_set_index=problem_set_index,
                problem_set_total=problem_set_total,
                problem_set_title=problem_set_title,
                problem_index=problem_index,
                problem_total=total_problems,
                expected_problem_total=total_problems,
                parsed_problem_total=problem_index - 1,
                problem_title=problem.title,
                message=ScraperText.exporting_problem(
                    problem_set_index,
                    problem_set_total,
                    problem_set_title,
                    problem_index,
                    total_problems,
                    problem.title,
                ),
            )
            warnings.extend(self._download_images(problem))
        return warnings

    def _download_images(self, problem: Problem) -> list[str]:
        warnings: list[str] = []
        for index, image in enumerate(problem.images, start=1):
            try:
                data, content_type = self.session.download_bytes(
                    image.url,
                    base_url=problem.url,
                    referer=problem.url,
                )
            except Exception as error:
                warnings.append(ScraperText.image_download_failed(problem.title, error))
                continue

            suffix = self._suffix_from_content_type(content_type, image.url)
            target = self.config.temp_dir / f"{self._slug(problem.id or problem.title)}-{index}{suffix}"
            try:
                target.write_bytes(data)
                image.local_path = str(target)
            except OSError as error:
                warnings.append(ScraperText.image_write_failed(problem.title, error))
        return warnings

    def _parse_problem_snapshot(
        self,
        snapshot: PageSnapshot,
        *,
        title_hint: str = "",
        sequence_label: str = "",
        title_source: str = "",
    ) -> Problem:
        document = html.fromstring(snapshot.html)
        self._remove_noise(document)
        root = self._content_root(document)
        prepared_root = self._prepared_content_root(root)
        page_heading = self._extract_page_heading(prepared_root)
        title, resolved_title_source = self._choose_problem_title(
            sequence_label=sequence_label,
            title_hint=title_hint,
            title_source=title_source or "page",
            page_heading=page_heading,
            page_title=snapshot.title,
            snapshot_url=snapshot.url,
        )

        sections, samples = self._extract_sections_and_samples(prepared_root)
        images = self._extract_images(prepared_root, snapshot.url)
        score = self._extract_score(prepared_root, snapshot.title)
        problem = Problem(
            id=self._slug(title or snapshot.url),
            title=title,
            url=snapshot.url,
            score=score,
            sequence_label=sequence_label,
            title_source=resolved_title_source,
            sections=sections
            or [ProblemSection(kind="description", title=DocxText.DESCRIPTION_HEADING, content=self._fallback_problem_content(prepared_root))],
            samples=samples,
            images=images,
        )
        return self._finalize_problem(problem)

    def _extract_sections_and_samples(self, root: html.HtmlElement) -> tuple[list[ProblemSection], list[ProblemSample]]:
        rendered = self._render_element_text(root)
        protected = self._protect_blank_placeholders(rendered)
        normalized = self._normalize_text(protected, preserve_newlines=True)
        if not normalized:
            return [], []

        sections = self._extract_sections_from_text(normalized)
        samples = self._build_samples_from_sections(sections)
        if samples:
            sections = [section for section in sections if not section.kind.startswith("sample")]
        return sections, samples

    def _extract_sections_from_text(self, text: str) -> list[ProblemSection]:
        title_pattern = "|".join(re.escape(title) for title in SECTION_TITLES)
        pattern = re.compile(rf"(?m)^(?P<title>{title_pattern})\s*$")
        matches = list(pattern.finditer(text))
        if not matches:
            return []

        sections: list[ProblemSection] = []
        seen: set[tuple[str, str]] = set()
        for index, match in enumerate(matches):
            next_start = matches[index + 1].start() if index + 1 < len(matches) else len(text)
            content = text[match.end():next_start].strip()
            if not content:
                continue
            title = match.group("title")
            kind = SECTION_LABELS[title]
            cleaned = self._clean_section_content(content)
            if not cleaned:
                continue
            key = (kind, cleaned)
            if key in seen:
                continue
            seen.add(key)
            sections.append(ProblemSection(kind=kind, title=title, content=cleaned))
        return sections

    def _build_samples_from_sections(self, sections: list[ProblemSection]) -> list[ProblemSample]:
        input_blocks = []
        output_blocks = []
        for section in sections:
            if section.kind == "sample_input":
                input_blocks.extend(self._split_sample_blocks(section.content))
            elif section.kind == "sample_output":
                output_blocks.extend(self._split_sample_blocks(section.content))

        samples: list[ProblemSample] = []
        max_len = max(len(input_blocks), len(output_blocks))
        for index in range(max_len):
            samples.append(
                ProblemSample(
                    input_text=input_blocks[index] if index < len(input_blocks) else "",
                    output_text=output_blocks[index] if index < len(output_blocks) else "",
                )
            )
        return samples

    def _split_sample_blocks(self, content: str) -> list[str]:
        blocks = [block.strip() for block in re.split(r"\n{2,}", content) if block.strip()]
        return blocks or ([content] if content.strip() else [])

    def _extract_images(self, root: html.HtmlElement, base_url: str) -> list[ProblemImage]:
        images: list[ProblemImage] = []
        seen: set[str] = set()
        for element in root.xpath('.//img[@src]'):
            src = (element.get("src") or "").strip()
            if not src:
                continue
            url = urljoin(base_url, src)
            if url in seen:
                continue
            seen.add(url)
            alt = self._normalize_text(element.get("alt", ""))
            if TITLE_FILENAME_RE.fullmatch(alt):
                alt = ""
            images.append(ProblemImage(url=url, alt=alt))
        return images

    def _extract_score(self, root: html.HtmlElement, fallback_title: str) -> str:
        text = self._normalize_text(" ".join(root.xpath(".//text()")))
        match = re.search(r"(\d+(?:\.\d+)?)\s*分", text)
        if match:
            return match.group(1)
        fallback_match = re.search(r"(\d+(?:\.\d+)?)\s*分", self._normalize_text(fallback_title))
        return fallback_match.group(1) if fallback_match else ""

    def _extract_sequence_label(self, node: html.HtmlElement) -> str:
        candidates = [
            self._normalize_text("".join(node.xpath('.//button[1]//text()'))),
            self._normalize_text("".join(node.xpath('.//*[contains(@class,"text-xs")][1]//text()'))),
            self._normalize_text((node.xpath('.//*[@data-label][1]/@data-label') or [""])[0]),
        ]
        for candidate in candidates:
            sequence = self._extract_sequence_from_text(candidate)
            if sequence:
                return sequence
        return ""

    def _extract_problem_title_hint(self, node: html.HtmlElement) -> str:
        candidates = [
            self._normalize_text((node.xpath('.//*[@title][1]/@title') or [""])[0]),
            self._normalize_text("".join(node.xpath('.//*[contains(@class,"font-bold")][1]//text()'))),
            self._normalize_text("".join(node.xpath('.//*[@aria-label][1]/@aria-label'))),
        ]
        for candidate in candidates:
            if candidate and not self._is_bad_title_candidate(candidate):
                return candidate
        return ""

    def _choose_problem_title(
        self,
        *,
        sequence_label: str = "",
        title_hint: str = "",
        title_source: str = "",
        page_heading: str = "",
        page_title: str = "",
        snapshot_url: str = "",
    ) -> tuple[str, str]:
        cleaned_page_title = self._strip_site_suffix(self._normalize_text(page_title))
        url_title = self._title_from_url(snapshot_url)
        candidates = [
            (title_hint, title_source or "title-hint"),
            (sequence_label, "sequence-label"),
            (page_heading, "page-heading"),
            (cleaned_page_title, "page-title"),
            (url_title, "url"),
        ]
        for candidate, source in candidates:
            normalized = self._normalize_text(candidate)
            if normalized and not self._is_bad_title_candidate(normalized):
                return normalized, source
        return ScraperText.UNTITLED_PROBLEM, "fallback"

    def _extract_page_heading(self, root: html.HtmlElement) -> str:
        for node in root.xpath(".//*[self::h1 or self::h2 or self::h3][normalize-space()]"):
            candidate = self._normalize_text("".join(node.xpath(".//text()")))
            if candidate and candidate not in SECTION_LABELS and not self._is_bad_title_candidate(candidate):
                return candidate
        return ""

    def _content_root(self, document: html.HtmlElement) -> html.HtmlElement:
        nodes = document.xpath("//main | //article | //section[contains(@class,'problem')]")
        return nodes[0] if nodes else document

    def _remove_noise(self, root: html.HtmlElement) -> None:
        for node in root.xpath(
            ".//script | .//style | .//noscript | .//header | .//footer | .//aside | .//nav | .//form | .//button"
        ):
            parent = node.getparent()
            if parent is not None:
                parent.remove(node)

    def _render_element_text(self, element: html.HtmlElement) -> str:
        parts: list[str] = []
        if element.text:
            parts.append(element.text)
        for child in element:
            if not isinstance(child.tag, str):
                continue
            tag = child.tag.lower()
            if tag == "br":
                parts.append("\n")
            elif tag == "sup":
                parts.append("^" + self._render_inline_text(child))
            elif tag == "sub":
                parts.append("_" + self._render_inline_text(child))
            else:
                child_text = self._render_element_text(child)
                if tag in BLOCK_TAGS:
                    if child_text.strip():
                        parts.append("\n" + child_text.strip() + "\n")
                else:
                    parts.append(child_text)
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def _render_inline_text(self, element: html.HtmlElement) -> str:
        parts: list[str] = []
        if element.text:
            parts.append(element.text)
        for child in element:
            if not isinstance(child.tag, str):
                continue
            tag = child.tag.lower()
            if tag == "sup":
                parts.append("^" + self._render_inline_text(child))
            elif tag == "sub":
                parts.append("_" + self._render_inline_text(child))
            else:
                parts.append(self._render_inline_text(child))
            if child.tail:
                parts.append(child.tail)
        return "".join(parts)

    def _fallback_problem_content(self, root: html.HtmlElement) -> str:
        protected = self._protect_blank_placeholders(self._render_element_text(root))
        content = self._normalize_text(protected, preserve_newlines=True)
        return self._clean_section_content(content)

    def _finalize_problem(self, problem: Problem, *, promote_inline_title: bool = False) -> Problem:
        finalized_sections: list[ProblemSection] = []
        for index, section in enumerate(problem.sections):
            content = self._clean_section_content(section.content)
            if index == 0:
                for title_variant in self._problem_title_variants(problem):
                    content = self._strip_leading_problem_label(content, title_variant)
                if promote_inline_title:
                    problem.title, content = self._promote_leading_line_to_title(
                        problem.title,
                        problem.sequence_label,
                        content,
                    )
                if section.kind == "description" and self._is_duplicate_problem_prompt(problem, content):
                    content = ""
            if content:
                finalized_sections.append(ProblemSection(kind=section.kind, title=section.title, content=content))
        problem.sections = finalized_sections

        finalized_samples: list[ProblemSample] = []
        for sample in problem.samples:
            input_text = self._clean_section_content(sample.input_text)
            output_text = self._clean_section_content(sample.output_text)
            note = self._clean_section_content(sample.note)
            if input_text or output_text or note:
                finalized_samples.append(ProblemSample(input_text=input_text, output_text=output_text, note=note))
        problem.samples = finalized_samples
        return problem

    def _clean_section_content(self, content: str) -> str:
        if not content:
            return ""
        protected = self._protect_blank_placeholders(content)
        normalized = self._normalize_text(protected, preserve_newlines=True)
        normalized = self._strip_published_answer_content(normalized)
        normalized = self._split_inline_options(normalized)
        normalized = self._merge_option_lines(normalized)
        cleaned_lines: list[str] = []
        for raw_line in normalized.splitlines():
            line = self._strip_problem_metadata(raw_line)
            line = self._normalize_text(line, preserve_newlines=False)
            if line:
                cleaned_lines.append(line)
        cleaned = "\n".join(line for line in cleaned_lines if line).strip()
        return self._restore_blank_placeholders(cleaned)

    def _strip_problem_metadata(self, value: str) -> str:
        text = value
        text = re.sub(r"\b分数\s*\d+(?:\.\d+)?\b", "", text)
        text = re.sub(r"\b作者\s*[^\s，。；:：]+", "", text)
        text = re.sub(r"\b关闭时间[:：]?\s*[0-9:\-\s]+", "", text)
        text = re.sub(rf"\b单位\s*[^\n]+?(?=(?:\s+\d+-\d+\s+|\s+{OPTION_LABEL_PATTERN}\s+|$))", "", text)
        return text

    def _strip_leading_problem_label(self, content: str, label: str) -> str:
        if not content or not label:
            return content
        return re.sub(rf"^{re.escape(label)}[\s:：.．、-]*", "", content).strip()

    def _problem_title_variants(self, problem: Problem) -> list[str]:
        candidates = [problem.sequence_label, problem.title]
        if problem.title and problem.sequence_label:
            stripped_title = self._strip_leading_problem_label(problem.title, problem.sequence_label)
            if stripped_title:
                candidates.append(stripped_title)

        variants: list[str] = []
        seen: set[str] = set()
        for candidate in candidates:
            normalized = self._normalize_text(candidate, preserve_newlines=False)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            variants.append(normalized)
        return variants

    def _is_duplicate_problem_prompt(self, problem: Problem, content: str) -> bool:
        normalized_content = self._normalize_text(content, preserve_newlines=False)
        if not normalized_content:
            return False
        return normalized_content in self._problem_title_variants(problem)

    def _strip_published_answer_content(self, content: str) -> str:
        lines = [line.rstrip() for line in content.splitlines()]
        kept_lines: list[str] = []
        for line in lines:
            normalized = self._normalize_text(line, preserve_newlines=False)
            if normalized and any(normalized.startswith(marker) for marker in PUBLISHED_ANSWER_MARKERS):
                break
            kept_lines.append(line)
        return "\n".join(kept_lines).strip()

    def _promote_leading_line_to_title(self, title: str, sequence_label: str, content: str) -> tuple[str, str]:
        if not title or not sequence_label or title != sequence_label or not content:
            return title, content
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        if not lines:
            return title, content
        leading_line = lines[0]
        leading_sequence = self._extract_sequence_from_text(leading_line)
        if leading_sequence and leading_sequence != sequence_label:
            promoted_title = f"{title} {leading_line}".strip()
            remaining = "\n".join(lines[1:]).strip()
            if not remaining:
                return promoted_title, content
            return promoted_title, remaining
        if OPTION_LABEL_LINE_RE.match(leading_line):
            return title, content
        promoted_title = f"{title} {leading_line}".strip()
        remaining = "\n".join(lines[1:]).strip()
        if not remaining:
            return title, content
        return promoted_title, remaining

    def _normalize_text(self, value: str, *, preserve_newlines: bool = False) -> str:
        repaired = self._repair_mojibake(value or "")
        repaired = repaired.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ").replace("\u200b", "")
        repaired = repaired.replace("гм", "，")
        repaired = COMPACT_FORMULA_WRAPPER_RE.sub(
            lambda match: f"{match.group('base')}^{match.group('exp')}",
            repaired,
        )
        repaired = FORMULA_RE.sub(lambda match: f"{match.group(1)}^{match.group(2) or match.group(3)}", repaired)
        repaired = self._dedupe_formula_expansions(repaired)
        if preserve_newlines:
            repaired = re.sub(r"[ \t\f\v]+", " ", repaired)
            repaired = re.sub(r" *\n *", "\n", repaired)
            repaired = re.sub(r"\n{3,}", "\n\n", repaired)
        else:
            repaired = re.sub(r"\s+", " ", repaired)
        repaired = re.sub(r"([，。！？；：、])[ \t]+", r"\1", repaired)
        repaired = re.sub(r"[ \t]+([，。！？；：、）】])", r"\1", repaired)
        repaired = re.sub(r"([（【])[ \t]+", r"\1", repaired)
        return repaired.strip()

    def _dedupe_formula_expansions(self, value: str) -> str:
        formulas = sorted(set(re.findall(r"(?:10|2)\^\d+", value)), key=len, reverse=True)
        updated = value
        for formula in formulas:
            base, exponent = formula.split("^", 1)
            exploded = " ".join(list(base))
            duplicate_sequence = f"{exploded} {exponent}".strip()
            updated = updated.replace(f"{duplicate_sequence} {formula} {duplicate_sequence}", formula)
            compact_sequence = f"{base}{exponent}"
            compact_pattern = re.compile(rf"{re.escape(compact_sequence)}{re.escape(formula)}{re.escape(compact_sequence)}")
            updated = compact_pattern.sub(formula, updated)
        return updated

    def _merge_option_lines(self, value: str) -> str:
        merged = OPTION_LABEL_LINE_RE.sub(lambda match: f"{match.group(1)} ", value)
        merged = re.sub(rf"(?m)^({OPTION_LABEL_PATTERN})\s+$", r"\1", merged)
        return merged

    def _split_inline_options(self, value: str) -> str:
        return INLINE_OPTION_RE.sub(lambda match: f"{match.group(1)}\n{match.group(2)} ", value)

    def _protect_blank_placeholders(self, value: str) -> str:
        def replace(match: re.Match[str]) -> str:
            return f"{match.group(1)}{{{{BLANK:{len(match.group(2))}}}}}{match.group(3)}"

        protected = BRACKETED_BLANK_RE.sub(replace, value)
        return INLINE_BLANK_RE.sub(lambda match: f"{{{{BLANK:{len(match.group(1))}}}}}", protected)

    def _restore_blank_placeholders(self, value: str) -> str:
        return BLANK_TOKEN_RE.sub(lambda match: " " * int(match.group(1)), value)

    def _repair_mojibake(self, value: str) -> str:
        if not value or not any(marker in value for marker in LIKELY_MOJIBAKE):
            return value

        best_text = value
        best_score = self._text_quality(value)
        for encoding in ("gb18030", "gbk"):
            try:
                repaired = value.encode(encoding).decode("utf-8")
            except (UnicodeEncodeError, UnicodeDecodeError):
                continue
            score = self._text_quality(repaired)
            if score > best_score:
                best_text = repaired
                best_score = score
        return best_text

    def _text_quality(self, value: str) -> int:
        chinese_chars = sum(1 for ch in value if "\u4e00" <= ch <= "\u9fff")
        expected_hits = sum(value.count(word) for word in EXPECTED_CHINESE)
        mojibake_hits = sum(value.count(word) for word in LIKELY_MOJIBAKE)
        return chinese_chars + expected_hits * 4 - mojibake_hits * 6

    def _extract_sequence_from_text(self, value: str) -> str:
        match = SEQUENCE_RE.search(value or "")
        return match.group(0) if match else ""

    def _is_bad_title_candidate(self, value: str) -> bool:
        if not value:
            return True
        normalized = self._normalize_text(value)
        if normalized in SECTION_LABELS:
            return True
        if TITLE_FILENAME_RE.fullmatch(normalized):
            return True
        if any(fragment in normalized for fragment in ("作者", "单位", "分数")):
            return True
        return False

    def _strip_site_suffix(self, value: str) -> str:
        parts = [part.strip() for part in re.split(r"[|｜]", value) if part.strip()]
        return parts[0] if parts else value

    def _title_from_url(self, value: str) -> str:
        path = Path(urlparse(value).path)
        candidate = path.name or (path.parent.name if path.parent else "")
        return candidate.upper() if candidate else ""

    def _slug(self, value: str) -> str:
        cleaned = re.sub(r"[^0-9A-Za-z\u4e00-\u9fff]+", "-", value).strip("-").lower()
        return cleaned or "item"

    def _suffix_from_content_type(self, content_type: str, fallback_url: str) -> str:
        mapping = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "image/svg+xml": ".svg",
        }
        for key, suffix in mapping.items():
            if content_type.startswith(key):
                return suffix
        parsed = Path(urlparse(fallback_url).path)
        return parsed.suffix or ".bin"

    def _build_problem_total_warnings(self, title: str, expected_total: int, parsed_total: int) -> list[str]:
        if expected_total <= 0 or expected_total == parsed_total:
            return []
        return [ScraperText.missing_problem_warning(title, expected_total, parsed_total)]

    def _expected_inline_problem_total(self, snapshot: PageSnapshot, inline_problems: list[Problem]) -> int:
        if not snapshot.html:
            return len(inline_problems)
        document = html.fromstring(snapshot.html)
        inline_ids = {
            (node.get("id") or "").strip()
            for node in document.xpath('//div[contains(@class,"pc-x")]')
            if (node.get("id") or "").strip()
        }
        if inline_ids:
            return len(inline_ids)
        return len(inline_problems)

    def _emit_progress(
        self,
        progress_callback: ProgressCallback | None,
        *,
        percent: float,
        message: str,
        **extra: Any,
    ) -> None:
        if progress_callback is None:
            return
        payload = {"percent": max(0.0, min(100.0, percent)), "message": message, **extra}
        progress_callback(payload)

    def _emit_export_progress(
        self,
        progress_callback: ProgressCallback | None,
        *,
        problem_set_index: int,
        problem_set_total: int,
        problem_set_title: str,
        message: str,
        problem_index: int = 0,
        problem_total: int = 0,
        problem_title: str = "",
        expected_problem_total: int = 0,
        parsed_problem_total: int = 0,
        warnings: list[str] | None = None,
        finished_set: bool = False,
    ) -> None:
        percent = self._calculate_export_percent(
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
            problem_index=problem_index,
            problem_total=problem_total,
            finished_set=finished_set,
        )
        self._emit_progress(
            progress_callback,
            percent=percent,
            message=message,
            problem_set_index=problem_set_index,
            problem_set_total=problem_set_total,
            problem_set_title=problem_set_title,
            problem_index=problem_index,
            problem_total=problem_total,
            problem_title=problem_title,
            expected_problem_total=expected_problem_total,
            parsed_problem_total=parsed_problem_total,
            warnings=warnings or [],
        )

    def _calculate_export_percent(
        self,
        *,
        problem_set_index: int,
        problem_set_total: int,
        problem_index: int,
        problem_total: int,
        finished_set: bool,
    ) -> float:
        if problem_set_total <= 0:
            return 0.0
        completed_sets = max(problem_set_index - 1, 0)
        fraction = 0.0
        if problem_total > 0:
            fraction = min(problem_index, problem_total) / problem_total
        elif finished_set:
            fraction = 1.0
        return ((completed_sets + fraction) / problem_set_total) * 100
