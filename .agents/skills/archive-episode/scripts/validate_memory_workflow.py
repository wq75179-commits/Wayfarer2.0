#!/usr/bin/env python3
"""Read-only validation for the episode archive and memory workflow."""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path


EPISODE_ID_PATTERN = re.compile(r"^WF-\d{8}-\d{2}$")
FIELD_PATTERN = re.compile(r"(?m)^[ \t]*-[ \t]*([^:\n：]+?)[ \t]*[：:][ \t]*(.*?)[ \t]*$")
PLACEHOLDERS = {"", "—", "-", "暂无", "暂无可核验数据", "n/a", "N/A"}
ARCHIVE_RESULTS = {"已发布", "未发布", "取消", "暂停"}
CHANGELOG_HEADERS = ["日期", "阶段", "类型", "决策或变更", "原因", "依据"]
CHANGELOG_STAGES = {"选题", "简要架构", "资料补全", "写作大纲", "口播文稿", "发布物料", "归档", "记忆整理"}
CHANGELOG_TYPES = {"决策", "变更", "否决", "记忆写入"}
MEMORY_SHAPES = {
    "往期影片信息记录.md": (
        "同步口径",
        "圈层配额（最近 10 期已发布）",
        "影片索引",
        "已验证经验索引",
        "待验证队列",
    ),
    "大纲创作技巧记忆.md": (
        "一、钩子/开场经验",
        "二、科学锚点使用记录",
        "三、比喻库",
        "四、结构变体经验",
        "五、用户修改模式（我的盲区）",
        "六、选题切入经验",
    ),
    "文稿撰写记忆.md": (
        "一、风格校准补丁",
        "二、好句收集",
        "三、用户表达偏好",
        "四、我的常犯错误",
        "五、段落级经验",
    ),
    "重大决策记忆.md": ("使用说明", "决策记录"),
}


@dataclass(frozen=True)
class Issue:
    severity: str
    code: str
    path: str
    message: str


def issue(severity: str, code: str, path: Path | str, message: str) -> Issue:
    return Issue(severity, code, str(path), message)


def read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def is_blank(value: str | None) -> bool:
    return value is None or value.strip() in PLACEHOLDERS


def extract_fields(text: str) -> dict[str, str]:
    return {match.group(1).strip(): match.group(2).strip() for match in FIELD_PATTERN.finditer(text)}


def extract_heading_section(text: str, title: str, level: int) -> str:
    pattern = re.compile(rf"(?m)^{'#' * level}\s+{re.escape(title)}\s*$")
    match = pattern.search(text)
    if match is None:
        return ""
    tail = text[match.end() :]
    next_heading = re.search(rf"(?m)^#{{1,{level}}}\s+", tail)
    return tail[: next_heading.start()] if next_heading else tail


def table_cells(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in cells)


def parse_markdown_table(section: str) -> tuple[list[str], list[dict[str, str]]]:
    header: list[str] = []
    rows: list[dict[str, str]] = []
    for raw_line in section.splitlines():
        line = raw_line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = table_cells(line)
        if is_separator_row(cells):
            continue
        if not header:
            header = cells
            continue
        if len(cells) == len(header):
            rows.append(dict(zip(header, cells)))
    return header, rows


def strip_html_comments(text: str) -> str:
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def validate_changelog(path: Path, *, require_archive_entry: bool = False) -> list[Issue]:
    issues: list[Issue] = []
    text = read_utf8(path)
    analysis_position = text.find("\n## 数据分析")
    changelog_position = text.find("\n## Changelog")
    index_position = text.find("\n## 文档索引")
    if changelog_position < 0:
        return [issue("ERROR", "MISSING_CHANGELOG", path, "README 缺少 Changelog。")]
    if not (analysis_position < changelog_position < index_position):
        issues.append(issue("ERROR", "INVALID_CHANGELOG_POSITION", path, "Changelog 必须位于数据分析之后、文档索引之前。"))

    section = extract_heading_section(text, "Changelog", 2)
    header, rows = parse_markdown_table(section)
    if header != CHANGELOG_HEADERS:
        issues.append(issue("ERROR", "INVALID_CHANGELOG_HEADER", path, "Changelog 表头不符合约定。"))
        return issues

    table_lines = [line.strip() for line in section.splitlines() if line.strip().startswith("|") and line.strip().endswith("|")]
    for row_number, line in enumerate(table_lines[2:], start=1):
        cells = table_cells(line)
        if not is_separator_row(cells) and len(cells) != len(CHANGELOG_HEADERS):
            issues.append(issue("ERROR", "INVALID_CHANGELOG_ROW_WIDTH", path, f"Changelog 第 {row_number} 条列数不正确。"))

    real_rows: list[dict[str, str]] = []
    placeholder_rows = 0
    seen: set[tuple[str, str, str, str]] = set()
    for row_number, row in enumerate(rows, start=1):
        if row.get("决策或变更", "").strip() == "暂无已确认记录":
            placeholder_rows += 1
            continue
        real_rows.append(row)
        missing = [column for column in CHANGELOG_HEADERS if is_blank(row.get(column))]
        if missing:
            issues.append(issue("ERROR", "INCOMPLETE_CHANGELOG_ROW", path, f"Changelog 第 {row_number} 条缺少：{'、'.join(missing)}。"))
            continue
        try:
            datetime.strptime(row["日期"], "%Y-%m-%d")
        except ValueError:
            issues.append(issue("ERROR", "INVALID_CHANGELOG_DATE", path, f"Changelog 第 {row_number} 条日期必须为 YYYY-MM-DD。"))
        if row["阶段"] not in CHANGELOG_STAGES:
            issues.append(issue("ERROR", "INVALID_CHANGELOG_STAGE", path, f"Changelog 第 {row_number} 条阶段无效。"))
        if row["类型"] not in CHANGELOG_TYPES:
            issues.append(issue("ERROR", "INVALID_CHANGELOG_TYPE", path, f"Changelog 第 {row_number} 条类型无效。"))
        key = (row["日期"], row["阶段"], row["类型"], row["决策或变更"])
        if key in seen:
            issues.append(issue("ERROR", "DUPLICATE_CHANGELOG_ROW", path, f"Changelog 第 {row_number} 条与已有记录重复。"))
        seen.add(key)

    if placeholder_rows and real_rows:
        issues.append(issue("ERROR", "STALE_CHANGELOG_PLACEHOLDER", path, "写入真实记录后必须删除 Changelog 占位行。"))

    if require_archive_entry and not any(row.get("阶段") == "归档" for row in real_rows):
        issues.append(issue("ERROR", "MISSING_ARCHIVE_CHANGELOG", path, "Changelog 缺少本期归档记录。"))
    return issues


def discover_episode_readmes(repo_root: Path) -> list[Path]:
    project_dir = repo_root / "project"
    if not project_dir.is_dir():
        return []
    return sorted(path for path in project_dir.glob("*/README.md") if path.parent.name != "example")


def resolve_episode(repo_root: Path, value: str | None) -> tuple[Path | None, list[Issue]]:
    if value:
        candidate = Path(value)
        if not candidate.is_absolute():
            candidate = repo_root / candidate
        candidate = candidate.resolve()
        try:
            candidate.relative_to(repo_root.resolve())
        except ValueError:
            return None, [issue("ERROR", "EPISODE_OUTSIDE_REPO", candidate, "目标 README 不得位于仓库外。")]
        if candidate.parent.name == "example":
            return None, [issue("ERROR", "TEMPLATE_IS_NOT_EPISODE", candidate, "example 模板不能作为真实项目归档。")]
        if not candidate.is_file():
            return None, [issue("ERROR", "EPISODE_NOT_FOUND", candidate, "找不到目标项目 README。")]
        return candidate, []

    candidates = discover_episode_readmes(repo_root)
    if not candidates:
        return None, [issue("ERROR", "NO_REAL_EPISODE", repo_root / "project", "没有可归档的真实单期项目。")]
    active: list[Path] = []
    for candidate in candidates:
        try:
            state = extract_fields(read_utf8(candidate)).get("当前状态", "").strip()
        except (OSError, UnicodeError) as error:
            return None, [issue("ERROR", "UNREADABLE_EPISODE", candidate, str(error))]
        if state != "归档":
            active.append(candidate)
    if len(active) == 1:
        return active[0], []
    if len(active) > 1:
        return None, [issue("ERROR", "MULTIPLE_ACTIVE_EPISODES", repo_root / "project", "发现多个未归档项目，不能自动选择。")]
    if len(candidates) == 1:
        return candidates[0], []
    return None, [issue("ERROR", "NO_ACTIVE_EPISODE", repo_root / "project", "历史项目均已归档，没有唯一的当前项目。")]


def validate_template(repo_root: Path) -> list[Issue]:
    path = repo_root / "project" / "example" / "README.md"
    if not path.is_file():
        return [issue("ERROR", "MISSING_TEMPLATE", path, "缺少单期 README 模板。")]
    return validate_changelog(path)


def validate_archive(path: Path) -> list[Issue]:
    issues = validate_changelog(path, require_archive_entry=True)
    text = read_utf8(path)
    fields = extract_fields(text)
    episode_id = fields.get("episode_id", "").strip()
    if not EPISODE_ID_PATTERN.fullmatch(episode_id):
        issues.append(issue("ERROR", "INVALID_EPISODE_ID", path, "episode_id 必须匹配 WF-YYYYMMDD-NN。"))
    for field in ("创建日期", "选题", "切入角度", "受众圈层", "内容类型", "核心承诺"):
        if is_blank(fields.get(field)):
            issues.append(issue("ERROR", "MISSING_ARCHIVE_FACT", path, f"归档缺少：{field}。"))
    if fields.get("当前状态", "").strip() != "归档":
        issues.append(issue("ERROR", "NOT_ARCHIVED", path, "当前状态必须为归档。"))

    confirmation_section = extract_heading_section(text, "创作确认", 2)
    _, confirmation_rows = parse_markdown_table(confirmation_section)
    archive_row = next((row for row in confirmation_rows if row.get("节点") == "归档"), None)
    if archive_row is None or archive_row.get("状态") != "已确认":
        issues.append(issue("ERROR", "ARCHIVE_NOT_CONFIRMED", path, "创作确认中的归档必须为已确认。"))
    elif is_blank(archive_row.get("确认日期")):
        issues.append(issue("ERROR", "MISSING_ARCHIVE_DATE", path, "归档确认缺少日期。"))

    result = fields.get("归档结果", "").strip()
    if result not in ARCHIVE_RESULTS:
        issues.append(issue("ERROR", "INVALID_ARCHIVE_RESULT", path, "归档结果必须是已发布、未发布、取消或暂停。"))
    elif result == "已发布":
        for field in ("最终标题", "发布平台", "视频链接", "发布时间", "视频时长"):
            if is_blank(fields.get(field)):
                issues.append(issue("ERROR", "MISSING_PUBLISH_FACT", path, f"已发布项目缺少：{field}。"))
    else:
        for field in ("终局原因", "下一次复核动作"):
            if is_blank(fields.get(field)):
                issues.append(issue("ERROR", "MISSING_TERMINAL_FACT", path, f"{result or '未发布'}项目缺少：{field}。"))
    return issues


def validate_memory_presence(repo_root: Path) -> list[Issue]:
    issues: list[Issue] = []
    for filename in MEMORY_SHAPES:
        path = repo_root / "memories" / filename
        if not path.is_file():
            issues.append(issue("ERROR", "MISSING_MEMORY_FILE", path, "缺少长期记忆文件。"))
    return issues


def validate_memory_shapes(repo_root: Path) -> list[Issue]:
    issues = validate_memory_presence(repo_root)
    for filename, headings in MEMORY_SHAPES.items():
        path = repo_root / "memories" / filename
        if not path.is_file():
            continue
        text = strip_html_comments(read_utf8(path))
        for heading in headings:
            if not re.search(rf"(?m)^##\s+{re.escape(heading)}\s*$", text):
                issues.append(issue("ERROR", "MISSING_MEMORY_HEADING", path, f"缺少章节：{heading}。"))
    return issues


def validate_workflow(repo_root: Path, stage: str, episode_value: str | None = None) -> list[Issue]:
    repo_root = repo_root.resolve()
    issues = validate_template(repo_root)
    if stage == "template":
        return issues
    issues.extend(validate_memory_presence(repo_root))
    episode, resolve_issues = resolve_episode(repo_root, episode_value)
    issues.extend(resolve_issues)
    if episode is not None:
        issues.extend(validate_archive(episode))
    if stage == "all":
        issues.extend(validate_memory_shapes(repo_root))
    return issues


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="只读检查单期归档与四份长期记忆的工作流结构。")
    parser.add_argument("--repo-root", type=Path, default=Path.cwd(), help="仓库根目录。")
    parser.add_argument("--stage", choices=("template", "archive", "all"), default="all", help="检查阶段。")
    parser.add_argument("--episode", help="真实单期 README 路径；省略时仅在唯一项目存在时自动选择。")
    parser.add_argument("--json", action="store_true", help="以 JSON 输出问题。")
    args = parser.parse_args(argv)

    issues = validate_workflow(args.repo_root, args.stage, args.episode)
    if args.json:
        print(json.dumps([asdict(item) for item in issues], ensure_ascii=False, indent=2))
    elif not issues:
        print("OK：归档与记忆工作流结构检查通过。")
    else:
        for item in issues:
            print(f"{item.severity} [{item.code}] {item.path}: {item.message}")
    return 1 if any(item.severity == "ERROR" for item in issues) else 0


if __name__ == "__main__":
    raise SystemExit(main())
