# Changelog

## Unreleased

- Organize Promote and Project Synthesis around reader questions as well as source topics, using the existing coverage ledger for answers and explicit gaps.
- Add focused knowledge-writing guidance and complete Chinese procedural and research examples; separate durable content depth from completion-report brevity.
- Review actual explanations, examples, and useful details independently of structural audit, and place material conditions beside the claims they qualify.
- Keep Capture lightweight without a synthesis ledger and explicitly preserve whether material is an actual observation, fiction, or simulation; add fictional behavior fixtures for source gaps, short replies, and mode isolation. Models, runtime scripts, metadata schemas, and publication remain unchanged.

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
