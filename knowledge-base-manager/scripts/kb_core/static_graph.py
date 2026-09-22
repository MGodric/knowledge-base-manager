"""Graph and preview data extraction module for static knowledge base reader.

Produces GraphData and PreviewData conforming to proposals/知识库图谱设计与数据接口.md.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field
import hashlib
import html
import json
import os
import re
import urllib.parse
import uuid
from typing import Any

from markdown_it import MarkdownIt

from .paths import get_canonical_path, test_path_inside_root


@dataclass
class SectionInfo:
    node_id: str
    heading_level: int
    ordinal: int
    title: str
    fragment: str
    parent_node_id: str
    owner_page_id: str
    html_content: str


@dataclass
class AnchorResult:
    html: str
    sections: list[SectionInfo]
    diagnostics: list[dict[str, Any]]


@dataclass
class GraphModelResult:
    graph_data: dict[str, Any]
    preview_data: dict[str, Any]
    diagnostics: list[dict[str, Any]]

    @property
    def GraphData(self) -> dict[str, Any]:
        return self.graph_data

    @property
    def PreviewData(self) -> dict[str, Any]:
        return self.preview_data

    @property
    def Diagnostics(self) -> list[dict[str, Any]]:
        return self.diagnostics

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)


def get_page_frontmatter(text: str) -> dict[str, Any]:
    """Parse id, type, status, and tags from YAML frontmatter."""
    result: dict[str, Any] = {
        "id": None,
        "type": None,
        "status": None,
        "tags": [],
    }
    if not text.startswith("---"):
        return result

    front = re.match(r"\A---\s*\r?\n(?P<fields>[\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)", text)
    if not front:
        return result

    fields = front.group("fields")

    id_match = re.search(r"(?m)^id:[ \t]*(?P<val>[^\r\n#]+)", fields)
    if id_match:
        val = id_match.group("val").strip().strip("\"'")
        if val:
            result["id"] = val

    type_match = re.search(r"(?m)^type:[ \t]*(?P<val>[^\r\n#]+)", fields)
    if type_match:
        val = type_match.group("val").strip().strip("\"'").lower()
        if val:
            result["type"] = val

    status_match = re.search(r"(?m)^status:[ \t]*(?P<val>[^\r\n#]+)", fields)
    if status_match:
        val = status_match.group("val").strip().strip("\"'").lower()
        if val:
            result["status"] = val

    inline_tags = re.search(r"(?m)^tags:[ \t]*\[(?P<val>[^\]]*)\]", fields)
    if inline_tags:
        raw_tags = inline_tags.group("val").split(",")
        tag_list = []
        for t in raw_tags:
            clean = t.strip().strip("\"'")
            if clean:
                tag_list.append(clean)
        result["tags"] = tag_list
    else:
        block_tags = re.search(
            r"(?m)^tags:[ \t]*\r?\n(?P<items>(?:[ \t]+-[ \t]+[^\r\n]+\r?\n?)+)", fields
        )
        if block_tags:
            tag_list = []
            for line in block_tags.group("items").splitlines():
                m = re.match(r"^[ \t]+-[ \t]+(?P<val>[^\r\n#]+)", line)
                if m:
                    clean = m.group("val").strip().strip("\"'")
                    if clean:
                        tag_list.append(clean)
            result["tags"] = tag_list

    return result


def update_heading_anchors(
    html_text: str, owner_page_id: str = "", source_path: str = ""
) -> AnchorResult:
    """Mask code blocks, assign unique anchors, build section hierarchy.

    Equivalent to Update-KbHeadingAnchors in PowerShell.
    """
    used_ids: set[str] = set()
    diagnostics: list[dict[str, Any]] = []

    for m in re.finditer(r'(?i)\bid\s*=\s*(?P<q>["\'])(?P<id>[^"\']+)(?P=q)', html_text):
        used_ids.add(m.group("id"))

    code_tokens: list[str] = []
    token_prefix = f"KBCODEBLOCK_{uuid.uuid4().hex}_"

    def mask_code(match: re.Match) -> str:
        idx = len(code_tokens)
        code_tokens.append(match.group(0))
        return f"<!-- {token_prefix}{idx} -->"

    masked_html = re.sub(r"(?is)<(pre|code)\b[^>]*>.*?</\1>", mask_code, html_text)

    heading_regex = r"(?is)<h(?P<level>[2-6])(?P<attrs>\b[^>]*)>(?P<content>.*?)</h(?P=level)>"
    heading_matches = list(re.finditer(heading_regex, masked_html))

    h24_to_assign: list[int] = []
    h56_to_assign: list[int] = []
    heading_ids: list[str] = [""] * len(heading_matches)
    seen_heading_ids: set[str] = set()

    for i, m in enumerate(heading_matches):
        lvl = int(m.group("level"))
        attrs = m.group("attrs")
        id_match = re.search(r'(?i)\bid\s*=\s*(?P<q>["\'])(?P<id>[^"\']+)(?P=q)', attrs)
        if id_match:
            existing_id = id_match.group("id")
            heading_ids[i] = existing_id
            if existing_id in seen_heading_ids:
                diagnostics.append(
                    {
                        "code": "duplicate_heading_id",
                        "severity": "warning",
                        "source_path": source_path,
                        "link_ordinal": None,
                        "message": f"Duplicate heading id '{existing_id}' in {source_path}",
                    }
                )
            else:
                seen_heading_ids.add(existing_id)
        else:
            if lvl <= 4:
                h24_to_assign.append(i)
            else:
                h56_to_assign.append(i)

    next_num = 1
    for idx in h24_to_assign:
        while f"kb-heading-{next_num}" in used_ids:
            next_num += 1
        hid = f"kb-heading-{next_num}"
        used_ids.add(hid)
        heading_ids[idx] = hid

    for idx in h56_to_assign:
        while f"kb-heading-{next_num}" in used_ids:
            next_num += 1
        hid = f"kb-heading-{next_num}"
        used_ids.add(hid)
        heading_ids[idx] = hid

    sections: list[SectionInfo] = []
    sb: list[str] = []
    last_index = 0
    ancestors: list[dict[str, Any]] = []

    for i, m in enumerate(heading_matches):
        sb.append(masked_html[last_index : m.start()])
        last_index = m.end()

        lvl = int(m.group("level"))
        attrs = m.group("attrs")
        content = m.group("content")
        final_id = heading_ids[i]

        if re.search(r"(?i)\bid\s*=\s*", attrs):
            new_attrs = attrs
        else:
            new_attrs = f' id="{final_id}"{attrs}'

        sb.append(f"<h{lvl}{new_attrs}>{content}</h{lvl}>")

        plain_title = html.unescape(re.sub(r"<[^>]+>", "", content)).strip()
        sec_node_id = (
            f"section:{owner_page_id}#{final_id}" if owner_page_id else f"section:#{final_id}"
        )

        while ancestors and ancestors[-1]["level"] >= lvl:
            ancestors.pop()
        parent_node_id = ancestors[-1]["node_id"] if ancestors else owner_page_id
        ancestors.append({"level": lvl, "node_id": sec_node_id})

        content_start = m.end()
        content_end = (
            heading_matches[i + 1].start() if i + 1 < len(heading_matches) else len(masked_html)
        )
        sec_html_slice = masked_html[content_start : max(content_start, content_end)]

        sections.append(
            SectionInfo(
                node_id=sec_node_id,
                heading_level=lvl,
                ordinal=i,
                title=plain_title,
                fragment=final_id,
                parent_node_id=parent_node_id,
                owner_page_id=owner_page_id,
                html_content=sec_html_slice,
            )
        )

    sb.append(masked_html[last_index:])
    reconstructed = "".join(sb)

    for i, code_val in enumerate(code_tokens):
        reconstructed = reconstructed.replace(f"<!-- {token_prefix}{i} -->", code_val)

    return AnchorResult(
        html=reconstructed,
        sections=sections,
        diagnostics=diagnostics,
    )


def get_text_excerpt(html_text: str, max_length: int = 600) -> dict[str, Any]:
    """Excerpt extraction for preview modals.

    Equivalent to Get-KbTextExcerpt in PowerShell.
    """
    clean = re.sub(r"(?is)<(h[1-6]|pre|script|style)\b[^>]*>.*?</\1>", " ", html_text)
    clean = re.sub(r"(?is)<!-- kb-nav:children:start -->.*?<!-- kb-nav:children:end -->", " ", clean)

    block_match = re.search(r"(?is)<(p|ul|ol|blockquote|table)\b[^>]*>.*?</\1>", clean)
    candidate_html = block_match.group(0) if block_match else clean

    clean_text = re.sub(r"(?is)<br\s*/?>", " ", candidate_html)
    clean_text = re.sub(r"(?is)</(p|li|tr|div|blockquote|td|th)>", " ", clean_text)
    clean_text = re.sub(r"<[^>]+>", " ", clean_text)
    decoded = html.unescape(clean_text)
    text = re.sub(r"\s+", " ", decoded).strip()

    if text:
        truncated = False
        if len(text) > max_length:
            text = text[:max_length]
            truncated = True
        return {
            "mode": "excerpt",
            "text": text,
            "truncated": truncated,
        }

    return {
        "mode": "unavailable",
        "text": "",
        "truncated": False,
    }


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest().lower()


def get_graph_model(
    content_root: str,
    navigation: Any,
    validated_pages: list[Any] | None = None,
    markdown_files: list[Any] | None = None,
) -> GraphModelResult:
    """Builds GraphData (nodes, edges, graph_digest) and PreviewData (previews, preview_digest).

    Equivalent to Get-KbGraphModel in PowerShell.
    """
    root = get_canonical_path(content_root)
    entry_source = (
        navigation.entry_source
        if hasattr(navigation, "entry_source")
        else navigation["entry_source"]
    )
    entrypoint = entry_source.replace("\\", "/")

    pages_list: list[dict[str, Any]] = []
    formal_ids: dict[str, str] = {}

    nav_pages = (
        navigation.pages
        if hasattr(navigation, "pages")
        else navigation["pages"]
    )

    if validated_pages is not None and len(validated_pages) > 0:
        for vp in validated_pages:
            source = str(vp.get("source", "") if isinstance(vp, dict) else getattr(vp, "source", "") or getattr(vp, "Source", ""))
            if source.lower().startswith("inbox/") or source.lower().startswith("archive/"):
                continue
            raw = str(vp.get("raw_markdown", "") if isinstance(vp, dict) else getattr(vp, "raw_markdown", "") or getattr(vp, "RawMarkdown", "") or "")
            fm = vp.get("frontmatter") if isinstance(vp, dict) else getattr(vp, "frontmatter", None) or getattr(vp, "Frontmatter", None)
            if not fm:
                fm = get_page_frontmatter(raw)
            title = vp.get("title") if isinstance(vp, dict) else getattr(vp, "title", None) or getattr(vp, "Title", None)
            if not title:
                if source in nav_pages:
                    np = nav_pages[source]
                    title = np.title if hasattr(np, "title") else np["title"]
                else:
                    title = os.path.splitext(os.path.basename(source))[0]
            if source in nav_pages:
                np = nav_pages[source]
                output = np.output if hasattr(np, "output") else np["output"]
            else:
                output = re.sub(r"(?i)\.md$", ".html", source)
            prerendered_html = vp.get("html") if isinstance(vp, dict) else getattr(vp, "html", None) or getattr(vp, "Html", None)

            pages_list.append(
                {
                    "source": source,
                    "output": output,
                    "title": title,
                    "raw_markdown": raw,
                    "frontmatter": fm,
                    "prerendered_html": prerendered_html,
                }
            )
    elif markdown_files is not None and len(markdown_files) > 0:
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
            if source.lower().startswith("inbox/") or source.lower().startswith("archive/"):
                continue
            with open(full_path, "r", encoding="utf-8") as f:
                raw = f.read()
            fm = get_page_frontmatter(raw)
            if source in nav_pages:
                np = nav_pages[source]
                title = np.title if hasattr(np, "title") else np["title"]
                output = np.output if hasattr(np, "output") else np["output"]
            else:
                title = os.path.splitext(file_name)[0]
                output = re.sub(r"(?i)\.md$", ".html", source)

            pages_list.append(
                {
                    "source": source,
                    "output": output,
                    "title": title,
                    "raw_markdown": raw,
                    "frontmatter": fm,
                    "prerendered_html": None,
                }
            )
    else:
        raise ValueError("BLOCKER: get_graph_model requires either validated_pages or markdown_files")

    page_node_ids: dict[str, str] = {}
    for p in pages_list:
        kb_id = p["frontmatter"].get("id")
        if kb_id and kb_id.strip():
            kb_id_clean = kb_id.strip()
            kb_id_lower = kb_id_clean.lower()
            if kb_id_lower in formal_ids:
                raise ValueError(
                    f"BLOCKER: duplicate formal id '{kb_id_clean}' in '{formal_ids[kb_id_lower]}' and '{p['source']}'"
                )
            formal_ids[kb_id_lower] = p["source"]
            page_node_ids[p["source"]] = f"page:id:{kb_id_clean}"
        else:
            page_node_ids[p["source"]] = f"page:path:{p['source']}"

    if entrypoint not in page_node_ids:
        raise ValueError(f"BLOCKER: entrypoint '{entrypoint}' not found in validated pages")

    entry_id = page_node_ids[entrypoint]

    nodes: dict[str, Any] = {}
    edges: dict[str, Any] = {}
    preview_records: dict[str, Any] = {}
    diagnostics: list[dict[str, Any]] = []
    page_fragments: dict[str, set[str]] = {}

    rendered_page_map: dict[str, Any] = {}
    md_renderer = MarkdownIt("commonmark", {"html": True})
    md_renderer.validateLink = lambda url: not bool(
        re.match(r"^(javascript|vbscript):", url.strip().lower())
    )

    for p in pages_list:
        source = p["source"]
        page_node_id = page_node_ids[source]
        fm = p["frontmatter"]

        if p["prerendered_html"] is not None:
            raw_html = p["prerendered_html"]
        else:
            text = p["raw_markdown"]
            if text.startswith("---"):
                front_match = re.match(
                    r"\A---\s*\r?\n[\s\S]*?\r?\n---[ \t]*(?:\r?\n|$)", text
                )
                if front_match:
                    text = text[front_match.end() :]
            raw_html = md_renderer.render(text) if text.strip() else ""

        anchor_result = update_heading_anchors(
            raw_html, owner_page_id=page_node_id, source_path=source
        )
        unified_html = anchor_result.html
        sections = anchor_result.sections
        if anchor_result.diagnostics:
            diagnostics.extend(anchor_result.diagnostics)

        frag_set = {sec.fragment for sec in sections}
        page_fragments[source] = frag_set

        page_target = {
            "kind": "internal",
            "path": p["output"],
            "fragment": None,
        }

        page_kb_id = str(fm["id"]) if fm.get("id") and str(fm["id"]).strip() else None
        page_type = str(fm["type"]) if fm.get("type") and str(fm["type"]).strip() else None
        page_status = (
            str(fm["status"]) if fm.get("status") and str(fm["status"]).strip() else None
        )

        page_details = {
            "source_path": source,
            "kb_id": page_kb_id,
            "type": page_type,
            "status": page_status,
            "tags": list(fm.get("tags") or []),
        }

        page_node = {
            "id": page_node_id,
            "kind": "page",
            "title": p["title"],
            "depth": None,
            "target": page_target,
            "preview_key": page_node_id,
            "page": page_details,
            "section": None,
            "reference": None,
        }
        nodes[page_node_id] = page_node

        page_excerpt = get_text_excerpt(unified_html, max_length=600)
        page_origin = "rendered-body" if page_excerpt["mode"] == "excerpt" else "none"

        preview_records[page_node_id] = {
            "key": page_node_id,
            "node_id": page_node_id,
            "mode": page_excerpt["mode"],
            "text": page_excerpt["text"],
            "truncated": page_excerpt["truncated"],
            "origin": page_origin,
        }

        sibling_counters: dict[str, int] = {}
        for sec in sections:
            if source == entrypoint or re.search(
                r"(?i)^(待整理笔记|待整理|收件箱|inbox)$", sec.title
            ):
                continue
            sec_node_id = sec.node_id
            sec_target = {
                "kind": "internal",
                "path": p["output"],
                "fragment": sec.fragment,
            }
            sec_details = {
                "owner_page": page_node_id,
                "heading_level": int(sec.heading_level),
                "ordinal": int(sec.ordinal),
            }
            sec_node = {
                "id": sec_node_id,
                "kind": "section",
                "title": sec.title,
                "depth": None,
                "target": sec_target,
                "preview_key": sec_node_id,
                "page": None,
                "section": sec_details,
                "reference": None,
            }
            nodes[sec_node_id] = sec_node

            sec_excerpt = get_text_excerpt(sec.html_content, max_length=600)
            sec_origin = "rendered-body" if sec_excerpt["mode"] == "excerpt" else "none"

            preview_records[sec_node_id] = {
                "key": sec_node_id,
                "node_id": sec_node_id,
                "mode": sec_excerpt["mode"],
                "text": sec_excerpt["text"],
                "truncated": sec_excerpt["truncated"],
                "origin": sec_origin,
            }

            parent_id = sec.parent_node_id
            contains_order = sibling_counters.get(parent_id, 0)
            sibling_counters[parent_id] = contains_order + 1

            source_sec_occ = parent_id if parent_id != page_node_id else None

            contains_edge_id = f"edge:contains:{parent_id}->{sec_node_id}"
            edges[contains_edge_id] = {
                "id": contains_edge_id,
                "kind": "contains",
                "source": parent_id,
                "target": sec_node_id,
                "order": contains_order,
                "occurrences": [
                    {
                        "owner_page": page_node_id,
                        "source_section": source_sec_occ,
                        "link_ordinal": -1,
                        "target_fragment": sec.fragment,
                        "label": sec.title,
                    }
                ],
            }

        rendered_page_map[source] = {
            "page": p,
            "unified_html": unified_html,
            "sections": sections,
        }

    # Collects edges
    for p in pages_list:
        source = p["source"]
        page_node_id = page_node_ids[source]

        raw_text = p["raw_markdown"]
        nav_block_match = re.search(
            r"(?is)<!-- kb-nav:children:start -->([\s\S]*?)<!-- kb-nav:children:end -->",
            raw_text,
        )
        ordered_children: list[str] = []

        collect_source_node_id = page_node_id
        if source != entrypoint and source in rendered_page_map:
            matched_sec = None
            for sec in rendered_page_map[source]["sections"]:
                if re.search(r"<!--\s*kb-nav:children:start\s*-->", sec.html_content):
                    matched_sec = sec
            if matched_sec and matched_sec.node_id in nodes:
                collect_source_node_id = matched_sec.node_id

        if nav_block_match:
            block_text = nav_block_match.group(1)
            block_text = re.sub(r"(?is)```[\s\S]*?```", "", block_text)
            top_level_block_text = re.sub(r"(?m)^[ \t]+[-*+0-9].*$", "", block_text)
            link_matches = list(
                re.finditer(
                    r"(?is)\[([^\]]*)\]\((<[^>]+>|[^)\s]+)[^)]*\)", top_level_block_text
                )
            )
            seen_children: set[str] = set()

            for lm in link_matches:
                raw_target = lm.group(2).strip().strip("<>")
                target_path = re.split(r"[?#]", raw_target, maxsplit=1)[0]
                try:
                    decoded_path = urllib.parse.unquote(target_path)
                except Exception:
                    decoded_path = target_path

                source_parent_dir = os.path.dirname(
                    os.path.join(root, source.replace("/", os.sep))
                )
                candidate = os.path.normpath(
                    os.path.join(source_parent_dir, decoded_path.replace("/", os.sep))
                )
                if test_path_inside_root(candidate, root) and candidate != root:
                    rel_child = os.path.relpath(candidate, root).replace("\\", "/")
                    if rel_child in page_node_ids and rel_child.lower() not in seen_children:
                        seen_children.add(rel_child.lower())
                        ordered_children.append(rel_child)

        if source in nav_pages:
            np = nav_pages[source]
            nav_children = list(np.children if hasattr(np, "children") else np["children"])
            for nc in nav_children:
                if nc not in ordered_children:
                    ordered_children.append(nc)

        collect_order = 0
        for child_source in ordered_children:
            if child_source in page_node_ids:
                child_node_id = page_node_ids[child_source]
                collect_edge_id = f"edge:collects:{collect_source_node_id}->{child_node_id}"
                if child_source in nav_pages:
                    np = nav_pages[child_source]
                    child_title = np.title if hasattr(np, "title") else np["title"]
                else:
                    child_title = child_source

                edges[collect_edge_id] = {
                    "id": collect_edge_id,
                    "kind": "collects",
                    "source": collect_source_node_id,
                    "target": child_node_id,
                    "order": collect_order,
                    "occurrences": [
                        {
                            "owner_page": page_node_id,
                            "source_section": (
                                collect_source_node_id
                                if collect_source_node_id != page_node_id
                                else None
                            ),
                            "link_ordinal": 0,
                            "target_fragment": None,
                            "label": child_title,
                        }
                    ],
                }
                collect_order += 1

    # References edges
    for p in pages_list:
        source = p["source"]
        page_node_id = page_node_ids[source]
        unified_html = rendered_page_map[source]["unified_html"]

        clean_html = re.sub(r"(?is)<(pre|code)\b[^>]*>.*?</\1>", "", unified_html)
        clean_html = re.sub(
            r"(?is)<!-- kb-nav:children:start -->.*?<!-- kb-nav:children:end -->",
            "",
            clean_html,
        )

        scan_regex = (
            r"(?is)(?P<heading><h(?P<hlevel>[2-6])\b[^>]*\bid\s*=\s*(?P<hquote>[\"'])(?P<hid>[^\"']+)(?P=hquote)[^>]*>)|"
            r"(?P<anchor><a\b(?P<aattrs>[^>]*)\bhref\s*=\s*(?P<aquote>[\"'])(?P<href>[^\"']*?)(?P=aquote)[^>]*>(?P<alabel>.*?)</a>)"
        )
        scan_matches = list(re.finditer(scan_regex, clean_html))

        current_section_node_id: str | None = None
        link_ordinal = 0
        ref_edge_occurrences: dict[str, list[dict[str, Any]]] = {}
        ref_edge_order: dict[str, int] = {}
        next_ref_order = 0

        for sm in scan_matches:
            if sm.group("heading"):
                hid = sm.group("hid")
                candidate_sec_id = f"section:{page_node_id}#{hid}"
                current_section_node_id = candidate_sec_id if candidate_sec_id in nodes else None
                continue

            href = html.unescape(sm.group("href") or "").strip()
            raw_label = sm.group("alabel") or ""
            if re.search(r"(?is)<img\b", raw_label):
                continue

            plain_label = html.unescape(re.sub(r"<[^>]+>", "", raw_label)).strip()
            ordinal = link_ordinal
            link_ordinal += 1

            if not href:
                continue

            if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*:", href) and not re.match(
                r"^(https?|file):", href, re.I
            ):
                diagnostics.append(
                    {
                        "code": "unsupported_scheme",
                        "severity": "warning",
                        "source_path": source,
                        "link_ordinal": ordinal,
                        "message": f"Unsupported link scheme in href '{href}'",
                    }
                )
                continue

            target_node_id: str | None = None
            target_fragment: str | None = None

            # Check if link is on same line as <!-- kb-external-local -->
            line_start = clean_html.rfind("\n", 0, sm.start())
            if line_start < 0:
                line_start = 0
            line_end = clean_html.find("\n", sm.end())
            if line_end < 0:
                line_end = len(clean_html)
            line_text = clean_html[line_start:line_end]
            is_external_local = href.startswith("file://") or bool(
                re.search(r"<!--\s*kb-external-local\s*-->", line_text)
            )

            if href.startswith("#"):
                frag = href[1:]
                target_fragment = frag
                target_node_id = page_node_id
                if frag not in page_fragments[source]:
                    diagnostics.append(
                        {
                            "code": "missing_fragment",
                            "severity": "warning",
                            "source_path": source,
                            "link_ordinal": ordinal,
                            "message": f"Target fragment '#{frag}' not found in {source}",
                        }
                    )
            elif re.match(r"^https?://", href, re.I):
                canonical_target = f"web:{href}"
                ref_hash = _sha256_hex(canonical_target)
                ref_node_id = f"ref:{ref_hash}"
                target_node_id = ref_node_id

                if ref_node_id not in nodes:
                    ref_title = plain_label if plain_label else href
                    nodes[ref_node_id] = {
                        "id": ref_node_id,
                        "kind": "reference",
                        "title": ref_title,
                        "target": {
                            "kind": "web",
                            "url": href,
                        },
                        "preview_key": ref_node_id,
                        "page": None,
                        "section": None,
                        "reference": {
                            "medium": "web",
                            "source_label": plain_label,
                        },
                    }
                    web_preview_text = (
                        f"{plain_label}\n{href} (外部来源)" if plain_label else f"{href} (外部来源)"
                    )
                    preview_records[ref_node_id] = {
                        "key": ref_node_id,
                        "node_id": ref_node_id,
                        "mode": "metadata",
                        "text": web_preview_text,
                        "truncated": False,
                        "origin": "link-registration",
                    }
            elif is_external_local:
                safe_label = plain_label if plain_label else "外部来源"
                canonical_target = f"external-local:{safe_label}"
                ref_hash = _sha256_hex(canonical_target)
                ref_node_id = f"ref:{ref_hash}"
                target_node_id = ref_node_id

                if ref_node_id not in nodes:
                    nodes[ref_node_id] = {
                        "id": ref_node_id,
                        "kind": "reference",
                        "title": safe_label,
                        "target": {
                            "kind": "display-only",
                            "label": safe_label,
                            "reason": "external-local",
                        },
                        "preview_key": ref_node_id,
                        "page": None,
                        "section": None,
                        "reference": {
                            "medium": "external-local",
                            "source_label": safe_label,
                        },
                    }
                    preview_records[ref_node_id] = {
                        "key": ref_node_id,
                        "node_id": ref_node_id,
                        "mode": "metadata",
                        "text": f"{safe_label} (外部来源)",
                        "truncated": False,
                        "origin": "link-registration",
                    }
            else:
                path_part = re.split(r"[?#]", href, maxsplit=1)[0]
                frag_match = re.search(r"#(?P<frag>.*)$", href)
                frag_part = frag_match.group("frag") if frag_match else None

                try:
                    decoded_path = urllib.parse.unquote(path_part)
                except Exception:
                    decoded_path = path_part

                if not decoded_path.strip():
                    if frag_part:
                        target_fragment = frag_part
                        target_node_id = page_node_id
                        if frag_part not in page_fragments[source]:
                            diagnostics.append(
                                {
                                    "code": "missing_fragment",
                                    "severity": "warning",
                                    "source_path": source,
                                    "link_ordinal": ordinal,
                                    "message": f"Target fragment '#{frag_part}' not found in {source}",
                                }
                            )
                else:
                    source_parent_dir = os.path.dirname(
                        os.path.join(root, source.replace("/", os.sep))
                    )
                    candidate_path = os.path.normpath(
                        os.path.join(source_parent_dir, decoded_path.replace("/", os.sep))
                    )
                    is_inside = (
                        test_path_inside_root(candidate_path, root)
                        and candidate_path != root
                    )

                    if is_inside:
                        rel_target = os.path.relpath(candidate_path, root).replace("\\", "/")
                        if rel_target.lower().startswith("inbox/") or rel_target.lower().startswith("archive/"):
                            continue
                        md_equiv = re.sub(r"(?i)\.html$", ".md", rel_target)
                        resolved_target_source = None

                        if rel_target in page_node_ids:
                            target_node_id = page_node_ids[rel_target]
                            resolved_target_source = rel_target
                        elif md_equiv in page_node_ids:
                            target_node_id = page_node_ids[md_equiv]
                            resolved_target_source = md_equiv
                        elif os.path.isfile(candidate_path):
                            canonical_target = f"attachment:{rel_target}"
                            ref_hash = _sha256_hex(canonical_target)
                            ref_node_id = f"ref:{ref_hash}"
                            target_node_id = ref_node_id

                            if ref_node_id not in nodes:
                                att_title = (
                                    plain_label if plain_label else os.path.basename(rel_target)
                                )
                                nodes[ref_node_id] = {
                                    "id": ref_node_id,
                                    "kind": "reference",
                                    "title": att_title,
                                    "target": {
                                        "kind": "internal",
                                        "path": rel_target,
                                        "fragment": None,
                                    },
                                    "preview_key": ref_node_id,
                                    "page": None,
                                    "section": None,
                                    "reference": {
                                        "medium": "attachment",
                                        "source_label": att_title,
                                    },
                                }
                                preview_records[ref_node_id] = {
                                    "key": ref_node_id,
                                    "node_id": ref_node_id,
                                    "mode": "metadata",
                                    "text": f"{att_title}\n{rel_target} (附件)",
                                    "truncated": False,
                                    "origin": "link-registration",
                                }
                        else:
                            diagnostics.append(
                                {
                                    "code": "missing_target",
                                    "severity": "warning",
                                    "source_path": source,
                                    "link_ordinal": ordinal,
                                    "message": f"Target not found: {path_part}",
                                }
                            )
                            continue

                        if frag_part is not None:
                            target_fragment = frag_part
                            if (
                                resolved_target_source
                                and resolved_target_source in page_fragments
                                and frag_part not in page_fragments[resolved_target_source]
                            ):
                                diagnostics.append(
                                    {
                                        "code": "missing_fragment",
                                        "severity": "warning",
                                        "source_path": source,
                                        "link_ordinal": ordinal,
                                        "message": f"Target fragment '#{frag_part}' not found in {resolved_target_source}",
                                    }
                                )
                    else:
                        safe_label = plain_label if plain_label else "外部来源"
                        canonical_target = f"external-local:{safe_label}"
                        ref_hash = _sha256_hex(canonical_target)
                        ref_node_id = f"ref:{ref_hash}"
                        target_node_id = ref_node_id

                        if ref_node_id not in nodes:
                            nodes[ref_node_id] = {
                                "id": ref_node_id,
                                "kind": "reference",
                                "title": safe_label,
                                "target": {
                                    "kind": "display-only",
                                    "label": safe_label,
                                    "reason": "external-local",
                                },
                                "preview_key": ref_node_id,
                                "page": None,
                                "section": None,
                                "reference": {
                                    "medium": "external-local",
                                    "source_label": safe_label,
                                },
                            }
                            preview_records[ref_node_id] = {
                                "key": ref_node_id,
                                "node_id": ref_node_id,
                                "mode": "metadata",
                                "text": f"{safe_label} (外部来源)",
                                "truncated": False,
                                "origin": "link-registration",
                            }

            if target_node_id is not None:
                edge_key = f"{page_node_id}->{target_node_id}"
                if edge_key not in ref_edge_occurrences:
                    ref_edge_occurrences[edge_key] = []
                    ref_edge_order[edge_key] = next_ref_order
                    next_ref_order += 1
                occ_label = plain_label if plain_label else href
                ref_edge_occurrences[edge_key].append(
                    {
                        "owner_page": page_node_id,
                        "source_section": current_section_node_id,
                        "link_ordinal": ordinal,
                        "target_fragment": target_fragment,
                        "label": occ_label,
                    }
                )

        for edge_key, occs in ref_edge_occurrences.items():
            src, tgt = edge_key.split("->", 1)
            ref_edge_id = f"edge:references:{src}->{tgt}"
            edges[ref_edge_id] = {
                "id": ref_edge_id,
                "kind": "references",
                "source": src,
                "target": tgt,
                "order": int(ref_edge_order[edge_key]),
                "occurrences": list(occs),
            }

    # BFS Shortest Path Depth Calculation from Entrypoint
    bfs_depths: dict[str, int] = {}
    if entry_id and entry_id in nodes:
        bfs_depths[entry_id] = 0
        bfs_queue: collections.deque[str] = collections.deque([entry_id])
        bfs_children: dict[str, set[str]] = {nid: set() for nid in nodes}

        # 1. contains edges
        for e in edges.values():
            if e["kind"] == "contains":
                s = str(e["source"])
                t = str(e["target"])
                if s in bfs_children and t in nodes:
                    bfs_children[s].add(t)

        # 2. collects edges
        for e in edges.values():
            if e["kind"] == "collects":
                s = str(e["source"])
                t = str(e["target"])
                if s in bfs_children and t in nodes:
                    bfs_children[s].add(t)

        # 3. references edges
        for e in edges.values():
            if e["kind"] == "references":
                t = str(e["target"])
                if e.get("occurrences"):
                    for occ in e["occurrences"]:
                        occ_sec = str(occ.get("source_section") or "")
                        parent_id = occ_sec if occ_sec and occ_sec in nodes else str(e["source"])
                        if parent_id in bfs_children and t in nodes:
                            bfs_children[parent_id].add(t)
                else:
                    s = str(e["source"])
                    if s in bfs_children and t in nodes:
                        bfs_children[s].add(t)

        while bfs_queue:
            curr = bfs_queue.popleft()
            curr_depth = bfs_depths[curr]
            for child in bfs_children.get(curr, set()):
                if child not in bfs_depths or (curr_depth + 1 < bfs_depths[child]):
                    bfs_depths[child] = curr_depth + 1
                    bfs_queue.append(child)

    for n in nodes.values():
        nid = str(n["id"])
        n["depth"] = bfs_depths.get(nid, None)

    sorted_nodes = sorted(nodes.values(), key=lambda x: str(x["id"]))
    sorted_edges = sorted(edges.values(), key=lambda x: str(x["id"]))
    sorted_diagnostics = sorted(
        diagnostics,
        key=lambda d: (
            str(d.get("source_path") or ""),
            int(d.get("link_ordinal") if d.get("link_ordinal") is not None else 0),
            str(d.get("code") or ""),
            str(d.get("message") or ""),
        ),
    )
    sorted_preview_records = sorted(
        preview_records.values(), key=lambda r: str(r["node_id"])
    )

    digest_payload = {
        "schema": "kb-graph",
        "schema_version": 1,
        "entry_id": entry_id,
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "diagnostics": sorted_diagnostics,
    }
    serialized_for_digest = json.dumps(
        digest_payload, ensure_ascii=False, separators=(",", ":")
    )
    graph_digest = _sha256_hex(serialized_for_digest)

    graph_data = {
        "schema": "kb-graph",
        "schema_version": 1,
        "graph_digest": graph_digest,
        "entry_id": entry_id,
        "nodes": sorted_nodes,
        "edges": sorted_edges,
        "diagnostics": sorted_diagnostics,
    }

    preview_digest_payload = {
        "schema": "kb-graph-previews",
        "schema_version": 1,
        "graph_digest": graph_digest,
        "records": sorted_preview_records,
    }
    preview_serialized_for_digest = json.dumps(
        preview_digest_payload, ensure_ascii=False, separators=(",", ":")
    )
    preview_digest = _sha256_hex(preview_serialized_for_digest)

    preview_data = {
        "schema": "kb-graph-previews",
        "schema_version": 1,
        "preview_digest": preview_digest,
        "graph_digest": graph_digest,
        "records": sorted_preview_records,
    }

    return GraphModelResult(
        graph_data=graph_data,
        preview_data=preview_data,
        diagnostics=sorted_diagnostics,
    )


def convert_to_graph_javascript(graph_data: dict[str, Any]) -> str:
    """Serialize GraphData as standalone JavaScript window export."""
    json_str = json.dumps(graph_data, ensure_ascii=False, indent=2)
    safe_json = (
        json_str.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return f"window.__KB_GRAPH_DATA__ = {safe_json};\n"


def convert_to_graph_previews_javascript(preview_data: dict[str, Any]) -> str:
    """Serialize PreviewData as standalone JavaScript window export."""
    json_str = json.dumps(preview_data, ensure_ascii=False, indent=2)
    safe_json = (
        json_str.replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )
    return f"window.__KB_GRAPH_PREVIEWS__ = {safe_json};\n"
