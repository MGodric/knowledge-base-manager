"""CLI argument parsing and routing for kb.py."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .model import Diagnostic, Envelope
from .paths import resolve_root
from .runtime_dependencies import ensure_runtime_dependencies


_THIRD_PARTY_DEPENDENCIES = {
    "yaml": "PyYAML",
    "markdown_it": "markdown-it-py",
    "mdit_py_plugins": "mdit-py-plugins",
    "mdurl": "mdurl",
}


def dependency_missing_envelope(command: str, root: str | None, error: ImportError) -> Envelope | None:
    """Translate only known third-party import failures into an actionable envelope."""
    module = (error.name or "").split(".", 1)[0]
    package = _THIRD_PARTY_DEPENDENCIES.get(module)
    if package is None:
        return None
    return Envelope(
        command=command,
        status="failed",
        root=root,
        data=None,
        diagnostics=[
            Diagnostic(
                code="DEPENDENCY_MISSING",
                severity="error",
                file=None,
                span=None,
                target=package,
                message=(
                    f"{package} is required from bundled vendor packages; please re-download "
                    f"or reinstall the complete Skill distribution package ({sys.executable}). No output directory was created."
                ),
            )
        ],
    )


def format_text_output(envelope: Envelope) -> str:
    lines: list[str] = []
    lines.append(f"Command: {envelope.command} (Status: {envelope.status})")
    if envelope.root:
        lines.append(f"Root: {envelope.root}")

    data = envelope.data
    if data:
        if envelope.command == "resolve":
            lines.append(f"Resolved root: {data.get('resolved_root')}")
            lines.append(f"Exists: {data.get('exists')}")
            lines.append(f"Candidates: {data.get('candidates')}")
            lines.append(f"Reason: {data.get('reason')}")
        elif envelope.command == "inspect":
            if "items" in data:
                lines.append(f"Total: {data.get('total')}, Offset: {data.get('offset')}, Limit: {data.get('limit')}")
                for item in data.get("items", []):
                    lines.append(f"- [{item.get('id') or 'NO-ID'}] {item.get('path')} ({item.get('title')}) [{item.get('status')}]")
            elif "page" in data:
                p = data["page"]
                lines.append(f"Page: {p.get('path')} ({p.get('title')})")
                lines.append(f"ID: {p.get('id')}, Type: {p.get('type')}, Status: {p.get('status')}")
                if data.get("sections"):
                    lines.append("Sections:")
                    for s in data["sections"]:
                        lines.append(f"  [{s.get('key')}] {' > '.join(s.get('heading_path', []))} (L{s.get('span', {}).get('start_line')}-{s.get('span', {}).get('end_line')})")
                if data.get("relations"):
                    lines.append("Relations:")
                    for r in data["relations"]:
                        lines.append(f"  - {r.get('kind')}: {r.get('from', {}).get('locator')} -> {r.get('to', {}).get('locator')}")
                if data.get("sources"):
                    lines.append("Sources:")
                    for src in data["sources"]:
                        lines.append(f"  - [{src.get('id')}] {src.get('raw_text')}")
        elif envelope.command == "search":
            lines.append(f"Total matching pages: {data.get('total')}")
            for item in data.get("items", []):
                p = item["page"]
                lines.append(f"\nPage: {p.get('path')} ({p.get('title')}) - Matched queries: {item.get('matched_queries')}")
                for h in item.get("hits", []):
                    lines.append(f"  Hit (Line {h.get('span', {}).get('start_line')}): {h.get('snippet')}")
        elif envelope.command == "read":
            lines.append(f"Path: {data.get('path')} (Truncated: {data.get('truncated')}, Content hash: {data.get('content_hash')})")
            lines.append("--- Content ---")
            lines.append(data.get("text", ""))
        elif envelope.command == "audit":
            lines.append(f"Knowledge base audit: {data.get('root')}")
            lines.append(f"Errors: {data.get('errors')}  Warnings: {data.get('warnings')}")
            for iss in data.get("issues", []):
                loc = f" [{iss.get('file')}]" if iss.get("file") else ""
                tgt = f" -> {iss.get('target')}" if iss.get("target") else ""
                lines.append(f"[{iss.get('severity', '').upper()}] {iss.get('code')}{loc}{tgt} - {iss.get('message')}")
        elif envelope.command == "backup":
            lines.append(f"Backup status: {envelope.status}")
            if "message" in data:
                lines.append(f"Message: {data.get('message')}")
            if data.get("plan"):
                plan = data["plan"]
                lines.append(f"Plan digest: {plan.get('plan_digest')}")
                if "totals" in plan:
                    t = plan["totals"]
                    lines.append(
                        f"Files: {t.get('all_source_files')} (manifest: {t.get('kb_manifest_files')}, content: {t.get('content_files')}, external: {t.get('external_files')})"
                    )
                if plan.get("files"):
                    lines.append("Source files:")
                    for f_rec in plan["files"]:
                        kind = f_rec.get("kind", "")
                        src = f_rec.get("source_path", "")
                        port = f_rec.get("portable_path", "")
                        extra = ""
                        if kind == "external":
                            extra = f" (project: {f_rec.get('project_id')}, source: {f_rec.get('project_relative_source')})"
                        lines.append(f"  - [{kind}] {src} -> {port}{extra}")
                if plan.get("ignored_legacy_paths"):
                    lines.append("Ignored legacy paths:")
                    for ign in plan["ignored_legacy_paths"]:
                        lines.append(f"  - {ign.get('path')}: {ign.get('reason')}")
            if data.get("change_summary"):
                lines.append("Changes:")
                for c in data["change_summary"]:
                    lines.append(f"  - {c}")
        elif envelope.command == "verify-backup":
            lines.append(f"Verification status: {envelope.status}")
            lines.append(f"Bundle: {data.get('bundle')}")
            lines.append(f"Errors: {data.get('errors')}")
            if data.get("issues"):
                lines.append("Issues:")
                for iss in data["issues"]:
                    lines.append(f"  - {iss}")
        elif envelope.command == "restore":
            lines.append(f"Restore status: {envelope.status}")
            if "message" in data:
                lines.append(f"Message: {data.get('message')}")
            if "bundle" in data:
                lines.append(f"Bundle: {data.get('bundle')}")
            if "destination" in data:
                lines.append(f"Destination: {data.get('destination')}")
            if "file_count" in data:
                lines.append(f"Files restored: {data.get('file_count')}")
        elif envelope.command == "build-static":
            lines.append(f"Build static status: {envelope.status}")
            if "destination" in data:
                lines.append(f"Destination: {data.get('destination')}")
            if "entry_page" in data:
                lines.append(f"Entry page: {data.get('entry_page')}")
            lines.append(
                f"Pages generated: {data.get('generated')}, skipped: {data.get('skipped')}, removed: {data.get('removed')}"
            )
            lines.append(
                f"KaTeX assets generated: {data.get('assets_generated')}, skipped: {data.get('assets_skipped')}"
            )
            lines.append(
                f"Graph assets generated: {data.get('graph_assets_generated')}, skipped: {data.get('graph_assets_skipped')}"
            )

    if envelope.diagnostics:
        lines.append("\nDiagnostics:")
        for d in envelope.diagnostics:
            f_str = f" [{d.file}]" if d.file else ""
            t_str = f" -> {d.target}" if d.target else ""
            lines.append(f"[{d.severity.upper()}] {d.code}{f_str}{t_str}: {d.message}")

    return "\n".join(lines)


class KbArgumentParser(argparse.ArgumentParser):
    _current_argv: list[str] | None = None
    _cmd_name: str = "kb"

    def error(self, message: str) -> None:
        raw_argv = getattr(self, "_current_argv", None) or sys.argv[1:]
        is_json = False
        for i, a in enumerate(raw_argv):
            if a == "--format" and i + 1 < len(raw_argv) and raw_argv[i + 1] == "json":
                is_json = True
            elif a.startswith("--format=") and a.split("=", 1)[1] == "json":
                is_json = True

        if is_json:
            cmd = getattr(self, "_cmd_name", "kb")
            envelope = Envelope(
                command=cmd,
                status="invalid",
                root=None,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target=None,
                        message=message,
                    )
                ],
            )
            print(json.dumps(envelope.to_dict(), ensure_ascii=False))
            sys.exit(4)
        super().error(message)


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    fmt_parent = argparse.ArgumentParser(add_help=False)
    fmt_parent.add_argument(
        "--format",
        choices=["text", "json"],
        default=argparse.SUPPRESS,
        help="Output format (default: text)",
    )

    parser = KbArgumentParser(
        prog="kb",
        parents=[fmt_parent],
        description="Knowledge base manager unified Python CLI toolset.",
    )
    parser._cmd_name = "kb"
    parser._current_argv = argv

    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.parser_class = KbArgumentParser

    # 1. resolve
    resolve_parser = subparsers.add_parser(
        "resolve", parents=[fmt_parent], help="Resolve knowledge base root"
    )
    resolve_parser._cmd_name = "resolve"
    resolve_parser._current_argv = argv
    resolve_parser.add_argument("--requested", required=True, help="Requested path or bare name")
    resolve_parser.add_argument("--project-root", default=None, help="Project root (default: cwd)")
    resolve_parser.add_argument(
        "--source-root", action="append", default=[], help="Source root to search (repeatable)"
    )
    resolve_parser.add_argument(
        "--search-depth", type=int, default=2, help="Directory search depth (0-8, default: 2)"
    )
    resolve_parser.add_argument(
        "--allow-missing", action="store_true", help="Allow missing exact path resolution"
    )

    # 2. inspect
    inspect_parser = subparsers.add_parser(
        "inspect", parents=[fmt_parent], help="Inspect pages, sections, relations, sources"
    )
    inspect_parser._cmd_name = "inspect"
    inspect_parser._current_argv = argv
    inspect_parser.add_argument("--root", required=True, help="Knowledge base root path")
    inspect_parser.add_argument("--path", default=None, help="Content-relative path of single page")
    inspect_parser.add_argument("--scope", default=None, help="Scope path prefix")
    inspect_parser.add_argument("--type", default=None, help="Filter by page type")
    inspect_parser.add_argument("--status", default=None, help="Filter by page status")
    inspect_parser.add_argument("--include-archive", action="store_true", help="Include archive pages")
    inspect_parser.add_argument(
        "--include",
        default=None,
        help="Comma-separated sections,relations,sources for single page inspect",
    )
    inspect_parser.add_argument("--limit", type=int, default=None, help="Page limit (default: 50)")
    inspect_parser.add_argument("--offset", type=int, default=None, help="Pagination offset (default: 0)")
    inspect_parser.add_argument("--expect-view", default=None, help="Expected view_id for pagination")

    # 3. search
    search_parser = subparsers.add_parser(
        "search", parents=[fmt_parent], help="Search pages by literal phrases"
    )
    search_parser._cmd_name = "search"
    search_parser._current_argv = argv
    search_parser.add_argument("--root", required=True, help="Knowledge base root path")
    search_parser.add_argument(
        "--query", action="append", required=True, help="Search query phrase (repeatable)"
    )
    search_parser.add_argument(
        "--match", choices=["any", "all"], default="any", help="Match any or all queries"
    )
    search_parser.add_argument("--scope", default=None, help="Scope path prefix")
    search_parser.add_argument("--type", default=None, help="Filter by page type")
    search_parser.add_argument("--status", default=None, help="Filter by page status")
    search_parser.add_argument("--include-archive", action="store_true", help="Include archive pages")
    search_parser.add_argument("--limit", type=int, default=10, help="Results limit (default: 10)")
    search_parser.add_argument("--offset", type=int, default=0, help="Pagination offset (default: 0)")
    search_parser.add_argument("--hits-per-page", type=int, default=2, help="Max hits per page (default: 2)")
    search_parser.add_argument(
        "--snippet-chars", type=int, default=240, help="Max snippet chars (default: 240)"
    )
    search_parser.add_argument("--expect-view", default=None, help="Expected view_id for pagination")

    # 4. read
    read_parser = subparsers.add_parser(
        "read", parents=[fmt_parent], help="Read page or section content by position"
    )
    read_parser._cmd_name = "read"
    read_parser._current_argv = argv
    read_parser.add_argument("--root", required=True, help="Knowledge base root path")
    read_parser.add_argument("--path", required=True, help="Content-relative page path")
    read_parser.add_argument("--section", default=None, help="Section key (e.g. s1, preamble)")
    read_parser.add_argument("--lines", default=None, help="Line range 'start:end' (1-based, inclusive)")
    read_parser.add_argument("--expect-hash", default=None, help="Expected page content hash")
    read_parser.add_argument(
        "--max-chars", type=int, default=8000, help="Max characters to return (default: 8000)"
    )
    read_parser.add_argument("--offset", type=int, default=0, help="Character offset within selection")

    # 5. audit
    audit_parser = subparsers.add_parser(
        "audit", parents=[fmt_parent], help="Audit knowledge base integrity"
    )
    audit_parser._cmd_name = "audit"
    audit_parser._current_argv = argv
    audit_parser.add_argument("--root", required=True, help="Knowledge base root path")
    audit_parser.add_argument(
        "--profile", choices=["legacy", "write", "default"], default="legacy", help="Audit profile (default: legacy)"
    )
    audit_parser.add_argument(
        "--changed", action="append", default=[], help="Content-relative path of changed file"
    )

    # 6. backup
    backup_parser = subparsers.add_parser(
        "backup", parents=[fmt_parent], help="Plan or execute knowledge base backup"
    )
    backup_parser._cmd_name = "backup"
    backup_parser._current_argv = argv
    backup_parser.add_argument("--root", required=True, help="Knowledge base root path")
    backup_parser.add_argument("--destination", required=True, help="Backup destination directory")
    backup_parser.add_argument(
        "--mode",
        choices=["ReferenceComplete", "ProjectSnapshot"],
        default="ReferenceComplete",
        help="Backup mode (default: ReferenceComplete)",
    )
    backup_parser.add_argument(
        "--ignore-legacy-path",
        action="append",
        default=[],
        help="Ignored legacy path 'path|reason' (repeatable)",
    )
    backup_parser.add_argument(
        "--execute", action="store_true", help="Execute confirmed backup"
    )
    backup_parser.add_argument(
        "--confirmed-plan-digest", default=None, help="Confirmed plan digest required for execution"
    )

    # 7. verify-backup
    verify_parser = subparsers.add_parser(
        "verify-backup", parents=[fmt_parent], help="Verify portable backup bundle"
    )
    verify_parser._cmd_name = "verify-backup"
    verify_parser._current_argv = argv
    verify_parser.add_argument("--bundle", required=True, help="Portable backup bundle directory")

    # 8. restore
    restore_parser = subparsers.add_parser(
        "restore", parents=[fmt_parent], help="Plan or execute portable backup restore"
    )
    restore_parser._cmd_name = "restore"
    restore_parser._current_argv = argv
    restore_parser.add_argument("--bundle", required=True, help="Portable backup bundle directory")
    restore_parser.add_argument("--destination", required=True, help="Restore destination directory")
    restore_parser.add_argument(
        "--mode",
        choices=["Portable", "Relink"],
        default="Portable",
        help="Restore mode (default: Portable)",
    )
    restore_parser.add_argument(
        "--project-root-map", default=None, help="Project root map (for future Relink mode)"
    )
    restore_parser.add_argument(
        "--execute", action="store_true", help="Execute restore"
    )

    # 9. build-static
    build_static_parser = subparsers.add_parser(
        "build-static", parents=[fmt_parent], help="Build local static HTML reading view"
    )
    build_static_parser._cmd_name = "build-static"
    build_static_parser._current_argv = argv
    build_static_parser.add_argument("--root", required=True, help="Knowledge base root path")
    build_static_parser.add_argument(
        "--destination", "--output", dest="destination", required=True, help="Output destination directory"
    )
    build_static_parser.add_argument(
        "--force", action="store_true", help="Force rebuild all pages and rewrite assets"
    )
    build_static_parser.add_argument(
        "--katex-assets-root", default=None, help="Local KaTeX assets directory to copy from"
    )
    build_static_parser.add_argument(
        "--graph-assets-root", default=None, help="Local graph assets directory to copy from"
    )

    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:
        return exc.code

    output_format = getattr(args, "format", "text")
    cmd = args.command

    exit_code = 0
    envelope: Envelope

    try:
        if cmd in ("inspect", "search", "read", "audit", "backup", "verify-backup", "restore", "build-static"):
            ok, dep_envelope = ensure_runtime_dependencies(command=cmd, root=getattr(args, "root", None))
            if not ok and dep_envelope is not None:
                return _output_envelope(dep_envelope, output_format, 3)

        if cmd == "resolve":
            exit_code, envelope = resolve_root(
                requested=args.requested,
                project_root=args.project_root,
                source_roots=args.source_root,
                search_depth=args.search_depth,
                allow_missing=args.allow_missing,
            )
        elif cmd in ("inspect", "search", "read"):
            # Lazy import query modules
            try:
                from .query import inspect_command, read_command, search_command
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, getattr(args, "root", None), ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            if cmd == "inspect":
                inc_list = (
                    [item.strip() for item in args.include.split(",") if item.strip()]
                    if args.include is not None
                    else None
                )
                exit_code, envelope = inspect_command(
                    root=args.root,
                    path=args.path,
                    scope=args.scope,
                    page_type=args.type,
                    status=args.status,
                    include_archive=args.include_archive,
                    include=inc_list,
                    limit=args.limit,
                    offset=args.offset,
                    expect_view=args.expect_view,
                )
            elif cmd == "search":
                exit_code, envelope = search_command(
                    root=args.root,
                    queries=args.query,
                    match_mode=args.match,
                    scope=args.scope,
                    page_type=args.type,
                    status=args.status,
                    include_archive=args.include_archive,
                    limit=args.limit,
                    offset=args.offset,
                    hits_per_page=args.hits_per_page,
                    snippet_chars=args.snippet_chars,
                    expect_view=args.expect_view,
                )
            elif cmd == "read":
                exit_code, envelope = read_command(
                    root=args.root,
                    path=args.path,
                    section_key=args.section,
                    lines_range=args.lines,
                    expect_hash=args.expect_hash,
                    max_chars=args.max_chars,
                    offset=args.offset,
                )
        elif cmd == "audit":
            try:
                from .audit import audit_command
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, getattr(args, "root", None), ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            audit_prof = "legacy" if args.profile == "default" else args.profile
            exit_code, envelope = audit_command(
                root=args.root,
                profile=audit_prof,
                changed=args.changed,
            )
        elif cmd == "backup":
            try:
                from .backup import execute_backup
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, args.root, ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            exit_code, envelope = execute_backup(
                root=args.root,
                destination=args.destination,
                mode=args.mode,
                ignore_legacy_path=args.ignore_legacy_path,
                execute=args.execute,
                confirmed_plan_digest=args.confirmed_plan_digest,
            )
        elif cmd == "verify-backup":
            try:
                from .backup import verify_backup
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, None, ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            exit_code, envelope = verify_backup(
                bundle=args.bundle,
            )
        elif cmd == "restore":
            try:
                from .backup import restore_backup
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, None, ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            exit_code, envelope = restore_backup(
                bundle=args.bundle,
                destination=args.destination,
                mode=args.mode,
                project_root_map=args.project_root_map,
                execute=args.execute,
            )
        elif cmd == "build-static":
            try:
                from .static_build import execute_static_build
            except ImportError as ie:
                envelope = dependency_missing_envelope(cmd, args.root, ie)
                if envelope is None:
                    raise
                return _output_envelope(envelope, output_format, 3)

            exit_code, envelope = execute_static_build(
                root=args.root,
                destination=args.destination,
                force=args.force,
                katex_assets_root=args.katex_assets_root,
                graph_assets_root=args.graph_assets_root,
            )
        else:
            envelope = Envelope(
                command=cmd,
                status="invalid",
                root=None,
                data=None,
                diagnostics=[
                    Diagnostic(
                        code="INVALID_ARGUMENT",
                        severity="error",
                        file=None,
                        span=None,
                        target=cmd,
                        message=f"Unknown command: {cmd}",
                    )
                ],
            )
            exit_code = 4
    except Exception as exc:
        envelope = Envelope(
            command=cmd,
            status="failed",
            root=getattr(args, "root", None),
            data=None,
            diagnostics=[
                Diagnostic(
                    code="RUNTIME_FAILURE",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message=str(exc),
                )
            ],
        )
        exit_code = 3

    return _output_envelope(envelope, output_format, exit_code)


def _output_envelope(envelope: Envelope, output_format: str, exit_code: int) -> int:
    if output_format == "json":
        sys.stdout.write(json.dumps(envelope.to_dict(), ensure_ascii=False, indent=None) + "\n")
    else:
        sys.stdout.write(format_text_output(envelope) + "\n")
    sys.stdout.flush()
    return exit_code
