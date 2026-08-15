#!/usr/bin/env python3
"""Validate episode README facts and the derived long-term memory index.

This program is intentionally read-only. It does not create summaries, infer
conclusions, modify Markdown, or access the network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable


EPISODE_ID_PATTERN = re.compile(r"^WF-\d{8}-\d{2}$")
EPISODE_ID_IN_TEXT = re.compile(r"WF-\d{8}-\d{2}")
FIELD_PATTERN = re.compile(r"(?m)^[ \t]*-[ \t]*([^:\n：]+?)[ \t]*[：:][ \t]*(.*?)[ \t]*$")
PLACEHOLDER_VALUES = {"", "—", "-", "暂无", "暂无可核验数据", "n/a", "N/A"}
ARCHIVED_RESULTS = {"已发布", "未发布", "取消", "暂停"}
CONCLUSION_STATES = {"已验证", "待验证", "失败", "无法判断"}
CIRCLES = {"第一圈", "第二圈", "第三圈"}
CONTENT_TYPES = {"原创", "再创作"}
CONFIRMATION_NODES = ("选题", "简要架构", "资料补全", "写作大纲", "口播文稿", "发布物料", "归档")
MEMORY_REQUIRED_FIELDS = (
    "README",
    "最终标题",
    "发布日期",
    "归档日期",
    "归档结果",
    "一句话选题",
    "切入角度",
    "受众圈层",
    "内容类型",
    "核心承诺",
    "关键确认",
    "重大决策摘要",
    "发布摘要",
    "指标摘要",
    "结论状态",
    "已验证做法",
    "失败或限制",
    "待验证假设",
    "下一期验证动作",
)


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


@dataclass
class Episode:
    path: Path
    fields: dict[str, str]
    confirmations: dict[str, dict[str, str]]
    data_rows: list[dict[str, str]]

    @property
    def episode_id(self) -> str:
        return self.fields.get("episode_id", "").strip()

    @property
    def is_archived(self) -> bool:
        return self.fields.get("当前状态", "").strip() == "归档"


@dataclass
class MemoryEntry:
    episode_id: str
    fields: dict[str, str]
    link_target: str


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() in PLACEHOLDER_VALUES


def normalize(value: str | None) -> str:
    return "" if value is None else value.strip()


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def extract_heading_section(text: str, title: str, level: int) -> str:
    """Return content under an exact heading until a heading at the same/higher level."""
    pattern = re.compile(rf"(?m)^{'#' * level}\s+{re.escape(title)}\s*$")
    match = pattern.search(text)
    if match is None:
        return ""

    tail = text[match.end() :]
    next_heading = re.search(rf"(?m)^#{{1,{level}}}\s+", tail)
    return tail[: next_heading.start()] if next_heading else tail


def extract_fields(text: str) -> dict[str, str]:
    return {match.group(1).strip(): match.group(2).strip() for match in FIELD_PATTERN.finditer(text)}


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def parse_markdown_table(text: str) -> list[dict[str, str]]:
    header: list[str] | None = None
    rows: list[dict[str, str]] = []

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        if is_separator_row(cells):
            continue
        if header is None:
            header = cells
            continue
        if len(cells) != len(header):
            continue
        rows.append(dict(zip(header, cells)))

    return rows


def parse_episode(path: Path) -> Episode:
    text = read_utf8(path)
    return Episode(
        path=path,
        fields=extract_fields(text),
        confirmations={
            row.get("节点", "").strip(): row
            for row in parse_markdown_table(extract_heading_section(text, "创作确认", 2))
            if row.get("节点", "").strip()
        },
        data_rows=parse_markdown_table(extract_heading_section(text, "数据记录", 3)),
    )


def parse_memory_entries(text: str) -> list[MemoryEntry]:
    index_section = extract_heading_section(text, "影片索引", 2)
    headings = list(re.finditer(r"(?m)^###\s+(.+?)\s*$", index_section))
    entries: list[MemoryEntry] = []

    for index, heading in enumerate(headings):
        start = heading.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(index_section)
        block = index_section[start:end]
        fields = extract_fields(block)
        readme_value = fields.get("README", "")
        link_match = re.search(r"\[[^\]]+\]\(([^)]+)\)", readme_value)
        entries.append(
            MemoryEntry(
                episode_id=heading.group(1).strip(),
                fields=fields,
                link_target=link_match.group(1).strip() if link_match else "",
            )
        )

    return entries


def parse_summary(value: str) -> dict[str, str]:
    pairs: dict[str, str] = {}
    for part in re.split(r"[；;]", value):
        if "=" not in part:
            continue
        key, item_value = part.split("=", 1)
        pairs[key.strip()] = item_value.strip()
    return pairs


def discover_episode_readmes(repo_root: Path) -> list[Path]:
    project_dir = repo_root / "project"
    if not project_dir.is_dir():
        return []
    return sorted(
        path
        for path in project_dir.glob("*/README.md")
        if path.parent.name != "example"
    )


def issue(severity: str, code: str, path: Path | str, message: str) -> Issue:
    return Issue(severity=severity, code=code, path=str(path), message=message)


def validate_episode_shape(episode: Episode) -> list[Issue]:
    issues: list[Issue] = []
    path = episode.path
    fields = episode.fields
    episode_id = episode.episode_id

    if not EPISODE_ID_PATTERN.fullmatch(episode_id):
        issues.append(issue("ERROR", "INVALID_EPISODE_ID", path, "episode_id 必须匹配 WF-YYYYMMDD-NN。"))

    required_identity_fields = ("创建日期", "选题", "切入角度", "受众圈层", "内容类型", "核心承诺", "当前状态")
    for field in required_identity_fields:
        if is_blank(fields.get(field)):
            issues.append(issue("ERROR", "MISSING_REQUIRED_FIELD", path, f"缺少基础信息字段：{field}。"))

    if not is_blank(fields.get("受众圈层")) and normalize(fields.get("受众圈层")) not in CIRCLES:
        issues.append(issue("ERROR", "INVALID_CIRCLE", path, "受众圈层只能是第一圈、第二圈或第三圈。"))
    if not is_blank(fields.get("内容类型")) and normalize(fields.get("内容类型")) not in CONTENT_TYPES:
        issues.append(issue("ERROR", "INVALID_CONTENT_TYPE", path, "内容类型只能是原创或再创作。"))

    if not episode.is_archived:
        issues.append(issue("WARNING", "SKIP_NOT_ARCHIVED", path, "当前状态不是归档，本次不会同步此 README。"))
        return issues

    for node in CONFIRMATION_NODES:
        if node not in episode.confirmations:
            issues.append(issue("ERROR", "MISSING_CONFIRMATION_NODE", path, f"创作确认表缺少节点：{node}。"))

    archive_confirmation = episode.confirmations.get("归档", {})
    if normalize(archive_confirmation.get("状态")) != "已确认":
        issues.append(issue("ERROR", "ARCHIVE_NOT_CONFIRMED", path, "归档节点必须为已确认。"))
    if is_blank(archive_confirmation.get("确认日期")):
        issues.append(issue("ERROR", "MISSING_ARCHIVE_DATE", path, "归档节点缺少确认日期。"))

    archive_result = normalize(fields.get("归档结果"))
    if archive_result not in ARCHIVED_RESULTS:
        issues.append(issue("ERROR", "INVALID_ARCHIVE_RESULT", path, "归档结果必须是已发布、未发布、取消或暂停。"))
    elif archive_result == "已发布":
        for field in ("最终标题", "发布平台", "视频链接", "发布时间", "视频时长"):
            if is_blank(fields.get(field)):
                issues.append(issue("ERROR", "MISSING_PUBLISH_FIELD", path, f"已发布影片缺少字段：{field}。"))
    else:
        for field in ("终局原因", "下一次复核动作"):
            if is_blank(fields.get(field)):
                issues.append(issue("ERROR", "MISSING_TERMINAL_FIELD", path, f"{archive_result}影片缺少字段：{field}。"))

    analysis_fields = ("分析复核日期", "现象", "证据", "限制/原因", "结论", "结论状态", "下一期验证动作")
    for field in analysis_fields:
        if is_blank(fields.get(field)):
            issues.append(issue("ERROR", "MISSING_ANALYSIS_FIELD", path, f"数据分析缺少字段：{field}。"))

    conclusion_state = normalize(fields.get("结论状态"))
    if not is_blank(conclusion_state) and conclusion_state not in CONCLUSION_STATES:
        issues.append(issue("ERROR", "INVALID_CONCLUSION_STATE", path, "结论状态只能是已验证、待验证、失败或无法判断。"))
    if conclusion_state == "已验证" and is_blank(fields.get("可复用经验")):
        issues.append(issue("ERROR", "MISSING_REUSABLE_LESSON", path, "已验证结论必须填写可复用经验。"))
    if conclusion_state == "失败" and is_blank(fields.get("可复用经验")):
        issues.append(issue("ERROR", "MISSING_FAILURE_LESSON", path, "失败结论必须填写可复用经验。"))
    if conclusion_state == "待验证" and is_blank(fields.get("待验证假设")):
        issues.append(issue("ERROR", "MISSING_HYPOTHESIS", path, "待验证结论必须填写待验证假设。"))

    for row_number, row in enumerate(episode.data_rows, start=1):
        if normalize(row.get("指标")) == "暂无可核验数据":
            continue
        for column in ("采集日期", "统计周期", "来源", "平台", "指标", "数值"):
            if is_blank(row.get(column)):
                issues.append(
                    issue("ERROR", "INVALID_DATA_RECORD", path, f"数据记录第 {row_number} 行缺少列：{column}。")
                )

    return issues


def validate_memory_entry(
    entry: MemoryEntry,
    memory_path: Path,
    repo_root: Path,
    episodes_by_id: dict[str, Episode],
) -> list[Issue]:
    issues: list[Issue] = []
    entry_path = f"{memory_path}::{entry.episode_id}"

    if not EPISODE_ID_PATTERN.fullmatch(entry.episode_id):
        issues.append(issue("ERROR", "INVALID_MEMORY_EPISODE_ID", entry_path, "影片索引标题必须是合法 episode_id。"))

    for field in MEMORY_REQUIRED_FIELDS:
        if field not in entry.fields:
            issues.append(issue("ERROR", "MISSING_MEMORY_FIELD", entry_path, f"影片索引缺少字段：{field}。"))

    if not entry.link_target:
        issues.append(issue("ERROR", "MISSING_README_LINK", entry_path, "README 字段必须包含 Markdown 链接。"))
    else:
        resolved_link = (memory_path.parent / entry.link_target).resolve()
        try:
            resolved_link.relative_to(repo_root.resolve())
        except ValueError:
            issues.append(issue("ERROR", "README_LINK_OUTSIDE_REPO", entry_path, "README 链接不得指向仓库外。"))
        if not resolved_link.is_file():
            issues.append(issue("ERROR", "BROKEN_README_LINK", entry_path, "README 链接目标不存在。"))

    source = episodes_by_id.get(entry.episode_id)
    if source is None:
        issues.append(issue("WARNING", "ORPHAN_MEMORY_ENTRY", entry_path, "找不到同 episode_id 的项目 README，不自动删除。"))
        return issues

    expected_link = f"../project/{source.path.parent.name}/README.md"
    if entry.link_target.replace("\\", "/") != expected_link:
        issues.append(issue("ERROR", "NONCANONICAL_README_LINK", entry_path, f"README 链接必须为 {expected_link}。"))

    published = normalize(source.fields.get("归档结果")) == "已发布"
    expected_archive_date = normalize(source.confirmations.get("归档", {}).get("确认日期"))
    if normalize(entry.fields.get("归档日期")) != expected_archive_date:
        issues.append(issue("ERROR", "ARCHIVE_DATE_MISMATCH", entry_path, "归档日期必须与 README 的归档确认日期一致。"))

    authority_mapping = {
        "最终标题": "最终标题",
        "发布日期": "发布时间",
        "归档结果": "归档结果",
        "一句话选题": "选题",
        "切入角度": "切入角度",
        "受众圈层": "受众圈层",
        "内容类型": "内容类型",
        "核心承诺": "核心承诺",
        "结论状态": "结论状态",
        "下一期验证动作": "下一期验证动作",
    }
    for memory_field, readme_field in authority_mapping.items():
        memory_value = normalize(entry.fields.get(memory_field))
        source_value = normalize(source.fields.get(readme_field))
        expected_value = "未发布" if memory_field == "发布日期" and not published else source_value
        if memory_value != expected_value:
            issues.append(
                issue(
                    "ERROR",
                    "AUTHORITY_FIELD_MISMATCH",
                    entry_path,
                    f"{memory_field} 必须与 README 的 {readme_field} 对应值一致。",
                )
            )

    summary = parse_summary(entry.fields.get("发布摘要", ""))
    if published:
        for summary_key, readme_field in (("平台", "发布平台"), ("链接", "视频链接"), ("时长", "视频时长"), ("表现等级", "表现等级")):
            if summary.get(summary_key) != normalize(source.fields.get(readme_field)):
                issues.append(
                    issue(
                        "ERROR",
                        "PUBLISH_SUMMARY_MISMATCH",
                        entry_path,
                        f"发布摘要中的 {summary_key} 必须与 README 的 {readme_field} 一致。",
                    )
                )
    elif normalize(entry.fields.get("发布摘要")) != "未发布":
        issues.append(issue("ERROR", "INVALID_UNPUBLISHED_SUMMARY", entry_path, "未发布条目的发布摘要必须为未发布。"))

    metric_summary = normalize(entry.fields.get("指标摘要"))
    if not published:
        if metric_summary != "无（未发布）":
            issues.append(issue("ERROR", "INVALID_UNPUBLISHED_METRIC", entry_path, "未发布条目的指标摘要必须为无（未发布）。"))
    elif "统计周期=" not in metric_summary or "来源=" not in metric_summary:
        issues.append(issue("ERROR", "UNLABELED_METRIC_SUMMARY", entry_path, "指标摘要必须包含统计周期= 和 来源=。"))
    else:
        metric_fields = parse_summary(metric_summary)
        summarized_metrics = {
            key: value
            for key, value in metric_fields.items()
            if key not in {"统计周期", "来源"}
        }
        matches_source_data = any(
            normalize(row.get("统计周期")) == metric_fields.get("统计周期")
            and normalize(row.get("来源")) == metric_fields.get("来源")
            and all(
                normalize(row.get("指标")) == metric_name and normalize(row.get("数值")) == metric_value
                for metric_name, metric_value in summarized_metrics.items()
            )
            for row in source.data_rows
        )
        if not summarized_metrics or not matches_source_data:
            issues.append(issue("ERROR", "METRIC_SUMMARY_NOT_IN_SOURCE", entry_path, "指标摘要必须回溯到 README 中同周期、同来源的原始数据记录。"))

    return issues


def index_bullets(text: str, heading: str) -> list[str]:
    section = extract_heading_section(text, heading, 2)
    return [
        line.strip()[1:].strip()
        for line in section.splitlines()
        if line.strip().startswith("-") and "暂无" not in line
    ]


def validate_derived_indexes(text: str, memory_path: Path, entries_by_id: dict[str, MemoryEntry]) -> list[Issue]:
    issues: list[Issue] = []
    expected_states = {
        "已验证经验索引": {"已验证", "失败"},
        "待验证队列": {"待验证"},
    }

    for heading, allowed_states in expected_states.items():
        for bullet in index_bullets(text, heading):
            source_ids = EPISODE_ID_IN_TEXT.findall(bullet)
            if not source_ids:
                issues.append(issue("ERROR", "MISSING_INDEX_SOURCE", memory_path, f"{heading}中的条目缺少来源 episode_id。"))
                continue
            for source_id in source_ids:
                source_entry = entries_by_id.get(source_id)
                if source_entry is None:
                    issues.append(issue("ERROR", "UNKNOWN_INDEX_SOURCE", memory_path, f"{heading}引用了不存在的 {source_id}。"))
                    continue
                if normalize(source_entry.fields.get("结论状态")) not in allowed_states:
                    issues.append(
                        issue(
                            "ERROR",
                            "INVALID_INDEX_STATE",
                            memory_path,
                            f"{heading}不能引用结论状态为 {source_entry.fields.get('结论状态', '缺失')} 的 {source_id}。",
                        )
                    )
    return issues


def parse_datetime(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d %H:%M")
    except ValueError:
        return None


def validate_quota(text: str, memory_path: Path, entries: Iterable[MemoryEntry]) -> list[Issue]:
    issues: list[Issue] = []
    published: list[tuple[datetime, MemoryEntry]] = []

    for entry in entries:
        if normalize(entry.fields.get("归档结果")) != "已发布":
            continue
        published_at = parse_datetime(normalize(entry.fields.get("发布日期")))
        if published_at is None:
            issues.append(issue("ERROR", "INVALID_PUBLISH_DATETIME", f"{memory_path}::{entry.episode_id}", "发布日期必须为 YYYY-MM-DD HH:mm。"))
            continue
        circle = normalize(entry.fields.get("受众圈层"))
        if circle not in CIRCLES:
            issues.append(issue("ERROR", "INVALID_MEMORY_CIRCLE", f"{memory_path}::{entry.episode_id}", "已发布条目的受众圈层无效。"))
            continue
        published.append((published_at, entry))

    latest_ten = [entry for _, entry in sorted(published, key=lambda item: item[0], reverse=True)[:10]]
    counts = Counter(normalize(entry.fields.get("受众圈层")) for entry in latest_ten)
    quota_fields = extract_fields(extract_heading_section(text, "圈层配额（最近 10 期已发布）", 2))

    sample_match = re.fullmatch(r"(\d+)\s*/\s*10", normalize(quota_fields.get("样本数")))
    expected_values = {
        "第一圈": counts["第一圈"],
        "第二圈": counts["第二圈"],
        "第三圈": counts["第三圈"],
    }

    if sample_match is None or int(sample_match.group(1)) != len(latest_ten):
        issues.append(issue("ERROR", "QUOTA_SAMPLE_MISMATCH", memory_path, "圈层配额的样本数必须等于最近十期已发布影片数。"))

    for circle, expected in expected_values.items():
        actual_match = re.match(r"(\d+)", normalize(quota_fields.get(circle)))
        if actual_match is None or int(actual_match.group(1)) != expected:
            issues.append(issue("ERROR", "QUOTA_COUNT_MISMATCH", memory_path, f"圈层配额中的{circle}数量与影片索引不一致。"))

    return issues


def validate_repository(repo_root: Path, memory_path: Path | None = None) -> list[Issue]:
    repo_root = repo_root.resolve()
    issues: list[Issue] = []
    readme_paths = discover_episode_readmes(repo_root)
    episodes: list[Episode] = []

    for path in readme_paths:
        try:
            episode = parse_episode(path)
        except (OSError, UnicodeError) as error:
            issues.append(issue("ERROR", "UNREADABLE_README", path, str(error)))
            continue
        episodes.append(episode)
        issues.extend(validate_episode_shape(episode))

    episodes_by_id: dict[str, Episode] = {}
    duplicates: dict[str, list[Episode]] = defaultdict(list)
    for episode in episodes:
        if EPISODE_ID_PATTERN.fullmatch(episode.episode_id):
            duplicates[episode.episode_id].append(episode)
    for episode_id, matching_episodes in duplicates.items():
        if len(matching_episodes) > 1:
            paths = ", ".join(str(item.path) for item in matching_episodes)
            issues.append(issue("ERROR", "DUPLICATE_EPISODE_ID", repo_root, f"{episode_id} 同时出现在多个 README：{paths}"))
        else:
            episodes_by_id[episode_id] = matching_episodes[0]

    target_memory = memory_path or repo_root / "memories" / "往期影片信息记录.md"
    if not target_memory.is_file():
        issues.append(issue("ERROR", "MISSING_MEMORY_FILE", target_memory, "找不到长期记忆文件。"))
        return issues

    try:
        memory_text = read_utf8(target_memory)
    except (OSError, UnicodeError) as error:
        issues.append(issue("ERROR", "UNREADABLE_MEMORY_FILE", target_memory, str(error)))
        return issues

    if normalize(extract_fields(memory_text).get("schema_version")) != "1":
        issues.append(issue("ERROR", "INVALID_SCHEMA_VERSION", target_memory, "schema_version 必须为 1。"))

    entries = parse_memory_entries(memory_text)
    entries_by_id: dict[str, MemoryEntry] = {}
    seen_entry_ids: Counter[str] = Counter(entry.episode_id for entry in entries)
    for entry in entries:
        if seen_entry_ids[entry.episode_id] > 1:
            issues.append(issue("ERROR", "DUPLICATE_MEMORY_EPISODE_ID", target_memory, f"影片索引重复出现 {entry.episode_id}。"))
            continue
        entries_by_id[entry.episode_id] = entry
        issues.extend(validate_memory_entry(entry, target_memory, repo_root, episodes_by_id))

    for episode in episodes:
        if episode.is_archived and EPISODE_ID_PATTERN.fullmatch(episode.episode_id) and episode.episode_id not in entries_by_id:
            issues.append(issue("WARNING", "MEMORY_NOT_SYNCED", episode.path, "已归档 README 尚未同步到长期记忆。"))

    issues.extend(validate_derived_indexes(memory_text, target_memory, entries_by_id))
    issues.extend(validate_quota(memory_text, target_memory, entries))
    return issues


def issue_to_dict(item: Issue) -> dict[str, str]:
    return asdict(item)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读校验单期 README 与长期记忆索引的一致性。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="包含 project/ 与 memories/ 的仓库根目录。")
    parser.add_argument("--memory", type=Path, help="替代默认长期记忆文件路径。")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出校验问题。")
    args = parser.parse_args(argv)

    issues = validate_repository(args.repo_root, args.memory)
    if args.json:
        print(json.dumps([issue_to_dict(item) for item in issues], ensure_ascii=False, indent=2))
    elif not issues:
        print("OK：未发现结构性问题。")
    else:
        for item in issues:
            print(f"{item.severity} [{item.code}] {item.path}: {item.message}")

    return 1 if any(item.severity == "ERROR" for item in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())