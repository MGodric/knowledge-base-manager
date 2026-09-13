"""Implementation of inspect, search, and read commands."""

from __future__ import annotations

import collections
import hashlib
import json
import os
import re
import urllib.parse
from typing import Any

from .markdown_reader import parse_markdown_page
from .model import (
    VALID_INCLUDES,
    VALID_PAGE_STATUSES,
    VALID_PAGE_TYPES,
    Diagnostic,
    Envelope,
    Page,
    Relation,
    Section,
)
from .paths import (
    assert_no_redirecting_reparse_point,
    get_canonical_path,
    get_normalized_relative_path,
    is_explicit_relative_path,
    resolve_contained_path,
    split_and_decode_target_path,
    test_path_inside_root,
)
from .yaml_reader import parse_yaml_text


def normalize_target_page_locator(
    content_root: str, current_page_path: str, target: str
) -> tuple[str, str]:
    """Normalize link target.

    Returns (kind, locator):
    - ('external', target) if web or machine-absolute or mailto
    - ('page', normalized_content_rel_path) if relative markdown link
    """
    if not target:
        return "page", ""
    target_clean = target.strip()
    if target_clean.startswith("<") and target_clean.endswith(">"):
        target_clean = target_clean[1:-1].strip()

    # Check external schemes or absolute paths
    if (
        bool(re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target_clean))
        or bool(re.match(r"^[A-Za-z]:[\\/]", target_clean))
        or target_clean.startswith(("//", "\\\\"))
    ):
        return "external", target_clean

    # Strip fragment and query using shared split_and_decode_target_path
    decoded_path, query, fragment = split_and_decode_target_path(target_clean)

    if not decoded_path:
        # Same-page reference
        return "page", current_page_path.replace("\\", "/")

    # Resolve relative to current_page_path directory
    cur_dir = os.path.dirname(current_page_path.replace("\\", "/"))
    combined = os.path.normpath(os.path.join(cur_dir, decoded_path)).replace("\\", "/")
    if combined.startswith("./"):
        combined = combined[2:]
    return "page", combined


def load_manifest(root: str) -> tuple[dict[str, Any], list[Diagnostic], int, str]:
    """Load and strictly validate kb.yaml manifest within root.

    Returns (manifest_dict, diagnostics, exit_code, status_string).
    """
    root_canon = get_canonical_path(root)
    if not os.path.isdir(root_canon):
        return (
            {},
            [
                Diagnostic(
                    code="TARGET_NOT_FOUND",
                    severity="error",
                    file=None,
                    span=None,
                    target=root,
                    message="Knowledge base root does not exist or is not a directory.",
                )
            ],
            3,
            "failed",
        )

    try:
        assert_no_redirecting_reparse_point(root_canon, "knowledge base root")
    except Exception as exc:
        return (
            {},
            [
                Diagnostic(
                    code="PATH_REDIRECTED",
                    severity="error",
                    file=None,
                    span=None,
                    target=root_canon,
                    message=str(exc),
                )
            ],
            3,
            "failed",
        )

    manifest_path = os.path.join(root_canon, "kb.yaml")
    if not os.path.isfile(manifest_path):
        return (
            {},
            [
                Diagnostic(
                    code="MANIFEST_NOT_FOUND",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=manifest_path,
                    message="The root must contain kb.yaml.",
                )
            ],
            3,
            "failed",
        )

    try:
        assert_no_redirecting_reparse_point(manifest_path, "kb.yaml")
        with open(manifest_path, "r", encoding="utf-8") as f:
            content = f.read()
        manifest, m_diags = parse_yaml_text(content, filename="kb.yaml")
    except Exception as exc:
        return (
            {},
            [
                Diagnostic(
                    code="PARSE_FAILED",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=manifest_path,
                    message=str(exc),
                )
            ],
            3,
            "failed",
        )

    if m_diags:
        return {}, m_diags, 3, "failed"

    if not isinstance(manifest, dict):
        return (
            {},
            [
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=None,
                    message="kb.yaml content must be a mapping.",
                )
            ],
            4,
            "invalid",
        )

    # Validate content_dir boundary
    content_dir = str(manifest.get("content_dir", "content")).strip()
    if not is_explicit_relative_path(content_dir):
        return (
            {},
            [
                Diagnostic(
                    code="PATH_OUTSIDE_SCOPE",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=content_dir,
                    message=f"content_dir '{content_dir}' escapes root or is absolute.",
                )
            ],
            4,
            "invalid",
        )
    content_dir_canon, err = resolve_contained_path(root_canon, content_dir)
    if err or not content_dir_canon:
        return (
            {},
            [
                Diagnostic(
                    code="PATH_OUTSIDE_SCOPE",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=content_dir,
                    message=f"content_dir '{content_dir}' escapes root.",
                )
            ],
            4,
            "invalid",
        )

    # Validate entrypoint boundary if specified
    if "entrypoint" in manifest and str(manifest["entrypoint"]).strip():
        entrypoint = str(manifest["entrypoint"]).strip()
        if not is_explicit_relative_path(entrypoint):
            return (
                {},
                [
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file="kb.yaml",
                        span=None,
                        target=entrypoint,
                        message=f"entrypoint '{entrypoint}' escapes root or is absolute.",
                    )
                ],
                4,
                "invalid",
            )
        ep_canon, ep_err = resolve_contained_path(root_canon, entrypoint)
        if ep_err or not ep_canon:
            return (
                {},
                [
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file="kb.yaml",
                        span=None,
                        target=entrypoint,
                        message=f"entrypoint '{entrypoint}' escapes root.",
                    )
                ],
                4,
                "invalid",
            )

    # Validate schema_version
    schema_ver = manifest.get("schema_version")
    if schema_ver != 1 and schema_ver != "1":
        return (
            {},
            [
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=str(schema_ver),
                    message=f"Only schema_version 1 is supported; found '{schema_ver}'.",
                )
            ],
            4,
            "invalid",
        )

    # Verify content_root directory exists and is not redirected
    try:
        assert_no_redirecting_reparse_point(content_dir_canon, "content_dir")
    except Exception as exc:
        return (
            {},
            [
                Diagnostic(
                    code="PATH_REDIRECTED",
                    severity="error",
                    file="kb.yaml",
                    span=None,
                    target=content_dir_canon,
                    message=str(exc),
                )
            ],
            3,
            "failed",
        )

    if not os.path.isdir(content_dir_canon):
        return (
            {},
            [
                Diagnostic(
                    code="CONTENT_DIR_NOT_FOUND",
                    severity="error",
                    file=content_dir,
                    span=None,
                    target=content_dir_canon,
                    message="The configured content directory does not exist.",
                )
            ],
            3,
            "failed",
        )

    return manifest, [], 0, "ok"


def compute_file_hash_and_text(full_path: str) -> tuple[str, str]:
    with open(full_path, "rb") as f:
        raw = f.read()
    content_hash = hashlib.sha256(raw).hexdigest()
    # Strip UTF-8 BOM from text representation if present
    if raw.startswith(b"\xef\xbb\xbf"):
        text = raw[3:].decode("utf-8")
    else:
        text = raw.decode("utf-8")
    return content_hash, text


def load_page(
    root: str, content_root: str, rel_path: str
) -> tuple[Page | None, Any | None, list[Diagnostic]]:
    if not is_explicit_relative_path(rel_path):
        return (
            None,
            None,
            [
                Diagnostic(
                    code="PATH_OUTSIDE_SCOPE",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=rel_path,
                    message=f"Path '{rel_path}' is absolute or not a valid relative path.",
                )
            ],
        )

    full_path, err = resolve_contained_path(content_root, rel_path)
    if err or not full_path:
        return (
            None,
            None,
            [
                Diagnostic(
                    code="PATH_OUTSIDE_SCOPE",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=rel_path,
                    message=f"Path '{rel_path}' escapes content root.",
                )
            ],
        )

    if not os.path.isfile(full_path):
        return (
            None,
            None,
            [
                Diagnostic(
                    code="TARGET_NOT_FOUND",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=rel_path,
                    message=f"Target file does not exist: {rel_path}",
                )
            ],
        )

    try:
        assert_no_redirecting_reparse_point(full_path, "page")
        content_hash, text = compute_file_hash_and_text(full_path)
        parsed_md, diags = parse_markdown_page(text, filename=rel_path)

        fm = parsed_md.front_matter_fields
        entry_id = str(fm.get("id")) if fm.get("id") is not None else None
        page_type = str(fm.get("type")) if fm.get("type") is not None else None
        status = str(fm.get("status")) if fm.get("status") is not None else None
        tags = list(fm.get("tags", [])) if isinstance(fm.get("tags"), list) else []

        source_locators = [s.to_locator_dict() for s in parsed_md.sources]

        page = Page(
            path=rel_path.replace("\\", "/"),
            entry_id=entry_id,
            title=parsed_md.title or os.path.splitext(os.path.basename(rel_path))[0],
            type=page_type,
            status=status,
            tags=tags,
            source_locators=source_locators,
            content_hash=content_hash,
            raw_text=text,
            metadata=fm,
        )
        return page, parsed_md, diags
    except Exception as exc:
        return (
            None,
            None,
            [
                Diagnostic(
                    code="FILE_UNREADABLE",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=rel_path,
                    message=str(exc),
                )
            ],
        )


def get_all_content_markdown_files(content_root: str) -> list[str]:
    results: list[str] = []
    for dirpath, dirnames, filenames in os.walk(content_root):
        dirnames.sort()
        filenames.sort()
        for f in filenames:
            if f.lower().endswith(".md"):
                full = os.path.join(dirpath, f)
                rel = get_normalized_relative_path(content_root, full)
                results.append(rel)
    return results


def inspect_command(
    root: str,
    path: str | None = None,
    scope: str | None = None,
    page_type: str | None = None,
    status: str | None = None,
    include_archive: bool = False,
    include: list[str] | None = None,
    limit: int | None = None,
    offset: int | None = None,
    expect_view: str | None = None,
) -> tuple[int, Envelope]:
    root_canon = get_canonical_path(root) if os.path.exists(root) else root

    # 1. Validate page_type enum
    if page_type is not None and page_type not in VALID_PAGE_TYPES:
        return 4, Envelope(
            command="inspect",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target="--type",
                    message=f"Invalid page type '{page_type}'. Expected one of: {', '.join(sorted(VALID_PAGE_TYPES))}.",
                )
            ],
        )

    # 2. Validate status enum
    if status is not None and status not in VALID_PAGE_STATUSES:
        return 4, Envelope(
            command="inspect",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target="--status",
                    message=f"Invalid status '{status}'. Expected one of: {', '.join(sorted(VALID_PAGE_STATUSES))}.",
                )
            ],
        )

    # 3. Validate include items
    if include:
        invalid_inc = [inc_item for inc_item in include if inc_item not in VALID_INCLUDES]
        if invalid_inc:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target="--include",
                        message=f"Invalid include value(s): {', '.join(invalid_inc)}. Expected one of: {', '.join(sorted(VALID_INCLUDES))}.",
                    )
                ],
            )

    # 4. Mutual exclusion and parameter applicability
    if path is not None:
        if limit is not None:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target="--limit",
                        message="Cannot specify pagination parameter '--limit' with single-page inspect ('--path').",
                    )
                ],
            )
        if offset is not None:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target="--offset",
                        message="Cannot specify pagination parameter '--offset' with single-page inspect ('--path').",
                    )
                ],
            )
        if expect_view is not None:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target="--expect-view",
                        message="Cannot specify '--expect-view' with single-page inspect ('--path').",
                    )
                ],
            )
        if scope is not None or page_type is not None or status is not None:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target=None,
                        message="path cannot be combined with scope, type, or status.",
                    )
                ],
            )
    else:
        # List mode
        if include:
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target="--include",
                        message="Cannot specify '--include' with list inspect. Use '--path <file>' for single-page inspection.",
                    )
                ],
            )
        if limit is None:
            limit = 50
        if offset is None:
            offset = 0

    manifest, m_diags, m_code, m_status = load_manifest(root_canon)
    if m_diags:
        return m_code, Envelope(
            command="inspect",
            status=m_status,
            root=root_canon,
            data=None,
            diagnostics=m_diags,
        )

    content_dir = manifest.get("content_dir", "content")
    content_root = get_canonical_path(content_dir, root_canon)

    # Single page inspect
    if path is not None:
        if not is_explicit_relative_path(path):
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file=path,
                        span=None,
                        target=path,
                        message=f"Path '{path}' is absolute or not a valid relative path.",
                    )
                ],
            )
        rel_path = path.replace("\\", "/")
        page, parsed_md, diags = load_page(root_canon, content_root, rel_path)
        if page is None:
            code = 4 if any(d.code == "PATH_OUTSIDE_SCOPE" for d in diags) else 3
            st = "invalid" if code == 4 else "not_found"
            return code, Envelope(
                command="inspect",
                status=st,
                root=root_canon,
                data=None,
                diagnostics=diags,
            )

        inc = include or []
        sections_out = None
        if "sections" in inc:
            sections_out = [s.to_dict() for s in parsed_md.sections]

        relations_out = None
        has_scan_errors = False
        if "relations" in inc:
            relations_out = []
            rel_path_norm = rel_path.replace("\\", "/")

            # 1. Outbound relations from current page
            for lk in parsed_md.link_occurrences:
                if lk.is_in_collection and lk.is_direct_collection:
                    kind_ep, to_loc = normalize_target_page_locator(
                        content_root, rel_path_norm, lk.target
                    )
                    relations_out.append(
                        {
                            "kind": "collection",
                            "from": {"kind": "page", "locator": rel_path_norm},
                            "to": {"kind": kind_ep, "locator": to_loc},
                            "evidence_refs": [lk.id],
                        }
                    )
                elif not lk.is_in_collection and not lk.is_image:
                    kind_ep, to_loc = normalize_target_page_locator(
                        content_root, rel_path_norm, lk.target
                    )
                    relations_out.append(
                        {
                            "kind": "reference",
                            "from": {"kind": "page", "locator": rel_path_norm},
                            "to": {"kind": kind_ep, "locator": to_loc},
                            "evidence_refs": [lk.id],
                        }
                    )

            for src in parsed_md.sources:
                if not src.locator or src.recognition == "unclassified":
                    continue
                kind_ep, to_loc = normalize_target_page_locator(
                    content_root, rel_path_norm, src.locator
                )
                if not to_loc:
                    continue
                relations_out.append(
                    {
                        "kind": "provenance",
                        "from": {"kind": "page", "locator": rel_path_norm},
                        "to": {"kind": kind_ep, "locator": to_loc},
                        "evidence_refs": [src.id],
                    }
                )

            # 2. Inbound relations from other pages to current page
            all_content_files = get_all_content_markdown_files(content_root)
            for other_file in all_content_files:
                if other_file == rel_path_norm:
                    continue
                other_page, other_md, other_diags = load_page(
                    root_canon, content_root, other_file
                )
                if other_diags:
                    diags.extend(other_diags)
                    has_scan_errors = True
                if not other_page or not other_md:
                    has_scan_errors = True
                    continue
                for other_lk in other_md.link_occurrences:
                    if other_lk.is_in_collection and other_lk.is_direct_collection:
                        _, other_to = normalize_target_page_locator(
                            content_root, other_file, other_lk.target
                        )
                        if other_to == rel_path_norm:
                            relations_out.append(
                                {
                                    "kind": "collection",
                                    "from": {"kind": "page", "locator": other_file},
                                    "to": {"kind": "page", "locator": rel_path_norm},
                                    "evidence_refs": [other_lk.id],
                                }
                            )
                    elif not other_lk.is_in_collection and not other_lk.is_image:
                        _, other_to = normalize_target_page_locator(
                            content_root, other_file, other_lk.target
                        )
                        if other_to == rel_path_norm:
                            relations_out.append(
                                {
                                    "kind": "reference",
                                    "from": {"kind": "page", "locator": other_file},
                                    "to": {"kind": "page", "locator": rel_path_norm},
                                    "evidence_refs": [other_lk.id],
                                }
                            )
                for other_src in other_md.sources:
                    if not other_src.locator or other_src.recognition == "unclassified":
                        continue
                    other_kind, other_to = normalize_target_page_locator(
                        content_root, other_file, other_src.locator
                    )
                    if other_kind == "page" and other_to == rel_path_norm:
                        relations_out.append(
                            {
                                "kind": "provenance",
                                "from": {"kind": "page", "locator": other_file},
                                "to": {"kind": "page", "locator": rel_path_norm},
                                "evidence_refs": [other_src.id],
                            }
                        )

            relations_out.sort(
                key=lambda r: (
                    r["kind"],
                    r["from"]["locator"],
                    r["to"]["locator"],
                    r["evidence_refs"],
                )
            )

        sources_out = None
        if "sources" in inc:
            sources_out = [s.to_dict() for s in parsed_md.sources]

        exit_code = 2 if (has_scan_errors if "relations" in inc else False) else 0
        status_str = "partial" if (has_scan_errors if "relations" in inc else False) else "ok"

        return exit_code, Envelope(
            command="inspect",
            status=status_str,
            root=root_canon,
            data={
                "page": page.to_summary_dict(),
                "sections": sections_out,
                "relations": relations_out,
                "sources": sources_out,
            },
            diagnostics=diags,
        )

    # List pages
    if limit <= 0 or limit > 200:
        return 4, Envelope(
            command="inspect",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=str(limit),
                    message="limit must be between 1 and 200.",
                )
            ],
        )
    if offset < 0:
        return 4, Envelope(
            command="inspect",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=str(offset),
                    message="offset must be non-negative.",
                )
            ],
        )

    scope_clean: str | None = None
    if scope:
        if not is_explicit_relative_path(scope):
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file=scope,
                        span=None,
                        target=scope,
                        message=f"Scope '{scope}' is absolute or not a valid relative path.",
                    )
                ],
            )
        scope_canon, s_err = resolve_contained_path(content_root, scope)
        if s_err or not scope_canon or not os.path.exists(scope_canon):
            return 4, Envelope(
                command="inspect",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file=scope,
                        span=None,
                        target=scope,
                        message=f"Scope '{scope}' does not exist inside content root or escapes.",
                    )
                ],
            )
        scope_clean = get_normalized_relative_path(content_root, scope_canon)

    all_files = get_all_content_markdown_files(content_root)
    filtered_pages: list[Page] = []
    diagnostics: list[Diagnostic] = []
    has_partial = False

    for f_rel in all_files:
        if not include_archive and f_rel.startswith("archive/"):
            continue
        if scope_clean:
            if not (f_rel == scope_clean or f_rel.startswith(scope_clean + "/")):
                continue

        p, _, p_diags = load_page(root_canon, content_root, f_rel)
        if p_diags:
            diagnostics.extend(p_diags)
            has_partial = True
            continue
        if p is None:
            continue

        if page_type and p.type != page_type:
            continue
        if status and p.status != status:
            continue

        filtered_pages.append(p)

    # Sort pages stably by path
    filtered_pages.sort(key=lambda p: p.path)

    # Compute deterministic view_id
    view_hasher = hashlib.sha256()
    view_meta = {
        "scope": scope_clean,
        "type": page_type,
        "status": status,
        "include_archive": include_archive,
        "files": [(p.path, p.content_hash) for p in filtered_pages],
    }
    view_hasher.update(json.dumps(view_meta, sort_keys=True).encode("utf-8"))
    view_id = view_hasher.hexdigest()

    if expect_view is not None and expect_view != view_id:
        return 3, Envelope(
            command="inspect",
            status="stale",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="VIEW_CHANGED",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message="View changed; retrieve the page list again before paginating.",
                )
            ],
        )

    total = len(filtered_pages)
    sliced = filtered_pages[offset : offset + limit]
    has_more = (offset + limit) < total

    items = [p.to_summary_dict() for p in sliced]

    return (2 if has_partial else 0), Envelope(
        command="inspect",
        status="partial" if has_partial else "ok",
        root=root_canon,
        data={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "view_id": view_id,
        },
        diagnostics=diagnostics,
    )


def search_command(
    root: str,
    queries: list[str],
    match_mode: str = "any",  # 'any' | 'all'
    scope: str | None = None,
    page_type: str | None = None,
    status: str | None = None,
    include_archive: bool = False,
    limit: int = 10,
    offset: int = 0,
    hits_per_page: int = 2,
    snippet_chars: int = 240,
    expect_view: str | None = None,
) -> tuple[int, Envelope]:
    root_canon = get_canonical_path(root) if os.path.exists(root) else root

    if page_type is not None and page_type not in VALID_PAGE_TYPES:
        return 4, Envelope(
            command="search",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target="--type",
                    message=f"Invalid page type '{page_type}'. Expected one of: {', '.join(sorted(VALID_PAGE_TYPES))}.",
                )
            ],
        )

    if status is not None and status not in VALID_PAGE_STATUSES:
        return 4, Envelope(
            command="search",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target="--status",
                    message=f"Invalid status '{status}'. Expected one of: {', '.join(sorted(VALID_PAGE_STATUSES))}.",
                )
            ],
        )

    manifest, m_diags, m_code, m_status = load_manifest(root_canon)
    if m_diags:
        return m_code, Envelope(
            command="search",
            status=m_status,
            root=root_canon,
            data=None,
            diagnostics=m_diags,
        )

    content_dir = manifest.get("content_dir", "content")
    content_root = get_canonical_path(content_dir, root_canon)

    if limit <= 0 or limit > 200:
        return 4, Envelope(
            command="search",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=str(limit),
                    message="limit must be between 1 and 200.",
                )
            ],
        )
    if offset < 0:
        return 4, Envelope(
            command="search",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=str(offset),
                    message="offset must be non-negative.",
                )
            ],
        )

    clean_queries = [q.strip() for q in queries if q.strip()]
    if not clean_queries:
        return 4, Envelope(
            command="search",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message="At least one non-empty query must be provided.",
                )
            ],
        )

    scope_clean: str | None = None
    if scope:
        if not is_explicit_relative_path(scope):
            return 4, Envelope(
                command="search",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file=scope,
                        span=None,
                        target=scope,
                        message=f"Scope '{scope}' is absolute or not a valid relative path.",
                    )
                ],
            )
        scope_canon, s_err = resolve_contained_path(content_root, scope)
        if s_err or not scope_canon or not os.path.exists(scope_canon):
            return 4, Envelope(
                command="search",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="PATH_OUTSIDE_SCOPE",
                        severity="error",
                        file=scope,
                        span=None,
                        target=scope,
                        message=f"Scope '{scope}' does not exist inside content root or escapes.",
                    )
                ],
            )
        scope_clean = get_normalized_relative_path(content_root, scope_canon)

    all_files = get_all_content_markdown_files(content_root)
    matched_results: list[dict[str, Any]] = []
    diagnostics: list[Diagnostic] = []
    has_partial = False

    for f_rel in all_files:
        if not include_archive and f_rel.startswith("archive/"):
            continue
        if scope_clean:
            if not (f_rel == scope_clean or f_rel.startswith(scope_clean + "/")):
                continue

        p, parsed_md, p_diags = load_page(root_canon, content_root, f_rel)
        if p_diags:
            diagnostics.extend(p_diags)
            has_partial = True
            continue
        if p is None or parsed_md is None:
            continue

        if page_type and p.type != page_type:
            continue
        if status and p.status != status:
            continue

        # Check queries against page
        # Map fields: id, title, tags, source_fields, path, body
        matched_queries: set[str] = set()
        matched_fields: set[str] = set()
        page_hits: list[dict[str, Any]] = []

        # Helper to find section for a line number
        def find_section(line_no: int) -> tuple[str | None, list[str]]:
            best_sec = None
            for sec in parsed_md.sections:
                if sec.span["start_line"] <= line_no <= sec.span["end_line"]:
                    if best_sec is None or sec.level >= best_sec.level:
                        best_sec = sec
            if best_sec is not None:
                return best_sec.key, best_sec.heading_path
            return None, []

        for q in clean_queries:
            q_cf = q.casefold()

            # ID match
            if p.entry_id and q_cf in p.entry_id.casefold():
                matched_queries.add(q)
                matched_fields.add("id")

            # Title match
            if p.title and q_cf in p.title.casefold():
                matched_queries.add(q)
                matched_fields.add("title")

            # Tags match
            if any(q_cf in t.casefold() for t in p.tags):
                matched_queries.add(q)
                matched_fields.add("tags")

            # Path match
            if q_cf in p.path.casefold():
                matched_queries.add(q)
                matched_fields.add("path")

            # Source locators match
            for s in p.source_locators:
                for val in s.values():
                    if isinstance(val, str) and q_cf in val.casefold():
                        matched_queries.add(q)
                        matched_fields.add("source_fields")
                        break

            # Body match
            lines = parsed_md.lines
            for line_idx, line_str in enumerate(lines):
                line_no = line_idx + 1
                if q_cf in line_str.casefold():
                    matched_queries.add(q)
                    matched_fields.add("body")

                    # Extract snippet
                    cf_line = line_str.casefold()
                    pos = cf_line.find(q_cf)
                    start_char = max(0, pos - snippet_chars // 2)
                    end_char = min(len(line_str), start_char + snippet_chars)
                    snippet_text = line_str[start_char:end_char].strip()
                    is_snippet_trunc = (len(line_str) > len(snippet_text))

                    sec_key, h_path = find_section(line_no)
                    page_hits.append(
                        {
                            "query": q,
                            "field": "body",
                            "snippet": snippet_text,
                            "span": {
                                "start_line": line_no,
                                "end_line": line_no,
                                "precision": "line",
                            },
                            "section_key": sec_key,
                            "heading_path": h_path,
                            "truncated": is_snippet_trunc,
                        }
                    )

        # Evaluate match mode
        if match_mode == "all":
            if len(matched_queries) < len(clean_queries):
                continue
        else:
            if not matched_queries:
                continue

        # Sort and cap hits
        hits_truncated = len(page_hits) > hits_per_page
        capped_hits = page_hits[:hits_per_page]

        # Sorting keys:
        # 1. Exact match on id or title
        is_exact_id_or_title = any(
            (p.entry_id and q.casefold() == p.entry_id.casefold())
            or (p.title and q.casefold() == p.title.casefold())
            for q in clean_queries
        )
        # 2. Match count (negative for descending)
        match_count = len(matched_queries)
        # 3. Best matched field rank
        field_ranks = {"id": 0, "title": 0, "tags": 1, "source_fields": 2, "path": 2, "body": 3}
        best_field_rank = min((field_ranks.get(f, 4) for f in matched_fields), default=4)

        matched_results.append(
            {
                "page": p,
                "matched_queries": sorted(matched_queries),
                "matched_fields": sorted(matched_fields),
                "hits": capped_hits,
                "hits_truncated": hits_truncated,
                "_sort_key": (
                    0 if is_exact_id_or_title else 1,
                    -match_count,
                    best_field_rank,
                    p.path,
                ),
            }
        )

    # Sort results
    matched_results.sort(key=lambda r: r["_sort_key"])

    # Compute view_id
    view_hasher = hashlib.sha256()
    view_meta = {
        "queries": clean_queries,
        "match": match_mode,
        "scope": scope_clean,
        "type": page_type,
        "status": status,
        "include_archive": include_archive,
        "files": [(r["page"].path, r["page"].content_hash) for r in matched_results],
    }
    view_hasher.update(json.dumps(view_meta, sort_keys=True).encode("utf-8"))
    view_id = view_hasher.hexdigest()

    if expect_view is not None and expect_view != view_id:
        return 3, Envelope(
            command="search",
            status="stale",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="VIEW_CHANGED",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message="View changed; execute search again before paginating.",
                )
            ],
        )

    total = len(matched_results)
    sliced = matched_results[offset : offset + limit]
    has_more = (offset + limit) < total

    items = []
    for r in sliced:
        items.append(
            {
                "page": r["page"].to_summary_dict(),
                "matched_queries": r["matched_queries"],
                "matched_fields": r["matched_fields"],
                "hits": r["hits"],
                "hits_truncated": r["hits_truncated"],
            }
        )

    return (2 if has_partial else 0), Envelope(
        command="search",
        status="partial" if has_partial else "ok",
        root=root_canon,
        data={
            "items": items,
            "total": total,
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "view_id": view_id,
        },
        diagnostics=diagnostics,
    )


def read_command(
    root: str,
    path: str,
    section_key: str | None = None,
    lines_range: str | None = None,
    expect_hash: str | None = None,
    max_chars: int = 8000,
    offset: int = 0,
) -> tuple[int, Envelope]:
    root_canon = get_canonical_path(root)
    manifest, m_diags, m_code, m_status = load_manifest(root_canon)
    if m_diags:
        return m_code, Envelope(
            command="read",
            status=m_status,
            root=root_canon,
            data=None,
            diagnostics=m_diags,
        )

    content_dir = manifest.get("content_dir", "content")
    content_root = get_canonical_path(content_dir, root_canon)

    if not is_explicit_relative_path(path):
        return 4, Envelope(
            command="read",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="PATH_OUTSIDE_SCOPE",
                    severity="error",
                    file=path,
                    span=None,
                    target=path,
                    message=f"Path '{path}' is absolute or not a valid relative path.",
                )
            ],
        )

    rel_path = path.replace("\\", "/")
    page, parsed_md, diags = load_page(root_canon, content_root, rel_path)
    if page is None:
        code = 4 if any(d.code == "PATH_OUTSIDE_SCOPE" for d in diags) else 3
        st = "invalid" if code == 4 else "not_found"
        return code, Envelope(
            command="read",
            status=st,
            root=root_canon,
            data=None,
            diagnostics=diags,
        )

    # Validate expect_hash if provided
    if expect_hash is not None and expect_hash != page.content_hash:
        return 3, Envelope(
            command="read",
            status="stale",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="CONTENT_CHANGED",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=None,
                    message="Content changed; inspect the page again before reading by position.",
                )
            ],
        )

    # Enforce expect_hash when required
    positional_read = (section_key is not None) or (lines_range is not None) or (offset > 0)
    if positional_read and expect_hash is None:
        return 4, Envelope(
            command="read",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=None,
                    message="expect_hash is required when reading by section, lines, or with offset > 0.",
                )
            ],
        )

    full_text = page.raw_text
    page_lines = parsed_md.lines
    total_page_chars = len(full_text)

    # Determine requested range in full page coordinates
    req_start_char = 0
    req_end_char = total_page_chars
    req_start_line = 1
    req_end_line = len(page_lines)

    if section_key is not None and lines_range is not None:
        return 4, Envelope(
            command="read",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=None,
                    message="--section and --lines are mutually exclusive.",
                )
            ],
        )

    if section_key is not None:
        target_sec = next((s for s in parsed_md.sections if s.key == section_key), None)
        if target_sec is None:
            return 4, Envelope(
                command="read",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=rel_path,
                        span=None,
                        target=section_key,
                        message=f"Section '{section_key}' not found in page.",
                    )
                ],
            )
        req_start_line = target_sec.span["start_line"]
        req_end_line = target_sec.span["end_line"]

        # Calculate char offsets
        req_start_char = sum(len(page_lines[l]) for l in range(req_start_line - 1))
        req_end_char = sum(len(page_lines[l]) for l in range(req_end_line))

    elif lines_range is not None:
        m = re.match(r"^(\d+):(\d+)$", lines_range.strip())
        if not m:
            return 4, Envelope(
                command="read",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=rel_path,
                        span=None,
                        target=lines_range,
                        message="--lines must match 'start:end' with 1-based line numbers.",
                    )
                ],
            )
        l_start = int(m.group(1))
        l_end = int(m.group(2))
        if l_start < 1 or l_end > len(page_lines) or l_start > l_end:
            return 4, Envelope(
                command="read",
                status="invalid",
                root=root_canon,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=rel_path,
                        span=None,
                        target=lines_range,
                        message=f"Line range {l_start}:{l_end} is out of bounds (1..{len(page_lines)}).",
                    )
                ],
            )
        req_start_line = l_start
        req_end_line = l_end
        req_start_char = sum(len(page_lines[l]) for l in range(req_start_line - 1))
        req_end_char = sum(len(page_lines[l]) for l in range(req_end_line))

    selected_text = full_text[req_start_char:req_end_char]
    sel_len = len(selected_text)

    if offset < 0 or offset > sel_len:
        return 4, Envelope(
            command="read",
            status="invalid",
            root=root_canon,
            data=None,
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=rel_path,
                    span=None,
                    target=str(offset),
                    message=f"Offset {offset} is out of bounds for selected range of length {sel_len}.",
                )
            ],
        )

    chunk = selected_text[offset : offset + max_chars]
    ret_start_char = req_start_char + offset
    ret_end_char = ret_start_char + len(chunk)
    truncated = (offset + len(chunk)) < sel_len
    next_offset = (offset + len(chunk)) if truncated else None

    # Determine returned line range
    # Find start and end line for ret_start_char and ret_end_char
    curr_char = 0
    ret_start_line = 1
    ret_end_line = 1
    for idx, l_text in enumerate(page_lines):
        line_no = idx + 1
        line_end_char = curr_char + len(l_text)
        if curr_char <= ret_start_char < line_end_char or (ret_start_char == line_end_char and idx == len(page_lines) - 1):
            ret_start_line = line_no
        if curr_char < ret_end_char <= line_end_char or (ret_end_char == curr_char and line_no == ret_start_line):
            ret_end_line = line_no
        curr_char = line_end_char

    source_refs = [
        {
            "id": s.id,
            "span": s.span,
            "recognition": s.recognition,
        }
        for s in parsed_md.sources
    ]

    is_archived = rel_path.startswith("archive/")

    return 0, Envelope(
        command="read",
        status="ok",
        root=root_canon,
        data={
            "path": rel_path,
            "status": page.status or "draft",
            "archived": is_archived,
            "content_hash": page.content_hash,
            "text": chunk,
            "requested_range": {
                "start_char": req_start_char,
                "end_char": req_end_char,
                "start_line": req_start_line,
                "end_line": req_end_line,
            },
            "returned_range": {
                "start_char": ret_start_char,
                "end_char": ret_end_char,
                "start_line": ret_start_line,
                "end_line": ret_end_line,
            },
            "truncated": truncated,
            "next_offset": next_offset,
            "source_refs": source_refs,
        },
        diagnostics=[],
    )
