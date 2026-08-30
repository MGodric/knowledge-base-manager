# Safety and synchronization

Read this reference before any knowledge-base mutation, migration, conflict handling, or bulk rename.

## Authorization

- Search, explanation, review, and audit are read-only.
- Capture, organize, promote, link, rename, move, or repair authorize only the files necessary for that requested operation.
- Access to project data does not authorize permanent storage. Do not capture secrets, credentials, personal information, unpublished research, licensed material, or large artifacts without a clear user request and appropriate scope.
- Do not modify project files merely to advertise the knowledge base unless the user asks for project integration.

## Safe writes

- Before writing, report the user-confirmed absolute root. A bare folder name is not write authority.
- Searching a bare folder name always requires a user confirmation turn, whether zero, one, or several matches are found.
- Resolve every target to an absolute path and verify it stays under the selected root.
- Reject directory junctions and symbolic links in knowledge-base, source, bundle, and destination paths; reject file symbolic links rather than following them outside a reviewed tree. Ordinary locally available cloud-provider files are allowed.
- Re-read immediately before editing. Minimize the number of files changed.
- Never overwrite a same-name file or discard text to make a merge convenient.
- Prefer archive to deletion. Deletion requires an explicit request and exact targets.
- Preserve unknown `kb.yaml` fields and existing front matter not superseded by the requested change.
- A portable backup is generated metadata and copies; create it only outside the live KB and project source roots. Plan first, require explicit execution, and never overwrite an existing bundle or restore destination.
- Run backup and restore only under source and destination parents controlled by the current user, with no other process renaming or replacing those directories. Reparse checks are not a sandbox against a process that already has mutation rights on the parent.
- Report every created, modified, moved, archived, or unresolved file.

## User-managed file synchronization

Synchronization is configured and operated by the user. The Skill has no provider API dependency and can use Google Drive, OneDrive, Dropbox, or another service that exposes the knowledge base as an ordinary local folder. The synchronizer transports files; it is not a transaction system or knowledge database.

- Keep Markdown and required attachments in the synchronized root.
- Keep databases, search indexes, generated HTML, caches, logs, temporary files, dependencies, and machine-specific configuration outside it. Absolute source locators may remain in Markdown only when explicitly labeled as outside the knowledge base and machine-specific.
- If a conflict copy, parallel version, or unexpected duplicate appears, stop automatic merging. Preserve all versions and explain the conflict.
- Avoid broad mechanical rewrites that touch every note. Plan and report bulk migrations before executing them.
- After writes, audit the latest synchronized state. An audit cannot prove that another machine has finished syncing.
- Make remote-only placeholders locally available before audit or backup. The Skill does not hydrate files, wait for upload completion, resolve provider conflicts, or verify remote state.

## Content integrity

- Keep source claims, project observations, inference, and uncertainty distinguishable.
- Preserve original quotations and citations within copyright and user-provided constraints.
- Do not generalize a finding beyond its stated model, environment, sample, time, or evidence.
- When meanings conflict, keep both versions until the user or evidence resolves them.
- Do not silently translate existing entries. Follow explicit language requests and local content conventions.

## Stopping conditions

Stop and request direction when:

- The root cannot be verified.
- A requested destination would escape the root.
- A merge has multiple materially different outcomes.
- A conflict copy cannot be reconciled without losing information.
- A bulk move has unresolved collisions or would leave known broken links.
- Completing the request would require storing sensitive or out-of-scope project material.
