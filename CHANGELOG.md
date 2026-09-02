# Changelog

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
