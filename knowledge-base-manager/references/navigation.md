# Curated reading navigation

Markdown collection pages are the source of truth for reading relationships.
The directory layout still groups file roles; it does not determine project
or topic membership. Do not move or duplicate a reusable entry merely to give
it a breadcrumb.

## Explicit collection region

The configured root entrypoint and formal pages with `type: project` or
`type: map` may declare one region. Place each marker on its own line:

```markdown
## Collected entries

<!-- kb-nav:children:start -->

- [A reusable entry](../knowledge/example.md)
- [Supporting source](../sources/paper.md)

<!-- kb-nav:children:end -->
```

Only Markdown links inside this region declare collection membership. Other
links remain ordinary references. Reuse the existing curated list where
possible instead of keeping a second list or adding `parents` to every child.
Code examples of markers or links do not declare membership. Keep the region
simple: ordinary links to existing Markdown files, not raw HTML, images,
external URLs, directory links, or links with query strings. Fragments may
identify a section, but membership refers to the whole target page.

The root collection links only project or map pages. Other collections may
include reusable entries, sources, decisions, or other collections. A child
may be collected by more than one page; an ordinary citation, filename prefix,
tag, or provenance project ID never creates a parent relationship.

Before publishing generated pages, the builder checks region pairing,
collection eligibility, target existence and containment, self-links, and
cycles. Duplicate links inside a region count once. Invalid declarations
block the build; they are not silently treated as ordinary links. Existing
knowledge bases without regions remain buildable, but no semantic membership
is inferred for them.

## Homepage and type indexes

Keep the homepage short: an introduction, a curated topic/project entry list
inside its collection region, and optional secondary type-browsing links
outside that region. A topic can collect multiple projects; independent
projects can stay directly on the homepage. Do not add a topic merely for
symmetry, and do not repeat all leaf entries on the homepage.

The conventional type directories have generated auxiliary indexes labeled
in Chinese (for example `全部知识条目` and `全部来源`). These lists use page
titles and include Markdown descendants of the type directory. They are
storage inventories, not collections, and do not create breadcrumb parents.
An existing directory `index.md` remains authoritative and is not overwritten
by an automatic index. Custom directories retain ordinary directory browsing.

The auditor accepts existing standard type-directory links on the configured
homepage outside its collection region; see the precise
[audit exception](audit-rules.md). Other directory links still warn, and type
inventories never establish a collection relationship or cure orphan entries.

## Reading behavior

A unique chain leading back to the configured entrypoint becomes the
breadcrumb. If the chain is ambiguous or disconnected, show the homepage and
current page plus the direct collection entrances, instead of inventing a
unique route. This does not track browser history or depend on how the page
was opened. An uncollected page is marked as such; type indexes are auxiliary
and are not marked as missing a collection.

Titles, paths, types, and explicit collection edges participate in the static
navigation digest. Changes to them invalidate generated page navigation;
ordinary body-only edits retain the per-page incremental behavior. The digest
and generated HTML are derived output, not a second editable knowledge source.

## Write-time maintenance

When promoting a new formal entry, add its required inbound link to one
appropriate project/map collection region. Keep source provenance on the
entry. Do not add reciprocal, sibling, or extra-parent links mechanically.
When renaming or moving a collected page, update collection links as well as
ordinary references. Audit the knowledge base, then build the static reader
to validate collection semantics. Do not claim that the general audit alone
has validated the navigation graph.

Adopting regions in an existing knowledge base requires authorization for the
specific collection pages and the normal designated-editor write gate. Do not
silently rewrite old pages as a side effect of a static build.
