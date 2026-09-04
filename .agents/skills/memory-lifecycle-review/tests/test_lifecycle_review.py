import json
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPT_DIR))

import lifecycle_review  # noqa: E402


class LifecycleReviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        (self.root / "project").mkdir()
        (self.root / "memories").mkdir()
        (self.root / "memories" / "大纲记忆.md").write_text("# 大纲记忆\n", encoding="utf-8")
        (self.root / "memories" / "包装记忆.md").write_text("# 包装记忆\n", encoding="utf-8")
        self.write_memory("候选")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def write_memory(self, status: str, memory_id: str = "SCR-0001") -> None:
        text = (
            "# 文稿记忆\n\n"
            f"### {memory_id}｜先给具体场景\n"
            "阶段：文稿\n"
            f"状态：{status}\n"
            "内容：先给具体场景，再解释抽象概念。\n"
        )
        (self.root / "memories" / "文稿记忆.md").write_text(text, encoding="utf-8")

    def write_ledger(
        self,
        index_row: str = "| — | — | — | — | — | — | — | — | — |\n",
        history_rows: str = "| — | — | — | — | 暂无已确认记录 | — |\n",
    ) -> Path:
        path = self.root / "memories" / "记忆登记簿.md"
        path.write_text(
            "# 记忆登记簿\n\n"
            "## 记忆索引\n\n"
            "| 记忆ID | 阶段 | 当前状态 | 采用期数 | 结果支持期数 | 结果反例期数 | 观察期数 | 涉及期数 | 最近复核日期 |\n"
            "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- |\n"
            + index_row
            + "\n## 状态历史\n\n"
            "| 日期 | 记忆ID | 原状态 | 新状态 | 原因 | 依据 |\n"
            "| --- | --- | --- | --- | --- | --- |\n"
            + history_rows,
            encoding="utf-8",
        )
        return path

    def write_project(
        self,
        directory: str,
        episode_id: str,
        rows=None,
        include_snapshot: bool = True,
    ) -> Path:
        path = self.root / "project" / directory
        path.mkdir()
        lines = ["# 本期影片记录", "", "## 基础信息", f"- episode_id：{episode_id}", "", "## Changelog", ""]
        if include_snapshot:
            lines.extend(
                [
                    "### 本期相关记忆（快照）",
                    "",
                    "| 日期 | 记忆ID | 阶段 | 状态 | 本期结果 | 依据 |",
                    "| --- | --- | --- | --- | --- | --- |",
                ]
            )
            for row in rows or []:
                result = row.get("result", "采用")
                evidence = row.get("evidence", "用户确认版本")
                lines.append(
                    f"| 2026-09-02 | {row.get('id', 'SCR-0001')} | {row.get('stage', '文稿')} | {row.get('status', '候选')} | {result} | {evidence} |"
                )
        (path / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        return path

    def test_counts_are_separate_and_full_scan_can_request_promotion(self) -> None:
        self.write_project("任意-a", "WF-20260808-01", [{"result": "采用、待验证"}])
        self.write_project("任意-b", "WF-20260815-01", [{"result": "采用、已验证"}])
        self.write_project("任意-c", "WF-20260822-01", [{"result": "采用、失败"}])

        scoped = lifecycle_review.build_report(
            self.root,
            ["WF-20260808-01", "WF-20260815-01", "WF-20260822-01"],
            False,
            ["SCR-0001"],
        )
        entry = scoped["memories"][0]
        self.assertEqual((entry["adoption_periods"], entry["result_support_periods"]), (3, 1))
        self.assertEqual(
            (entry["result_counterexample_periods"], entry["observation_periods"]),
            (1, 1),
        )
        self.assertEqual(scoped["applications"][0]["to"], "正式")

        full = lifecycle_review.build_report(self.root, [], True, ["SCR-0001"])
        self.assertEqual(full["applications"][0]["to"], "正式")
        self.assertIn("结果支持期数为 1", full["applications"][0]["reason"])

    def test_same_memory_twice_in_one_readme_is_rejected(self) -> None:
        self.write_project(
            "重复项目",
            "WF-20260808-01",
            [{"result": "采用"}, {"result": "待验证"}],
        )
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, ["WF-20260808-01"], False)

    def test_old_readme_is_marked_unstructured_and_not_counted(self) -> None:
        self.write_project("新项目", "WF-20260808-01", [{"result": "采用"}])
        self.write_project("旧项目", "WF-20260815-01", include_snapshot=False)
        report = lifecycle_review.build_report(
            self.root,
            ["WF-20260808-01", "WF-20260815-01"],
            False,
        )
        self.assertEqual(report["memories"][0]["adoption_periods"], 1)
        self.assertEqual(len(report["unstructured"]), 1)
        self.assertIn("历史未结构化", report["unstructured"][0]["reason"])

    def test_invalid_result_and_stage_fail_closed(self) -> None:
        self.write_project("非法结果", "WF-20260808-01", [{"result": "采用、神奇"}])
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, ["WF-20260808-01"], False)

        self.root.joinpath("project", "非法结果", "README.md").unlink()
        self.write_project(
            "非法阶段",
            "WF-20260815-01",
            [{"id": "SCR-0001", "stage": "大纲", "result": "采用"}],
        )
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, ["WF-20260815-01"], False)

    def test_formal_memory_only_requests_staging_for_explicit_conflict(self) -> None:
        self.write_memory("正式")
        self.write_project("单次失败", "WF-20260808-01", [{"result": "失败"}])
        failed = lifecycle_review.build_report(self.root, ["WF-20260808-01"], False)
        self.assertEqual(failed["applications"], [])

        self.root.joinpath("project", "单次失败", "README.md").unlink()
        self.write_project(
            "明确冲突",
            "WF-20260815-01",
            [{"result": "明确冲突", "evidence": "用户版本明确冲突"}],
        )
        conflict = lifecycle_review.build_report(self.root, ["WF-20260815-01"], False)
        self.assertEqual(conflict["applications"][0]["to"], "暂存")

    def test_example_is_excluded_and_directory_name_is_not_episode_id(self) -> None:
        self.write_project("目录名不是 ID", "WF-20260808-01", [{"result": "采用"}])
        example = self.root / "project" / "example"
        example.mkdir()
        (example / "README.md").write_text(
            "# 模板\n- episode_id：WF-20990101-99\n## Changelog\n",
            encoding="utf-8",
        )
        report = lifecycle_review.build_report(self.root, [], True)
        self.assertEqual(report["episodes"], ["WF-20260808-01"])

    def test_duplicate_episode_ids_across_projects_are_rejected(self) -> None:
        self.write_project("项目甲", "WF-20260808-01", [{"result": "采用"}])
        self.write_project("项目乙", "WF-20260808-01", [{"result": "采用"}])
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, [], True)

    def test_duplicate_requested_episode_ids_are_rejected(self) -> None:
        self.write_project("唯一项目", "WF-20260808-01", [{"result": "采用"}])
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(
                self.root,
                ["WF-20260808-01", "WF-20260808-01"],
                False,
            )

    def test_empty_requested_episode_ids_are_rejected(self) -> None:
        self.write_project("唯一项目", "WF-20260808-01", [{"result": "采用"}])
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, [""], False)

    def test_ledger_mismatch_is_reported_during_full_scan(self) -> None:
        self.write_project("有快照", "WF-20260808-01", [{"result": "采用"}])
        self.write_ledger(
            "| SCR-0001 | 文稿 | 候选 | 0 | 0 | 0 | 0 | 0 | — |\n"
        )
        report = lifecycle_review.build_report(self.root, [], True, ["SCR-0001"])
        self.assertEqual(report["ledger_check"]["status"], "不一致")
        self.assertTrue(any("采用期数不一致" in warning for warning in report["warnings"]))

    def test_status_history_requires_table_rows(self) -> None:
        self.write_memory("正式")
        self.write_project("状态历史损坏", "WF-20260808-01", [{"result": "采用"}])
        self.write_ledger(
            "| SCR-0001 | 文稿 | 正式 | 1 | 0 | 0 | 0 | 1 | 2026-09-02 |\n",
            "损坏的状态历史行\n",
        )
        with self.assertRaises(lifecycle_review.LifecycleError):
            lifecycle_review.build_report(self.root, [], True, ["SCR-0001"])

    def test_negated_history_text_does_not_request_staging(self) -> None:
        self.write_memory("正式")
        self.write_project("无停用事实", "WF-20260808-01", [{"result": "失败"}])
        self.write_ledger(
            "| SCR-0001 | 文稿 | 正式 | 0 | 0 | 1 | 0 | 1 | 2026-09-02 |\n",
            "| 2026-09-02 | SCR-0001 | 正式 | 候选 | 无停用证据 | 用户尚未确认 |\n",
        )
        report = lifecycle_review.build_report(self.root, [], True, ["SCR-0001"])
        self.assertEqual(report["applications"], [])

    def test_explicit_replacement_history_requests_staging_with_traceable_evidence(self) -> None:
        self.write_memory("正式")
        self.write_project("被替代", "WF-20260808-01", [{"result": "失败"}])
        self.write_ledger(
            "| SCR-0001 | 文稿 | 正式 | 0 | 0 | 1 | 0 | 1 | 2026-09-02 |\n",
            "| 2026-09-02 | SCR-0001 | 正式 | 暂存 | 被替代 | 用户确认的新规则链接 |\n",
        )
        report = lifecycle_review.build_report(self.root, [], True, ["SCR-0001"])
        application = report["applications"][0]
        self.assertEqual(application["to"], "暂存")
        self.assertIn("登记簿状态历史", "；".join(application["evidence"]))

    def test_staged_memory_requires_explicit_reobserve_request(self) -> None:
        self.write_memory("暂存")
        self.write_project("重新观察", "WF-20260808-01", [{"result": "待验证"}])
        without_request = lifecycle_review.build_report(
            self.root, ["WF-20260808-01"], False, ["SCR-0001"]
        )
        self.assertEqual(without_request["applications"], [])
        with_request = lifecycle_review.build_report(
            self.root,
            ["WF-20260808-01"],
            False,
            ["SCR-0001"],
            ["SCR-0001"],
        )
        self.assertEqual(with_request["applications"][0]["to"], "候选")

    def test_report_is_read_only_and_json_serializable(self) -> None:
        path = self.write_project("只读项目", "WF-20260808-01", [{"result": "采用"}]) / "README.md"
        before = path.read_bytes()
        report = lifecycle_review.build_report(self.root, ["WF-20260808-01"], False)
        json.dumps(report, ensure_ascii=False)
        self.assertEqual(path.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
