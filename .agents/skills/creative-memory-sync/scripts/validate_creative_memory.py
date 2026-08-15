#!/usr/bin/env python3
"""Read-only validation for outline and script memory documents."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import asdict
from pathlib import Path


COMMON_PATH = Path(__file__).parents[2] / "archive-episode" / "scripts" / "validate_memory_workflow.py"
SPEC = importlib.util.spec_from_file_location("memory_workflow_common_for_creative", COMMON_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"无法加载共享检查器：{COMMON_PATH}")
COMMON = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = COMMON
SPEC.loader.exec_module(COMMON)


EPISODE_ID_PATTERN = re.compile(r"WF-\d{8}-\d{2}")
WATCH_PATTERN = re.compile(r"\[待观察[｜|](\d+)/3\]")
TARGETS = {
    "大纲创作技巧记忆.md": COMMON.MEMORY_SHAPES["大纲创作技巧记忆.md"],
    "文稿撰写记忆.md": COMMON.MEMORY_SHAPES["文稿撰写记忆.md"],
}


def validate_source_lines(path: Path, text: str) -> list[COMMON.Issue]:
    issues: list[COMMON.Issue] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        watch_match = WATCH_PATTERN.search(line)
        if "[待观察" in line and watch_match is None:
            issues.append(COMMON.issue("ERROR", "INVALID_WATCH_FORMAT", path, f"第 {line_number} 行待观察格式无效。"))
            continue
        source_ids = EPISODE_ID_PATTERN.findall(line)
        if len(source_ids) != len(set(source_ids)):
            issues.append(COMMON.issue("ERROR", "DUPLICATE_CREATIVE_SOURCE", path, f"第 {line_number} 行重复引用同一期项目。"))
        if watch_match is not None:
            expected_count = int(watch_match.group(1))
            if not 1 <= expected_count <= 3:
                issues.append(COMMON.issue("ERROR", "INVALID_WATCH_COUNT", path, f"第 {line_number} 行待观察次数必须为 1 到 3。"))
            if expected_count != len(set(source_ids)):
                issues.append(COMMON.issue("ERROR", "WATCH_SOURCE_COUNT_MISMATCH", path, f"第 {line_number} 行出现次数与来源期数不一致。"))
        if "来源：WF-" in line and not source_ids:
            issues.append(COMMON.issue("ERROR", "INVALID_CREATIVE_SOURCE", path, f"第 {line_number} 行来源项目编号无效。"))
    return issues


def has_creative_log(readme: Path) -> bool:
    section = COMMON.extract_heading_section(COMMON.read_utf8(readme), "Changelog", 2)
    _, rows = COMMON.parse_markdown_table(section)
    return any(
        row.get("阶段") == "记忆整理"
        and row.get("类型") == "记忆写入"
        and ("大纲" in row.get("决策或变更", "") or "文稿" in row.get("决策或变更", ""))
        for row in rows
    )


def validate_creative_memory(
    repo_root: Path,
    episode_value: str | None = None,
    *,
    require_log: bool = False,
) -> list[COMMON.Issue]:
    repo_root = repo_root.resolve()
    issues: list[COMMON.Issue] = []
    for filename, headings in TARGETS.items():
        path = repo_root / "memories" / filename
        if not path.is_file():
            issues.append(COMMON.issue("ERROR", "MISSING_CREATIVE_MEMORY", path, "缺少创作记忆文件。"))
            continue
        text = COMMON.strip_html_comments(COMMON.read_utf8(path))
        for heading in headings:
            if not re.search(rf"(?m)^##\s+{re.escape(heading)}\s*$", text):
                issues.append(COMMON.issue("ERROR", "MISSING_CREATIVE_HEADING", path, f"缺少章节：{heading}。"))
        issues.extend(validate_source_lines(path, text))

    if episode_value is not None or require_log:
        readme, resolve_issues = COMMON.resolve_episode(repo_root, episode_value)
        issues.extend(resolve_issues)
        if readme is not None:
            issues.extend(COMMON.validate_changelog(readme, require_archive_entry=True))
            if require_log and not has_creative_log(readme):
                issues.append(COMMON.issue("ERROR", "MISSING_CREATIVE_CHANGELOG", readme, "Changelog 缺少创作记忆写入记录。"))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读检查大纲与文稿长期记忆。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="仓库根目录。")
    parser.add_argument("--episode", help="本期真实 README 路径。")
    parser.add_argument("--require-log", action="store_true", help="要求本期 Changelog 存在创作记忆写入记录。")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出问题。")
    args = parser.parse_args(argv)
    issues = validate_creative_memory(args.repo_root, args.episode, require_log=args.require_log)
    if args.json:
        print(json.dumps([asdict(item) for item in issues], ensure_ascii=False, indent=2))
    elif not issues:
        print("OK：大纲与文稿记忆检查通过。")
    else:
        for item in issues:
            print(f"{item.severity} [{item.code}] {item.path}: {item.message}")
    return 1 if any(item.severity == "ERROR" for item in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
