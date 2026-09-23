"""Static site builder for knowledge-base-manager.

Implements full static HTML generation, navigation embedding, graph assets,
and incremental build tracking via .kb-static-manifest.json.
"""

from __future__ import annotations

import datetime
import hashlib
import html
import json
import os
import re
import shutil
import urllib.parse
from typing import Any

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from .model import Diagnostic, Envelope
from .paths import (
    assert_no_redirecting_reparse_point,
    get_canonical_path,
    get_safe_tree_files,
    is_redirecting_reparse_point,
    test_path_inside_root,
)
from .static_graph import (
    convert_to_graph_javascript,
    convert_to_graph_previews_javascript,
    get_graph_model,
    update_heading_anchors,
)
from .static_nav import get_static_navigation_href, get_static_navigation_model
from .yaml_reader import read_yaml_fields

GENERATOR_VERSION = "1.2.0"
TEMPLATE_VERSION = "9"
MANIFEST_NAME = ".kb-static-manifest.json"
KATEX_ASSET_VERSION = "0.18.1"
GRAPH_ASSET_VERSION = "1.0.0"

ALERT_TYPES = {
    "note": "Note",
    "tip": "Tip",
    "important": "Important",
    "warning": "Warning",
    "caution": "Caution",
}


def transform_github_alerts(html_text: str) -> str:
    """Transform GitHub-style alert blockquotes to semantic markdown-alert HTML."""
    pattern = re.compile(
        r"<blockquote>\s*<p>\[!(NOTE|TIP|IMPORTANT|WARNING|CAUTION)\](?:\s*<br\s*/?>)?\s*(.*?)</p>(.*?)</blockquote>",
        re.IGNORECASE | re.DOTALL,
    )

    def replace_alert(m: re.Match) -> str:
        alert_type = m.group(1).lower()
        title = ALERT_TYPES.get(alert_type, alert_type.capitalize())
        body1 = m.group(2).strip()
        rest = m.group(3)
        content_parts = []
        if body1:
            content_parts.append(f"<p>{body1}</p>")
        if rest.strip():
            content_parts.append(rest.strip())
        content = "\n".join(content_parts)
        return (
            f'<div class="markdown-alert markdown-alert-{alert_type}">\n'
            f'<p class="markdown-alert-title">{title}</p>\n'
            f"{content}\n"
            f"</div>"
        )

    return pattern.sub(replace_alert, html_text)


def create_static_markdown_parser() -> MarkdownIt:
    """Create and configure markdown-it-py parser tailored for static HTML generation."""
    md = (
        MarkdownIt("commonmark", {"html": True})
        .enable("table")
        .enable("strikethrough")
        .use(footnote_plugin)
        .use(
            dollarmath_plugin,
            allow_labels=False,
            allow_space=True,
            allow_digits=True,
            allow_blank_lines=True,
            double_inline=False,
        )
        .use(tasklists_plugin)
    )

    md.validateLink = lambda url: not bool(
        re.match(r"^(javascript|vbscript):", url.strip().lower())
    )

    # Format table alignment with semicolon for Markdig compliance
    orig_th_open = md.renderer.rules.get("th_open")

    def render_th_open(self, tokens, idx, options, env):
        token = tokens[idx]
        style = token.attrGet("style")
        if style:
            style = re.sub(r"text-align:\s*(\w+)", r"text-align: \1;", style)
            token.attrSet("style", style)
        if orig_th_open:
            return orig_th_open(self, tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    orig_td_open = md.renderer.rules.get("td_open")

    def render_td_open(self, tokens, idx, options, env):
        token = tokens[idx]
        style = token.attrGet("style")
        if style:
            style = re.sub(r"text-align:\s*(\w+)", r"text-align: \1;", style)
            token.attrSet("style", style)
        if orig_td_open:
            return orig_td_open(self, tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("th_open", render_th_open)
    md.add_render_rule("td_open", render_td_open)

    # <del> for strikethrough
    md.add_render_rule("s_open", lambda self, tokens, idx, options, env: "<del>")
    md.add_render_rule("s_close", lambda self, tokens, idx, options, env: "</del>")

    # Math formatting for KaTeX auto-render
    def render_math_inline(self, tokens, idx, options, env):
        return f'<span class="math">\\({tokens[idx].content}\\)</span>'

    def render_math_block(self, tokens, idx, options, env):
        return f'<div class="math">\\[\n{tokens[idx].content}\n\\]</div>\n'

    md.add_render_rule("math_inline", render_math_inline)
    md.add_render_rule("math_block", render_math_block)

    # Footnote formatting matching tests
    def render_footnote_ref(self, tokens, idx, options, env):
        ident = tokens[idx].meta["id"] + 1
        sub_id = tokens[idx].meta["subId"]
        id_str = f"fnref{ident}" + (f":{sub_id}" if sub_id > 0 else "")
        fn_id = f"fn{ident}"
        return f'<a class="footnote-ref" id="{id_str}" href="#{fn_id}"><sup>{ident}</sup></a>'

    def render_footnote_block_open(self, tokens, idx, options, env):
        return '<div class="footnotes">\n<hr class="footnotes-sep">\n<ol class="footnotes-list">\n'

    def render_footnote_block_close(self, tokens, idx, options, env):
        return "</ol>\n</div>\n"

    md.add_render_rule("footnote_ref", render_footnote_ref)
    md.add_render_rule("footnote_block_open", render_footnote_block_open)
    md.add_render_rule("footnote_block_close", render_footnote_block_close)

    return md


def get_kb_static_relative_path(base: str, path: str) -> str:
    return os.path.relpath(path, base).replace("\\", "/")


def get_kb_static_sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest().lower()


def get_kb_static_body(text: str) -> str:
    """Extract body text excluding initial front matter."""
    if not text.startswith("---"):
        return text
    lines = text.splitlines(keepends=True)
    if len(lines) < 2 or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            if i == len(lines) - 1:
                return ""
            return "".join(lines[i + 1 :])
    return text


def get_kb_static_link_destination(inside: str) -> tuple[str, str]:
    trimmed = inside.strip()
    if trimmed.startswith("<"):
        close = trimmed.find(">")
        if close > 0:
            return trimmed[1:close], trimmed[close + 1 :]
    m = re.match(r"^(?P<destination>\S+)(?P<suffix>\s+.*)?$", trimmed)
    if m:
        return m.group("destination"), m.group("suffix") or ""
    return trimmed, ""


def convert_to_kb_static_href(target: str) -> str:
    path_part = re.split(r"[?#]", target, maxsplit=1)[0]
    trailer = target[len(path_part) :]
    try:
        decoded = urllib.parse.unquote(path_part)
    except Exception:
        decoded = path_part
    encoded = "/".join(urllib.parse.quote(part, safe="~") for part in decoded.split("/"))
    return encoded + trailer


def convert_kb_static_single_link(m: re.Match, source_file: str, content_root: str) -> str:
    destination, suffix = get_kb_static_link_destination(m.group("inside"))
    if (
        not destination.strip()
        or destination.startswith("#")
        or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", destination)
        or destination.startswith(("\\", "//"))
    ):
        return m.group(0)

    path_part = re.split(r"[?#]", destination, maxsplit=1)[0]
    if not path_part.strip():
        return m.group(0)

    try:
        decoded_path = urllib.parse.unquote(path_part).replace("/", os.sep)
    except Exception:
        return m.group(0)

    if os.path.isabs(decoded_path) or re.match(r"^[A-Za-z]:", decoded_path):
        return m.group(0)

    candidate = os.path.normpath(
        os.path.join(os.path.dirname(source_file), decoded_path)
    )
    if not test_path_inside_root(candidate, content_root):
        return m.group(0)

    rewritten = destination
    if re.search(r"(?i)\.md$", path_part):
        rewritten = re.sub(r"(?i)\.md(?=([?#]|$))", ".html", destination)
    elif os.path.isdir(candidate):
        trailer = destination[len(path_part) :]
        directory_part = path_part.rstrip("/\\")
        rewritten = "index.html" + trailer if not directory_part else directory_part + "/index.html" + trailer

    if rewritten == destination:
        return m.group(0)

    return (
        m.group("prefix")
        + convert_to_kb_static_href(rewritten)
        + suffix
        + m.group("close")
    )


def convert_kb_static_links(markdown: str, source_file: str, content_root: str) -> str:
    pattern = re.compile(r"(?P<prefix>!?\[[^\]]*\]\()(?P<inside>[^)]+)(?P<close>\))")
    return pattern.sub(
        lambda m: convert_kb_static_single_link(m, source_file, content_root), markdown
    )


def get_kb_static_page_output_path(relative_source: str) -> str:
    if re.search(r"(?i)(^|/)index\.md$", relative_source):
        return re.sub(r"(?i)index\.md$", "index.html", relative_source)
    return re.sub(r"(?i)\.md$", ".html", relative_source)


def get_kb_static_katex_prefix(output_relative: str) -> str:
    directory = os.path.dirname(output_relative.replace("/", os.sep))
    if not directory or directory == ".":
        return "./_assets/katex"
    levels = len([p for p in re.split(r"[\\/]+", directory) if p])
    return ("../" * levels) + "_assets/katex"


def get_kb_static_graph_prefix(output_relative: str) -> str:
    directory = os.path.dirname(output_relative.replace("/", os.sep))
    if not directory or directory == ".":
        return "./_assets/graph"
    levels = len([p for p in re.split(r"[\\/]+", directory) if p])
    return ("../" * levels) + "_assets/graph"


def get_kb_static_output_base_url(output_relative: str) -> str:
    directory = os.path.dirname(output_relative.replace("/", os.sep))
    if not directory or directory == ".":
        return "."
    levels = len([p for p in re.split(r"[\\/]+", directory) if p])
    return ("../" * (levels - 1)) + ".."


def new_kb_static_breadcrumb(
    title: str,
    output_relative: str,
    navigation: Any,
    source_relative: str = "",
    is_home: bool = False,
    inbox_count: int = 0,
) -> str:
    root_page = navigation.pages[navigation.entry_source]
    items: list[str] = []
    chain: list[str] = []
    connected = False

    page = (
        navigation.pages.get(source_relative)
        if source_relative and source_relative in navigation.pages
        else None
    )
    if page and source_relative != navigation.entry_source:
        cursor = page
        while len(cursor.parents) == 1:
            parent_source = cursor.parents[0]
            if parent_source == navigation.entry_source:
                connected = True
                break
            chain.append(parent_source)
            cursor = navigation.pages[parent_source]

    if source_relative != navigation.entry_source:
        href = html.escape(
            get_static_navigation_href(output_relative, root_page.output)
        )
        items.append(f'<li><a href="{href}">{html.escape(root_page.title)}</a></li>')
        if connected:
            for ancestor_source in reversed(chain):
                ancestor = navigation.pages[ancestor_source]
                a_href = html.escape(
                    get_static_navigation_href(output_relative, ancestor.output)
                )
                items.append(
                    f'<li><a href="{a_href}">{html.escape(ancestor.title)}</a></li>'
                )

    items.append(f'<li><span aria-current="page">{html.escape(title)}</span></li>')
    nav_html = f'<nav class="kb-breadcrumb" aria-label="面包屑"><ol>{"".join(items)}</ol></nav>'

    badge_class = "kb-inbox-badge-active" if inbox_count > 0 else "kb-inbox-badge-empty"
    if is_home:
        inbox_href = html.escape(
            get_static_navigation_href(output_relative, "inbox/index.html")
        )
        inbox_link = (
            f'<a href="{inbox_href}" class="kb-inbox-trigger-btn" id="kb-inbox-trigger" aria-label="查看收件箱">'
            f'<span>收件箱</span><span class="kb-inbox-badge {badge_class}">{inbox_count}</span></a>'
        )
    else:
        inbox_link = ""

    actions_html = (
        f'<div class="kb-nav-actions">'
        f'<button type="button" class="kb-graph-trigger-btn" id="kb-graph-trigger" aria-label="打开关系图谱">关系图谱</button>'
        f"{inbox_link}</div>"
    )
    res_html = f'<div class="kb-nav-header">{nav_html}{actions_html}</div>'

    if page and source_relative != navigation.entry_source and not connected:
        if len(page.parents) == 0:
            res_html += '<p class="kb-uncollected">尚未被项目或主题收录</p>'
        else:
            links = []
            for parent_source in page.parents:
                parent = navigation.pages[parent_source]
                p_href = html.escape(
                    get_static_navigation_href(output_relative, parent.output)
                )
                links.append(f'<li><a href="{p_href}">{html.escape(parent.title)}</a></li>')
            res_html += f'<nav class="kb-collections" aria-label="收录入口"><p>收录入口</p><ul>{"".join(links)}</ul></nav>'

    return res_html


def new_kb_static_html_document(
    title: str,
    body_html: str,
    output_relative: str,
    navigation: Any,
    source_relative: str = "",
    is_home: bool = False,
    page_node_id: str = "",
    inbox_count: int = 0,
) -> str:
    safe_title = html.escape(title)
    katex_prefix = get_kb_static_katex_prefix(output_relative)
    graph_prefix = get_kb_static_graph_prefix(output_relative)
    output_base_url = get_kb_static_output_base_url(output_relative)
    breadcrumb = new_kb_static_breadcrumb(
        title=title,
        output_relative=output_relative,
        navigation=navigation,
        source_relative=source_relative,
        is_home=is_home,
        inbox_count=inbox_count,
    )

    inline_graph_html = (
        """
<section id="kb-graph-inline" class="kb-graph-inline kb-graph-inline-section" aria-label="知识关系图谱">
  <div class="kb-graph-inline-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:0.75rem;">
    <h2 style="margin:0;border-bottom:none;padding-bottom:0;font-size:1.15rem;">知识关系图谱</h2>
    <button type="button" class="kb-graph-trigger-btn" id="kb-graph-trigger-inline" aria-label="弹出大窗口浏览关系图谱" title="弹出大窗口浏览">⛶ 全屏大窗口</button>
  </div>
  <div id="kb-graph-app" class="kb-graph-app kb-graph-inline-container"></div>
</section>
"""
        if is_home
        else ""
    )

    escaped_node_id = html.escape(page_node_id)
    if is_home:
        graph_script = f"""<script id="kb-graph-inline-script" defer>
document.addEventListener('DOMContentLoaded', function () {{
    var container = document.getElementById('kb-graph-app') || document.getElementById('kb-graph-container');
    var inlineGraph = null;
    if (container && window.mountKbGraph) {{
        inlineGraph = window.mountKbGraph(container, {{
            mode: 'inline',
            outputBaseUrl: '{output_base_url}',
            initialPageId: '{escaped_node_id}'
        }});
    }}
    function openOverlay() {{
        if (window.mountKbGraph && !document.querySelector('.kb-graph-mode-overlay')) {{
            var state = (inlineGraph && typeof inlineGraph.getState === 'function') ? inlineGraph.getState() : null;
            window.mountKbGraph(document.body, {{
                mode: 'overlay',
                outputBaseUrl: '{output_base_url}',
                initialPageId: (state && state.focusedId) ? state.focusedId : '{escaped_node_id}',
                initialExpanded: state ? state.expanded : null,
                initialEgoFocusId: state ? state.egoFocusId : null,
                onClose: function (finalState) {{
                    if (inlineGraph && finalState && typeof inlineGraph.setState === 'function') {{
                        inlineGraph.setState(finalState);
                    }}
                }}
            }});
        }}
    }}
    var trigger = document.getElementById('kb-graph-trigger');
    if (trigger) {{
        trigger.addEventListener('click', openOverlay);
    }}
    var inlineTrigger = document.getElementById('kb-graph-trigger-inline');
    if (inlineTrigger) {{
        inlineTrigger.addEventListener('click', openOverlay);
    }}
}});
</script>"""
    else:
        graph_script = f"""<script id="kb-graph-overlay-script" defer>
document.addEventListener('DOMContentLoaded', function () {{
    var trigger = document.getElementById('kb-graph-trigger');
    if (trigger) {{
        trigger.addEventListener('click', function () {{
            if (window.mountKbGraph && !document.querySelector('.kb-graph-mode-overlay')) {{
                window.mountKbGraph(document.body, {{
                    mode: 'overlay',
                    outputBaseUrl: '{output_base_url}',
                    initialPageId: '{escaped_node_id}'
                }});
            }}
        }});
    }}
}});
</script>"""

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{safe_title}</title>
<style id="kb-theme">
:root{{color-scheme:light;font-family:"Segoe UI","Microsoft YaHei","PingFang SC",sans-serif;font-size:16px;color:#25384a;background:#edf4fa}}
*{{box-sizing:border-box}} html{{scroll-padding-top:2rem}}
body{{max-width:1040px;margin:2.5rem auto;padding:0 2rem;background:#edf4fa;line-height:1.85}}
.kb-paper{{min-width:0;background:#fff;border:1px solid #d6e3ee;border-radius:14px;box-shadow:0 8px 30px #284d7210;padding:2rem 3.25rem 2.5rem}}
.kb-content{{min-width:0;overflow-wrap:anywhere}} .kb-content>:last-child{{margin-bottom:0}}
a{{color:#176bb0;text-underline-offset:.2em;text-decoration-thickness:1px}} a:hover{{color:#105184}} :focus-visible{{outline:3px solid #176bb0;outline-offset:4px}}
h1,h2,h3,h4,h5,h6{{line-height:1.45;color:#1d4c71;scroll-margin-top:2rem}} h1{{font-size:clamp(1.75rem,3vw,2.25rem);letter-spacing:-.025em;margin:1.5rem 0;color:#163d5e}} .kb-content>h1:first-child{{margin:0 0 1.5rem;padding:1.25rem 1.5rem;border:1px solid #dce7f0;border-radius:8px;background:linear-gradient(135deg,#f0f8ff 0%,#fff 85%)}}
h2{{margin:2.25rem 0 1rem;padding-bottom:.6rem;border-bottom:1px solid #dce7f0;font-size:1.3rem}} h3{{font-size:1.08rem;margin:1.6rem 0 .6rem}} p{{margin:.9rem 0}}
pre{{overflow:auto;max-width:100%;margin:1.25rem 0;padding:1.25rem 1.4rem;background:#f1f6fb;border:1px solid #d6e5f1;border-radius:8px;line-height:1.7;tab-size:4;color:#274963}} pre code{{padding:0;background:transparent;border:0;font-size:1em;overflow-wrap:normal}}
code,pre{{font-family:Consolas,"Cascadia Code","SFMono-Regular",monospace;font-size:.88em}} :not(pre)>code{{background:#edf4fa;padding:.15em .4em;border:1px solid #e0eaf3;border-radius:4px;color:#1c5c8d}}
table{{display:block;max-width:100%;width:max-content;overflow-x:auto;border-collapse:collapse;margin:1.25rem 0;font-size:.9rem}} th,td{{border:1px solid #dce7f0;padding:.7rem .9rem;text-align:left;vertical-align:top}} th{{background:#edf5fc;color:#2a5b80;font-weight:650}} tr:nth-child(even) td{{background:#f9fbfd}} caption{{text-align:left;color:#60758a;padding:.5rem 0}}
ul,ol{{padding-left:1.6rem}} li+li{{margin-top:.3rem}} li>ul,li>ol{{margin:.2rem 0 .1rem}} li::marker{{color:#4388bb}}
ul.task-list,ul.contains-task-list{{list-style:none;padding-left:.25rem}} .task-list-item{{display:flex;align-items:baseline;gap:.45rem}} .task-list-item>input[type="checkbox"]{{margin:0;flex:0 0 auto}}
blockquote{{margin:1.4rem 0;padding:.15rem 1.25rem;border-left:.2rem solid #65a9dc;background:#f3f8fd;color:#466278;border-radius:0 7px 7px 0}} blockquote>:first-child{{margin-top:.55rem}} blockquote>:last-child{{margin-bottom:.55rem}}
.markdown-alert{{margin:1rem 0;padding:.1rem 1rem;border-left:.28rem solid #60a5fa;background:#eff6ff}} .markdown-alert-title{{font-weight:700}} .markdown-alert-warning{{border-color:#f59e0b;background:#fffbeb}} .markdown-alert-important{{border-color:#a855f7;background:#faf5ff}} .markdown-alert-caution{{border-color:#ef4444;background:#fef2f2}}
.footnotes{{font-size:.92em;border-top:1px solid #dce7f0;margin-top:2rem;color:#60758a}} .footnote-ref{{text-decoration:none}}
hr{{border:0;border-top:1px solid #dce7f0;margin:2rem 0}} del{{color:#60758a}} img{{max-width:100%;height:auto}} .katex-display{{max-width:100%;overflow-x:auto;overflow-y:hidden;padding:.25rem 0}}
.kb-nav-header{{display:flex;align-items:center;justify-content:space-between;flex-wrap:wrap;gap:.5rem;margin:0 0 1.5rem}}
.kb-nav-header .kb-breadcrumb{{margin:0}}
.kb-nav-header .kb-breadcrumb ol{{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0;margin:0;font-size:.85rem;color:#60758a}}
.kb-breadcrumb ol{{display:flex;flex-wrap:wrap;gap:.4rem;list-style:none;padding:0;margin:0 0 1.5rem;font-size:.85rem;color:#60758a}} .kb-breadcrumb li{{min-width:0;overflow-wrap:anywhere}} .kb-breadcrumb li+li{{margin:0}} .kb-breadcrumb li+li::before{{content:'/';margin-right:.4rem;color:#94a3b8}} .kb-breadcrumb [aria-current]{{color:#466278;overflow-wrap:anywhere}}
.kb-nav-actions{{display:flex;align-items:center;gap:.6rem}}
.kb-graph-trigger-btn{{font:inherit;font-size:.85rem;padding:.2rem .65rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer;touch-action:manipulation;white-space:nowrap}}
.kb-graph-trigger-btn:hover{{background:#dbeafe;border-color:#388bc9}}
.kb-inbox-trigger-btn{{position:relative;display:inline-flex;align-items:center;font:inherit;font-size:.85rem;padding:.2rem .7rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer;text-decoration:none;touch-action:manipulation;white-space:nowrap}}
.kb-inbox-trigger-btn:hover{{background:#dbeafe;border-color:#388bc9;text-decoration:none}}
.kb-inbox-badge{{position:absolute;top:-6px;right:-6px;display:flex;align-items:center;justify-content:center;min-width:16px;height:16px;padding:0 3px;border-radius:50%;font-size:10px;font-weight:700;line-height:1;box-shadow:0 0 0 1.5px #fff}}
.kb-inbox-badge-empty{{background:#94a3b8;color:#ffffff}}
.kb-inbox-badge-active{{background:#ef4444;color:#ffffff}}
.kb-graph-inline-section{{margin-top:2.5rem;padding-top:1.5rem;border-top:1px solid #dce7f0}}
.kb-collections,.kb-uncollected{{font-size:.85rem;color:#60758a;margin:0 0 1.5rem}} .kb-collections p{{margin:0}} .kb-collections ul{{display:flex;flex-wrap:wrap;gap:.4rem 1rem;list-style:none;padding:0;margin:.3rem 0}} .kb-collections li+li{{margin:0}}
details{{margin:1.4rem 0;padding:.75rem 1.1rem;border:1px solid #dce7f0;border-radius:8px;background:#fbfdff}} summary{{cursor:pointer;font-weight:650;color:#285d86}} details[open]>summary{{margin-bottom:.65rem}}
.kb-code-tools{{display:flex;align-items:center;flex-wrap:wrap;gap:.65rem;margin:1rem 0 -.7rem}} .kb-code-tools button{{font:inherit;font-size:.85rem;padding:.25rem .65rem;color:#176bb0;background:#eff6ff;border:1px solid #b5d7f0;border-radius:5px;cursor:pointer}} .kb-code-tools button:hover{{background:#dbeafe}} .kb-code-tools button:disabled{{cursor:wait;opacity:.65}} .kb-copy-status{{font-size:.85rem;color:#60758a}}
.kb-toc{{min-width:0;font-size:.85rem;color:#60758a}} .kb-toc-title{{margin:0 0 .75rem;font-size:.9rem;color:#285d86;font-weight:650}} .kb-toc ol{{list-style:none;margin:0;padding:0}} .kb-toc li+li{{margin-top:.15rem}} .kb-toc a{{display:block;padding:.35rem .6rem;border-left:1px solid #cdddea;text-decoration:none;overflow-wrap:anywhere}} .kb-toc a:hover{{background:#e2eef8;border-color:#388bc9}} .kb-toc .kb-toc-level-3 a{{padding-left:1.3rem}} .kb-toc .kb-toc-level-4 a{{padding-left:2rem}}
@media (min-width:1100px){{body.kb-has-toc{{max-width:1320px;display:grid;grid-template-columns:minmax(0,1fr) 200px;gap:2rem;align-items:start}} .kb-toc{{position:sticky;top:2rem;max-height:calc(100vh - 4rem);overflow-y:auto;padding:.75rem .25rem}}}}
@media (max-width:1099px){{body.kb-has-toc{{display:flex;flex-direction:column}} .kb-toc{{order:-1;width:100%;margin:0 0 1rem;padding:1rem;background:#f3f8fd;border:1px solid #d6e3ee;border-radius:8px}} .kb-paper{{width:100%}}}}
@media (max-width:600px){{body{{margin:1rem auto;padding:0 .75rem}} .kb-paper{{padding:1.25rem 1.1rem 1.5rem;border-radius:10px}} .kb-content>h1:first-child{{padding:1rem}} pre{{padding:.9rem}} th,td{{padding:.5rem .65rem}}}}
@media print{{:root{{font-size:11pt;background:#fff;color:#000}} body,body.kb-has-toc{{display:block;max-width:none;margin:0;padding:0;background:#fff;color:#000}} .kb-paper{{padding:0;border:0;border-radius:0;box-shadow:none}} .kb-code-tools,.kb-toc,.kb-graph-trigger-btn,.kb-inbox-trigger-btn,.kb-graph-inline-section,.kb-graph-root{{display:none}} .kb-content>h1:first-child{{padding:0;border:0;background:#fff}} h1,h2,h3{{break-after:avoid}} pre{{white-space:pre-wrap;overflow-wrap:anywhere}} pre code{{overflow-wrap:anywhere}} table{{display:table;width:100%;overflow:visible}} tr,blockquote{{break-inside:avoid}} a{{color:inherit}}}}
</style>
<link rel="stylesheet" href="{katex_prefix}/katex.min.css">
<script defer src="{katex_prefix}/katex.min.js"></script>
<script defer src="{katex_prefix}/contrib/auto-render.min.js"></script>
<script defer>document.addEventListener('DOMContentLoaded',function(){{renderMathInElement(document.body,{{delimiters:[{{left:'\\\\(',right:'\\\\)',display:false}},{{left:'\\\\[',right:'\\\\]',display:true}}],throwOnError:false}});}});</script>
<link rel="stylesheet" href="{graph_prefix}/graph.css">
<script defer src="{graph_prefix}/graph-data.js"></script>
<script defer src="{graph_prefix}/graph-previews.js"></script>
<script defer src="{graph_prefix}/graph.js"></script>
{graph_script}
<script id="kb-toc-script">
document.addEventListener('DOMContentLoaded', function () {{
    var toc = document.getElementById('kb-toc');
    var list = document.createElement('ol');
    var nextId = 1;
    document.querySelectorAll('.kb-content h2, .kb-content h3, .kb-content h4').forEach(function (heading) {{
        if (heading.closest('pre, code')) return;
        if (!heading.id) {{
            var candidate;
            do {{ candidate = 'kb-heading-' + nextId++; }} while (document.getElementById(candidate));
            heading.id = candidate;
        }}
        var item = document.createElement('li');
        item.className = 'kb-toc-level-' + heading.tagName.substring(1);
        var link = document.createElement('a');
        link.textContent = heading.textContent;
        link.setAttribute('href', '#' + encodeURIComponent(heading.id));
        link.addEventListener('click', function () {{
            var ancestor = heading.parentElement;
            while (ancestor) {{
                if (ancestor.tagName === 'DETAILS') ancestor.open = true;
                ancestor = ancestor.parentElement;
            }}
        }});
        item.appendChild(link);
        list.appendChild(item);
    }});
    if (!list.children.length) return;
    toc.appendChild(list);
    toc.hidden = false;
    document.body.classList.add('kb-has-toc');
}});
</script>
<script id="kb-i18n-script">
(function () {{
    var isZh = (function () {{
        if (typeof window !== 'undefined' && window.location && window.location.search) {{
            try {{
                var params = new URLSearchParams(window.location.search);
                var q = params.get('lang');
                if (q === 'en') return false;
                if (q === 'zh') return true;
            }} catch (e) {{}}
        }}
        var nav = (typeof navigator !== 'undefined' && ((navigator.languages && navigator.languages[0]) || navigator.language || navigator.userLanguage)) || '';
        return nav.toLowerCase().startsWith('zh');
    }})();
    window.__KB_IS_ZH__ = isZh;
    if (!isZh) {{
        document.documentElement.lang = 'en';
        document.addEventListener('DOMContentLoaded', function () {{
            var bc = document.querySelector('.kb-breadcrumb');
            if (bc) bc.setAttribute('aria-label', 'Breadcrumbs');
            var tr = document.getElementById('kb-graph-trigger');
            if (tr) {{
                tr.textContent = 'Graph View';
                tr.setAttribute('aria-label', 'Open Knowledge Graph');
            }}
            var inb = document.getElementById('kb-inbox-trigger');
            if (inb) {{
                var inbSpan = inb.querySelector('span:first-child');
                if (inbSpan) inbSpan.textContent = 'Inbox';
                inb.setAttribute('aria-label', 'View Inbox');
            }}
            var trIn = document.getElementById('kb-graph-trigger-inline');
            if (trIn) {{
                trIn.textContent = '⛶ Fullscreen';
                trIn.setAttribute('aria-label', 'Open Knowledge Graph in fullscreen');
                trIn.setAttribute('title', 'Open fullscreen');
            }}
            var inSec = document.getElementById('kb-graph-inline');
            if (inSec) {{
                inSec.setAttribute('aria-label', 'Knowledge Graph');
                var h2 = inSec.querySelector('h2');
                if (h2) h2.textContent = 'Knowledge Graph';
            }}
            var uncoll = document.querySelector('.kb-uncollected');
            if (uncoll) uncoll.textContent = 'Not yet collected into any project or topic';
            var colls = document.querySelector('.kb-collections');
            if (colls) {{
                colls.setAttribute('aria-label', 'Collection Entries');
                var p = colls.querySelector('p');
                if (p) p.textContent = 'Collection Entries';
            }}
            var toc = document.getElementById('kb-toc');
            if (toc) toc.setAttribute('aria-label', 'Table of Contents');
            var tocTitle = document.querySelector('.kb-toc-title');
            if (tocTitle) tocTitle.textContent = 'Table of Contents';
        }});
    }}
}})();
</script>
<script id="kb-copy-script">
document.addEventListener('DOMContentLoaded', function () {{
    var isZh = window.__KB_IS_ZH__ !== false;
    document.querySelectorAll('pre > code').forEach(function (code) {{
        var pre = code.parentElement;
        var controls = document.createElement('div');
        controls.className = 'kb-code-tools';
        var button = document.createElement('button');
        button.type = 'button';
        button.textContent = isZh ? '复制代码' : 'Copy Code';
        var status = document.createElement('span');
        status.className = 'kb-copy-status';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        controls.appendChild(button);
        controls.appendChild(status);
        pre.parentNode.insertBefore(controls, pre);
        function selectForManualCopy() {{
            try {{
                var selection = window.getSelection();
                if (!selection) throw new Error('Selection unavailable');
                var range = document.createRange();
                range.selectNodeContents(code);
                selection.removeAllRanges();
                selection.addRange(range);
                status.textContent = isZh ? '未自动复制；已选中代码，请按 Ctrl+C / Command+C 复制。' : 'Not copied automatically; text selected, press Ctrl+C / Command+C to copy.';
            }} catch (error) {{
                status.textContent = isZh ? '未自动复制，请手动选中代码并按 Ctrl+C / Command+C。' : 'Not copied automatically; please manually select code and press Ctrl+C / Command+C.';
            }}
        }}
        button.addEventListener('click', async function () {{
            button.disabled = true;
            status.textContent = '';
            try {{
                if (!navigator.clipboard || typeof navigator.clipboard.writeText !== 'function') {{
                    selectForManualCopy();
                    return;
                }}
                await navigator.clipboard.writeText(code.textContent);
                status.textContent = isZh ? '已复制代码。' : 'Code copied.';
            }} catch (error) {{
                selectForManualCopy();
            }} finally {{
                button.disabled = false;
            }}
        }});
    }});
}});
</script>
</head>
<body>
<main class="kb-paper">
{breadcrumb}
<div class="kb-content">
{body_html}
</div>
{inline_graph_html}
</main>
<aside id="kb-toc" class="kb-toc" aria-label="文章目录" hidden><p class="kb-toc-title">文章目录</p></aside>
</body>
</html>
"""


def new_kb_static_navigation_page_html() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>知识库全景导航</title>
<link rel="stylesheet" href="./_assets/graph/graph.css">
<style>
* { box-sizing: border-box; }
html, body { margin: 0; padding: 0; width: 100%; height: 100%; overflow: hidden; background: #f3f8fc; }
#kb-nav-app { width: 100%; height: 100%; }
</style>
<script id="kb-nav-i18n">
(function () {
    var isZh = (function () {
        if (typeof window !== 'undefined' && window.location && window.location.search) {
            try {
                var params = new URLSearchParams(window.location.search);
                var q = params.get('lang');
                if (q === 'en') return false;
                if (q === 'zh') return true;
            } catch (e) {}
        }
        var nav = (typeof navigator !== 'undefined' && ((navigator.languages && navigator.languages[0]) || navigator.language || navigator.userLanguage)) || '';
        return nav.toLowerCase().startsWith('zh');
    })();
    if (!isZh) {
        document.documentElement.lang = 'en';
        document.title = 'Knowledge Base Panoramic Navigation';
    }
})();
</script>
<script defer src="./_assets/graph/graph-data.js"></script>
<script defer src="./_assets/graph/graph-previews.js"></script>
<script defer src="./_assets/graph/graph.js"></script>
<script defer>
document.addEventListener('DOMContentLoaded', function () {
    var container = document.getElementById('kb-nav-app');
    if (container && window.mountKbGraph) {
        window.mountKbGraph(container, {
            mode: 'standalone',
            outputBaseUrl: '.'
        });
    }
});
</script>
</head>
<body>
<div id="kb-nav-app"></div>
</body>
</html>
"""


def get_kb_static_safe_asset_files(root: str, label: str = "asset tree") -> list[str]:
    root_full = get_canonical_path(root)
    if not os.path.isdir(root_full):
        raise RuntimeError(f"BLOCKER: {label} is not a directory: {root_full}")
    if is_redirecting_reparse_point(root_full):
        raise RuntimeError(f"BLOCKER: {label} contains a junction or symbolic link: {root_full}")

    files: list[str] = []
    for dirpath, dirnames, filenames in os.walk(root_full, followlinks=False):
        if is_redirecting_reparse_point(dirpath):
            raise RuntimeError(f"BLOCKER: {label} contains a junction or symbolic link: {dirpath}")
        for dirname in dirnames:
            child_dir = os.path.join(dirpath, dirname)
            if is_redirecting_reparse_point(child_dir):
                raise RuntimeError(f"BLOCKER: {label} contains a junction or symbolic link: {child_dir}")
        for filename in filenames:
            file_path = os.path.join(dirpath, filename)
            if is_redirecting_reparse_point(file_path):
                raise RuntimeError(f"BLOCKER: {label} contains a junction or symbolic link: {file_path}")
            files.append(file_path)
    return sorted(files)


def get_kb_static_katex_asset_records(assets_root: str) -> list[dict[str, Any]]:
    assets_full = get_canonical_path(assets_root)
    files = get_kb_static_safe_asset_files(assets_full, label="bundled KaTeX assets")

    for required in ("katex.min.js", "katex.min.css", "contrib/auto-render.min.js"):
        req_path = os.path.join(assets_full, required.replace("/", os.sep))
        if not os.path.isfile(req_path):
            raise RuntimeError(f"BLOCKER: bundled KaTeX asset is missing: {required}")

    fonts_root = os.path.join(assets_full, "fonts")
    if not os.path.isdir(fonts_root):
        raise RuntimeError("BLOCKER: bundled KaTeX fonts directory is missing")

    has_font = any(
        get_kb_static_relative_path(assets_full, f).startswith("fonts/") for f in files
    )
    if not has_font:
        raise RuntimeError("BLOCKER: bundled KaTeX fonts directory is empty")

    records = []
    for f in sorted(files):
        rel = get_kb_static_relative_path(assets_full, f)
        records.append(
            {
                "source_path": f"assets/katex/{rel}",
                "source_relative_path": rel,
                "output_path": f"_assets/katex/{rel}",
                "sha256": get_kb_static_sha256(f),
                "full_path": f,
            }
        )
    return records


def get_kb_static_graph_asset_records(assets_root: str) -> list[dict[str, Any]]:
    assets_full = get_canonical_path(assets_root)
    files = get_kb_static_safe_asset_files(assets_full, label="bundled Graph assets")

    for required in ("graph.css", "graph.js"):
        req_path = os.path.join(assets_full, required.replace("/", os.sep))
        if not os.path.isfile(req_path):
            raise RuntimeError(f"BLOCKER: bundled Graph asset is missing: {required}")

    records = []
    for f in sorted(files):
        rel = get_kb_static_relative_path(assets_full, f)
        records.append(
            {
                "source_path": f"assets/graph/{rel}",
                "source_relative_path": rel,
                "output_path": f"_assets/graph/{rel}",
                "sha256": get_kb_static_sha256(f),
                "full_path": f,
            }
        )
    return records


def get_kb_static_directory_hash(directory: str, content_root: str) -> str:
    children: list[str] = []
    try:
        entries = sorted(os.scandir(directory), key=lambda e: e.name)
    except Exception:
        entries = []
    for entry in entries:
        if entry.is_dir(follow_symlinks=False):
            children.append(f"d:{entry.name}")
        elif entry.name.lower().endswith(".md"):
            children.append(f"m:{entry.name}")
    children.sort()
    rel = get_kb_static_relative_path(content_root, directory)
    text = rel + "\n" + "\n".join(children)
    return hashlib.sha256(text.encode("utf-8")).hexdigest().lower()


def execute_static_build(
    root: str,
    destination: str,
    force: bool = False,
    katex_assets_root: str | None = None,
    graph_assets_root: str | None = None,
) -> tuple[int, Envelope]:
    """Execute complete static build with safety preflight and incremental caching."""
    root_full = get_canonical_path(root)
    dest_full = get_canonical_path(destination)

    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        pkg_root = os.path.dirname(os.path.dirname(script_dir))

        default_katex = os.path.join(pkg_root, "assets", "katex")
        eff_katex_root = katex_assets_root if katex_assets_root else default_katex
        katex_assets = get_kb_static_katex_asset_records(eff_katex_root)

        default_graph = os.path.join(pkg_root, "assets", "graph")
        eff_graph_root = graph_assets_root if graph_assets_root else default_graph
        graph_assets = get_kb_static_graph_asset_records(eff_graph_root)

        if not os.path.isdir(root_full):
            raise RuntimeError(f"BLOCKER: knowledge-base root is not a directory: {root}")
        assert_no_redirecting_reparse_point(root_full, label="knowledge-base root")

        kb_manifest_path = os.path.join(root_full, "kb.yaml")
        if not os.path.isfile(kb_manifest_path):
            raise RuntimeError("BLOCKER: knowledge-base root must contain kb.yaml")
        assert_no_redirecting_reparse_point(kb_manifest_path, label="kb.yaml")

        kb_manifest = read_yaml_fields(kb_manifest_path)
        if not kb_manifest.get("content_dir") or not str(kb_manifest["content_dir"]).strip():
            raise RuntimeError("BLOCKER: kb.yaml must define content_dir")
        if not kb_manifest.get("entrypoint") or not str(kb_manifest["entrypoint"]).strip():
            raise RuntimeError("BLOCKER: kb.yaml must define entrypoint")

        content_dir_str = str(kb_manifest["content_dir"]).strip()
        if os.path.isabs(content_dir_str) or re.match(r"^[A-Za-z]:", content_dir_str):
            raise RuntimeError("BLOCKER: content_dir must be relative to the knowledge-base root")

        content_root = get_canonical_path(os.path.join(root_full, content_dir_str))
        if not test_path_inside_root(content_root, root_full):
            raise RuntimeError("BLOCKER: content_dir escapes knowledge-base root")
        if not os.path.isdir(content_root):
            raise RuntimeError(f"BLOCKER: content_dir is not a directory: {content_root}")
        assert_no_redirecting_reparse_point(content_root, label="knowledge-base content")

        content_files = get_safe_tree_files(content_root, label="knowledge-base content")

        entrypoint_str = str(kb_manifest["entrypoint"]).strip()
        if os.path.isabs(entrypoint_str) or re.match(r"^[A-Za-z]:", entrypoint_str):
            raise RuntimeError("BLOCKER: entrypoint must be relative to the knowledge-base root")

        entrypoint_full = get_canonical_path(os.path.join(root_full, entrypoint_str))
        if not test_path_inside_root(entrypoint_full, content_root):
            raise RuntimeError("BLOCKER: entrypoint must resolve inside content_dir")
        if not os.path.isfile(entrypoint_full) or not entrypoint_full.lower().endswith(".md"):
            raise RuntimeError("BLOCKER: entrypoint must be an existing Markdown file")

        entrypoint_relative = get_kb_static_relative_path(content_root, entrypoint_full)
        entry_output_relative = get_kb_static_page_output_path(entrypoint_relative)

        markdown_files = [f for f in sorted(content_files) if f.lower().endswith(".md")]
        inbox_count = sum(
            1
            for f in markdown_files
            if re.search(r"(?i)^inbox[\\/]", get_kb_static_relative_path(content_root, f))
        )

        # Pre-validate complete navigation graph before any destination directory creation
        navigation = get_static_navigation_model(
            markdown_files=markdown_files,
            content_root=content_root,
            entry_source_path=entrypoint_full,
        )

        # Whole-KB graph model extraction
        graph_model = get_graph_model(
            content_root=content_root,
            navigation=navigation,
            markdown_files=markdown_files,
        )

        page_node_ids: dict[str, str] = {}
        for node in graph_model.graph_data.get("nodes", []):
            if node.get("kind") == "page":
                page_node_ids[str(node["page"]["source_path"])] = str(node["id"])

        assert_no_redirecting_reparse_point(dest_full, label="static-site destination")
        if test_path_inside_root(dest_full, root_full) or test_path_inside_root(
            root_full, dest_full
        ):
            raise RuntimeError(
                "BLOCKER: static-site destination must be outside and must not contain the knowledge-base root"
            )

        if os.path.isfile(dest_full):
            raise RuntimeError(f"BLOCKER: static-site destination is a file: {dest_full}")

        if not os.path.exists(dest_full):
            os.makedirs(dest_full, exist_ok=True)
        assert_no_redirecting_reparse_point(dest_full, label="static-site destination")

        manifest_path = os.path.join(dest_full, MANIFEST_NAME)
        previous: dict[str, Any] | None = None
        if os.path.isfile(manifest_path):
            try:
                with open(manifest_path, "r", encoding="utf-8") as mf:
                    previous = json.load(mf)
            except Exception as e:
                raise RuntimeError(f"BLOCKER: existing static-site manifest is invalid JSON: {e}")
            if (
                not isinstance(previous, dict)
                or previous.get("schema") != "knowledge-base-static-site"
                or previous.get("schema_version") != 1
            ):
                raise RuntimeError("BLOCKER: existing static-site manifest uses an unsupported schema")

        previous_pages: dict[str, Any] = {}
        previous_directories: dict[str, Any] = {}
        previous_katex_assets: dict[str, Any] = {}
        previous_graph_assets: dict[str, Any] = {}
        previous_graph_data_assets: dict[str, Any] = {}
        previous_graph: dict[str, Any] | None = None

        if previous is not None:
            for page in previous.get("pages", []):
                previous_pages[str(page.get("source_path"))] = page
            for directory in previous.get("directories", []):
                previous_directories[str(directory.get("output_path"))] = directory
            if "katex" in previous and isinstance(previous["katex"], dict):
                for asset in previous["katex"].get("assets", []):
                    previous_katex_assets[str(asset.get("source_path"))] = asset
            if "graph" in previous and isinstance(previous["graph"], dict):
                previous_graph = previous["graph"]
                for asset in previous_graph.get("assets", []):
                    previous_graph_assets[str(asset.get("source_path"))] = asset
                for asset in previous_graph.get("data_assets", []):
                    previous_graph_data_assets[str(asset.get("output_path"))] = asset

        state_matches = (
            previous is not None
            and previous.get("generator_version") == GENERATOR_VERSION
            and previous.get("template_version") == TEMPLATE_VERSION
            and previous.get("navigation_digest") == navigation.digest
        )
        katex_state_matches = (
            previous is not None
            and "katex" in previous
            and previous["katex"].get("asset_version") == KATEX_ASSET_VERSION
        )
        graph_state_matches = (
            previous_graph is not None
            and previous_graph.get("asset_version") == GRAPH_ASSET_VERSION
        )

        # Collect directories
        directories: list[str] = [content_root]
        for dirpath, dirnames, _ in os.walk(content_root, followlinks=False):
            for dirname in dirnames:
                directories.append(os.path.join(dirpath, dirname))

        current_output_paths: dict[str, bool] = {}
        for f in markdown_files:
            rel = get_kb_static_relative_path(content_root, f)
            current_output_paths[get_kb_static_page_output_path(rel)] = True

        for d in directories:
            if os.path.isfile(os.path.join(d, "index.md")):
                continue
            rel = get_kb_static_relative_path(content_root, d)
            dir_output = "index.html" if not rel or rel == "." else f"{rel}/index.html"
            current_output_paths[dir_output] = True

        if "kb-navigation.html" in current_output_paths:
            raise RuntimeError("BLOCKER: source contains reserved navigation page name: kb-navigation.html")
        current_output_paths["kb-navigation.html"] = True

        # Preflight destination file ownership check
        previous_owned_outputs: dict[str, bool] = {}
        previous_records_to_check: list[dict[str, Any]] = (
            list(previous_pages.values())
            + list(previous_directories.values())
            + list(previous_katex_assets.values())
            + list(previous_graph_assets.values())
            + list(previous_graph_data_assets.values())
        )
        if (
            previous_graph
            and "navigation_page" in previous_graph
            and previous_graph["navigation_page"].get("output_path")
        ):
            previous_records_to_check.append(previous_graph["navigation_page"])

        for rec in previous_records_to_check:
            rel = str(rec.get("output_path", "")).strip()
            if rel and not os.path.isabs(rel) and not re.search(r"(^|[\\/])\.\.([\\/]|$)", rel):
                previous_owned_outputs[rel] = True

        for rel in current_output_paths:
            cand = os.path.normpath(os.path.join(dest_full, rel.replace("/", os.sep)))
            if not test_path_inside_root(cand, dest_full):
                raise RuntimeError(f"BLOCKER: static output path escapes destination: {rel}")
            if os.path.isdir(cand):
                raise RuntimeError(f"BLOCKER: static output path is an existing directory: {rel}")
            if os.path.isfile(cand) and rel not in previous_owned_outputs:
                raise RuntimeError(
                    f"BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: {rel}"
                )

        for asset in katex_assets:
            cand = os.path.normpath(
                os.path.join(dest_full, asset["output_path"].replace("/", os.sep))
            )
            if not test_path_inside_root(cand, dest_full):
                raise RuntimeError(
                    f"BLOCKER: KaTeX asset output path escapes destination: {asset['output_path']}"
                )
            if os.path.isdir(cand):
                raise RuntimeError(
                    f"BLOCKER: KaTeX asset output is an existing directory: {asset['output_path']}"
                )
            if os.path.isfile(cand) and asset["output_path"] not in previous_owned_outputs:
                raise RuntimeError(
                    f"BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: {asset['output_path']}"
                )

        graph_preflight_paths = [a["output_path"] for a in graph_assets]
        graph_preflight_paths.extend(
            ["_assets/graph/graph-data.js", "_assets/graph/graph-previews.js"]
        )
        for rel in graph_preflight_paths:
            cand = os.path.normpath(os.path.join(dest_full, rel.replace("/", os.sep)))
            if not test_path_inside_root(cand, dest_full):
                raise RuntimeError(f"BLOCKER: Graph asset output path escapes destination: {rel}")
            if os.path.isdir(cand):
                raise RuntimeError(f"BLOCKER: Graph asset output is an existing directory: {rel}")
            if os.path.isfile(cand) and rel not in previous_owned_outputs:
                raise RuntimeError(
                    f"BLOCKER: refusing to overwrite destination file not owned by a prior static-site manifest: {rel}"
                )

        generated: list[str] = []
        skipped: list[str] = []
        removed: list[str] = []
        asset_generated: list[str] = []
        asset_skipped: list[str] = []
        asset_records: list[dict[str, Any]] = []
        graph_asset_generated: list[str] = []
        graph_asset_skipped: list[str] = []
        graph_asset_records: list[dict[str, Any]] = []
        graph_data_asset_records: list[dict[str, Any]] = []

        # KaTeX assets
        for asset in katex_assets:
            output_path = os.path.normpath(
                os.path.join(dest_full, asset["output_path"].replace("/", os.sep))
            )
            old = previous_katex_assets.get(asset["source_path"])
            can_skip = (
                not force
                and katex_state_matches
                and old is not None
                and old.get("sha256") == asset["sha256"]
                and old.get("output_path") == asset["output_path"]
                and os.path.isfile(output_path)
            )
            if can_skip and old.get("output_sha256"):
                can_skip = old["output_sha256"] == get_kb_static_sha256(output_path)

            if can_skip:
                output_hash = get_kb_static_sha256(output_path)
                asset_skipped.append(asset["output_path"])
            else:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copyfile(asset["full_path"], output_path)
                output_hash = get_kb_static_sha256(output_path)
                if output_hash != asset["sha256"]:
                    raise RuntimeError(
                        f"BLOCKER: copied KaTeX asset hash does not match source: {asset['source_path']}"
                    )
                asset_generated.append(asset["output_path"])

            asset_records.append(
                {
                    "source_path": asset["source_path"],
                    "output_path": asset["output_path"],
                    "sha256": asset["sha256"],
                    "output_sha256": output_hash,
                }
            )

        # Graph static assets (graph.css, graph.js)
        for asset in graph_assets:
            output_path = os.path.normpath(
                os.path.join(dest_full, asset["output_path"].replace("/", os.sep))
            )
            old = previous_graph_assets.get(asset["source_path"])
            can_skip = (
                not force
                and graph_state_matches
                and old is not None
                and old.get("sha256") == asset["sha256"]
                and old.get("output_path") == asset["output_path"]
                and os.path.isfile(output_path)
            )
            if can_skip and old.get("output_sha256"):
                can_skip = old["output_sha256"] == get_kb_static_sha256(output_path)

            if can_skip:
                output_hash = get_kb_static_sha256(output_path)
                graph_asset_skipped.append(asset["output_path"])
            else:
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                shutil.copyfile(asset["full_path"], output_path)
                output_hash = get_kb_static_sha256(output_path)
                if output_hash != asset["sha256"]:
                    raise RuntimeError(
                        f"BLOCKER: copied Graph asset hash does not match source: {asset['source_path']}"
                    )
                graph_asset_generated.append(asset["output_path"])

            graph_asset_records.append(
                {
                    "source_path": asset["source_path"],
                    "output_path": asset["output_path"],
                    "sha256": asset["sha256"],
                    "output_sha256": output_hash,
                }
            )

        # Graph data script: _assets/graph/graph-data.js
        graph_data_output_rel = "_assets/graph/graph-data.js"
        graph_data_full = os.path.normpath(
            os.path.join(dest_full, graph_data_output_rel.replace("/", os.sep))
        )
        old_graph_data = previous_graph_data_assets.get(graph_data_output_rel)
        can_skip_graph_data = (
            not force
            and previous_graph is not None
            and previous_graph.get("graph_digest") == graph_model.graph_data["graph_digest"]
            and os.path.isfile(graph_data_full)
        )
        if can_skip_graph_data and old_graph_data and old_graph_data.get("output_sha256"):
            can_skip_graph_data = (
                old_graph_data["output_sha256"] == get_kb_static_sha256(graph_data_full)
            )

        if can_skip_graph_data:
            graph_data_hash = get_kb_static_sha256(graph_data_full)
            graph_asset_skipped.append(graph_data_output_rel)
        else:
            os.makedirs(os.path.dirname(graph_data_full), exist_ok=True)
            js_code = convert_to_graph_javascript(graph_model.graph_data)
            with open(graph_data_full, "w", encoding="utf-8", newline="\n") as f:
                f.write(js_code)
            graph_data_hash = get_kb_static_sha256(graph_data_full)
            graph_asset_generated.append(graph_data_output_rel)

        graph_data_asset_records.append(
            {
                "source_path": "generated:graph-data.js",
                "output_path": graph_data_output_rel,
                "output_sha256": graph_data_hash,
            }
        )

        # Graph preview script: _assets/graph/graph-previews.js
        graph_previews_output_rel = "_assets/graph/graph-previews.js"
        graph_previews_full = os.path.normpath(
            os.path.join(dest_full, graph_previews_output_rel.replace("/", os.sep))
        )
        old_graph_previews = previous_graph_data_assets.get(graph_previews_output_rel)
        can_skip_graph_previews = (
            not force
            and previous_graph is not None
            and previous_graph.get("preview_digest") == graph_model.preview_data["preview_digest"]
            and os.path.isfile(graph_previews_full)
        )
        if can_skip_graph_previews and old_graph_previews and old_graph_previews.get("output_sha256"):
            can_skip_graph_previews = (
                old_graph_previews["output_sha256"] == get_kb_static_sha256(graph_previews_full)
            )

        if can_skip_graph_previews:
            graph_previews_hash = get_kb_static_sha256(graph_previews_full)
            graph_asset_skipped.append(graph_previews_output_rel)
        else:
            os.makedirs(os.path.dirname(graph_previews_full), exist_ok=True)
            js_code = convert_to_graph_previews_javascript(graph_model.preview_data)
            with open(graph_previews_full, "w", encoding="utf-8", newline="\n") as f:
                f.write(js_code)
            graph_previews_hash = get_kb_static_sha256(graph_previews_full)
            graph_asset_generated.append(graph_previews_output_rel)

        graph_data_asset_records.append(
            {
                "source_path": "generated:graph-previews.js",
                "output_path": graph_previews_output_rel,
                "output_sha256": graph_previews_hash,
            }
        )

        # Navigation page: kb-navigation.html
        nav_page_output_rel = "kb-navigation.html"
        nav_page_full = os.path.normpath(os.path.join(dest_full, nav_page_output_rel))
        old_nav_page = (
            previous_graph.get("navigation_page")
            if previous_graph and "navigation_page" in previous_graph
            else None
        )
        can_skip_nav_page = (
            not force
            and state_matches
            and old_nav_page is not None
            and old_nav_page.get("output_path") == nav_page_output_rel
            and os.path.isfile(nav_page_full)
        )
        if can_skip_nav_page and old_nav_page and old_nav_page.get("output_sha256"):
            can_skip_nav_page = old_nav_page["output_sha256"] == get_kb_static_sha256(nav_page_full)

        if can_skip_nav_page:
            nav_page_hash = get_kb_static_sha256(nav_page_full)
            skipped.append(nav_page_output_rel)
        else:
            nav_page_html = new_kb_static_navigation_page_html()
            with open(nav_page_full, "w", encoding="utf-8", newline="\n") as f:
                f.write(nav_page_html)
            nav_page_hash = get_kb_static_sha256(nav_page_full)
            generated.append(nav_page_output_rel)

        navigation_page_record = {
            "output_path": nav_page_output_rel,
            "output_sha256": nav_page_hash,
        }

        # Render Markdown pages
        md_parser = create_static_markdown_parser()
        page_records: list[dict[str, Any]] = []

        for f in markdown_files:
            source_rel = get_kb_static_relative_path(content_root, f)
            output_rel = get_kb_static_page_output_path(source_rel)
            current_output_paths[output_rel] = True
            source_hash = get_kb_static_sha256(f)
            output_full = os.path.normpath(
                os.path.join(dest_full, output_rel.replace("/", os.sep))
            )
            old = previous_pages.get(source_rel)

            can_skip = (
                not force
                and state_matches
                and old is not None
                and old.get("sha256") == source_hash
                and old.get("output_path") == output_rel
                and os.path.isfile(output_full)
            )
            if can_skip and old.get("output_sha256"):
                can_skip = old["output_sha256"] == get_kb_static_sha256(output_full)

            if can_skip:
                output_hash = get_kb_static_sha256(output_full)
                skipped.append(output_rel)
            else:
                with open(f, "r", encoding="utf-8") as rf:
                    raw_text = rf.read()
                body = get_kb_static_body(raw_text)
                rewritten = convert_kb_static_links(
                    body, source_file=f, content_root=content_root
                )
                rendered_markup = md_parser.render(rewritten)
                rendered_markup = transform_github_alerts(rendered_markup)
                owner_page_id = page_node_ids.get(source_rel, "")
                anchor_res = update_heading_anchors(
                    rendered_markup, owner_page_id=owner_page_id, source_path=source_rel
                )
                is_home = source_rel == entrypoint_relative
                page_title = navigation.pages[source_rel].title
                doc_html = new_kb_static_html_document(
                    title=page_title,
                    body_html=anchor_res.html,
                    output_relative=output_rel,
                    navigation=navigation,
                    source_relative=source_rel,
                    is_home=is_home,
                    page_node_id=owner_page_id,
                    inbox_count=inbox_count,
                )

                os.makedirs(os.path.dirname(output_full), exist_ok=True)
                with open(output_full, "w", encoding="utf-8", newline="\n") as wf:
                    wf.write(doc_html)
                output_hash = get_kb_static_sha256(output_full)
                generated.append(output_rel)

            page_records.append(
                {
                    "source_path": source_rel,
                    "output_path": output_rel,
                    "sha256": source_hash,
                    "output_sha256": output_hash,
                }
            )

        # Directory index generation
        directory_records: list[dict[str, Any]] = []
        directory_titles = {
            "projects": "全部项目",
            "maps": "全部主题",
            "knowledge": "全部知识条目",
            "sources": "全部来源",
            "decisions": "全部决策",
            "inbox": "收件箱",
            "archive": "归档",
            "assets": "附件",
        }

        for d in sorted(directories):
            d_rel = get_kb_static_relative_path(content_root, d)
            output_rel = "index.html" if not d_rel or d_rel == "." else f"{d_rel}/index.html"
            dir_index_source = os.path.join(d, "index.md")
            if os.path.isfile(dir_index_source):
                continue
            current_output_paths[output_rel] = True
            structure_hash = get_kb_static_directory_hash(d, content_root)
            output_full = os.path.normpath(
                os.path.join(dest_full, output_rel.replace("/", os.sep))
            )
            old = previous_directories.get(output_rel)

            can_skip = (
                not force
                and state_matches
                and old is not None
                and old.get("structure_sha256") == structure_hash
                and os.path.isfile(output_full)
            )
            if can_skip and old.get("output_sha256"):
                can_skip = old["output_sha256"] == get_kb_static_sha256(output_full)

            if can_skip:
                output_hash = get_kb_static_sha256(output_full)
                skipped.append(output_rel)
            else:
                items: list[str] = []
                is_type_dir = d_rel in directory_titles

                if is_type_dir:
                    child_mds = []
                    for root_d, _, filenames in os.walk(d, followlinks=False):
                        for fn in filenames:
                            if fn.lower().endswith(".md"):
                                child_mds.append(os.path.join(root_d, fn))
                    child_mds.sort()
                    for cmd in child_mds:
                        c_rel = get_kb_static_relative_path(content_root, cmd)
                        href = get_static_navigation_href(
                            output_rel, navigation.pages[c_rel].output
                        )
                        label = navigation.pages[c_rel].title
                        items.append(
                            f'<li><a href="{html.escape(href)}">{html.escape(label)}</a></li>'
                        )
                else:
                    try:
                        dir_entries = list(os.scandir(d))
                        dir_entries.sort(key=lambda e: (not e.is_dir(follow_symlinks=False), e.name))
                    except Exception:
                        dir_entries = []

                    for entry in dir_entries:
                        c_rel = get_kb_static_relative_path(content_root, entry.path)
                        if entry.is_dir(follow_symlinks=False):
                            href = get_static_navigation_href(
                                output_rel, f"{c_rel}/index.html"
                            )
                            label = directory_titles.get(c_rel, f"{entry.name}/")
                            items.append(
                                f'<li><a href="{html.escape(href)}">{html.escape(label)}</a></li>'
                            )
                        elif entry.name.lower().endswith(".md"):
                            href = get_static_navigation_href(
                                output_rel, navigation.pages[c_rel].output
                            )
                            label = navigation.pages[c_rel].title
                            items.append(
                                f'<li><a href="{html.escape(href)}">{html.escape(label)}</a></li>'
                            )

                heading = (
                    "文件目录"
                    if not d_rel or d_rel == "."
                    else directory_titles.get(d_rel, os.path.basename(d))
                )

                if is_type_dir and d_rel == "inbox" and len(items) == 0:
                    body_content = (
                        f"<h1>{html.escape(heading)}</h1>"
                        f'<p class="kb-inbox-empty" style="color:#60758a;margin:1.5rem 0;">收件箱为空，暂无待整理笔记。</p>'
                    )
                else:
                    items_joined = "\n".join(items)
                    body_content = f"<h1>{html.escape(heading)}</h1><ul>{items_joined}</ul>"

                dir_html = new_kb_static_html_document(
                    title=heading,
                    body_html=body_content,
                    output_relative=output_rel,
                    navigation=navigation,
                    is_home=False,
                    page_node_id="",
                )

                os.makedirs(os.path.dirname(output_full), exist_ok=True)
                with open(output_full, "w", encoding="utf-8", newline="\n") as wf:
                    wf.write(dir_html)
                output_hash = get_kb_static_sha256(output_full)
                generated.append(output_rel)

            directory_records.append(
                {
                    "output_path": output_rel,
                    "structure_sha256": structure_hash,
                    "output_sha256": output_hash,
                }
            )

        # Cleanup obsolete pages from previous manifest
        for old_page in previous_pages.values():
            rel_out = str(old_page.get("output_path", ""))
            if rel_out in current_output_paths:
                continue
            if not rel_out or os.path.isabs(rel_out) or re.search(r"(^|[\\/])\.\.([\\/]|$)", rel_out):
                continue
            cand = os.path.normpath(os.path.join(dest_full, rel_out.replace("/", os.sep)))
            if (
                test_path_inside_root(cand, dest_full)
                and os.path.isfile(cand)
                and old_page.get("output_sha256")
                and get_kb_static_sha256(cand) == str(old_page["output_sha256"])
            ):
                os.remove(cand)
                removed.append(rel_out)

        for old_dir in previous_directories.values():
            rel_out = str(old_dir.get("output_path", ""))
            if rel_out in current_output_paths:
                continue
            if not rel_out or os.path.isabs(rel_out) or re.search(r"(^|[\\/])\.\.([\\/]|$)", rel_out):
                continue
            cand = os.path.normpath(os.path.join(dest_full, rel_out.replace("/", os.sep)))
            if (
                test_path_inside_root(cand, dest_full)
                and os.path.isfile(cand)
                and old_dir.get("output_sha256")
                and get_kb_static_sha256(cand) == str(old_dir["output_sha256"])
            ):
                os.remove(cand)
                removed.append(rel_out)

        current_katex_sources = {a["source_path"]: True for a in katex_assets}
        for old_asset in previous_katex_assets.values():
            if old_asset.get("source_path") in current_katex_sources:
                continue
            rel_out = str(old_asset.get("output_path", ""))
            if (
                not rel_out
                or not rel_out.startswith("_assets/katex/")
                or os.path.isabs(rel_out)
                or re.search(r"(^|[\\/])\.\.([\\/]|$)", rel_out)
            ):
                continue
            cand = os.path.normpath(os.path.join(dest_full, rel_out.replace("/", os.sep)))
            if not test_path_inside_root(cand, dest_full) or not os.path.isfile(cand):
                continue
            if not old_asset.get("output_sha256"):
                continue
            if get_kb_static_sha256(cand) != str(old_asset["output_sha256"]):
                continue
            os.remove(cand)
            removed.append(rel_out)

        current_graph_sources = {a["source_path"]: True for a in graph_assets}
        for old_asset in previous_graph_assets.values():
            if old_asset.get("source_path") in current_graph_sources:
                continue
            rel_out = str(old_asset.get("output_path", ""))
            if (
                not rel_out
                or not rel_out.startswith("_assets/graph/")
                or os.path.isabs(rel_out)
                or re.search(r"(^|[\\/])\.\.([\\/]|$)", rel_out)
            ):
                continue
            cand = os.path.normpath(os.path.join(dest_full, rel_out.replace("/", os.sep)))
            if not test_path_inside_root(cand, dest_full) or not os.path.isfile(cand):
                continue
            if not old_asset.get("output_sha256"):
                continue
            if get_kb_static_sha256(cand) != str(old_asset["output_sha256"]):
                continue
            os.remove(cand)
            removed.append(rel_out)

        # Write new manifest
        new_manifest = {
            "schema": "knowledge-base-static-site",
            "schema_version": 1,
            "generator_version": GENERATOR_VERSION,
            "template_version": TEMPLATE_VERSION,
            "navigation_digest": navigation.digest,
            "root_content_dir": content_root,
            "entry_source_path": entrypoint_relative,
            "entry_output_path": entry_output_relative,
            "generated_utc": datetime.datetime.now(datetime.timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "katex": {
                "asset_version": KATEX_ASSET_VERSION,
                "assets": sorted(asset_records, key=lambda x: x["source_path"]),
            },
            "graph": {
                "asset_version": GRAPH_ASSET_VERSION,
                "graph_digest": graph_model.graph_data["graph_digest"],
                "preview_digest": graph_model.preview_data["preview_digest"],
                "navigation_page": navigation_page_record,
                "assets": sorted(graph_asset_records, key=lambda x: x["source_path"]),
                "data_assets": sorted(graph_data_asset_records, key=lambda x: x["output_path"]),
            },
            "pages": sorted(page_records, key=lambda x: x["source_path"]),
            "directories": sorted(directory_records, key=lambda x: x["output_path"]),
        }

        with open(manifest_path, "w", encoding="utf-8", newline="\n") as mf:
            json.dump(new_manifest, mf, ensure_ascii=False, indent=2)

        entry_full_out = os.path.normpath(
            os.path.join(dest_full, entry_output_relative.replace("/", os.sep))
        )
        data = {
            "status": "success",
            "root": root_full,
            "destination": dest_full,
            "manifest": MANIFEST_NAME,
            "entry_page": entry_full_out,
            "generator_version": GENERATOR_VERSION,
            "template_version": TEMPLATE_VERSION,
            "force_rebuild": bool(force),
            "generated": len(generated),
            "generated_paths": generated,
            "skipped": len(skipped),
            "skipped_paths": skipped,
            "removed": len(removed),
            "removed_paths": removed,
            "assets_generated": len(asset_generated),
            "assets_generated_paths": asset_generated,
            "assets_skipped": len(asset_skipped),
            "assets_skipped_paths": asset_skipped,
            "graph_assets_generated": len(graph_asset_generated),
            "graph_assets_generated_paths": graph_asset_generated,
            "graph_assets_skipped": len(graph_asset_skipped),
            "graph_assets_skipped_paths": graph_asset_skipped,
        }
        return 0, Envelope(command="build-static", status="success", root=root_full, data=data)

    except Exception as exc:
        msg = str(exc)
        return 2, Envelope(
            command="build-static",
            status="blocked",
            root=root_full,
            data={"status": "blocked", "message": msg},
            diagnostics=[
                Diagnostic(
                    code="BUILD_BLOCKED",
                    severity="error",
                    file=None,
                    span=None,
                    target=None,
                    message=msg,
                )
            ],
        )
