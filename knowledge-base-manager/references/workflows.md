# Workflows

Use only the section needed for the current operation. Search first when another mode could create duplicates.

## Search

Search is read-only unless the user separately asks for a change.

1. Resolve and verify the knowledge-base root and `kb.yaml`.
2. Determine `content_dir`; exclude `archive/` by default.
3. Search filenames, level-one headings, IDs, and tags with `rg`.
4. Search body text using the user’s terms and useful synonyms across the languages already present.
5. Inspect relevant map pages and links around strong matches.
6. Distinguish what entries explicitly state, what is inferred across entries, and what remains absent or uncertain.
7. Cite or link the exact local entries used in the response.

Include `archive/` only when the user asks for history, deprecated knowledge, exhaustive search, or when current entries explicitly point there.

## Capture

Capture favors speed and information preservation over taxonomy.

1. Resolve and verify the root.
2. Re-read the user-supplied material and any explicitly provided source.
3. Search only enough to avoid an obvious duplicate capture.
4. Create a readable Markdown file under `content/inbox/` with a date and concise title.
5. Preserve facts, context, source pointers, uncertainties, and follow-up questions. Label inference as inference.
6. Apply [the Markdown content format](markdown-format.md): write mathematical notation as KaTeX-compatible `$...$` or `$$...$$`, and keep backticks only for literal code or identifiers.
7. Add only obvious links; do not invent a final type or broad generalization.
8. Run the audit, resolve every `MATH_CODE_SPAN` issue in the new file, and report the new file.

An inbox entry may omit formal metadata. Never claim that capture has validated or promoted its contents.

## Promote

Promotion converts a capture into reusable knowledge without losing the original evidence boundary.

1. Read the inbox item, its explicit sources, and directly related formal entries.
2. Inventory the material source topics and make a candidate coverage ledger before deciding the number of entries.
3. Search for duplicate titles, IDs, synonyms, and overlapping content.
4. Decide whether to merge, create a new entry, or split distinct concepts. Do not inherit a fixed entry count from the parent unless the user explicitly required one. If multiple interpretations would materially change the result, surface the ambiguity before writing.
5. Choose `type`, destination, filename, and a permanent unique `id` using the knowledge model.
6. Preserve useful original information while separating facts, sourced claims, project observations, inferences, and open questions.
7. Add a concise summary, necessary scope and limitations, complete source/reproduction locators, and meaningful links.
8. Apply [the Markdown content format](markdown-format.md): distinguish mathematics from literal code, normalize formulas to KaTeX-compatible TeX, and preserve intentional code spans.
9. Add reciprocal discoverability only where useful; avoid mechanical link duplication.
10. By default, move the processed inbox item to `content/archive/inbox/<year>/`. If the user wants it retained in place, add a clear pointer to the promoted entry instead.
11. Finish the coverage ledger: map every material topic to a formal entry, project-summary-only treatment, or deliberate deferral with a reason.
12. Run the audit and resolve every `MATH_CODE_SPAN` issue in files changed by the promotion. Report the created or merged entry, archived source, modified links, coverage ledger, and unresolved questions. State that structural audit success does not prove semantic completeness.

Promotion does not itself authorize changing `draft` to `stable`.

## Link, move, and rename

### Add a relationship

1. Read both entries and confirm the relationship is meaningful.
2. Prefer a contextual link in the body.
3. When a dedicated related-entry list improves discovery, add a short relationship description.
4. Add a reciprocal link only if it helps a reader navigate in both directions.
5. Audit.

### Add or refresh a project source locator

1. Verify the source target exists and is inside the authorized project/source root; do not copy the target into the knowledge base.
2. Record project identity, a project-relative path when available, a concise supported-claim description, `verified: YYYY-MM-DD`, and either `revision: <value>` or `version-state: <value>`.
3. Determine version state honestly. Use a commit only when it actually identifies the source content; use `uncommitted`, `unversioned`, `no-git-head`, or `unknown` when appropriate.
4. If adding an absolute Markdown link, label it in the entry language as outside the knowledge base and machine-specific, and include `<!-- kb-external-local -->` on the same line.
5. Re-read every written source item and compare it field-by-field with the requested mapping. Do not infer that a date or version was written merely because it appeared in the plan.
6. Audit and report intentional unavailable local paths separately from broken internal links.

### Move or rename

1. Resolve the exact source and destination inside the knowledge base.
2. Search the entire content tree for inbound links before moving.
3. Refuse to overwrite a destination. Preserve the entry `id`.
4. Move the file and update every affected relative link, including links from and within the moved entry.
5. Re-run the inbound-link search and the audit.
6. Stop further bulk changes if errors remain; report every modified path.

For a large migration, first produce a mapping of old path, new path, affected inbound links, and collisions. Execute only after the migration scope is authorized.

## Audit

Run the bundled script in read-only mode:

```powershell
./scripts/kb-audit.ps1 -Root "<verified-root>"
```

Use `-Format Json` when another deterministic step must consume the result. Read `audit-rules.md` before deciding whether or how to fix findings. A request to audit is not permission to repair.
