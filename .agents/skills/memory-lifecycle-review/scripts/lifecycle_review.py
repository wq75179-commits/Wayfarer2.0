#!/usr/bin/env python3
"""Aggregate per-episode memory snapshots without changing repository files."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple


EPISODE_ID_RE = re.compile(r"^WF-\d{8}-\d{2}$")
EPISODE_FIELD_RE = re.compile(
    r"^\s*(?:[-*]\s*)?episode_id\s*[:：]\s*(.*?)\s*$", re.IGNORECASE
)
HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SNAPSHOT_HEADING = "本期相关记忆（快照）"
SNAPSHOT_COLUMNS = ("日期", "记忆ID", "阶段", "状态", "本期结果", "依据")
HISTORY_COLUMNS = ("日期", "记忆ID", "原状态", "新状态", "原因", "依据")
STAGES = ("大纲", "文稿", "包装")
STAGE_PREFIX = {"大纲": "OUT", "文稿": "SCR", "包装": "PKG"}
MEMORY_ID_RE = re.compile(r"^(OUT|SCR|PKG)-\d{4}$")
STATUSES = {"候选", "正式", "暂存"}
RESULT_LABELS = {
    "采用",
    "已验证",
    "失败",
    "待验证",
    "无法判断",
    "明确冲突",
    "未采用",
}
RESULT_SPLIT_RE = re.compile(r"[、，,;/；+＋\s]+")
PLACEHOLDERS = {"", "—", "-", "暂无可核验数据", "未进行"}
CONFLICT_PAIRS = (
    {"采用", "未采用"},
    {"已验证", "失败"},
    {"已验证", "明确冲突"},
)
HISTORY_TERMS = ("被替代", "停用", "不再使用", "停止使用")
HISTORY_NEGATION_PREFIXES = (
    "未明确",
    "没有明确",
    "尚未",
    "尚无",
    "从未",
    "并非",
    "并未",
    "不会",
    "无需",
    "无须",
    "没有",
    "无",
    "未",
    "不再",
    "不",
)
LEDGER_FIELD_LABELS = {
    "stage": "阶段",
    "current_status": "当前状态",
    "adoption_periods": "采用期数",
    "result_support_periods": "结果支持期数",
    "result_counterexample_periods": "结果反例期数",
    "observation_periods": "观察期数",
    "involved_periods": "涉及期数",
}


class LifecycleError(Exception):
    """A user-actionable validation or selection error."""


@dataclass(frozen=True)
class Snapshot:
    path: str
    line: int
    episode_id: str
    date: str
    memory_id: str
    stage: str
    status: str
    results: Tuple[str, ...]
    evidence: str


@dataclass(frozen=True)
class Episode:
    path: Path
    relative_path: str
    episode_id: str
    snapshots: Tuple[Snapshot, ...]
    structured: bool
    unstructured_reason: Optional[str] = None


def read_utf8(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise LifecycleError(f"无法按 UTF-8 读取文件：{path}: {error}") from error
    except OSError as error:
        raise LifecycleError(f"无法读取文件：{path}: {error}") from error


def relative_path(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def episode_field_values(lines: Sequence[str]) -> List[Tuple[int, str]]:
    values: List[Tuple[int, str]] = []
    for line_number, line in enumerate(lines, start=1):
        match = EPISODE_FIELD_RE.match(line)
        if match:
            values.append((line_number, match.group(1).strip()))
    return values


def extract_episode_id(lines: Sequence[str], source: str) -> str:
    found = episode_field_values(lines)
    for line_number, value in found:
        if not EPISODE_ID_RE.fullmatch(value):
            raise LifecycleError(
                f"{source}:{line_number} 的 episode_id 格式无效：{value or '空值'}"
            )
    if not found:
        raise LifecycleError(f"{source} 缺少 episode_id")
    if len({value for _, value in found}) != 1 or len(found) > 1:
        locations = "、".join(f"{source}:{line}" for line, _ in found)
        raise LifecycleError(f"{source} 重复填写 episode_id：{locations}")
    return found[0][1]


def _heading(line: str) -> Optional[Tuple[int, str]]:
    match = HEADING_RE.match(line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _section_bounds(lines: Sequence[str], heading_text: str) -> Optional[Tuple[int, int]]:
    matches: List[int] = []
    for index, line in enumerate(lines):
        heading = _heading(line)
        if heading and heading[0] == 2 and heading[1] == heading_text:
            matches.append(index)
    if not matches:
        return None
    if len(matches) > 1:
        locations = "、".join(str(index + 1) for index in matches)
        raise LifecycleError(f"README 中出现多个 ## {heading_text}：第 {locations} 行")
    start = matches[0] + 1
    end = len(lines)
    for index in range(start, len(lines)):
        heading = _heading(lines[index])
        if heading and heading[0] <= 2:
            end = index
            break
    return start, end


def _visible_lines(lines: Sequence[str], start: int, end: int) -> Iterable[Tuple[int, str]]:
    in_comment = False
    for index in range(start, end):
        line = lines[index]
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line:
            if "-->" not in line.split("<!--", 1)[1]:
                in_comment = True
            continue
        yield index + 1, line


def split_table_row(line: str) -> Optional[List[str]]:
    stripped = line.strip()
    if "|" not in stripped:
        return None
    if stripped.startswith("|"):
        stripped = stripped[1:]
    if stripped.endswith("|"):
        stripped = stripped[:-1]
    return [cell.strip() for cell in stripped.split("|")]


def is_separator_row(cells: Sequence[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.strip()) for cell in cells)


def is_placeholder_row(cells: Sequence[str]) -> bool:
    return all(cell.strip() in PLACEHOLDERS for cell in cells)


def is_history_placeholder_row(cells: Sequence[str]) -> bool:
    return (
        len(cells) == len(HISTORY_COLUMNS)
        and all(cell.strip() in {"—", "-"} for cell in cells[:4])
        and cells[4].strip() in {"暂无已确认记录", "暂无记录"}
        and cells[5].strip() in {"—", "-"}
    )


def contains_history_fact(text: str) -> bool:
    compact = re.sub(r"\s+", "", text)
    for term in HISTORY_TERMS:
        for match in re.finditer(re.escape(term), compact):
            prefix = compact[max(0, match.start() - 5) : match.start()]
            if any(prefix.endswith(negation) for negation in HISTORY_NEGATION_PREFIXES):
                continue
            return True
    return False


def canonical_results(raw: str, source: str, line: int) -> Tuple[str, ...]:
    labels = tuple(dict.fromkeys(part.strip() for part in RESULT_SPLIT_RE.split(raw.strip()) if part.strip()))
    if not labels:
        raise LifecycleError(f"{source}:{line} 的本期结果不能为空")
    unknown = [label for label in labels if label not in RESULT_LABELS]
    if unknown:
        raise LifecycleError(f"{source}:{line} 含未知本期结果标签：{'、'.join(unknown)}")
    result_set = set(labels)
    for pair in CONFLICT_PAIRS:
        if pair <= result_set:
            raise LifecycleError(f"{source}:{line} 的本期结果组合矛盾：{'、'.join(pair)}")
    return labels


def parse_snapshot_table(
    lines: Sequence[str], source: str, episode_id: str
) -> Tuple[Tuple[Snapshot, ...], Optional[str]]:
    changelog = _section_bounds(lines, "Changelog")
    if changelog is None:
        return (), "缺少 ## Changelog 或本期快照表"
    start, end = changelog
    snapshot_headings: List[Tuple[int, int]] = []
    for line_number, line in _visible_lines(lines, start, end):
        heading = _heading(line)
        if heading and heading[0] == 3 and heading[1] == SNAPSHOT_HEADING:
            snapshot_headings.append((line_number, line_number - 1))
    if not snapshot_headings:
        return (), "缺少 ### 本期相关记忆（快照）"
    if len(snapshot_headings) > 1:
        locations = "、".join(str(line) for line, _ in snapshot_headings)
        raise LifecycleError(f"{source} 中出现多个本期快照标题：第 {locations} 行")
    heading_line, heading_index = snapshot_headings[0]

    visible = list(_visible_lines(lines, heading_index + 1, end))
    header_position: Optional[int] = None
    header_cells: Optional[List[str]] = None
    for position, (line_number, line) in enumerate(visible):
        cells = split_table_row(line)
        if cells is None:
            continue
        header_position = position
        header_cells = cells
        if tuple(cells) != SNAPSHOT_COLUMNS:
            raise LifecycleError(
                f"{source}:{line_number} 的本期快照表头必须为：{' | '.join(SNAPSHOT_COLUMNS)}"
            )
        break
    if header_position is None or header_cells is None:
        raise LifecycleError(f"{source}:{heading_line} 缺少本期快照六列表格")

    separator_position = header_position + 1
    while separator_position < len(visible) and not visible[separator_position][1].strip():
        separator_position += 1
    if separator_position >= len(visible):
        raise LifecycleError(f"{source}:{visible[header_position][0]} 的快照表缺少分隔行")
    separator_cells = split_table_row(visible[separator_position][1])
    if separator_cells is None or len(separator_cells) != len(SNAPSHOT_COLUMNS) or not is_separator_row(separator_cells):
        raise LifecycleError(f"{source}:{visible[separator_position][0]} 的快照表分隔行无效")

    snapshots: List[Snapshot] = []
    seen_ids: Set[str] = set()
    for line_number, line in visible[separator_position + 1 :]:
        if not line.strip():
            continue
        cells = split_table_row(line)
        if cells is None:
            break
        if is_separator_row(cells):
            continue
        if len(cells) != len(SNAPSHOT_COLUMNS):
            raise LifecycleError(f"{source}:{line_number} 的快照行必须有六列，实际为 {len(cells)} 列")
        if is_placeholder_row(cells) or is_history_placeholder_row(cells):
            continue
        date_text, memory_id, stage, status, result_text, evidence = cells
        try:
            dt.date.fromisoformat(date_text)
        except ValueError as error:
            raise LifecycleError(f"{source}:{line_number} 的日期格式无效：{date_text}") from error
        if not MEMORY_ID_RE.fullmatch(memory_id):
            raise LifecycleError(f"{source}:{line_number} 的记忆ID格式无效：{memory_id}")
        if stage not in STAGES:
            raise LifecycleError(f"{source}:{line_number} 的阶段无效：{stage}")
        if not memory_id.startswith(f"{STAGE_PREFIX[stage]}-"):
            raise LifecycleError(f"{source}:{line_number} 的记忆ID与阶段不匹配：{memory_id} / {stage}")
        if status not in STATUSES:
            raise LifecycleError(f"{source}:{line_number} 的状态无效：{status}")
        results = canonical_results(result_text, source, line_number)
        if evidence.strip() in PLACEHOLDERS:
            raise LifecycleError(f"{source}:{line_number} 的依据不能为空或占位")
        if memory_id in seen_ids:
            raise LifecycleError(f"{source}:{line_number} 的记忆ID在同一 README 中重复：{memory_id}")
        seen_ids.add(memory_id)
        snapshots.append(
            Snapshot(
                path=source,
                line=line_number,
                episode_id=episode_id,
                date=date_text,
                memory_id=memory_id,
                stage=stage,
                status=status,
                results=results,
                evidence=evidence.strip(),
            )
        )
    return tuple(snapshots), None


def project_readmes(repo_root: Path) -> List[Path]:
    project_dir = repo_root / "project"
    if not project_dir.is_dir():
        raise LifecycleError(f"找不到项目目录：{project_dir}")
    paths = []
    for child in sorted(project_dir.iterdir(), key=lambda item: item.name.lower()):
        if not child.is_dir() or child.name.lower() == "example":
            continue
        readme = child / "README.md"
        if readme.is_file():
            paths.append(readme)
    return paths


def parse_episode(path: Path, repo_root: Path) -> Episode:
    source = relative_path(path, repo_root)
    lines = read_utf8(path).splitlines()
    episode_id = extract_episode_id(lines, source)
    snapshots, reason = parse_snapshot_table(lines, source, episode_id)
    if reason is not None:
        reason = f"历史未结构化：{reason}"
    return Episode(path, source, episode_id, snapshots, reason is None, reason)


def load_all_episodes(repo_root: Path) -> List[Episode]:
    episodes: List[Episode] = []
    seen: Dict[str, str] = {}
    for path in project_readmes(repo_root):
        episode = parse_episode(path, repo_root)
        previous = seen.get(episode.episode_id)
        if previous:
            raise LifecycleError(
                f"episode_id 重复：{episode.episode_id}（{previous} 与 {episode.relative_path}）"
            )
        seen[episode.episode_id] = episode.relative_path
        episodes.append(episode)
    return episodes


def select_episodes(repo_root: Path, requested: Sequence[str], scan_all: bool) -> Tuple[List[Episode], str]:
    if scan_all and requested:
        raise LifecycleError("--all 不能与 --episode 同时使用")
    if scan_all:
        return load_all_episodes(repo_root), "全库计数"
    requested_ids = [item.strip() for item in requested if item.strip()]
    if not requested_ids:
        raise LifecycleError("必须指定至少一个 --episode，或显式使用 --all")
    seen_requested: Set[str] = set()
    duplicate_requested: List[str] = []
    for item in requested_ids:
        if item in seen_requested and item not in duplicate_requested:
            duplicate_requested.append(item)
        seen_requested.add(item)
    if duplicate_requested:
        raise LifecycleError(
            f"指定的 episode_id 重复：{'、'.join(duplicate_requested)}；请每期只指定一次"
        )
    invalid = [item for item in requested_ids if not EPISODE_ID_RE.fullmatch(item)]
    if invalid:
        raise LifecycleError(f"指定的 episode_id 格式无效：{'、'.join(invalid)}")
    by_id: Dict[str, Episode] = {}
    for path in project_readmes(repo_root):
        source = relative_path(path, repo_root)
        try:
            lines = read_utf8(path).splitlines()
        except LifecycleError:
            # A broken unselected legacy README must not block scoped review.
            continue
        try:
            episode_id = extract_episode_id(lines, source)
        except LifecycleError:
            raw_values = {value for _, value in episode_field_values(lines)}
            if raw_values.intersection(requested_ids):
                raise
            # An unselected legacy README must not block a scoped review.
            continue
        if episode_id not in requested_ids:
            continue
        episode = parse_episode(path, repo_root)
        previous = by_id.get(episode_id)
        if previous is not None:
            raise LifecycleError(
                f"episode_id 重复：{episode_id}（{previous.relative_path} 与 {episode.relative_path}）"
            )
        by_id[episode_id] = episode
    missing = [item for item in requested_ids if item not in by_id]
    if missing:
        raise LifecycleError(f"找不到指定 episode_id：{'、'.join(missing)}")
    return [by_id[item] for item in requested_ids], "指定范围计数"


def query_script_directory(repo_root: Path) -> Path:
    candidates = (
        repo_root / ".agents" / "skills" / "memory-query" / "scripts",
        Path(__file__).resolve().parents[2] / "memory-query" / "scripts",
    )
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    raise LifecycleError("找不到 memory-query 解析器")


def load_current_memories(repo_root: Path) -> Dict[str, Dict[str, str]]:
    """Read the current stage files through memory-query's strict parser."""

    query_script = query_script_directory(repo_root)
    sys.path.insert(0, str(query_script))
    try:
        import query_memory  # type: ignore

        memories = query_memory.load_memories(repo_root)
    except Exception as error:
        if isinstance(error, LifecycleError):
            raise
        raise LifecycleError(f"阶段记忆校验失败：{error}") from error
    finally:
        try:
            sys.path.remove(str(query_script))
        except ValueError:
            pass
    return {
        memory.memory_id: {
            "stage": memory.stage,
            "status": memory.status,
            "title": memory.title,
            "content": memory.content,
        }
        for memory in memories
    }


def load_ledger_projection(repo_root: Path) -> Optional[Dict[str, object]]:
    """Load the ledger through memory-query only for integrity comparison."""

    path = repo_root / "memories" / "记忆登记簿.md"
    if not path.is_file():
        return None
    query_script = query_script_directory(repo_root)
    sys.path.insert(0, str(query_script))
    try:
        import query_memory  # type: ignore

        return query_memory.load_evidence(repo_root)
    except Exception as error:
        raise LifecycleError(f"登记簿校验失败：{error}") from error
    finally:
        try:
            sys.path.remove(str(query_script))
        except ValueError:
            pass


def compare_ledger(
    report_memories: Sequence[dict],
    current_memories: Dict[str, Dict[str, str]],
    ledger: Optional[Dict[str, object]],
    scope: str,
    memory_ids: Sequence[str] = (),
) -> dict:
    if ledger is None:
        return {"status": "缺失", "mismatches": []}
    if scope != "全库计数":
        return {
            "status": "未比较",
            "mismatches": [],
            "note": "指定范围只展示范围内计数，未与全局登记簿总数比较。",
        }
    mismatches: List[str] = []
    aggregate_by_id = {item["id"]: item for item in report_memories}
    selected_ids = set(memory_ids)
    for memory_id, current in current_memories.items():
        if selected_ids and memory_id not in selected_ids:
            continue
        item = aggregate_by_id.get(memory_id)
        summary = ledger.get(memory_id)
        if summary is None:
            mismatches.append(f"登记簿缺少阶段记忆 {memory_id}")
            continue
        expected = item or {
            "stage": current["stage"],
            "current_status": current["status"],
            "adoption_periods": 0,
            "result_support_periods": 0,
            "result_counterexample_periods": 0,
            "observation_periods": 0,
            "involved_periods": 0,
            "last_reviewed": "—",
        }
        fields = (
            ("stage", current["stage"], summary.stage),
            ("current_status", current["status"], summary.current_status),
            ("adoption_periods", expected["adoption_periods"], summary.adoption_periods),
            ("result_support_periods", expected["result_support_periods"], summary.result_support_periods),
            ("result_counterexample_periods", expected["result_counterexample_periods"], summary.result_counterexample_periods),
            ("observation_periods", expected["observation_periods"], summary.observation_periods),
            ("involved_periods", expected["involved_periods"], summary.involved_periods),
        )
        for field, expected_value, actual_value in fields:
            if expected_value != actual_value:
                field_label = LEDGER_FIELD_LABELS.get(field, field)
                mismatches.append(
                    f"{memory_id} 的{field_label}不一致：快照重建={expected_value}，登记簿={actual_value}"
                )
        expected_date = expected.get("last_reviewed", "—")
        if expected_date != "—" and expected_date != summary.last_reviewed:
            mismatches.append(
                f"{memory_id} 的最近复核日期不一致：快照重建={expected_date}，登记簿={summary.last_reviewed}"
            )
    for memory_id in ledger:
        if selected_ids and memory_id not in selected_ids:
            continue
        if memory_id not in current_memories:
            mismatches.append(f"登记簿包含未在阶段记忆中找到的 {memory_id}")
    return {"status": "一致" if not mismatches else "不一致", "mismatches": mismatches}


def aggregate(episodes: Sequence[Episode], current_memories: Dict[str, Dict[str, str]], memory_ids: Sequence[str]) -> List[dict]:
    by_id: Dict[str, List[Snapshot]] = {}
    for episode in episodes:
        for snapshot in episode.snapshots:
            by_id.setdefault(snapshot.memory_id, []).append(snapshot)
    selected_ids = set(memory_ids)
    if selected_ids:
        by_id = {memory_id: rows for memory_id, rows in by_id.items() if memory_id in selected_ids}

    result: List[dict] = []
    for memory_id in sorted(by_id):
        rows = by_id[memory_id]
        episodes_for = {row.episode_id for row in rows}
        adoption = {row.episode_id for row in rows if "采用" in row.results}
        support = {row.episode_id for row in rows if "已验证" in row.results}
        counterexamples = {
            row.episode_id
            for row in rows
            if "失败" in row.results or "明确冲突" in row.results
        }
        conflicts = {
            row.episode_id for row in rows if "明确冲突" in row.results
        }
        observations = {
            row.episode_id
            for row in rows
            if "待验证" in row.results or "无法判断" in row.results
        }
        current = current_memories.get(memory_id)
        item = {
            "id": memory_id,
            "stage": current["stage"] if current else rows[0].stage,
            "current_status": current["status"] if current else "未找到阶段记忆",
            "adoption_periods": len(adoption),
            "result_support_periods": len(support),
            "result_counterexample_periods": len(counterexamples),
            "observation_periods": len(observations),
            "involved_periods": len(episodes_for),
            "episodes": sorted(episodes_for),
            "adoption_episodes": sorted(adoption),
            "support_episodes": sorted(support),
            "counterexample_episodes": sorted(counterexamples),
            "conflict_episodes": sorted(conflicts),
            "observation_episodes": sorted(observations),
            "last_reviewed": max(row.date for row in rows),
        }
        result.append(item)
    return result


def read_status_history(repo_root: Path) -> List[dict]:
    path = repo_root / "memories" / "记忆登记簿.md"
    if not path.is_file():
        return []
    lines = read_utf8(path).splitlines()
    history_heading = next(
        (index for index, line in enumerate(lines) if line.strip() == "## 状态历史"), None
    )
    if history_heading is None:
        return []
    section_end = len(lines)
    for index in range(history_heading + 1, len(lines)):
        heading = _heading(lines[index])
        if heading and heading[0] <= 2:
            section_end = index
            break
    header_index: Optional[int] = None
    for index in range(history_heading + 1, section_end):
        cells = split_table_row(lines[index])
        if cells is None:
            continue
        header_index = index
        if tuple(cells) != HISTORY_COLUMNS:
            raise LifecycleError(
                f"登记簿状态历史表头必须为：{' | '.join(HISTORY_COLUMNS)}"
            )
        break
    if header_index is None:
        raise LifecycleError("登记簿状态历史缺少表头")
    separator_index = header_index + 1
    while separator_index < section_end and not lines[separator_index].strip():
        separator_index += 1
    separator_cells = (
        split_table_row(lines[separator_index]) if separator_index < section_end else None
    )
    if separator_cells is None or len(separator_cells) != len(HISTORY_COLUMNS) or not is_separator_row(separator_cells):
        raise LifecycleError("登记簿状态历史分隔行无效")

    rows: List[dict] = []
    for index in range(separator_index + 1, section_end):
        cells = split_table_row(lines[index])
        if cells is None:
            if lines[index].strip():
                raise LifecycleError(
                    f"登记簿状态历史第 {index + 1} 行必须是六列表格"
                )
            continue
        if is_separator_row(cells):
            continue
        if len(cells) != len(HISTORY_COLUMNS):
            raise LifecycleError(f"登记簿状态历史第 {index + 1} 行必须有六列")
        if is_placeholder_row(cells) or is_history_placeholder_row(cells):
            continue
        date_text, memory_id, from_status, to_status, reason, evidence = cells
        try:
            dt.date.fromisoformat(date_text)
        except ValueError as error:
            raise LifecycleError(f"登记簿状态历史第 {index + 1} 行日期无效：{date_text}") from error
        if not MEMORY_ID_RE.fullmatch(memory_id):
            raise LifecycleError(f"登记簿状态历史第 {index + 1} 行记忆ID无效：{memory_id}")
        if from_status not in STATUSES or to_status not in STATUSES or from_status == to_status:
            raise LifecycleError(f"登记簿状态历史第 {index + 1} 行状态变化无效：{from_status} → {to_status}")
        if reason in PLACEHOLDERS or evidence in PLACEHOLDERS:
            raise LifecycleError(f"登记簿状态历史第 {index + 1} 行原因和依据不能为空")
        rows.append(
            {
                "date": date_text,
                "id": memory_id,
                "from": from_status,
                "to": to_status,
                "reason": reason,
                "evidence": evidence,
            }
        )
    return rows


def build_applications(
    aggregates: Sequence[dict],
    scope: str,
    status_history: Sequence[dict],
    reobserve_memory_ids: Sequence[str] = (),
) -> List[dict]:
    applications: List[dict] = []
    history_by_id: Dict[str, List[dict]] = {}
    reobserve_ids = set(reobserve_memory_ids)
    for row in status_history:
        history_by_id.setdefault(row["id"], []).append(row)
    for item in aggregates:
        if item["current_status"] == "候选" and item["adoption_periods"] >= 3:
            applications.append(
                {
                    "id": item["id"],
                    "from": "候选",
                    "to": "正式",
                    "reason": (
                        "在本次统计范围内已被三个不同 episode 采用；"
                        f"采用期数为 {item['adoption_periods']}，"
                        f"结果支持期数为 {item['result_support_periods']}，"
                        f"结果反例期数为 {item['result_counterexample_periods']}，"
                        f"观察期数为 {item['observation_periods']}；"
                        "采用次数与效果支持次数分开列示。"
                    ),
                    "evidence": item["adoption_episodes"],
                    "scope": scope,
                }
            )
        explicit_conflict = bool(item["conflict_episodes"])
        history_reason = any(
            contains_history_fact(f"{row['reason']} {row['evidence']}")
            for row in history_by_id.get(item["id"], [])
        )
        if item["current_status"] == "正式" and (explicit_conflict or history_reason):
            reasons = []
            if explicit_conflict:
                reasons.append("快照包含明确冲突")
            if history_reason:
                reasons.append("登记簿状态历史记录了被替代或停用事实")
            evidence = list(item["conflict_episodes"])
            if history_reason:
                evidence.extend(
                    "登记簿状态历史：{date}，{reason}，依据：{evidence}".format(
                        date=row["date"], reason=row["reason"], evidence=row["evidence"]
                    )
                    for row in history_by_id.get(item["id"], [])
                    if contains_history_fact(f"{row['reason']} {row['evidence']}")
                )
            applications.append(
                {
                    "id": item["id"],
                    "from": "正式",
                    "to": "暂存",
                    "reason": "；".join(reasons),
                    "evidence": evidence,
                    "scope": scope,
                }
            )
        if item["current_status"] == "暂存" and item["id"] in reobserve_ids:
            applications.append(
                {
                    "id": item["id"],
                    "from": "暂存",
                    "to": "候选",
                    "reason": "用户明确要求重新观察；本申请只恢复候选状态，不改写历史快照。",
                    "evidence": item["episodes"] or ["用户明确要求重新观察"],
                    "scope": scope,
                }
            )
    return applications


def build_report(
    repo_root: Path,
    requested: Sequence[str] = (),
    scan_all: bool = False,
    memory_ids: Sequence[str] = (),
    reobserve_memory_ids: Sequence[str] = (),
) -> dict:
    invalid_memory_ids = [
        item
        for item in (*memory_ids, *reobserve_memory_ids)
        if not MEMORY_ID_RE.fullmatch(item)
    ]
    if invalid_memory_ids:
        raise LifecycleError(f"指定的记忆ID格式无效：{'、'.join(invalid_memory_ids)}")
    episodes, scope = select_episodes(repo_root, requested, scan_all)
    current = load_current_memories(repo_root)
    aggregates = aggregate(episodes, current, memory_ids)
    unstructured = [
        {"path": episode.relative_path, "episode_id": episode.episode_id, "reason": episode.unstructured_reason}
        for episode in episodes
        if not episode.structured
    ]
    warnings: List[str] = []
    for episode in episodes:
        for snapshot in episode.snapshots:
            current_memory = current.get(snapshot.memory_id)
            if current_memory is None:
                warnings.append(
                    f"快照 {episode.episode_id} 的 {snapshot.memory_id} 未在三份阶段记忆中找到。"
                )
            elif current_memory["stage"] != snapshot.stage:
                warnings.append(
                    f"{snapshot.memory_id} 的阶段不一致：快照为 {snapshot.stage}，当前阶段记忆为 {current_memory['stage']}。"
                )
    ledger_path = repo_root / "memories" / "记忆登记簿.md"
    if not ledger_path.is_file():
        warnings.append("缺少 memories/记忆登记簿.md；统计仍以 README 快照为准，但登记簿证据不完整。")
    ledger = load_ledger_projection(repo_root)
    ledger_check = compare_ledger(aggregates, current, ledger, scope, memory_ids)
    if ledger_check["status"] == "不一致":
        warnings.extend(ledger_check["mismatches"])
    elif ledger_check["status"] == "未比较":
        warnings.append(ledger_check["note"])
    elif ledger_check["status"] == "缺失" and ledger_path.is_file():
        warnings.append("登记簿存在但无法读取索引；统计仍以 README 快照为准。")
    history = read_status_history(repo_root)
    applications = build_applications(aggregates, scope, history, reobserve_memory_ids)
    return {
        "scope": scope,
        "episodes": [episode.episode_id for episode in episodes],
        "memories": aggregates,
        "unstructured": unstructured,
        "applications": applications,
        "warnings": warnings,
        "ledger_check": ledger_check,
        "read_only": True,
    }


def render_markdown(report: dict) -> str:
    lines = [
        "# 记忆生命周期复核",
        "",
        f"- 统计范围：{report['scope']}（{ '、'.join(report['episodes']) or '无' }）",
        "- 文件变更：无（本报告为只读统计）",
        "",
        "## 记忆统计",
        "",
        "| 记忆ID | 阶段 | 当前状态 | 采用期数 | 结果支持期数 | 结果反例期数 | 观察期数 | 涉及期数 | 涉及 episode | 最近复核日期 |",
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    if report["memories"]:
        for item in report["memories"]:
            lines.append(
                f"| {item['id']} | {item['stage']} | {item['current_status']} | {item['adoption_periods']} | {item['result_support_periods']} | {item['result_counterexample_periods']} | {item['observation_periods']} | {item['involved_periods']} | {'、'.join(item['episodes'])} | {item['last_reviewed']} |"
            )
    else:
        lines.append("| — | — | — | 0 | 0 | 0 | 0 | 0 | — | — |")
    lines.extend(["", "## 状态申请", ""])
    if report["applications"]:
        for application in report["applications"]:
            evidence = "；".join(application["evidence"]) or "无"
            lines.append(
                f"- `{application['id']}`：{application['from']} → {application['to']}；{application['reason']}；依据：{evidence}。"
            )
    else:
        lines.append("本次没有满足规则的状态申请。")
    lines.extend(["", "## 未结构化与警告", ""])
    if report["unstructured"]:
        for item in report["unstructured"]:
            lines.append(f"- `{item['path']}`（{item['episode_id']}）：{item['reason']}。")
    else:
        lines.append("没有发现未结构化的指定项目。")
    for warning in report["warnings"]:
        lines.append(f"- {warning}")
    ledger_status = report["ledger_check"]["status"]
    lines.append(f"- 登记簿一致性检查：{ledger_status}。")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按 episode 汇总记忆快照，不修改文件。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--episode", action="append", default=[], help="要处理的 episode_id，可重复指定")
    parser.add_argument("--all", action="store_true", help="显式扫描全部真实项目")
    parser.add_argument("--memory-id", action="append", default=[], help="只输出指定记忆ID，可重复指定")
    parser.add_argument(
        "--reobserve-memory-id",
        action="append",
        default=[],
        help="用户明确要求重新观察的暂存记忆ID，只生成暂存→候选申请",
    )
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        report = build_report(
            args.repo_root.resolve(),
            args.episode,
            args.all,
            args.memory_id,
            args.reobserve_memory_id,
        )
        if args.format == "json":
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(report), end="")
        return 0
    except LifecycleError as error:
        print(f"memory-lifecycle-review 复核停止：{error}", file=sys.stderr)
        return 2
    except OSError as error:
        print(f"memory-lifecycle-review 复核停止：无法访问文件：{error}", file=sys.stderr)
        return 2
    except Exception as error:  # Fail closed; never silently skip malformed evidence.
        print(f"memory-lifecycle-review 复核停止：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
