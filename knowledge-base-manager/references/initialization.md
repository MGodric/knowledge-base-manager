# Initialization

Use this workflow to create a knowledge base or adopt an existing directory. Initialization is a write operation and must follow `safety.md` and, when available, `delegation.md`.

## Resolve before creating

1. Resolve the requested location using the rules in `SKILL.md`.
   Run `scripts/kb-resolve-root.ps1`; do not reimplement bare-name search ad hoc.
2. When the request contains only a folder name, search the active project source/workspace folders and show every exact match, or state that none exists.
3. Stop and obtain an absolute path from the user regardless of the number of matches.
4. Convert the confirmed root to an absolute canonical path and report it before writing.

Never create a directory merely by appending a bare name to the current project. A new directory is allowed only after the user confirms its exact absolute path.

Keep these states distinct:

- `cleanup_target`: an existing directory the user explicitly authorized removing or archiving;
- `candidate_root`: an unresolved search result;
- `active_kb_root`: the absolute destination the user confirmed;
- `persisted_root`: an optional machine-local default.

An anaphoric phrase such as "the one just created" can resolve `cleanup_target` when the prior creation is unambiguous. It cannot silently become `active_kb_root` for a new initialization. In a delete-and-reinitialize request, inventory and authorize the old target, then independently resolve and confirm the new destination.

Once an absolute candidate has been shown and the user confirms it, bind it as `active_kb_root` for the remainder of the same ongoing task. Revalidate the directory or manifest before later operations, but do not ask the user to confirm the same root again. Ask again only if the user changes the location, the stored state is ambiguous, or filesystem evidence conflicts with it.

## Initialize an empty root

When the exact root does not exist and creation is authorized, create only that directory. When it exists, confirm it is a directory and inventory it before writing.

For an empty root:

1. Create `kb.yaml` with relative `content_dir` and `entrypoint` fields.
2. Create the content directories defined in `knowledge-model.md`.
3. Create a concise human-readable `content/index.md` in the language selected by the shared language rule.
4. Add a short root `README.md` only when it helps a person understand the directory without opening the manifest.
5. Do not add machine-specific absolute paths, generated HTML, databases, caches, or editor-specific configuration.
6. Run the audit and report every created path.

Initialization is idempotent: do not overwrite an existing file or replace a partially initialized tree.

## Adopt a non-empty root

If the directory contains files but lacks `kb.yaml`, do not impose the proposed structure immediately.

1. Inventory its top-level structure and representative Markdown files read-only.
2. Identify collisions, existing conventions, and paths that would need migration.
3. Propose a compatibility or migration mapping.
4. Write only after the user authorizes that mapping.
5. Preserve existing information and refuse destination overwrites.

If `kb.yaml` already exists, treat the request as verification or repair rather than fresh initialization. Preserve unknown manifest fields.

## Optional local default

Use `active_kb_root` throughout the same ongoing task and include it in every subagent handoff. Do not discard it merely because a later user turn starts another Capture or Promote operation. A new task, restart, or compacted context that no longer contains an unambiguous confirmed path requires the persisted setting or a new confirmation.

Registering the root in `knowledge-base-manager.local.yaml` is separate from initializing knowledge content. When asking the required root-confirmation question, also mention that the user may save it as the local default in the same reply. If they do not request persistence, initialization still proceeds and the same-task binding remains valid. Keep the file outside the synchronized knowledge base and preserve unrelated local settings.

Use `root` when one knowledge base should be the machine-wide default. Use `project_roots` only when a particular project needs a different knowledge base:

```yaml
schema_version: 1
root: 'D:\KnowledgeBase'
project_roots:
  'D:\Projects\example-project': 'D:\KnowledgeBase'
```

Canonicalize project paths before matching them; path matching is case-insensitive on Windows. Reload this file on every skill invocation instead of injecting it permanently into the conversation.

Do not write machine-specific absolute paths into a repository `AGENTS.md` by default. Use `AGENTS.md` only when the repository intentionally owns a portable, project-wide instruction, such as a stable relative path that collaborators should share.
