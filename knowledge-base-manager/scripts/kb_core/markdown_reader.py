"""Markdown parser and reader using markdown-it-py and plugins."""

from __future__ import annotations

import html
import re
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.rules_inline import StateInline
from markdown_it.token import Token
from mdit_py_plugins.dollarmath import dollarmath_plugin
from mdit_py_plugins.footnote import footnote_plugin

from .model import Diagnostic, LinkOccurrence, Section, SourceDeclaration


def create_markdown_parser() -> MarkdownIt:
    """Create and configure the project markdown-it-py parser."""
    md = (
        MarkdownIt("commonmark")
        .enable("table")
        .enable("strikethrough")
        .use(footnote_plugin, inline=False, move_to_end=False)
        .use(
            dollarmath_plugin,
            allow_labels=False,
            allow_space=True,
            allow_digits=True,
            allow_blank_lines=True,
            double_inline=False,
        )
    )

    orig_parse = md.helpers.parseLinkDestination

    def custom_parse(string: str, pos: int, maximum: int):
        if pos < maximum and string[pos] == "<":
            return orig_parse(string, pos, maximum)
        res = orig_parse(string, pos, maximum)
        if res.ok:
            p = res.pos
            while p < maximum and string[p] in (" ", "\t", "\n"):
                p += 1
            if p < maximum and string[p] == ")":
                return res
            if p < maximum and string[p] in ('"', "'", "("):
                return res

        level = 0
        p = pos
        while p < maximum:
            ch = string[p]
            if ch == "(":
                level += 1
            elif ch == ")":
                if level == 0:
                    break
                level -= 1
            elif ch == "\n":
                break
            p += 1
        if p > pos and level == 0 and p < maximum and string[p] == ")":
            res.str = string[pos:p].strip()
            res.pos = p
            res.ok = True
            return res

        return res

    md.helpers.parseLinkDestination = custom_parse
    _enable_inline_source_spans(md)
    return md


_SOURCE_START_META = "kb_source_start"
_SOURCE_END_META = "kb_source_end"


def _enable_inline_source_spans(md: MarkdownIt) -> None:
    """Record source offsets while markdown-it performs the real inline parse.

    Child token content is normalized by markdown-it (notably multiline code spans),
    so consumers cannot recover source positions from ``Token.content``.  This wrapper
    records the rule's input range on the tokens created by that rule instead.
    Offsets are relative to the containing inline block's original ``content``.
    """

    def annotate_new_tokens(
        state: StateInline, token_start: int, source_start: int, source_end: int
    ) -> None:
        new_tokens = state.tokens[token_start:]

        # Atomic syntax tokens are created by one rule invocation.
        for token in new_tokens:
            if token.type in (
                "code_inline",
                "math_inline",
                "math_inline_double",
                "image",
            ) and _SOURCE_START_META not in token.meta:
                token.meta[_SOURCE_START_META] = source_start
                token.meta[_SOURCE_END_META] = source_end

        # Link parsing recursively tokenizes its label.  The outer rule invocation
        # is the only one whose range covers the complete Markdown link syntax.
        for token in new_tokens:
            if token.type == "link_open" and _SOURCE_START_META not in token.meta:
                token.meta[_SOURCE_START_META] = source_start
                token.meta[_SOURCE_END_META] = source_end
                break

    ruler = md.inline.ruler
    rule_names = ruler.get_active_rules()
    active_rules = ruler.getRules("")
    rules_by_name = dict(zip(rule_names, active_rules, strict=True))

    # Wrap only rules whose exact source syntax the reader consumes.  The parser's
    # own tokenizer, nesting behavior, silent lookahead and backtracking remain
    # untouched.  The wrappers belong solely to this configured parser instance.
    for rule_name in ("math_inline", "backticks", "link", "image", "autolink"):
        original_rule = rules_by_name.get(rule_name)
        if original_rule is None:
            continue

        def source_mapped_rule(
            state: StateInline,
            silent: bool,
            original=original_rule,
        ) -> bool:
            source_start = state.pos
            token_start = len(state.tokens)
            matched = original(state, silent)
            if matched and not silent:
                annotate_new_tokens(state, token_start, source_start, state.pos)
            return matched

        ruler.at(rule_name, source_mapped_rule)


_MATH_RE_PATTERNS = [
    re.compile(r"(?i)^GF\s*\(\s*2\s*\^\s*\d+\s*\)$"),
    re.compile(r"(?i)^P\s*\([^)]*=.*\|.*\)$"),
    re.compile(
        r"(?i)^(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|tau|phi|psi|omega)\s*\([^)]*\)$"
    ),
    re.compile(r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9{}]+\s*="),
    re.compile(
        r"(?<![:A-Za-z0-9_.-])\\(?:alpha|beta|gamma|delta|epsilon|theta|lambda|mu|sigma|tau|phi|psi|omega|frac|sqrt|sum|prod|int|mathrm|mathbf|mathbb|mathcal|left|right|cdot|times|leq|geq|neq|in|notin|subset|subseteq|cup|cap|to|rightarrow|ldots|dots)\b"
    ),
    re.compile(r"[α-ωΑ-Ω∑∏√∞≈≠≤≥∈∉⊂⊆∪∩→←↔⇒⇔±×÷·∘⊕⊗∂∇∀∃∅∧∨¬]"),
]


def test_high_confidence_math(content: str) -> bool:
    val = content.strip()
    if not val:
        return False
    if re.match(r"^[A-Za-z]:[\\/]", val) or val.startswith(r"\\"):
        return False
    return any(p.search(val) is not None for p in _MATH_RE_PATTERNS)


def test_explicit_external_local_label(line: str) -> bool:
    if re.search(r"(?i)kb-external-local", line):
        return True
    if "知识库外" in line and any(k in line for k in ("仅本机", "机器相关", "本机专用")):
        return True
    return bool(
        re.search(r"(?i)outside\s+(the\s+)?knowledge\s+base", line)
        and re.search(r"(?i)machine[- ]specific|local[- ]only", line)
    )


_CONTROL_FIELD_NAME = (
    r"(?:verified|last\s+verified|验证日期|已验证|revision|"
    r"version[-_ ]?state|版本状态|版本|project[-_ ]?id|项目标识|"
    r"project[-_ ]?relative(?:\s+source)?|项目相对路径|相对路径)"
)
_SOURCE_TOKEN_RE = re.compile(
    r"(?i)(?:verified|last\s+verified|验证日期|已验证|revision|"
    r"version[-_ ]?state|版本状态|版本|project[-_ ]?id|项目标识|"
    r"kb-external-local)"
)
_CONTROL_FIELD_LABEL_RE = re.compile(rf"(?i){_CONTROL_FIELD_NAME}\s*[:：]")
_CONTROL_FIELD_BEFORE_CODE_RE = re.compile(
    rf"(?i)^\s*{_CONTROL_FIELD_NAME}\s*[:：]\s*$"
)
_WHOLE_CODE_CONTROL_FIELD_RE = re.compile(
    rf"(?is)^\s*{_CONTROL_FIELD_NAME}\s*[:：]\s*[^;；\r\n]+[;；]?\s*$"
)


def _mask_source_interval(chars: list[str], start: int, end: int) -> None:
    """Mask a parser-confirmed syntax interval while retaining newline offsets."""
    for index in range(max(0, start), min(end, len(chars))):
        if chars[index] not in ("\r", "\n"):
            chars[index] = " "


def _code_token_can_supply_source_field(
    source: str, start: int, end: int, content: str
) -> bool:
    """Allow established field-code forms, but reject code examples.

    Supported forms are ``field: `value``` and a code span containing exactly one
    complete ``field: value``.  The decision uses the parser-confirmed code span;
    it never reparses arbitrary backtick ranges.
    """
    raw_code = source[start:end]
    if "\n" in raw_code or "\r" in raw_code:
        return False

    line_start = max(source.rfind("\n", 0, start), source.rfind("\r", 0, start)) + 1
    prefix = source[line_start:start]
    field_boundary = max(prefix.rfind(";"), prefix.rfind("；")) + 1
    local_prefix = prefix[field_boundary:]

    stripped_content = content.strip()
    if (
        not local_prefix.strip()
        and len(_CONTROL_FIELD_LABEL_RE.findall(stripped_content)) == 1
        and _WHOLE_CODE_CONTROL_FIELD_RE.fullmatch(stripped_content)
    ):
        return True

    return _CONTROL_FIELD_BEFORE_CODE_RE.fullmatch(local_prefix) is not None


def _inline_source_projection(token: Token) -> str:
    """Return inline source with only parser-recognized code/math regions masked."""
    source = token.content or ""
    chars = list(source)
    for child in token.children or []:
        if child.type not in (
            "code_inline",
            "math_inline",
            "math_inline_double",
        ):
            continue
        start = child.meta.get(_SOURCE_START_META)
        end = child.meta.get(_SOURCE_END_META)
        if not isinstance(start, int) or not isinstance(end, int):
            # Missing parser source metadata makes this block unsafe for field
            # extraction.  Mask it completely rather than infer delimiters.
            return "".join("\n" if ch == "\n" else " " for ch in source)
        if child.type == "code_inline" and _code_token_can_supply_source_field(
            source, start, end, child.content or ""
        ):
            continue
        _mask_source_interval(chars, start, end)
    return "".join(chars)


def _inline_support_projection(token: Token) -> str | None:
    """Mask every parser-confirmed code/math region for support-field locating.

    Unlike the source-field projection, support text must retain inline Markdown in
    its returned value.  This view is used only to locate a support label and its
    boundary; its offsets therefore remain aligned with the original inline source.
    A missing source span cannot safely supply those offsets, so callers fail closed.
    """
    source = token.content or ""
    chars = list(source)
    for child in token.children or []:
        if child.type not in (
            "code_inline",
            "math_inline",
            "math_inline_double",
        ):
            continue
        start = child.meta.get(_SOURCE_START_META)
        end = child.meta.get(_SOURCE_END_META)
        if (
            not isinstance(start, int)
            or not isinstance(end, int)
            or start < 0
            or end <= start
            or end > len(source)
        ):
            return None
        _mask_source_interval(chars, start, end)
    return "".join(chars)


def _inline_line_map(token: Token) -> list[int] | None:
    """Map parent inline-content lines to document lines when the block map is exact."""
    if not token.map:
        return None
    source_line_count = (token.content or "").count("\n") + 1
    block_line_count = token.map[1] - token.map[0]
    if source_line_count != block_line_count:
        return None
    return [token.map[0] + offset + 1 for offset in range(source_line_count)]


def _inline_projected_lines(token: Token) -> dict[int, str] | None:
    line_map = _inline_line_map(token)
    if line_map is None:
        return None
    projected = _inline_source_projection(token).split("\n")
    if len(projected) != len(line_map):
        return None
    return dict(zip(line_map, projected, strict=True))


def _inline_support_source_lines(token: Token) -> dict[int, tuple[str, str]] | None:
    """Return aligned support projection and original inline source by document line."""
    line_map = _inline_line_map(token)
    projection = _inline_support_projection(token)
    if line_map is None or projection is None:
        return None
    projected_lines = projection.split("\n")
    source_lines = (token.content or "").split("\n")
    if len(projected_lines) != len(line_map) or len(source_lines) != len(line_map):
        return None
    return dict(
        zip(line_map, zip(projected_lines, source_lines, strict=True), strict=True)
    )


_SUPPORT_FIELD_LABEL_RE = re.compile(
    r"(?i)(?:supports?|支持范围|支持)\s*[:：]"
)
_SUPPORT_FIELD_END_RE = re.compile(r"[;；]")


def _support_text_from_aligned_line(
    projected_line: str, source_line: str
) -> str | None:
    """Extract the first real support field while preserving its original Markdown."""
    if len(projected_line) != len(source_line):
        return None
    match = _SUPPORT_FIELD_LABEL_RE.search(projected_line)
    if match is None:
        return None
    value_start = match.end()
    while value_start < len(source_line) and source_line[value_start].isspace():
        value_start += 1
    end_match = _SUPPORT_FIELD_END_RE.search(projected_line, value_start)
    end = end_match.start() if end_match else len(projected_line)
    return source_line[value_start:end].strip() or None


def _token_source_document_span(
    inline_token: Token, child: Token
) -> tuple[int, int] | None:
    """Map a child rule's recorded source offsets to document line numbers."""
    line_map = _inline_line_map(inline_token)
    start = child.meta.get(_SOURCE_START_META)
    end = child.meta.get(_SOURCE_END_META)
    if line_map is None or not isinstance(start, int) or not isinstance(end, int):
        return None
    source = inline_token.content or ""
    if start < 0 or end <= start or end > len(source):
        return None
    start_index = source.count("\n", 0, start)
    end_index = source.count("\n", 0, end - 1)
    if start_index >= len(line_map) or end_index >= len(line_map):
        return None
    return line_map[start_index], line_map[end_index]




class ParsedMarkdownPage:
    def __init__(
        self,
        raw_text: str,
        lines: list[str],
        front_matter_present: bool,
        front_matter_end_line: int,
        front_matter_fields: dict[str, Any],
        tokens: list[Token],
    ) -> None:
        self.raw_text = raw_text
        self.lines = lines
        self.front_matter_present = front_matter_present
        self.front_matter_end_line = front_matter_end_line
        self.front_matter_fields = front_matter_fields
        self.tokens = tokens
        self.body_start_line = (
            (front_matter_end_line + 1) if front_matter_present else 0
        )

        self.title: str = ""
        self.h1_count: int = 0
        self.sections: list[Section] = []
        self.links: list[dict[str, Any]] = []
        self.link_occurrences: list[LinkOccurrence] = []
        self.math_code_spans: list[dict[str, Any]] = []
        self.sources: list[SourceDeclaration] = []
        self.collection_block: dict[str, Any] | None = None
        self.collection_well_formed: bool = True

        self._extract()

    def _extract(self) -> None:
        self._extract_headings_and_sections()
        self._extract_collection_and_links()
        self._extract_math_spans()
        self._extract_sources()

    def _extract_headings_and_sections(self) -> None:
        heading_tokens: list[tuple[int, str, int, int]] = []  # (level, title, start_line, end_line)
        for i, token in enumerate(self.tokens):
            if token.type == "heading_open":
                level = int(token.tag[1:])
                # Heading content is in inline token at i + 1
                heading_title = ""
                if i + 1 < len(self.tokens) and self.tokens[i + 1].type == "inline":
                    inline_token = self.tokens[i + 1]
                    heading_title = self._render_inline_text(inline_token).strip()

                start_line = token.map[0] + 1 if token.map else 1
                end_line = token.map[1] if token.map else start_line

                if level == 1:
                    self.h1_count += 1
                    if not self.title:
                        self.title = heading_title

                heading_tokens.append((level, heading_title, start_line, end_line))

        total_lines = len(self.lines)

        # Check preamble
        first_heading_line = heading_tokens[0][2] if heading_tokens else total_lines + 1
        preamble_start = self.body_start_line + 1
        # Find if there is any non-blank line in preamble
        has_preamble_content = False
        for lno in range(preamble_start, min(first_heading_line, total_lines + 1)):
            if self.lines[lno - 1].strip():
                has_preamble_content = True
                break

        if has_preamble_content:
            preamble_end = first_heading_line - 1
            # Trim trailing blank lines from preamble
            while preamble_end >= preamble_start and not self.lines[preamble_end - 1].strip():
                preamble_end -= 1
            if preamble_end >= preamble_start:
                self.sections.append(
                    Section(
                        key="preamble",
                        title="",
                        heading_path=[],
                        level=0,
                        span={
                            "start_line": preamble_start,
                            "end_line": preamble_end,
                            "precision": "line",
                        },
                    )
                )

        # Build hierarchical sections
        heading_path_stack: list[tuple[int, str]] = []
        for idx, (level, h_title, s_line, _) in enumerate(heading_tokens):
            # Pop stack for headings with >= current level
            while heading_path_stack and heading_path_stack[-1][0] >= level:
                heading_path_stack.pop()
            heading_path_stack.append((level, h_title))
            curr_heading_path = [item[1] for item in heading_path_stack]

            # Determine end line of section: extends until line before next heading with level <= current level
            end_line = total_lines
            for next_idx in range(idx + 1, len(heading_tokens)):
                next_level, _, next_sline, _ = heading_tokens[next_idx]
                if next_level <= level:
                    end_line = next_sline - 1
                    break

            # Trim trailing empty lines
            while end_line > s_line and not self.lines[end_line - 1].strip():
                end_line -= 1

            key = f"s{idx + 1}"
            self.sections.append(
                Section(
                    key=key,
                    title=h_title,
                    heading_path=curr_heading_path,
                    level=level,
                    span={
                        "start_line": s_line,
                        "end_line": end_line,
                        "precision": "line",
                    },
                )
            )

    def _render_inline_text(self, token: Token) -> str:
        if not token.children:
            return token.content or ""
        pieces: list[str] = []
        for child in token.children:
            if child.type in ("text", "code_inline", "math_inline"):
                pieces.append(child.content)
            elif child.type == "image":
                pieces.append(child.content or "")
            elif child.children:
                pieces.append(self._render_inline_text(child))
        return html.unescape("".join(pieces))

    def _extract_collection_and_links(self) -> None:
        # Check kb-nav collection comments
        # Collection block markers must be standalone exact lines outside fenced code
        fenced_lines: set[int] = set()
        for token in self.tokens:
            if token.type in ("fence", "code_block", "math_block", "math_block_label") and token.map:
                for l in range(token.map[0] + 1, token.map[1] + 1):
                    fenced_lines.add(l)

        in_collection = False
        collection_start_line = -1
        collection_end_line = -1
        collection_count = 0
        collection_well_formed = True

        for i in range(self.body_start_line, len(self.lines)):
            line_no = i + 1
            raw_line = self.lines[i].rstrip("\r\n")

            if line_no in fenced_lines:
                continue

            if raw_line == "<!-- kb-nav:children:start -->":
                collection_count += 1
                if in_collection or collection_count > 1:
                    collection_well_formed = False
                in_collection = True
                collection_start_line = line_no
                continue

            if raw_line == "<!-- kb-nav:children:end -->":
                if not in_collection:
                    collection_well_formed = False
                in_collection = False
                collection_end_line = line_no
                continue

            if "kb-nav:children:" in raw_line:
                collection_well_formed = False

        if in_collection:
            collection_well_formed = False

        self.collection_well_formed = collection_well_formed
        if collection_start_line != -1 and collection_end_line != -1 and collection_well_formed:
            self.collection_block = {
                "start_line": collection_start_line,
                "end_line": collection_end_line,
            }

        # Extract links from AST tokens
        # We traverse self.tokens to extract links purely from token syntax / AST.
        # Track list nesting inside collection block:
        # Only depth == 1 list items are direct collection items.
        link_count = 0
        collection_list_depth = 0
        curr_block_map: list[int] | None = None

        coll_s = collection_start_line
        coll_e = collection_end_line

        for token in self.tokens:
            if token.map:
                curr_block_map = token.map

            # Check if this token is within collection block
            is_in_coll_block = False
            if self.collection_block and token.map:
                t_s = token.map[0] + 1
                t_e = token.map[1]
                if coll_s <= t_s and t_e <= coll_e:
                    is_in_coll_block = True
            elif self.collection_block and curr_block_map:
                t_s = curr_block_map[0] + 1
                t_e = curr_block_map[1]
                if coll_s <= t_s and t_e <= coll_e:
                    is_in_coll_block = True

            if token.type in ("bullet_list_open", "ordered_list_open"):
                if is_in_coll_block:
                    collection_list_depth += 1
                continue
            if token.type in ("bullet_list_close", "ordered_list_close"):
                if collection_list_depth > 0:
                    collection_list_depth -= 1
                continue

            if token.type != "inline" or not token.children:
                continue

            inline_map = token.map or curr_block_map
            s_0 = inline_map[0] if inline_map else self.body_start_line
            e_0 = inline_map[1] if inline_map else len(self.lines)

            # Check if this inline is inside collection block
            is_in_coll = False
            if self.collection_block:
                if coll_s < e_0 and s_0 + 1 < coll_e:
                    is_in_coll = True

            is_direct_coll = is_in_coll and (collection_list_depth == 1)

            projected_lines = _inline_projected_lines(token)
            source = token.content or ""

            # Preserve the previous conservative behavior for an identical link
            # spelling repeated on different lines of one inline block.  The parser
            # identifies both links, but a line-level source association is still
            # intentionally withheld.
            syntax_lines: dict[tuple[bool, str], set[int]] = {}
            for candidate in token.children:
                if candidate.type not in ("link_open", "image"):
                    continue
                candidate_span = _token_source_document_span(token, candidate)
                start = candidate.meta.get(_SOURCE_START_META)
                end = candidate.meta.get(_SOURCE_END_META)
                if (
                    candidate_span is None
                    or candidate_span[0] != candidate_span[1]
                    or not isinstance(start, int)
                    or not isinstance(end, int)
                ):
                    continue
                key = (candidate.type == "image", source[start:end])
                syntax_lines.setdefault(key, set()).add(candidate_span[0])

            def locate_child(
                child_token: Token,
            ) -> tuple[int, str, bool, dict[str, Any]]:
                child_span = _token_source_document_span(token, child_token)
                start = child_token.meta.get(_SOURCE_START_META)
                end = child_token.meta.get(_SOURCE_END_META)
                is_repeated_across_lines = False
                if isinstance(start, int) and isinstance(end, int):
                    key = (child_token.type == "image", source[start:end])
                    is_repeated_across_lines = len(syntax_lines.get(key, set())) > 1

                if (
                    child_span is not None
                    and child_span[0] == child_span[1]
                    and not is_repeated_across_lines
                    and projected_lines is not None
                    and child_span[0] in projected_lines
                    and 1 <= child_span[0] <= len(self.lines)
                ):
                    line_no = child_span[0]
                    raw_line = self.lines[line_no - 1]
                    is_explicit = test_explicit_external_local_label(
                        projected_lines[line_no]
                    )
                    return (
                        line_no,
                        raw_line,
                        is_explicit,
                        {
                            "start_line": line_no,
                            "end_line": line_no,
                            "precision": "line",
                        },
                    )

                return (
                    s_0 + 1,
                    "",
                    False,
                    {
                        "start_line": s_0 + 1,
                        "end_line": e_0,
                        "precision": "block",
                    },
                )

            # Process inline children.  Locations come from the parser-recorded
            # rule spans above, never from normalized child token content.
            idx = 0
            while idx < len(token.children):
                child = token.children[idx]
                if child.type == "link_open":
                    destination = child.attrGet("href") or ""
                    # Find label and check for nested image
                    label_parts: list[str] = []
                    is_img = False
                    j = idx + 1
                    while j < len(token.children) and token.children[j].type != "link_close":
                        sub = token.children[j]
                        if sub.type == "image":
                            is_img = True
                            label_parts.append(sub.content or "")
                        elif sub.content:
                            label_parts.append(sub.content)
                        j += 1
                    label = "".join(label_parts)
                    idx = j + 1  # advance past link_close
                    line_no, line_text, is_explicit, span = locate_child(child)

                    link_count += 1
                    link_id = f"link-{link_count}"

                    lk_obj = LinkOccurrence(
                        id=link_id,
                        target=destination,
                        label=label,
                        line=line_text,
                        line_number=line_no,
                        is_explicit_external_local=is_explicit,
                        is_image=is_img,
                        is_in_collection=is_in_coll,
                        collection_well_formed=collection_well_formed,
                        is_direct_collection=is_direct_coll,
                        span=span,
                    )
                    self.link_occurrences.append(lk_obj)
                    self.links.append(lk_obj.to_dict())

                elif child.type == "image":
                    destination = child.attrGet("src") or ""
                    label = child.content or ""
                    idx += 1
                    line_no, line_text, is_explicit, span = locate_child(child)

                    link_count += 1
                    link_id = f"link-{link_count}"

                    lk_obj = LinkOccurrence(
                        id=link_id,
                        target=destination,
                        label=label,
                        line=line_text,
                        line_number=line_no,
                        is_explicit_external_local=is_explicit,
                        is_image=True,
                        is_in_collection=is_in_coll,
                        collection_well_formed=collection_well_formed,
                        is_direct_collection=is_direct_coll,
                        span=span,
                    )
                    self.link_occurrences.append(lk_obj)
                    self.links.append(lk_obj.to_dict())

                else:
                    idx += 1


    def _extract_math_spans(self) -> None:
        # Check math code spans from bodyStart
        in_fence = False
        for i in range(self.body_start_line, len(self.lines)):
            line_no = i + 1
            line = self.lines[i]
            if re.match(r"^\s*(```|~~~)", line):
                in_fence = not in_fence
                continue
            if in_fence or "<!-- kb-literal-code -->" in line or "kb-literal-code" in line:
                continue

            for m in re.finditer(r"(?<!`)`(?P<content>[^`\r\n]+)`(?!`)", line):
                content = m.group("content")
                if test_high_confidence_math(content):
                    self.math_code_spans.append(
                        {
                            "content": content,
                            "line_number": line_no,
                        }
                    )

    def _extract_sources(self) -> None:
        line_candidates: dict[int, list[tuple[str, str | None, str | None]]] = {}
        block_candidates: list[tuple[int, int, str]] = []
        for token in self.tokens:
            if token.type != "inline" or not token.children:
                continue
            projection = _inline_source_projection(token)
            projected_lines = _inline_projected_lines(token)
            support_source_lines = _inline_support_source_lines(token)
            if projected_lines is not None:
                for line_no, projected_line in projected_lines.items():
                    if _SOURCE_TOKEN_RE.search(projected_line):
                        support_line = (
                            support_source_lines.get(line_no)
                            if support_source_lines is not None
                            else None
                        )
                        line_candidates.setdefault(line_no, []).append(
                            (
                                projected_line,
                                support_line[0] if support_line is not None else None,
                                support_line[1] if support_line is not None else None,
                            )
                        )
                continue

            # An inline block without an exact source-line map may still contain a
            # candidate.  Preserve it as unclassified block evidence, but do not
            # extract fields or bind a same-line locator from an uncertain region.
            if _SOURCE_TOKEN_RE.search(projection) and token.map:
                start_line = token.map[0] + 1
                end_line = token.map[1]
                raw_block = "".join(self.lines[token.map[0] : token.map[1]]).strip()
                block_candidates.append((start_line, end_line, raw_block))

        src_count = 0
        for line_no in sorted(line_candidates):
            candidate_lines = line_candidates[line_no]
            projected_line = "; ".join(item[0] for item in candidate_lines)
            raw_line = self.lines[line_no - 1] if 1 <= line_no <= len(self.lines) else ""

            # Find metadata
            date_m = re.search(
                r"(?i)(?:verified|last\s+verified|验证日期|已验证)\s*[:：]\s*[`'\"]?(?P<date>\d{4}-\d{2}-\d{2})[`'\"]?",
                projected_line,
            )
            verified = date_m.group("date") if date_m else None

            ver_m = re.search(
                r"(?i)(?:revision|版本)\s*[:：]\s*[`'\"]?(?P<rev>[^;；,，`'\"]+)[`'\"]?",
                projected_line,
            )
            revision = (ver_m.group("rev").strip() or None) if ver_m else None

            vstate_m = re.search(
                r"(?i)(?:version[-_ ]?state|版本状态)\s*[:：]\s*[`'\"]?(?P<state>[^;；,，`'\"]+)[`'\"]?",
                projected_line,
            )
            version_state = (
                (vstate_m.group("state").strip() or None) if vstate_m else None
            )

            proj_m = re.search(
                r"(?i)(?:project[-_ ]?id|项目标识)\s*[:：]\s*[`'\"]?(?P<pid>[a-z0-9][a-z0-9._-]{0,63})[`'\"]?",
                projected_line,
            )
            project_id = proj_m.group("pid") if proj_m else None

            rel_m = re.search(
                r"(?i)(?:project[-_ ]?relative(?:\s+source)?|项目相对路径|相对路径)\s*[:：]\s*[`'\"]?(?P<rel>[^;；,，`'\"]+)[`'\"]?",
                projected_line,
            )
            project_rel_path = (
                (rel_m.group("rel").strip() or None) if rel_m else None
            )

            support_text = None
            for _, support_projection, support_source in candidate_lines:
                if support_projection is None or support_source is None:
                    continue
                support_text = _support_text_from_aligned_line(
                    support_projection, support_source
                )
                if support_text is not None:
                    break

            # Bind to genuine same-line LinkOccurrence on this exact line
            matching_links = [
                lk
                for lk in self.link_occurrences
                if not lk.is_image
                and lk.span
                and lk.span.get("precision") == "line"
                and lk.line_number == line_no
            ]
            locator = matching_links[0].target if len(matching_links) == 1 else None

            if not (locator or project_id or verified or revision or version_state):
                continue

            recognition = "unclassified"
            if project_id and verified and (revision or version_state):
                recognition = "structured"
            elif verified or revision or version_state or project_id:
                recognition = "partial"

            src_count += 1
            src_id = f"src-{src_count}"
            self.sources.append(
                SourceDeclaration(
                    id=src_id,
                    span={"start_line": line_no, "end_line": line_no, "precision": "line"},
                    raw_text=raw_line.strip(),
                    locator=locator,
                    project_id=project_id,
                    project_relative_path=project_rel_path,
                    verified=verified,
                    revision=revision,
                    version_state=version_state,
                    support_text=support_text,
                    recognition=recognition,
                )
            )

        for start_line, end_line, raw_block in sorted(block_candidates):
            src_count += 1
            self.sources.append(
                SourceDeclaration(
                    id=f"src-{src_count}",
                    span={
                        "start_line": start_line,
                        "end_line": end_line,
                        "precision": "block",
                    },
                    raw_text=raw_block,
                    locator=None,
                    project_id=None,
                    project_relative_path=None,
                    verified=None,
                    revision=None,
                    version_state=None,
                    support_text=None,
                    recognition="unclassified",
                )
            )


def parse_markdown_page(
    content: str,
    filename: str | None = None,
    md_parser: MarkdownIt | None = None,
) -> tuple[ParsedMarkdownPage, list[Diagnostic]]:
    """Parse a markdown file, returning a ParsedMarkdownPage and any parsing diagnostics."""
    if md_parser is None:
        md_parser = create_markdown_parser()

    from .yaml_reader import extract_front_matter

    fm_present, fm_end_line, fm_fields, diagnostics = extract_front_matter(
        content, filename=filename
    )
    lines = content.splitlines(keepends=True)

    # To maintain 0-based token.map line numbers matching original file lines,
    # blank out the front matter lines.
    if fm_present and fm_end_line >= 0:
        blanked_text = ("\n" * (fm_end_line + 1)) + "".join(lines[fm_end_line + 1 :])
    else:
        blanked_text = content

    tokens = md_parser.parse(blanked_text)
    parsed = ParsedMarkdownPage(
        raw_text=content,
        lines=lines,
        front_matter_present=fm_present,
        front_matter_end_line=fm_end_line,
        front_matter_fields=fm_fields,
        tokens=tokens,
    )
    return parsed, diagnostics
