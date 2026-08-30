---
name: knowledge-base-manager
description: Manage a human-readable Markdown knowledge base across projects, including portable backup, verification, restore, and cross-machine migration. Use when the user asks to locate, set up, capture, organize, promote, link, rename, search, audit, back up, verify, restore, or migrate durable personal knowledge. Do not use for ordinary project documentation that is meant to stay only in the current project.
---

# Knowledge Base Manager

Maintain one portable Markdown knowledge base for both people and agents. Markdown is the source of truth; user-managed Google Drive, OneDrive, Dropbox, or another local-folder synchronizer is only a transport layer.

## Resolve the knowledge base

Resolve the root in this order:

1. A path explicitly supplied in the current request.
2. The task-specific `CODEX_KB_ROOT` environment variable.
3. `knowledge-base-manager.local.yaml` in the local Codex configuration directory: use `$CODEX_HOME/knowledge-base-manager.local.yaml` when `CODEX_HOME` is set, otherwise use `~/.codex/knowledge-base-manager.local.yaml`. Prefer a matching canonical current-project key in `project_roots`; otherwise use `root` as the machine default.
4. An already-established personal default in the current environment.

Interpret a location supplied by the user before applying that order:

- An absolute or relative path names one exact candidate. Resolve a relative path from the verified current project root.
- A bare folder name is not a path. Search for exact directory-name matches inside the active project source/workspace folders, report all matches or that none were found, and always ask the user to confirm an absolute path before continuing. This confirmation is required even when there is exactly one match.
- Never create or write to a directory based only on a bare name. A subsequent user-confirmed absolute path may authorize initialization at that exact location.
- An unresolved explicit location does not fall through to a different configured default.
- A phrase such as "this knowledge base" or "the one just created" may identify an existing cleanup target from the current task, but it does not select a destination for initialization. For a combined delete-and-reinitialize request, resolve `cleanup_target` and `new_root` separately. Never assume they are the same path.

For a supplied path or folder name, use `scripts/kb-resolve-root.ps1`. The parameter is `-RequestedPath` (`-RequestedRoot` is accepted only as a compatibility alias). Pass the active project source/workspace folders with `-SourceRoot` when searching a bare name. Its `confirmation_required` result prohibits writes. Use `-AllowMissing` only for an exact path whose creation the user has authorized.

```powershell
./scripts/kb-resolve-root.ps1 -RequestedPath "<user-supplied-location>" -ProjectRoot "<verified-project-root>" -SourceRoot "<workspace-source-root>"
```

Maintain an explicit `active_kb_root` after the user confirms an absolute candidate. In the same ongoing task, reuse that root for later knowledge-base operations without asking again; revalidate it read-only before use. A confirmation such as "yes, the sibling folder" binds the absolute candidate most recently shown by the agent. Do not treat an unconfirmed path merely mentioned by the agent as selected.

Conversation state is not durable across a new task, restart, or missing/ambiguous compacted context. For durable reuse, persist the selection in the local YAML file above and reload it whenever this skill runs. Do not put a machine-specific absolute knowledge-base path in `AGENTS.md` by default.

Never discover a writable root by broadly searching a drive and guessing. Require a readable `kb.yaml` for ordinary operations. Initialization may instead select an existing empty directory or an exact, explicitly authorized new absolute path; follow [references/initialization.md](references/initialization.md).

Before the first write in an operation, state `active_kb_root` in the working update and verify every target remains inside it. Verification is not a second confirmation request. If no verified root is available, continue only with work that does not require the knowledge base, or ask for its location.

Before modifying a path, resolve it and verify that it remains inside the selected root.

## Mandatory write-isolation gate

Initialize, Capture, Promote, Link/move/rename, migration, deletion, and repair are write modes. Before detailed source reading, drafting, staging, or mutation, a primary agent must read [references/delegation.md](references/delegation.md) and spawn one isolated designated knowledge-base editor when subagent orchestration is available. This requirement is an explicit skill instruction to delegate, not an optional optimization.

The primary agent may resolve paths, identify a minimal source-file list, settle authorization or evidence-boundary decisions, and verify the result. It must not draft knowledge entries or stage their content in the main session. A designated editor whose handoff contains `KB_EDITOR_ROLE: designated` performs the write directly and must not spawn another agent.

If spawning is unavailable or fails, stop before reading sources in detail or writing. Explain the loss of isolation and obtain the user's explicit approval before falling back to a main-session write. Never silently perform the work in the primary agent.

## Select a mode

- **Initialize** when setting up a new knowledge base or adopting an existing directory. Read [references/initialization.md](references/initialization.md) and [references/safety.md](references/safety.md).
- **Search** for questions about existing knowledge. This mode is read-only. Read [references/workflows.md](references/workflows.md#search).
- **Capture** for requests such as “remember this” or “put this in the knowledge base.” Read [references/workflows.md](references/workflows.md#capture) and [references/safety.md](references/safety.md).
- **Promote** when an inbox note should become durable, reusable knowledge. Read [references/knowledge-model.md](references/knowledge-model.md), [references/workflows.md](references/workflows.md#promote), and [references/safety.md](references/safety.md).
- **Link or move** when creating relationships, renaming, or relocating entries. Read [references/knowledge-model.md](references/knowledge-model.md), [references/workflows.md](references/workflows.md#link-move-and-rename), and [references/safety.md](references/safety.md).
- **Audit** when checking consistency. Read [references/audit-rules.md](references/audit-rules.md) and run `scripts/kb-audit.ps1`.
- **Backup or restore** when creating, validating, or recovering a portable knowledge-base copy. These bundled scripts require PowerShell 7+ via `pwsh`; Windows PowerShell 5.1 is unsupported. Read [references/backup-restore.md](references/backup-restore.md). For `ReferenceComplete`, show the user the full path-marked plan file list, ask for explicit post-plan confirmation, then invoke `-Execute -ConfirmedPlanDigest <exact digest>`. A generic initial backup request never authorizes execution. If unchanged, no further confirmation is needed; any drift returns a new plan and asks again. Never point backup output at the live knowledge base.

If a request combines modes, search before writing and audit after all writes.

## Shared invariants

- Keep content understandable in a generic Markdown reader. Use standard relative Markdown links, not editor-specific wiki-link syntax as the canonical format.
- Follow the user’s explicit language, then the surrounding note or project convention, then the current conversation and environment. Do not translate existing content unless asked.
- Preserve sources, scope, uncertainty, and limits. Do not turn a project-specific observation into a general fact without evidence.
- For project-derived knowledge, record reproducible provenance: project identity, a project-relative locator when available, `verified: YYYY-MM-DD`, and either `revision: <value>` or an honest `version-state: <value>`. An external absolute path is optional; when used, label it as outside the knowledge base and machine-specific and add `<!-- kb-external-local -->` on the same line. Such links never replace the distilled explanation.
- Capture quickly with little classification; make taxonomy and deduplication decisions during promotion.
- Store distilled knowledge, not automatic copies of project trees, secrets, personal data, unpublished material, large results, caches, or generated artifacts.
- Treat search, explanation, and audit requests as read-only. A request to write authorizes only the smallest relevant knowledge-base changes.
- Prefer archiving over deletion. Do not silently overwrite, merge, or discard divergent sync copies.
- Do not add databases, vector indexes, HTML output, Obsidian dependencies, Google Drive APIs, Git automation, or background hooks unless the user separately requests that expansion.
- Do not follow directory junctions or symbolic links in knowledge-base, registered source, portable-bundle, or write-destination data paths. Require ordinary local paths and locally available files; a development link to the Skill directory itself is not a knowledge-base data path.

## Search and edits

Use `rg` first for filenames, headings, IDs, tags, and body text. If `rg` is unavailable, fall back to built-in PowerShell commands. Exclude `content/archive/` from ordinary searches unless the user asks for historical or deprecated material.

Before creating or promoting an entry, search for duplicate titles, IDs, synonyms, and overlapping content. Before moving a file, find all inbound links. Re-read every file immediately before editing so a stale snapshot does not overwrite a synchronized update.

After a write, run:

```powershell
./scripts/kb-audit.ps1 -Root "<verified-knowledge-base-root>"
```

Stop additional bulk edits if the audit reports errors introduced or exposed by the operation. Report files created, modified, moved, or archived, plus unresolved warnings.

## Knowledge model

Read [references/knowledge-model.md](references/knowledge-model.md) before creating a formal entry, changing metadata, choosing a destination, or changing links. Do not load it for a simple read-only keyword search.

## Safety and synchronization

Read [references/safety.md](references/safety.md) before any mutation, conflict resolution, migration, or bulk rename. A readable file is not automatically authorized for long-term storage.

## Audit behavior

The bundled auditor is deterministic and read-only. Its text format is for people; JSON is for further automation:

```powershell
./scripts/kb-audit.ps1 -Root "<verified-knowledge-base-root>" -Format Json
```

Read [references/audit-rules.md](references/audit-rules.md) before interpreting or repairing findings. Audit does not authorize fixes.
