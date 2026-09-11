# Changelog

## 0.1.5a - 2026-09-12

- Refined inbox curation and Promote workflows with project origin tracking, localized fallback categorization, and strict evidence grounding without ungrounded model extrapolations.
- Added a pre-rendered homepage Inbox navigation button with an active/empty count badge, directory index empty-state handling, and nested list hierarchy support in curated navigation.
- Excluded draft and archive notes from the 2D offline relationship graph to keep graph views clean.

## 0.1.5 - 2026-09-11

- Added an offline two-dimensional relationship graph built with native SVG, CSS, and zero runtime dependencies, featuring multi-parent BFS depth resolution, radial layout, and node excerpt previews.
- Added inline graph embedding on the homepage, a full-screen overlay modal on reading pages with state synchronization, and a standalone `kb-navigation.html` full-viewport navigation page.
- Added 1-hop ego-network focus mode with compact radial neighbor clustering, smooth camera centering on exit, and bidirectional expand/focus state preservation.
- Added offline bilingual (Chinese and English) support with client-side environment detection and URL `?lang=` override for graph controls, table of contents, breadcrumbs, and copy buttons.
- Extended `kb-build-static.ps1` with incremental manifest tracking for graph data and preview assets, avoiding unneeded rebuilds when graph topology is unchanged.

## 0.1.4 - 2026-09-09

- Organize Promote and Project Synthesis around reader questions, retain explanations and examples, and check for missing answers separately from formatting and source metadata.
- Use lower-tier subagents for routine organization and same-tier models for complex synthesis; require user approval before upgrading to the highest available tier.
- Remove non-deterministic, human/model-reviewed test cases not used by CI from version control.

## 0.1.3 - 2026-09-08

- Added a light-blue static reading theme with a distinct article panel, responsive article outline, collapsible details, and code-copy buttons with a manual-copy fallback.
- Added explicit project/topic collection regions for semantic breadcrumbs and multiple collection entrances, plus auxiliary type indexes; navigation changes invalidate affected static output without moving Markdown sources.
- Exempted ordinary homepage links to existing standard type directories outside collection regions from directory-link warnings, while preserving warnings elsewhere and orphan-entry checks.
- Added CI coverage for curated navigation and the generated page's code-copy and article-outline behavior. Node.js is used only for development tests, not by the Skill runtime.

## 0.1.2 - 2026-09-02

- Added explicit Project Synthesis v1 with bounded source and evidence handling, one designated editor, a coverage ledger, and independent review for material or high-risk conclusions.
- Added a tested renderer-compatible structured Markdown authoring profile, including representation choices without fixed table or template quotas.
- Added static HTML template v3 styling and behavior tests for tables, task lists, nested lists, blockquotes and GitHub alerts, footnotes, code, and link rewriting.

## 0.1.1 - 2026-08-31

- Added recursive local static HTML generation with SHA-256 incremental rebuilds and generated directory indexes.
- Added `-Force` regeneration of managed pages, indexes, and bundled assets while preserving unrelated destination files.
- Bundled KaTeX 0.18.1 browser assets for offline formula rendering and documented their third-party provenance and MIT license.
- Defined canonical `$...$` and `$$...$$` math syntax and added `MATH_CODE_SPAN` audit errors for likely formulas written as code.
- Added regression tests and Windows CI coverage for static HTML generation and math-format behavior.

## 0.1.0 - 2026-08-30

- Initial public preview with Markdown knowledge-base initialization, provenance-aware capture and promotion, deterministic audit, and confirmation-gated `ReferenceComplete` backup, verification, and `Portable` restore.
