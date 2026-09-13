"""Unit tests for Python parser and path safety (Gate G1)."""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

# Add scripts directory to sys.path
TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "knowledge-base-manager" / "scripts"))

from kb_core.markdown_reader import parse_markdown_page, test_high_confidence_math
from kb_core.paths import (
    assert_no_redirecting_reparse_point,
    get_canonical_path,
    is_redirecting_reparse_point,
    test_path_inside_root,
)
from kb_core.yaml_reader import extract_front_matter, parse_yaml_text
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


class TestYamlReader(unittest.TestCase):
    def test_valid_yaml(self):
        doc = """
id: kb-20260830-a1b2
type: concept
status: draft
created: 2026-08-30
updated: 2026-08-30
tags:
  - math
  - test
unknown_field: custom_value
"""
        data, diags = parse_yaml_text(doc)
        self.assertEqual(len(diags), 0)
        self.assertEqual(data["id"], "kb-20260830-a1b2")
        self.assertEqual(data["created"], "2026-08-30")
        self.assertIsInstance(data["created"], str)
        self.assertEqual(data["tags"], ["math", "test"])
        self.assertEqual(data["unknown_field"], "custom_value")

    def test_duplicate_key_rejected(self):
        doc = "id: 1\nid: 2\n"
        data, diags = parse_yaml_text(doc)
        self.assertTrue(any(d.code == "PARSE_FAILED" and "duplicate key" in d.message for d in diags))

    def test_alias_anchor_rejected(self):
        doc = "base: &base\n  val: 1\nref: *base\n"
        data, diags = parse_yaml_text(doc)
        self.assertTrue(any(d.code == "PARSE_FAILED" and "alias" in d.message for d in diags))

    def test_merge_key_rejected(self):
        doc = "base: { a: 1 }\nchild:\n  <<: *base\n  b: 2\n"
        data, diags = parse_yaml_text(doc)
        self.assertTrue(any(d.code == "PARSE_FAILED" for d in diags))

    def test_front_matter_extraction(self):
        content = """---
id: kb-20260901-test
type: method
status: stable
created: 2026-09-01
updated: 2026-09-01
---
# Actual Document Title

Body text here.
---
This horizontal rule in body must not be mistaken for front matter.
"""
        present, end_line, fields, diags = extract_front_matter(content)
        self.assertTrue(present)
        self.assertEqual(end_line, 6)
        self.assertEqual(fields.get("id"), "kb-20260901-test")
        self.assertEqual(len(diags), 0)

    def test_front_matter_missing(self):
        content = "# No front matter\nJust text\n"
        present, end_line, fields, diags = extract_front_matter(content)
        self.assertFalse(present)
        self.assertEqual(end_line, -1)
        self.assertEqual(fields, {})


class TestPathSafety(unittest.TestCase):
    def setUp(self):
        self.temp_dir = create_temp_dir("kb-test-paths-")

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_canonical_and_inside_root(self):
        root = os.path.join(self.temp_dir, "kb_root")
        os.makedirs(root, exist_ok=True)
        inside = os.path.join(root, "content", "index.md")
        outside = os.path.join(self.temp_dir, "other.md")

        self.assertTrue(test_path_inside_root(inside, root))
        self.assertTrue(test_path_inside_root(root, root))
        self.assertFalse(test_path_inside_root(outside, root))

    def test_normal_directory_not_reparse(self):
        d = os.path.join(self.temp_dir, "normal_dir")
        os.makedirs(d, exist_ok=True)
        self.assertFalse(is_redirecting_reparse_point(d))
        # assert_no_redirecting_reparse_point should pass without error
        assert_no_redirecting_reparse_point(d)


class TestMarkdownParser(unittest.TestCase):
    def test_cjk_bom_and_crlf(self):
        # Japanese and Chinese text with BOM and CRLF
        content = (
            "---\r\n"
            "id: kb-20260913-cjk1\r\n"
            "type: concept\r\n"
            "status: draft\r\n"
            "created: 2026-09-13\r\n"
            "updated: 2026-09-13\r\n"
            "---\r\n"
            "# 日本語と中文のノート\r\n\r\n"
            "これはテストです。[リンク](knowledge/子ノート.md)。\r\n\r\n"
            "## セクション1\r\n\r\n"
            "内容です。\r\n"
        )
        parsed, diags = parse_markdown_page(content, filename="test.md")
        self.assertEqual(len(diags), 0)
        self.assertEqual(parsed.title, "日本語と中文のノート")
        self.assertEqual(parsed.h1_count, 1)
        self.assertEqual(len(parsed.sections), 2)
        self.assertEqual(parsed.sections[0].key, "s1")
        self.assertEqual(parsed.sections[0].title, "日本語と中文のノート")
        self.assertEqual(parsed.sections[1].key, "s2")
        self.assertEqual(parsed.sections[1].title, "セクション1")
        self.assertEqual(parsed.sections[1].heading_path, ["日本語と中文のノート", "セクション1"])

        # Check link
        self.assertEqual(len(parsed.links), 1)
        self.assertEqual(
            parsed.links[0]["target"], "knowledge/%E5%AD%90%E3%83%8E%E3%83%BC%E3%83%88.md"
        )
        self.assertEqual(parsed.links[0]["line_number"], 10)

    def test_code_blocks_exclusion(self):
        content = """---
id: kb-20260913-code
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Code Test Page

Here is genuine text with [real link](real.md).

```markdown
# Fake Heading in Code
[Fake Link in Code](fake.md)
<!-- kb-nav:children:start -->
- [Fake Collection](fake_coll.md)
<!-- kb-nav:children:end -->
project-id: fake-proj; verified: 2026-09-13; revision: 123
```

    # Indented code fake heading
    [Indented fake link](fake_indent.md)

And `[inline fake link](fake_inline.md)` in backticks.
"""
        parsed, diags = parse_markdown_page(content, filename="code.md")
        self.assertEqual(len(diags), 0)
        self.assertEqual(parsed.h1_count, 1)
        self.assertEqual(parsed.title, "Code Test Page")
        # Only one genuine section
        self.assertEqual(len(parsed.sections), 1)
        self.assertEqual(parsed.sections[0].title, "Code Test Page")

        # Links: only the genuine link "real.md" should be extracted
        targets = [lk["target"] for lk in parsed.links]
        self.assertIn("real.md", targets)
        self.assertNotIn("fake.md", targets)
        self.assertNotIn("fake_coll.md", targets)
        self.assertNotIn("fake_indent.md", targets)
        self.assertNotIn("fake_inline.md", targets)

        # No fake collection block
        self.assertIsNone(parsed.collection_block)
        # No fake sources
        self.assertEqual(len(parsed.sources), 0)

    def test_preamble_and_duplicate_headings(self):
        content = """---
id: kb-20260913-pre
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
This is introductory preamble before any heading.

# Main Title

Introduction under main title.

## Duplicate

First duplicate.

## Duplicate

Second duplicate with same title.
"""
        parsed, diags = parse_markdown_page(content, filename="pre.md")
        self.assertEqual(len(diags), 0)
        keys = [s.key for s in parsed.sections]
        self.assertEqual(keys, ["preamble", "s1", "s2", "s3"])
        self.assertEqual(parsed.sections[0].key, "preamble")
        self.assertEqual(parsed.sections[0].span["start_line"], 8)

        # Duplicate headings retain unique keys
        self.assertEqual(parsed.sections[2].title, "Duplicate")
        self.assertEqual(parsed.sections[3].title, "Duplicate")
        self.assertNotEqual(parsed.sections[2].key, parsed.sections[3].key)

    def test_math_detection(self):
        content = """# Math Page

Valid dollar math: $\\mathrm{GF}(2^8)$ and $\\tau_x = \\alpha x$.

Display math:
$$
\\int_0^1 f(x) dx
$$

Inline code with math: `GF(2^8)` on line 10.
Literal code with exception: `P(A|B)` <!-- kb-literal-code --> on line 11.
Normal code: `my_func()` and `path/to/file.py`.
"""
        parsed, diags = parse_markdown_page(content, filename="math.md")
        self.assertEqual(len(parsed.math_code_spans), 1)
        self.assertEqual(parsed.math_code_spans[0]["content"], "GF(2^8)")
        self.assertEqual(parsed.math_code_spans[0]["line_number"], 10)

    def test_collection_block_parsing(self):
        content = """---
id: kb-20260913-map1
type: map
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Map Page

<!-- kb-nav:children:start -->
- [Child 1](child1.md)
  - [Nested Child 2](nested2.md)
- [Child 3](child3.md)
<!-- kb-nav:children:end -->
"""
        parsed, diags = parse_markdown_page(content, filename="map.md")
        self.assertTrue(parsed.collection_well_formed)
        self.assertIsNotNone(parsed.collection_block)
        coll_links = [lk for lk in parsed.links if lk["is_in_collection"]]
        # Both links in collection region are marked is_in_collection
        self.assertEqual(len(coll_links), 3)

    def test_source_declarations_extraction(self):
        content = """---
id: kb-20260913-src
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Source Page

- Project: `Example`; project-id: `example`; project-relative source: `docs/test.md`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [test.md](D:/Projects/example/docs/test.md); `verified: 2026-08-30`; `revision: abc1234`; supports: sample claim.
"""
        parsed, diags = parse_markdown_page(content, filename="source.md")
        self.assertEqual(len(parsed.sources), 1)
        src = parsed.sources[0]
        self.assertEqual(src.project_id, "example")
        self.assertEqual(src.project_relative_path, "docs/test.md")
        self.assertEqual(src.verified, "2026-08-30")
        self.assertEqual(src.revision, "abc1234")
        self.assertEqual(src.recognition, "structured")
        self.assertEqual(src.span["start_line"], 10)
        self.assertEqual(src.span["end_line"], 10)


    def test_math_span_not_fake_link(self):
        content = "# Title\n\n$[ghost](ghost.md)$\n"
        parsed, diags = parse_markdown_page(content, filename="math.md")
        self.assertEqual([x["target"] for x in parsed.links], [])
        self.assertEqual(diags, [])

    def test_balanced_parentheses_link(self):
        content = "# Title\n\n[real](a(b).md)\n"
        parsed, diags = parse_markdown_page(content, filename="paren.md")
        self.assertEqual([x["target"] for x in parsed.links], ["a(b).md"])
        self.assertEqual(diags, [])

    def test_autolink(self):
        content = "# Title\n\n<https://example.com/evidence>\n"
        parsed, diags = parse_markdown_page(content, filename="auto.md")
        self.assertEqual([x["target"] for x in parsed.links], ["https://example.com/evidence"])
        self.assertEqual(diags, [])

    def test_nested_collection_direct_vs_indirect(self):
        content = """# Map

<!-- kb-nav:children:start -->
- [A](a.md)
  - [B](b.md)
<!-- kb-nav:children:end -->
"""
        parsed, diags = parse_markdown_page(content, filename="map.md")
        self.assertEqual(len(parsed.links), 2)
        link_a = next(l for l in parsed.link_occurrences if l.target == "a.md")
        link_b = next(l for l in parsed.link_occurrences if l.target == "b.md")
        self.assertTrue(link_a.is_in_collection)
        self.assertTrue(link_a.is_direct_collection)
        self.assertTrue(link_b.is_in_collection)
        self.assertFalse(link_b.is_direct_collection)

    def test_math_and_inline_code_source_not_extracted(self):
        declaration = "[fake](ghost.md); project-id: demo; project-relative source: ghost.md; verified: 2026-09-13; revision: abc;"
        # Inside inline math
        parsed_math, _ = parse_markdown_page("# Sample\n\n$" + declaration + "$\n")
        self.assertEqual(len(parsed_math.sources), 0)
        self.assertEqual(len(parsed_math.links), 0)

        # Inside inline code
        parsed_code, _ = parse_markdown_page("# Sample\n\n`" + declaration + "`\n")
        self.assertEqual(len(parsed_code.sources), 0)
        self.assertEqual(len(parsed_code.links), 0)

    def test_valid_project_source_without_link_preserved_with_null_locator(self):
        content = (
            "# Page\n\n"
            "- Project: demo; project-id: demo; project-relative source: file.md; verified: 2026-09-13; revision: abc;\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.sources), 1)
        src = parsed.sources[0]
        self.assertIsNone(src.locator)
        self.assertEqual(src.project_id, "demo")
        self.assertEqual(src.project_relative_path, "file.md")
        self.assertEqual(src.verified, "2026-09-13")
        self.assertEqual(src.revision, "abc")
        self.assertEqual(src.recognition, "structured")

    def test_source_with_backtick_wrapped_fields_recognized(self):
        content = (
            "# Page\n\n"
            "- [Actual](source.md); project-id: `demo`; verified: `2026-09-13`; revision: `v1.0`\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.sources), 1)
        src = parsed.sources[0]
        self.assertEqual(src.locator, "source.md")
        self.assertEqual(src.project_id, "demo")
        self.assertEqual(src.verified, "2026-09-13")
        self.assertEqual(src.revision, "v1.0")
        self.assertEqual(src.recognition, "structured")

    def test_link_positioning_matches_full_link_syntax_not_substring(self):
        content = (
            "# Sample\n\n"
            "The text mentions source.md.\n"
            "[Actual](source.md) <!-- kb-external-local -->\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 1)
        lk = parsed.link_occurrences[0]
        self.assertEqual(lk.line_number, 4)
        self.assertTrue(lk.is_explicit_external_local)
        self.assertEqual(lk.span["precision"], "line")

    def test_link_positioning_fallback_to_block_when_ambiguous(self):
        content = (
            "# Sample\n\n"
            "[A](target.md)\n"
            "[A](target.md)\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 2)
        for lk in parsed.link_occurrences:
            self.assertEqual(lk.span["precision"], "block")
            self.assertFalse(lk.is_explicit_external_local)

    def test_multiline_link_block_precision_does_not_bind_to_source_on_another_line(self):
        content = (
            "# Page\n\n"
            "[Actual\n"
            "label](source.md)\n"
            "project-id: demo; project-relative source: source.md; verified: 2026-09-13; revision: abc;\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 1)
        lk = parsed.link_occurrences[0]
        self.assertEqual(lk.span["precision"], "block")
        self.assertEqual(lk.span["start_line"], 3)
        self.assertEqual(lk.span["end_line"], 5)
        self.assertEqual(lk.line, "")
        self.assertFalse(lk.is_explicit_external_local)

        self.assertEqual(len(parsed.sources), 1)
        src = parsed.sources[0]
        self.assertIsNone(src.locator)
        self.assertEqual(src.project_id, "demo")
        self.assertEqual(src.project_relative_path, "source.md")
        self.assertEqual(src.verified, "2026-09-13")
        self.assertEqual(src.revision, "abc")
        self.assertEqual(src.recognition, "structured")
        self.assertEqual(src.span["start_line"], 5)
        self.assertEqual(src.span["precision"], "line")

    def test_double_backtick_code_example_not_extracted_as_source(self):
        content = (
            "# Page\n\n"
            "示例：``project-id: demo; project-relative source: source.md; verified: 2026-09-13; revision: abc;``。\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.sources), 0)

    def test_code_example_does_not_steal_link_position_or_marker(self):
        content = (
            "# Page\n\n"
            "[Actual\n"
            "label](source.md)\n"
            "`[Fake](source.md)` <!-- kb-external-local -->\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 1)
        lk = parsed.link_occurrences[0]
        self.assertEqual(lk.span["precision"], "block")
        self.assertEqual(lk.line, "")
        self.assertFalse(lk.is_explicit_external_local)
        self.assertEqual(len(parsed.sources), 0)

    def test_multiple_links_on_same_line_do_not_bind_locator_ambiguously(self):
        content = (
            "# Page\n\n"
            "[Link 1](s1.md) and [Link 2](s2.md); project-id: demo; project-relative source: s1.md; verified: 2026-09-13; revision: abc;\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 2)
        for lk in parsed.link_occurrences:
            self.assertEqual(lk.span["precision"], "line")
            self.assertEqual(lk.line_number, 3)

        self.assertEqual(len(parsed.sources), 1)
        src = parsed.sources[0]
        # Ambiguous candidate links on same line must not be arbitrarily bound
        self.assertIsNone(src.locator)
        self.assertEqual(src.project_id, "demo")
        self.assertEqual(src.recognition, "structured")

    def test_link_retains_raw_percent_encoding(self):
        content = "# Sample\n\n- [Hash](knowledge/a%23b.md)\n"
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.links), 1)
        self.assertEqual(parsed.links[0]["target"], "knowledge/a%23b.md")

    def test_multiline_inline_code_source_fields_are_excluded_in_block_contexts(self):
        metadata = (
            "project-id: demo; project-relative source: source.md; "
            "verified: 2026-09-13; revision: abc;"
        )
        bodies = (
            f"`sample\n{metadata}\nend`\n",
            f"- `sample\n  {metadata}\n  end`\n",
            f"> `sample\n> {metadata}\n> end`\n",
        )
        for body in bodies:
            with self.subTest(body=body):
                parsed, _ = parse_markdown_page("# Page\n\n" + body)
                self.assertEqual(parsed.sources, [])

    def test_source_after_multiline_code_uses_parser_source_line(self):
        content = (
            "# Page\n\n"
            "`one\n"
            "two`\n"
            "[Doc](source.md); project-id: demo; project-relative source: source.md; "
            "verified: 2026-09-13; revision: abc;\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(parsed.link_occurrences[0].span["precision"], "line")
        self.assertEqual(parsed.link_occurrences[0].line_number, 5)
        self.assertEqual(parsed.sources[0].locator, "source.md")
        self.assertEqual(parsed.sources[0].span["start_line"], 5)

    def test_code_examples_cannot_supply_or_override_source_fields(self):
        for prefix in ("示例：", "Example:", "e.g. ", "说明："):
            with self.subTest(prefix=prefix):
                content = (
                    "# Page\n\n"
                    "[Doc](source.md); project-id: demo; project-relative source: source.md; "
                    f"{prefix}`verified: 1999-01-01; revision: fake;`; "
                    "verified: 2026-09-13; revision: abc;\n"
                )
                parsed, _ = parse_markdown_page(content)
                self.assertEqual(len(parsed.sources), 1)
                self.assertEqual(parsed.sources[0].verified, "2026-09-13")
                self.assertEqual(parsed.sources[0].revision, "abc")
                self.assertEqual(parsed.sources[0].recognition, "structured")

        uncertain = (
            "# Page\n\n"
            "[Doc](source.md); project-id: demo; project-relative source: source.md; "
            "说明：`verified: 1999-01-01; revision: fake;`\n"
        )
        parsed, _ = parse_markdown_page(uncertain)
        self.assertEqual(len(parsed.sources), 1)
        self.assertIsNone(parsed.sources[0].verified)
        self.assertIsNone(parsed.sources[0].revision)
        self.assertEqual(parsed.sources[0].recognition, "partial")

    def test_code_example_marker_does_not_mark_real_link_external_local(self):
        content = (
            "# Page\n\n"
            "[Doc](source.md) `<!-- kb-external-local -->`\n"
        )
        parsed, _ = parse_markdown_page(content)
        self.assertEqual(len(parsed.link_occurrences), 1)
        self.assertEqual(parsed.link_occurrences[0].span["precision"], "line")
        self.assertFalse(parsed.link_occurrences[0].is_explicit_external_local)


if __name__ == "__main__":
    unittest.main()
