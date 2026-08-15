from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_channel_decisions.py"
SPEC = importlib.util.spec_from_file_location("channel_decision_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def decision(decision_id: str = "D001", status: str = "🟢 执行中", source: str = "") -> str:
    source_line = f"\n- **来源项目**：{source}" if source else ""
    return f"""### {decision_id}：频道定位

- **决策日期**：2026-08-01
- **决策内容**：聚焦学习效率
- **决策原因**：用户明确决定
- **影响范围**：选题
- **生效起始**：频道创立起
- **状态**：{status}{source_line}
- **回顾评价**：待补填
"""


def memory(body: str) -> str:
    return f"""# 重大决策记忆

## 使用说明

只记录频道长期决定。

## 决策记录

{body}
"""


def readme(log_text: str = "整理频道重大决策：D003") -> str:
    return f"""# 本期影片记录

## 数据分析

## Changelog

| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-08 | 归档 | 决策 | 本期已归档 | 用户已确认 | 发布结果 |
| 2026-08-08 | 记忆整理 | 记忆写入 | {log_text} | 用户已批准 | 本期 README |

## 文档索引
"""


class ChannelDecisionValidatorTests(unittest.TestCase):
    def create_repo(self, body: str | None = None) -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write(root, "project/episode-a/README.md", readme())
        write(root, "memories/重大决策记忆.md", memory(body or decision()))
        return temporary

    def codes(self, root: Path, require_log: bool = False) -> set[str]:
        return {
            item.code
            for item in VALIDATOR.validate_channel_decisions(
                root,
                "project/episode-a/README.md",
                require_log=require_log,
            )
        }

    def test_legacy_decision_without_source_is_valid(self) -> None:
        with self.create_repo() as temporary:
            self.assertEqual(self.codes(Path(temporary)), set())

    def test_duplicate_ids_are_rejected(self) -> None:
        with self.create_repo(decision() + "\n" + decision()) as temporary:
            self.assertIn("DUPLICATE_DECISION_ID", self.codes(Path(temporary)))

    def test_invalid_status_is_rejected(self) -> None:
        with self.create_repo(decision(status="准备中")) as temporary:
            self.assertIn("INVALID_DECISION_STATUS", self.codes(Path(temporary)))

    def test_new_source_link_is_validated(self) -> None:
        source = "[WF-20260801-01](../project/missing/README.md)"
        body = decision() + "\n" + decision(decision_id="D002") + "\n" + decision(decision_id="D003", source=source)
        with self.create_repo(body) as temporary:
            self.assertIn("BROKEN_DECISION_SOURCE", self.codes(Path(temporary)))

    def test_new_decision_requires_source(self) -> None:
        body = decision() + "\n" + decision(decision_id="D002") + "\n" + decision(decision_id="D003")
        with self.create_repo(body) as temporary:
            self.assertIn("MISSING_DECISION_SOURCE", self.codes(Path(temporary)))

    def test_required_log_is_checked(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", readme("整理文稿经验"))
            self.assertIn("MISSING_DECISION_CHANGELOG", self.codes(root, require_log=True))


if __name__ == "__main__":
    unittest.main()
