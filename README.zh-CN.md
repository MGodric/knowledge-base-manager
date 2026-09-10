# Knowledge Base Manager

[English](README.md) · [版本历史](CHANGELOG.md)

Knowledge Base Manager 是面向 AI 编程助手（Codex / Antigravity）设计的跨项目个人知识库管理 Skill。它以标准纯文本 Markdown 作为唯一事实源，不依赖专有笔记软件或外部数据库，用于在日常软件开发中沉淀、整理和检索知识，并支持生成包含离线关系图谱的静态阅读站点。

> **当前状态**：公开预览版（v0.1.5）。知识库与便携备份 Manifest Schema 版本均为 `1`。

---

## 设计目标

- **标准纯文本格式**：知识库完全由标准 Markdown 文件构成，脱离 AI 助手或特定软件后，仍可直接使用通用文本编辑器查阅与编辑。
- **跨项目知识提炼**：将分散在各个开发项目中的技术方案、排查记录与规范沉淀为可跨项目复用的知识条目。
- **人机协同可读**：针对人类阅读与 AI 检索进行结构规范化，兼顾文章可读性与模型检索边界。
- **零外部服务依赖**：基于 PowerShell 7 与原生静态 Web 技术实现，运行时无需安装 Python、Node.js、数据库或网络服务。

---

## 核心功能

- **知识捕获与条目提炼**
  - **随手记录（Capture）**：记录开发过程中的临时想法与排查笔记，写入 Inbox 或项目草稿。
  - **正式提炼（Promote）**：将草稿规范化提炼为结构完整的正式知识条目，明确核心结论、原理机制与应用边界。
  - **跨项目知识综合（Project Synthesis）**：在明确指示下综合多个项目的关联知识，生成带问题导向、来源溯源与审阅记录的专题条目。
- **结构审计**
  - 执行 `kb-audit` 检查死链、元数据规范、路径越界、重复 ID 以及云同步冲突文件。
- **静态站点与关系图谱**
  - **离线静态阅读层**：直接本地双击 HTML 文件浏览，无需启动 Web 服务器。包含自适应排版、KaTeX 公式渲染、文章目录导航与代码块复制。
  - **交互式 2D 关系图谱**：基于原生 SVG 与 CSS 实现。提供首页内嵌、正文全屏弹窗与独立导航页，支持层级展开/收起、节点邻域聚焦（Ego Network）与离线中英双语界面。
- **便携备份与恢复**
  - **`ReferenceComplete` 备份**：归档知识库及已显式登记的外部关联源码，并计算 SHA-256 校验和。
  - **规划与确认机制**：备份规划为只读操作，生成明确的文件清单与摘要哈希；需用户二次确认且数据无漂移后执行导出。
  - **`Portable` 恢复**：解压恢复至未存在的目标目录，并自动执行完整性校验与审计。

---

## 运行环境要求

- **操作系统**：Windows
- **PowerShell**：PowerShell 7 或更高版本（命令行直接调用 `pwsh`，不支持 Windows PowerShell 5.1）
- **运行时依赖**：不需要安装 Python、Node.js、数据库或第三方 PowerShell 模块。

---

## 安装方式

让 AI 助手调用安装器安装：

```text
使用 $skill-installer 从以下地址安装 knowledge-base-manager：
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

或者手动将仓库中的 `knowledge-base-manager/` 目录复制到 Codex Skills 目录：
`$CODEX_HOME/skills/knowledge-base-manager`（通常位于 `~/.codex/skills/knowledge-base-manager`）。

---

## 常用指令速查

在对话中直接告诉 AI 助手你的需求即可：

```text
# 1. 初始化
使用 $knowledge-base-manager 在 <绝对路径> 初始化一个知识库。

# 2. 捕获灵感或笔记
使用 $knowledge-base-manager 将这段笔记记录到知识库：<笔记内容>。

# 3. 提炼正式知识条目
使用 $knowledge-base-manager 将 <草稿路径或内容> 提炼为正式知识条目。

# 4. 跨项目知识综合
使用 $knowledge-base-manager 对 <项目A> 和 <项目B> 的相关实现进行知识提炼与综合。

# 5. 质量审计与构建离线阅读站点
使用 $knowledge-base-manager 检查知识库，并全量生成静态 HTML 阅览网站。

# 6. 便携备份（先查看计划）
使用 $knowledge-base-manager 生成一份 ReferenceComplete 备份计划；先不要执行。

# 7. 从备份还原
使用 $knowledge-base-manager 验证 <备份包路径> 并将其恢复到新目录 <目标路径>。
```

---

## 功能支持现状

| 功能领域 | 当前状态 | 说明 |
| --- | --- | --- |
| 知识捕获、提升与链接维护 | 已支持 | 标准 Markdown 语法，支持标签、类型与元数据。 |
| 跨项目知识综合（Project Synthesis） | 已支持 | 需明确触发；带证据溯源与审阅记录。 |
| 确定性质量审计（Audit） | 已支持 | 扫描死链、孤立条目、格式与路径违规。 |
| 离线静态阅读站点构建 | 已支持 | 自适应布局、KaTeX 公式、响应式目录、代码复制。 |
| 离线交互式 2D 关系图谱 | 已支持 | 首页内嵌、正文全屏弹窗、邻域聚焦特写、中英双语自适应。 |
| ReferenceComplete 备份与恢复 | 已支持 | SHA-256 校验、防漂移二次确认、便携外部来源迁移。 |
| Antigravity 原生适配 | 规划中 | 适配 Antigravity 工作流与规则/Skill 标准。 |
| ProjectSnapshot 备份 / Relink 恢复 | 规划中 | 针对大型外部项目整库快照的策略仍在设计中。 |
| 全文搜索索引 UI 与反向链接面板 | 规划中 | 后续在保持纯离线、无后端的前提下逐步演进。 |
| 跨平台原生支持（Linux / macOS） | 规划中 | 待完成跨平台运行时与路径抽象适配。 |

---

## 安全与设计边界

1. **Markdown 为唯一事实源**：静态 HTML 为只读派生副本，修改知识内容应直接编辑 Markdown 源文件。
2. **云同步边界**：知识库支持存放在 OneDrive、Google Drive 等同步盘中，但执行审计或备份前需确保相关文件已完全下载至本地（避免仅在线占位文件导致读取失败）。
3. **外部引用显式登记**：备份仅复制正文中显式登记的外部项目源文件，不递归扫描或打包宿主工程目录。
4. **两阶段安全防护**：备份规划严格只读；只有哈希一致且用户确认后才执行导出，防止误覆盖与数据漂移。

---

## 详细参考文档

- [Skill 主说明 (SKILL.md)](knowledge-base-manager/SKILL.md)
- [核心工作流指南 (workflows.md)](knowledge-base-manager/references/workflows.md)
- [静态站点与图谱说明 (static-site.md)](knowledge-base-manager/references/static-site.md)
- [知识综合工作流 (project-synthesis.md)](knowledge-base-manager/references/project-synthesis.md)
- [知识写作规范 (knowledge-writing.md)](knowledge-base-manager/references/knowledge-writing.md)
- [写作样文参考 (knowledge-writing-examples.md)](knowledge-base-manager/references/knowledge-writing-examples.md)
- [知识组织模型 (knowledge-model.md)](knowledge-base-manager/references/knowledge-model.md)
- [Markdown 格式要求 (markdown-format.md)](knowledge-base-manager/references/markdown-format.md)
- [审计规则与错误排查 (audit-rules.md)](knowledge-base-manager/references/audit-rules.md)
- [阅读导航协议 (navigation.md)](knowledge-base-manager/references/navigation.md)
- [备份与恢复方案 (backup-restore.md)](knowledge-base-manager/references/backup-restore.md)
- [安全边界与防护 (safety.md)](knowledge-base-manager/references/safety.md)

---

## 开发与测试

```text
knowledge-base-manager/   # 实际发布的 Skill 源码
tests/                    # 自动化测试脚本（PowerShell + Node.js 离线环境）
```

测试均在隔离的临时目录中运行，绝不触碰真实知识库：

```powershell
# 1. 核心解析与审计
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1

# 2. 备份与恢复全链路
pwsh -NoProfile -File ./tests/test-kb-backup.ps1

# 3. 静态站点构建与导航
pwsh -NoProfile -File ./tests/test-kb-build-static.ps1
pwsh -NoProfile -File ./tests/test-kb-static-navigation.ps1

# 4. 图谱模型与交互组件
pwsh -NoProfile -File ./tests/test-kb-static-graph.ps1
node ./tests/test-kb-static-graph-component.cjs

# 5. 文章目录与复制代码交互
node ./tests/test-kb-static-toc.cjs
node ./tests/test-kb-static-copy.cjs
```

> *注：Node.js 仅用于开发阶段模拟 DOM 单元测试，安装和运行此 Skill 本身不需要安装 Node.js。*

---

## 许可证 (License)

本项目采用 [MIT 许可证](LICENSE)。
内置的离线静态阅览资源包含 [KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1)，遵循其原有开源许可，详见[第三方归属说明](knowledge-base-manager/assets/katex/THIRD_PARTY.md)。
