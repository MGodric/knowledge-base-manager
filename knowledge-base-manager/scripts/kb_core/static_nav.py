"""Static site navigation model extraction, validation, and topological sorting."""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
import hashlib
import html
import json
import os
import re
import tempfile
import urllib.parse
import uuid
from typing import Any

from markdown_it import MarkdownIt

from .paths import get_canonical_path, test_path_inside_root


@dataclass
class StaticNavigationPage:
    source: str
    output: str
    title: str
    type: str
    children: list[str] = field(default_factory=list)
    parents: list[str] = field(default_factory=list)

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __setitem__(self, item: str, value: Any) -> None:
        setattr(self, item, value)

    def get(self, item: str, default: Any = None) -> Any:
        return getattr(self, item, default)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "output": self.output,
            "title": self.title,
            "type": self.type,
            "children": list(self.children),
            "parents": list(self.parents),
        }


@dataclass
class StaticNavigationModel:
    pages: dict[str, StaticNavigationPage]
    digest: str
    entry_source: str

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def to_dict(self) -> dict[str, Any]:
        return {
            "pages": {k: v.to_dict() for k, v in self.pages.items()},
            "digest": self.digest,
            "entry_source": self.entry_source,
        }


def get_static_navigation_href(from_output: str, to_output: str) -> str:
    """Encode filesystem-relative output paths once, including literal #/%/?.

    Equivalent to Get-KbStaticNavigationHref in PowerShell.
    """
    base = os.path.join(tempfile.gettempdir(), "kb-navigation-path-base")
    from_dir = os.path.dirname(os.path.join(base, from_output.replace("/", os.sep)))
    to_path = os.path.join(base, to_output.replace("/", os.sep))
    relative = os.path.relpath(to_path, from_dir).replace("\\", "/")
    return "/".join(urllib.parse.quote(part, safe="~") for part in relative.split("/"))


def get_static_navigation_model(
    markdown_files: list[Any],
    content_root: str,
    entry_source_path: str,
) -> StaticNavigationModel:
    """Read-only navigation model extraction and validation.

    Validates:
    - Children blocks within project/map pages or entrypoint.
    - Local relative target links with no query string and no self-collection.
    - Kahn's algorithm cycle detection (topological sort).
    - SHA-256 digest computation matching PowerShell.
    """
    root = get_canonical_path(content_root)
    entry_full = get_canonical_path(entry_source_path)
    entry = os.path.relpath(entry_full, root).replace("\\", "/")

    pages: dict[str, StaticNavigationPage] = {}
    blocks: dict[str, str] = {}
    md = MarkdownIt("commonmark", {"html": True})

    for file_item in markdown_files:
        if isinstance(file_item, (str, os.PathLike)):
            full_path = get_canonical_path(str(file_item))
            file_name = os.path.basename(full_path)
        elif hasattr(file_item, "FullName"):
            full_path = get_canonical_path(str(file_item.FullName))
            file_name = str(file_item.Name)
        elif hasattr(file_item, "full_path"):
            full_path = get_canonical_path(str(file_item.full_path))
            file_name = os.path.basename(full_path)
        else:
            full_path = get_canonical_path(str(file_item))
            file_name = os.path.basename(full_path)

        source = os.path.relpath(full_path, root).replace("\\", "/")
        with open(full_path, "r", encoding="utf-8") as f:
            text = f.read()

        page_type = ""
        front_match = re.match(
            r"\A---\s*\r?\n(?P<fields>[\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)", text
        )
        if front_match:
            fields = front_match.group("fields")
            type_match = re.search(r"(?m)^type:[ \t]*(?P<val>[^\r\n#]*)", fields)
            if type_match:
                page_type = type_match.group("val").strip().strip("\"'").lower()
            text = text[front_match.end() :]

        token = "kb-nav-" + uuid.uuid4().hex
        marked = re.sub(
            r"(?m)^<!-- kb-nav:children:(start|end) -->\r?$",
            lambda m: f"<!-- {token}:{m.group(1)} -->",
            text,
        )

        rendered_html = md.render(marked) if marked else ""
        title = os.path.splitext(file_name)[0]
        heading_match = re.search(r"(?is)<h1\b[^>]*>(.*?)</h1>", rendered_html)
        if heading_match:
            title = html.unescape(
                re.sub(r"<[^>]+>", "", heading_match.group(1))
            ).strip()

        marker_matches = list(re.finditer(rf"<!-- {token}:(start|end) -->", rendered_html))
        if marker_matches:
            if (
                len(marker_matches) != 2
                or marker_matches[0].group(1) != "start"
                or marker_matches[1].group(1) != "end"
            ):
                raise ValueError(
                    f"BLOCKER: invalid kb-nav children block (duplicate, nested, or unmatched markers): {source}"
                )
            if source != entry and page_type not in ("project", "map"):
                raise ValueError(
                    f"BLOCKER: kb-nav children block requires project/map type: {source}"
                )
            start = marker_matches[0].end()
            end = marker_matches[1].start()
            blocks[source] = rendered_html[start:end]

        output = re.sub(r"(?i)\.md$", ".html", source)
        pages[source] = StaticNavigationPage(
            source=source,
            output=output,
            title=title,
            type=page_type,
            children=[],
            parents=[],
        )

    if entry not in pages:
        raise ValueError("BLOCKER: navigation entrypoint is missing from Markdown files")

    for source, block in list(blocks.items()):
        block_clean = re.sub(r"(?is)<(pre|code)\b[^>]*>.*?</\1>", "", block)
        nested_list_pattern = r"(?is)(<li\b[^>]*>(?:(?!<li\b)[\s\S])*?)<(ul|ol)\b(?:(?!<(ul|ol)\b)[\s\S])*?</\2>"
        while re.search(nested_list_pattern, block_clean):
            block_clean = re.sub(nested_list_pattern, r"\1", block_clean)

        targets: dict[str, bool] = {}
        anchor_matches = re.finditer(
            r'(?is)<a\b[^>]*\bhref\s*=\s*"([^"]*)"[^>]*>(.*?)</a>', block_clean
        )
        for anchor in anchor_matches:
            if re.search(r"(?is)<img\b", anchor.group(2)):
                continue
            href = html.unescape(anchor.group(1))
            path_part = href.split("#", 1)[0]
            if "?" in path_part:
                raise ValueError(f"BLOCKER: query is unsupported in kb-nav link: {source} -> {href}")
            path_part = urllib.parse.unquote(path_part)
            if (
                not path_part.strip()
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", path_part)
                or path_part.startswith("/")
                or path_part.startswith("\\")
                or os.path.isabs(path_part)
            ):
                raise ValueError(
                    f"BLOCKER: kb-nav link must target a relative local Markdown file: {source} -> {href}"
                )

            source_parent_dir = os.path.dirname(os.path.join(root, source.replace("/", os.sep)))
            candidate = os.path.normpath(os.path.join(source_parent_dir, path_part.replace("/", os.sep)))
            if not test_path_inside_root(candidate, root) or candidate == root:
                raise ValueError(f"BLOCKER: kb-nav link escapes content root: {source} -> {href}")

            target = os.path.relpath(candidate, root).replace("\\", "/")
            if target not in pages:
                raise ValueError(f"BLOCKER: kb-nav target is not an existing Markdown file: {source} -> {href}")
            if target == source:
                raise ValueError(f"BLOCKER: self collection in kb-nav: {source}")
            if source == entry and pages[target].type not in ("project", "map"):
                raise ValueError(f"BLOCKER: entrypoint may collect only project/map pages: {target}")

            targets[target] = True

        pages[source].children = sorted(targets.keys())
        for target in pages[source].children:
            pages[target].parents.append(source)

    # Kahn's topological sort algorithm checks every component for cycles
    indegree: dict[str, int] = {}
    queue: collections.deque[str] = collections.deque()
    for source in pages:
        pages[source].parents = sorted(pages[source].parents)
        indegree[source] = len(pages[source].parents)
        if indegree[source] == 0:
            queue.append(source)

    visited = 0
    while queue:
        s = queue.popleft()
        visited += 1
        for target in pages[s].children:
            indegree[target] -= 1
            if indegree[target] == 0:
                queue.append(target)

    if visited != len(pages):
        raise ValueError("BLOCKER: cycle in kb-nav collections")

    records = [
        {
            "source": pages[s].source,
            "output": pages[s].output,
            "title": pages[s].title,
            "type": pages[s].type,
            "children": list(pages[s].children),
        }
        for s in sorted(pages.keys())
    ]
    serialized = json.dumps({"entry": entry, "pages": records}, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(serialized.encode("utf-8")).hexdigest().lower()

    return StaticNavigationModel(pages=pages, digest=digest, entry_source=entry)
