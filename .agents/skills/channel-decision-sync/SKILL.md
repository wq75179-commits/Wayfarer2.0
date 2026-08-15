---
name: channel-decision-sync
description: 根据已归档单期 README 的 Changelog，只同步用户明确作出的频道长期决定，并完成四份记忆的最终一致性审计。用于归档记忆流程的最后阶段，或用户明确要求把某期频道级决定写入重大决策记忆时；不得从单期表现、修改习惯或 agent 推测生成战略决策。
---

# 频道重大决策整理

## 目标与写入边界

把用户明确作出的频道长期决定写入 `memories/重大决策记忆.md`，并在本期流程结束前确认四份记忆都已审计。

- 只写重大决策记忆，以及本期 README 的一条成功写入日志。
- 不把大纲技巧、文稿偏好、单期结果或数据相关性包装成频道决策。
- 决策可以先记录、后验证；尚无结果不等于不能记录。
- 没有新决策时不得为了“所有文件都处理过”而改写文件或更新时间。

执行前完整读取：

- [重大决策契约](references/channel-decision-contract.md)
- [归档工作流契约](../archive-episode/references/workflow-contract.md)
- 当前真实单期 README、其 Changelog、重大决策记忆，以及前三步的当前文件状态。

## 整理流程

### 1. 验证入口

1. 确认目标是真实已归档项目，归档节点已确认。
2. 在串联流程中确认内部交接来自已完成的 `creative-memory-sync`；直接调用时要求用户明确指定一期项目。
3. 重新读取 Changelog，只考虑用户已明确作出的长期方向、规则或资源取舍。

### 2. 生成候选

每个候选必须回答：

- 用户明确决定了什么。
- 为什么作出决定；没有明确原因时如实写“未说明”，不得推断。
- 影响哪些频道范围。
- 从何时开始执行。
- 当前是执行中、待观察还是替代旧决定。
- 是否与已有决定重复、冲突或构成更新。

单期表现、一次创作修改、agent 建议、未确认讨论和只有数据相关性的判断都不是候选。

### 3. 唯一正常暂停点

有候选时，用日常语言复述准备记录的决定、原因和状态，再询问是否写入。没有候选时使用直白说明：

> 这期没有发现你明确作出的频道长期决定，所以我不会改动长期决策记录。现在要完成最后检查吗？

不要展示 Skill 名、编号生成规则、字段、脚本或校验术语。

### 4. 批准后写入

1. 重新读取 README 和重大决策记忆；任一来源变化时重新说明。
2. 为新决定分配下一个连续的 `D` 编号；更新旧决定时保留原编号和历史文字。
3. 新决定必须回链本期 README。执行中的明确规则标为执行中；尚待效果检验的决定标为待观察。
4. 废弃决定时保留原记录，追加废弃原因和替代决定；不得删除。
5. 写入成功后，在本期 README Changelog 追加一条 `记忆写入` 记录。
6. 回读并运行本技能验证器。

当前步骤失败时恢复本步骤开始前的重大决策记忆与 Changelog，停止流程。

### 5. 最终四文件审计

无论本期是否产生重大决策，都必须依次运行：

```powershell
rtk python -B -X utf8 .agents/skills/episode-memory-sync/scripts/validate_sync.py --repo-root .
rtk python -B -X utf8 .agents/skills/creative-memory-sync/scripts/validate_creative_memory.py --repo-root . --episode <README路径>
rtk python -B -X utf8 .agents/skills/channel-decision-sync/scripts/validate_channel_decisions.py --repo-root . --episode <README路径>
rtk python -B -X utf8 .agents/skills/archive-episode/scripts/validate_memory_workflow.py --repo-root . --stage all --episode <README路径>
```

最后按四份记忆分别报告：已更新、无变更、用户未批准或阻断。与本期无关的历史问题只报告，不自动整理。

## 版本提交交接

本技能不提交 Git。最终审计通过后回到主流程，用日常语言询问用户是否确认整体完成、内容无误并允许保存版本记录。只有用户再次明确批准后才可创建包含全部已批准修改的提交。

## 完成条件

- 重大决策候选只来自用户明确决定。
- 获批决定已保留原因、状态、影响范围和本期来源。
- 四份记忆都已审计并有明确结果。
- 全部只读检查通过，或已清楚列出阻断并停止。
