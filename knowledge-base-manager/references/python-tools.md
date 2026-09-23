# Python Core Toolset

This reference describes the Python CLI (`kb.py`) for reading, searching, auditing, static builds, and portable backup/restore.

## Overview and Invocation

`resolve`, `inspect`, `search`, `read`, `audit`, and `verify-backup` are read-only. `backup` and `restore` default to read-only planning and write only with `--execute`; backup also requires the exact confirmed plan digest. `build-static` writes a derived reading site to a separate destination. None of these operations authorize editing the live knowledge source.

To run the CLI tool:

```bash
python -X utf8 ./knowledge-base-manager/scripts/kb.py [--format text|json] <command> [arguments...]
```

When called by agents, `--format json` is recommended. The tool outputs a single UTF-8 JSON object to stdout, including structured diagnostics in its envelope. Argument-parser errors may also write usage information to stderr.

### Python Environment Requirements

- Python 3.12+ (verified baseline: CPython 3.14.7 Windows x64 and CPython 3.12 Linux x86_64)
- All required pure-Python runtime dependencies (`PyYAML 6.0.3`, `markdown-it-py 4.2.0`, `mdit-py-plugins 0.6.1`, `mdurl 0.1.2`) are bundled directly within the Skill in `knowledge-base-manager/vendor/`. End users do not need to `pip install` any third-party packages or rely on internet access.
- If bundled vendor dependencies or entrypoints are missing or corrupted, commands report `DEPENDENCY_MISSING` or `DEPENDENCY_INVALID` and exit code `3` without performing partial execution. In that event, re-download or reinstall the complete Skill distribution package of the same version. `resolve` and `--help` do not require third-party packages.

## Command Reference

### 1. `resolve`

Resolves a requested path or bare directory name to an absolute knowledge-base root.

```bash
python -X utf8 ./knowledge-base-manager/scripts/kb.py resolve --requested <path-or-name> [--project-root <dir>] [--source-root <dir>...] [--search-depth <0-8>] [--allow-missing]
```

- **Exit codes**:
  - `0`: Resolved exact path (`status: "resolved"` or `"resolved_missing"`).
  - `2`: Bare name requires explicit absolute path confirmation (`status: "confirmation_required"`).
  - `3`: Path not found (`status: "not_found"`).
  - `4`: Invalid path, redirecting reparse point, or not a directory (`status: "invalid"`).

### 2. `inspect`

Lists knowledge base pages or inspects a single page's structural elements.

```bash
# List pages with filtering and pagination
python -X utf8 ./knowledge-base-manager/scripts/kb.py inspect --root <root> [--scope <prefix>] [--type <type>] [--status <status>] [--include-archive] [--limit <n>] [--offset <n>] [--expect-view <view_id>]

# Inspect single page details
python -X utf8 ./knowledge-base-manager/scripts/kb.py inspect --root <root> --path <content-relative-path> [--include sections,relations,sources]
```

- Output data:
  - List mode: `items` (page summaries), `total`, `offset`, `limit`, `has_more`, `view_id`.
  - Single page mode: `page`, `sections` (headings and spans), `relations` (1-hop inbound/outbound links), `sources` (declared source locators and evidence).

Source fields are declarations, not independently verified evidence. Code and math examples do not supply registration fields. Existing code-wrapped values (for example, ``verified: `2026-09-13` ``) remain supported; a code span containing a whole field (for example, `` `verified: 2026-09-13` ``) must occupy its own slot at the start of the inline line or after a semicolon. Commas or explanatory prose do not establish that slot. `support_text` is different: when a real `supports:` / `support:` / `支持范围:` / `支持:` label is on a precisely mapped inline line, it preserves the original Markdown value (including inline code, inline math, and links) through the first semicolon outside code or math, or the line end. A label inside code or math is not recognized. A locator is attached only to a unique, precisely located link on the same line; otherwise it remains null. When source-line mapping is uncertain, a candidate may be retained as an unclassified block without extracted fields.

### 3. `search`

Performs deterministic phrase-based lexical search across pages.

```bash
python -X utf8 ./knowledge-base-manager/scripts/kb.py search --root <root> --query <phrase> [--query <phrase>...] [--match any|all] [--scope <prefix>] [--type <type>] [--status <status>] [--include-archive] [--limit <n>] [--offset <n>] [--hits-per-page <n>] [--snippet-chars <n>] [--expect-view <view_id>]
```

- **Matching**: Uses Unicode casefold on literal phrases. Matches across id, title, tags, source fields, path, and body.
- **Ranking**: Exact id or title match > number of matched query terms > best matched field priority > path ascending.
- **Hits**: Includes snippet, line numbers, and deepest enclosing section key/heading path.

### 4. `read`

Reads page, section, or line-range text by position with stale-read detection.

```bash
# Read whole page
python -X utf8 ./knowledge-base-manager/scripts/kb.py read --root <root> --path <content-relative-path> [--expect-hash <hash>] [--max-chars <n>]

# Read specific section
python -X utf8 ./knowledge-base-manager/scripts/kb.py read --root <root> --path <content-relative-path> --section <key> --expect-hash <hash> [--max-chars <n>] [--offset <n>]

# Read line range
python -X utf8 ./knowledge-base-manager/scripts/kb.py read --root <root> --path <content-relative-path> --lines <start:end> --expect-hash <hash> [--max-chars <n>] [--offset <n>]
```

- **Hash Verification**: Position-based reading (`--section`, `--lines`, or `--offset > 0`) requires `--expect-hash`. If the file on disk has changed, returns status `stale` (exit code `3`) with code `CONTENT_CHANGED` and `data: null`.
- **Character Slicing**: Chars are counted in Unicode characters; UTF-8 BOM is excluded. Truncation and `next_offset` allow clean continuation.

### 5. `audit`

Audits knowledge base integrity. Supports `legacy` (default) and `write` profiles.

```bash
# Legacy audit: manifest, metadata, links, math, orphans
python -X utf8 ./knowledge-base-manager/scripts/kb.py audit --root <root> --profile legacy

# Write audit: legacy audit plus full collection graph and parent validation
python -X utf8 ./knowledge-base-manager/scripts/kb.py audit --root <root> --profile write --changed <rel-path> [--changed <rel-path>...]
```

- **`legacy` profile**: Checks manifest fields, formal entry YAML front matter, ID formatting/uniqueness, broken/escaping links, math in inline code, and orphan entries.
- **`write` profile**: In addition to legacy checks, validates that every formal entry has a valid direct collection parent in a project or map page collection region (`<!-- kb-nav:children:start -->`), checks for cycles, and marks issues with `in_changed: true/false`.
- **Exit codes**:
  - `0`: No errors (warnings may be present).
  - `2`: Validation errors detected (`status: "validation_failed"`).
  - `3`: Fatal failure / unreadable knowledge base (`status: "failed"`).
  - `4`: Invalid arguments (e.g. non-existent changed file).

### 6. `build-static`

Generates an offline, disposable HTML reading copy of the knowledge base.

```bash
# Incremental build
python -X utf8 ./knowledge-base-manager/scripts/kb.py build-static --root <root> --destination <destination>

# Force complete rebuild
python -X utf8 ./knowledge-base-manager/scripts/kb.py build-static --root <root> --destination <destination> --force
```

- **Features**:
  - Fast incremental build with hash caching in `.kb-static-manifest.json`.
  - Embedded navigation hierarchy, breadcrumbs, and standalone `kb-navigation.html`.
  - Offline KaTeX formula rendering and interactive 2D graph visualizations.
  - Safe deletion of orphaned HTML files recorded in prior manifest; never touches unmanaged destination files.
- **Exit codes**:
  - `0`: Build succeeded (`status: "success"`).
  - `2`: Build blocked by validation, target conflict, or an execution error (`status: "blocked"`).

### 7. `backup`

Generates a deterministic portable backup bundle (`ReferenceComplete` mode).

Plans use `plan_schema_version: 2`. Legacy PowerShell or unversioned confirmation digests require a new displayed plan and explicit confirmation; bundle manifest schema v1 remains unchanged. See [backup and restore](backup-restore.md) for the migration and publication contract.

```bash
# Read-only planning (deterministic plan digest output):
python -X utf8 ./knowledge-base-manager/scripts/kb.py backup --root <root> --destination <destination>

# Execution (requires explicit plan digest confirmation):
python -X utf8 ./knowledge-base-manager/scripts/kb.py backup --root <root> --destination <destination> --execute --confirmed-plan-digest <plan_digest>
```

- **Invariants**:
  - Zero staging directories created before pre-write plan verification.
  - Staging under `<destination>/.incomplete-<uuid>`, atomically moved to `portable-kb` only after full bundle verification and audit pass.
  - Live knowledge base remains 100% byte-identical; link rewriting to `<!-- kb-portable-source -->` occurs only in backup copy.
  - Generates `backup-manifest.json`, `CHECKSUMS.sha256`, `backup-report.md`, and `README-RESTORE.md`.
- **Exit codes**:
  - `0`: Plan generated or backup executed successfully (`status: "plan"` or `"created"`).
  - `2`: Confirmation required, digest drift/reconfirm required, or blocker (`status: "confirmation_required"`, `"reconfirm_required"`, `"blocked"`).
  - `3`: Fatal backup error (`status: "blocked"`).

### 8. `verify-backup`

Verifies integrity, checksums, manifest completeness, and audit rules of a portable backup bundle.

```bash
python -X utf8 ./knowledge-base-manager/scripts/kb.py verify-backup --bundle <bundle-path>
```

- **Checks**:
  - Bundle directory structure and manifest schema v1.
  - Exact checksum match for all files listed in `CHECKSUMS.sha256`.
  - Zero missing files and zero unmanifested files.
  - Portable external links resolve inside bundle `external/`.
  - Read-only audit passes on bundled `content/`.
- **Exit codes**:
  - `0`: Bundle valid (`status: "valid"`).
  - `2`: Verification failed or tampering detected (`status: "invalid"`).
  - `3`: Fatal error (`status: "fatal"`).

### 9. `restore`

Restores a verified portable bundle into a new, non-existent destination directory (`Portable` mode).

```bash
# Read-only restore plan:
python -X utf8 ./knowledge-base-manager/scripts/kb.py restore --bundle <bundle-path> --destination <new-root>

# Execute restore:
python -X utf8 ./knowledge-base-manager/scripts/kb.py restore --bundle <bundle-path> --destination <new-root> --execute
```

- **Invariants**:
  - Refuses to restore if destination already exists.
  - Staged in sibling `.restore-incomplete-<uuid>`, hashes checked before and after copy.
  - Audits staged KB before atomic directory publish.
- **Exit codes**:
  - `0`: Plan generated or restore executed successfully (`status: "plan"` or `"restored"`).
  - `2`: Blocker (e.g. `Relink` mode or destination exists) (`status: "blocked"`).
  - `3`: Fatal restore error (`status: "blocked"`).
