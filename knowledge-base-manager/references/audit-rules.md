# Audit rules

The audit script is read-only. It never creates, edits, moves, or deletes knowledge-base files.

## Invocation and exit codes

```powershell
./scripts/kb-audit.ps1 -Root "<verified-root>"
./scripts/kb-audit.ps1 -Root "<verified-root>" -Format Json
```

- Exit `0`: no errors; warnings may still be present.
- Exit `2`: one or more validation errors.
- Exit `3`: the audit could not complete because of a fatal input or runtime problem.

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

The entrypoint must have exactly one level-one heading but may omit formal metadata. Files under `inbox/` and `archive/` are retained material and are not required to satisfy the formal-entry schema.

## Warnings

Warnings require human judgment and do not produce a failing exit code:

- A formal current entry has no inbound link from current content.
- A current entry links to archived content.
- An absolute local link lacks an explicit outside-knowledge-base, machine-specific label.
- A labeled external local source lacks a valid `verified: YYYY-MM-DD` token.
- A labeled external local source lacks either `revision: <value>` or `version-state: <value>`.
- An internal link uses backslashes, a directory target, or path casing inconsistent with the stored file.

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

The script validates ordinary inline Markdown links. It intentionally does not perform network checks, validate remote URL availability, parse editor-specific wiki-link syntax, or prove that a link’s anchor heading exists.
