# Knowledge Base Manager

[English](README.md) · [版本历史](CHANGELOG.md)

Knowledge Base Manager 是面向 AI 编程助手（Codex / Antigravity）设计的跨项目个人知识库管理 Skill。它以标准纯文本 Markdown 作为唯一事实源，不依赖专有笔记软件或外部数据库，用于在日常软件开发中沉淀、整理和检索知识，并支持生成包含离线关系图谱的静态阅读站点。

> **当前状态**：公开预览版（v0.2.0）。知识库与便携备份 Manifest Schema 版本均为 `1`。

---

## 设计目标

- **标准纯文本格式**：知识库完全由标准 Markdown 文件构成，脱离 AI 助手或特定软件后，仍可直接使用通用文本编辑器查阅与编辑。
- **跨项目知识提炼**：将分散在各个开发项目中的技术方案、排查记录与规范沉淀为可跨项目复用的知识条目。
- **人机协同可读**：针对人类阅读与 AI 检索进行结构规范化，兼顾文章可读性与模型检索边界。
- **零外部数据库与后台服务依赖**：基于标准纯文本格式与离线 Web 标准构建，无需专有数据库、PowerShell 或常驻服务。纯 Python 驱动全套本地写作、检索、静态站点生成与便携备份工具集。

---

## 核心功能

- **知识捕获与条目提炼**
  - **随手记录（Capture）**：快速保存临时笔记与调试日志至收件箱（Inbox），显式标注来源项目，未明确归属时自动归入本地化兜底分类（如“杂项”）。
  - **正式提炼（Promote）**：将草稿规范化提炼为结构完整的正式知识条目；严格基于授权源材料范围进行总结，严禁基于模型先验记忆无依据扩写细节，知识库内补充显式标注来源标签。
  - **跨项目知识综合（Project Synthesis）**：在明确指示下综合多个项目的关联知识，生成带问题导向、来源溯源与审阅记录的专题条目。
- **结构审计**
  - 执行 `kb-audit` 检查死链、元数据规范、路径越界、重复 ID 以及云同步冲突文件。
- **静态站点与关系图谱**
  - **离线静态阅读层**：直接本地双击 HTML 文件浏览，无需启动 Web 服务器。包含自适应排版、KaTeX 公式渲染、文章目录导航、代码块复制、显式收录区嵌套列表层级展示，以及首页右上角带离线预渲染待办计数徽标的收件箱直达按钮。
  - **交互式 2D 关系图谱**：基于原生 SVG 与 CSS 实现，自动隔离草稿与归档节点。提供首页内嵌、正文全屏弹窗与独立导航页，支持层级展开/收起、节点邻域聚焦（Ego Network）与离线中英双语界面。
- **便携备份与恢复**
  - **`ReferenceComplete` 备份**：归档知识库及已显式登记的外部关联源码，并计算 SHA-256 校验和。
  - **规划与确认机制**：备份规划为只读操作，生成明确的文件清单与摘要哈希；需用户二次确认且数据无漂移后执行导出。
  - **`Portable` 恢复**：解压恢复至未存在的目标目录，并自动执行完整性校验与审计。
- **使用反馈机制（按需触发）**
  - **事件驱动记录**：仅在实际观察到具体问题（检索遗漏、阅读误用、更新遗漏、工具故障）时记录带锚点的简短观察；不引入后台常驻服务、不发起额外全库扫描、不作无依据的质量保证声称。

---

## 运行环境要求

- **运行平台**：Windows；Ubuntu 24.04 x86_64 也已通过原生测试。
- **运行环境**：Python 3.12+；所需 Python 包已随 Skill 附带。

---

## 安装说明

在对话中告知 AI 助手通过 Skill 安装工具安装：

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
| 实际使用反馈机制（Anchor / Trigger） | 已支持 | 事件驱动的短记录机制，无后台常驻进程与额外扫描。 |
| Antigravity 原生适配 | 规划中 | 适配 Antigravity 工作流与规则/Skill 标准。 |
| ProjectSnapshot 备份 / Relink 恢复 | 规划中 | 针对大型外部项目整库快照的策略仍在设计中。 |
| 全文搜索索引 UI 与反向链接面板 | 规划中 | 后续在保持纯离线、无后端的前提下逐步演进。 |
| Linux 原生支持 | Ubuntu 24.04 x86_64 已验证 | ext4 / Python 3.12.3 / Node 22 原生测试通过；其他配置及完整 CI 矩阵仍待验证。 |

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
- [使用反馈机制 (usage-feedback.md)](knowledge-base-manager/references/usage-feedback.md)
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

Python 核心工具与结构验证统一使用项目 `.venv` 与固定版本的[开发依赖](requirements-dev.txt)。
初始化、验证命令与 Codex/Gemini 共用约定见[开发环境说明](DEVELOPMENT.md)。
Python（搭配 PyYAML 与 markdown-it-py）驱动全套命令行工具集（`kb.py`），涵盖写作、阅读、静态站点构建与备份恢复。

```text
knowledge-base-manager/   # 实际发布的 Skill 源码
tests/                    # 自动化测试脚本（Python + Node.js 离线环境）
```

测试均在隔离的临时目录中运行，绝不触碰真实知识库：

```bash
# 1. 运行全部测试套件：
python -X utf8 ./tests/run-all-tests.py

# 2. 或单独运行 Python 测试：
python -X utf8 ./tests/test-kb-python-parser.py
python -X utf8 ./tests/test-kb-python-query.py
python -X utf8 ./tests/test-kb-python-audit.py
python -X utf8 ./tests/test-kb-python-workflow.py
python -X utf8 ./tests/test-kb-python-backup.py
python -X utf8 ./tests/test-kb-python-static.py

# 3. Node.js DOM 组件交互单元测试：
node ./tests/test-kb-static-toc.cjs
node ./tests/test-kb-static-copy.cjs
node ./tests/test-kb-static-graph-component.cjs
```

> *注：Node.js 仅用于开发阶段模拟 DOM 单元测试，安装和运行此 Skill 本身不需要安装 Node.js。*

---

## 许可证 (License)

本项目采用 [MIT 许可证](LICENSE)。
内置的离线静态阅览资源包含 [KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1)，遵循其原有开源许可，详见[第三方归属说明](knowledge-base-manager/assets/katex/THIRD_PARTY.md)。
