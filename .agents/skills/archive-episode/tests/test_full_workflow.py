from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SKILLS_ROOT = Path(__file__).parents[2]


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


WORKFLOW = load_module(
    "full_workflow_common",
    SKILLS_ROOT / "archive-episode" / "scripts" / "validate_memory_workflow.py",
)
HISTORY_TEST_HELPERS = load_module(
    "full_workflow_history_helpers",
    SKILLS_ROOT / "episode-memory-sync" / "tests" / "test_validate_sync.py",
)
CREATIVE = load_module(
    "full_workflow_creative",
    SKILLS_ROOT / "creative-memory-sync" / "scripts" / "validate_creative_memory.py",
)
DECISIONS = load_module(
    "full_workflow_decisions",
    SKILLS_ROOT / "channel-decision-sync" / "scripts" / "validate_channel_decisions.py",
)


def template() -> str:
    return """# 本期影片记录

## 数据分析

## Changelog

| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| — | — | — | 暂无已确认记录 | — | — |

## 文档索引
"""


def archived_episode() -> str:
    return HISTORY_TEST_HELPERS.episode_markdown() + """

## Changelog

| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-08 | 归档 | 决策 | 本期已发布并归档 | 用户已确认 | 发布结果 |

## 文档索引

- [README](./README.md)
"""


def simple_memory(headings: tuple[str, ...]) -> str:
    return "# 长期记忆\n\n" + "\n\n".join(f"## {heading}" for heading in headings) + "\n"


def decision_memory() -> str:
    return """# 重大决策记忆

## 使用说明

只记录频道长期决定。

## 决策记录

### D001：频道定位

- **决策日期**：2026-08-01
- **决策内容**：聚焦学习效率
- **决策原因**：用户明确决定
- **影响范围**：选题
- **生效起始**：频道创立起
- **状态**：🟢 执行中
- **回顾评价**：待补填
"""


class FullWorkflowTests(unittest.TestCase):
    def test_all_validators_accept_one_complete_archived_episode(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            HISTORY_TEST_HELPERS.write_file(root, "project/example/README.md", template())
            HISTORY_TEST_HELPERS.write_file(root, "project/episode-a/README.md", archived_episode())
            HISTORY_TEST_HELPERS.write_file(root, "memories/往期影片信息记录.md", HISTORY_TEST_HELPERS.memory_markdown())
            HISTORY_TEST_HELPERS.write_file(
                root,
                "memories/大纲创作技巧记忆.md",
                simple_memory(WORKFLOW.MEMORY_SHAPES["大纲创作技巧记忆.md"]),
            )
            HISTORY_TEST_HELPERS.write_file(
                root,
                "memories/文稿撰写记忆.md",
                simple_memory(WORKFLOW.MEMORY_SHAPES["文稿撰写记忆.md"]),
            )
            HISTORY_TEST_HELPERS.write_file(root, "memories/重大决策记忆.md", decision_memory())

            validators = (
                WORKFLOW.validate_workflow(root, "all", "project/episode-a/README.md"),
                HISTORY_TEST_HELPERS.VALIDATOR.validate_repository(root),
                CREATIVE.validate_creative_memory(root, "project/episode-a/README.md"),
                DECISIONS.validate_channel_decisions(root, "project/episode-a/README.md"),
            )
            error_codes = {
                item.code
                for issues in validators
                for item in issues
                if item.severity == "ERROR"
            }
            self.assertEqual(error_codes, set())


if __name__ == "__main__":
    unittest.main()
