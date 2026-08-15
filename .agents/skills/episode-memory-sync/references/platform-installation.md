# 跨平台安装与验证

四个核心技能目录位于仓库根目录的 `.agents/skills/`：

- `archive-episode/`
- `episode-memory-sync/`
- `creative-memory-sync/`
- `channel-decision-sync/`

这些目录共同构成唯一版本化事实源，严禁复制并长期维护第二份 `SKILL.md`。

## 平台发现路径

| 平台 | 项目级发现路径 | 验证方式 |
| --- | --- | --- |
| Cursor | `.agents/skills/` 下四个目录 | 在技能列表中确认四个名称，或分别显式调用 |
| Codex | `.agents/skills/` 下四个目录 | 从仓库根目录启动后检查可用技能列表 |
| Antigravity CLI | `.agents/skills/` 下四个目录 | 从仓库根目录启动后使用其技能列表命令确认 |
| Claude Code | `.claude/skills/` 下四个目录链接 | 在可用技能或斜杠命令中确认四个名称 |

Cursor、Codex 与 Antigravity CLI 都可直接发现 `.agents/skills/`，无需新增专属副本。

## Claude Code 的单一事实源接入

Claude Code 原生发现 `.claude/skills/`，因此仅为本地发现分别创建目录链接，目标始终是仓库中的对应核心目录：

```text
~/.claude/skills/archive-episode -> <仓库根目录>/.agents/skills/archive-episode
~/.claude/skills/episode-memory-sync -> <仓库根目录>/.agents/skills/episode-memory-sync
~/.claude/skills/creative-memory-sync -> <仓库根目录>/.agents/skills/creative-memory-sync
~/.claude/skills/channel-decision-sync -> <仓库根目录>/.agents/skills/channel-decision-sync
```

- 链接是本机安装状态，不纳入仓库提交。
- 使用绝对目标路径，避免从不同工作目录启动时解析错误。
- 创建链接前确认目标目录存在，创建后读取链接内的 `SKILL.md`，并确认内容与核心文件一致。
- 操作系统或权限策略不允许链接时，不创建副本；在需要时将核心 `SKILL.md` 作为显式上下文附加给 Claude Code。

## 安装后的最小验证

在任一平台中执行以下只读演练：

1. 请求使用 `archive-episode` 归档 `project/example/README.md`。
2. 预期结果：技能说明该目录是模板并排除，不修改任何文件。
3. 请求“审计所有归档影片”。
4. 预期结果：当前项目没有正式影片时只输出空审计；不会创建虚构条目。
5. 分别打开四个 `SKILL.md`，确认 frontmatter 只有标准 `name` 和 `description`，名称与目录一致。
6. 运行四个技能自带的只读校验和单元测试，确认空项目与模板场景不会生成记忆。

## 版本更新规则

- 只修改 `.agents/skills/` 下的四个核心目录；共享工作流规则以 `archive-episode/references/workflow-contract.md` 为准。
- 变更后在四个平台分别重新发现或重新加载四个目录；不要依赖平台缓存中的旧说明。
- 若某平台忽略此目录，记录该平台的实际发现机制到本文件，但不为它复制核心协议；优先使用链接、显式加载或该平台认可的单一入口机制。
