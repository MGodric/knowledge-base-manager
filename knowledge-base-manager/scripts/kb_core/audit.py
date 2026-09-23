"""Implementation of knowledge base audit command (legacy and write profiles)."""

from __future__ import annotations

import collections
import html
import os
import re
import urllib.parse
from pathlib import Path
from typing import Any

from .markdown_reader import parse_markdown_page
from .model import Diagnostic, Envelope, Issue
from .paths import (
    assert_no_redirecting_reparse_point,
    get_canonical_path,
    get_normalized_relative_path,
    split_and_decode_target_path,
    test_path_inside_root,
)
from .yaml_reader import parse_yaml_text


def is_valid_iso_date(value: str) -> bool:
    if not isinstance(value, str):
        return False
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", value.strip())
    if not m:
        return False
    year, month, day = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if month < 1 or month > 12 or day < 1 or day > 31:
        return False
    # Basic day count validation
    if month in (4, 6, 9, 11) and day > 30:
        return False
    if month == 2:
        is_leap = (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0))
        if day > (29 if is_leap else 28):
            return False
    return True


def audit_command(
    root: str,
    profile: str = "legacy",
    changed: list[str] | None = None,
) -> tuple[int, Envelope]:
    changed_list = changed or []
    root_canon = get_canonical_path(root)

    issues: list[Issue] = []
    fatal_failure = False

    def add_issue(
        severity: str,
        code: str,
        file: str,
        message: str,
        target: str = "",
        origin: str = "legacy",
        span: dict[str, Any] | None = None,
    ) -> None:
        in_ch = (file in changed_list) if changed_list else False
        issues.append(
            Issue(
                code=code,
                severity=severity,
                file=file,
                span=span,
                target=target,
                message=message,
                origin=origin,
                in_changed=in_ch,
            )
        )

    # 1. Root existence and reparse point
    if not os.path.isdir(root_canon):
        add_issue(
            severity="error",
            code="ROOT_NOT_FOUND",
            file="",
            message="The knowledge-base root does not exist or is not a directory.",
            target=root,
            origin="legacy",
        )
        return 3, Envelope(
            command="audit",
            status="failed",
            root=root_canon,
            data={
                "root": root_canon,
                "errors": 1,
                "warnings": 0,
                "issues": [i.to_dict() for i in issues],
                "checked_scope": {"legacy": "full", "collection": "none", "changed": []},
                "completed": False,
            },
            diagnostics=[
                Diagnostic(
                    code="TARGET_NOT_FOUND",
                    severity="error",
                    file=None,
                    span=None,
                    target=root,
                    message="Root directory not found.",
                )
            ],
        )

    try:
        assert_no_redirecting_reparse_point(root_canon, "knowledge-base root")
    except Exception as exc:
        add_issue("error", "AUDIT_RUNTIME_FAILURE", "", str(exc), target=root_canon)
        return 3, Envelope(
            command="audit",
            status="failed",
            root=root_canon,
            data={
                "root": root_canon,
                "errors": 1,
                "warnings": 0,
                "issues": [i.to_dict() for i in issues],
                "checked_scope": {"legacy": "full", "collection": "none", "changed": []},
                "completed": False,
            },
            diagnostics=[
                Diagnostic(
                    code="PATH_REDIRECTED",
                    severity="error",
                    file=None,
                    span=None,
                    target=root_canon,
                    message=str(exc),
                )
            ],
        )

    manifest_path = os.path.join(root_canon, "kb.yaml")
    manifest_file = "kb.yaml"
    if not os.path.isfile(manifest_path):
        add_issue("error", "MANIFEST_NOT_FOUND", manifest_file, "The root must contain kb.yaml.")
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    try:
        assert_no_redirecting_reparse_point(manifest_path, "kb.yaml")
    except Exception as exc:
        add_issue("error", "AUDIT_RUNTIME_FAILURE", manifest_file, str(exc), target=manifest_path)
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    try:
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest_content = f.read()
        manifest, m_diags = parse_yaml_text(manifest_content, filename=manifest_file)
        for d in m_diags:
            add_issue("error", d.code, manifest_file, d.message)
    except Exception as exc:
        add_issue("error", "AUDIT_RUNTIME_FAILURE", manifest_file, str(exc))
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    for req_key in ("schema_version", "content_dir", "entrypoint"):
        if req_key not in manifest or not str(manifest[req_key]).strip():
            add_issue(
                "error",
                "MANIFEST_FIELD_MISSING",
                manifest_file,
                f"Required manifest field '{req_key}' is missing.",
            )

    if any(i.severity == "error" for i in issues):
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    if str(manifest.get("schema_version")) != "1":
        add_issue(
            "error",
            "SCHEMA_VERSION_UNSUPPORTED",
            manifest_file,
            f"Only schema_version 1 is supported; found '{manifest.get('schema_version')}'.",
        )
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    for field_name in ("content_dir", "entrypoint"):
        conf_path = str(manifest[field_name])
        if os.path.isabs(conf_path) or bool(re.match(r"^[A-Za-z]:[\\/]", conf_path)):
            add_issue(
                "error",
                "MANIFEST_PATH_ABSOLUTE",
                manifest_file,
                f"'{field_name}' must be relative to the knowledge-base root.",
                target=conf_path,
            )

    if any(i.severity == "error" for i in issues):
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    content_full = get_canonical_path(str(manifest["content_dir"]), root_canon)
    entrypoint_full = get_canonical_path(str(manifest["entrypoint"]), root_canon)
    external_full: str | None = None

    if "external_dir" in manifest and str(manifest["external_dir"]).strip():
        ext_conf = str(manifest["external_dir"])
        if os.path.isabs(ext_conf) or bool(re.match(r"^[A-Za-z]:[\\/]", ext_conf)):
            add_issue(
                "error",
                "EXTERNAL_DIR_ABSOLUTE",
                manifest_file,
                "external_dir must be relative to the knowledge-base root.",
                target=ext_conf,
            )
        else:
            external_full = get_canonical_path(ext_conf, root_canon)
            if not test_path_inside_root(external_full, root_canon):
                add_issue(
                    "error",
                    "EXTERNAL_DIR_ESCAPES_ROOT",
                    manifest_file,
                    "external_dir resolves outside the knowledge-base root.",
                    target=ext_conf,
                )
            elif not os.path.isdir(external_full):
                add_issue(
                    "error",
                    "EXTERNAL_DIR_NOT_FOUND",
                    manifest_file,
                    "The configured external_dir does not exist.",
                    target=ext_conf,
                )

    if not test_path_inside_root(content_full, root_canon):
        add_issue(
            "error",
            "CONTENT_DIR_ESCAPES_ROOT",
            manifest_file,
            "content_dir resolves outside the knowledge-base root.",
            target=str(manifest["content_dir"]),
        )
    if not test_path_inside_root(entrypoint_full, root_canon):
        add_issue(
            "error",
            "ENTRYPOINT_ESCAPES_ROOT",
            manifest_file,
            "entrypoint resolves outside the knowledge-base root.",
            target=str(manifest["entrypoint"]),
        )
    if not test_path_inside_root(entrypoint_full, content_full):
        add_issue(
            "error",
            "ENTRYPOINT_OUTSIDE_CONTENT",
            manifest_file,
            "entrypoint must resolve inside content_dir.",
            target=str(manifest["entrypoint"]),
        )

    if any(i.severity == "error" for i in issues):
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    if not os.path.isdir(content_full):
        add_issue(
            "error",
            "CONTENT_DIR_NOT_FOUND",
            str(manifest["content_dir"]),
            "The configured content directory does not exist.",
        )
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    if not os.path.isfile(entrypoint_full):
        add_issue(
            "error",
            "ENTRYPOINT_NOT_FOUND",
            str(manifest["entrypoint"]),
            "The configured entrypoint does not exist.",
        )

    try:
        assert_no_redirecting_reparse_point(content_full, "content_dir")
        assert_no_redirecting_reparse_point(entrypoint_full, "entrypoint")
        if external_full and os.path.isdir(external_full):
            assert_no_redirecting_reparse_point(external_full, "external_dir")
    except Exception as exc:
        add_issue("error", "AUDIT_RUNTIME_FAILURE", "", str(exc))
        return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=False)

    # Validate changed files if in write profile
    if profile == "write":
        for ch in changed_list:
            ch_clean = ch.replace("\\", "/").strip().lstrip("/")
            ch_full = os.path.normpath(os.path.join(content_full, ch_clean.replace("/", os.sep)))
            if not os.path.isfile(ch_full) or not test_path_inside_root(ch_full, content_full):
                return 4, Envelope(
                    command="audit",
                    status="invalid",
                    root=root_canon,
                    data=None,
                    diagnostics=[
                        Diagnostic(
                            code="INVALID_ARGUMENT",
                            severity="error",
                            file=ch,
                            span=None,
                            target=ch,
                            message=f"Changed file does not exist in content directory: {ch}",
                        )
                    ],
                )

    # Collect content files
    content_files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(content_full):
        for d in dirnames:
            dp = os.path.join(dirpath, d)
            try:
                assert_no_redirecting_reparse_point(dp, "content directory")
            except Exception as exc:
                add_issue("error", "AUDIT_RUNTIME_FAILURE", get_normalized_relative_path(content_full, dp), str(exc))
        for f in filenames:
            fp = os.path.join(dirpath, f)
            try:
                assert_no_redirecting_reparse_point(fp, "content file")
            except Exception as exc:
                add_issue("error", "AUDIT_RUNTIME_FAILURE", get_normalized_relative_path(content_full, fp), str(exc))
            content_files.append(fp)

    # Check filename issues (sync conflict and temporary files)
    for fp in content_files:
        fn = os.path.basename(fp)
        rel = get_normalized_relative_path(content_full, fp)
        if re.search(r"(?i)(conflicted copy|sync-conflict|conflict copy|冲突副本|冲突的副本)", fn):
            add_issue("warning", "SYNC_CONFLICT_COPY", rel, "This filename looks like a synchronization conflict copy.")
        elif re.search(r"(?i)(\.tmp$|\.temp$|\.swp$|~$|^~\$)", fn):
            add_issue("warning", "TEMPORARY_FILE", rel, "Temporary files should not remain in the synchronized knowledge base.")

    # Parse all markdown files
    markdown_files = [fp for fp in content_files if fp.lower().endswith(".md")]
    parsed_pages: dict[str, tuple[str, Any]] = {}  # rel -> (full, parsed_page)
    inbound_count: dict[str, int] = {}
    ids: dict[str, list[str]] = collections.defaultdict(list)

    for full in markdown_files:
        rel = get_normalized_relative_path(content_full, full)
        inbound_count[rel] = 0
        try:
            with open(full, "rb") as f:
                raw_bytes = f.read()
            if raw_bytes.startswith(b"\xef\xbb\xbf"):
                text = raw_bytes[3:].decode("utf-8")
            else:
                text = raw_bytes.decode("utf-8")
        except Exception as exc:
            add_issue("error", "FILE_UNREADABLE", rel, str(exc))
            continue

        parsed_md, p_diags = parse_markdown_page(text, filename=rel)
        for d in p_diags:
            add_issue("error", d.code, rel, d.message)

        parsed_pages[rel] = (full, parsed_md)

        # H1 count check
        if parsed_md.h1_count != 1:
            add_issue(
                "error",
                "H1_COUNT_INVALID",
                rel,
                f"Expected exactly one level-one heading; found {parsed_md.h1_count}.",
            )

        # Math code span check
        for m_span in parsed_md.math_code_spans:
            add_issue(
                "error",
                "MATH_CODE_SPAN",
                rel,
                f"Inline code on line {m_span['line_number']} looks like a mathematical expression; write inline math as $...$ or display math as $$...$$. Use <!-- kb-literal-code --> on the same line only when literal code is intentional.",
                target=m_span["content"],
            )

        is_entrypoint = (full.lower() == entrypoint_full.lower())
        is_inbox = rel.lower().startswith("inbox/")
        is_archive = rel.lower().startswith("archive/")
        is_formal = not is_entrypoint and not is_inbox and not is_archive

        if is_formal:
            if not parsed_md.front_matter_present:
                add_issue("error", "FRONT_MATTER_MISSING", rel, "Formal entries require YAML front matter.")
                continue

            fm = parsed_md.front_matter_fields
            for req_field in ("id", "type", "status", "created", "updated"):
                if req_field not in fm or not str(fm[req_field]).strip():
                    add_issue("error", "ENTRY_FIELD_MISSING", rel, f"Required field '{req_field}' is missing.")

            if "id" in fm and fm["id"] is not None:
                id_str = str(fm["id"])
                if not re.match(r"^kb-\d{8}-[0-9a-fA-F]{4,}$", id_str):
                    add_issue(
                        "error",
                        "ID_FORMAT_INVALID",
                        rel,
                        f"ID '{id_str}' must match kb-YYYYMMDD-xxxx with a hexadecimal suffix.",
                    )
                ids[id_str].append(rel)

            if "type" in fm and fm["type"] is not None:
                t_str = str(fm["type"])
                if t_str not in ("concept", "method", "source", "decision", "project", "map"):
                    add_issue("error", "TYPE_INVALID", rel, f"Unknown type '{t_str}'.")

            if "status" in fm and fm["status"] is not None:
                s_str = str(fm["status"])
                if s_str not in ("draft", "stable", "deprecated"):
                    add_issue("error", "STATUS_INVALID", rel, f"Unknown status '{s_str}'.")

            for date_field in ("created", "updated"):
                if date_field in fm and fm[date_field] is not None:
                    d_val = str(fm[date_field])
                    if not is_valid_iso_date(d_val):
                        add_issue(
                            "error",
                            "DATE_INVALID",
                            rel,
                            f"Field '{date_field}' must use a valid YYYY-MM-DD date.",
                        )

    # Check duplicate IDs
    for id_val, rel_list in ids.items():
        if len(rel_list) > 1:
            for rel in rel_list:
                others = ", ".join(x for x in rel_list if x != rel)
                add_issue("error", "ID_DUPLICATE", rel, f"ID '{id_val}' is also used by: {others}.")

    # Resolve each allowed root once so case checks compare paths in the same
    # filesystem namespace, even when Windows canonicalizes an ancestor.
    resolved_link_roots: dict[str, str] = {}

    # Validate links in all parsed markdown files
    for rel, (page_full, parsed_md) in parsed_pages.items():
        source_is_current = not rel.lower().startswith("inbox/") and not rel.lower().startswith("archive/")

        for lk in parsed_md.links:
            raw_target = str(lk["target"]).strip()
            if not raw_target or raw_target.startswith("#"):
                continue

            is_portable_source = bool(re.search(r"(?i)<!--\s*kb-portable-source\s*-->", lk["line"]))

            if re.match(r"^[A-Za-z]:[\\/]", raw_target) or raw_target.startswith(r"\\"):
                if not lk["is_explicit_external_local"]:
                    add_issue(
                        "warning",
                        "ABSOLUTE_LOCAL_LINK",
                        rel,
                        "Local absolute links require an explicit outside-knowledge-base, machine-specific label.",
                        target=raw_target,
                    )
                    continue

                date_m = re.search(
                    r"(?i)(?:verified|last\s+verified|验证日期|已验证)\s*[:：]\s*(?P<date>\d{4}-\d{2}-\d{2})",
                    lk["line"],
                )
                ver_m = re.search(
                    r"(?i)(?:revision|version-state|版本状态|版本)\s*[:：]\s*(?P<val>[^;；,，]+)",
                    lk["line"],
                )

                if not date_m:
                    add_issue(
                        "warning",
                        "SOURCE_VERIFIED_DATE_MISSING",
                        rel,
                        f"The labeled external local source on line {lk['line_number']} requires verified: YYYY-MM-DD.",
                        target=raw_target,
                    )
                elif not is_valid_iso_date(date_m.group("date")):
                    add_issue(
                        "warning",
                        "SOURCE_VERIFIED_DATE_INVALID",
                        rel,
                        f"The labeled external local source on line {lk['line_number']} has an invalid verification date.",
                        target=raw_target,
                    )

                if not ver_m or not ver_m.group("val").strip():
                    add_issue(
                        "warning",
                        "SOURCE_VERSION_STATE_MISSING",
                        rel,
                        f"The labeled external local source on line {lk['line_number']} requires revision: <value> or version-state: <value>.",
                        target=raw_target,
                    )
                continue

            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", raw_target):
                continue

            if "\\" in raw_target:
                add_issue(
                    "warning",
                    "BACKSLASH_LINK",
                    rel,
                    "Use / separators in Markdown links.",
                    target=raw_target,
                )

            try:
                decoded_path_norm, query, fragment = split_and_decode_target_path(raw_target)
            except Exception:
                add_issue(
                    "error",
                    "LINK_ENCODING_INVALID",
                    rel,
                    "The link target contains invalid URL encoding.",
                    target=raw_target,
                )
                continue

            if not decoded_path_norm.strip():
                continue

            decoded_path = decoded_path_norm.replace("/", os.sep)
            if "....\\" in decoded_path:
                decoded_path = decoded_path.replace("....\\", "..\\..\\")
            if "..../" in decoded_path:
                decoded_path = decoded_path.replace("..../", "../../")

            if is_portable_source and not external_full:
                add_issue(
                    "error",
                    "PORTABLE_LINK_WITHOUT_EXTERNAL_DIR",
                    rel,
                    "A kb-portable-source link requires a valid external_dir in kb.yaml.",
                    target=raw_target,
                )
                continue

            is_root_relative = os.path.isabs(decoded_path) or decoded_path.startswith(("\\", "/"))
            if is_root_relative:
                add_issue(
                    "warning",
                    "ROOT_RELATIVE_LINK",
                    rel,
                    "Use a relative Markdown link instead of a root-relative path.",
                    target=raw_target,
                )
                decoded_clean = decoded_path.lstrip("\\/")
                root_for_rr = external_full if is_portable_source else content_full
                candidate_full = get_canonical_path(os.path.join(root_for_rr, decoded_clean))
            else:
                candidate_full = get_canonical_path(
                    os.path.join(os.path.dirname(page_full), decoded_path)
                )

            allowed_root = external_full if is_portable_source else content_full
            if not test_path_inside_root(candidate_full, allowed_root):
                code_str = (
                    "PORTABLE_LINK_ESCAPES_EXTERNAL" if is_portable_source else "LINK_ESCAPES_CONTENT"
                )
                msg_str = (
                    "Portable source links must remain inside external_dir."
                    if is_portable_source
                    else "Internal links must remain inside content_dir."
                )
                add_issue("error", code_str, rel, msg_str, target=raw_target)
                continue

            if not os.path.exists(candidate_full):
                add_issue(
                    "error",
                    "LINK_BROKEN",
                    rel,
                    "The internal link target does not exist.",
                    target=raw_target,
                )
                continue

            if os.path.isdir(candidate_full):
                dir_rel = get_normalized_relative_path(content_full, candidate_full).rstrip("/")
                is_homepage_browse = (
                    page_full.lower() == entrypoint_full.lower()
                    and lk["collection_well_formed"]
                    and not lk["is_in_collection"]
                    and not lk["is_image"]
                    and not is_portable_source
                    and not lk["is_explicit_external_local"]
                    and not is_root_relative
                    and not any(c in raw_target for c in "\\?#")
                    and "\\" not in decoded_path_norm
                    and dir_rel
                    in (
                        "projects",
                        "maps",
                        "knowledge",
                        "sources",
                        "decisions",
                        "inbox",
                        "archive",
                        "assets",
                    )
                )
                if not is_homepage_browse:
                    add_issue(
                        "warning",
                        "DIRECTORY_LINK",
                        rel,
                        "Link to a Markdown entry rather than a directory.",
                        target=raw_target,
                    )
                continue

            try:
                # Path(candidate_full).resolve() returns real casing on Windows
                actual_full = str(Path(candidate_full).resolve())
                if allowed_root not in resolved_link_roots:
                    resolved_link_roots[allowed_root] = str(Path(allowed_root).resolve())
                exp_rel = get_normalized_relative_path(allowed_root, candidate_full)
                act_rel = get_normalized_relative_path(
                    resolved_link_roots[allowed_root], actual_full
                )
                if exp_rel != act_rel:
                    add_issue(
                        "warning",
                        "LINK_CASE_MISMATCH",
                        rel,
                        "Link path casing differs from the stored target.",
                        target=raw_target,
                    )
            except Exception:
                pass

            act_rel_std = get_normalized_relative_path(content_full, candidate_full)
            if (
                candidate_full.lower().endswith(".md")
                and act_rel_std in inbound_count
                and source_is_current
            ):
                inbound_count[act_rel_std] += 1
                if act_rel_std.lower().startswith("archive/"):
                    add_issue(
                        "warning",
                        "CURRENT_LINKS_TO_ARCHIVE",
                        rel,
                        "Current content links to archived material; explain why the historical target is still relevant.",
                        target=raw_target,
                    )

    # Check orphan entries
    for rel, (page_full, parsed_md) in parsed_pages.items():
        is_entrypoint = (page_full.lower() == entrypoint_full.lower())
        excluded = (
            is_entrypoint
            or rel.lower().startswith("inbox/")
            or rel.lower().startswith("archive/")
        )
        if not excluded and inbound_count.get(rel, 0) == 0:
            add_issue("warning", "ORPHAN_ENTRY", rel, "No current entry or map links to this formal entry.")

    # ----------------------------------------------------
    # Profile write: Full Collection Graph Validation
    # ----------------------------------------------------
    if profile == "write":
        bad_collection_owners: set[str] = set()
        collection_edges: dict[str, list[str]] = collections.defaultdict(list)
        bad_owner_targets: set[str] = set()

        entrypoint_rel = get_normalized_relative_path(content_full, entrypoint_full)

        for rel, (page_full, parsed_md) in parsed_pages.items():
            # Check collection block syntax
            if not parsed_md.collection_well_formed:
                add_issue(
                    "error",
                    "COLLECTION_REGION_INVALID",
                    rel,
                    "Invalid kb-nav children block (duplicate, nested, or unmatched markers).",
                    origin="collection",
                )
                bad_collection_owners.add(rel)
                continue

            if parsed_md.collection_block is not None:
                page_type = parsed_md.front_matter_fields.get("type")
                is_entrypoint = (page_full.lower() == entrypoint_full.lower())

                if not is_entrypoint and page_type not in ("project", "map"):
                    add_issue(
                        "error",
                        "COLLECTION_OWNER_INVALID",
                        rel,
                        "kb-nav children block requires project/map type.",
                        origin="collection",
                    )
                    bad_collection_owners.add(rel)
                    continue

                # Extract top-level direct links inside collection block using unified AST model
                top_level_targets: list[tuple[str, str]] = [
                    (lk.target, lk.line)
                    for lk in parsed_md.link_occurrences
                    if lk.is_in_collection and lk.is_direct_collection
                ]

                seen_targets_for_page: set[str] = set()
                for raw_href, src_line in top_level_targets:
                    # Check query
                    if "?" in raw_href:
                        add_issue(
                            "error",
                            "COLLECTION_TARGET_INVALID",
                            rel,
                            f"query is unsupported in kb-nav link: {rel} -> {raw_href}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    decoded_href, _, _ = split_and_decode_target_path(raw_href)

                    if (
                        not decoded_href.strip()
                        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", decoded_href)
                        or decoded_href.startswith(("/", "\\"))
                        or os.path.isabs(decoded_href)
                    ):
                        add_issue(
                            "error",
                            "COLLECTION_TARGET_INVALID",
                            rel,
                            f"kb-nav link must target a relative local Markdown file: {rel} -> {raw_href}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    target_full = get_canonical_path(
                        os.path.join(os.path.dirname(page_full), decoded_href.replace("/", os.sep))
                    )
                    if not test_path_inside_root(target_full, content_full):
                        add_issue(
                            "error",
                            "COLLECTION_TARGET_INVALID",
                            rel,
                            f"kb-nav link escapes content root: {rel} -> {raw_href}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    target_rel = get_normalized_relative_path(content_full, target_full)
                    if target_rel not in parsed_pages:
                        add_issue(
                            "error",
                            "COLLECTION_TARGET_INVALID",
                            rel,
                            f"kb-nav target is not an existing Markdown file: {rel} -> {raw_href}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    if target_rel == rel:
                        add_issue(
                            "error",
                            "COLLECTION_SELF_LINK",
                            rel,
                            f"self collection in kb-nav: {rel}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    target_type = parsed_pages[target_rel][1].front_matter_fields.get("type")
                    if is_entrypoint and target_type not in ("project", "map"):
                        add_issue(
                            "error",
                            "COLLECTION_TARGET_INVALID",
                            rel,
                            f"entrypoint may collect only project/map pages: {target_rel}",
                            target=raw_href,
                            origin="collection",
                        )
                        continue

                    if target_rel not in seen_targets_for_page:
                        seen_targets_for_page.add(target_rel)
                        collection_edges[rel].append(target_rel)

        # Record bad owner targets for suppression of secondary errors
        for b_owner in bad_collection_owners:
            for lk in parsed_pages.get(b_owner, ("", None))[1].links:
                if lk["is_in_collection"]:
                    bad_owner_targets.add(lk["target"])

        # Check collection cycles using Kahn's algorithm
        in_degree: dict[str, int] = {r: 0 for r in parsed_pages}
        for parent, children in collection_edges.items():
            for ch in children:
                in_degree[ch] += 1

        queue = collections.deque([r for r, deg in in_degree.items() if deg == 0])
        visited_count = 0
        while queue:
            node = queue.popleft()
            visited_count += 1
            for ch in collection_edges.get(node, []):
                in_degree[ch] -= 1
                if in_degree[ch] == 0:
                    queue.append(ch)

        if visited_count != len(parsed_pages):
            # Nodes with in_degree > 0 are part of or descendants of a cycle
            cycle_nodes = [r for r, deg in in_degree.items() if deg > 0]
            for c_node in sorted(cycle_nodes):
                add_issue(
                    "error",
                    "COLLECTION_CYCLE",
                    c_node,
                    "cycle in kb-nav collections",
                    origin="collection",
                )

        # Check collection parents for formal entries
        parents_by_child: dict[str, list[str]] = collections.defaultdict(list)
        for parent, children in collection_edges.items():
            for ch in children:
                parents_by_child[ch].append(parent)

        for rel, (p_full, p_md) in parsed_pages.items():
            is_entry = (p_full.lower() == entrypoint_full.lower())
            is_inbox = rel.lower().startswith("inbox/")
            is_archive = rel.lower().startswith("archive/")
            is_formal = not is_entry and not is_inbox and not is_archive

            if is_formal:
                p_list = parents_by_child.get(rel, [])
                if len(p_list) == 0:
                    # Check if suppressed by bad owner
                    suppressed = (rel in bad_owner_targets or os.path.basename(rel) in bad_owner_targets)
                    if not suppressed:
                        add_issue(
                            "error",
                            "COLLECTION_PARENT_MISSING",
                            rel,
                            "Formal entry has no valid direct collection parent.",
                            origin="collection",
                        )

    return _build_audit_envelope(root_canon, issues, profile, changed_list, completed=True)


def _build_audit_envelope(
    root: str,
    issues: list[Issue],
    profile: str,
    changed: list[str],
    completed: bool,
) -> tuple[int, Envelope]:
    # Sort issues stably: severity ('error' rank 0, 'warning' rank 1), file, code, target
    severity_rank = {"error": 0, "warning": 1}
    issues.sort(
        key=lambda i: (
            severity_rank.get(i.severity, 2),
            i.file,
            i.code,
            i.target or "",
        )
    )

    error_count = sum(1 for i in issues if i.severity == "error")
    warning_count = sum(1 for i in issues if i.severity == "warning")

    checked_scope = {
        "legacy": "full",
        "collection": "full" if profile == "write" else "none",
        "changed": changed,
    }

    status = "ok" if error_count == 0 else "validation_failed"
    if not completed:
        status = "failed"
        exit_code = 3
    elif error_count > 0:
        exit_code = 2
    else:
        exit_code = 0

    envelope = Envelope(
        command="audit",
        status=status,
        root=root,
        data={
            "root": root,
            "errors": error_count,
            "warnings": warning_count,
            "issues": [i.to_dict() for i in issues],
            "checked_scope": checked_scope,
            "completed": completed,
        },
        diagnostics=[],
    )
    return exit_code, envelope
