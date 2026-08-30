# Knowledge Base Manager

[English](README.md) · [版本历史](CHANGELOG.md)

Knowledge Base Manager 是一个 Codex Skill，用于在多个项目之间维护持久、可由人类直接阅读的 Markdown 知识库。Markdown 是唯一可信内容源；即使不使用 agent 或专有笔记软件，也可以正常浏览和编辑。

当前支持知识库定位和初始化、知识整理、确定性审计，以及需要用户确认的便携备份、验证和恢复。

> **项目状态：**早期公开预览版。知识库 schema 和便携备份 manifest 当前均为版本 1。现有测试在 Windows PowerShell 7.6.4 上通过，但最低 PowerShell 7 版本仍需通过 CI 确认。

## 主要能力

- 初始化或接管以 `kb.yaml` 描述的 Markdown 知识库。
- 捕获笔记、提升正式条目、维护链接和归档旧内容，并要求公式使用统一的 KaTeX 兼容 Markdown 格式；审计器会检查高置信度的“公式误写为代码”问题。
- 审计 manifest、条目元数据、内部链接、来源信息、路径范围、重复 ID 和同步冲突迹象。
- 在不启动 Web 服务器、不要求用户安装第三方运行时的前提下，递归生成可在本机浏览的 HTML 阅读副本，以 SHA-256 增量重建，并通过随 Skill 分发的 KaTeX 静态资源离线渲染公式。
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
- 本机静态阅读层是生成物，不是备份；第一版不提供搜索、反向链接、关系图谱、鉴权、发布或库外链接内容复制。
- 公式渲染识别 Markdown 的 `$...$` 和 `$$...$$`；反引号代码跨度仍按代码处理，不会自动视为公式。审计器能够发现高置信度误用，但不能推断每个代码跨度的语义。
- SHA-256 用于包内完整性检查，不是发送者身份认证或数字签名。
- 备份和恢复假定来源与目标父目录由当前用户控制，且没有其他进程竞态替换目录；reparse 检查会阻止观察到的链接，但不是针对已有父目录写权限的本机恶意进程的沙箱。

## 仓库结构

```text
knowledge-base-manager/     可安装的 Codex Skill
  SKILL.md
  agents/openai.yaml
  assets/katex/             固定版本 KaTeX 0.18.1 浏览器文件及 MIT 许可证
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

一次调用递归生成或增量刷新本机静态 HTML 阅读副本：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-build-static.ps1 `
  -Root <knowledge-base-root> `
  -Destination <知识库之外的静态输出目录>
```

第一次构建会递归生成全部 Markdown 页面；以后通过目标目录中的
`.kb-static-manifest.json` 和 SHA-256，只重新生成新增、修改、缺失或被改动的页面，
未变化页面直接跳过。源 Markdown 删除后，只会移除旧 manifest 明确拥有的对应
HTML，不会删除目标目录中的无关文件。生成的入口页可通过 `file://` 直接在浏览器中打开。

如果明确需要忽略哈希跳过逻辑并重新生成全部受管理页面、目录索引及 KaTeX 资源，
可增加 `-Force`。强制模式仍会保留目标目录中的无关文件，并拒绝覆盖旧 manifest
未拥有的同名路径：

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-build-static.ps1 `
  -Root <knowledge-base-root> `
  -Destination <知识库之外的静态输出目录> `
  -Force
```

行内公式使用 `$...$`，独立公式使用 `$$...$$`。构建器会把固定版本的 KaTeX 浏览器资源复制到 `_assets/katex/`；整个过程离线运行，不调用 Node.js、npm、CDN 或本地服务器。

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

## 兼容性

`kb.yaml` 中的现行知识库 schema 与 `backup-manifest.json` 中的备份 schema 当前均为版本 1。安装新版 Skill 不会自动改写现有知识库；未来如有格式变化，将提供明确的迁移指引。

## 后续计划

- 带显式跨机器项目根目录映射的 `Relink` 恢复。
- 可选的 `ProjectSnapshot` 和受控递归来源集合。
- 为静态 HTML 阅读层增加可选搜索、反向链接、关系图谱和发布能力。
- 可选的签名备份 manifest，用于来源身份认证。
- 面向不可信共享目录威胁模型的可选 handle-relative 强化 I/O。
- Windows 以外的平台实现与 CI。

## 开发与测试

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
pwsh -NoProfile -File ./tests/test-kb-build-static.ps1
```

测试只使用隔离的临时目录，不应访问个人知识库。

## 第三方软件

Skill 随附 [KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1) 的预编译浏览器资源：JavaScript、CSS、自动渲染支持和字体。它们只用于生成的本机静态 HTML，以离线渲染公式。KaTeX 代码在阅读者的浏览器中执行；构建和运行过程不调用 Node.js、npm、pnpm、CDN 或本地服务器。

上游发行版、随附文件清单、发行资源 SHA-256 和来源记录见 [THIRD_PARTY.md](knowledge-base-manager/assets/katex/THIRD_PARTY.md)。KaTeX 使用 MIT License，其随附许可证文本位于 [knowledge-base-manager/assets/katex/LICENSE](knowledge-base-manager/assets/katex/LICENSE)。运行 Skill 需要 PowerShell 7，但不会随附 PowerShell 7；查看生成的 HTML 需要普通的现代浏览器，浏览器也不随附。

## 许可证

本项目采用 [MIT License](LICENSE)。随 Skill 分发的 KaTeX 浏览器资源在 `knowledge-base-manager/assets/katex/` 下另行保留其上游 MIT 许可证和发行来源记录。
