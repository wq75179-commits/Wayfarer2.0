#!/usr/bin/env python3
"""Read-only validation for channel-level decision memory."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


COMMON_PATH = Path(__file__).parents[2] / "archive-episode" / "scripts" / "validate_memory_workflow.py"
SPEC = importlib.util.spec_from_file_location("memory_workflow_common_for_decisions", COMMON_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载共享检查器：{COMMON_PATH}")
COMMON = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COMMON
SPEC.loader.exec_module(COMMON)


DECISION_HEADING = re.compile(r"(?m)^###\s+(D(\d{3}))[：:]\s*(.+?)\s*$")
DECISION_FIELD = re.compile(r"(?m)^-\s+\*\*([^*]+)\*\*[：:]\s*(.*?)\s*$")
REQUIRED_FIELDS = ("决策日期", "决策内容", "决策原因", "影响范围", "生效起始", "状态", "回顾评价")
VALID_STATUS_WORDS = ("执行中", "待观察", "已废弃")


@dataclass(frozen=True)
class Decision:
    decision_id: str
    number: int
    title: str
    fields: dict[str, str]


def parse_decisions(text: str) -> list[Decision]:
    section = COMMON.extract_heading_section(COMMON.strip_html_comments(text), "决策记录", 2)
    headings = list(DECISION_HEADING.finditer(section))
    decisions: list[Decision] = []
    for index, heading in enumerate(headings):
        end = headings[index + 1].start() if index + 1 < len(headings) else len(section)
        block = section[heading.end() : end]
        decisions.append(
            Decision(
                decision_id=heading.group(1),
                number=int(heading.group(2)),
                title=heading.group(3).strip(),
                fields={match.group(1).strip(): match.group(2).strip() for match in DECISION_FIELD.finditer(block)},
            )
        )
    return decisions


def validate_source_link(path: Path, value: str, repo_root: Path, decision_id: str) -> list[COMMON.Issue]:
    link = re.search(r"\[[^\]]+\]\(([^)]+)\)", value)
    if link is None:
        return [COMMON.issue("ERROR", "INVALID_DECISION_SOURCE", f"{path}::{decision_id}", "来源项目必须是 README 链接。")]
    target = (path.parent / link.group(1)).resolve()
    try:
        target.relative_to(repo_root.resolve())
    except ValueError:
        return [COMMON.issue("ERROR", "DECISION_SOURCE_OUTSIDE_REPO", f"{path}::{decision_id}", "来源项目不得位于仓库外。")]
    if not target.is_file() or target.name != "README.md" or target.parent.name == "example":
        return [COMMON.issue("ERROR", "BROKEN_DECISION_SOURCE", f"{path}::{decision_id}", "来源项目必须指向真实单期 README。")]
    return []


def has_decision_log(readme: Path) -> bool:
    section = COMMON.extract_heading_section(COMMON.read_utf8(readme), "Changelog", 2)
    _, rows = COMMON.parse_markdown_table(section)
    return any(
        row.get("阶段") == "记忆整理"
        and row.get("类型") == "记忆写入"
        and ("重大决策" in row.get("决策或变更", "") or "频道决定" in row.get("决策或变更", ""))
        for row in rows
    )


def validate_channel_decisions(
    repo_root: Path,
    episode_value: str | None = None,
    *,
    require_log: bool = False,
) -> list[COMMON.Issue]:
    repo_root = repo_root.resolve()
    path = repo_root / "memories" / "重大决策记忆.md"
    if not path.is_file():
        return [COMMON.issue("ERROR", "MISSING_DECISION_MEMORY", path, "缺少重大决策记忆。")]

    text = COMMON.read_utf8(path)
    cleaned = COMMON.strip_html_comments(text)
    issues: list[COMMON.Issue] = []
    for heading in COMMON.MEMORY_SHAPES["重大决策记忆.md"]:
        if not re.search(rf"(?m)^##\s+{re.escape(heading)}\s*$", cleaned):
            issues.append(COMMON.issue("ERROR", "MISSING_DECISION_HEADING", path, f"缺少章节：{heading}。"))

    decisions = parse_decisions(text)
    ids = [item.decision_id for item in decisions]
    if len(ids) != len(set(ids)):
        issues.append(COMMON.issue("ERROR", "DUPLICATE_DECISION_ID", path, "重大决策编号重复。"))
    numbers = sorted({item.number for item in decisions})
    if numbers and numbers != list(range(1, max(numbers) + 1)):
        issues.append(COMMON.issue("ERROR", "DECISION_ID_GAP", path, "重大决策编号必须从 D001 连续递增。"))

    for decision in decisions:
        item_path = f"{path}::{decision.decision_id}"
        if not decision.title:
            issues.append(COMMON.issue("ERROR", "MISSING_DECISION_TITLE", item_path, "重大决策缺少标题。"))
        for field in REQUIRED_FIELDS:
            if COMMON.is_blank(decision.fields.get(field)):
                issues.append(COMMON.issue("ERROR", "MISSING_DECISION_FIELD", item_path, f"缺少字段：{field}。"))
        date_value = decision.fields.get("决策日期", "")
        try:
            datetime.strptime(date_value, "%Y-%m-%d")
        except ValueError:
            issues.append(COMMON.issue("ERROR", "INVALID_DECISION_DATE", item_path, "决策日期必须为 YYYY-MM-DD。"))
        status = decision.fields.get("状态", "")
        if status and not any(word in status for word in VALID_STATUS_WORDS):
            issues.append(COMMON.issue("ERROR", "INVALID_DECISION_STATUS", item_path, "决策状态必须是执行中、待观察或已废弃。"))
        source = decision.fields.get("来源项目")
        if decision.number >= 3 and source is None:
            issues.append(COMMON.issue("ERROR", "MISSING_DECISION_SOURCE", item_path, "新重大决策必须回链来源项目。"))
        elif source is not None:
            issues.extend(validate_source_link(path, source, repo_root, decision.decision_id))

    if episode_value is not None or require_log:
        readme, resolve_issues = COMMON.resolve_episode(repo_root, episode_value)
        issues.extend(resolve_issues)
        if readme is not None:
            issues.extend(COMMON.validate_changelog(readme, require_archive_entry=True))
            if require_log and not has_decision_log(readme):
                issues.append(COMMON.issue("ERROR", "MISSING_DECISION_CHANGELOG", readme, "Changelog 缺少重大决策写入记录。"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读检查频道重大决策记忆。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="仓库根目录。")
    parser.add_argument("--episode", help="本期真实 README 路径。")
    parser.add_argument("--require-log", action="store_true", help="要求本期 Changelog 存在重大决策写入记录。")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出问题。")
    args = parser.parse_args(argv)
    issues = validate_channel_decisions(args.repo_root, args.episode, require_log=args.require_log)
    if args.json:
        print(json.dumps([asdict(item) for item in issues], ensure_ascii=False, indent=2))
    elif not issues:
        print("OK：频道重大决策记忆检查通过。")
    else:
        for item in issues:
            print(f"{item.severity} [{item.code}] {item.path}: {item.message}")
    return 1 if any(item.severity == "ERROR" for item in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
