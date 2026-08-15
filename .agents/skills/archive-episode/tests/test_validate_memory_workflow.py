from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_memory_workflow.py"
SPEC = importlib.util.spec_from_file_location("memory_workflow_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def readme(*, changelog: str | None = None, archived: bool = True) -> str:
    changelog_block = changelog or """| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-08 | 归档 | 决策 | 本期已发布并归档 | 用户已确认 | 发布结果 |"""
    status = "归档" if archived else "口播文稿"
    archive_state = "已确认" if archived else "未进行"
    return f"""# 本期影片记录

## 基础信息

- episode_id：WF-20260801-01
- 创建日期：2026-08-01
- 选题：用行动摩擦解释启动困难
- 切入角度：从启动阻力切入
- 受众圈层：第一圈
- 内容类型：原创
- 核心承诺：给出一个最小行动
- 当前状态：{status}

## 创作确认

| 节点 | 状态 | 确认日期 | 决策摘要 | 备注 |
| --- | --- | --- | --- | --- |
| 归档 | {archive_state} | 2026-08-08 | 已发布并归档 | — |

## 发布结果

- 归档结果：已发布
- 最终标题：为什么启动比坚持更难
- 发布平台：B站
- 视频链接：https://example.com/video
- 发布时间：2026-08-08 20:00
- 视频时长：10:00
- 表现等级：符合预期
- 终局原因：
- 下一次复核动作：发布后 14D 复核

## 数据分析

- 结论状态：待验证

## Changelog

{changelog_block}

## 文档索引

- [README](./README.md)
"""


def empty_template() -> str:
    return """# 本期影片记录

## 数据分析

## Changelog

| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| — | — | — | 暂无已确认记录 | — | — |

## 文档索引
"""


def memory_shapes(root: Path) -> None:
    for filename, headings in VALIDATOR.MEMORY_SHAPES.items():
        write(root, f"memories/{filename}", "# 记忆\n\n" + "\n\n".join(f"## {heading}" for heading in headings))


class WorkflowValidatorTests(unittest.TestCase):
    def create_repo(self) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write(root, "project/example/README.md", empty_template())
        memory_shapes(root)
        return temporary

    def codes(self, root: Path, stage: str = "all", episode: str | None = None) -> set[str]:
        return {item.code for item in VALIDATOR.validate_workflow(root, stage, episode)}

    def test_template_with_changelog_is_valid(self) -> None:
        with self.create_repo() as temporary:
            self.assertEqual(self.codes(Path(temporary), "template"), set())

    def test_template_requires_changelog(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/example/README.md", "# 本期影片记录\n\n## 数据分析\n\n## 文档索引\n")
            self.assertIn("MISSING_CHANGELOG", self.codes(root, "template"))

    def test_archive_is_valid(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", readme())
            self.assertEqual(self.codes(root, "archive"), set())

    def test_archive_reports_when_no_real_project_exists(self) -> None:
        with self.create_repo() as temporary:
            self.assertIn("NO_REAL_EPISODE", self.codes(Path(temporary), "archive"))

    def test_archive_requires_confirmed_state(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", readme(archived=False))
            codes = self.codes(root, "archive")
            self.assertIn("NOT_ARCHIVED", codes)
            self.assertIn("ARCHIVE_NOT_CONFIRMED", codes)

    def test_archive_requires_changelog_entry(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            placeholder = """| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| — | — | — | 暂无已确认记录 | — | — |"""
            write(root, "project/episode-a/README.md", readme(changelog=placeholder))
            self.assertIn("MISSING_ARCHIVE_CHANGELOG", self.codes(root, "archive"))

    def test_duplicate_changelog_is_rejected(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            row = "| 2026-08-08 | 归档 | 决策 | 本期已发布并归档 | 用户已确认 | 发布结果 |"
            changelog = "| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |\n| --- | --- | --- | --- | --- | --- |\n" + row + "\n" + row
            path = write(root, "project/episode-a/README.md", readme(changelog=changelog))
            self.assertIn("DUPLICATE_CHANGELOG_ROW", {item.code for item in VALIDATOR.validate_changelog(path)})

    def test_placeholder_must_be_removed_after_real_entry(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            changelog = """| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| — | — | — | 暂无已确认记录 | — | — |
| 2026-08-08 | 归档 | 决策 | 本期已发布并归档 | 用户已确认 | 发布结果 |"""
            path = write(root, "project/episode-a/README.md", readme(changelog=changelog))
            self.assertIn("STALE_CHANGELOG_PLACEHOLDER", {item.code for item in VALIDATOR.validate_changelog(path)})

    def test_multiple_projects_are_not_guessed(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", readme(archived=False))
            write(root, "project/episode-b/README.md", readme(archived=False))
            self.assertIn("MULTIPLE_ACTIVE_EPISODES", self.codes(root, "archive"))

    def test_one_active_project_is_selected_among_archived_history(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/history/README.md", readme())
            active = write(root, "project/current/README.md", readme(archived=False))
            selected, issues = VALIDATOR.resolve_episode(root, None)
            self.assertEqual(issues, [])
            self.assertEqual(selected, active)

    def test_all_stage_requires_memory_headings(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", readme())
            write(root, "memories/文稿撰写记忆.md", "# 文稿撰写记忆\n")
            self.assertIn("MISSING_MEMORY_HEADING", self.codes(root, "all"))


if __name__ == "__main__":
    unittest.main()
