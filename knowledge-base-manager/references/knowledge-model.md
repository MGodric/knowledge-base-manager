# Knowledge model

Read this reference when creating or promoting a formal entry, selecting its location, editing metadata, or changing internal links.

## Manifest and layout

The root contains a minimal `kb.yaml`:

```yaml
schema_version: 1
content_dir: content
entrypoint: content/index.md
```

All paths in the shared manifest are relative to the root.

For a persistent machine-local default, use `knowledge-base-manager.local.yaml` in the Codex configuration directory:

```yaml
root: "<absolute path on this machine>"
```

Use `$CODEX_HOME/knowledge-base-manager.local.yaml` when `CODEX_HOME` is set; otherwise use `~/.codex/knowledge-base-manager.local.yaml`. This file is local configuration, not knowledge content, and must not be copied into the synchronized root or distributed with the Skill.

Use this role-based layout unless the manifest or an existing migrated knowledge base explicitly defines compatible alternatives:

```text
content/
├─ index.md
├─ inbox/
├─ maps/
├─ knowledge/
├─ sources/
├─ decisions/
├─ projects/
├─ assets/
└─ archive/
```

- `inbox/`: low-friction, unpromoted captures.
- `maps/`: human-maintained curated navigation or map-of-content pages.
- `knowledge/`: reusable concepts, methods, observations, and explanations.
- `sources/`: notes about papers, books, webpages, or other evidence.
- `decisions/`: choices, alternatives, reasoning, consequences, and review conditions.
- `projects/`: project scope and knowledge outputs, not copies of project worktrees.
- `assets/`: images and attachments required by entries.
- `archive/`: superseded or processed material retained for recovery and history.

Create shallow topic subdirectories only after volume justifies them. Use links and maps for cross-topic relationships rather than forcing every entry into a single subject hierarchy. The root entrypoint links only stable project pages and human-maintained topic maps; it must not become a generated aggregation of leaf entries. Do not define topic-map thresholds, sharding, queues, or automatic aggregation. A future map proposal may be made only after unaggregated pages accumulate and the user explicitly asks for a manual batch proposal or operation.

## Formal entry metadata

Formal entries outside `inbox/` and `archive/` use:

```yaml
---
id: kb-YYYYMMDD-xxxx
type: concept
status: draft
created: YYYY-MM-DD
updated: YYYY-MM-DD
tags:
  - optional-tag
---
```

- `id` is permanently unique. Generate a random four-or-more hexadecimal suffix and check it against the whole knowledge base.
- `type` is one of `concept`, `method`, `source`, `decision`, `project`, or `map`.
- `status` is `draft`, `stable`, or `deprecated`. Do not mark an entry `stable` without the user’s confirmation unless a later local policy explicitly allows it.
- `created` and `updated` are ISO dates. Change `updated` only for substantive content changes.
- `tags` are optional and sparse. They improve discovery but do not replace links.
- The single level-one heading is the title. Do not duplicate it in front matter.

The root entrypoint may omit formal metadata, but it still needs one clear level-one heading.

## Body shape

Use the sections that materially help the entry; do not create empty boilerplate:

```markdown
# Title

> One to three sentences explaining what this is and when it is useful.

## Content

## Scope and limitations

## Sources

## Related entries
```

Adapt by type:

- `source`: bibliographic identity, source summary, evidence, and reusable conclusions.
- `decision`: context, decision, alternatives, rationale, consequences, and review trigger.
- `project`: scope, external location hints, and knowledge outputs.
- `map`: curated groups of links with explanatory context, not copied entry bodies.

Adapt the representation to the entry's information shape; these structures
are optional, not boilerplate. A project can use a status or asset matrix. A
method can pair inputs and outputs with ordered steps and explicit stop or
failure conditions. A decision can compare options, rationale, tradeoffs, and
review triggers. A source can use an evidence table that distinguishes what it
supports from its limits. A map can group links under short explanatory labels.
Use prose to preserve causal explanation and uncertainty around those
structures. “Distilled” removes duplicated or tree-copied content; it does not
suppress explanation needed to understand why, when, or with what limits an
entry applies.

For a new formal entry, require one reasonable inbound link from a parent
project page or topic map: the parent links to the new entry. Do not require a
reciprocal child-to-parent link or automatically add a `Related entries`
section, sibling links, or additional parents. Add them only when the user
explicitly requests a meaningful relationship; a formal entry otherwise
maintains only its supporting source provenance and necessary
scope/limitations.

Before writing body content, follow [the Markdown content format](markdown-format.md).
Mathematics uses KaTeX-compatible `$...$` or `$$...$$`; backticks retain their
ordinary Markdown meaning of literal code.

## Sources and reproduction

Project-derived formal entries should make every material claim traceable without copying source code, datasets, or bulky results into the knowledge base. Use a language-appropriate source/reproduction section. Every source item must include:

- source project or repository identity and a stable ASCII `project-id: <id>` matching `[a-z0-9][a-z0-9._-]{0,63}`;
- a project-relative document, source, data, or result path when one exists;
- the stable token `verified: YYYY-MM-DD`;
- `revision: <commit-or-version>` when the source has a reproducible revision, otherwise `version-state: <honest-state>` such as `uncommitted`, `unversioned`, `no-git-head`, or `unknown`;
- a short claim-to-source explanation.

An external absolute path is optional. Include it when it materially helps the user reopen the source on this machine. Label it explicitly as outside the knowledge base and machine-specific, and put `<!-- kb-external-local -->` on the same line so the deterministic auditor can distinguish intentional source locators from accidental non-portable internal links. The prose label follows the entry language; the three machine tokens remain stable across languages.

Label every absolute path explicitly as outside the knowledge base and machine-specific. A recommended shape is:

```markdown
## Sources and reproduction

- Project: `Example`; project-id: `example`; project-relative source: `docs/research/example.md`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [example.md](D:/Projects/example-project/docs/research/example.md); `verified: 2026-08-30`; `revision: abc1234`; supports: the bounded experimental observation in the preceding section, not the general claim.
```

If the repository has no `HEAD`, the source is untracked, or the relevant worktree differs from its commit, do not invent a revision. Use an accurate `version-state` and keep the verification date. An absolute path may be the only available locator for an unversioned local artifact, but it must not be the only description of what the artifact supports. Keep the distilled facts, scope, and limitations in the knowledge entry so human readers still understand it when the path is unavailable. Do not copy secrets, unpublished material, licensed data, or large artifacts merely to make provenance complete.

Preserve the language of existing material. For new text, follow the explicit request, surrounding content, and user environment. Mixed-language knowledge bases are valid.

Portable backup copies may add `external_dir: external` to their copied `kb.yaml`. This is generated backup structure, not a replacement for Markdown/YAML knowledge content. In those copies only, rewritten source links use `<!-- kb-portable-source -->` and resolve inside `external_dir`.

## Files and links

- Use a human-readable filename in the content’s language. Remove platform-forbidden characters and avoid long paths, trailing periods, and names distinguished only by case.
- Use standard relative Markdown links with `/` separators.
- Use meaningful link text and explain important relationships.
- Use full HTTPS URLs for external sources.
- A local absolute path may appear as an explicitly labeled external source locator. It is machine-specific and outside the knowledge base; durable explanation must not depend on access to it.
- Keep `id` unchanged on rename or move. Find and update every inbound link, then audit.
- Never overwrite a same-name destination. Merge only when the user’s request authorizes it and no meaning is lost.
