"""Path canonicalization, safety, reparse point detection, and root resolution."""

from __future__ import annotations

import collections
import ctypes
import os
import re
import sys
import urllib.parse
from typing import Any

from .model import Diagnostic, Envelope

IS_WINDOWS = sys.platform == "win32"

if IS_WINDOWS:
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

    FILE_READ_ATTRIBUTES = 0x0080
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    FILE_SHARE_DELETE = 4
    OPEN_EXISTING = 3
    FILE_FLAG_OPEN_REPARSE_POINT = 0x00200000
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_ATTRIBUTE_REPARSE_POINT = 0x00000400

    class FileAttributeTagInfo(ctypes.Structure):
        _fields_ = [
            ("FileAttributes", wintypes.DWORD),
            ("ReparseTag", wintypes.DWORD),
        ]

    CreateFileW = kernel32.CreateFileW
    CreateFileW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.HANDLE,
    ]
    CreateFileW.restype = wintypes.HANDLE

    GetFileInformationByHandleEx = kernel32.GetFileInformationByHandleEx
    GetFileInformationByHandleEx.argtypes = [
        wintypes.HANDLE,
        ctypes.c_int,
        ctypes.c_void_p,
        wintypes.DWORD,
    ]
    GetFileInformationByHandleEx.restype = wintypes.BOOL

    CloseHandle = kernel32.CloseHandle
    CloseHandle.argtypes = [wintypes.HANDLE]
    CloseHandle.restype = wintypes.BOOL

    INVALID_HANDLE_VALUE = wintypes.HANDLE(-1).value


def is_redirecting_reparse_point(path: str) -> bool:
    """Check if the given path is a redirecting reparse point (junction, symlink, mount point).

    Cloud placeholders and hydration points are allowed (bit 29 not set).
    """
    if not os.path.exists(path) and not os.path.islink(path):
        return False

    if IS_WINDOWS:
        try:
            attrs = kernel32.GetFileAttributesW(path)
            if attrs == 0xFFFFFFFF or not (attrs & FILE_ATTRIBUTE_REPARSE_POINT):
                return False

            handle = CreateFileW(
                path,
                0,
                FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                None,
                OPEN_EXISTING,
                FILE_FLAG_OPEN_REPARSE_POINT | FILE_FLAG_BACKUP_SEMANTICS,
                None,
            )
            if handle == INVALID_HANDLE_VALUE:
                return False
            try:
                info = FileAttributeTagInfo()
                if GetFileInformationByHandleEx(
                    handle, 9, ctypes.byref(info), ctypes.sizeof(info)
                ):
                    # Bit 29 indicates name surrogate (junction, symlink, mount point)
                    return bool(info.ReparseTag & 0x20000000)
                return False
            finally:
                CloseHandle(handle)
        except Exception:
            return False
    else:
        return os.path.islink(path)


def assert_no_redirecting_reparse_point(path: str, label: str = "path") -> None:
    """Traverse ancestors and path itself to ensure no redirecting reparse points exist."""
    full = os.path.abspath(path)
    cursor = full
    while cursor and not os.path.exists(cursor):
        parent = os.path.dirname(cursor)
        if not parent or parent == cursor:
            break
        cursor = parent

    while cursor:
        if os.path.exists(cursor) or os.path.islink(cursor):
            if is_redirecting_reparse_point(cursor):
                raise RuntimeError(
                    f"BLOCKER: {label} contains a junction or symbolic link: {cursor}"
                )
        parent = os.path.dirname(cursor)
        if not parent or parent == cursor:
            break
        cursor = parent


def get_canonical_path(path: str, base_path: str | None = None) -> str:
    """Return normalized absolute path without trailing slashes."""
    if not path:
        return ""
    if base_path and not os.path.isabs(path):
        combined = os.path.join(base_path, path)
    else:
        combined = path
    return os.path.normpath(os.path.abspath(combined)).rstrip("\\/")


def test_path_inside_root(candidate: str, base_root: str) -> bool:
    """Return True if candidate is equal to or inside base_root."""
    cand_full = os.path.normcase(get_canonical_path(candidate))
    base_full = os.path.normcase(get_canonical_path(base_root))
    if cand_full == base_full:
        return True
    prefix = base_full + os.sep
    return cand_full.startswith(prefix)


def get_normalized_relative_path(base_path: str, target_path: str) -> str:
    """Return relative path with forward slashes."""
    base = get_canonical_path(base_path)
    target = get_canonical_path(target_path)
    rel = os.path.relpath(target, base)
    return rel.replace("\\", "/")


def is_explicit_relative_path(path: str) -> bool:
    """Return True if path is a relative path that does not attempt to be absolute."""
    if not path or not isinstance(path, str):
        return False
    clean = path.strip()
    if not clean:
        return False
    if clean.startswith(("/", "\\")):
        return False
    if bool(re.match(r"^[A-Za-z]:", clean)):
        return False
    if os.path.isabs(clean):
        return False
    return True


def resolve_contained_path(base_root: str, rel_path: str) -> tuple[str | None, str | None]:
    """Resolve rel_path inside base_root.

    Returns (canonical_path, None) if safe and contained, or (None, error_code) if not.
    """
    if not is_explicit_relative_path(rel_path):
        return None, "PATH_OUTSIDE_SCOPE"
    base_canon = get_canonical_path(base_root)
    combined = os.path.normpath(os.path.join(base_canon, rel_path.replace("/", os.sep)))
    if not test_path_inside_root(combined, base_canon):
        return None, "PATH_OUTSIDE_SCOPE"
    return combined, None


def resolve_root(
    requested: str,
    project_root: str | None = None,
    source_roots: list[str] | None = None,
    search_depth: int = 2,
    allow_missing: bool = False,
) -> tuple[int, Envelope]:
    """Execute root resolution according to the kb-resolve-root contract."""
    requested_clean = (requested or "").strip()
    if not requested_clean:
        return 4, Envelope(
            command="resolve",
            status="invalid",
            root=None,
            data={
                "resolved_root": None,
                "exists": False,
                "candidates": [],
                "searched_roots": [],
                "reason": "RequestedPath is empty.",
            },
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message="RequestedPath is empty.",
                )
            ],
        )

    base_proj = project_root if project_root else os.getcwd()
    project = get_canonical_path(base_proj)

    if not os.path.isdir(project):
        return 4, Envelope(
            command="resolve",
            status="invalid",
            root=None,
            data={
                "resolved_root": None,
                "exists": False,
                "candidates": [],
                "searched_roots": [],
                "reason": f"ProjectRoot is not a directory: {project}",
            },
            diagnostics=[
                Diagnostic(
                    code="INVALID_ARGUMENT",
                    severity="error",
                    file=None,
                    span=None,
                    target=project,
                    message=f"ProjectRoot is not a directory: {project}",
                )
            ],
        )

    try:
        assert_no_redirecting_reparse_point(project, "ProjectRoot")
    except Exception as exc:
        return 4, Envelope(
            command="resolve",
            status="invalid",
            root=None,
            data={
                "resolved_root": None,
                "exists": False,
                "candidates": [],
                "searched_roots": [],
                "reason": str(exc),
            },
            diagnostics=[
                Diagnostic(
                    code="PATH_REDIRECTED",
                    severity="error",
                    file=None,
                    span=None,
                    target=project,
                    message=str(exc),
                )
            ],
        )

    is_abs = os.path.isabs(requested_clean) or bool(re.match(r"^[A-Za-z]:[\\/]", requested_clean))
    has_separator = ("\\" in requested_clean) or ("/" in requested_clean)
    is_bare_name = not is_abs and not has_separator

    if not is_bare_name:
        exact = get_canonical_path(requested_clean, project)
        if os.path.isdir(exact):
            try:
                assert_no_redirecting_reparse_point(exact, "requested path")
            except Exception as exc:
                return 4, Envelope(
                    command="resolve",
                    status="invalid",
                    root=None,
                    data={
                        "resolved_root": None,
                        "exists": False,
                        "candidates": [exact],
                        "searched_roots": [],
                        "reason": str(exc),
                    },
                    diagnostics=[
                        Diagnostic(
                            code="PATH_REDIRECTED",
                            severity="error",
                            file=None,
                            span=None,
                            target=exact,
                            message=str(exc),
                        )
                    ],
                )
            return 0, Envelope(
                command="resolve",
                status="resolved",
                root=exact,
                data={
                    "resolved_root": exact,
                    "exists": True,
                    "candidates": [exact],
                    "searched_roots": [],
                    "reason": "Resolved exact path.",
                },
            )

        if os.path.exists(exact):
            return 4, Envelope(
                command="resolve",
                status="invalid",
                root=None,
                data={
                    "resolved_root": None,
                    "exists": False,
                    "candidates": [exact],
                    "searched_roots": [],
                    "reason": "The exact target exists but is not a directory.",
                },
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target=exact,
                        message="The exact target exists but is not a directory.",
                    )
                ],
            )

        if allow_missing:
            try:
                assert_no_redirecting_reparse_point(exact, "requested path")
            except Exception as exc:
                return 4, Envelope(
                    command="resolve",
                    status="invalid",
                    root=None,
                    data={
                        "resolved_root": None,
                        "exists": False,
                        "candidates": [exact],
                        "searched_roots": [],
                        "reason": str(exc),
                    },
                    diagnostics=[
                        Diagnostic(
                            code="PATH_REDIRECTED",
                            severity="error",
                            file=None,
                            span=None,
                            target=exact,
                            message=str(exc),
                        )
                    ],
                )
            return 0, Envelope(
                command="resolve",
                status="resolved_missing",
                root=exact,
                data={
                    "resolved_root": exact,
                    "exists": False,
                    "candidates": [exact],
                    "searched_roots": [],
                    "reason": "Missing exact path resolved; creation still requires authorization.",
                },
            )

        return 3, Envelope(
            command="resolve",
            status="not_found",
            root=None,
            data={
                "resolved_root": None,
                "exists": False,
                "candidates": [exact],
                "searched_roots": [],
                "reason": "The exact path does not exist.",
            },
            diagnostics=[
                Diagnostic(
                    code="TARGET_NOT_FOUND",
                    severity="error",
                    file=None,
                    span=None,
                    target=exact,
                    message="The exact path does not exist.",
                )
            ],
        )

    # Bare name search
    roots_to_search = list(source_roots) if source_roots else [project]
    searched: list[str] = []
    matches: list[str] = []
    visited: set[str] = set()
    match_keys: set[str] = set()

    for root_item in roots_to_search:
        if not (root_item or "").strip():
            continue
        source = get_canonical_path(root_item, project)
        if not os.path.isdir(source):
            continue
        try:
            assert_no_redirecting_reparse_point(source, "SourceRoot")
        except Exception:
            continue

        if source not in searched:
            searched.append(source)

        queue = collections.deque([(source, 0)])
        while queue:
            current, depth = queue.popleft()
            current_key = os.path.normcase(current)
            if current_key in visited:
                continue
            visited.add(current_key)

            current_redirects = is_redirecting_reparse_point(current)
            leaf = os.path.basename(current)
            if (
                not current_redirects
                and leaf.lower() == requested_clean.lower()
                and current_key not in match_keys
            ):
                match_keys.add(current_key)
                matches.append(current)

            if depth >= search_depth:
                continue

            try:
                entries = sorted(os.scandir(current), key=lambda e: e.name)
            except Exception:
                continue

            for entry in entries:
                try:
                    if entry.is_dir(follow_symlinks=False):
                        child_path = get_canonical_path(entry.path)
                        child_key = os.path.normcase(child_path)
                        child_redirects = is_redirecting_reparse_point(child_path)
                        if (
                            not child_redirects
                            and entry.name.lower() == requested_clean.lower()
                            and child_key not in match_keys
                        ):
                            match_keys.add(child_key)
                            matches.append(child_path)
                        if not child_redirects:
                            queue.append((child_path, depth + 1))
                except Exception:
                    continue

    reason = (
        "No exact directory-name match was found in the project source folders; confirm an absolute path before continuing."
        if not matches
        else f"Found {len(matches)} exact directory-name match(es); confirm one absolute path before continuing."
    )

    return 2, Envelope(
        command="resolve",
        status="confirmation_required",
        root=None,
        data={
            "resolved_root": None,
            "exists": len(matches) > 0,
            "candidates": matches,
            "searched_roots": searched,
            "reason": reason,
        },
    )


def split_and_decode_target_path(raw_target: str) -> tuple[str, str, str]:
    """Split raw markdown link target into (decoded_path, query, fragment).

    Splitting order:
    1. Surrounding angle brackets (<...>) are stripped if present.
    2. Fragment ('#') is split first (remains undecoded).
    3. Query ('?') is split second from the remaining path (remains undecoded).
    4. Path is unquoted with urllib.parse.unquote (single pass).
    """
    cleaned = (raw_target or "").strip()
    if cleaned.startswith("<") and cleaned.endswith(">"):
        cleaned = cleaned[1:-1].strip()

    if not cleaned:
        return "", "", ""
    if cleaned.startswith("#"):
        return "", "", cleaned[1:]

    # 1. Split fragment first
    path_query, _, fragment = cleaned.partition("#")

    # 2. Split query second
    path_part, _, query = path_query.partition("?")

    # 3. Single unquote on path_part
    try:
        decoded_path = urllib.parse.unquote(path_part)
    except Exception:
        decoded_path = path_part

    return decoded_path, query, fragment
