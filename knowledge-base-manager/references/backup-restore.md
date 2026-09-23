# Portable backup and restore

Use this workflow when a user needs a transferable, self-contained backup rather than a sync copy. It is intentionally narrow: `ReferenceComplete` copies the complete KB plus only structured local project sources that are explicitly registered in Markdown. It never writes to the live KB.

Run commands below with Python 3.12+ using `python -X utf8 ./scripts/kb.py`. No PowerShell or third-party background services are required.

## ReferenceComplete backup

Run a plan first; it performs read-only validation and creates nothing:

```bash
python -X utf8 ./scripts/kb.py backup --root "<knowledge-base-root>" --destination "<backup-parent>"
```

The default text output lists every input file and its source and portable paths. Use `--format json` for complete records including byte size, UTC modification time, SHA-256, registered reference mappings, totals, and `plan_digest`. Display the complete path-marked file list to the user and ask for explicit confirmation. A generic request such as “back it up” is not execution authorization.

Backup plans use `plan_schema_version: 2`, with deterministic Unicode ordinal record ordering and SHA-256 over compact UTF-8 JSON including the plan version. This deliberately replaces the culture-sensitive legacy PowerShell plan digest. An old or unversioned confirmation digest is not transferable: execution returns `reconfirm_required` with the new plan before creating any output directory. Review and confirm the new digest. The portable bundle manifest remains schema version 1; existing v1 bundles remain eligible for verification and restore.

After confirmation, creation requires the exact digest from that displayed plan:

```bash
python -X utf8 ./scripts/kb.py backup --root "<knowledge-base-root>" --destination "<backup-parent>" --execute --confirmed-plan-digest "<plan_digest>"
```

There are no further confirmation prompts when the source snapshot is unchanged. The script recomputes the full plan immediately before creating any destination or staging directory and once more before publication. Before and after each individual copy it checks that file's canonical path, size, UTC modification time, and SHA-256. This is a small fixed number of complete scans plus linear per-file checks, not a complete rehash for every copied file. A missing digest returns `confirmation_required`; a wrong or stale digest, or any later source/mapping drift, returns `reconfirm_required` with a new list and requires a new explicit confirmation. It never publishes `portable-kb/` after such drift; a drift discovered after staging starts retains and reports the incomplete directory for inspection.

The destination becomes `portable-kb/` and must not already exist or lie in the KB/project source roots. Creation first builds `Destination/.incomplete-<id>`, verifies checksums, manifest/link containment, and the copied KB audit there, then publishes it with a fail-if-exists directory move. A failed build is never published; its retained incomplete path is reported for inspection. The bundle contains `content/`, `external/projects/`, a copied-and-extended `kb.yaml`, `backup-manifest.json`, `CHECKSUMS.sha256`, `backup-report.md`, and `README-RESTORE.md`.

Publication requires an atomic fail-if-exists directory move on the host platform and filesystem. If the required primitive is unavailable or fails, the operation stops and reports the staging directory; it never falls back to an overwrite-capable rename or reports an unpublished staging directory as success.

Knowledge-base roots, registered source paths, backup destinations, and every bundle tree must use ordinary filesystem paths. Directory junctions and symbolic links, and file symbolic links, are rejected rather than followed. Hydrated cloud-provider files that are ordinary files remain supported; make remote-only placeholders locally available before planning a backup.

This is a local-user backup tool, not a sandbox against another process that can rename or replace directories during execution. The knowledge-base root, bundle root, and destination parent must be access-controlled by the user and must not be concurrently mutated. Reparse checks reject pre-existing and observed redirects; they do not replace trustworthy parent-directory permissions or handle-relative OS APIs.

An eligible source is a same-line local Markdown link marked `<!-- kb-external-local -->` and containing a human `Project:` (or `项目:`), an explicit stable `project-id:` matching `[a-z0-9][a-z0-9._-]{0,63}`, `project-relative source:`, `verified: YYYY-MM-DD`, and `revision:` or `version-state:`. The source path must exactly agree with its project-relative suffix. The copied Markdown replaces only that link target and marker with a relative portable target and `<!-- kb-portable-source -->`.

Legacy absolute local links without the marker block a complete backup. Exclude one only with a specific reason, for example `--ignore-legacy-path "D:\old\missing.md|obsolete locator retained for history"`; exclusions remain in generated metadata. Do not use an ignore to conceal a source that is required for the requested completeness claim.

`ProjectSnapshot` is explicitly deferred in v1 and returns a blocker rather than a partial backup.

## Verification and restore

```bash
python -X utf8 ./scripts/kb.py verify-backup --bundle "<backup-parent>/portable-kb"
python -X utf8 ./scripts/kb.py restore --bundle "<backup-parent>/portable-kb" --destination "<new-root>"
python -X utf8 ./scripts/kb.py restore --bundle "<backup-parent>/portable-kb" --destination "<new-root>" --execute
```

Verification checks hashes, one-to-one manifest/file agreement, portable-link containment, redirecting reparse points, and the complete status. Restore requires a destination that does not yet exist. It pins the verified manifest, copies only its exact portable KB records into a sibling `.restore-incomplete-*` directory, checks source and destination hashes before and after copying, audits the staged KB, then publishes with a fail-if-exists directory move. A failed restore leaves the reported staging directory for inspection and never publishes the requested destination. `Relink` restore is deferred in v1; portable restore is the supported production path.

`CHECKSUMS.sha256` provides internal integrity checking. It can detect accidental corruption or modification when the checksum file is trusted, but it is not a signature and does not authenticate who produced a bundle. Accept bundles only from a trusted channel; optional signed manifests are a future extension.

## Audit behavior

Ordinary relative links remain confined to `content_dir`. A `<!-- kb-portable-source -->` link is allowed only when `kb.yaml` declares a contained `external_dir` and the target remains inside it. This is a backup-only representation; live entries continue using the external-local marker and their machine-specific provenance.
