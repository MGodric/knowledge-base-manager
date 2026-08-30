# Markdown content format

Read this reference before Capture, Promote, or any other operation that writes
knowledge content. Markdown remains the source of truth, and the same source
must remain readable in a generic Markdown reader and render correctly in the
bundled static HTML reader.

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
