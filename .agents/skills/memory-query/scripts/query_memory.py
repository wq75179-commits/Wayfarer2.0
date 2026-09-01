#!/usr/bin/env python3
"""Read-only query for the channel's small, shared memory collection.

The script deliberately keeps the query surface narrow: a stage and an
optional status.  It never writes to the repository and it never changes a
memory's state.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Sequence, Tuple


STAGE_ALIASES = {
    "大纲": "大纲",
    "写作大纲": "大纲",
    "outline": "大纲",
    "outline-drafting": "大纲",
    "阶段4": "大纲",
    "文稿": "文稿",
    "口播文稿": "文稿",
    "script": "文稿",
    "阶段5": "文稿",
    "包装": "包装",
    "发布物料": "包装",
    "packaging": "包装",
    "阶段6": "包装",
}

STATUS_ALIASES = {
    "候选": "候选",
    "候选记忆": "候选",
    "candidate": "候选",
    "正式": "正式",
    "正式记忆": "正式",
    "confirmed": "正式",
    "暂存": "暂存",
    "暂存记忆": "暂存",
    "staged": "暂存",
    "废弃": "暂存",
    "已废弃": "暂存",
}

DEFAULT_STATUSES = ("候选", "正式")
FIELD_PATTERNS = {
    "stage": re.compile(r"^\s*(?:[-*]\s*)?阶段\s*[:：]\s*(.*?)\s*$"),
    "status": re.compile(r"^\s*(?:[-*]\s*)?状态\s*[:：]\s*(.*?)\s*$"),
    "content": re.compile(r"^\s*(?:[-*]\s*)?内容\s*[:：]\s*(.*?)\s*$"),
}

CONTROLLED_ID_RE = re.compile(r"^(?:OUT|SCR|PKG)-\d{4}$")
ID_LIKE_RE = re.compile(r"^[A-Za-z]{1,12}-\d+$")
STAGE_ID_PREFIX = {"大纲": "OUT", "文稿": "SCR", "包装": "PKG"}
MEMORY_FILES = {
    "大纲记忆.md": "大纲",
    "文稿记忆.md": "文稿",
    "包装记忆.md": "包装",
}
HEADING_RE = re.compile(r"^(#{2,6})[ \t]+(.+?)\s*$")
CONTROLLED_HEADING_RE = re.compile(
    r"^(?P<id>(?!(?:D|EP)\d+$)[A-Za-z][A-Za-z0-9_-]{1,63})\s*[|｜:：]\s*(?P<title>.+?)\s*$"
)


class QueryError(Exception):
    """An expected, user-actionable query failure."""

    def __init__(self, message: str, code: int = 2) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class Memory:
    memory_id: str
    title: str
    stage: str
    status: str
    content: str
    source: str
    line: int


@dataclass(frozen=True)
class Heading:
    level: int
    title: str
    line: int
    explicit_id: Optional[str]
    explicit_title: Optional[str]


def clean_value(value: str) -> str:
    """Remove presentation marks that commonly surround a field value."""

    value = value.strip()
    value = re.sub(r"^\*+|\*+$", "", value).strip()
    return value


def split_values(value: str) -> List[str]:
    return [part.strip() for part in re.split(r"[,，、/|｜]+", value) if part.strip()]


def canonical_stage(value: str) -> str:
    value = clean_value(value).lower() if value.isascii() else clean_value(value)
    if value not in STAGE_ALIASES:
        raise QueryError(f"无法识别阶段：{value}")
    return STAGE_ALIASES[value]


def canonical_status(value: str) -> str:
    value = clean_value(value).lower() if value.isascii() else clean_value(value)
    if value in {"全部", "所有", "all"}:
        return "全部"
    if value not in STATUS_ALIASES:
        raise QueryError(f"无法识别状态：{value}")
    return STATUS_ALIASES[value]


def parse_stage_value(value: str, source: str, line: int) -> str:
    values = split_values(value)
    if not values:
        raise QueryError(f"{source}:{line} 的阶段不能为空")
    if len(values) != 1:
        raise QueryError(f"{source}:{line} 的记忆只能属于一个阶段")
    return canonical_stage(values[0])


def parse_status_value(value: str, source: str, line: int) -> str:
    status = canonical_status(value)
    if status == "全部":
        raise QueryError(f"{source}:{line} 的状态不能写成全部")
    return status


def heading_list(lines: Sequence[str]) -> List[Heading]:
    headings: List[Heading] = []
    in_fence = False
    in_comment = False
    for index, line in enumerate(lines, start=1):
        if re.match(r"^\s*(```|~~~)", line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if in_comment:
            if "-->" in line:
                in_comment = False
            continue
        if "<!--" in line:
            if "-->" not in line:
                in_comment = True
            continue
        match = HEADING_RE.match(line)
        if not match:
            continue
        level = len(match.group(1))
        title = match.group(2).strip()
        controlled = CONTROLLED_HEADING_RE.match(title)
        explicit_id: Optional[str] = None
        explicit_title: Optional[str] = None
        if controlled and CONTROLLED_ID_RE.fullmatch(controlled.group("id")):
            explicit_id = controlled.group("id")
            explicit_title = controlled.group("title").strip()
        headings.append(Heading(level, title, index, explicit_id, explicit_title))
    return headings


def block_body(lines: Sequence[str], heading: Heading, headings: Sequence[Heading]) -> str:
    next_line = len(lines) + 1
    for candidate in headings:
        if candidate.line > heading.line:
            next_line = candidate.line
            break
    body = "\n".join(lines[heading.line:next_line - 1]).strip()
    return body


def parse_fields(body: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    stage: Optional[str] = None
    status: Optional[str] = None
    content_line: Optional[int] = None
    body_lines = body.splitlines()
    for index, line in enumerate(body_lines):
        for key, pattern in FIELD_PATTERNS.items():
            match = pattern.match(line)
            if not match:
                continue
            value = clean_value(match.group(1))
            if key == "stage":
                stage = value
            elif key == "status":
                status = value
            else:
                content_line = index
                if value:
                    return stage, status, value
                remainder = [item.strip() for item in body_lines[index + 1:] if item.strip()]
                return stage, status, "\n".join(remainder)
    return stage, status, None


def parse_memory_file(path: Path, repo_root: Path) -> List[Memory]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as error:
        raise QueryError(f"无法按 UTF-8 读取记忆文件：{path}: {error}") from error
    except OSError as error:
        raise QueryError(f"无法读取记忆文件：{path}: {error}") from error

    try:
        source = path.relative_to(repo_root).as_posix()
    except ValueError:
        source = path.as_posix()

    expected_stage = MEMORY_FILES.get(path.name)
    if expected_stage is None:
        raise QueryError(f"不支持的记忆文件：{source}")

    lines = text.splitlines()
    headings = heading_list(lines)
    if not headings:
        return []

    memories: List[Memory] = []
    for heading in headings:
        if heading.level < 2:
            continue
        body = block_body(lines, heading, headings)
        if heading.explicit_id is not None:
            stage_text, status_text, content = parse_fields(body)
            if stage_text is None or status_text is None or content is None or not content.strip():
                raise QueryError(
                    f"受控记忆 {source}:{heading.line} 必须同时包含阶段、状态和内容"
                )
            stage = parse_stage_value(stage_text, source, heading.line)
            if stage != expected_stage:
                raise QueryError(
                    f"受控记忆 {source}:{heading.line} 的阶段必须是 {expected_stage}"
                )
            expected_prefix = STAGE_ID_PREFIX[stage]
            if not heading.explicit_id.startswith(f"{expected_prefix}-"):
                raise QueryError(
                    f"受控记忆 {source}:{heading.line} 的编号必须使用 {expected_prefix}-xxxx"
                )
            status = parse_status_value(status_text, source, heading.line)
            memories.append(
                Memory(
                    memory_id=heading.explicit_id,
                    title=heading.explicit_title or heading.title,
                    stage=stage,
                    status=status,
                    content=content.strip(),
                    source=source,
                    line=heading.line,
                )
            )
            continue

        matched_heading = CONTROLLED_HEADING_RE.match(heading.title)
        if matched_heading and ID_LIKE_RE.match(matched_heading.group("id")):
            raise QueryError(f"受控记忆 {source}:{heading.line} 的编号格式无效")

        if not body or body.strip("-*_ ") == "":
            continue
        raise QueryError(
            f"记忆文件 {source}:{heading.line} 包含无编号内容；请使用 ### <阶段前缀>-xxxx｜标题"
        )
    return memories


def load_memories(repo_root: Path) -> List[Memory]:
    memory_dir = repo_root / "memories"
    if not memory_dir.is_dir():
        raise QueryError(f"找不到记忆目录：{memory_dir}")
    unexpected_paths = sorted(
        (path for path in memory_dir.rglob("*.md") if path.name not in MEMORY_FILES),
        key=lambda item: item.as_posix().lower(),
    )
    if unexpected_paths:
        listed = "、".join(path.relative_to(repo_root).as_posix() for path in unexpected_paths)
        raise QueryError(f"发现不支持的记忆文件：{listed}")
    paths = []
    for filename in MEMORY_FILES:
        path = memory_dir / filename
        if not path.is_file():
            raise QueryError(f"缺少阶段记忆文件：{path.relative_to(repo_root).as_posix()}")
        paths.append(path)
    memories: List[Memory] = []
    seen = {}
    for path in paths:
        for memory in parse_memory_file(path, repo_root):
            previous = seen.get(memory.memory_id)
            if previous is not None:
                raise QueryError(
                    f"记忆编号重复：{memory.memory_id}（{previous.source}:{previous.line} 与 {memory.source}:{memory.line}）"
                )
            seen[memory.memory_id] = memory
            memories.append(memory)
    return memories


def stage_matches(memory: Memory, query_stage: str) -> bool:
    return query_stage == memory.stage


def status_filter(raw: Optional[str]) -> Tuple[str, ...]:
    if raw is None or not raw.strip():
        return DEFAULT_STATUSES
    values: List[str] = []
    for part in split_values(raw):
        status = canonical_status(part)
        if status == "全部":
            return DEFAULT_STATUSES
        if status not in values:
            values.append(status)
    if not values:
        return DEFAULT_STATUSES
    return tuple(values)


def entry_as_dict(memory: Memory) -> dict:
    return {
        "id": memory.memory_id,
        "title": memory.title,
        "stage": memory.stage,
        "status": memory.status,
        "content": memory.content,
    }


def select_entries(memories: Sequence[Memory], stage: str, statuses: Sequence[str]) -> List[dict]:
    candidates = [
        memory
        for memory in memories
        if stage_matches(memory, stage) and memory.status in statuses
    ]
    candidates.sort(key=lambda item: (item.source.lower(), item.line, item.memory_id))

    return [entry_as_dict(memory) for memory in candidates]


def build_result(stage: str, statuses: Sequence[str], memories: Sequence[Memory]) -> dict:
    entries = select_entries(memories, stage, statuses)
    return {
        "stage": stage,
        "status": list(statuses),
        "count": len(entries),
        "entries": entries,
    }


def render_markdown(result: dict) -> str:
    statuses = "、".join(result["status"])
    lines = [
        "# 记忆查询结果",
        "",
        f"- 阶段：{result['stage']}",
        f"- 状态：{statuses}",
        f"- 数量：{result['count']} 条",
        "",
    ]
    if not result["entries"]:
        lines.append("没有找到符合条件的记忆。")
    for entry in result["entries"]:
        lines.extend(
            [
                f"## {entry['id']}｜{entry['title']}",
                f"- 阶段：{entry['stage']}",
                f"- 状态：{entry['status']}",
                "",
                entry["content"],
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按阶段和状态只读查询频道记忆。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd())
    parser.add_argument("--stage", required=True, help="创作阶段")
    parser.add_argument("--status", help="候选、正式或暂存；省略时为候选和正式")
    parser.add_argument("--format", choices=("json", "markdown"), default="markdown")
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    try:
        args = parse_args(argv)
        stage = canonical_stage(args.stage)
        statuses = status_filter(args.status)
        repo_root = args.repo_root.resolve()
        memories = load_memories(repo_root)
        result = build_result(stage, statuses, memories)
        if args.format == "json":
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(render_markdown(result), end="")
        return 0
    except QueryError as error:
        print(f"memory-query 查询停止：{error}", file=sys.stderr)
        return error.code
    except OSError as error:
        print(f"memory-query 查询停止：无法访问文件：{error}", file=sys.stderr)
        return 2
    except Exception as error:  # Fail closed; never expose raw files as fallback.
        print(f"memory-query 查询停止：{error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
