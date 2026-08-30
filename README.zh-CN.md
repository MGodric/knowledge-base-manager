# Knowledge Base Manager

[English](README.md)

Knowledge Base Manager 是一个 Codex Skill，用于在多个项目之间维护持久、可由人类直接阅读的 Markdown 知识库。Markdown 是唯一可信内容源；即使不使用 agent 或专有笔记软件，也可以正常浏览和编辑。

当前支持知识库定位和初始化、知识整理、确定性审计，以及需要用户确认的便携备份、验证和恢复。

> **项目状态：**早期公开预览版。知识库 schema 和便携备份 manifest 当前均为版本 1。现有测试在 Windows PowerShell 7.6.4 上通过，但最低 PowerShell 7 版本仍需通过 CI 确认。

## 主要能力

- 初始化或接管以 `kb.yaml` 描述的 Markdown 知识库。
- 捕获笔记、提升正式条目、维护链接和归档旧内容。
- 审计 manifest、条目元数据、内部链接、来源信息、路径范围、重复 ID 和同步冲突迹象。
- 创建 `ReferenceComplete` 备份：包含完整知识库和每个明确登记的库外来源文件。
- 使用 SHA-256 和 manifest 验证备份完整性。
- 将自包含的 `Portable` 知识库恢复到另一台机器，不依赖原盘符和项目目录。

## 云同步

云同步由用户自行配置和管理。Skill 不依赖特定服务商：只要服务把知识库呈现为普通本地文件夹，Google Drive、OneDrive、Dropbox 及同类服务都可以使用；当前实现不调用任何云盘 API，也没有专有存储格式。

审计和备份前必须确保文件已经下载到本机。Skill 不会等待上传完成、证明另一台机器已同步、自动下载仅在线文件或合并同步冲突副本。知识库和备份的数据路径不能经过目录联接或符号链接。

## 当前限制

- 目前面向 Windows，必须通过 `pwsh` 使用 PowerShell 7；不支持 Windows PowerShell 5.1。
- `ReferenceComplete` 不会复制整个项目，只复制 Markdown 中明确登记的单个库外来源文件。
- 库外来源不会递归展开。
- `ProjectSnapshot` 备份和 `Relink` 恢复尚未实现。
- 普通相对 Markdown 链接是规范格式；Obsidian wiki-link 不是规范输入。
- 不验证远程 URL、标题锚点或云端同步状态，也不提供完整的秘密扫描和加密。
- SHA-256 用于包内完整性检查，不是发送者身份认证或数字签名。
- 备份和恢复假定来源与目标父目录由当前用户控制，且没有其他进程竞态替换目录；reparse 检查会阻止观察到的链接，但不是针对已有父目录写权限的本机恶意进程的沙箱。

## 仓库结构

```text
knowledge-base-manager/     可安装的 Codex Skill
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
tests/                      使用临时 fixture 的 PowerShell 测试
```

只有 `knowledge-base-manager/` 是 Skill 安装包；根目录 README 和测试不属于运行时依赖。本地设计资料统一放在已忽略的 `docs/`，不进入仓库。

## 安装

可以让 Codex 从公开 GitHub 仓库安装指定子目录：

```text
使用 $skill-installer 从以下地址安装 knowledge-base-manager：
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

也可以手动把 `knowledge-base-manager/` 复制到：

```text
$CODEX_HOME/skills/knowledge-base-manager
```

如果没有设置 `CODEX_HOME`，通常使用 `~/.codex/skills/knowledge-base-manager`。Skill 允许自动触发，也可以显式调用 `$knowledge-base-manager`。

## 快速使用

知识库初始化和接管建议交给 Codex，以便明确确认路径和写入授权：

```text
使用 $knowledge-base-manager 在 <绝对路径> 初始化知识库。
```

直接运行审计：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-audit.ps1 `
  -Root <knowledge-base-root>
```

生成只读备份计划：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-backup.ps1 `
  -Root <knowledge-base-root> `
  -Destination <backup-parent>
```

计划会列出所有来源的绝对路径、备份内路径、大小、UTC 修改时间和 SHA-256，并返回确定性的 `plan_digest`。用户检查完整清单后，使用同一 digest 执行：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-backup.ps1 `
  -Root <knowledge-base-root> `
  -Destination <backup-parent> `
  -Execute `
  -ConfirmedPlanDigest <confirmed-plan-digest>
```

任何路径、大小、时间、哈希或来源映射变化都会使确认失效，并要求重新检查。

验证和恢复时，目标目录必须尚不存在。恢复会先写入同级暂存目录，逐文件核对来源与副本哈希并审计结果，最后以不覆盖方式发布：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-verify-backup.ps1 `
  -Bundle <backup-parent>/portable-kb

pwsh -NoProfile -File <skill-directory>/scripts/kb-restore.ps1 `
  -Bundle <backup-parent>/portable-kb `
  -Destination <new-root> `
  -Execute
```

## 本机信息和隐私边界

| 位置 | 是否随知识库同步 | 内容 |
| --- | --- | --- |
| `$CODEX_HOME/knowledge-base-manager.local.yaml` | 否 | 当前机器的默认知识库根目录和项目映射。 |
| `<knowledge-base-root>/kb.yaml` | 是 | schema 版本及 `content_dir`、`entrypoint` 等相对路径；不得包含本机绝对路径。 |
| Markdown 条目 | 是 | 持久内容；可以有意包含带 `<!-- kb-external-local -->` 标记的本机库外来源绝对路径。 |
| 备份中的 `backup-manifest.json` | 取决于用户是否复制或同步备份 | 包含原始绝对路径等备份来源信息。 |

备份计划会暴露本机路径、文件名、大小、修改时间和哈希；备份包还会包含已登记库外来源的实际内容。不要未经单独检查就公开备份计划或备份包。

## Git 公开边界

公开 `.gitignore` 只包含所有开发者共同适用的规则：

- 本机配置文件 `knowledge-base-manager.local.yaml`；
- `.local/`、`.private/`、`private/` 和整个 `docs/` 中的私人开发记录；
- 备份包、计划、报告、暂存目录和测试产物。

只有某台机器需要的额外排除项应写入 `.git/info/exclude`，该文件不会被 push。必须发布的 Skill 文件不能靠 Git 忽略其中几行，必须使用中性示例并在发布前检查实际跟踪集合：

```powershell
git status --short --ignored
git ls-files
git grep -n -I -E '([A-Za-z]:[\\/]|/Users/|/home/)' -- .
```

`.gitignore` 不影响已经被跟踪的文件，也不能防止 `git add -f`。如果隐私内容已经被 push，仅新增忽略规则无法从 Git 历史中删除它。

## 兼容性

Skill 发行版本使用 SemVer；`kb.yaml` 中的知识库 schema 与 `backup-manifest.json` 中的备份 schema 独立编号，当前均为版本 1。

- 安装新版 Skill 不得自动迁移或改写现有知识库。
- 同一 schema 只增加可选字段，并保留未知字段；破坏性格式变化必须升级 schema。
- 破坏性格式变化必须升级 schema，并提供向后读取能力或显式、非破坏式迁移方案；CI 为受支持版本保留审计、备份和恢复 fixture。

目前只有 schema 1，因此尚无迁移命令。

## 后续计划

- 带显式跨机器项目根目录映射的 `Relink` 恢复。
- 可选的 `ProjectSnapshot` 和受控递归来源集合。
- 以 Markdown 为权威源生成 HTML/wiki 阅读层。
- 可选的签名备份 manifest，用于来源身份认证。
- 面向不可信共享目录威胁模型的可选 handle-relative 强化 I/O。
- Windows 以外的平台实现与 CI。
- schema 2 出现时加入版本化迁移 fixture 和工具。

## 开发与测试

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
```

测试只使用隔离的临时目录，不应访问个人知识库。

## 许可证

本项目采用 [MIT License](LICENSE)。
