# Knowledge Base Manager

[简体中文](README.zh-CN.md) · [Changelog](CHANGELOG.md)

Knowledge Base Manager is a Codex Skill for maintaining a durable,
human-readable Markdown knowledge base across projects. Markdown is the only
source of truth: it remains readable and editable without an agent or a
proprietary notes app.

> **Status:** early public preview. The knowledge-base and portable-backup
> manifest schemas are version 1.

## Features

- Initialize or adopt a `kb.yaml`-described knowledge base.
- Capture notes, promote durable entries, maintain links, and archive obsolete
  material using canonical, KaTeX-compatible Markdown.
- Run **Project Synthesis only when explicitly requested** to reconcile sources
  or projects, with an auditable evidence boundary and review record.
- Audit manifests, metadata, links, provenance, path containment, duplicate
  IDs, and likely synchronization-conflict artifacts.
- Build an offline, recursively browsable static HTML reading copy with bundled
  KaTeX formula rendering; no web server is required.
- Create and verify `ReferenceComplete` backups, including the knowledge base
  and explicitly registered external source files; restore them as `Portable`
  knowledge bases.

## Requirements

- Codex and Windows
- PowerShell 7 or later, invoked as `pwsh` (not Windows PowerShell 5.1)
- No Python, Node.js, database, or cloud-provider API runtime dependency

## Installation

Ask Codex to use the installer:

```text
Use $skill-installer to install knowledge-base-manager from
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

Or copy `knowledge-base-manager/` manually to
`$CODEX_HOME/skills/knowledge-base-manager` (usually
`~/.codex/skills/knowledge-base-manager`).

## Quick start

```text
Use $knowledge-base-manager to initialize a knowledge base at <absolute path>.

Use $knowledge-base-manager to capture this note in <knowledge-base path>: <note>.

Use $knowledge-base-manager to promote <draft entry> into a durable entry.

Use $knowledge-base-manager to run Project Synthesis for <projects or sources>.

Use $knowledge-base-manager to audit <knowledge-base path> and build a separate local static HTML reader.

Use $knowledge-base-manager to make a read-only ReferenceComplete backup plan for <knowledge-base path>; do not execute it yet.

Use $knowledge-base-manager to verify <Portable bundle> and restore it to the new, nonexistent directory <path>.
```

## Supported and planned

Today, the Skill supports the workflows above on Windows, including
`ReferenceComplete` backup and `Portable` restore. `ProjectSnapshot` backup and
`Relink` restore are planned but unavailable. A dedicated search index or UI,
backlinks, graph navigation, and cross-platform support are also not yet
provided.

## Safety boundaries

- Configure cloud synchronization yourself; hydrate remote-only files locally
  before audit or backup. The Skill neither proves remote sync nor resolves
  provider conflicts.
- Register each external source file explicitly in Markdown. A
  `ReferenceComplete` backup never recursively copies a project.
- Backup planning is read-only and exposes a complete path-marked file list.
  Execution requires a second, exact confirmation; changed input requires a
  new plan.
- Static HTML is a generated local reading layer, not a backup.
- The Skill does not guarantee secret scanning, remote synchronization,
  licensing validation, encryption, or signature/authentication of backups.

## Documentation

- [Skill entrypoint](knowledge-base-manager/SKILL.md)
- [Workflows](knowledge-base-manager/references/workflows.md)
- [Project Synthesis](knowledge-base-manager/references/project-synthesis.md)
- [Knowledge model](knowledge-base-manager/references/knowledge-model.md)
- [Markdown format](knowledge-base-manager/references/markdown-format.md)
- [Audit rules](knowledge-base-manager/references/audit-rules.md)
- [Static site](knowledge-base-manager/references/static-site.md)
- [Backup and restore](knowledge-base-manager/references/backup-restore.md)
- [Safety](knowledge-base-manager/references/safety.md)
- [Changelog](CHANGELOG.md)

## Development

```text
knowledge-base-manager/  installable Skill source
tests/                   disposable PowerShell fixtures
```

Only `knowledge-base-manager/` is installed. Tests use isolated temporary
knowledge bases, projects, backups, and restore destinations:

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
pwsh -NoProfile -File ./tests/test-kb-build-static.ps1
```

## License

Licensed under the [MIT License](LICENSE). Offline static reading bundles
[KaTeX 0.18.1](https://github.com/KaTeX/KaTeX/releases/tag/v0.18.1) browser
assets; see its [third-party attribution](knowledge-base-manager/assets/katex/THIRD_PARTY.md).
