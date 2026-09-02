# Knowledge Base Manager

[English](README.md) · [版本历史](CHANGELOG.md)

Knowledge Base Manager 是一个 Codex Skill，用于在多个项目之间维护持久、可由人类直接阅读的 Markdown 知识库。Markdown 是唯一的事实源：即使不使用 agent 或专有笔记软件，知识库仍可阅读和编辑。

> **状态：**早期公开预览版。知识库与便携备份 manifest schema 当前均为版本 1。

## 功能

- 初始化或接管由 `kb.yaml` 描述的知识库。
- 使用规范的 KaTeX 兼容 Markdown 捕获笔记、提升持久条目、维护链接和归档旧内容。
- **仅在明确请求时**运行 Project Synthesis 来协调多个来源或项目，并保留可审计的证据边界和审阅记录。
- 审计 manifest、元数据、链接、来源信息、路径范围、重复 ID 及可能的同步冲突痕迹。
- 生成可离线递归浏览的静态 HTML 阅读副本，并以随附 KaTeX 渲染公式；无需 Web 服务器。
- 创建和验证 `ReferenceComplete` 备份，其中包含知识库及显式登记的库外来源文件；可将其恢复为 `Portable` 知识库。

## 要求

- Codex 和 Windows
- PowerShell 7 或更高版本，通过 `pwsh` 调用（不支持 Windows PowerShell 5.1）
- 运行时不需要 Python、Node.js、数据库或云服务商 API

## 安装

让 Codex 使用安装器：

```text
使用 $skill-installer 从以下地址安装 knowledge-base-manager：
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

也可手动将 `knowledge-base-manager/` 复制到
`$CODEX_HOME/skills/knowledge-base-manager`（通常为
`~/.codex/skills/knowledge-base-manager`）。

## 快速开始

```text
使用 $knowledge-base-manager 在 <绝对路径> 初始化知识库。

使用 $knowledge-base-manager 将以下笔记捕获到 <知识库路径>：<笔记>。

使用 $knowledge-base-manager 将 <草稿条目> 提升为持久条目。

使用 $knowledge-base-manager 对 <项目或来源> 运行 Project Synthesis。

使用 $knowledge-base-manager 审计 <知识库路径>，并构建独立的本机静态 HTML 阅读副本。

使用 $knowledge-base-manager 为 <知识库路径> 生成只读 ReferenceComplete 备份计划；暂不执行。

使用 $knowledge-base-manager 验证 <Portable 备份包>，并将其恢复到不存在的新目录 <路径>。
```

## 已支持与计划中

目前，Skill 在 Windows 上支持上述工作流，包括 `ReferenceComplete` 备份和
`Portable` 恢复。`ProjectSnapshot` 备份与 `Relink` 恢复正在规划但尚不可用；专用搜索索引或界面、反向链接、关系图谱和跨平台支持也尚未提供。

## 安全边界

- 云同步由用户自行配置；审计或备份前，应先将仅在线文件下载到本机。Skill 不证明远程同步状态，也不处理服务商冲突副本。
- 每个库外来源文件都必须在 Markdown 中显式登记。`ReferenceComplete` 备份绝不递归复制整个项目。
- 备份计划为只读操作，并展示完整、带路径标记的文件清单。执行须经第二次、完全一致的确认；输入变化后必须重新规划。
- 静态 HTML 是生成的本机阅读层，不是备份。
- Skill 不保证秘密扫描、远程同步、许可验证、加密，或备份的签名/身份认证。

## 文档

- [Skill 入口](knowledge-base-manager/SKILL.md)
- [工作流](knowledge-base-manager/references/workflows.md)
- [Project Synthesis](knowledge-base-manager/references/project-synthesis.md)
- [知识模型](knowledge-base-manager/references/knowledge-model.md)
- [Markdown 格式](knowledge-base-manager/references/markdown-format.md)
- [审计规则](knowledge-base-manager/references/audit-rules.md)
- [静态站点](knowledge-base-manager/references/static-site.md)
- [备份与恢复](knowledge-base-manager/references/backup-restore.md)
- [安全](knowledge-base-manager/references/safety.md)
- [版本历史](CHANGELOG.md)

## 开发

```text
knowledge-base-manager/  可安装的 Skill 源码
tests/                   可丢弃的 PowerShell fixture
```

只有 `knowledge-base-manager/` 会被安装。测试使用隔离的临时知识库、项目、备份和恢复目标：

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
pwsh -NoProfile -File ./tests/test-kb-build-static.ps1
```

## 许可证

本项目采用 [MIT License](LICENSE)。离线静态阅读会随附
[KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1) 浏览器资源；见其[第三方归属说明](knowledge-base-manager/assets/katex/THIRD_PARTY.md)。
