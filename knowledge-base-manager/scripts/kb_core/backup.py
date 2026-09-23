"""Knowledge base backup, verification, and restore implementations."""

from __future__ import annotations

import collections
import ctypes
import datetime
import errno
import hashlib
import json
import os
import re
import shutil
import sys
import urllib.parse
import uuid
from typing import Any

from .audit import audit_command
from .markdown_reader import (
    _SOURCE_END_META,
    _SOURCE_START_META,
    _inline_projected_lines,
    _token_source_document_span,
    parse_markdown_page,
)
from .model import Diagnostic, Envelope
from .paths import (
    assert_no_redirecting_reparse_point,
    get_canonical_path,
    get_normalized_relative_path,
    get_safe_tree_files,
    split_and_decode_target_path,
    test_path_inside_root,
)


class ReconfirmException(Exception):
    """Raised when source snapshot changes and reconfirmation is required."""

    def __init__(self, plan: dict[str, Any] | None, change_summary: list[str]):
        super().__init__(
            "RECONFIRM: the source snapshot changed; obtain confirmation for the newly listed plan."
        )
        self.plan = plan
        self.change_summary = change_summary


def get_sha256(path: str) -> str:
    """Calculate lowercase SHA-256 hex string for a file."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def get_bytes_sha256(data: bytes) -> str:
    """Calculate lowercase SHA-256 hex string for raw bytes."""
    return hashlib.sha256(data).hexdigest().lower()


def get_file_mtime_utc(path: str) -> str:
    """Return ISO 8601 UTC timestamp with 7 fractional digits matching .NET 'o' format."""
    st = os.stat(path)
    ticks = (st.st_mtime_ns // 100) % 10_000_000
    dt_sec = datetime.datetime.fromtimestamp(
        st.st_mtime_ns // 1_000_000_000, tz=datetime.timezone.utc
    )
    return dt_sec.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ticks:07d}Z"


def get_canonical_existing_path(path: str) -> str:
    """Validate source file exists and return canonical path with no reparse points."""
    if not os.path.isfile(path):
        raise RuntimeError(f"BLOCKER: source file is missing: {path}")
    canonical = get_canonical_path(path)
    assert_no_redirecting_reparse_point(canonical, "source path")
    return canonical


def new_snapshot_record(
    kind: str,
    source_path: str,
    portable_path: str,
    project_id: str | None = None,
    project_relative_source: str | None = None,
) -> dict[str, Any]:
    """Create a snapshot record for a file."""
    canonical = get_canonical_existing_path(source_path)
    st = os.stat(canonical)
    record: dict[str, Any] = {
        "kind": kind,
        "source_path": canonical,
        "portable_path": portable_path.replace("\\", "/"),
        "size_bytes": st.st_size,
        "mtime_utc": get_file_mtime_utc(canonical),
        "sha256": get_sha256(canonical),
    }
    if kind == "external":
        record["project_id"] = project_id or ""
        record["project_relative_source"] = (project_relative_source or "").replace("\\", "/")
    return record


def test_snapshot_record(record: dict[str, Any]) -> bool:
    """Test if the file on disk matches its recorded snapshot."""
    try:
        actual = new_snapshot_record(
            kind=record["kind"],
            source_path=record["source_path"],
            portable_path=record["portable_path"],
            project_id=record.get("project_id"),
            project_relative_source=record.get("project_relative_source"),
        )
    except Exception:
        return False

    for field in (
        "kind",
        "source_path",
        "portable_path",
        "size_bytes",
        "mtime_utc",
        "sha256",
        "project_id",
        "project_relative_source",
    ):
        if field in record or field in actual:
            if str(record.get(field, "")) != str(actual.get(field, "")):
                return False
    return True


def get_plan_digest(plan_without_digest: dict[str, Any]) -> str:
    """Compute a plan-v2 digest from canonical UTF-8 JSON."""
    if plan_without_digest.get("plan_schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError(
            f"unsupported backup plan schema version: {plan_without_digest.get('plan_schema_version')!r}"
        )
    json_bytes = json.dumps(
        plan_without_digest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(json_bytes).hexdigest().lower()


def read_manifest(root: str) -> dict[str, Any]:
    """Read and validate kb.yaml manifest."""
    assert_no_redirecting_reparse_point(root, "knowledge-base root")
    path = os.path.join(root, "kb.yaml")
    if not os.path.isfile(path):
        raise RuntimeError(f"BLOCKER: kb.yaml is missing: {path}")
    assert_no_redirecting_reparse_point(path, "kb.yaml")

    values: dict[str, str] = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            m = re.match(r"^\s*([A-Za-z_][A-Za-z0-9_-]*)\s*:\s*(.*?)\s*$", line)
            if m:
                val = m.group(2).strip().strip('"').strip("'")
                values[m.group(1)] = val

    for key in ("schema_version", "content_dir", "entrypoint"):
        if key not in values or not values[key].strip():
            raise RuntimeError(f"BLOCKER: kb.yaml requires {key}")

    if values["schema_version"] != "1":
        raise RuntimeError("BLOCKER: only schema_version 1 is supported")

    content_val = values["content_dir"]
    content = get_canonical_path(os.path.join(root, content_val))
    if (
        os.path.isabs(content_val)
        or re.match(r"^[A-Za-z]:", content_val)
        or content_val.startswith(("/", "\\"))
        or not test_path_inside_root(content, root)
    ):
        raise RuntimeError("BLOCKER: content_dir escapes knowledge-base root")

    if not os.path.isdir(content):
        raise RuntimeError(f"BLOCKER: content_dir is missing: {content}")
    assert_no_redirecting_reparse_point(content, "content_dir")

    return {"values": values, "content": content, "manifest_path": path}


def is_absolute_local_path(target: str) -> bool:
    """Check if target string represents an absolute local filesystem path."""
    if not target or not target.strip():
        return False
    t = target.strip()
    # Windows drive letter absolute path: C:\... or C:/...
    if re.match(r"^[A-Za-z]:[\\/]", t):
        return True
    # UNC path: \\server\share or //server/share
    if t.startswith(("\\\\", "//")):
        return True
    # URI schemes like http://, https://, ftp://, mailto:, urn:
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", t) or re.match(r"^(mailto|tel|urn):", t, re.I):
        return False
    # POSIX absolute path: starts with /
    if t.startswith("/"):
        return True
    return False


def path_equals(p1: str, p2: str) -> bool:
    """Compare two filesystem paths for equality, honoring platform case sensitivity."""
    if os.name == "nt":
        return p1.lower() == p2.lower()
    return p1 == p2


def path_ends_with(path: str, suffix: str) -> bool:
    """Check if path ends with suffix, honoring platform case sensitivity."""
    if os.name == "nt":
        return path.lower().endswith(suffix.lower())
    return path.endswith(suffix)


PLAN_SCHEMA_VERSION = 2


def unicode_ordinal_key(value: str) -> tuple[int, ...]:
    """Return the explicit, locale-independent ordering key used by plan v2."""
    return tuple(ord(char) for char in value)


def _linux_rename_noreplace(src: str, dst: str) -> bool:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    RENAME_NOREPLACE = 1
    AT_FDCWD = -100
    if hasattr(libc, "renameat2"):
        ret = libc.renameat2(
            AT_FDCWD,
            src.encode("utf-8"),
            AT_FDCWD,
            dst.encode("utf-8"),
            RENAME_NOREPLACE,
        )
        if ret != 0:
            err = ctypes.get_errno()
            if err in (errno.EEXIST, errno.ENOTEMPTY):
                raise FileExistsError(f"Destination already exists: {dst}")
            raise OSError(err, os.strerror(err), dst)
        return True
    return False


def _darwin_rename_excl(src: str, dst: str) -> bool:
    libc = ctypes.CDLL("libSystem.B.dylib", use_errno=True)
    RENAME_EXCL = 0x00000004
    AT_FDCWD = -2
    if hasattr(libc, "renameatx_np"):
        ret = libc.renameatx_np(
            AT_FDCWD,
            src.encode("utf-8"),
            AT_FDCWD,
            dst.encode("utf-8"),
            RENAME_EXCL,
        )
        if ret != 0:
            err = ctypes.get_errno()
            if err in (errno.EEXIST, errno.ENOTEMPTY):
                raise FileExistsError(f"Destination already exists: {dst}")
            raise OSError(err, os.strerror(err), dst)
        return True
    return False


def publish_dir_fail_if_exists(src: str, dst: str) -> None:
    """Atomically move directory src to dst, refusing to overwrite dst if it exists."""
    if os.path.exists(dst) or os.path.islink(dst):
        raise FileExistsError(f"Destination already exists: {dst}")

    if os.name == "nt":
        # Win32 MoveFile / os.rename raises FileExistsError if dst exists.
        os.rename(src, dst)
        return

    if sys.platform.startswith("linux"):
        if _linux_rename_noreplace(src, dst):
            return
        raise RuntimeError("FATAL: Linux renameat2(RENAME_NOREPLACE) is unavailable; refusing non-atomic publish")

    if sys.platform == "darwin":
        if _darwin_rename_excl(src, dst):
            return
        raise RuntimeError("FATAL: macOS renameatx_np(RENAME_EXCL) is unavailable; refusing non-atomic publish")

    raise RuntimeError("FATAL: no verified atomic fail-if-exists directory publish primitive for this platform")


def get_links_in_line(line: str) -> list[dict[str, Any]]:
    """Extract parser-compatible inline link targets and their spans in a line."""
    links: list[dict[str, Any]] = []
    cursor = 0
    while cursor < len(line):
        label_open = line.find("[", cursor)
        if label_open < 0:
            break
        if label_open > 0 and line[label_open - 1] == "\\":
            cursor = label_open + 1
            continue
        label_close = label_open + 1
        escaped = False
        while label_close < len(line):
            char = line[label_close]
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == "]":
                break
            label_close += 1
        if label_close + 1 >= len(line) or line[label_close + 1] != "(":
            cursor = label_open + 1
            continue
        target_start = label_close + 2
        if target_start < len(line) and line[target_start] == "<":
            target_end = line.find(">", target_start + 1)
            close = target_end + 1 if target_end >= 0 and target_end + 1 < len(line) and line[target_end + 1] == ")" else -1
            target = line[target_start + 1 : target_end] if target_end >= 0 else ""
        else:
            depth = 0
            escaped = False
            close = -1
            for index in range(target_start, len(line)):
                char = line[index]
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == "(":
                    depth += 1
                elif char == ")":
                    if depth == 0:
                        close = index
                        break
                    depth -= 1
            target = line[target_start:close].strip() if close >= 0 else ""
        if close < 0:
            cursor = label_open + 1
            continue
        links.append({"target": target, "start": label_open, "length": close - label_open + 1})
        cursor = close + 1
    return links


def get_markdown_link_target_span(syntax: str) -> tuple[int, int] | None:
    """Return the target span inside one parser-confirmed Markdown link syntax.

    This operates only on the source interval supplied by markdown-it.  It is
    deliberately not a document-wide link regex: an escaped or parenthesized
    target must retain the exact source location that the parser accepted.
    """
    close_label = -1
    escaped = False
    for index, char in enumerate(syntax):
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "]" and index + 1 < len(syntax) and syntax[index + 1] == "(":
            close_label = index
            break
    if close_label < 0:
        return None
    start = close_label + 2
    if start >= len(syntax):
        return None
    if syntax[start] == "<":
        end = syntax.find(">", start + 1)
        return (start, end + 1) if end > start + 1 else None

    depth = 0
    escaped = False
    for index in range(start, len(syntax)):
        char = syntax[index]
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if char == "(":
            depth += 1
            continue
        if char == ")":
            if depth == 0:
                return (start, index)
            depth -= 1
    return None


def get_field(line: str, name: str) -> str | None:
    """Extract a metadata field value from a line or projected line."""
    m = re.search(rf"(?i){re.escape(name)}\s*[:：]\s*[`'\"]?([^;；,，`'\"]+)[`'\"]?", line)
    if not m:
        return None
    return m.group(1).strip().strip("`")


def test_safe_relative_source_path(path: str | None) -> bool:
    """Check if relative source path contains no traversal or root escape."""
    if not path or not path.strip():
        return False
    if os.path.isabs(path) or re.match(r"^[A-Za-z]:", path) or path.startswith(("/", "\\")):
        return False
    parts = path.replace("\\", "/").split("/")
    return not any(p in ("", ".", "..") for p in parts)


def test_safe_portable_path(path: str | None) -> bool:
    """Check if portable path contains no traversal or root escape."""
    return test_safe_relative_source_path(path)


def get_ignore_map(ignore_legacy_path: list[str]) -> dict[str, str]:
    """Parse ignore_legacy_path arguments into a canonical path -> reason map."""
    map_res: dict[str, str] = {}
    for item in ignore_legacy_path:
        split = item.split("|", 1)
        if len(split) != 2 or not split[1].strip():
            raise RuntimeError(f"BLOCKER: IgnoreLegacyPath must be 'absolute-path|reason': {item}")
        map_res[get_canonical_path(split[0])] = split[1].strip()
    return map_res


def get_backup_references(
    manifest: dict[str, Any], kb_root: str, ignore_legacy_path: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any], dict[str, str]]:
    """Scan content tree for registered external references and unregistered absolute paths."""
    ignore_map = get_ignore_map(ignore_legacy_path)
    refs: list[dict[str, Any]] = []
    blockers: list[str] = []

    content_dir = manifest["content"]
    tree_files = get_safe_tree_files(content_dir, "knowledge-base content")
    md_files = [f for f in tree_files if f.lower().endswith(".md")]

    for file_path in md_files:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()

        parsed, _ = parse_markdown_page(content, filename=file_path)
        raw_lines = parsed.lines

        projected_lines_by_line: dict[int, str] = {}
        inline_code_spans: list[tuple[int, str]] = []
        # (line, parser href, full syntax start/length, target start/length).
        # Offsets are in the original document line, not normalized token text.
        link_syntax_spans: list[tuple[int, str, int, int, int, int]] = []
        marker_spans_by_line: dict[int, tuple[int, int]] = {}

        for token in parsed.tokens:
            if token.type != "inline" or not token.children:
                continue
            proj_dict = _inline_projected_lines(token)
            if proj_dict:
                projected_lines_by_line.update(proj_dict)
                for projected_line_no, projected_line in proj_dict.items():
                    marker = re.search(r"(?i)<!--\s*kb-external-local\s*-->", projected_line)
                    if marker is None or projected_line_no in marker_spans_by_line:
                        continue
                    if token.map is None:
                        continue
                    source_line_index = projected_line_no - (token.map[0] + 1)
                    source_lines = token.content.split("\n")
                    if not 0 <= source_line_index < len(source_lines):
                        continue
                    source_line = source_lines[source_line_index]
                    raw_line = raw_lines[projected_line_no - 1].rstrip("\r\n")
                    source_column = raw_line.find(source_line)
                    if source_column >= 0:
                        marker_spans_by_line[projected_line_no] = (
                            source_column + marker.start(),
                            marker.end() - marker.start(),
                        )

            for child in token.children:
                if child.type == "code_inline":
                    span = _token_source_document_span(token, child)
                    line_no = span[0] if span else (token.map[0] + 1 if token.map else 1)
                    val = (child.content or "").strip()
                    inline_code_spans.append((line_no, val))
                elif child.type == "link_open":
                    span = _token_source_document_span(token, child)
                    line_no = span[0] if span else (token.map[0] + 1 if token.map else 1)
                    s = child.meta.get(_SOURCE_START_META)
                    e = child.meta.get(_SOURCE_END_META)
                    if isinstance(s, int) and isinstance(e, int) and token.content:
                        link_text = token.content[s:e]
                        href = child.attrGet("href") or ""
                        line_start = token.content.rfind("\n", 0, s) + 1
                        line_end = token.content.find("\n", s)
                        if line_end < 0:
                            line_end = len(token.content)
                        source_line = token.content[line_start:line_end]
                        raw_line = (
                            raw_lines[line_no - 1].rstrip("\r\n")
                            if 1 <= line_no <= len(raw_lines)
                            else ""
                        )
                        source_column = raw_line.find(source_line)
                        target_span = get_markdown_link_target_span(link_text)
                        if source_column < 0 or target_span is None:
                            continue
                        target_start, target_end = target_span
                        syntax_start = source_column + s - line_start
                        link_syntax_spans.append(
                            (
                                line_no,
                                href,
                                syntax_start,
                                e - s,
                                syntax_start + target_start,
                                target_end - target_start,
                            )
                        )

        # First pass: map registered external sources on each line
        registered_on_line: dict[int, dict[str, bool]] = collections.defaultdict(dict)
        for lk in parsed.link_occurrences:
            if lk.is_image or not lk.target:
                continue
            decoded_target, _, _ = split_and_decode_target_path(lk.target)
            if is_absolute_local_path(decoded_target):
                line_no = lk.line_number
                raw_line = (
                    raw_lines[line_no - 1].rstrip("\r\n")
                    if 1 <= line_no <= len(raw_lines)
                    else ""
                )
                marked = lk.is_explicit_external_local and line_no in marker_spans_by_line
                if marked:
                    canon = get_canonical_path(decoded_target)
                    registered_on_line[line_no][canon] = True

        # Second pass: check link occurrences
        used_cand_indices: dict[int, set[int]] = collections.defaultdict(set)
        for lk in parsed.link_occurrences:
            if lk.is_image or not lk.target:
                continue
            decoded_target, _, _ = split_and_decode_target_path(lk.target)
            if not is_absolute_local_path(decoded_target):
                continue

            target = decoded_target
            source = get_canonical_path(decoded_target)
            line_no = lk.line_number
            raw_line = raw_lines[line_no - 1].rstrip("\r\n") if 1 <= line_no <= len(raw_lines) else ""
            marked = lk.is_explicit_external_local and line_no in marker_spans_by_line
            rel_file = get_normalized_relative_path(content_dir, file_path)

            if not marked:
                if source not in registered_on_line[line_no] and source not in ignore_map:
                    blockers.append(
                        f"legacy absolute local link at {rel_file}:{line_no} -> {lk.target}"
                    )
                continue

            proj_line = projected_lines_by_line.get(line_no, raw_line)
            project = get_field(proj_line, "project") or get_field(proj_line, "项目")
            project_id = get_field(proj_line, "project-id") or get_field(proj_line, "项目标识")
            relative = (
                get_field(proj_line, "project-relative source")
                or get_field(proj_line, "项目相对来源")
                or get_field(proj_line, "project-relative")
                or get_field(proj_line, "项目相对路径")
                or get_field(proj_line, "相对路径")
            )
            verified = (
                get_field(proj_line, "verified")
                or get_field(proj_line, "last verified")
                or get_field(proj_line, "验证日期")
                or get_field(proj_line, "已验证")
            )
            revision = get_field(proj_line, "revision") or get_field(proj_line, "版本")
            version_state = (
                get_field(proj_line, "version-state")
                or get_field(proj_line, "version_state")
                or get_field(proj_line, "版本状态")
            )

            if (
                not project
                or not project_id
                or not re.match(r"^[a-z0-9][a-z0-9._-]{0,63}$", project_id)
                or not test_safe_relative_source_path(relative)
                or not verified
                or not re.match(r"^\d{4}-\d{2}-\d{2}$", verified)
                or (not revision and not version_state)
            ):
                blockers.append(f"incomplete external-source metadata at {rel_file}:{line_no}")
                continue

            if not os.path.isfile(source):
                blockers.append(f"external source is missing: {source}")
                continue

            try:
                assert_no_redirecting_reparse_point(source, "external source")
            except Exception as exc:
                blockers.append(str(exc))
                continue

            assert relative is not None
            suffix = relative.replace("/", os.sep)
            expected_suffix = os.sep + suffix
            if not path_ends_with(source, expected_suffix):
                blockers.append(
                    f"source-path/root inconsistency: {source} does not end in project-relative source {relative}"
                )
                continue

            project_root = source[: len(source) - len(suffix)].rstrip("\\/")
            if (
                not project_root
                or not os.path.isdir(project_root)
                or test_path_inside_root(project_root, kb_root)
            ):
                blockers.append(f"invalid external project root for {source}")
                continue

            try:
                assert_no_redirecting_reparse_point(project_root, "external project root")
            except Exception as exc:
                blockers.append(str(exc))
                continue

            link_start = -1
            link_length = -1
            target_start = -1
            target_length = -1
            raw_target_in_text = decoded_target
            for cand_idx, cand in enumerate(link_syntax_spans):
                if cand_idx in used_cand_indices[line_no]:
                    continue
                cand_line, cand_href, cand_start, cand_length, cand_target_start, cand_target_length = cand
                if cand_line != line_no:
                    continue
                candidate_target = raw_line[cand_target_start : cand_target_start + cand_target_length]
                target_for_decode = (
                    candidate_target[1:-1]
                    if candidate_target.startswith("<") and candidate_target.endswith(">")
                    else candidate_target
                )
                cand_dec, _, _ = split_and_decode_target_path(target_for_decode)
                if cand_href == lk.target and (cand_dec == decoded_target or target_for_decode == lk.target):
                    link_start = cand_start
                    link_length = cand_length
                    target_start = cand_target_start
                    target_length = cand_target_length
                    raw_target_in_text = candidate_target
                    used_cand_indices[line_no].add(cand_idx)
                    break

            if target_start < 0:
                blockers.append(
                    f"cannot locate parser-confirmed registered Markdown link target at {rel_file}:{line_no}"
                )
                continue

            refs.append(
                {
                    "source": source,
                    "original_target": raw_target_in_text,
                    "project_root": project_root,
                    "project": project,
                    "project_id": project_id,
                    "relative": relative.replace("\\", "/"),
                    "verified": verified,
                    "revision": revision,
                    "version_state": version_state,
                    "referrer": rel_file,
                    "line": line_no,
                    "original_line": raw_line,
                    "link_start": link_start,
                    "link_length": link_length,
                    "target_start": target_start,
                    "target_length": target_length,
                    "marker_start": marker_spans_by_line[line_no][0],
                    "marker_length": marker_spans_by_line[line_no][1],
                }
            )

        # Third pass: validate inline code spans
        for line_no, span_val in inline_code_spans:
            decoded_span, _, _ = split_and_decode_target_path(span_val)
            if is_absolute_local_path(decoded_span):
                span_source = get_canonical_path(decoded_span)
                if (
                    span_source not in registered_on_line[line_no]
                    and span_source not in ignore_map
                ):
                    rel_file = get_normalized_relative_path(content_dir, file_path)
                    blockers.append(
                        f"legacy absolute local path in code span at {rel_file}:{line_no} -> {span_val}"
                    )

    if blockers:
        raise RuntimeError("BLOCKER: " + "; ".join(blockers))

    targets: dict[str, Any] = {}
    sources: dict[str, str] = {}
    for ref in refs:
        target = f"external/projects/{ref['project_id']}/{ref['relative']}"
        if target in targets and not path_equals(targets[target]["source"], ref["source"]):
            raise RuntimeError(
                f"BLOCKER: two canonical sources map to one portable target: {target}"
            )
        canon_source = get_canonical_existing_path(ref["source"])
        if canon_source in sources and sources[canon_source] != target:
            raise RuntimeError(
                f"BLOCKER: one canonical external source maps to multiple portable targets: {canon_source}"
            )
        targets[target] = ref
        sources[canon_source] = target

    return refs, targets, ignore_map


def add_portable_manifest_field(source_manifest: str, destination_manifest: str) -> None:
    """Add external_dir: external to manifest if not already present."""
    with open(source_manifest, "r", encoding="utf-8") as f:
        raw = f.read()
    if not re.search(r"(?m)^\s*external_dir\s*:", raw):
        raw = raw.rstrip("\r\n") + "\nexternal_dir: external\n"
    with open(destination_manifest, "w", encoding="utf-8", newline="\n") as f:
        f.write(raw)


def get_backup_plan(
    kb_root: str,
    destination: str,
    mode: str = "ReferenceComplete",
    ignore_legacy_path: list[str] | None = None,
) -> dict[str, Any]:
    """Generate deterministic backup plan and digest."""
    if mode == "ProjectSnapshot":
        raise RuntimeError(
            "BLOCKER: ProjectSnapshot is deliberately deferred in v1; use ReferenceComplete."
        )
    if mode != "ReferenceComplete":
        raise RuntimeError(f"BLOCKER: unsupported backup mode: {mode}")

    root_canon = get_canonical_path(kb_root)
    manifest = read_manifest(root_canon)
    refs, targets, ignore_map = get_backup_references(
        manifest=manifest, kb_root=root_canon, ignore_legacy_path=ignore_legacy_path or []
    )

    destination_full = get_canonical_path(destination)
    assert_no_redirecting_reparse_point(destination_full, "backup destination")
    bundle = os.path.join(destination_full, "portable-kb")

    source_roots = [root_canon] + sorted(
        {ref["project_root"] for ref in refs}, key=unicode_ordinal_key
    )
    for sr in source_roots:
        if test_path_inside_root(destination_full, sr):
            raise RuntimeError(
                f"BLOCKER: destination must not be inside a source root: {destination_full}"
            )
    if test_path_inside_root(bundle, root_canon):
        raise RuntimeError("BLOCKER: bundle output must not be inside the knowledge-base root")

    records: list[dict[str, Any]] = []
    records.append(new_snapshot_record("kb_manifest", manifest["manifest_path"], "kb.yaml"))

    content_tree = get_safe_tree_files(manifest["content"], "knowledge-base content")
    content_records: list[dict[str, Any]] = []
    for f_path in content_tree:
        rel = get_normalized_relative_path(manifest["content"], f_path)
        content_records.append(new_snapshot_record("content", f_path, f"content/{rel}"))
    content_records.sort(
        key=lambda r: (
            unicode_ordinal_key(r["portable_path"]),
            unicode_ordinal_key(r["source_path"]),
        )
    )
    records.extend(content_records)

    external_records: list[dict[str, Any]] = []
    for target_key, ref_val in targets.items():
        external_records.append(
            new_snapshot_record(
                "external",
                ref_val["source"],
                target_key,
                project_id=ref_val["project_id"],
                project_relative_source=ref_val["relative"],
            )
        )
    external_records.sort(
        key=lambda r: (
            unicode_ordinal_key(r["portable_path"]),
            unicode_ordinal_key(r["source_path"]),
        )
    )
    records.extend(external_records)

    reference_mappings: list[dict[str, Any]] = []
    for ref in refs:
        reference_mappings.append(
            {
                "source_path": get_canonical_existing_path(ref["source"]),
                "portable_path": f"external/projects/{ref['project_id']}/{ref['relative']}",
                "project": ref["project"],
                "project_id": ref["project_id"],
                "project_relative_source": ref["relative"],
                "referrer": ref["referrer"],
                "line": int(ref["line"]),
                "verified": ref["verified"],
                "revision": ref["revision"],
                "version_state": ref["version_state"],
            }
        )
    reference_mappings.sort(
        key=lambda r: (
            unicode_ordinal_key(r["portable_path"]),
            unicode_ordinal_key(r["source_path"]),
            unicode_ordinal_key(r["referrer"]),
            r["line"],
        )
    )

    ignored: list[dict[str, str]] = [
        {"path": get_canonical_path(k), "reason": v}
        for k, v in sorted(ignore_map.items(), key=lambda item: unicode_ordinal_key(item[0]))
    ]
    ignored.sort(key=lambda r: unicode_ordinal_key(r["path"]))

    totals = {
        "kb_manifest_files": 1,
        "content_files": len(content_records),
        "external_files": len(external_records),
        "external_references": len(reference_mappings),
        "all_source_files": len(records),
    }

    plan_without_digest: dict[str, Any] = {
        "plan_schema_version": PLAN_SCHEMA_VERSION,
        "root": root_canon,
        "destination": destination_full,
        "bundle": bundle,
        "mode": mode,
        "content_dir": manifest["content"],
        "ignored_legacy_paths": ignored,
        "files": records,
        "reference_mappings": reference_mappings,
        "totals": totals,
    }

    plan = dict(plan_without_digest)
    plan["plan_digest"] = get_plan_digest(plan_without_digest)
    return plan


def get_plan_change_summary(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    """Compare expected and actual plans and generate list of changes."""
    changes: list[str] = []
    for setting in (
        "plan_schema_version",
        "root",
        "destination",
        "bundle",
        "mode",
        "content_dir",
    ):
        if str(expected.get(setting, "")) != str(actual.get(setting, "")):
            changes.append(f"plan setting changed: {setting}")

    expected_files = {f"{r['kind']}|{r['portable_path']}": r for r in expected.get("files", [])}
    actual_files = {f"{r['kind']}|{r['portable_path']}": r for r in actual.get("files", [])}
    all_file_keys = sorted(set(expected_files.keys()) | set(actual_files.keys()))

    for key in all_file_keys:
        if key not in expected_files:
            changes.append(f"source added: {key}")
            continue
        if key not in actual_files:
            changes.append(f"source removed: {key}")
            continue
        exp_rec = expected_files[key]
        act_rec = actual_files[key]
        for field in (
            "source_path",
            "size_bytes",
            "mtime_utc",
            "sha256",
            "project_id",
            "project_relative_source",
        ):
            if str(exp_rec.get(field, "")) != str(act_rec.get(field, "")):
                changes.append(f"source changed ({field}): {key}")

    exp_refs = json.dumps(
        expected.get("reference_mappings", []), ensure_ascii=False, separators=(",", ":")
    )
    act_refs = json.dumps(
        actual.get("reference_mappings", []), ensure_ascii=False, separators=(",", ":")
    )
    if exp_refs != act_refs:
        changes.append("registered reference mapping or provenance changed")

    exp_ign = json.dumps(
        expected.get("ignored_legacy_paths", []), ensure_ascii=False, separators=(",", ":")
    )
    act_ign = json.dumps(
        actual.get("ignored_legacy_paths", []), ensure_ascii=False, separators=(",", ":")
    )
    if exp_ign != act_ign:
        changes.append("ignored legacy path configuration changed")

    if not changes:
        changes.append("confirmed plan digest differs from the current plan")

    # Deduplicate while preserving order
    seen: set[str] = set()
    unique_changes: list[str] = []
    for c in changes:
        if c not in seen:
            seen.add(c)
            unique_changes.append(c)
    return unique_changes


def assert_confirmed_plan_current(
    expected_plan: dict[str, Any],
    kb_root: str,
    destination: str,
    mode: str,
    ignore_legacy_path: list[str],
) -> dict[str, Any]:
    """Verify that current plan matches expected plan digest; raise ReconfirmException if not."""
    actual = get_backup_plan(kb_root, destination, mode, ignore_legacy_path)
    if actual["plan_digest"] != expected_plan["plan_digest"]:
        summary = get_plan_change_summary(expected_plan, actual)
        raise ReconfirmException(actual, summary)
    return actual


def assert_record_current(record: dict[str, Any]) -> None:
    """Verify record has not changed during copy; raise ReconfirmException if modified."""
    if not test_snapshot_record(record):
        summary = [f"source changed during copy: {record['kind']} {record['source_path']}"]
        raise ReconfirmException(None, summary)


def execute_backup(
    root: str,
    destination: str,
    mode: str = "ReferenceComplete",
    ignore_legacy_path: list[str] | None = None,
    execute: bool = False,
    confirmed_plan_digest: str | None = None,
) -> tuple[int, Envelope]:
    """Execute backup planning or execution according to contract."""
    staging: str | None = None
    reconfirm_plan: dict[str, Any] | None = None
    reconfirm_summary: list[str] = []
    ignore_paths = ignore_legacy_path or []
    kb_root: str | None = None

    try:
        if mode == "ProjectSnapshot":
            raise RuntimeError(
                "BLOCKER: ProjectSnapshot is deliberately deferred in v1; use ReferenceComplete."
            )
        if not os.path.isdir(root):
            raise RuntimeError(f"FATAL: knowledge-base root does not exist: {root}")

        kb_root = get_canonical_path(root)
        plan = get_backup_plan(
            kb_root=kb_root, destination=destination, mode=mode, ignore_legacy_path=ignore_paths
        )

        if os.path.exists(plan["bundle"]):
            raise RuntimeError(
                f"BLOCKER: bundle already exists and will not be overwritten: {plan['bundle']}"
            )

        if not execute:
            return 0, Envelope(
                command="backup",
                status="plan",
                root=kb_root,
                data={
                    "plan": plan,
                    "change_summary": [],
                    "execute": False,
                    "message": "Read-only plan succeeded. Display every listed source path, obtain explicit confirmation, then pass this exact plan_digest with -Execute -ConfirmedPlanDigest.",
                },
                diagnostics=[],
            )

        if not confirmed_plan_digest or not confirmed_plan_digest.strip():
            return 2, Envelope(
                command="backup",
                status="confirmation_required",
                root=kb_root,
                data={
                    "plan": plan,
                    "change_summary": [],
                    "execute": True,
                    "message": "Execution requires a post-plan confirmation. Re-run with the exact plan_digest returned by the current full plan.",
                },
                diagnostics=[
                    Diagnostic(
                        code="CONFIRMATION_REQUIRED",
                        severity="error",
                        file=None,
                        span=None,
                        target=None,
                        message="Execution requires a post-plan confirmation. Re-run with the exact plan_digest returned by the current full plan.",
                    )
                ],
            )

        if confirmed_plan_digest != plan["plan_digest"]:
            return 2, Envelope(
                command="backup",
                status="reconfirm_required",
                root=kb_root,
                data={
                    "plan": plan,
                    "change_summary": [
                        "supplied plan_digest does not match the current plan; the prior snapshot is not available to compare"
                    ],
                    "execute": True,
                    "message": "The supplied plan digest does not match the current full plan. Review the new list and confirm it again.",
                },
                diagnostics=[
                    Diagnostic(
                        code="RECONFIRM_REQUIRED",
                        severity="error",
                        file=None,
                        span=None,
                        target=None,
                        message="The supplied plan digest does not match the current full plan. Review the new list and confirm it again.",
                    )
                ],
            )

        # Pre-write plan check. No destination or staging directory exists before it.
        confirmed_plan = assert_confirmed_plan_current(
            expected_plan=plan,
            kb_root=kb_root,
            destination=destination,
            mode=mode,
            ignore_legacy_path=ignore_paths,
        )
        if os.path.exists(confirmed_plan["bundle"]):
            raise RuntimeError(
                f"BLOCKER: bundle already exists and will not be overwritten: {confirmed_plan['bundle']}"
            )

        manifest = read_manifest(kb_root)
        references, targets, _ = get_backup_references(
            manifest=manifest, kb_root=kb_root, ignore_legacy_path=ignore_paths
        )

        backup_id = str(uuid.uuid4())
        dest_full = confirmed_plan["destination"]
        assert_no_redirecting_reparse_point(dest_full, "backup destination")
        os.makedirs(dest_full, exist_ok=True)
        assert_no_redirecting_reparse_point(dest_full, "backup destination")

        staging = os.path.join(dest_full, f".incomplete-{backup_id}")
        os.makedirs(staging, exist_ok=False)
        assert_no_redirecting_reparse_point(staging, "backup staging directory")

        bundle = staging
        bundle_content = os.path.join(bundle, "content")
        os.makedirs(bundle_content, exist_ok=True)
        os.makedirs(os.path.join(bundle, "external", "projects"), exist_ok=True)

        file_records: list[dict[str, Any]] = []
        manifest_records = [
            r for r in confirmed_plan["files"] if r.get("kind") == "kb_manifest"
        ]
        if len(manifest_records) != 1:
            raise RuntimeError("FATAL: confirmed plan has no unique kb.yaml record")
        manifest_record = manifest_records[0]

        assert_record_current(manifest_record)
        add_portable_manifest_field(
            manifest_record["source_path"], os.path.join(bundle, "kb.yaml")
        )
        assert_record_current(manifest_record)

        file_records.append(
            {
                "kind": "kb_manifest",
                "source_path": manifest_record["source_path"],
                "portable_path": "kb.yaml",
                "size_bytes": manifest_record["size_bytes"],
                "mtime_utc": manifest_record["mtime_utc"],
                "source_sha256": manifest_record["sha256"],
                "sha256": get_sha256(os.path.join(bundle, "kb.yaml")),
                "copy_status": "copied",
            }
        )

        for record in [r for r in confirmed_plan["files"] if r.get("kind") == "content"]:
            assert_record_current(record)
            copied = os.path.join(bundle, record["portable_path"].replace("/", os.sep))
            if not test_path_inside_root(copied, bundle):
                raise RuntimeError(
                    f"FATAL: content portable path escaped bundle: {record['portable_path']}"
                )
            copied_dir = os.path.dirname(copied)
            os.makedirs(copied_dir, exist_ok=True)
            assert_no_redirecting_reparse_point(copied_dir, "backup staging path")
            shutil.copyfile(record["source_path"], copied)
            assert_record_current(record)
            if get_sha256(copied) != record["sha256"]:
                raise RuntimeError(f"FATAL: copied content hash differs: {record['source_path']}")
            file_records.append(
                {
                    "kind": "content",
                    "source_path": record["source_path"],
                    "portable_path": record["portable_path"],
                    "size_bytes": record["size_bytes"],
                    "mtime_utc": record["mtime_utc"],
                    "source_sha256": record["sha256"],
                    "sha256": record["sha256"],
                    "copy_status": "copied",
                }
            )

        for record in [r for r in confirmed_plan["files"] if r.get("kind") == "external"]:
            assert_record_current(record)
            target_full = os.path.join(bundle, record["portable_path"].replace("/", os.sep))
            if not test_path_inside_root(target_full, bundle):
                raise RuntimeError(
                    f"FATAL: external portable path escaped bundle: {record['portable_path']}"
                )
            target_dir = os.path.dirname(target_full)
            os.makedirs(target_dir, exist_ok=True)
            assert_no_redirecting_reparse_point(target_dir, "backup staging path")
            shutil.copyfile(record["source_path"], target_full)
            assert_record_current(record)
            if get_sha256(target_full) != record["sha256"]:
                raise RuntimeError(f"FATAL: copied external hash differs: {record['source_path']}")
            file_records.append(
                {
                    "kind": "external",
                    "source_path": record["source_path"],
                    "portable_path": record["portable_path"],
                    "size_bytes": record["size_bytes"],
                    "mtime_utc": record["mtime_utc"],
                    "source_sha256": record["sha256"],
                    "sha256": record["sha256"],
                    "copy_status": "copied",
                    "project_id": record.get("project_id", ""),
                    "project_relative_source": record.get("project_relative_source", ""),
                }
            )

        # Markdown links rewrite
        refs_by_referrer: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
        for ref in references:
            refs_by_referrer[ref["referrer"]].append(ref)

        for referrer_name, ref_list in refs_by_referrer.items():
            copy_path = os.path.join(bundle_content, referrer_name.replace("/", os.sep))
            with open(copy_path, "r", encoding="utf-8") as f:
                lines = [line.rstrip("\r\n") for line in f]

            refs_by_line: dict[int, list[dict[str, Any]]] = collections.defaultdict(list)
            for r in ref_list:
                refs_by_line[r["line"]].append(r)

            for line_no, line_refs in refs_by_line.items():
                idx = line_no - 1
                original = line_refs[0]["original_line"].rstrip("\r\n")
                if lines[idx] != original:
                    raise RuntimeError(
                        f"FATAL: copied Markdown changed after scan before rewrite: {referrer_name}:{line_no}"
                    )
                working = lines[idx]
                edits: list[tuple[int, int, str]] = []
                marker_edits: set[tuple[int, int]] = set()
                for reference in line_refs:
                    target_start = reference["target_start"]
                    target_length = reference["target_length"]
                    old_target = lines[idx][target_start : target_start + target_length]
                    if old_target != reference["original_target"]:
                        raise RuntimeError(
                            f"FATAL: registered Markdown link target no longer matches scan: {referrer_name}:{line_no}"
                        )
                    portable_target = os.path.join(
                        bundle,
                        f"external/projects/{reference['project_id']}/{reference['relative']}".replace(
                            "/", os.sep
                        ),
                    )
                    relative_target = os.path.relpath(
                        portable_target, os.path.dirname(copy_path)
                    ).replace("\\", "/")
                    edits.append((target_start, target_length, relative_target))
                    marker_edits.add((reference["marker_start"], reference["marker_length"]))

                for marker_start, marker_length in marker_edits:
                    old_marker = lines[idx][marker_start : marker_start + marker_length]
                    if not re.fullmatch(r"(?i)<!--\s*kb-external-local\s*-->", old_marker):
                        raise RuntimeError(
                            f"FATAL: registered Markdown marker no longer matches scan: {referrer_name}:{line_no}"
                        )
                    edits.append((marker_start, marker_length, "<!-- kb-portable-source -->"))

                for start, length, replacement in sorted(edits, key=lambda item: item[0], reverse=True):
                    working = working[:start] + replacement + working[start + length :]
                lines[idx] = working

            with open(copy_path, "w", encoding="utf-8", newline="\n") as f:
                f.write("\n".join(lines) + "\n")

        for record in [r for r in file_records if r.get("kind") == "content"]:
            record["sha256"] = get_sha256(
                os.path.join(bundle, record["portable_path"].replace("/", os.sep))
            )

        now_utc = datetime.datetime.now(datetime.timezone.utc)
        ticks = int(now_utc.microsecond * 10)
        created_utc = now_utc.strftime("%Y-%m-%dT%H:%M:%S.") + f"{ticks:07d}Z"

        manifest_obj = {
            "schema": "portable-kb-backup-manifest",
            "schema_version": 1,
            "backup_id": backup_id,
            "created_utc": created_utc,
            "mode": mode,
            "plan_digest": confirmed_plan["plan_digest"],
            "completeness": {
                "complete": True,
                "blockers": [],
                "ignored_legacy_paths": confirmed_plan["ignored_legacy_paths"],
            },
            "source": {
                "kb_root": kb_root,
                "content_dir": confirmed_plan["content_dir"],
                "kb_manifest": "kb.yaml",
            },
            "files": file_records,
            "references": confirmed_plan["reference_mappings"],
            "totals": confirmed_plan["totals"],
        }

        report = "\n".join(
            [
                "# Portable knowledge-base backup",
                "",
                f"- Backup ID: {backup_id}",
                f"- Mode: {mode}",
                f"- Confirmed plan digest: {confirmed_plan['plan_digest']}",
                "- Complete: true",
                f"- Content files: {manifest_obj['totals']['content_files']}",
                f"- External files: {manifest_obj['totals']['external_files']}",
                "",
                "Restore with python -X utf8 ./scripts/kb.py restore --bundle <portable-kb> --destination <new-root> --execute. The destination must not already exist.",
                "",
            ]
        )
        with open(os.path.join(bundle, "backup-report.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(report)

        readme = "\n".join(
            [
                "# Restore",
                "",
                "This bundle is self-contained. Verify it before restore, then restore only into a destination that does not already exist. The original paths in backup-manifest.json are provenance only. CHECKSUMS.sha256 detects accidental or untrusted modification only when the checksum file itself is trusted; it is not a digital signature.",
                "",
            ]
        )
        with open(os.path.join(bundle, "README-RESTORE.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(readme)

        with open(os.path.join(bundle, "backup-manifest.json"), "w", encoding="utf-8", newline="") as f:
            json.dump(manifest_obj, f, ensure_ascii=False, indent=2)

        checksum_path = os.path.join(bundle, "CHECKSUMS.sha256")
        checksum_files = [
            f
            for f in get_safe_tree_files(bundle, "backup staging tree")
            if f.lower() != checksum_path.lower()
        ]
        checksum_lines = [
            f"{get_sha256(f)}  {get_normalized_relative_path(bundle, f)}" for f in checksum_files
        ]
        with open(checksum_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("\n".join(checksum_lines) + "\n")

        v_code, v_env = verify_backup(bundle)
        if v_code != 0:
            issues_str = " ".join(v_env.data.get("issues", []))
            raise RuntimeError(f"FATAL: staging verification failed: {issues_str}")

        audit_code, audit_env = audit_command(bundle, profile="legacy")
        if audit_code != 0:
            issues_str = " ".join(
                [f"{i.get('code')}: {i.get('message')}" for i in audit_env.data.get("issues", [])]
            )
            raise RuntimeError(f"FATAL: staging knowledge-base audit failed: {issues_str}")

        assert_confirmed_plan_current(
            expected_plan=confirmed_plan,
            kb_root=kb_root,
            destination=destination,
            mode=mode,
            ignore_legacy_path=ignore_paths,
        )
        get_safe_tree_files(bundle, "backup staging tree")
        assert_no_redirecting_reparse_point(dest_full, "backup destination")
        if os.path.exists(confirmed_plan["bundle"]):
            raise RuntimeError(
                f"BLOCKER: bundle appeared before publication and will not be overwritten: {confirmed_plan['bundle']}"
            )

        # Atomic directory move
        try:
            publish_dir_fail_if_exists(bundle, confirmed_plan["bundle"])
        except FileExistsError:
            raise RuntimeError(
                f"BLOCKER: bundle appeared before publication and will not be overwritten: {confirmed_plan['bundle']}"
            )

        return 0, Envelope(
            command="backup",
            status="created",
            root=kb_root,
            data={
                "plan": confirmed_plan,
                "change_summary": [],
                "execute": True,
                "message": "Portable ReferenceComplete backup created from the confirmed plan and verified before publication.",
            },
            diagnostics=[],
        )

    except ReconfirmException as r_exc:
        reconfirm_plan = r_exc.plan
        reconfirm_summary = r_exc.change_summary
        if reconfirm_plan is None and kb_root is not None:
            try:
                reconfirm_plan = get_backup_plan(
                    kb_root=kb_root,
                    destination=destination,
                    mode=mode,
                    ignore_legacy_path=ignore_paths,
                )
            except Exception as exc:
                reconfirm_summary.append(f"current plan could not be rebuilt: {exc}")

        data: dict[str, Any] = {
            "plan": reconfirm_plan,
            "change_summary": reconfirm_summary,
            "execute": execute,
            "message": "The source snapshot changed. No portable-kb was published; review the current plan and confirm again.",
        }
        if staging and os.path.exists(staging):
            data["incomplete_bundle"] = staging

        return 2, Envelope(
            command="backup",
            status="reconfirm_required",
            root=kb_root,
            data=data,
            diagnostics=[
                Diagnostic(
                    code="RECONFIRM_REQUIRED",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message="The source snapshot changed. No portable-kb was published; review the current plan and confirm again.",
                )
            ],
        )

    except Exception as exc:
        msg = str(exc)
        code = 3 if msg.startswith("FATAL:") else 2
        data_err: dict[str, Any] = {
            "plan": None,
            "change_summary": [],
            "execute": execute,
            "message": msg,
        }
        if staging and os.path.exists(staging):
            data_err["incomplete_bundle"] = staging

        diag_code = "FATAL_ERROR" if code == 3 else "BLOCKER_ERROR"
        return code, Envelope(
            command="backup",
            status="blocked",
            root=kb_root,
            data=data_err,
            diagnostics=[
                Diagnostic(
                    code=diag_code,
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message=msg,
                )
            ],
        )


def verify_backup(bundle: str) -> tuple[int, Envelope]:
    """Verify integrity and structure of a portable backup bundle."""
    try:
        if not os.path.isdir(bundle):
            raise RuntimeError(f"FATAL: bundle directory does not exist: {bundle}")
        assert_no_redirecting_reparse_point(bundle, "portable bundle")
        bundle_full = get_canonical_path(bundle)
        bundle_files = get_safe_tree_files(bundle_full, "portable bundle")

        issues: list[str] = []

        required_members = (
            "kb.yaml",
            "content",
            "external",
            "backup-manifest.json",
            "CHECKSUMS.sha256",
            "backup-report.md",
            "README-RESTORE.md",
        )
        for req in required_members:
            if not os.path.exists(os.path.join(bundle_full, req)):
                issues.append(f"missing required bundle member: {req}")

        if issues:
            return 2, Envelope(
                command="verify-backup",
                status="invalid",
                root=bundle_full,
                data={
                    "status": "invalid",
                    "bundle": bundle_full,
                    "errors": len(issues),
                    "issues": issues,
                },
                diagnostics=[
                    Diagnostic(code="VERIFY_FAILED", severity="error", file=None, span=None, target=None, message=i)
                    for i in issues
                ],
            )

        manifest_path = os.path.join(bundle_full, "backup-manifest.json")
        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
        except Exception as exc:
            issues.append(f"manifest JSON invalid: {exc}")
            return 3, Envelope(
                command="verify-backup",
                status="fatal",
                root=bundle_full,
                data={
                    "status": "fatal",
                    "bundle": bundle_full,
                    "errors": len(issues),
                    "issues": issues,
                },
                diagnostics=[
                    Diagnostic(code="FATAL", severity="error", file=None, span=None, target=None, message=i)
                    for i in issues
                ],
            )

        if (
            metadata.get("schema") != "portable-kb-backup-manifest"
            or metadata.get("schema_version") != 1
            or not metadata.get("completeness", {}).get("complete")
        ):
            issues.append("manifest does not claim a complete supported backup")

        checksum_records: dict[str, str] = {}
        checksum_path = os.path.join(bundle_full, "CHECKSUMS.sha256")
        with open(checksum_path, "r", encoding="utf-8") as f:
            for raw_line in f:
                line = raw_line.rstrip("\r\n")
                m = re.match(r"^([0-9a-fA-F]{64})\s\s(.+)$", line)
                if not m:
                    issues.append(f"invalid checksum record: {line}")
                    continue
                relative = m.group(2).replace("\\", "/")
                if not test_safe_portable_path(relative):
                    issues.append(f"unsafe checksum path: {relative}")
                    continue
                target = get_canonical_path(
                    os.path.join(bundle_full, relative.replace("/", os.sep))
                )
                if not test_path_inside_root(target, bundle_full):
                    issues.append(f"checksum path escapes bundle: {relative}")
                    continue
                if relative in checksum_records:
                    issues.append(f"duplicate checksum record: {relative}")
                    continue
                checksum_records[relative] = m.group(1).lower()
                if not os.path.isfile(target):
                    issues.append(f"checksum file missing: {relative}")
                elif get_sha256(target) != checksum_records[relative]:
                    issues.append(f"checksum mismatch: {relative}")

        for file_path in bundle_files:
            if file_path.lower() == checksum_path.lower():
                continue
            relative = get_normalized_relative_path(bundle_full, file_path)
            if relative not in checksum_records:
                issues.append(f"checksum missing for bundle file: {relative}")

        manifest_files: dict[str, Any] = {}
        manifest_external: dict[str, bool] = {}

        for file_entry in metadata.get("files", []):
            kind = str(file_entry.get("kind"))
            relative = str(file_entry.get("portable_path", "")).replace("\\", "/")
            if kind not in ("kb_manifest", "content", "external"):
                issues.append(f"unsupported manifest file kind: {kind} ({relative})")
                continue
            if not test_safe_portable_path(relative):
                issues.append(f"unsafe manifest portable path: {relative}")
                continue

            kind_matches = (
                (kind == "kb_manifest" and relative == "kb.yaml")
                or (kind == "content" and relative.lower().startswith("content/"))
                or (kind == "external" and relative.lower().startswith("external/"))
            )
            if not kind_matches:
                issues.append(f"manifest kind/path mismatch: {kind} -> {relative}")
                continue
            if relative in manifest_files:
                issues.append(f"duplicate manifest portable path: {relative}")
                continue

            manifest_files[relative] = file_entry
            if kind == "external":
                manifest_external[relative] = True

            target = get_canonical_path(os.path.join(bundle_full, relative.replace("/", os.sep)))
            if relative not in checksum_records:
                issues.append(f"manifest file lacks checksum: {relative}")
            if not test_path_inside_root(target, bundle_full) or not os.path.isfile(target):
                issues.append(f"manifest file missing or escaping: {relative}")
                continue
            expected_hash = str(file_entry.get("sha256", "")).lower()
            if not re.match(r"^[0-9a-f]{64}$", expected_hash) or get_sha256(target) != expected_hash:
                issues.append(f"manifest hash mismatch: {relative}")

        for file_path in bundle_files:
            relative = get_normalized_relative_path(bundle_full, file_path)
            is_restore_member = (
                relative == "kb.yaml"
                or relative.lower().startswith("content/")
                or relative.lower().startswith("external/")
            )
            if is_restore_member and relative not in manifest_files:
                issues.append(f"unmanifested restore file: {relative}")

        for reference in metadata.get("references", []):
            portable_path = str(reference.get("portable_path", "")).replace("\\", "/")
            if portable_path not in manifest_external:
                issues.append(f"reference has no manifest external file: {portable_path}")

        for file_path in bundle_files:
            relative = get_normalized_relative_path(bundle_full, file_path)
            if relative.lower().startswith("external/") and relative not in manifest_external:
                issues.append(f"unmanifested external file: {relative}")

        for file_path in bundle_files:
            relative = get_normalized_relative_path(bundle_full, file_path)
            if relative.lower().startswith("content/") and file_path.lower().endswith(".md"):
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        for link in get_links_in_line(line):
                            target = str(link["target"])
                            if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target) or target.startswith("#"):
                                continue
                            path_part, _, _ = split_and_decode_target_path(target)
                            if not path_part.strip():
                                continue
                            resolved = get_canonical_path(
                                os.path.join(os.path.dirname(file_path), path_part.replace("/", os.sep))
                            )
                            portable = bool(
                                re.search(r"(?i)<!--\s*kb-portable-source\s*-->", line)
                            )
                            allowed_root = (
                                os.path.join(bundle_full, "external")
                                if portable
                                else os.path.join(bundle_full, "content")
                            )
                            if not test_path_inside_root(resolved, allowed_root):
                                issues.append(
                                    f"portable link escapes its allowed root: {os.path.basename(file_path)} -> {target}"
                                )
                            elif not os.path.isfile(resolved):
                                issues.append(
                                    f"portable link missing: {os.path.basename(file_path)} -> {target}"
                                )

        audit_code, audit_env = audit_command(bundle_full, profile="legacy")
        if audit_code != 0:
            issues_str = " ".join(
                [f"{i.get('code')}: {i.get('message')}" for i in audit_env.data.get("issues", [])]
            )
            issues.append(f"knowledge-base audit failed: {issues_str}")

        if issues:
            return 2, Envelope(
                command="verify-backup",
                status="invalid",
                root=bundle_full,
                data={
                    "status": "invalid",
                    "bundle": bundle_full,
                    "errors": len(issues),
                    "issues": issues,
                },
                diagnostics=[
                    Diagnostic(code="VERIFY_FAILED", severity="error", file=None, span=None, target=None, message=i)
                    for i in issues
                ],
            )

        return 0, Envelope(
            command="verify-backup",
            status="valid",
            root=bundle_full,
            data={
                "status": "valid",
                "bundle": bundle_full,
                "errors": 0,
                "issues": [],
            },
            diagnostics=[],
        )

    except Exception as exc:
        msg = str(exc)
        return 3, Envelope(
            command="verify-backup",
            status="fatal",
            root=get_canonical_path(bundle) if os.path.exists(bundle) else None,
            data={
                "status": "fatal",
                "bundle": bundle,
                "errors": 1,
                "issues": [msg],
            },
            diagnostics=[
                Diagnostic(
                    code="FATAL",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message=msg,
                )
            ],
        )


def restore_backup(
    bundle: str,
    destination: str,
    mode: str = "Portable",
    project_root_map: str | None = None,
    execute: bool = False,
) -> tuple[int, Envelope]:
    """Restore a verified portable backup bundle into a new destination."""
    staging: str | None = None
    dest_full: str | None = None

    try:
        if mode == "Relink":
            raise RuntimeError(
                "BLOCKER: Relink restore is not implemented in v1; Portable mode is the supported production path."
            )
        if not os.path.isdir(bundle):
            raise RuntimeError(f"FATAL: bundle directory does not exist: {bundle}")
        assert_no_redirecting_reparse_point(bundle, "portable bundle")
        bundle_full = get_canonical_path(bundle)
        get_safe_tree_files(bundle_full, "portable bundle")

        dest_full = get_canonical_path(destination)
        assert_no_redirecting_reparse_point(dest_full, "restore destination")
        if test_path_inside_root(dest_full, bundle_full):
            raise RuntimeError("BLOCKER: restore destination must not be inside the bundle")
        if os.path.exists(dest_full):
            raise RuntimeError(
                "BLOCKER: restore destination must not already exist; restore never overwrites"
            )

        manifest_path = os.path.join(bundle_full, "backup-manifest.json")
        if not os.path.isfile(manifest_path):
            raise RuntimeError("BLOCKER: backup manifest is missing")
        with open(manifest_path, "rb") as f:
            manifest_bytes = f.read()
        manifest_hash = get_bytes_sha256(manifest_bytes)
        try:
            metadata = json.loads(manifest_bytes.decode("utf-8"))
        except Exception as exc:
            raise RuntimeError(f"BLOCKER: backup manifest JSON is invalid: {exc}")

        v_code, v_env = verify_backup(bundle_full)
        if v_code != 0:
            issues_str = " ".join(v_env.data.get("issues", []))
            raise RuntimeError(f"BLOCKER: bundle verification failed: {issues_str}")
        if get_sha256(manifest_path) != manifest_hash:
            raise RuntimeError("BLOCKER: backup manifest changed during verification")

        seen: dict[str, bool] = {}
        records: list[dict[str, Any]] = []
        for file_entry in metadata.get("files", []):
            kind = str(file_entry.get("kind"))
            relative = str(file_entry.get("portable_path", "")).replace("\\", "/")
            if kind not in ("kb_manifest", "content", "external") or not test_safe_portable_path(
                relative
            ):
                raise RuntimeError(f"BLOCKER: unsupported or unsafe restore record: {kind} -> {relative}")

            kind_matches = (
                (kind == "kb_manifest" and relative == "kb.yaml")
                or (kind == "content" and relative.lower().startswith("content/"))
                or (kind == "external" and relative.lower().startswith("external/"))
            )
            if not kind_matches or relative in seen:
                raise RuntimeError(
                    f"BLOCKER: duplicate or mismatched restore record: {kind} -> {relative}"
                )
            seen[relative] = True
            expected_hash = str(file_entry.get("sha256", "")).lower()
            if not re.match(r"^[0-9a-f]{64}$", expected_hash):
                raise RuntimeError(f"BLOCKER: invalid expected hash for restore record: {relative}")
            source = get_canonical_path(os.path.join(bundle_full, relative.replace("/", os.sep)))
            if not test_path_inside_root(source, bundle_full) or not os.path.isfile(source):
                raise RuntimeError(f"BLOCKER: restore source is missing or escaping: {relative}")
            records.append(
                {
                    "kind": kind,
                    "portable_path": relative,
                    "source": source,
                    "sha256": expected_hash,
                }
            )

        if "kb.yaml" not in seen:
            raise RuntimeError("BLOCKER: restore manifest does not contain kb.yaml")
        if (
            metadata.get("schema") != "portable-kb-backup-manifest"
            or metadata.get("schema_version") != 1
            or not metadata.get("completeness", {}).get("complete")
        ):
            raise RuntimeError("BLOCKER: pinned restore manifest is not a complete supported backup")

        actual_restore_files: dict[str, bool] = {}
        for f_path in get_safe_tree_files(bundle_full, "portable bundle"):
            rel = get_normalized_relative_path(bundle_full, f_path)
            if (
                rel == "kb.yaml"
                or rel.lower().startswith("content/")
                or rel.lower().startswith("external/")
            ):
                actual_restore_files[rel] = True

        for rel in actual_restore_files.keys():
            if rel not in seen:
                raise RuntimeError(f"BLOCKER: pinned manifest omits restore file: {rel}")
        for rel in seen.keys():
            if rel not in actual_restore_files:
                raise RuntimeError(f"BLOCKER: pinned manifest restore file is missing: {rel}")

        for rec in records:
            if get_sha256(rec["source"]) != rec["sha256"]:
                raise RuntimeError(
                    f"BLOCKER: pinned manifest hash mismatch: {rec['portable_path']}"
                )
        if get_sha256(manifest_path) != manifest_hash:
            raise RuntimeError("BLOCKER: backup manifest changed while binding restore files")

        plan = {
            "bundle": bundle_full,
            "destination": dest_full,
            "mode": mode,
            "source_members": ["kb.yaml", "content", "external"],
            "file_count": len(records),
            "manifest_sha256": manifest_hash,
        }

        if not execute:
            return 0, Envelope(
                command="restore",
                status="plan",
                root=dest_full,
                data=plan,
                diagnostics=[],
            )

        if os.path.exists(dest_full):
            raise RuntimeError(
                "BLOCKER: restore destination appeared after planning; restore never overwrites"
            )

        parent = os.path.dirname(dest_full)
        assert_no_redirecting_reparse_point(parent, "restore destination parent")
        os.makedirs(parent, exist_ok=True)
        assert_no_redirecting_reparse_point(parent, "restore destination parent")

        restore_id = uuid.uuid4().hex
        staging = os.path.join(parent, f".restore-incomplete-{restore_id}")
        os.makedirs(staging, exist_ok=False)
        os.makedirs(os.path.join(staging, "content"), exist_ok=True)
        os.makedirs(os.path.join(staging, "external"), exist_ok=True)
        assert_no_redirecting_reparse_point(staging, "restore staging directory")

        for rec in records:
            assert_no_redirecting_reparse_point(rec["source"], "restore source")
            if get_sha256(rec["source"]) != rec["sha256"]:
                raise RuntimeError(
                    f"FATAL: restore source changed before copy: {rec['portable_path']}"
                )
            target = get_canonical_path(os.path.join(staging, rec["portable_path"].replace("/", os.sep)))
            if not test_path_inside_root(target, staging):
                raise RuntimeError(
                    f"FATAL: restore target escaped staging: {rec['portable_path']}"
                )
            target_parent = os.path.dirname(target)
            os.makedirs(target_parent, exist_ok=True)
            assert_no_redirecting_reparse_point(target_parent, "restore staging path")
            shutil.copyfile(rec["source"], target)
            if get_sha256(rec["source"]) != rec["sha256"]:
                raise RuntimeError(
                    f"FATAL: restore source changed during copy: {rec['portable_path']}"
                )
            if get_sha256(target) != rec["sha256"]:
                raise RuntimeError(
                    f"FATAL: restored file hash differs: {rec['portable_path']}"
                )

        audit_code, audit_env = audit_command(staging, profile="legacy")
        if audit_code != 0:
            issues_str = " ".join(
                [f"{i.get('code')}: {i.get('message')}" for i in audit_env.data.get("issues", [])]
            )
            raise RuntimeError(f"FATAL: restored knowledge base did not pass audit: {issues_str}")

        for rec in records:
            target = get_canonical_path(os.path.join(staging, rec["portable_path"].replace("/", os.sep)))
            if (
                get_sha256(rec["source"]) != rec["sha256"]
                or get_sha256(target) != rec["sha256"]
            ):
                raise RuntimeError(
                    f"FATAL: restore source or staging changed before publication: {rec['portable_path']}"
                )

        if get_sha256(manifest_path) != manifest_hash:
            raise RuntimeError("FATAL: backup manifest changed before publication")

        get_safe_tree_files(staging, "restore staging tree")
        assert_no_redirecting_reparse_point(parent, "restore destination parent")
        if os.path.exists(dest_full):
            raise RuntimeError(
                "BLOCKER: restore destination appeared before publication; restore never overwrites"
            )

        try:
            publish_dir_fail_if_exists(staging, dest_full)
        except FileExistsError:
            raise RuntimeError(
                "BLOCKER: restore destination appeared before publication; restore never overwrites"
            )

        return 0, Envelope(
            command="restore",
            status="restored",
            root=dest_full,
            data=plan,
            diagnostics=[],
        )

    except Exception as exc:
        msg = str(exc)
        code = 3 if msg.startswith("FATAL:") else 2
        data_err: dict[str, Any] = {
            "message": msg,
        }
        if staging and os.path.exists(staging):
            data_err["incomplete_restore"] = staging

        diag_code = "FATAL_ERROR" if code == 3 else "BLOCKER_ERROR"
        return code, Envelope(
            command="restore",
            status="blocked",
            root=dest_full,
            data=data_err,
            diagnostics=[
                Diagnostic(
                    code=diag_code,
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message=msg,
                )
            ],
        )
