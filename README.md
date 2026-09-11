# Knowledge Base Manager

[简体中文](README.zh-CN.md) · [Changelog](CHANGELOG.md)

Knowledge Base Manager is a skill designed for AI coding assistants (Codex / Antigravity) to maintain a durable, cross-project personal knowledge base. Using standard plain-text Markdown as the sole source of truth with no proprietary database requirements, it captures, promotes, and audits knowledge across development projects, and generates a standalone static reading website with an offline interactive relationship graph.

> **Status:** Public preview (v0.1.5a). Knowledge-base and portable-backup manifest schemas are version `1`.

---

## Design Goals

- **Standard Plain-Text Format**: The knowledge base consists strictly of standard Markdown files. It can be viewed and edited using standard text editors independently of AI assistants or proprietary software.
- **Cross-Project Synthesis**: Extract technical decisions, architectural patterns, and troubleshooting notes across repositories into reusable knowledge entries.
- **Human and Agent Usability**: Structured for human readability while maintaining explicit boundaries and schema metadata for accurate AI retrieval.
- **Zero External Runtime Dependencies**: Built with PowerShell 7 and native static web standards. Requires no Python, Node.js, databases, or web services at runtime.

---

## Key Features

- **Capture & Knowledge Promotion**
  - **Capture**: Save transient notes and debugging logs into an Inbox with explicit project origin tracking and localized fallback categorization (`Miscellaneous` / `杂项`).
  - **Promote**: Refine raw drafts into structured knowledge entries grounded strictly in authorized sources, prohibiting ungrounded model extrapolations and explicitly tagging intra-knowledge-base additions.
  - **Project Synthesis**: On explicit request, synthesize related knowledge across multiple projects with question-driven outlines and verified provenance.
- **Structure Audit**
  - Run `kb-audit` to detect broken links, missing metadata, path containment escapes, duplicate IDs, and cloud synchronization conflict files.
- **Static Site & Relationship Graph**
  - **Offline Static Reader**: Open HTML files directly in a browser without running a local web server. Includes responsive layout, offline KaTeX math rendering, table of contents navigation, code copying, curated collection hierarchy with nested lists, and a homepage Inbox header button with an offline pre-rendered count badge.
  - **Interactive 2D Relationship Graph**: Zero-dependency native SVG and CSS implementation with draft and archive isolation. Provides homepage embedding, reading-page overlay modals, and a standalone navigation page. Supports branch expanding/collapsing, 1-hop ego-network focus, and offline bilingual (EN/ZH) interface.
- **Portable Backup & Restore**
  - **`ReferenceComplete` Backup**: Archives the knowledge base alongside explicitly registered external source files with SHA-256 checksums.
  - **Plan & Confirm Workflow**: Read-only planning produces a deterministic file list and digest; execution requires confirmation with drift detection.
  - **`Portable` Restore**: Restores the bundle into a clean destination directory with integrity and structure verification.

---

## Requirements

- **Operating System**: Windows
- **PowerShell**: PowerShell 7 or later (`pwsh`; Windows PowerShell 5.1 is not supported)
- **Runtime Dependencies**: No Python, Node.js, database, or third-party PowerShell modules required at runtime.

---

## Installation

Ask your AI assistant to install via the Skill installer:

```text
Use $skill-installer to install knowledge-base-manager from
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

Or manually copy the `knowledge-base-manager/` folder into your Codex Skills directory:
`$CODEX_HOME/skills/knowledge-base-manager` (typically `~/.codex/skills/knowledge-base-manager`).

---

## Quick Start

Ask your AI assistant naturally in the chat:

```text
# 1. Initialize
Use $knowledge-base-manager to initialize a knowledge base at <absolute path>.

# 2. Capture a quick note
Use $knowledge-base-manager to capture this note in <knowledge-base path>: <note content>.

# 3. Promote into a durable entry
Use $knowledge-base-manager to promote <draft path or content> into a durable entry.

# 4. Synthesize knowledge across projects
Use $knowledge-base-manager to run Project Synthesis for <project A> and <project B>.

# 5. Audit and build local static reader
Use $knowledge-base-manager to audit <knowledge-base path> and build a separate local static HTML reader.

# 6. Plan a backup (read-only)
Use $knowledge-base-manager to generate a ReferenceComplete backup plan for <knowledge-base path>; do not execute it yet.

# 7. Restore from backup
Use $knowledge-base-manager to verify <backup bundle path> and restore it to the new directory <target path>.
```

---

## Feature Matrix

| Capability | Status | Description |
| --- | --- | --- |
| Note capture, promotion, and linking | Supported | Standard Markdown with tags, types, and frontmatter. |
| Cross-project synthesis | Supported | Explicitly triggered with evidence tracking and review records. |
| Deterministic audit | Supported | Scans broken links, orphaned entries, and format/path violations. |
| Static HTML reading site | Supported | Responsive layout, KaTeX math, responsive TOC, code copy. |
| Offline 2D relationship graph | Supported | Inline embedding, overlay modal, ego-focus, bilingual controls. |
| ReferenceComplete backup & restore | Supported | SHA-256 verification, anti-drift confirmation, external sources. |
| Antigravity native integration | Planned | Direct adapter for Antigravity skills, rules, and workflows. |
| ProjectSnapshot backup / Relink restore | Planned | Strategy for whole-repository external snapshots is under design. |
| Full-text search UI & backlinks | Planned | Exploring offline, serverless client-side implementations. |
| Cross-platform support (Linux / macOS) | Planned | Awaiting cross-platform runtime and path abstraction work. |

---

## Safety & Design Boundaries

1. **Markdown as Single Truth**: Static HTML pages are read-only derived artifacts. Modify knowledge content directly in the Markdown source files.
2. **Cloud Synchronization**: The knowledge base can be stored in OneDrive, Google Drive, or Dropbox; ensure files are fully hydrated locally before running audits or backups to prevent missing-file errors.
3. **Explicit External Registration**: Backups copy only explicitly registered external source files, never recursively scanning or packaging entire project directories.
4. **Two-Stage Safety Gate**: Backup planning is strictly read-only; execution requires an identical confirmed digest to prevent accidental overwrites or data drift.

---

## Documentation

- [Skill Entrypoint (SKILL.md)](knowledge-base-manager/SKILL.md)
- [Workflows (workflows.md)](knowledge-base-manager/references/workflows.md)
- [Static Site & Graph (static-site.md)](knowledge-base-manager/references/static-site.md)
- [Project Synthesis (project-synthesis.md)](knowledge-base-manager/references/project-synthesis.md)
- [Knowledge Writing (knowledge-writing.md)](knowledge-base-manager/references/knowledge-writing.md)
- [Writing Examples (knowledge-writing-examples.md)](knowledge-base-manager/references/knowledge-writing-examples.md)
- [Knowledge Model (knowledge-model.md)](knowledge-base-manager/references/knowledge-model.md)
- [Markdown Format (markdown-format.md)](knowledge-base-manager/references/markdown-format.md)
- [Audit Rules (audit-rules.md)](knowledge-base-manager/references/audit-rules.md)
- [Reading Navigation (navigation.md)](knowledge-base-manager/references/navigation.md)
- [Backup and Restore (backup-restore.md)](knowledge-base-manager/references/backup-restore.md)
- [Safety (safety.md)](knowledge-base-manager/references/safety.md)

---

## Development & Testing

```text
knowledge-base-manager/   # Distributable Skill source
tests/                    # Automated PowerShell and Node.js test suites
```

All tests run against isolated temporary directories and never alter live knowledge bases:

```powershell
# 1. Root resolution and audit
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1

# 2. Backup and restore lifecycle
pwsh -NoProfile -File ./tests/test-kb-backup.ps1

# 3. Static site builder and curated navigation
pwsh -NoProfile -File ./tests/test-kb-build-static.ps1
pwsh -NoProfile -File ./tests/test-kb-static-navigation.ps1

# 4. Graph model and interactive component
pwsh -NoProfile -File ./tests/test-kb-static-graph.ps1
node ./tests/test-kb-static-graph-component.cjs

# 5. Table of contents and code-copy interactions
node ./tests/test-kb-static-toc.cjs
node ./tests/test-kb-static-copy.cjs
```

> *Note: Node.js is used only for development unit testing with a simulated DOM. Installing or running the Skill does not require Node.js.*

---

## License

Licensed under the [MIT License](LICENSE). Offline static reading bundles [KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1) browser assets; see its [third-party attribution](knowledge-base-manager/assets/katex/THIRD_PARTY.md).
