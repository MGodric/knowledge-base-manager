# Knowledge Base Manager

[简体中文](README.zh-CN.md)

Knowledge Base Manager is a Codex Skill for maintaining a durable,
human-readable Markdown knowledge base across projects. Markdown remains the
source of truth, so the knowledge base can be browsed and edited without an
agent or a proprietary note-taking application.

The Skill supports knowledge-base discovery and initialization, structured
capture and promotion, deterministic auditing, and a confirmation-gated
portable backup and restore workflow.

> **Project status:** early public preview. The current knowledge-base schema
> and portable-backup manifest schema are both version 1. The existing test
> suite passes on Windows with PowerShell 7.6.4, but the minimum supported
> PowerShell 7 release has not yet been established by CI.

## Design goals

- Keep durable knowledge readable as ordinary Markdown files.
- Keep shared knowledge portable and machine-local configuration separate.
- Preserve source provenance without copying entire projects into the live
  knowledge base.
- Require a complete, reviewable file plan before a portable backup is written.
- Detect source drift between confirmation and backup publication.
- Avoid runtime dependencies on Python, PyYAML, Git, databases, Obsidian, or a
  cloud-provider API.

## Cloud synchronization

Cloud synchronization is configured and operated by the user. The Skill is
provider-agnostic: Google Drive, OneDrive, Dropbox, and similar services work
when they expose the knowledge base as an ordinary local folder. There is no
provider API integration or vendor-specific storage format.

Files must be locally readable before audit or backup; hydrate remote-only
placeholders first. The Skill does not wait for upload completion, prove remote
sync state, or resolve provider conflict copies. Knowledge-base and backup data
paths must not pass through directory junctions or symbolic links.

## Current capabilities

- Resolve a configured or explicitly selected knowledge-base root.
- Initialize or adopt a Markdown knowledge base with a small `kb.yaml`
  manifest.
- Capture notes, promote durable entries, maintain links, and archive obsolete
  material through agent-guided workflows.
- Audit manifest structure, entry metadata, internal links, source provenance,
  path containment, duplicate IDs, and synchronization-conflict artifacts.
- Create a `ReferenceComplete` backup containing the full knowledge base and
  each explicitly registered external source file.
- Verify backup manifests and SHA-256 checksums.
- Restore a self-contained `Portable` knowledge base without depending on the
  original drive letters or project locations.

## Important limits

- The current implementation is Windows-oriented and requires PowerShell 7 via
  `pwsh`. Windows PowerShell 5.1 is not supported.
- `ReferenceComplete` does not copy an entire project. External sources are
  copied only when individual files are explicitly registered in Markdown.
- External sources are not recursively traversed.
- `ProjectSnapshot` backup and `Relink` restore are reserved but not implemented.
- Obsidian wiki-links are not a canonical input format. Ordinary relative
  Markdown links are used instead.
- Remote URLs, heading anchors, cloud synchronization state, licensing,
  and secret detection are outside the deterministic audit guarantee.
- SHA-256 files provide internal integrity checks, not sender authentication or
  a digital signature.
- Backup and restore assume that the current user controls the source and
  destination parents and that no other process is racing directory
  replacements. Reparse checks block observed links; they are not a sandbox
  against a local process with write access to those parents.

## Repository layout

```text
knowledge-base-manager/     Distributable Codex Skill
  SKILL.md
  agents/openai.yaml
  references/
  scripts/
tests/                      Temporary-fixture PowerShell tests
```

Only the `knowledge-base-manager/` directory is the installable Skill. The
repository-level README and tests are not required at runtime. Local design
notes live in the ignored `docs/` tree and are never part of the repository.

## Public repository boundary

`.gitignore` is only one part of the privacy boundary:

- Machine-specific configuration uses the stable filename
  `knowledge-base-manager.local.yaml` and is ignored anywhere in the repository.
- New private development notes and inventories belong under `.local/`,
  `.private/`, `private/`, or `docs/`; those directories are ignored as a unit.
- Generated backup bundles, staging directories, plans, reports, and test
  artifacts use reserved names covered by `.gitignore`.
- Files that must be published, especially `knowledge-base-manager/SKILL.md`,
  `knowledge-base-manager/references/`, and tests, must contain neutral example
  paths rather than personal paths. Git cannot ignore only selected lines in a
  tracked file.

The committed `.gitignore` contains only repository-wide conventions. A
one-machine exception belongs in `.git/info/exclude` after `git init`; that file
is local to the clone and is never pushed.

Before every public release, inspect the actual tracked set rather than assuming
that ignore rules were applied:

```powershell
git status --short --ignored
git ls-files
git grep -n -I -E '([A-Za-z]:[\\/]|/Users/|/home/)' -- .
```

Review every match: source code and tests may contain intentional neutral path
fixtures, while names, home directories, project roots, backup destinations,
and unpublished project identifiers require removal. `.gitignore` does not
affect a file already tracked by Git and can be bypassed with `git add -f`. If a
private file is accidentally staged before the first push, remove it from the
index with `git rm --cached -- <path>` and verify `git ls-files` again. If it has
already been pushed, adding an ignore rule does not remove it from Git history.

## Installation

### Install through Codex

Ask Codex to install the Skill from the public repository and specify the Skill
subdirectory:

```text
Use $skill-installer to install knowledge-base-manager from
https://github.com/MGodric/knowledge-base-manager/tree/main/knowledge-base-manager
```

The equivalent installer inputs are:

```text
repository: MGodric/knowledge-base-manager
path: knowledge-base-manager
```

### Manual installation

Copy the distributable directory to:

```text
$CODEX_HOME/skills/knowledge-base-manager
```

If `CODEX_HOME` is not set, use the normal Codex configuration directory,
typically `~/.codex/skills/knowledge-base-manager`. A development checkout may
use a symbolic link or directory junction, but a copied installation is simpler
for ordinary users.

The Skill becomes available to Codex on a subsequent turn. It permits implicit
invocation and can also be called explicitly as `$knowledge-base-manager`.

## Quick start

Initialize or adopt a knowledge base through Codex so that path selection and
write authorization remain explicit:

```text
Use $knowledge-base-manager to initialize a knowledge base at <absolute path>.
```

Audit an existing knowledge base:

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-audit.ps1 `
  -Root <knowledge-base-root>
```

Create a read-only backup plan:

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-backup.ps1 `
  -Root <knowledge-base-root> `
  -Destination <backup-parent>
```

The plan lists every selected file with its absolute source path, portable
destination, byte size, UTC modification time, and SHA-256, and returns a
deterministic `plan_digest`. Review the complete list before authorizing the
write.

After confirmation, execute using that exact digest:

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-backup.ps1 `
  -Root <knowledge-base-root> `
  -Destination <backup-parent> `
  -Execute `
  -ConfirmedPlanDigest <confirmed-plan-digest>
```

Any change to the selected paths, sizes, modification times, hashes, or source
mapping invalidates the digest and requires a new review and confirmation.

Verify and restore a portable backup:

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-verify-backup.ps1 `
  -Bundle <backup-parent>/portable-kb

pwsh -NoProfile -File <skill-directory>/scripts/kb-restore.ps1 `
  -Bundle <backup-parent>/portable-kb `
  -Destination <new-root> `
  -Execute
```

The restore destination must not already exist. Restore writes into a sibling
staging directory, verifies every copied file and audits the result, then
publishes the completed directory without overwriting an existing path.

## Where personal and machine-local information is stored

Machine-local information is intentionally split according to its role:

| Location | Synchronized with the knowledge base? | Contents |
| --- | --- | --- |
| `$CODEX_HOME/knowledge-base-manager.local.yaml` | No | Default knowledge-base root and optional project-to-root mappings for the current machine. |
| `<knowledge-base-root>/kb.yaml` | Yes | Portable schema version and relative paths such as `content_dir` and `entrypoint`. It must not contain machine-specific absolute paths. |
| Markdown knowledge entries | Yes | Durable content. An entry may deliberately contain an absolute external-source locator marked `<!-- kb-external-local -->`; that locator is machine-specific and remains visible to readers. |
| `backup-manifest.json` in a portable backup | Only if the user synchronizes or copies the backup | Backup provenance, including original absolute source paths. |

Example machine-local configuration:

```yaml
schema_version: 1
root: 'D:\KnowledgeBase'
project_roots:
  'D:\Projects\example-project': 'D:\KnowledgeBase'
```

Example registered external source:

```markdown
- Project: `Example`; project-id: `example`; project-relative source: `docs/evidence.md`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [evidence.md](D:/Projects/example-project/docs/evidence.md); `verified: 2026-08-30`; `revision: abc1234`; supports: the bounded claim described above.
```

The absolute locator is optional. The project identity, project-relative path,
revision state, and explanation should remain sufficient for a human to
understand the provenance when that machine-local path is unavailable.

### Privacy warning

Backup plans reveal local paths, filenames, sizes, modification times, and
hashes. Portable backup manifests retain original absolute paths, and the bundle
contains the contents of every registered external source. Do not publish a
backup plan or bundle without reviewing it separately from this source-code
repository. The Skill is not a complete secret scanner and does not encrypt
backups.

## Compatibility policy

Skill releases use Semantic Versioning. The live knowledge-base schema in
`kb.yaml` and the generated backup schema in `backup-manifest.json` are
versioned independently; both are currently version 1.

- Installing a new Skill release never silently migrates or rewrites a live
  knowledge base.
- Additive optional fields may stay within the same schema; unknown fields are
  preserved. A breaking format change requires a new schema version.
- Breaking schema changes require a new schema version plus backward reading or
  an explicit, non-destructive migration path. CI retains supported-version
  fixtures for audit, backup, and restore.

No migration command exists yet because version 1 is the only defined live
schema.

## Roadmap

- `Relink` restore with explicit cross-machine project-root mappings.
- Opt-in `ProjectSnapshot` backups and controlled recursive source collections.
- A generated HTML/wiki reading layer while Markdown remains authoritative.
- Optional signed backup manifests for provenance authentication.
- Optional handle-relative hardened I/O for hostile shared-directory threat
  models.
- Cross-platform scripts and CI coverage beyond Windows.
- Versioned migration fixtures and tooling when schema 2 is proposed.

## Development and testing

Run the complete current test suite from the repository root:

```powershell
pwsh -NoProfile -File ./tests/test-kb-resolve-root.ps1
pwsh -NoProfile -File ./tests/test-kb-audit.ps1
pwsh -NoProfile -File ./tests/test-kb-backup.ps1
```

Tests create isolated temporary knowledge bases, projects, backups, and restore
destinations. They must not operate on a personal knowledge base.

## License

This project is licensed under the [MIT License](LICENSE).
