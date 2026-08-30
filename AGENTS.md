# Project instructions

## Scope

This project develops and tests the `knowledge-base-manager` Codex Skill. Treat `knowledge-base-manager/` as the distributable Skill source, `tests/` as disposable-fixture tests, and the ignored `docs/` tree as local project-level design and status documentation.

Read [README.md](README.md) before substantial changes. A developer checkout may also contain ignored local status and design notes under `docs/`; use them when present, but do not make the public project depend on them. Deferred HTML/wiki reading-layer notes are local-only.

## Skill development rules

- Use the `skill-creator` Skill when creating or materially updating this Skill.
- Use `knowledge-base-manager` only when the task is an actual durable-knowledge operation. Ordinary source code, tests, or project documentation in this repository are not personal knowledge-base writes.
- Keep `SKILL.md` concise and route detailed mode-specific behavior into `references/`.
- Preserve `agents/openai.yaml` fields that are unrelated to the requested change. Keep implicit invocation enabled unless the user explicitly changes that policy.
- Keep Markdown as the knowledge source of truth. Do not introduce a database, vector index, Obsidian-only syntax, Google Drive API, Git automation, HTML generator, or background service without a separate user request.
- Do not require Python, PyYAML, Git, or third-party PowerShell modules for runtime features. Generated JSON backup metadata is allowed; live knowledge content and configuration remain Markdown/YAML.
- All bundled PowerShell scripts require PowerShell 7 or later and must begin with `#Requires -Version 7.0`.

## Safety and workspace boundaries

- Do not modify a real personal knowledge base or sibling project while developing or testing this Skill unless the user explicitly places that exact target in scope.
- Tests must create their writable knowledge bases, external projects, backups, and restores under a unique temporary directory and clean them up unless a forward-test request explicitly asks to retain artifacts.
- A readable external project file is not automatically authorized for long-term storage. Keep sensitive-content, licensing, privacy, and size decisions with the primary agent or user.
- Use `apply_patch` for project file edits. Preserve unrelated user changes.
- Do not assume this project is a Git repository. Use filesystem inspection and explicit test results when Git metadata is unavailable.
- Never embed a machine-specific personal knowledge-base root in this file. Resolve it through the Skill's configured root rules when an actual knowledge-base task occurs.

## Backup invariants

Maintain these behaviors unless the user explicitly redesigns them:

- `ReferenceComplete` is the supported backup mode. `ProjectSnapshot` must return a clear blocker until it is fully implemented.
- `Portable` is the supported restore mode. `Relink` must return a clear blocker until it is fully implemented.
- Planning is read-only and must list `kb.yaml`, every file below `content_dir`, and every unique registered external source.
- Every plan record includes canonical source path, portable path, byte size, UTC mtime, and SHA-256. External records also include stable project identity fields.
- The plan produces a deterministic `plan_digest`. A generic backup request does not authorize execution.
- Before execution, show the user the complete path-marked file list and obtain explicit post-plan confirmation.
- `-Execute` requires the exact confirmed digest. A missing digest returns `confirmation_required`; a stale or incorrect digest, or any later input drift, returns `reconfirm_required` with a new plan.
- Do not create a destination or staging directory before the final pre-write digest check.
- Assemble under `.incomplete-<id>`, verify the bundle and audit the copied knowledge base, then publish `portable-kb` by rename. Never publish a failed or drifted staging directory.
- Reject junctions and symbolic links in knowledge-base, registered source, bundle, backup-destination, and restore-destination data paths. Allow ordinary locally available cloud-provider files; the development Junction that installs the Skill is outside this data boundary.
- Restore only to a destination that does not exist. Copy the exact verified manifest records to a sibling `.restore-incomplete-*` directory, recheck source and staged hashes, audit it, and publish with a fail-if-exists directory move.
- Keep full-plan hashing to a fixed small number of passes. Check each file before and after copying; do not rehash the entire plan inside per-file loops.
- The live knowledge base remains byte-identical. Rewrite external-local links only in the backup copy.
- Knowledge-base content is recursive; external sources are an explicit, deduplicated file list and are not recursively traversed.
- Keep SHA-256 for content and bundle integrity unless a versioned migration plan explicitly changes the manifest format.

## Source registration

An external source eligible for portable backup must have a same-line ordinary Markdown link and the stable tokens required by `references/knowledge-model.md`, including:

- human-readable project identity;
- `project-id` matching `[a-z0-9][a-z0-9._-]{0,63}`;
- `project-relative source`;
- `verified: YYYY-MM-DD`;
- `revision` or an honest `version-state`;
- `<!-- kb-external-local -->` on the same line as an optional absolute machine-local link.

Do not silently ignore an unregistered absolute path. An ignore requires an exact path and a concrete reason and must remain visible in generated metadata.

## Validation

Run all tests after script, schema, workflow, or safety changes:

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
```

Also parse every bundled `.ps1` with the PowerShell parser. For a material Skill change, validate frontmatter name/description, `agents/openai.yaml` policy, reference discoverability, and unfinished placeholders. If `skill-creator/scripts/quick_validate.py` cannot run because its Python lacks PyYAML, report that environment limitation and perform the equivalent structural checks manually; do not add PyYAML as a runtime dependency of this Skill.

Prefer observable end-to-end tests over wording assertions. Backup changes should cover plan determinism, confirmation-required behavior, stale-plan drift, live-KB byte preservation, checksum tampering, source isolation, Portable restore, and post-restore audit.

## Documentation maintenance

When the ignored `docs/local/当前项目状态.md` exists, update it when a capability moves between implemented, deferred, or unsupported states, when runtime dependencies change, or when a meaningful test boundary changes. Keep historical design intent in the local design plan instead of rewriting it as if every planned feature were complete. Keep public behavior and limitations accurate in the repository README.
