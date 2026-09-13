# Workflows

Use only the section needed for the current operation. Search first when another mode could create duplicates.

## Project Synthesis routing

Capture never triggers Project Synthesis. Ordinary promotion of one inbox item
continues to use the Promote workflow below. Read
[project-synthesis.md](project-synthesis.md) only when the user explicitly
requests Project Synthesis, a formal multi-source or cross-project
consolidation, or equivalent complete synthesis protocol.

For an explicitly authorized sustainable batch, use the one-time metadata
manifest and top-*k* ambiguity protocol in
[project-synthesis.md](project-synthesis.md#sustainable-batch-execution). It
does not create topic maps, queues, or background aggregation.

## Search

Search is read-only unless the user separately asks for a change.

1. Resolve and verify the knowledge-base root and `kb.yaml`.
2. Determine `content_dir`; exclude `archive/` by default.
3. Search filenames, headings, IDs, tags, and body text using `scripts/kb.py search --root "<root>" --query "<terms>"` and `scripts/kb.py inspect --root "<root>"`. Read specific sections with `scripts/kb.py read --root "<root>" --path "<path>" --section <key> --expect-hash <hash>` (see [python-tools.md](python-tools.md)). If raw regex search is needed or Python is unavailable, use `rg`.
4. Search body text using the user’s terms and useful synonyms across the languages already present.
5. Inspect relevant map pages, links, and sections around strong matches with `scripts/kb.py inspect`.
6. Distinguish what entries explicitly state, what is inferred across entries, and what remains absent or uncertain.
7. Cite or link the exact local entries used in the response.
8. If an actual retrieval omission is observed (such as a subsequently identified existing entry that should have matched the original query), record a concise observation following [usage-feedback.md](usage-feedback.md). Do not record feedback or load that reference during normal, problem-free searches.

Include `archive/` only when the user asks for history, deprecated knowledge, exhaustive search, or when current entries explicitly point there.

## Capture

Capture favors speed and information preservation over taxonomy.

1. Resolve and verify the root.
2. Re-read the user-supplied material and any explicitly provided source.
3. Search only enough to avoid an obvious duplicate capture.
4. Create a readable Markdown file under `content/inbox/` with a date and concise title. Capture writes only to `content/inbox/` without modifying the homepage `index.md`.
5. Preserve facts, context, source pointers, uncertainties, and follow-up questions. Explicitly record the origin project context (for example `> 来源项目: [项目名称/相对链接]` or `> Origin project: [Project name/relative link]` in the entry preface). Never speculate, invent, or force-fit an origin project. If the note has no explicit origin project and no clearly related existing project/topic can be found in the knowledge base, categorize it definitively under a top-level miscellaneous/uncategorized category in the content's language (for example `杂项` in Chinese, or `Miscellaneous` / `Misc` in English, such as `> 来源项目: 杂项` or `> Origin project: Miscellaneous`) rather than stalling capture or inventing speculative associations. Retain whether the source describes an actual observation, a fictional example, or a simulated result; do not rewrite fiction or a hypothesis as an event that actually occurred. Label inference as inference.
6. Apply [the Markdown content format](markdown-format.md): write mathematical notation as KaTeX-compatible `$...$` or `$$...$$`, and keep backticks only for literal code or identifiers.
7. Add only obvious links; do not invent a final type or broad generalization.
8. Run the audit (`python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile legacy` or `./scripts/kb-audit.ps1 -Root "<verified-root>"`), resolve every `MATH_CODE_SPAN` issue in the new file, and report the new file.

An inbox entry may omit formal metadata. Never claim that capture has validated or promoted its contents.

## Promote

Promotion turns a capture into knowledge a reader can understand and use, while preserving its supporting sources and material conditions. Read [knowledge-writing.md](knowledge-writing.md); this does not invoke the full Project Synthesis workflow.

1. Read the inbox item, its explicit sources, and directly related formal entries within the authorized material scope using `scripts/kb.py read` and `scripts/kb.py inspect`.
2. Identify the reader, intended use, and important questions from the request and material. Inventory material source topics in the same candidate coverage ledger before deciding the number of entries. Ask only when a material ambiguity cannot be resolved from context.
3. Search for duplicate titles, IDs, synonyms, and overlapping content using `scripts/kb.py search`.
4. Decide whether to merge, create a new entry, or split distinct concepts. Prioritize updating and consolidating into an existing page when the note complements an already covered topic, method, or project, rather than fragmenting into a near-duplicate page. When creating a new standalone page, determine an appropriate hierarchy position to link it into a parent project or topic-map subgraph. If the capture originates from a miscellaneous/uncategorized context (or has no existing project/topic in the knowledge base), and the user does not explicitly specify a mount position, mount it under the top-level miscellaneous node (a map/project node on the same level as other entries in the homepage collection, such as `maps/杂项.md`, `maps/miscellaneous.md`, or `maps/misc.md`). The agent must NEVER invent or create a new project or topic map without explicit user authorization. If multiple interpretations would materially change the result, surface the ambiguity before writing.
5. Choose `type`, destination, filename, and a permanent unique `id` using the knowledge model.
6. Organize answers strictly within authorized materials, providing the explanations, examples, conditions, and details needed to use them. If relevant supplementary information is drawn from other entries in the knowledge base or authorized project files, it may be included but must carry an explicit provenance label (e.g. `> 补充来源: [条目名称/相对链接]` or `> Supplementary source: [entry name/relative link]`). Never introduce ungrounded domain specifics, private APIs, protocol details, or parameters derived solely from pre-trained model memory. Keep facts, sourced claims, project observations, inferences, and open questions distinguishable without turning every paragraph into a verification report. Resolve gaps from authorized sources; otherwise name the missing answer and its effect.
7. Apply the writing reference's guidance on titles, answer order, and placement of conditions. Keep source/reproduction locators and meaningful links; do not substitute general reminders for available answers.
8. Apply [the Markdown content format](markdown-format.md): distinguish mathematics from literal code, normalize formulas to KaTeX-compatible TeX, and preserve intentional code spans.
9. Give a new formal entry one reasonable inbound link from a parent project
   page or topic map, inside its [explicit collection region](navigation.md).
   If the entry originates from a miscellaneous/uncategorized context and no specific parent was designated by the user, link it inside the collection region of the top-level miscellaneous node (e.g. `maps/杂项.md` or `maps/miscellaneous.md`).
   When adding a new entry or substantively updating an existing entry, evaluate upward whether its direct collection parent requires a synchronized update (such as adjusting a 1-sentence summary, overview bullet, or collection title). To prevent cascade explosion, evaluate strictly along the explicit `kb-nav:children` collection chain: if the direct parent's overall scope, thesis, or conclusions remain intact, terminate upward cascading immediately at layer 1 (pruning). Only if the parent's own external identity or scope is restructured should upward evaluation propagate to grandparent collections. Do not require the child to link back or mechanically add sibling, related-entry, or extra-parent links; keep source provenance on the entry itself.
10. By default, move the processed inbox item to `content/archive/inbox/<year>/`. If the user wants it retained in place, add a clear pointer to the promoted entry instead. Because capture notes are kept in `content/inbox/` without being embedded in `index.md`, archiving the processed inbox item and hooking into the parent collection does not require cleaning up `index.md`.
11. Finish the same coverage ledger for important reader questions and material source topics: locate their answers in an entry, project-summary-only treatment, or explain a gap/deferral. Apply [content acceptance](knowledge-writing.md#content-acceptance) to the actual body: explicitly verify that factual content is strictly grounded in authorized materials or explicitly labeled internal sources, repair missing supported answers, and reject any ungrounded extrapolations. Do not add a Synthesis Record or additional review machinery solely because an ordinary Promote uses this check.
12. Run the write-profile audit (`python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile write --changed <rel-path> [--changed <rel-path>...]`) to verify metadata, markdown formatting, links, and collection-tree containment. Resolve every `MATH_CODE_SPAN` and collection issue in files changed by the promotion. Report the created or merged entry, archived source, modified links, coverage ledger, and unresolved questions. A short completion report must not shorten the durable body; structural audit success does not establish content completeness.
13. If an update omission, reading failure, or tooling obstacle is observed during promotion, record a concise observation following [usage-feedback.md](usage-feedback.md). Normal successful promotions do not record feedback.

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
7. If an update omission, broken inbound reference, or tooling failure is observed, record a concise observation following [usage-feedback.md](usage-feedback.md).

For a large migration, first produce a mapping of old path, new path, affected inbound links, and collisions. Execute only after the migration scope is authorized.

## Homepage and type indexes

When structuring or reorganizing the homepage guide (`content/index.md`) or collection navigation:

1. Keep the homepage concise: an introductory summary, a curated collection region (`<!-- kb-nav:children -->`), and secondary type-browsing links outside that region.
2. Inside the collection region, list stable standalone projects and topic maps. Projects belonging to a topic map may be listed as indented sub-items (2 or 4 spaces) under that map. This visual hierarchy guides the reader without establishing direct homepage parentage for the subordinate projects.
3. Keep secondary type indexes (`projects/`, `maps/`, `knowledge/`, `sources/`, `decisions/`, `inbox/`) outside the collection region (for example in `<details><summary>按类型浏览</summary>`).
4. Re-run `scripts/kb-audit.ps1` and `scripts/kb-build-static.ps1` to ensure collection syntax and breadcrumb chains remain intact.

## Audit

Run the audit tool in read-only mode:

```powershell
python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile legacy
# For write validation (Promote / Synthesis):
python -X utf8 ./scripts/kb.py audit --root "<verified-root>" --profile write --changed <rel-path> [--changed <rel-path>...]
# Fallback:
./scripts/kb-audit.ps1 -Root "<verified-root>"
```

Use `--format json` (or PowerShell `-Format Json`) when another deterministic step must consume the result. Read `audit-rules.md` and `python-tools.md` before deciding whether or how to fix findings. A request to audit is not permission to repair.
