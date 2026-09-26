# Markdown content format

Read this reference before Capture, Promote, or any other operation that writes
knowledge content. Markdown remains the source of truth, and the same source
must remain readable in a generic Markdown reader and render correctly in the
bundled static HTML reader.

## Verified renderer profile

The current local behavior tests run on Python 3.12+ with `markdown-it-py`
and `mdit-py-plugins`. That is the verified baseline, tested across Windows,
Ubuntu, and macOS in CI. The behavior tests define this Skill's supported
renderer profile.

This reference controls representation and renderer compatibility. For Promote
and Project Synthesis, [knowledge-writing.md](knowledge-writing.md) controls
question selection, explanation, and content acceptance. Choose a structure for
the information being preserved rather than forcing a template.

- Use ordinary prose for explanation, causal rationale, and qualifications.
- Use a table when the reader must compare repeated dimensions, states, or
  options across several items.
- Use ordered lists for a sequence whose order changes the result; use nested
  lists for bounded substeps or grouped detail.
- Use task lists for static, checkable gates. They render as disabled
  checklists, not interactive forms.
- Use blockquotes when a quotation or short callout helps reading; they are not
  required for every qualification. GitHub alerts are useful only when the
  generated page has the bundled alert CSS.
- Use fenced code for executable examples and inline code for literal commands,
  identifiers, paths, labels, and strings.

### Inline code badges and plain prose

Inline code (` `...` `) renders with badge styling in the static reader (light background, border, monospace font). Use it intentionally to provide visual scanning anchors for concrete artifacts without cluttering prose with typographical noise:

- **Use inline code for:**
  1. *Epistemic and status labels*: Evidence markers like `（`PROVED`）`, `（`EXHAUSTIVE`）`, `（`EXPERIMENTAL`）`, `（`HEURISTIC`）`, `（`LITERATURE`）`, and workflow states like `PASS`, `FIX`, `BLOCKED`, `draft`, `stable`.
  2. *Literal paths, files, and code identifiers*: e.g., `~/.claude/CLAUDE.md`, `src/aesop/models.py`, `settings.json`, `f_x(k)`.
  3. *Commands, flags, literals, and hex witness strings*: e.g., `git status`, `--profile write`, `60ded0d98010de933785157a00287122`.
  4. *Configuration keys and exact UI labels*: e.g., `OPENAI_API_KEY`, `Auto Select`, `Multi-Monitor Sync (MMS)`.

- **Avoid inline code (keep as plain text, math, or bold emphasis) for:**
  1. *Mathematical symbols and variables*: Use `$x$`, `$E_K(P)$`, `$\mathrm{GF}(2^8)$`, never `` `x` `` or `` `E_K(P)` ``.
  2. *Conceptual terminology and domain nouns*: Use ordinary prose or `**bold**` (e.g., bijection, permutation, side-channel attack), not `` `bijection` ``.
  3. *General technical acronyms in prose flow*: Use ordinary text (e.g., "running AES on CPU and GPU"), not `` `AES` `` or `` `CPU` ``.
  4. *Long descriptive phrases*: Keep inline code to short tokens (1–3 words); do not wrap full clauses in backticks.

Do not manufacture empty tables, checklist rows, or headings merely to look
structured. Keep explanatory prose beside a table or list whenever its meaning
would otherwise be unclear.

### Supported Markdown

The tested profile supports headings, paragraphs, emphasis, strikethrough,
ordered/unordered/nested lists, task lists, tables and column alignment,
blockquotes, fenced and inline code, inline links and external autolinks,
horizontal rules, footnotes, and the current math delimiters.

### Conditional features

- Optional disclosures may use plain `<details>` and `<summary>` tags. Put
  each tag on its own line and leave a blank line after `</summary>` and
  before `</details>` so Markdown paragraphs, links and fenced code inside
  render normally. Keep the summary descriptive and essential conclusions
  and limitations visible outside the disclosure. Do not add inline styles,
  event handlers or scripts. This is a narrow raw-HTML exception; readers
  that strip HTML may show the body expanded or omit the disclosure UI.
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

Do not use other raw HTML (forms, `script`, `style`, `iframe`, or similar)
as canonical knowledge content. Plain `details`/`summary` as described above
and the required KB marker comments such as
`<!-- kb-external-local -->` and `<!-- kb-literal-code -->` remain allowed,
as do the paired `kb-nav:children:start` / `kb-nav:children:end` comments
specified in [reading navigation](navigation.md).
Definition lists, Mermaid and other non-native diagrams, Obsidian wiki links,
reference-style internal links before the builder can rewrite them, and
interactive forms are not supported canonical features.

## Mathematics versus literal code

Write mathematical notation as KaTeX-compatible TeX:

- inline mathematics uses `$...$`;
- display mathematics uses `$$...$$` with opening and closing delimiters each on their own standalone lines, surrounded by blank lines:
  - preceding introductory prose, followed by a blank line;
  - opening `$$` on its own line;
  - formula content (or multi-line environment such as `\begin{aligned}...\end{aligned}`);
  - closing `$$` on its own line;
  - a blank line, followed by the continuing explanation.
- keep ordinary prose and explanatory sentences outside math delimiters; never wrap full sentences or paragraphs in `\text{...}` to force prose into math regions. Reserve `\text{...}` for concise words or labels that are genuinely part of the mathematical formula (such as `\Pr(S\text{ 闭合})`).
- use TeX commands for Greek letters, operators, relations, and text inside a
  formula instead of spelling mathematical symbols as programming identifiers.

Examples:

```markdown
Process data $x$ with tag $\tau_x = \alpha x$.

Inversion is performed locally in $\mathrm{GF}(2^8)$, while the zero case is
handled by $\delta(x)$:

$$
P(X=x \mid \mathrm{accepted})
$$

Here the probability represents the normalized acceptance over all inputs.

Multi-step derivation with aligned equations:

$$
\begin{aligned}
\Delta C &= C_1 \oplus C_2 \\
\Delta A &= A_1 \oplus A_2
\end{aligned}
$$

The derivation establishes the difference propagation boundary.
```

Do not write those expressions as `` `tau_x = alpha*x` ``, `` `GF(2^8)` ``,
or `` `delta(x)` ``. Backticks mean literal code and cause the static reader to
emit `<code>`; KaTeX intentionally does not render inside code spans or fenced
code blocks.

Use backticks for actual identifiers, evidence labels, commands, file names,
literal strings, and code fragments, for example `` `LITERATURE` ``,
`` `d-SNI` ``, `` `kb.py` ``, or `` `Get-Item` ``. Keep complete code
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
4. Run `python -X utf8 ./scripts/kb.py audit` and resolve every `MATH_CODE_SPAN` issue in the
   changed files before reporting the write complete.
5. When formula presentation is material to the request, rebuild the static
   reader and inspect the generated page directly.

The auditor detects high-confidence mistakes, not every possible semantic
misclassification. A clean audit does not replace this review.
