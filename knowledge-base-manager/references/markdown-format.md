# Markdown content format

Read this reference before Capture, Promote, or any other operation that writes
knowledge content. Markdown remains the source of truth, and the same source
must remain readable in a generic Markdown reader and render correctly in the
bundled static HTML reader.

## Verified renderer profile

The current local behavior tests run on PowerShell 7.6.4 with
`Microsoft.PowerShell.MarkdownRender` 7.2.1 and `Markdig.Signed` 0.44.0.
That is the verified baseline, not a claim that every PowerShell 7 minor
release supports every feature below. Until CI establishes a minimum version,
the behavior tests define this Skill's supported renderer profile.

Choose a structure for the information being preserved, rather than forcing a
template. Distilled knowledge is not terse knowledge: remove duplicated or
tree-copied material, but retain causal rationale, consequences, uncertainty,
and boundaries that make a conclusion reusable.

- Use ordinary prose for explanation, causal rationale, and qualifications.
- Use a table when the reader must compare repeated dimensions, states, or
  options across several items.
- Use ordered lists for a sequence whose order changes the result; use nested
  lists for bounded substeps or grouped detail.
- Use task lists for static, checkable gates. They render as disabled
  checklists, not interactive forms.
- Use blockquotes for concise boundaries or warnings. GitHub alerts are useful
  only when the generated page has the bundled alert CSS.
- Use fenced code for executable examples and inline code for literal commands,
  identifiers, paths, labels, and strings.

Do not manufacture empty tables, checklist rows, or headings merely to look
structured. Keep explanatory prose beside a table or list whenever its meaning
would otherwise be unclear.

### Supported Markdown

The tested profile supports headings, paragraphs, emphasis, strikethrough,
ordered/unordered/nested lists, task lists, tables and column alignment,
blockquotes, fenced and inline code, inline links and external autolinks,
horizontal rules, footnotes, and the current math delimiters.

### Conditional features

- GitHub alerts are presentation-supported after the static builder's bundled
  CSS is present; keep their warning/boundary meaning understandable as plain
  Markdown too.
- Heading anchors may be used in ordinary inline links, but the auditor does
  not validate anchors.
- Images stored as authorized knowledge-base assets may remain durable,
  canonical Markdown-linked content. The current static builder does not copy
  local image assets, so static-reader parity is not guaranteed; external or
  machine-local images remain restricted and must not be relied on.

### Unsupported or restricted features

Do not use raw HTML (`details`, forms, `script`, `style`, `iframe`, or similar)
as canonical knowledge content. The required KB marker comments such as
`<!-- kb-external-local -->` and `<!-- kb-literal-code -->` remain allowed.
Definition lists, Mermaid and other non-native diagrams, Obsidian wiki links,
reference-style internal links before the builder can rewrite them, and
interactive forms are not supported canonical features.

## Mathematics versus literal code

Write mathematical notation as KaTeX-compatible TeX:

- inline mathematics uses `$...$`;
- display mathematics uses `$$...$$` on separate lines;
- use TeX commands for Greek letters, operators, relations, and text inside a
  formula instead of spelling mathematical symbols as programming identifiers.

Examples:

```markdown
Process data $x$ with tag $\tau_x = \alpha x$.

Inversion is performed locally in $\mathrm{GF}(2^8)$, while the zero case is
handled by $\delta(x)$.

$$
P(X=x \mid \mathrm{accepted})
$$
```

Do not write those expressions as `` `tau_x = alpha*x` ``, `` `GF(2^8)` ``,
or `` `delta(x)` ``. Backticks mean literal code and cause the static reader to
emit `<code>`; KaTeX intentionally does not render inside code spans or fenced
code blocks.

Use backticks for actual identifiers, evidence labels, commands, file names,
literal strings, and code fragments, for example `` `LITERATURE` ``,
`` `d-SNI` ``, `` `kb-audit.ps1` ``, or `` `Get-Item` ``. Keep complete code
examples in fenced code blocks.

When an intentional literal code span resembles mathematics closely enough to
trigger the auditor, add `<!-- kb-literal-code -->` on the same line. This is a
narrow suppression for real code, not a way to hide a formula.

## Tables and punctuation

Prefer inline mathematics inside Markdown table cells. Put a display formula
before or after a table instead of embedding `$$...$$` inside a cell. Use TeX
relations such as `\mid` inside formulas rather than a raw `|` that could be
interpreted as a table delimiter.

Keep sentence punctuation outside the closing math delimiter unless the
punctuation is part of the mathematical expression.

## Write-time check

For every created or substantively changed knowledge Markdown file:

1. Inventory equations, variables, functions, sets, probabilities, field
   notation, Greek symbols, superscripts, and subscripts.
2. Decide whether each span is mathematics or literal code; do not classify by
   typography alone.
3. Normalize mathematics to `$...$` or `$$...$$` and KaTeX-compatible TeX.
4. Run `scripts/kb-audit.ps1` and resolve every `MATH_CODE_SPAN` issue in the
   changed files before reporting the write complete.
5. When formula presentation is material to the request, rebuild the static
   reader and inspect the generated page directly.

The auditor detects high-confidence mistakes, not every possible semantic
misclassification. A clean audit does not replace this review.
