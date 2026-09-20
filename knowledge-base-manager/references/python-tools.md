# Python Core Toolset

This reference describes the Python-based reading, search, and audit CLI toolset (`kb.py`) for the knowledge base manager.

## Overview and Invocation

The Python core toolset provides unified reading, inspection, lexical search, and auditing capabilities for Markdown knowledge bases. All commands are strictly read-only and never mutate files, configurations, or external sources.

To run the CLI tool:

```powershell
python -X utf8 ./knowledge-base-manager/scripts/kb.py [--format text|json] <command> [arguments...]
```

When called by agents, `--format json` is recommended. The tool outputs a single UTF-8 JSON object to stdout. Diagnostic and operational logs are emitted to stderr.

### Python Environment Requirements

- Python 3.12+ (verified baseline: CPython 3.14.7 Windows x64)
- Packages:
  - `PyYAML` (>= 6.0.3)
  - `markdown-it-py` (>= 4.2.0)
  - `mdit-py-plugins` (>= 0.6.1)

If required dependencies are absent, commands report `DEPENDENCY_MISSING` and exit code `3` without performing partial or fallback execution. `resolve` does not require Markdown parser packages.

## Command Reference

### 1. `resolve`

Resolves a requested path or bare directory name to an absolute knowledge-base root.

```powershell
python -X utf8 ./knowledge-base-manager/scripts/kb.py resolve --requested <path-or-name> [--project-root <dir>] [--source-root <dir>...] [--search-depth <0-8>] [--allow-missing]
```

- **Exit codes**:
  - `0`: Resolved exact path (`status: "resolved"` or `"resolved_missing"`).
  - `2`: Bare name requires explicit absolute path confirmation (`status: "confirmation_required"`).
  - `3`: Path not found (`status: "not_found"`).
  - `4`: Invalid path, redirecting reparse point, or not a directory (`status: "invalid"`).

### 2. `inspect`

Lists knowledge base pages or inspects a single page's structural elements.

```powershell
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

```powershell
python -X utf8 ./knowledge-base-manager/scripts/kb.py search --root <root> --query <phrase> [--query <phrase>...] [--match any|all] [--scope <prefix>] [--type <type>] [--status <status>] [--include-archive] [--limit <n>] [--offset <n>] [--hits-per-page <n>] [--snippet-chars <n>] [--expect-view <view_id>]
```

- **Matching**: Uses Unicode casefold on literal phrases. Matches across id, title, tags, source fields, path, and body.
- **Ranking**: Exact id or title match > number of matched query terms > best matched field priority > path ascending.
- **Hits**: Includes snippet, line numbers, and deepest enclosing section key/heading path.

### 4. `read`

Reads page, section, or line-range text by position with stale-read detection.

```powershell
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

```powershell
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
