from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


SCRIPT_PATH = Path(__file__).parents[1] / "scripts" / "validate_sync.py"
SPEC = importlib.util.spec_from_file_location("episode_memory_sync_validator", SCRIPT_PATH)
assert SPEC is not None and SPEC.loader is not None
VALIDATOR = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = VALIDATOR
SPEC.loader.exec_module(VALIDATOR)


EPISODE_ID = "WF-20260801-01"


def write_file(root: Path, relative_path: str, contents: str) -> Path:
    path = root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(contents, encoding="utf-8")
    return path


def confirmation_rows() -> str:
    return """| 节点 | 状态 | 确认日期 | 决策摘要 |
| --- | --- | --- | --- |
| 选题 | 已确认 | 2026-08-01 | 聚焦启动阻力 |
| 简要架构 | 已确认 | 2026-08-01 | 使用行动摩擦切入 |
| 资料补全 | 已确认 | 2026-08-02 | 资料已锁定 |
| 写作大纲 | 已确认 | 2026-08-03 | 保留三步行动方案 |
| 口播文稿 | 已确认 | 2026-08-04 | 文稿已确认 |
| 发布物料 | 已确认 | 2026-08-05 | 标题与封面已确认 |
| 归档 | 已确认 | 2026-08-08 | 已发布并归档 |"""


def episode_markdown(
    *,
    episode_id: str = EPISODE_ID,
    title: str = "为什么启动比坚持更难",
    video_link: str = "https://example.com/video",
    conclusion_state: str = "已验证",
    reusable_lesson: str = "先降低启动摩擦，再要求持续行动。",
    hypothesis: str = "",
) -> str:
    return f"""# 本期影片记录

## 基础信息

- episode_id：{episode_id}
- 创建日期：2026-08-01
- 选题：用行动摩擦解释拖延启动困难
- 切入角度：从启动阻力而非意志力切入
- 受众圈层：第一圈
- 内容类型：原创
- 核心承诺：给出一个今天就能开始的动作
- 当前状态：归档

## 创作确认

{confirmation_rows()}

## 发布结果

- 归档结果：已发布
- 最终标题：{title}
- 发布平台：B站
- 视频链接：{video_link}
- 发布时间：2026-08-08 20:00
- 视频时长：10:00
- 表现等级：符合预期
- 终局原因：
- 下一次复核动作：发布后 14D 复核完播率

### 数据记录

| 采集日期 | 统计周期 | 来源 | 平台 | 指标 | 数值 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-15 | 发布后 7D | B站创作中心 | B站 | 播放量 | 1000 |

## 数据分析

- 分析复核日期：2026-08-15
- 现象：开场的前 30 秒留存高于频道平均
- 证据：发布后 7D，来源为 B站创作中心，播放量为 1000
- 限制/原因：样本仅一条，不能排除题材影响
- 结论：具体场景开场降低了理解门槛
- 结论状态：{conclusion_state}
- 可复用经验：{reusable_lesson}
- 待验证假设：{hypothesis}
- 下一期验证动作：下一期继续使用具体场景开场并比较留存
"""


def cancelled_episode_markdown() -> str:
    return (
        episode_markdown(conclusion_state="失败", reusable_lesson="选题证据不足时，应在写作前终止生产。")
        .replace("- 归档结果：已发布", "- 归档结果：取消")
        .replace("- 最终标题：为什么启动比坚持更难", "- 最终标题：")
        .replace("- 发布平台：B站", "- 发布平台：—")
        .replace("- 视频链接：https://example.com/video", "- 视频链接：—")
        .replace("- 发布时间：2026-08-08 20:00", "- 发布时间：—")
        .replace("- 视频时长：10:00", "- 视频时长：—")
        .replace("- 表现等级：符合预期", "- 表现等级：未评估")
        .replace("- 终局原因：", "- 终局原因：资料证据不足，取消本期制作。")
        .replace("- 下一次复核动作：发布后 14D 复核完播率", "- 下一次复核动作：下个选题评估阶段补齐证据后再决定是否重启。")
    )


def memory_markdown(
    *,
    episode_id: str = EPISODE_ID,
    directory: str = "episode-a",
    title: str = "为什么启动比坚持更难",
    metric_summary: str = "统计周期=发布后 7D；来源=B站创作中心；播放量=1000",
    readme_link: str | None = None,
) -> str:
    link = readme_link or f"../project/{directory}/README.md"
    return f"""# 往期影片信息记录

- schema_version：1
- 最近一次同步：2026-08-15

## 同步口径

- 单期事实源：`project/<episode>/README.md`

## 圈层配额（最近 10 期已发布）

- 样本数：1 / 10
- 第一圈：1
- 第二圈：0
- 第三圈：0
- 当前判断：样本不足十期。

## 影片索引

### {episode_id}

- README：[项目 README]({link})
- 最终标题：{title}
- 发布日期：2026-08-08 20:00
- 归档日期：2026-08-08
- 归档结果：已发布
- 一句话选题：用行动摩擦解释拖延启动困难
- 切入角度：从启动阻力而非意志力切入
- 受众圈层：第一圈
- 内容类型：原创
- 核心承诺：给出一个今天就能开始的动作
- 关键确认：归档已确认；发布物料已确认
- 重大决策摘要：保留三步行动方案。
- 发布摘要：平台=B站；链接=https://example.com/video；时长=10:00；表现等级=符合预期
- 指标摘要：{metric_summary}
- 结论状态：已验证
- 已验证做法：先降低启动摩擦，再要求持续行动。
- 失败或限制：样本仅一条，不能排除题材影响。
- 待验证假设：
- 下一期验证动作：下一期继续使用具体场景开场并比较留存

## 已验证经验索引

- 具体场景开场降低理解门槛（来源：{episode_id}）

## 待验证队列

暂无待验证假设。
"""


def cancelled_memory_markdown() -> str:
    return (
        memory_markdown()
        .replace("- 样本数：1 / 10", "- 样本数：0 / 10")
        .replace("- 第一圈：1", "- 第一圈：0")
        .replace("- 最终标题：为什么启动比坚持更难", "- 最终标题：")
        .replace("- 发布日期：2026-08-08 20:00", "- 发布日期：未发布")
        .replace("- 归档结果：已发布", "- 归档结果：取消")
        .replace("- 发布摘要：平台=B站；链接=https://example.com/video；时长=10:00；表现等级=符合预期", "- 发布摘要：未发布")
        .replace("- 指标摘要：统计周期=发布后 7D；来源=B站创作中心；播放量=1000", "- 指标摘要：无（未发布）")
        .replace("- 结论状态：已验证", "- 结论状态：失败")
        .replace("- 已验证做法：先降低启动摩擦，再要求持续行动。", "- 已验证做法：选题证据不足时，应在写作前终止生产。")
    )


def empty_memory_markdown() -> str:
    return """# 往期影片信息记录

- schema_version：1
- 最近一次同步：—

## 同步口径

- 单期事实源：`project/<episode>/README.md`

## 圈层配额（最近 10 期已发布）

- 样本数：0 / 10
- 第一圈：0
- 第二圈：0
- 第三圈：0
- 当前判断：暂无已发布影片。

## 影片索引

暂无已归档影片。

## 已验证经验索引

暂无已验证经验。

## 待验证队列

暂无待验证假设。
"""


def issue_codes(root: Path) -> set[str]:
    return {item.code for item in VALIDATOR.validate_repository(root)}


class ValidateSyncTests(unittest.TestCase):
    def create_repo(self) -> tempfile.TemporaryDirectory[str]:
        temporary_directory = tempfile.TemporaryDirectory()
        root = Path(temporary_directory.name)
        write_file(root, "memories/往期影片信息记录.md", empty_memory_markdown())
        return temporary_directory

    def test_empty_repository_is_valid(self) -> None:
        with self.create_repo() as temporary_directory:
            self.assertEqual(issue_codes(Path(temporary_directory)), set())

    def test_template_directory_is_excluded(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/example/README.md", "- episode_id：not-a-valid-id\n")
            self.assertEqual(issue_codes(root), set())

    def test_valid_published_episode_and_memory_are_valid(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(root, "memories/往期影片信息记录.md", memory_markdown())
            self.assertEqual(issue_codes(root), set())

    def test_cancelled_episode_is_structurally_valid_without_publication_fields(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            readme_path = write_file(root, "project/episode-a/README.md", cancelled_episode_markdown())
            episode = VALIDATOR.parse_episode(readme_path)
            errors = [item for item in VALIDATOR.validate_episode_shape(episode) if item.severity == "ERROR"]
            self.assertEqual(errors, [])

    def test_cancelled_episode_and_memory_are_valid(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", cancelled_episode_markdown())
            write_file(root, "memories/往期影片信息记录.md", cancelled_memory_markdown())
            self.assertEqual(issue_codes(root), set())

    def test_legacy_episode_id_is_rejected(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown(episode_id="202608010923"))
            self.assertIn("INVALID_EPISODE_ID", issue_codes(root))

    def test_duplicate_episode_id_is_rejected(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(root, "project/episode-b/README.md", episode_markdown())
            self.assertIn("DUPLICATE_EPISODE_ID", issue_codes(root))

    def test_published_episode_requires_video_link(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown(video_link=""))
            self.assertIn("MISSING_PUBLISH_FIELD", issue_codes(root))

    def test_unverified_conclusion_requires_hypothesis(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(
                root,
                "project/episode-a/README.md",
                episode_markdown(conclusion_state="待验证", reusable_lesson="", hypothesis=""),
            )
            self.assertIn("MISSING_HYPOTHESIS", issue_codes(root))

    def test_metric_summary_requires_period_and_source(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(root, "memories/往期影片信息记录.md", memory_markdown(metric_summary="播放量=1000"))
            self.assertIn("UNLABELED_METRIC_SUMMARY", issue_codes(root))

    def test_metric_summary_must_trace_to_source_data(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(
                root,
                "memories/往期影片信息记录.md",
                memory_markdown(metric_summary="统计周期=发布后 7D；来源=B站创作中心；播放量=999"),
            )
            self.assertIn("METRIC_SUMMARY_NOT_IN_SOURCE", issue_codes(root))

    def test_memory_link_must_exist_and_use_canonical_path(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(
                root,
                "memories/往期影片信息记录.md",
                memory_markdown(readme_link="../project/moved/README.md"),
            )
            codes = issue_codes(root)
            self.assertIn("BROKEN_README_LINK", codes)
            self.assertIn("NONCANONICAL_README_LINK", codes)

    def test_memory_authority_fields_must_match_readme(self) -> None:
        with self.create_repo() as temporary_directory:
            root = Path(temporary_directory)
            write_file(root, "project/episode-a/README.md", episode_markdown())
            write_file(root, "memories/往期影片信息记录.md", memory_markdown(title="错误标题"))
            self.assertIn("AUTHORITY_FIELD_MISMATCH", issue_codes(root))


if __name__ == "__main__":
    unittest.main()