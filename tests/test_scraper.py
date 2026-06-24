from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lxml import html

from app_text import DocxText
from config import AppConfig
from models import ExportSourceSummary, ProblemSetSummary
from pta.scraper import PTAScraper
from pta.session import PageSnapshot, SessionError
from ui.app import PTAExporterApp


FIXTURES = Path(__file__).resolve().parent / "fixtures"
REAL_HTML_SAMPLES = Path(__file__).resolve().parent.parent / "private" / "raw_pta_html"


def read_real_html_sample(filename: str) -> str:
    path = REAL_HTML_SAMPLES / filename
    if not path.exists():
        raise unittest.SkipTest(
            "Local PTA raw HTML samples are not available. "
            "Put 1.html-4.html under private/raw_pta_html/ to enable these tests."
        )
    return path.read_text(encoding="utf-8")


class FakeSession:
    def __init__(
        self,
        snapshots: dict[str, PageSnapshot],
        *,
        current_user: dict[str, object] | None = None,
    ) -> None:
        self.snapshots = snapshots
        self.current_user = current_user or {
            "authenticated": True,
            "accountId": "demo-user",
            "displayName": "Demo User",
        }
        self.switch_calls: list[str] = []

    def snapshot(self, url: str, options=None) -> PageSnapshot:
        if url not in self.snapshots:
            raise KeyError(url)
        return self.snapshots[url]

    def download_bytes(self, url: str, *, base_url: str = "", referer: str = "") -> tuple[bytes, str]:
        raise AssertionError("download_bytes should not be called in this test")

    def get_current_user(self) -> dict[str, object]:
        return dict(self.current_user)

    def switch_account(self, start_url: str) -> dict[str, object]:
        self.switch_calls.append(start_url)
        self.current_user = {
            "authenticated": False,
            "accountId": "",
            "displayName": "",
            "message": "已清除 PTA 登录态，请重新登录。",
        }
        return dict(self.current_user)

    def close(self) -> None:
        return None


class CapturingWriter:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def write_document(self, title: str, assignments, output_dir: Path, *, filename_stem: str) -> Path:
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"{filename_stem}.docx"
        path.write_bytes(b"docx")
        self.calls.append(
            {
                "title": title,
                "assignments": assignments,
                "output_dir": output_dir,
                "filename_stem": filename_stem,
                "path": path,
            }
        )
        return path


class ScraperParsingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        base = Path(self.temp_dir.name)
        config = AppConfig(
            start_url="https://pintia.cn/problem-sets/all",
            output_dir=base / "exports",
            session_profile_dir=base / "profile",
            temp_dir=base / "tmp",
        )
        config.output_dir.mkdir(parents=True, exist_ok=True)
        config.session_profile_dir.mkdir(parents=True, exist_ok=True)
        config.temp_dir.mkdir(parents=True, exist_ok=True)
        self.scraper = PTAScraper(config)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_extracts_problem_sets_from_precise_dom_container(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/all",
            title="PTA | 程序设计类实验辅助教学平台",
            html=(FIXTURES / "problem_sets_list.html").read_text(encoding="utf-8"),
            links=[],
        )
        items = self.scraper._extract_problem_sets_from_dom_snapshot(snapshot)
        self.assertEqual(2, len(items))
        self.assertEqual("计算机网络_单选题库", items[0].title)
        self.assertEqual("2066431007420686336", items[0].id)
        self.assertEqual("2026-07-01 17:58", items[0].ends_at)

    def test_rejects_error_snapshot(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/all",
            title="PTA | 程序设计类实验辅助教学平台",
            html=(FIXTURES / "problem_sets_error.html").read_text(encoding="utf-8"),
            links=[],
            body_text="错误信息 用户不存在 重新加载 登录",
        )
        with self.assertRaises(SessionError):
            self.scraper._assert_snapshot_usable(snapshot)

    def test_parses_problem_content_and_samples(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/homework-1/problems/l1-001",
            title="L1-001 Hello PTA",
            html=(FIXTURES / "problem.html").read_text(encoding="utf-8"),
            links=[],
        )
        problem = self.scraper._parse_problem_snapshot(snapshot)
        self.assertEqual("L1-001 Hello PTA", problem.title)
        self.assertEqual("25", problem.score)
        self.assertTrue(any(section.title == DocxText.DESCRIPTION_HEADING for section in problem.sections))
        self.assertEqual(1, len(problem.samples))
        self.assertEqual("Hello PTA", problem.samples[0].output_text)
        self.assertEqual("https://pintia.cn/assets/hello.png", problem.images[0].url)

    def test_parses_inline_multi_judge_and_blank_questions(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/exam/problems/type",
            title="题目列表",
            html=(FIXTURES / "problem_type_question_types.html").read_text(encoding="utf-8"),
            links=[],
        )

        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)

        self.assertEqual(3, len(problems))
        self.assertEqual("多选题：网络协议", problems[0].title)
        self.assertEqual(
            "下列属于应用层协议的是（多选）。\nA. HTTP\nB. SMTP\nC. UDP\nD. DNS",
            problems[0].sections[0].content,
        )
        self.assertEqual("判断题：TCP 基础", problems[1].title)
        self.assertEqual(
            "TCP 是面向连接的传输层协议。\nT. 正确\nF. 错误",
            problems[1].sections[0].content,
        )
        self.assertEqual("填空题：标准输出", problems[2].title)
        self.assertEqual(
            "请补全 C 语言中的标准输出语句：printf(    );\n函数名是 ________。",
            problems[2].sections[0].content,
        )

    def test_parses_standalone_multi_select_question(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/problems/multi",
            title="5-1 多选题：网络协议",
            html=(FIXTURES / "problem_multi_select.html").read_text(encoding="utf-8"),
            links=[],
        )

        problem = self.scraper._parse_problem_snapshot(snapshot)

        self.assertEqual("5-1 多选题：网络协议", problem.title)
        self.assertEqual("4", problem.score)
        self.assertEqual(
            "下列属于应用层协议的是（多选）。\nA. HTTP\nB. SMTP\nC. UDP\nD. DNS",
            problem.sections[0].content,
        )
        self.assertEqual("ABD", problem.samples[0].output_text)

    def test_parses_standalone_true_false_question_and_strips_answer_blocks(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/problems/judge",
            title="5-2 判断题：TCP 基础",
            html=(FIXTURES / "problem_true_false.html").read_text(encoding="utf-8"),
            links=[],
        )

        problem = self.scraper._parse_problem_snapshot(snapshot)

        self.assertEqual(
            "TCP 是面向连接的传输层协议。\nT. 正确\nF. 错误",
            problem.sections[0].content,
        )
        self.assertEqual("请根据 TCP 的特性判断。", problem.sections[1].content)
        self.assertNotIn("参考答案", "\n".join(section.content for section in problem.sections))
        self.assertNotIn("题目解析", "\n".join(section.content for section in problem.sections))

    def test_parses_standalone_fill_blank_question_preserving_blanks(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/problems/blank",
            title="5-3 填空题：标准输出",
            html=(FIXTURES / "problem_fill_blank.html").read_text(encoding="utf-8"),
            links=[],
        )

        problem = self.scraper._parse_problem_snapshot(snapshot)

        self.assertEqual(
            "请补全 C 语言中的标准输出语句：printf(    );\n函数名是 ________。",
            problem.sections[0].content,
        )

    def test_parses_real_judge_page_sample(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/local-sample/exam/problems/type/1",
            title="Local sample judge page",
            html=read_real_html_sample("1.html"),
            links=[],
        )

        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)

        self.assertGreater(len(problems), 10)
        self.assertEqual("1-1", problems[0].sequence_label)
        self.assertTrue(problems[0].title.startswith("1-1"))
        self.assertEqual("T\nF", problems[0].sections[0].content)

    def test_parses_real_single_choice_page_sample(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/local-sample/exam/problems/type/2",
            title="Local sample single choice page",
            html=read_real_html_sample("2.html"),
            links=[],
        )

        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)

        self.assertGreater(len(problems), 10)
        self.assertTrue(problems[0].sequence_label)
        self.assertIn("A.", problems[0].sections[0].content)
        self.assertIn("B.", problems[0].sections[0].content)

    def test_parses_real_multiple_choice_page_sample(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/local-sample/exam/problems/type/3",
            title="Local sample multiple choice page",
            html=read_real_html_sample("3.html"),
            links=[],
        )

        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)

        self.assertGreater(len(problems), 5)
        self.assertTrue(problems[0].sequence_label)
        self.assertIn("A.", problems[0].sections[0].content)
        self.assertIn("B.", problems[0].sections[0].content)

    def test_parses_real_fill_blank_page_sample(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/local-sample/exam/problems/type/4",
            title="Local sample fill blank page",
            html=read_real_html_sample("4.html"),
            links=[],
        )

        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)

        self.assertGreater(len(problems), 5)
        self.assertEqual("4-1", problems[0].title)
        self.assertIn("____", problems[0].sections[0].content)

    def test_inline_fill_blank_without_extra_lines_keeps_description(self) -> None:
        node = html.fromstring(
            """
            <div class="pc-x pt-2 pl-4 scroll-mt-0" id="fill-1">
              <div class="flex flex-wrap gap-2">
                <button><div class="text-xs">4-1</div></button>
              </div>
              <div class="mt-4">
                <p>无线传输媒体包括 <span data-blank-index="0"><span>1 分</span></span> 和 <span data-blank-index="1"><span>1 分</span></span>。</p>
              </div>
            </div>
            """
        )

        problem = self.scraper._parse_inline_problem_node(node, "https://pintia.cn/problem-sets/demo/exam/problems/type", 1)

        self.assertEqual("4-1", problem.title)
        self.assertEqual("无线传输媒体包括 ____ 和 ____。", problem.sections[0].content)

    def test_load_problem_set_types_from_real_navigation_sample(self) -> None:
        problem_set = ProblemSetSummary(
            id="local-sample",
            title="Local Sample Set",
            url="https://pintia.cn/problem-sets/local-sample/overview",
        )
        type_page_url = "https://pintia.cn/problem-sets/local-sample/exam/problems/type/1"
        self.scraper.session = FakeSession(
            {
                type_page_url: PageSnapshot(
                    url=type_page_url,
                    title="Local sample judge page",
                    html=read_real_html_sample("1.html"),
                    links=[],
                )
            }
        )

        items = self.scraper.load_problem_set_types(problem_set, target_account="demo-user")

        self.assertEqual(4, len(items))
        self.assertTrue(all(item.type_label for item in items))
        self.assertTrue(all(item.problem_count > 0 for item in items))
        self.assertTrue(items[0].url.endswith("/exam/problems/type/1"))
        self.assertEqual("problem_type", items[0].source_kind)
        self.assertEqual(problem_set.id, items[0].parent_problem_set_id)

    def test_export_problem_type_source_uses_type_specific_title_and_filename(self) -> None:
        type_source = ExportSourceSummary(
            id="local-sample:type:1",
            title="Judge",
            url="https://pintia.cn/problem-sets/local-sample/exam/problems/type/1",
            source_kind="problem_type",
            parent_problem_set_id="local-sample",
            parent_title="Local Sample Set",
            type_label="Judge",
            problem_count=1,
        )
        self.scraper.session = FakeSession(
            {
                type_source.url: PageSnapshot(
                    url=type_source.url,
                    title="Local sample judge page",
                    html=read_real_html_sample("1.html"),
                    links=[],
                )
            }
        )
        capturing_writer = CapturingWriter()
        self.scraper.writer = capturing_writer

        result = self.scraper.export_problem_sets(
            [type_source],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=False,
            export_mode="separate",
            target_account="demo-user",
        )

        self.assertEqual("separate", result.export_mode)
        self.assertEqual("Local Sample Set_Judge.docx", Path(result.output_path).name)
        self.assertEqual(1, len(capturing_writer.calls))
        assignment = capturing_writer.calls[0]["assignments"][0]
        self.assertEqual("Local Sample Set_Judge", assignment.title)
        self.assertGreater(assignment.parsed_problem_total, 0)
        self.assertEqual("1-1", assignment.problems[0].sequence_label)

    def test_strips_score_author_and_school_from_inline_problem(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/2068321589395034112/exam/problems/type",
            title="题目列表",
            html=(FIXTURES / "problem_type.html").read_text(encoding="utf-8"),
            links=[],
        )
        problems = self.scraper._extract_inline_problems_from_snapshot(snapshot)
        self.assertEqual(1, len(problems))
        self.assertEqual("4-1", problems[0].title)
        self.assertEqual("4-1", problems[0].sequence_label)
        description = problems[0].sections[0].content
        self.assertNotIn("分数", description)
        self.assertNotIn("作者", description)
        self.assertNotIn("单位", description)

    def test_prefers_title_hint_when_page_heading_is_image_filename(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/problems/p1",
            title="image.png",
            html="""
            <html><body><main>
              <h1>image.png</h1>
              <h2>题目描述</h2>
              <p>请输出 1。</p>
            </main></body></html>
            """,
            links=[],
        )
        problem = self.scraper._parse_problem_snapshot(snapshot, title_hint="2-31", title_source="list-link")
        self.assertEqual("2-31", problem.title)
        self.assertEqual("list-link", problem.title_source)

    def test_strips_published_answer_and_analysis_blocks(self) -> None:
        cleaned = self.scraper._clean_section_content(
            "6-1 在客户/服务器模型中，客户指的是（）。\n"
            "A. 请求方\n"
            "B. 响应方\n"
            "评测结果\n"
            "答案正确\n"
            "参考答案\n"
            "A\n"
            "题目解析\n"
            "略"
        )
        self.assertEqual("6-1 在客户/服务器模型中，客户指的是（）。\nA. 请求方\nB. 响应方", cleaned)

    def test_inline_problem_uses_mt4_content_root_only(self) -> None:
        node = html.fromstring(
            """
            <div class="pc-x pt-2 pl-4 scroll-mt-0" id="2066179739422924804">
              <div class="flex flex-wrap gap-2">
                <button><div class="text-xs">2-1</div></button>
              </div>
              <div class="mt-4">
                <h2>题目描述</h2>
                <p>6-1 在客户/服务器模型中，客户指的是（）。</p>
                <p>A. 请求方</p>
                <p>B. 响应方</p>
              </div>
              <div>评测结果</div>
              <div>参考答案</div>
              <div>题目解析</div>
            </div>
            """
        )
        problem = self.scraper._parse_inline_problem_node(node, "https://pintia.cn/problem-sets/demo/exam/problems/type", 1)
        self.assertEqual("2-1 6-1 在客户/服务器模型中，客户指的是（）。", problem.title)
        self.assertEqual("A. 请求方\nB. 响应方", problem.sections[0].content)

    def test_inline_problem_promotes_plain_stem_to_title(self) -> None:
        node = html.fromstring(
            """
            <div class="pc-x pt-2 pl-4 scroll-mt-0" id="2066179739422924805">
              <div class="flex flex-wrap gap-2">
                <button><div class="text-xs">2-76</div></button>
              </div>
              <div class="mt-4">
                <h2>题目描述</h2>
                <p>10.UDP数据报中长度字段记录包括首部和数据部分的长度，以8位为长度计算单位。在TCP/IP网络中，为各种公共服务保留的端口号范围是</p>
                <p>A. 1～255</p>
                <p>B. 1～1023</p>
              </div>
            </div>
            """
        )
        problem = self.scraper._parse_inline_problem_node(node, "https://pintia.cn/problem-sets/demo/exam/problems/type", 2)
        self.assertEqual(
            "2-76 10.UDP数据报中长度字段记录包括首部和数据部分的长度，以8位为长度计算单位。在TCP/IP网络中，为各种公共服务保留的端口号范围是",
            problem.title,
        )
        self.assertEqual("A. 1～255\nB. 1～1023", problem.sections[0].content)

    def test_normalizes_duplicate_formula_text(self) -> None:
        cleaned = self.scraper._clean_section_content(
            "A. 1 0 3 10^3 1 0 3 гм 1 0 6 10^{6} 1 0 6"
        )
        self.assertEqual("A. 10^3，10^6", cleaned)

    def test_normalizes_compact_formula_text(self) -> None:
        cleaned = self.scraper._clean_section_content(
            "A. 10310^3103，10610^6106，10910^9109，101210^121012"
        )
        self.assertEqual("A. 10^3，10^6，10^9，10^12", cleaned)

    def test_merges_option_label_and_content_into_same_line(self) -> None:
        cleaned = self.scraper._clean_section_content("A.\n选项内容")
        self.assertEqual("A. 选项内容", cleaned)

    def test_splits_inline_option_after_stem(self) -> None:
        cleaned = self.scraper._clean_section_content(
            "1-1 因特网的前身是 1969 年创建的第一个分组交换网（）。A.\ninternet\nB. Internet\nC. NSFNET\nD. ARPANET"
        )
        self.assertEqual(
            "1-1 因特网的前身是 1969 年创建的第一个分组交换网（）。\nA. internet\nB. Internet\nC. NSFNET\nD. ARPANET",
            cleaned,
        )

    def test_export_returns_warning_when_some_problems_are_missing(self) -> None:
        base_url = "https://pintia.cn/problem-sets/demo"
        exam_url = f"{base_url}/exam/problems/type"
        problem_1 = f"{base_url}/problems/p1"
        problem_2 = f"{base_url}/problems/p2"
        self.scraper.session = FakeSession(
            {
                exam_url: PageSnapshot(
                    url=exam_url,
                    title="题目列表",
                    html=f"""
                    <html><body>
                      <a href="{problem_1}">题目一</a>
                      <a href="{problem_2}">题目二</a>
                    </body></html>
                    """,
                    links=[],
                    problem_count=2,
                ),
                problem_1: PageSnapshot(
                    url=problem_1,
                    title="题目一",
                    html="""
                    <html><body><main>
                      <h1>题目一</h1>
                      <h2>题目描述</h2>
                      <p>完整内容。</p>
                    </main></body></html>
                    """,
                    links=[],
                ),
            }
        )
        result = self.scraper.export_problem_sets(
            [ProblemSetSummary(id="demo", title="演示题目集", url=base_url)],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=False,
            target_account="demo-user",
        )
        self.assertTrue(Path(result.output_path).exists())
        self.assertTrue(any("可能漏题" in warning for warning in result.warnings))
        self.assertTrue(any("题目《题目二》抓取失败" in warning for warning in result.warnings))
        self.assertEqual(1, result.summary.failed_problem_total)
        self.assertEqual(2, result.summary.expected_problem_total)
        self.assertEqual(1, result.summary.parsed_problem_total)

    def test_export_records_image_download_warning_in_summary(self) -> None:
        class ImageFailingSession(FakeSession):
            def download_bytes(self, url: str, *, base_url: str = "", referer: str = "") -> tuple[bytes, str]:
                raise RuntimeError("image backend unavailable")

        problem_url = "https://pintia.cn/problem-sets/demo-image/problems/p1"
        self.scraper.session = ImageFailingSession(
            {
                problem_url: PageSnapshot(
                    url=problem_url,
                    title="题目一",
                    html="""
                    <html><body><main>
                      <h1>题目一</h1>
                      <h2>题目描述</h2>
                      <p>带图片的题面。</p>
                      <img src="https://example.com/image.png" alt="示意图" />
                    </main></body></html>
                    """,
                    links=[],
                )
            }
        )

        result = self.scraper.export_problem_sets(
            [ProblemSetSummary(id="demo-image", title="图片题目集", url=problem_url)],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=True,
            target_account="demo-user",
        )

        self.assertTrue(any("图片下载失败" in warning for warning in result.warnings))
        self.assertEqual(1, result.summary.image_warning_count)
        self.assertEqual(1, result.summary.warning_count)

    def test_export_separate_mode_generates_one_docx_per_problem_set(self) -> None:
        first_url = "https://pintia.cn/problem-sets/demo-a"
        second_url = "https://pintia.cn/problem-sets/demo-b"
        self.scraper.session = FakeSession(
            {
                first_url: PageSnapshot(
                    url=first_url,
                    title="Problem A",
                    html="""
                    <html><body><main>
                      <h1>Problem A</h1>
                      <h2>Description</h2>
                      <p>Content A</p>
                    </main></body></html>
                    """,
                    links=[],
                ),
                second_url: PageSnapshot(
                    url=second_url,
                    title="Problem B",
                    html="""
                    <html><body><main>
                      <h1>Problem B</h1>
                      <h2>Description</h2>
                      <p>Content B</p>
                    </main></body></html>
                    """,
                    links=[],
                ),
            }
        )
        result = self.scraper.export_problem_sets(
            [
                ProblemSetSummary(id="demo-a", title="Set A", url=first_url),
                ProblemSetSummary(id="demo-b", title="Set B", url=second_url),
            ],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=False,
            export_mode="separate",
            target_account="demo-user",
        )
        self.assertEqual("separate", result.export_mode)
        self.assertEqual(2, len(result.output_paths))
        self.assertEqual(result.output_paths[0], result.output_path)
        self.assertTrue(all(Path(path).exists() for path in result.output_paths))
        self.assertNotEqual(Path(result.output_paths[0]).name, Path(result.output_paths[1]).name)
        self.assertEqual("Set A.docx", Path(result.output_paths[0]).name)
        self.assertEqual("Set B.docx", Path(result.output_paths[1]).name)

    def test_export_merged_mode_uses_problem_set_name_for_filename(self) -> None:
        only_url = "https://pintia.cn/problem-sets/demo-single"
        self.scraper.session = FakeSession(
            {
                only_url: PageSnapshot(
                    url=only_url,
                    title="Problem Single",
                    html="""
                    <html><body><main>
                      <h1>Problem Single</h1>
                      <h2>Description</h2>
                      <p>Content Single</p>
                    </main></body></html>
                    """,
                    links=[],
                ),
            }
        )
        result = self.scraper.export_problem_sets(
            [ProblemSetSummary(id="demo-single", title="Single Set", url=only_url)],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=False,
            export_mode="merged",
            target_account="demo-user",
        )
        self.assertEqual("merged", result.export_mode)
        self.assertEqual("Single Set.docx", Path(result.output_path).name)

    def test_export_merged_mode_uses_custom_filename_when_provided(self) -> None:
        only_url = "https://pintia.cn/problem-sets/demo-custom"
        self.scraper.session = FakeSession(
            {
                only_url: PageSnapshot(
                    url=only_url,
                    title="Problem Custom",
                    html="""
                    <html><body><main>
                      <h1>Problem Custom</h1>
                      <h2>Description</h2>
                      <p>Content Custom</p>
                    </main></body></html>
                    """,
                    links=[],
                ),
            }
        )
        result = self.scraper.export_problem_sets(
            [ProblemSetSummary(id="demo-custom", title="Original Set", url=only_url)],
            output_dir=Path(self.temp_dir.name) / "exports",
            embed_images=False,
            export_mode="merged",
            merged_filename_stem="用户自定义文件名",
        )
        self.assertEqual("用户自定义文件名.docx", Path(result.output_path).name)

    def test_ensure_target_account_accepts_trimmed_case_insensitive_match(self) -> None:
        self.scraper.session = FakeSession(
            {},
            current_user={
                "authenticated": True,
                "accountId": " Demo-User ",
                "displayName": "Demo User",
            },
        )

        state = self.scraper.ensure_target_account("demo-user")
        self.assertEqual("Demo User", state["displayName"])

    def test_ensure_target_account_rejects_mismatch(self) -> None:
        self.scraper.session = FakeSession(
            {},
            current_user={
                "authenticated": True,
                "accountId": "account-a",
                "displayName": "Account A",
            },
        )

        with self.assertRaises(SessionError):
            self.scraper.ensure_target_account("account-b")

    def test_ensure_target_account_rejects_unidentified_account(self) -> None:
        self.scraper.session = FakeSession(
            {},
            current_user={
                "authenticated": True,
                "accountId": "",
                "displayName": "",
            },
        )

        with self.assertRaises(SessionError):
            self.scraper.ensure_target_account("account-a")

    def test_switch_account_forwards_to_session(self) -> None:
        fake_session = FakeSession({})
        self.scraper.session = fake_session

        result = self.scraper.switch_account("https://pintia.cn/problem-sets/all")

        self.assertEqual(["https://pintia.cn/problem-sets/all"], fake_session.switch_calls)
        self.assertFalse(result["authenticated"])

    def test_expected_inline_problem_total_uses_unique_problem_ids(self) -> None:
        snapshot = PageSnapshot(
            url="https://pintia.cn/problem-sets/demo/exam/problems/type",
            title="题目列表",
            html="""
            <html><body>
              <div class="flex flex-col m-4 mb-0 flex-1">
                <div class="pc-x" id="p1"></div>
                <div class="pc-x" id="p2"></div>
                <a href="/problems/p1">题目一</a>
                <a href="/problems/p2">题目二</a>
              </div>
            </body></html>
            """,
            links=[],
            problem_count=4,
        )
        inline_problems = [
            self.scraper._parse_inline_problem_node(html.fromstring('<div class="pc-x" id="p1"><button>1-1</button></div>'), snapshot.url, 1),
            self.scraper._parse_inline_problem_node(html.fromstring('<div class="pc-x" id="p2"><button>1-2</button></div>'), snapshot.url, 2),
        ]
        self.assertEqual(2, self.scraper._expected_inline_problem_total(snapshot, inline_problems))


class AppQueueHelperTests(unittest.TestCase):
    def test_problem_set_and_type_queue_conflicts_are_mutually_exclusive(self) -> None:
        whole = ExportSourceSummary(
            id="set-1",
            title="计算机网络",
            url="https://pintia.cn/problem-sets/set-1/overview",
            source_kind="problem_set",
            parent_problem_set_id="set-1",
            parent_title="计算机网络",
        )
        child = ExportSourceSummary(
            id="set-1:type:1",
            title="判断题",
            url="https://pintia.cn/problem-sets/set-1/exam/problems/type/1",
            source_kind="problem_type",
            parent_problem_set_id="set-1",
            parent_title="计算机网络",
            type_label="判断题",
        )

        self.assertIn("整套已在队列中", PTAExporterApp._queue_conflict_message([whole], child) or "")
        self.assertIn("已有题型子项", PTAExporterApp._queue_conflict_message([child], whole) or "")

    def test_duplicate_problem_type_is_rejected_and_type_name_drives_labels(self) -> None:
        child = ExportSourceSummary(
            id="set-1:type:4",
            title="填空题",
            url="https://pintia.cn/problem-sets/set-1/exam/problems/type/4",
            source_kind="problem_type",
            parent_problem_set_id="set-1",
            parent_title="计算机网络",
            type_label="填空题",
        )

        self.assertEqual("计算机网络 / 填空题", child.queue_label())
        self.assertEqual("计算机网络_填空题", child.export_title())
        self.assertIn("已在导出队列中", PTAExporterApp._queue_conflict_message([child], child) or "")


if __name__ == "__main__":
    unittest.main()
