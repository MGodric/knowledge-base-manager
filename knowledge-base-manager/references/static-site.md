# Local static site

Use this mode to generate a recursively browsable HTML reading copy while Markdown remains the only source of truth. The generated directory is disposable and must stay outside the live knowledge base.

## Build

The bundled script requires PowerShell 7 and uses its built-in Markdown renderer. It does not install or invoke Python, Node.js, npm, a site generator, a database, a CDN, or a web server. The Skill includes the precompiled KaTeX 0.18.1 browser distribution under `assets/katex/` for offline formula rendering; its MIT license and upstream provenance are stored with those assets.

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-build-static.ps1 `
  -Root <verified-knowledge-base-root> `
  -Destination <separate-static-output-directory>
```

The default is incremental. When the user explicitly requests a complete
regeneration, add `-Force`:

```powershell
pwsh -NoProfile -File <skill-directory>/scripts/kb-build-static.ps1 `
  -Root <verified-knowledge-base-root> `
  -Destination <separate-static-output-directory> `
  -Force
```

Forced mode regenerates every Markdown page and generated directory index and
recopies every currently bundled KaTeX asset. It does not clear the destination,
overwrite an unowned path, or delete unrelated files.

The root must be an initialized knowledge base with a readable `kb.yaml`. The script reads `content_dir` recursively, creates one `.html` page for every `.md` file at the corresponding relative path, and writes a complete HTML document that can be opened directly through `file://`. Relative links between Markdown pages are rewritten to the generated HTML targets. Generated navigation, styling, KaTeX scripts, and fonts use only local files.

Write formulas with Markdown math delimiters. All knowledge-content writers
must follow [the Markdown content format](markdown-format.md):

```markdown
Inline: $P(X=x \mid accepted)$

Display:

$$
R_K = ARK_{K_1} \circ SR \circ SB \circ ARK_{K_0}
$$
```

PowerShell's Markdown renderer converts these forms to math-marked HTML, then the locally bundled KaTeX auto-render script typesets them in the browser. Backtick code spans and fenced code blocks remain code and are intentionally not treated as formulas. Do not mechanically convert every code span to math.

The source knowledge base is read-only. Do not place the destination at, above, or below the knowledge-base root. Reject junctions and symbolic links in either data path. The builder does not copy or publish content reached through links outside `content_dir`.

## Incremental manifest

The destination contains `.kb-static-manifest.json`. Each source-page record binds its normalized source-relative path to the generated relative path and SHA-256 hashes. Asset records similarly bind each bundled KaTeX input to `_assets/katex/` output. A subsequent call:

- generates pages for new Markdown files;
- regenerates pages whose content hash, expected output, or generator/template state changed;
- skips pages whose inputs and generated output still match the manifest;
- recopies a bundled asset when its source changed or its generated copy is missing or altered;
- removes only stale HTML files explicitly owned by the prior manifest when their source Markdown was deleted;
- preserves unrelated files already present in the destination.

The JSON result exposes `force_rebuild` so callers can distinguish an explicit
full regeneration from a normal incremental run.

The manifest and generated HTML are cache-like output, not knowledge content or a backup. Rebuild them from Markdown after loss. A successful incremental result does not replace `kb-audit.ps1`; audit the knowledge base separately when link or content correctness matters.

For ordinary accepted content updates, build once after the batch audit and
acceptance. A second idempotence build is reserved for a generator change,
release acceptance, or a concrete suspicion of non-determinism; it is not a
normal per-batch step.

## Current boundary

This first local-reading implementation provides recursive page generation, ordinary relative-page navigation, local styling, offline KaTeX formulas, and hash-based incremental rebuilds. It does not provide a local HTTP server, full-text search, backlinks, a relationship graph, authentication, public deployment, or copying of linked external project material.
