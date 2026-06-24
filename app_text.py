from __future__ import annotations

from app_meta import APP_DISPLAY_NAME, APP_VERSION


class ParserText:
    SECTION_LABELS = {
        "题目描述": "description",
        "Description": "description",
        "输入格式": "input",
        "输入说明": "input",
        "Input Specification": "input",
        "输出格式": "output",
        "输出说明": "output",
        "Output Specification": "output",
        "样例输入": "sample_input",
        "Sample Input": "sample_input",
        "样例输出": "sample_output",
        "Sample Output": "sample_output",
        "提示": "hint",
        "备注": "hint",
        "Note": "hint",
        "Notes": "hint",
    }
    PUBLISHED_ANSWER_MARKERS = (
        "评测结果",
        "参考答案",
        "标准答案",
        "题目解析",
        "答案解析",
    )


class DocxText:
    DEFAULT_SET_NAME = "PTA题目集"
    DEFAULT_FILENAME_STEM = "PTA"
    WARNING_PREFIX = "抓取提醒："
    DESCRIPTION_HEADING = "题目描述"
    SAMPLE_HEADING = "样例"
    SAMPLE_INPUT_PREFIX = "样例输入"
    SAMPLE_OUTPUT_PREFIX = "样例输出"
    IMAGE_HEADING = "题面图片"

    @staticmethod
    def sample_input(index: int) -> str:
        return f"{DocxText.SAMPLE_INPUT_PREFIX} {index}"

    @staticmethod
    def sample_output(index: int) -> str:
        return f"{DocxText.SAMPLE_OUTPUT_PREFIX} {index}"


class ScraperText:
    DEFAULT_SET_NAME = "PTA题目集"
    UNTITLED_PROBLEM = "未命名题目"
    WARNING_CATEGORY_CONTENT = "content_mojibake"
    WARNING_CATEGORY_PAGE = "page_unavailable"
    WARNING_CATEGORY_PROBLEM = "problem_missing"
    WARNING_CATEGORY_IMAGE = "image_asset"
    WARNING_CODE_CONTENT_REPAIRED = "content_mojibake_detected"
    WARNING_CODE_PAGE_UNAVAILABLE = "page_unavailable"
    WARNING_CODE_PROBLEM_FETCH_FAILED = "problem_fetch_failed"
    WARNING_CODE_MISSING_PROBLEM_TOTAL = "missing_problem_total"
    WARNING_CODE_IMAGE_DOWNLOAD_FAILED = "image_download_failed"
    WARNING_CODE_IMAGE_WRITE_FAILED = "image_write_failed"

    TARGET_ACCOUNT_REQUIRED = "请先填写目标 PTA 账号。"
    LOGIN_REQUIRED = "未检测到有效登录状态，请先登录 PTA。"
    ACCOUNT_UNKNOWN = "已登录，但无法识别当前账号，请切换账号并重新登录。"
    PROBLEM_SET_LIST_LOADING = "正在加载题目集列表..."
    EXPORT_GENERATING = "题目抓取完成，正在生成 Word 文档..."

    @staticmethod
    def account_mismatch(current_display: str, target_account: str) -> str:
        return (
            f"当前登录账号“{current_display}”与目标账号“{target_account.strip()}”不一致，"
            "请切换账号后重试。"
        )

    @staticmethod
    def problem_sets_loaded(count: int) -> str:
        return f"题目集加载完成，共 {count} 个。"

    @staticmethod
    def loading_problem_types(title: str) -> str:
        return f"正在加载题型：{title}"

    @staticmethod
    def problem_types_loaded(title: str, count: int) -> str:
        return f"题型加载完成：{title}（{count} 个）"

    @staticmethod
    def problem_types_not_found(title: str) -> str:
        return (
            f"未发现可导出的题型：{title}。"
            "如果该页面本应显示题型列表，可能是 PTA 页面结构已变化，请更新样本后检查解析规则。"
        )

    @staticmethod
    def problem_set_list_empty() -> str:
        return (
            "没有加载到任何题目集。请先确认 PTA 已登录、入口页面可以正常打开；"
            "如果页面中本应显示题目集，可能是 PTA 页面结构已变化，请更新样本后检查解析规则。"
        )

    @staticmethod
    def preparing_export(total_sets: int) -> str:
        return f"准备抓取 {total_sets} 个题目集..."

    @staticmethod
    def exporting_problem_set(index: int, total: int, source_label: str) -> str:
        return f"正在抓取导出项 {index}/{total}：{source_label}"

    @staticmethod
    def exported_problem_set(
        index: int,
        total: int,
        source_label: str,
        parsed_problem_total: int,
        expected_problem_total: int,
    ) -> str:
        effective_total = expected_problem_total or parsed_problem_total
        return (
            f"导出项 {index}/{total} 抓取完成：{source_label}"
            f"（{parsed_problem_total}/{effective_total}）"
        )

    @staticmethod
    def export_completed(output_path: str) -> str:
        return f"导出完成：{output_path}"

    @staticmethod
    def exporting_problem(
        problem_set_index: int,
        problem_set_total: int,
        source_label: str,
        problem_index: int,
        expected_total: int,
        problem_title: str,
    ) -> str:
        return (
            f"导出项 {problem_set_index}/{problem_set_total}：{source_label} | "
            f"题目 {problem_index}/{expected_total}：{problem_title}"
        )

    @staticmethod
    def problem_fetch_failed(title: str, error: Exception) -> str:
        return f"题目《{title}》抓取失败：{error}"

    @staticmethod
    def missing_problem_warning(title: str, expected_total: int, parsed_total: int) -> str:
        return f"题目集《{title}》可能漏题：预期 {expected_total} 题，实际抓到 {parsed_total} 题。"

    @staticmethod
    def merged_export_name(titles: list[str]) -> str:
        if not titles:
            return ScraperText.DEFAULT_SET_NAME
        if len(titles) == 1:
            return titles[0]
        merged_name = "、".join(titles)
        return merged_name if len(merged_name) <= 120 else f"{titles[0]}等{len(titles)}个题目集"

    @staticmethod
    def session_expired_user_missing() -> str:
        return "登录状态失效，PTA 返回了“用户不存在”，请重新登录。"

    @staticmethod
    def snapshot_error_page() -> str:
        return "抓取页面返回错误页，请重新登录后再试。"

    @staticmethod
    def unsupported_export_mode(export_mode: str) -> str:
        return f"不支持的导出模式：{export_mode}"

    @staticmethod
    def content_mojibake_warning(title: str) -> str:
        return f"题目集《{title}》页面疑似存在乱码，程序已尝试自动修复，请导出后抽查内容。"

    @staticmethod
    def page_unavailable_warning(title: str, error: Exception) -> str:
        return f"题目《{title}》页面暂不可用：{error}"

    @staticmethod
    def image_download_failed(title: str, error: Exception) -> str:
        return f"题目《{title}》的图片下载失败：{error}"

    @staticmethod
    def image_write_failed(title: str, error: Exception) -> str:
        return f"题目《{title}》的图片写入失败：{error}"


class SessionText:
    BROWSER_SERVICE_PIPES_UNAVAILABLE = "浏览器桥服务的通信管道不可用。"
    UNKNOWN_BROWSER_SERVICE_ERROR = "浏览器桥服务返回了未知错误。"
    BROWSER_SERVICE_EXITED_UNEXPECTEDLY = "浏览器桥服务异常退出。"
    NODE_RUNTIME_MISSING = "未找到 Playwright 浏览器桥所需的 node.exe。"
    BROWSER_SERVICE_SCRIPT_MISSING_PREFIX = "缺少浏览器桥脚本："
    BROWSER_MISSING = "未检测到 Microsoft Edge 或 Google Chrome。"

    @staticmethod
    def browser_service_script_missing(script_path: str) -> str:
        return f"{SessionText.BROWSER_SERVICE_SCRIPT_MISSING_PREFIX}{script_path}"

    @staticmethod
    def decode_response_failed(line: str) -> str:
        return f"浏览器桥服务响应解析失败：{line}"


class UiText:
    APP_TITLE = APP_DISPLAY_NAME
    VERSION_LABEL = f"当前版本：v{APP_VERSION}"
    TYPE_PLACEHOLDER = "展开后加载题型..."
    READY = "准备就绪"
    NOT_LOGGED_IN = "未登录"
    UNKNOWN_ACCOUNT = "未识别"
    WAITING_FOR_LOGIN = "等待登录"
    NO_WARNING = "当前没有完整性警告"
    NO_EXPORT_YET = "尚未开始导出"
    NO_PROGRESS_TASK = "当前没有进行中的抓取任务"
    EXPORT_IN_PROGRESS = "任务进行中，完成后会在这里显示导出摘要"
    TASK_INCOMPLETE = "本次任务未完成"

    GROUP_BASIC = "基础配置"
    GROUP_INFO = "登录状态 / 抓取来源"
    GROUP_PROGRESS = "抓取进度"
    GROUP_AVAILABLE = "题目集 / 题型（左侧展开并加入导出）"
    GROUP_QUEUE = "已选导出项（导出顺序）"
    GROUP_LOG = "运行日志"

    LABEL_START_URL = "入口 URL"
    LABEL_OUTPUT_DIR = "导出目录"
    LABEL_EMBED_IMAGES = "下载并嵌入题面图片"
    LABEL_EXPORT_MODE = "导出方式"
    LABEL_LOGIN_STATE = "登录状态："
    LABEL_CURRENT_ACCOUNT = "当前账号："
    LABEL_SOURCE = "抓取来源："

    BUTTON_CHOOSE_DIR = "选择目录"
    BUTTON_LOGIN = "1. 打开登录页"
    BUTTON_SWITCH_ACCOUNT = "2. 重新登录"
    BUTTON_CONFIRM_ACCOUNT = "3. 确认账号"
    BUTTON_LOAD_SETS = "4. 加载题目集"
    BUTTON_EXPORT = "5. 导出 Word"
    BUTTON_ADD_TO_QUEUE = "加入导出 ->"
    BUTTON_REMOVE_FROM_QUEUE = "<- 移出导出"
    BUTTON_MOVE_UP = "上移"
    BUTTON_MOVE_DOWN = "下移"

    EXPORT_MODE_MERGED = "合并成一个 Word"
    EXPORT_MODE_SEPARATE = "每个导出项单独一个 Word"

    DIALOG_EXPORT_FILE = "选择合并导出的 Word 文件"
    DIALOG_CONFIRM_EXPORT = "确认导出"
    DIALOG_EXPORT_COMPLETE = "导出完成"
    DIALOG_EXPORT_COMPLETE_WITH_WARNING = "导出完成，但有警告"
    DIALOG_EXPORT_FAILED = "操作失败"
    DIALOG_OPEN_OUTPUT_DIR = "打开输出目录"
    DIALOG_WAIT = "请稍候"
    DIALOG_NEED_EXPORT_ITEM = "请选择导出项"
    DIALOG_NO_SELECTION = "未选择导出项"
    DIALOG_PARTIAL_ITEMS_SKIPPED = "部分导出项未加入"
    DIALOG_NEED_SINGLE_ITEM = "请选择单个导出项"
    WORD_FILETYPE_LABEL = "Word 文档"

    @staticmethod
    def queue_summary(count: int) -> str:
        return f"已选 {count} 个导出项"

    @staticmethod
    def source_label(start_url: str) -> str:
        return f"入口：{start_url}" if start_url else "固定入口：所有题目集"

    @staticmethod
    def merged_export_name(titles: list[str]) -> str:
        if not titles:
            return DocxText.DEFAULT_SET_NAME
        if len(titles) == 1:
            return titles[0]
        merged_name = "、".join(titles)
        return merged_name if len(merged_name) <= 120 else f"{titles[0]}等{len(titles)}个导出项"

    @staticmethod
    def merged_export_hint() -> str:
        return "合并导出时会弹出“另存为”窗口，这里的目录不会直接使用。"

    @staticmethod
    def separate_export_hint() -> str:
        return "单独导出时会把多个 Word 文档生成到这个目录。"

    @staticmethod
    def login_page_opened() -> str:
        return "登录页已打开，请登录后点击“确认账号”"

    @staticmethod
    def login_page_opened_log() -> str:
        return "登录页已打开，请登录后手动确认账号。"

    @staticmethod
    def account_cleared() -> str:
        return "已清除登录态，请在浏览器中登录要抓取的账号..."

    @staticmethod
    def account_cleared_log() -> str:
        return "已清除登录态，请重新登录。"

    @staticmethod
    def account_confirmed() -> str:
        return "账号确认完成，可以开始加载题目集"

    @staticmethod
    def account_confirmed_log() -> str:
        return "账号确认完成，浏览器已关闭。"

    @staticmethod
    def problem_sets_loaded(count: int) -> str:
        return f"题目集加载完成，共 {count} 个"

    @staticmethod
    def problem_sets_loaded_log(count: int) -> str:
        return f"已加载 {count} 个题目集。"

    @staticmethod
    def no_problem_sets_loaded() -> str:
        return "没有加载到任何题目集。"

    @staticmethod
    def problem_types_loaded(title: str, count: int) -> str:
        return f"已加载题型：{title}（{count} 个）"

    @staticmethod
    def no_exportable_types(title: str) -> str:
        return f"题目集未发现可导出的题型：{title}"

    @staticmethod
    def problem_types_loading(title: str) -> str:
        return f"正在加载题型：{title}"

    @staticmethod
    def export_summary(
        exported_count: int,
        parsed_total: int,
        expected_total: int,
        warning_count: int,
    ) -> str:
        effective_total = expected_total or parsed_total
        return (
            f"导出摘要：{exported_count} 个导出项，"
            f"{parsed_total}/{effective_total} 题成功，"
            f"{warning_count} 条警告"
        )

    @staticmethod
    def export_result_summary_lines(
        exported_count: int,
        parsed_total: int,
        expected_total: int,
        failed_total: int,
        warning_count: int,
        image_warning_count: int,
        missing_problem_warning_count: int,
        page_warning_count: int,
        content_warning_count: int,
    ) -> list[str]:
        effective_total = expected_total or parsed_total
        lines = [
            f"导出项：{exported_count}",
            f"题目：{parsed_total}/{effective_total}",
            f"缺失：{failed_total}",
            f"警告：{warning_count}",
        ]
        if missing_problem_warning_count:
            lines.append(f"漏题告警：{missing_problem_warning_count}")
        if page_warning_count:
            lines.append(f"页面告警：{page_warning_count}")
        if image_warning_count:
            lines.append(f"图片警告：{image_warning_count}")
        if content_warning_count:
            lines.append(f"乱码修复提示：{content_warning_count}")
        return lines

    @staticmethod
    def separate_export_completed(file_count: int) -> str:
        return f"导出完成，已生成 {file_count} 个 Word 文档。"

    @staticmethod
    def more_files(remaining_count: int) -> str:
        return f"... 还有 {remaining_count} 个文件"

    @staticmethod
    def more_warnings(remaining_count: int) -> str:
        return f"... 还有 {remaining_count} 条警告"

    @staticmethod
    def more_tips(remaining_count: int) -> str:
        return f"... 还有 {remaining_count} 条提示"

    @staticmethod
    def export_document_list(paths: list[str]) -> str:
        return "Word 文档已生成：\n" + "\n".join(paths)

    @staticmethod
    def export_completed(output_path: str) -> str:
        return f"导出完成：{output_path}"

    @staticmethod
    def export_document_single(path: str) -> str:
        return f"Word 文档已生成：\n{path}"

    @staticmethod
    def warning_banner(warnings: list[str]) -> str:
        return "当前有完整性警告：" + "；".join(warnings[:2])

    @staticmethod
    def warning_banner_inline(warnings: list[str]) -> str:
        return "完整性警告：" + "；".join(warnings[:2])

    @staticmethod
    def export_warning_details(dialog_message: str, warning_text: str) -> str:
        return f"{dialog_message}\n\n以下导出项可能没有抓全：\n{warning_text}"

    @staticmethod
    def export_result_summary_text(lines: list[str]) -> str:
        return "导出摘要：\n" + "\n".join(lines)

    @staticmethod
    def open_output_dir_prompt(target_dir: str) -> str:
        return f"是否打开输出目录？\n{target_dir}"

    @staticmethod
    def open_output_dir_failed(error: OSError) -> str:
        return f"打开输出目录失败：{error}"

    @staticmethod
    def task_failed(message: str) -> str:
        return f"任务失败：{message}"

    @staticmethod
    def wait_message() -> str:
        return "当前任务尚未完成，请等待。"

    @staticmethod
    def need_export_items() -> str:
        return "请先在左侧树中选择至少一个题目集或题型。"

    @staticmethod
    def need_add_items() -> str:
        return "请先在左侧树中选中要加入导出的题目集或题型。"

    @staticmethod
    def need_remove_items() -> str:
        return "请先在右侧列表中选中要移除的导出项。"

    @staticmethod
    def need_single_item() -> str:
        return "调整顺序时，请先在右侧列表中只选中一个导出项。"

    @staticmethod
    def added_to_queue(count: int) -> str:
        return f"已加入 {count} 个导出项到队列。"

    @staticmethod
    def removed_from_queue(count: int) -> str:
        return f"已从导出队列移除 {count} 个导出项。"

    @staticmethod
    def reordered_queue() -> str:
        return "已调整导出顺序。"

    @staticmethod
    def duplicate_queue_item(label: str) -> str:
        return f"《{label}》已在导出队列中。"

    @staticmethod
    def queue_has_problem_type(problem_set_title: str) -> str:
        return f"题目集《{problem_set_title}》已有题型子项在队列中，不能再加入整套导出。"

    @staticmethod
    def queue_has_problem_set(problem_set_title: str, type_title: str) -> str:
        return f"题目集《{problem_set_title}》整套已在队列中，不能再加入题型《{type_title}》。"

    @staticmethod
    def export_request_summary(item_count: int, mode_label: str, image_label: str, output_dir: str) -> str:
        return (
            f"将导出 {item_count} 个项目。\n"
            f"导出方式：{mode_label}\n"
            f"图片处理：{image_label}\n"
            f"输出位置：{output_dir}"
        )

    @staticmethod
    def export_mode_label(export_mode: str) -> str:
        return UiText.EXPORT_MODE_MERGED if export_mode == "merged" else "每个导出项单独生成 Word"

    @staticmethod
    def image_mode_label(embed_images: bool) -> str:
        return "下载并嵌入图片" if embed_images else "不下载图片"

    @staticmethod
    def ready_to_load_message() -> str:
        return "已登录，可以加载题目集"

    @staticmethod
    def logged_in_but_unknown() -> str:
        return "已登录，但无法识别账号"

    @staticmethod
    def login_confirmation_required() -> str:
        return "请先登录并确认账号。"

    @staticmethod
    def login_open_status() -> str:
        return "正在打开登录页，请在浏览器中完成 PTA 登录..."

    @staticmethod
    def switch_account_status() -> str:
        return "正在清除当前登录态并打开登录页..."

    @staticmethod
    def confirm_account_status() -> str:
        return "正在确认当前登录账号..."

    @staticmethod
    def load_problem_sets_status() -> str:
        return "正在校验登录状态并加载题目集，请稍候..."

    @staticmethod
    def export_status() -> str:
        return "正在校验登录状态并抓取题目生成 Word，请稍候..."

    @staticmethod
    def node_missing() -> str:
        return "未找到浏览器桥运行时 node.exe。请使用打包版本，或按 README 配置运行时后再试。"

    @staticmethod
    def browser_missing() -> str:
        return "未检测到 Microsoft Edge 或 Google Chrome。请先安装浏览器后再试。"

    @staticmethod
    def retry_after_login(message: str) -> str:
        return f"{message}\n\n请重新登录 PTA 后重试。"

    @staticmethod
    def retry_after_structure_change(message: str) -> str:
        return (
            f"{message}\n\n"
            "请先确认当前页面已经正常打开；如果页面内容存在但程序仍无法识别，"
            "可能是 PTA 页面结构变化导致抓取失败，请更新样本后检查解析规则。"
        )
