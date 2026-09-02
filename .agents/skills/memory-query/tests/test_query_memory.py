import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import query_memory  # noqa: E402


class MemoryQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        memory_dir = self.root / "memories"
        memory_dir.mkdir()
        for filename, title in (
            ("大纲记忆.md", "大纲记忆"),
            ("文稿记忆.md", "文稿记忆"),
            ("包装记忆.md", "包装记忆"),
        ):
            (memory_dir / filename).write_text(f"# {title}\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write(self, name: str, text: str) -> Path:
        path = self.root / "memories" / name
        path.write_text(text, encoding="utf-8")
        return path

    def write_ledger(self, rows: str = "") -> Path:
        path = self.root / "memories" / "记忆登记簿.md"
        path.write_text(
            "# 记忆登记簿\n\n"
            "## 记忆索引\n\n"
            "| 记忆ID | 阶段 | 当前状态 | 采用期数 | 结果支持期数 | 结果反例期数 | 观察期数 | 涉及期数 | 最近复核日期 |\n"
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n"
            + (rows or "| — | — | — | — | — | — | — | — | — |\n")
            + "\n## 状态历史\n\n"
            "| 日期 | 记忆ID | 原状态 | 新状态 | 原因 | 依据 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            "| — | — | — | — | 暂无已确认记录 | — |\n",
            encoding="utf-8",
        )
        return path

    def controlled(
        self,
        memory_id: str,
        title: str,
        stage: str = "文稿",
        status: str = "正式",
        content: str = "先给具体场景，再解释抽象概念。",
    ) -> str:
        return (
            f"### {memory_id}｜{title}\n"
            f"阶段：{stage}\n"
            f"状态：{status}\n"
            f"内容：{content}\n\n"
        )

    def invoke(self, *args: str):
        output = io.StringIO()
        error = io.StringIO()
        with redirect_stdout(output), redirect_stderr(error):
            code = query_memory.main(("--repo-root", str(self.root), *args))
        return code, output.getvalue(), error.getvalue()

    def test_default_returns_candidate_and_formal_but_excludes_staged(self) -> None:
        self.write(
            "文稿记忆.md",
            self.controlled("SCR-0001", "正式规则")
            + self.controlled("SCR-0002", "候选规则", status="候选")
            + self.controlled("SCR-0003", "暂存规则", status="暂存"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 2)
        self.assertEqual({item["status"] for item in body["entries"]}, {"正式", "候选"})

    def test_memory_must_belong_to_exactly_one_stage(self) -> None:
        self.write(
            "大纲记忆.md",
            self.controlled("OUT-0001", "跨阶段规则", stage="大纲,文稿,包装"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("只能属于一个阶段", error)

    def test_id_prefix_must_match_stage(self) -> None:
        self.write("文稿记忆.md", self.controlled("OUT-0001", "文稿规则"))
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("编号必须使用 SCR-xxxx", error)

    def test_removed_stage_is_rejected(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        code, output, error = self.invoke("--stage", "选题", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("无法识别阶段", error)

    def test_only_three_memory_stages_are_supported(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        for stage in ("核心承诺", "资料", "审稿", "复盘", "通用"):
            code, output, error = self.invoke("--stage", stage, "--format", "json")
            self.assertNotEqual(code, 0, stage)
            self.assertEqual(output, "")
            self.assertIn("无法识别阶段", error)

    def test_stage_alias_and_explicit_status(self) -> None:
        self.write("大纲记忆.md", self.controlled("OUT-0001", "大纲规则", stage="大纲", status="候选"))
        code, output, error = self.invoke("--stage", "outline-drafting", "--status", "候选", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["entries"][0]["id"], "OUT-0001")
        self.assertEqual(body["entries"][0]["status"], "候选")

    def test_old_promise_alias_is_not_misclassified_as_outline(self) -> None:
        self.write("大纲记忆.md", self.controlled("OUT-0001", "大纲规则", stage="大纲"))
        code, output, error = self.invoke("--stage", "structure-drafting", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("无法识别阶段", error)

    def test_explicit_staged_query_only_returns_staged(self) -> None:
        self.write(
            "文稿记忆.md",
            self.controlled("SCR-0001", "正式规则")
            + self.controlled("SCR-0002", "暂存规则", status="暂存"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--status", "暂存", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual([item["status"] for item in body["entries"]], ["暂存"])

    def test_uncontrolled_content_fails_closed(self) -> None:
        self.write("文稿记忆.md", "# 文稿记忆\n\n## 风格补丁\n\n先给场景，再解释术语。\n")
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("包含无编号内容", error)

    def test_all_status_means_candidate_and_formal_not_staged(self) -> None:
        self.write(
            "文稿记忆.md",
            self.controlled("SCR-0001", "正式规则")
            + self.controlled("SCR-0002", "候选规则", status="候选")
            + self.controlled("SCR-0003", "暂存规则", status="暂存"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--status", "全部", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 2)
        self.assertEqual({item["status"] for item in body["entries"]}, {"正式", "候选"})

    def test_duplicate_controlled_ids_fail_closed(self) -> None:
        self.write(
            "文稿记忆.md",
            self.controlled("SCR-0001", "第一条") + self.controlled("SCR-0001", "重复条"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("记忆编号重复", error)

    def test_missing_controlled_field_fails_closed(self) -> None:
        self.write("文稿记忆.md", "### SCR-0001｜缺内容\n阶段：文稿\n状态：正式\n")
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("必须同时包含阶段、状态和内容", error)

    def test_default_returns_all_matching_entries(self) -> None:
        self.write(
            "文稿记忆.md",
            self.controlled("SCR-0001", "第一条", content="甲" * 40)
            + self.controlled("SCR-0002", "第二条", content="乙" * 40),
        )
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 2)
        self.assertEqual([item["id"] for item in body["entries"]], ["SCR-0001", "SCR-0002"])

    def test_empty_result_is_explicit_and_not_an_error(self) -> None:
        self.write("大纲记忆.md", self.controlled("OUT-0001", "大纲规则", stage="大纲"))
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 0)
        self.assertEqual(body["entries"], [])

    def test_markdown_and_json_share_the_same_entries(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        json_code, json_output, json_error = self.invoke("--stage", "文稿", "--format", "json")
        md_code, md_output, md_error = self.invoke("--stage", "文稿", "--format", "markdown")
        self.assertEqual(json_code, 0, json_error)
        self.assertEqual(md_code, 0, md_error)
        self.assertIn("SCR-0001", md_output)
        self.assertIn("规则", md_output)
        self.assertEqual(json.loads(json_output)["count"], 1)

    def test_comment_template_is_not_returned_as_legacy_memory(self) -> None:
        self.write(
            "文稿记忆.md",
            "<!--\n### SCR-0001｜模板\n阶段：文稿\n状态：正式\n内容：不应读取。\n-->\n\n"
            + self.controlled("SCR-0002", "真实规则"),
        )
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 1)
        self.assertEqual(body["entries"][0]["title"], "真实规则")

    def test_unknown_memory_file_fails_closed(self) -> None:
        self.write("旧记忆.md", "# 旧记忆\n")
        code, output, error = self.invoke("--stage", "包装", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("发现不支持的记忆文件", error)

    def test_query_is_read_only(self) -> None:
        path = self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        before = path.read_bytes()
        code, _, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        self.assertEqual(path.read_bytes(), before)

    def test_unknown_stage_is_rejected(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        code, output, error = self.invoke("--stage", "未知阶段", "--format", "json")
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("无法识别阶段", error)

    def test_default_query_ignores_ledger(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        self.write_ledger()
        code, output, error = self.invoke("--stage", "文稿", "--format", "json")
        self.assertEqual(code, 0, error)
        body = json.loads(output)
        self.assertEqual(body["count"], 1)
        self.assertNotIn("evidence", body["entries"][0])

    def test_include_evidence_reads_ledger_without_changing_default_fields(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        self.write_ledger(
            "| SCR-0001 | 文稿 | 正式 | 3 | 1 | 0 | 1 | 3 | 2026-09-02 |\n"
        )
        code, output, error = self.invoke(
            "--stage", "文稿", "--format", "json", "--include-evidence"
        )
        self.assertEqual(code, 0, error)
        entry = json.loads(output)["entries"][0]
        self.assertEqual(entry["id"], "SCR-0001")
        self.assertEqual(entry["evidence"]["adoption_periods"], 3)
        self.assertEqual(entry["evidence"]["result_support_periods"], 1)
        self.assertEqual(entry["evidence"]["result_counterexample_periods"], 0)
        self.assertEqual(entry["evidence"]["observation_periods"], 1)

    def test_include_evidence_requires_ledger(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        code, output, error = self.invoke(
            "--stage", "文稿", "--format", "json", "--include-evidence"
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("详情模式不可用", error)

    def test_include_evidence_requires_matching_ledger_entry(self) -> None:
        self.write("文稿记忆.md", self.controlled("SCR-0001", "规则"))
        self.write_ledger(
            "| SCR-0002 | 文稿 | 候选 | 0 | 0 | 0 | 0 | 0 | 2026-09-02 |\n"
        )
        code, output, error = self.invoke(
            "--stage", "文稿", "--format", "json", "--include-evidence"
        )
        self.assertNotEqual(code, 0)
        self.assertEqual(output, "")
        self.assertIn("登记簿缺少阶段记忆", error)


if __name__ == "__main__":
    unittest.main()
