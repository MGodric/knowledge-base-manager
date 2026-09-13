# Audit rules

The audit script is read-only. It never creates, edits, moves, or deletes knowledge-base files.

## Invocation and exit codes

```powershell
# Python CLI (supports legacy and write profiles):
python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile legacy
python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile write --changed <rel-path> [--changed <rel-path>...]

# PowerShell fallback:
./scripts/kb-audit.ps1 -Root "<verified-root>"
./scripts/kb-audit.ps1 -Root "<verified-root>" -Format Json
```

- Exit `0`: no errors; warnings may still be present.
- Exit `2`: one or more validation errors (`status: "validation_failed"` in JSON).
- Exit `3`: fatal input or runtime error (`status: "failed"` or `"stale"` in JSON).

## Errors

Errors indicate that structure, identity, or navigation is unreliable:

- Missing or unreadable `kb.yaml`.
- Unsupported or missing `schema_version`.
- Missing, absolute, or root-escaping `content_dir` or `entrypoint`.
- Missing content directory or entrypoint.
- Formal entry missing front matter, a required field, or exactly one level-one heading.
- Invalid entry `type`, `status`, date, or ID shape.
- Duplicate `id`.
- Broken internal Markdown link.
- A high-confidence mathematical expression is written as an inline code span
  instead of `$...$` or `$$...$$` (`MATH_CODE_SPAN`). Put
  `<!-- kb-literal-code -->` on the same line only when the span is genuinely
  literal code.

### Collection graph errors (write profile)

The `write` profile adds collection graph and parent validation across the knowledge base:
- `COLLECTION_PARENT_MISSING`: Formal entry has no valid direct collection parent entry linking to it within an explicit `<!-- kb-nav:children -->` collection block.
- `COLLECTION_CYCLE`: A collection cycle was detected in the collection parent-child graph.
- Note: When a parent/owner is already invalid, secondary errors on pages it collects are suppressed.

The entrypoint must have exactly one level-one heading but may omit formal metadata. Files under `inbox/` and `archive/` are retained material and are not required to satisfy the formal-entry schema.

## Warnings

Warnings require human judgment and do not produce a failing exit code:

- A formal current entry has no inbound link from current content.
- A current entry links to archived content.
- An absolute local link lacks an explicit outside-knowledge-base, machine-specific label.
- A labeled external local source lacks a valid `verified: YYYY-MM-DD` token.
- A labeled external local source lacks either `revision: <value>` or `version-state: <value>`.
- An internal link uses backslashes, an unsupported directory target, or path casing inconsistent with the stored file.

The configured homepage may link to existing top-level `projects`, `maps`,
`knowledge`, `sources`, `decisions`, `inbox`, `archive`, or `assets` directories
under `content_dir` as auxiliary type inventories. These ordinary relative
links are permitted only outside the [explicit collection region](navigation.md).
They do not count as inbound links to entries. Directory links in other pages,
inside collection regions, or to other/nested directories still produce
`DIRECTORY_LINK`. Images, portable-source links, root-relative links, backslash
paths, and links with queries or fragments do not receive this exception.
Malformed or repeated collection delimiters disable the exception for the
homepage; examples inside fenced code do not declare a region. Missing or
escaping targets and reparse points retain their existing checks. This does
not replace the static builder's full collection-graph validation.

An explicitly labeled external local source locator with `<!-- kb-external-local -->`, valid verification date, and revision/version state is allowed and produces no warning. The link is still non-portable; the auditor does not require that another machine can open it.
- A `<!-- kb-portable-source -->` link is allowed only in a bundle/restored KB that declares a contained `external_dir`; it must resolve inside that directory. Ordinary relative links remain confined to `content_dir`.
- A likely Google Drive conflict copy or temporary file exists.

An isolated entry is not automatically wrong. Inbox and archive files are never reported as orphans.

## Repair boundary

An audit request is read-only. When the user asks to repair findings:

1. Re-read affected files and check for synchronization changes.
2. Fix deterministic issues narrowly.
3. Ask before choosing between divergent copies, semantic merges, or multiple plausible link targets.
4. Preserve IDs on moves and preserve both sides of unresolved conflicts.
5. Run the full audit again and report remaining warnings.

The script validates ordinary inline Markdown links and detects selected
high-confidence math-in-code patterns. It intentionally does not perform
network checks, validate remote URL availability, parse editor-specific
wiki-link syntax, prove that a link’s anchor heading exists, or infer the
semantics of every code span. A clean audit does not prove that every formula
was classified correctly.
