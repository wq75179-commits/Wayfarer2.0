# Wayfarer 2.0 Git 协作规范

> 目录：0 文档定位 · 1 绝对规则 · 2 仓库对象的解释 · 3 第一轮检查（3.1 本地安全设置） · 4 标准任务流程（4.1–4.7） · 5 不使用 PR 的本地合并流程 · 6 多人同时工作的规则 · 7 冲突处理 · 8 常见故障 · 9 完成报告模板 · 10 最小命令清单（速查）

## 0. 文档定位

本文档适用于本仓库的全部协作者（管理员与仓库拥有者），并约定 AI 如何代为执行 Git 操作。协作者只需要说明要完成的内容，并在 AI 报告修改结果后确认是否可以提交，不要求手动执行 Git 命令。下文中的“用户”指发起任务的协作者。

仓库根目录以 `git rev-parse --show-toplevel` 的输出为准，不在本文档中写死具体路径。整个仓库只允许有这一个 Git 仓库，不得在 `project/` 的任何子目录再次执行 `git init`。

本规范采用以下协作方式：

- 日常使用 `main` 作为共享稳定分支。
- 每个任务可以创建并保留一个任务分支。
- 不使用 GitHub Pull Request，不要求用户审查 PR。
- AI 在本地把任务分支合并到 `main`，再直接推送 `main`。
- AI 负责所有 Git 命令、状态判断、冲突处理和结果说明。

命令示例统一写成 `git ...`，这是唯一标准写法。如果协作者或 AI 的执行环境配置了 `rtk` 封装（`rtk git ...` 等价于 `git ...`），可以加 `rtk` 前缀，但**不强制要求**——其他主机未安装 `rtk` 时，直接执行 `git` 命令即可，命令本身不得改变。

## 1. 绝对规则

1. 修改前先检查工作区、当前分支和仓库根目录。
2. 默认不直接修改 `main`，先从最新 `main` 创建任务分支。
3. 工作区干净时，开始任务前直接执行 `git pull origin main`，不要求用户手动同步；工作区有未提交改动时先按第 3 节处理，不执行 `pull`。
4. AI 发现用户已有未提交改动时，不得覆盖、清除、隐藏或擅自提交这些改动。
5. 每次内容修改完成后，先向用户报告文件、目的和检查结果；只有用户明确确认并批准后，才能 `commit`。
6. 一个提交只包含一个清晰任务，不把无关文件一起提交。
7. 任务分支合并前，AI 必须再次同步最新 `main`，避免把旧版本直接覆盖到远端。
8. 推送失败、历史分叉或冲突无法判断时，停止并向用户说明，不使用破坏性命令强行继续。
9. 未经用户明确要求，不删除文件；需要删除时一次只处理一个明确路径。
10. 不使用 `git push --force`、`git reset --hard`、`git clean -fd`，不删除 `.git`，不手动修改 `.git/`。

## 2. 仓库对象的解释

AI 不得把这些名称混为一谈：

| 名称 | 含义 |
| --- | --- |
| `main` | 本地共享主分支；最终合并后的内容进入这里 |
| `origin` | GitHub 远端的简称 |
| `origin/main` | 本地记录的远端 `main` 状态，执行 `fetch` 或 `pull` 后才会更新 |
| `HEAD` | 当前检出的提交位置，不是一个普通分支 |
| 任务分支 | 为一个具体任务临时或长期保留的分支，例如 `task/WF-20260814-01-script` |

判断当前分支必须使用：

```powershell
git branch --show-current
```

不得根据 `HEAD` 这个词猜测当前分支。

## 3. AI 接手任务时的第一轮检查

每次 AI 开始工作，先执行以下命令：

```powershell
git rev-parse --show-toplevel
git status --short --branch
git branch -vv
```

检查结果：

- `git rev-parse --show-toplevel` 执行失败或输出为空：停止并报告路径错误。
- 检查结果与预期仓库不符（例如指向 `project/` 内的嵌套仓库或错误目录）：停止并报告路径错误。
- 有未提交改动：先判断这些改动是否由当前 AI 在本轮产生。
- 有用户或另一轮工作留下的改动：不执行 `pull`、`reset`、`checkout --`、`stash` 或自动覆盖；先向用户说明哪些文件已有改动，并请求处理决定。
- 当前不在 `main` 且没有明确任务分支：不要直接修改，先询问或切回 `main`，但切换前必须确认工作区干净。

AI 必须先把工作区现状告诉用户，再开始编辑。不能把“工作区本来就有的改动”误报为本轮成果。

### 3.1 AI 首次接手的本地安全设置

在仓库根目录检查并设置一次：

```powershell
git config --get pull.ff
git config pull.ff only
git config fetch.prune true
git config core.autocrlf true
```

这不会修改仓库文件，也不会产生 Git 提交。设置完成后，日常仍可直接执行：

```powershell
git pull origin main
```

`pull.ff only` 的作用是：如果本地和远端可以直接前进，正常完成 `pull`；如果双方已经分叉，则停止并报告，不在后台自动制造新的合并提交。

`core.autocrlf true` 统一 Windows 上的换行符处理，避免 CRLF/LF 差异造成整文件噪音 diff；如未来需要更强约束，可在仓库根目录提交 `.gitattributes` 锁定文本文件行尾。

本机环境相关的网络配置（如 `http.proxy`、`http.sslBackend`）一律使用 `--global` 或环境变量设置，**不得写入仓库级 `.git/config`**：仓库级配置会随克隆带到其他协作者的机器，而对方的网络环境可能不同（例如代理端口不同），会导致对方的 `pull`/`push` 直接失败。仓库级 `.git/config` 只放协作性配置。

## 4. 标准任务流程

### 4.1 同步最新 main

工作区干净时，执行：

```powershell
git switch main
git pull origin main
```

这里使用直接 `pull`，因为本项目不要求用户理解 `fetch`、`merge` 或 `rebase` 的区别。

执行后立即检查：

```powershell
git status --short --branch
git log --oneline --decorate -5
```

如果 `pull` 产生合并提交、提示冲突或报错，AI 必须先解释结果，不得假装同步成功。

### 4.2 创建任务分支

从已同步的 `main` 创建任务分支：

```powershell
git switch -c task/WF-20260814-01-script
```

命名格式：

```text
task/<episode_id>-<简短用途>
```

没有 `episode_id` 的仓库级任务可以使用：

```text
task/root-readme
task/git-guide
task/fix-links
```

任务分支可以保留。任务合并后，AI 不得擅自删除本地或远端任务分支；只有用户明确要求清理时才删除。

### 4.3 修改文件

AI 只修改用户请求涉及的文件和必要的索引文件。

对于本仓库，额外注意：

- 单期事实以 `project/<episode>/README.md` 为准。
- 修改目录结构时，必须检查对应 README 的“文档索引”。
- 只有用户明确确认，才能更新单期 README 的状态、创作确认表和 Changelog。
- 不把 `project/example/README.md` 当作真实影片事实。
- 不因为 Git 冲突而自行选择一方覆盖另一方；事实、数据和文稿内容需要依据来源判断。
- 二进制素材文件（图片、视频、音频等）不提交到 Git 仓库，大文件走网盘或素材库；如未来需要版本化管理素材，再评估 Git LFS。
- 新增工具、编辑器或软件生成的目录/文件前，先检查 `.gitignore` 是否已覆盖；未覆盖时先向用户说明并补入 `.gitignore`，不直接提交工具生成物。

### 4.4 修改后检查但暂不提交

编辑完成后执行：

```powershell
git status --short
git diff --check
git diff --stat
git diff -- "明确的文件路径"
```

AI 按第 9 节的报告模板向用户报告：修改了哪些文件、每个文件改变了什么、做了哪些检查、是否发现未解决的问题。

此时必须等待用户明确确认。用户未确认前，不得执行 `git add`、`git commit` 或 `git push`。

### 4.5 用户确认后提交任务分支

只加入明确路径，不使用无选择的 `git add .`：

```powershell
git add -- "文件或目录路径"
git diff --cached --name-status
git diff --cached --check
git diff --cached -- "明确的文件路径"
git commit -m "新增：WF-20260814-01 - 补充口播文稿"
```

提交前必须查看 `git diff --cached` 的完整内容，确认 staged 变更与本次任务一致、没有夹带无关改动；只核对统计不检查实际 diff 不算完成检查。提交信息必须让协作者只看信息就能明白改了什么（对象 + 具体变更），禁止使用无法说明内容的提交信息。

提交信息格式：

```text
<类型>：<对象> - <具体变更>
```

推荐类型：

| 类型 | 场景 |
| --- | --- |
| `新增` | 新增资料、文稿、章节或文件 |
| `修复` | 修正事实、链接、字段或格式 |
| `优化` | 改善结构、索引、可读性或流程 |
| `文档` | 只修改说明文档或规范 |
| `归档` | 完成已确认的归档或记忆同步 |

不要使用 `test`、`修改一下`、`更新文件` 等无法说明内容的提交信息。

仓库另有创作与归档规范（`AGENTS.md`）：归档记忆流程要求在用户明确批准前不得提交 Git，本节与之一致；提交前同时执行安全门禁（扫描待提交内容），通过后才提交。

### 4.6 推送任务分支作为备份

提交成功后，可以把任务分支推送到远端保存：

```powershell
git push -u origin task/WF-20260814-01-script
```

这一步只是备份和保留历史，不是创建 PR，也不需要用户审查。

### 4.7 认证与凭证

- 默认使用系统凭证管理器（Windows 上为 Git Credential Manager，`credential.helper=manager`），首次推送时完成一次登录，后续自动使用。
- 凭证管理器无法运行或认证失败时（例如受限执行环境禁止弹窗）：先向用户说明，优先请用户手动执行一次 `git push` 完成认证。
- 备用方案：用户提供 Personal Access Token（PAT，`repo` 权限）后用于认证；令牌只用于本次命令，不写入文件。
- 禁止把 token 写进 URL（`https://user:token@...`）或任何提交记录。
- 认证相关错误（`could not read Username`、`Authentication failed`）按第 8 节的诊断框架定位，不要把 TLS/代理问题误判为凭证问题。

## 5. 不使用 PR 时的本地合并流程

任务分支提交成功后（分支是否已推送均可），由 AI 在本地完成合并：

```powershell
git switch main
git pull origin main
git log --oneline main..task/WF-20260814-01-script
git diff --stat main...task/WF-20260814-01-script
git merge --no-ff --no-edit task/WF-20260814-01-script
git diff --check
git show --stat <合并提交 ID>
git push origin main
```

合并前先查看任务分支相对 `main` 的提交清单（`git log`）和文件变更概览（`git diff --stat`），确认将要合并的内容；发现夹带无关提交或文件时，先停下来向用户说明，不得直接合并。合并成功后执行 `git show --stat` 核对合并进入 `main` 的最终文件清单，再向用户报告。

解释：

- 第二次 `pull` 是为了吸收另一位协作者在任务期间推送到 `main` 的内容。
- `--no-ff` 保留“这个任务来自哪个任务分支”的历史边界。
- `push origin main` 成功后，任务才算进入共享主线。
- 任务分支默认保留，不自动删除。

如果 `merge` 发生冲突，按第 7 节处理；如果 `pull` 或 `push` 失败，按第 8 节处理。

合并完成后，AI 向用户报告：

- 任务分支名称。
- 任务提交 ID。
- 合并提交 ID（如果产生）。
- `main` 是否已成功推送。
- 当前工作区是否干净。

## 6. 两人同时工作的规则

任务分支允许两人同时存在，但 `main` 的推送仍然可能发生竞争。AI 必须遵循：

1. 不在旧的 `main` 上创建任务分支；创建前先 `pull`。
2. 合并任务分支前再次 `pull`。
3. 一次推送被拒绝后不重试强制推送；先重新同步并检查分叉。
4. 两个任务修改同一个文件时，AI 必须在合并前告知用户可能冲突。
5. 根目录 `README.md`、`AGENTS.md`、`.gitignore` 和 `memories/` 是共享文件；同一时刻尽量只让一个任务修改它们。

用户不需要记住谁占用 `main`。AI 通过远端状态、分支图和推送结果判断是否可以继续。

## 7. 冲突处理

### 7.1 发现冲突时

立即执行：

```powershell
git status
```

然后向用户说明：

- 哪些文件冲突。
- 冲突发生在同步还是合并阶段。
- 哪些内容可以依据文件上下文判断。
- 哪些内容必须由用户决定。

### 7.2 可以明确判断的冲突

仅当一方是明显的格式、链接或机械性修改，且不会改变影片事实时，AI 才可以自行合并。这与第 4.3 节“不因 Git 冲突而自行选择一方覆盖另一方”一致：机械性判断仅限格式、链接等不改变内容事实的修改；涉及事实、数据或文稿内容的冲突一律归入 7.3。处理后执行：

```powershell
git add -- "已解决的文件路径"
git diff --cached --check
git commit --no-edit
```

### 7.3 无法判断的冲突

涉及标题、脚本内容、发布数据、确认状态、Changelog 或长期记忆时，AI 不得自行选择。可以取消尚未完成的合并：

```powershell
git merge --abort
```

取消后保留现场信息，等待用户决定。

## 8. 常见故障

遇到任何 Git 失败，先按三层分类定位，再决定处理方式：

| 层次 | 典型错误 | 最小诊断命令 |
| --- | --- | --- |
| 网络层 | `Could not resolve host`、`Failed to connect`、连接超时 | `curl.exe -s -o NUL -w "%{http_code}" --connect-timeout 8 https://github.com`（返回 `000` = 网络不通） |
| TLS 层 | `schannel: ... SEC_E_...`、`SSL certificate problem` | `git -c http.sslBackend=openssl ls-remote origin`（成功 = schannel 后端与本机网络环境不兼容，改用 `openssl`） |
| 认证层 | `could not read Username`、`Authentication failed` | `git credential fill`（输入 `protocol=https`、`host=github.com` 后观察是否返回凭证） |

分类原则：先诊断定位，再决定是否调整本机配置。确属本机环境问题（代理、TLS 后端、凭证）时，向用户说明诊断结论与调整方案，经确认后调整，不擅自更换代理设置。

### 8.1 pull 失败

AI 记录完整错误信息，检查：

```powershell
git status --short --branch
git branch -vv
git log --graph --decorate --oneline --all -n 20
```

不要改用破坏性命令。网络失败时先按本节开头的三层分类诊断定位；确属本机环境问题（代理、TLS 后端）时，向用户说明诊断结论与调整方案，经确认后调整，不擅自更换代理设置。

### 8.2 push 被拒绝

说明远端 `main` 在本地任务期间已经前进。执行：

```powershell
git pull origin main
```

如果当前正在合并或有冲突，先不要继续；向用户报告状态。严禁 `git push --force`。

### 8.3 工作区已有用户修改

AI 不得执行以下操作来“清理”：

```text
reset --hard
checkout -- <文件>
clean -fd
stash（除非用户明确批准）
```

先报告文件列表，询问用户是继续、拆分提交，还是暂时停止。

### 8.4 误在 main 上修改

如果尚未提交，AI 可以在确认工作区内容后创建任务分支，把修改带到任务分支：

```powershell
git switch -c task/recover-current-work
```

如果已经提交，不重写历史；记录提交 ID，先向用户说明，再决定是否继续合并。

## 9. 完成报告模板

每次 Git 操作结束，AI 用简体中文报告，不要求用户解读命令输出：

```text
Git 状态：已完成 / 未完成
当前分支：<分支名>
任务提交：<短提交 ID>
合并到 main：是 / 否
已推送远端：是 / 否
本次修改：<文件和内容摘要>
检查结果：<工作区是否干净、是否有冲突或剩余风险>
下一步：<需要用户确认的事项，或“无需操作”>
```

如果没有执行提交或推送，必须明确写出原因，不能使用“应该已经同步”这类推测性表述。

## 10. AI 的最小命令清单（速查版）

> 本清单是常用命令的速查汇总；与第 4、5 节冲突时，以第 4、5 节的完整流程为准。

开始任务：

```powershell
git status --short --branch
git switch main
git pull origin main
git switch -c task/<任务名>
```

用户确认后提交：

```powershell
git add -- "明确路径"
git diff --cached --check
git commit -m "<类型>：<对象> - <具体变更>"
git push -u origin task/<任务名>
```

本地合并并推送：

```powershell
git switch main
git pull origin main
git merge --no-ff --no-edit task/<任务名>
git push origin main
```

以上流程不包含 Pull Request，也不要求用户执行任何 Git 命令。
