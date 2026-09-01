---
name: memory-query
description: 只读查询频道的大纲、文稿或包装记忆。按阶段和状态返回带编号的记忆，不写入、不升级、不删除。
---

# 记忆查询

## 目的

本 Skill 是后续创作阶段读取频道记忆的入口。它只回答：

> 当前阶段有哪些可参考的记忆？

记忆跨项目共用。单期事实、用户反馈和本期最终文件仍以对应的 `project/<项目>/README.md` 为准。

## 查询规则

查询只需要提供：

1. **阶段**：只能是大纲、文稿或包装。
2. **状态**：可省略。省略时返回该阶段的候选和正式记忆，不返回暂存记忆。

每条记忆只能属于一个阶段。跨阶段经验必须拆成多条记忆，分别写入对应阶段文件；不得在 `阶段` 字段中填写逗号、斜杠或多个值。

## 最小记忆格式

```text
### SCR-0001｜开场先解除羞耻感
阶段：文稿
状态：候选
内容：先承认观众并非不努力，再指出方法问题。
```

- 大纲记忆使用 `OUT-0001`、`OUT-0002` 等编号。
- 文稿记忆使用 `SCR-0001`、`SCR-0002` 等编号。
- 包装记忆使用 `PKG-0001`、`PKG-0002` 等编号。
- 编号建立后不能因为内容调整而改变，删除后也不能重复使用。
- 新条目必须写在对应的 `memories/大纲记忆.md`、`memories/文稿记忆.md` 或 `memories/包装记忆.md` 中。

## 调用方式

从仓库根目录使用 PowerShell 启动器：

```powershell
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 全部
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 候选
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 暂存
```

结果默认使用紧凑中文清单。需要结构化结果时添加 `-Format json`。每条结果只包含编号、标题、阶段、状态和内容。

## 使用边界

- 只读三份阶段记忆文件，不读取项目 README 或本期创作文件。
- 不把暂存记忆混入默认结果。
- 不根据调用次数、播放数据或模型判断改变状态。
- 不提出候选、不提醒升级、不判断失效、不执行删除。
- 不修改记忆文件、项目 README 或任何其他文件。
- 查询为空时只返回空清单；调用方不得猜测规则或退回整份原始记忆。

`creative-memory-review` 是经用户手动触发的整理写入方。它为去重、预览和回读而读取原始记忆文件，不属于创作阶段的读取路径。

## 出错处理

以下情况会停止查询：

- 缺少任一阶段记忆文件，或 `memories/` 中出现不支持的 Markdown 文件；
- 编号格式错误、编号与阶段前缀不一致、编号重复；
- 一条记忆声明多个阶段，或被写入错误的阶段文件；
- 缺少阶段、状态或内容；
- 出现无编号的记忆内容，或文件无法读取。

脚本不会把全部原始记忆交给创作 AI 作为退路，也不会因为没有结果而补写通用规则。

## 相关文件

- `references/query-contract.md`：阶段、状态和最小格式约定。
- `scripts/query_memory.py`：只读解析和输出。
- `scripts/query_memory.ps1`：PowerShell 启动入口。
- `tests/test_query_memory.py`：查询回归测试。
