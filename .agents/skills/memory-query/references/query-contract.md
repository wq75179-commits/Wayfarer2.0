# 记忆查询约定

本文件约定查询所读取的三份阶段记忆。查询没有写入权。

## 阶段文件

`memories/` 只包含以下三份可查询的 Markdown 文件：

| 文件 | 阶段 | 编号前缀 |
| --- | --- | --- |
| `大纲记忆.md` | 大纲 | `OUT-` |
| `文稿记忆.md` | 文稿 | `SCR-` |
| `包装记忆.md` | 包装 | `PKG-` |

其他 Markdown 文件、缺少阶段文件或阶段与文件不一致，都是停止查询的错误。

## 阶段

允许的查询阶段如下：

| 中文名称 | 兼容写法 |
| --- | --- |
| 大纲 | outline、写作大纲、阶段4、outline-drafting |
| 文稿 | script、口播文稿、阶段5 |
| 包装 | packaging、发布物料、阶段6 |

一条记忆只能写一个阶段。跨阶段经验要拆成对应阶段的独立条目；查询层不会共享、复制或推断跨阶段规则。

## 状态

- 候选：刚从用户反馈或对比中整理，仍待后续观察。
- 正式：用户已明确确认的稳定依据。
- 暂存：准备停止使用，默认不返回。

省略状态或查询“全部”时，范围都是候选加正式，不包括暂存。显式查询“暂存”时只返回暂存；查询“候选”或“正式”时只返回该状态。

## 条目格式

```text
### OUT-0001｜标题
阶段：大纲
状态：候选
内容：一条可直接指导创作的经验。
```

要求：

- 标题为 `### 编号｜标题`。
- 编号必须唯一，格式为 `OUT-0000`、`SCR-0000` 或 `PKG-0000`，且与阶段对应。
- 阶段只能写一个值：大纲、文稿或包装。
- 状态只能是候选、正式或暂存。
- 内容不能为空，并保持为一至三句可直接指导创作的经验。
- 内容不得嵌套新的 Markdown 标题、表格或另一条记忆。

不要求来源、项目编号、证据链、版本、冲突链或撤销字段。这些依据由真实项目 README 和用户确认过程保存。

## 查询命令

```powershell
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 全部
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 正式
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 候选
pwsh.exe -NoProfile -File .agents/skills/memory-query/scripts/query_memory.ps1 -Stage 文稿 -Status 暂存
```

`-Format json` 仅改变输出形式，`-RepoRoot` 仅用于测试或从其他目录调用。脚本返回该阶段符合状态条件的全部条目，不在查询层截断。

## 失败处理

下列情况必须停止：

- 阶段或状态无法识别；
- 记忆文件无法读取；
- 新条目缺少编号、阶段、状态或内容；
- 编号重复、编号前缀错误或编号格式错误；
- 条目声明多个阶段、阶段文件错误或出现无编号内容；
- `memories/` 中残留旧记忆文件或其他不支持的 Markdown 文件。

查询结果为零条不是错误。调用方必须明确显示零条结果，不能退回读取原始记忆或自行补写规则。
