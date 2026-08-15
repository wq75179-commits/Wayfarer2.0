from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "validate_creative_memory.py"
SPEC = importlib.util.spec_from_file_location("creative_memory_validator", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


def write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def memory(headings: tuple[str, ...], extra: str = "") -> str:
    return "# 记忆\n\n" + "\n\n".join(f"## {heading}" for heading in headings) + f"\n\n{extra}\n"


def archived_readme(log_text: str = "整理大纲经验：开场待观察") -> str:
    return f"""# 本期影片记录

## 数据分析

## Changelog

| 日期 | 阶段 | 类型 | 决策或变更 | 原因 | 依据 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-08 | 归档 | 决策 | 本期已归档 | 用户已确认 | 发布结果 |
| 2026-08-08 | 记忆整理 | 记忆写入 | {log_text} | 用户已批准 | 最终大纲 |

## 文档索引
"""


class CreativeMemoryValidatorTests(unittest.TestCase):
    def create_repo(self, outline_extra: str = "", script_extra: str = "") -> tempfile.TemporaryDirectory[str]:
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        write(root, "memories/大纲创作技巧记忆.md", memory(VALIDATOR.TARGETS["大纲创作技巧记忆.md"], outline_extra))
        write(root, "memories/文稿撰写记忆.md", memory(VALIDATOR.TARGETS["文稿撰写记忆.md"], script_extra))
        write(root, "project/episode-a/README.md", archived_readme())
        return temporary

    def codes(self, root: Path, require_log: bool = False) -> set[str]:
        return {
            item.code
            for item in VALIDATOR.validate_creative_memory(
                root,
                "project/episode-a/README.md",
                require_log=require_log,
            )
        }

    def test_existing_shapes_are_valid(self) -> None:
        with self.create_repo() as temporary:
            self.assertEqual(self.codes(Path(temporary)), set())

    def test_waiting_pattern_count_matches_sources(self) -> None:
        line = "- [待观察｜2/3] 偏好直接提问（来源：WF-20260801-01、WF-20260815-01）"
        with self.create_repo(outline_extra=line) as temporary:
            self.assertEqual(self.codes(Path(temporary)), set())

    def test_waiting_pattern_rejects_count_mismatch(self) -> None:
        line = "- [待观察｜2/3] 偏好直接提问（来源：WF-20260801-01）"
        with self.create_repo(outline_extra=line) as temporary:
            self.assertIn("WATCH_SOURCE_COUNT_MISMATCH", self.codes(Path(temporary)))

    def test_duplicate_source_is_rejected(self) -> None:
        line = "- [待观察｜2/3] 偏好直接提问（来源：WF-20260801-01、WF-20260801-01）"
        with self.create_repo(script_extra=line) as temporary:
            self.assertIn("DUPLICATE_CREATIVE_SOURCE", self.codes(Path(temporary)))

    def test_required_log_is_checked(self) -> None:
        with self.create_repo() as temporary:
            root = Path(temporary)
            write(root, "project/episode-a/README.md", archived_readme("整理往期影片记录"))
            self.assertIn("MISSING_CREATIVE_CHANGELOG", self.codes(root, require_log=True))


if __name__ == "__main__":
    unittest.main()
