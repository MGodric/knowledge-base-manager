"""Shared Markdown parser for the static reader and graph preview model."""

from __future__ import annotations

import re

from markdown_it import MarkdownIt
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin
from mdit_py_plugins.tasklists import tasklists_plugin

from .markdown_reader import patch_dollarmath_block_rule


def create_static_markdown_parser() -> MarkdownIt:
    """Create the parser used by both rendered pages and graph extraction."""
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
    patch_dollarmath_block_rule(md, allow_labels=False, allow_blank_lines=True)
    md.validateLink = lambda url: not bool(
        re.match(r"^(javascript|vbscript):", url.strip().lower())
    )

    orig_th_open = md.renderer.rules.get("th_open")

    def render_th_open(self, tokens, idx, options, env):
        token = tokens[idx]
        style = token.attrGet("style")
        if style:
            token.attrSet("style", re.sub(r"text-align:\s*(\w+)", r"text-align: \1;", style))
        if orig_th_open:
            return orig_th_open(self, tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    orig_td_open = md.renderer.rules.get("td_open")

    def render_td_open(self, tokens, idx, options, env):
        token = tokens[idx]
        style = token.attrGet("style")
        if style:
            token.attrSet("style", re.sub(r"text-align:\s*(\w+)", r"text-align: \1;", style))
        if orig_td_open:
            return orig_td_open(self, tokens, idx, options, env)
        return self.renderToken(tokens, idx, options, env)

    md.add_render_rule("th_open", render_th_open)
    md.add_render_rule("td_open", render_td_open)

    orig_table_open = md.renderer.rules.get("table_open")
    orig_table_close = md.renderer.rules.get("table_close")

    def render_table_open(self, tokens, idx, options, env):
        base = orig_table_open(self, tokens, idx, options, env) if orig_table_open else self.renderToken(tokens, idx, options, env)
        return f'<div class="kb-table-wrap">{base}'

    def render_table_close(self, tokens, idx, options, env):
        base = orig_table_close(self, tokens, idx, options, env) if orig_table_close else self.renderToken(tokens, idx, options, env)
        return f'{base}</div>'

    md.add_render_rule("table_open", render_table_open)
    md.add_render_rule("table_close", render_table_close)
    md.add_render_rule("s_open", lambda self, tokens, idx, options, env: "<del>")
    md.add_render_rule("s_close", lambda self, tokens, idx, options, env: "</del>")

    def render_math_inline(self, tokens, idx, options, env):
        return f'<span class="math">\\({tokens[idx].content}\\)</span>'

    def render_math_block(self, tokens, idx, options, env):
        return f'<div class="math">\\[\n{tokens[idx].content}\n\\]</div>\n'

    md.add_render_rule("math_inline", render_math_inline)
    md.add_render_rule("math_block", render_math_block)

    def render_footnote_ref(self, tokens, idx, options, env):
        ident = tokens[idx].meta["id"] + 1
        sub_id = tokens[idx].meta["subId"]
        id_str = f"fnref{ident}" + (f":{sub_id}" if sub_id > 0 else "")
        return f'<a class="footnote-ref" id="{id_str}" href="#fn{ident}"><sup>{ident}</sup></a>'

    def render_footnote_block_open(self, tokens, idx, options, env):
        return '<div class="footnotes">\n<hr class="footnotes-sep">\n<ol class="footnotes-list">\n'

    def render_footnote_block_close(self, tokens, idx, options, env):
        return "</ol>\n</div>\n"

    md.add_render_rule("footnote_ref", render_footnote_ref)
    md.add_render_rule("footnote_block_open", render_footnote_block_open)
    md.add_render_rule("footnote_block_close", render_footnote_block_close)
    return md
