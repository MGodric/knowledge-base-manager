# Knowledge Base Manager

[简体中文](README.zh-CN.md) · [Changelog](CHANGELOG.md)

Knowledge Base Manager is a skill designed for AI coding assistants (Codex / Antigravity) to maintain a durable, cross-project personal knowledge base. Using standard plain-text Markdown as the sole source of truth with no proprietary database requirements, it captures, promotes, and audits knowledge across development projects, and generates a standalone static reading website with an offline interactive relationship graph.

> **Status:** Public preview (v0.1.5a). Knowledge-base and portable-backup manifest schemas are version `1`.

---

## Design Goals

- **Standard Plain-Text Format**: The knowledge base consists strictly of standard Markdown files. It can be viewed and edited using standard text editors independently of AI assistants or proprietary software.
- **Cross-Project Synthesis**: Extract technical decisions, architectural patterns, and troubleshooting notes across repositories into reusable knowledge entries.
- **Human and Agent Usability**: Structured for human readability while maintaining explicit boundaries and schema metadata for accurate AI retrieval.
- **Zero External Database or Service Dependencies**: Built on standard plain-text formats with no proprietary databases, PowerShell, or background web services. Pure Python powers the entire authoring, reading, static site generation, and backup/restore toolset.

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
- **Usage Feedback (Conditional)**
  - **Event-Driven Issue Recording**: Record locatable observations anchored to entries or operations only when concrete failures (retrieval omission, reading misuse, update omission, tooling failure) are encountered. No background daemon, automated sweeps, or ungrounded quality claims.

---

## Requirements

- **Operating System**: Windows (locally verified); Ubuntu 24.04 x86_64 on ext4 with Python 3.12.3 (native tests passed). The full CI matrix remains pending. macOS compatibility is deferred and is outside the current acceptance and CI scope.
- **Python**: Python 3.12+ (CPython 3.12 or 3.14 recommended) for running the CLI toolset (`scripts/kb.py`: resolve, inspect, search, read, audit, build-static, backup, verify-backup, restore).
- **Runtime Dependencies**: Pure-Python runtime dependencies (`PyYAML 6.0.3`, `markdown-it-py 4.2.0`, `mdit-py-plugins 0.6.1`, `mdurl 0.1.2`) are bundled directly within `knowledge-base-manager/vendor/`. End users do not need `pip install`, virtual environments, external packages, Node.js, databases, or background services at runtime.

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
| Usage feedback (Anchor / Trigger) | Supported | Event-triggered workflow recording; no background daemon or quality claims. |
| Antigravity native integration | Planned | Direct adapter for Antigravity skills, rules, and workflows. |
| ProjectSnapshot backup / Relink restore | Planned | Strategy for whole-repository external snapshots is under design. |
| Full-text search UI & backlinks | Planned | Exploring offline, serverless client-side implementations. |
| Linux runtime | Verified on Ubuntu 24.04 x86_64 | Native tests passed on ext4 with Python 3.12.3 and Node 22; other configurations and the full CI matrix remain unverified. |
| macOS compatibility | Deferred | Outside the current acceptance and CI scope; no support claim. |

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
- [Usage Feedback (usage-feedback.md)](knowledge-base-manager/references/usage-feedback.md)
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

Python-based tools and structural validation use a project-local `.venv` and pinned
[development dependencies](requirements-dev.txt). See [development setup and the
shared Codex/Gemini commands](DEVELOPMENT.md). Python (with PyYAML and markdown-it-py) powers
the entire CLI toolset (`kb.py`), including authoring, reading, static site generation, and backup/restore.

```text
knowledge-base-manager/   # Distributable Skill source
tests/                    # Automated Python and Node.js test suites
```

All tests run against isolated temporary directories and never alter live knowledge bases:

```bash
# 1. Run all test suites:
python -X utf8 ./tests/run-all-tests.py

# 2. Or run individual Python suites:
python -X utf8 ./tests/test-kb-python-parser.py
python -X utf8 ./tests/test-kb-python-query.py
python -X utf8 ./tests/test-kb-python-audit.py
python -X utf8 ./tests/test-kb-python-workflow.py
python -X utf8 ./tests/test-kb-python-backup.py
python -X utf8 ./tests/test-kb-python-static.py

# 3. Node.js DOM component unit tests:
node ./tests/test-kb-static-toc.cjs
node ./tests/test-kb-static-copy.cjs
node ./tests/test-kb-static-graph-component.cjs
```

> *Note: Node.js is used only for development unit testing with a simulated DOM. Installing or running the Skill does not require Node.js.*

---

## License

Licensed under the [MIT License](LICENSE). Offline static reading bundles [KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1) browser assets; see its [third-party attribution](knowledge-base-manager/assets/katex/THIRD_PARTY.md).
