"""Comprehensive Python unit and integration tests for Static Site Generation,
Navigation Models, and Graph Models (Phase C).

Ports all assertions from:
- tests/test-kb-static-navigation.ps1
- tests/test-kb-static-graph.ps1
- tests/test-kb-build-static.ps1
"""

from __future__ import annotations

import glob
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "knowledge-base-manager" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
if str(TEST_DIR) not in sys.path:
    sys.path.insert(0, str(TEST_DIR))

from kb_core.cli import main
from kb_core.static_build import execute_static_build
from kb_core.static_graph import (
    convert_to_graph_javascript,
    convert_to_graph_previews_javascript,
    get_graph_model,
    get_page_frontmatter,
    get_text_excerpt,
    update_heading_anchors,
)
from kb_core.static_nav import get_static_navigation_href, get_static_navigation_model
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


def nav_block(links: str) -> str:
    return f"<!-- kb-nav:children:start -->\n{links}\n<!-- kb-nav:children:end -->"


def make_fake_katex_assets(root: str) -> None:
    write_file(os.path.join(root, "katex.min.js"), "fake katex javascript")
    write_file(os.path.join(root, "katex.min.css"), "fake katex stylesheet")
    write_file(os.path.join(root, "contrib", "auto-render.min.js"), "fake auto render javascript")
    write_file(os.path.join(root, "fonts", "KaTeX_Main-Regular.woff2"), "fake font")


def setup_test_kb(root: str, home_text: str, content_dir: str = "content", entrypoint: str = "content/首页.md") -> None:
    os.makedirs(root, exist_ok=True)
    kb_yaml = f"schema_version: 1\ncontent_dir: {content_dir}\nentrypoint: {entrypoint}\n"
    write_file(os.path.join(root, "kb.yaml"), kb_yaml)
    write_file(os.path.join(root, entrypoint.replace("/", os.sep)), home_text)


class TestStaticNavigation(unittest.TestCase):
    """Port of tests/test-kb-static-navigation.ps1."""

    def setUp(self) -> None:
        self.test_root = create_temp_dir("kb-py-nav-")
        self.assets_dir = os.path.join(self.test_root, "assets")
        make_fake_katex_assets(self.assets_dir)
        self.kb_dir = os.path.join(self.test_root, "kb")
        self.dest_dir = os.path.join(self.test_root, "output")

    def tearDown(self) -> None:
        cleanup_dir(self.test_root)

    def test_navigation_hierarchy_ancestry_and_digests(self) -> None:
        home_text = "# 我的首页\n\n" + nav_block("- [主题](集合/主题.md)")
        setup_test_kb(self.kb_dir, home_text)

        map_text = "---\ntype: map\n---\n# 主题 H1\n\n" + nav_block("- [工程](../项目/工程.md)")
        write_file(os.path.join(self.kb_dir, "content", "集合", "主题.md"), map_text)

        project_text = (
            "---\ntype: project\n---\n# 工程 H1\n\n"
            + nav_block(
                "- [条目](<../笔记/条目 中文.md>)\n"
                "- [重复条目](<../笔记/条目 中文.md>)\n\n"
                "```markdown\n"
                "- [不存在](missing.md)\n"
                "<!-- kb-nav:children:start -->\n"
                "<!-- kb-nav:children:end -->\n"
                "```\n"
            )
        )
        write_file(os.path.join(self.kb_dir, "content", "项目", "工程.md"), project_text)

        leaf_path = os.path.join(self.kb_dir, "content", "笔记", "条目 中文.md")
        write_file(leaf_path, "---\ntype: concept\n---\n# 条目 H1\n\n正文 A。\n")
        write_file(os.path.join(self.kb_dir, "content", "笔记", "孤立.md"), "# 未声明归属的笔记\n")
        write_file(os.path.join(self.kb_dir, "content", "projects", "展示 空格.md"), "---\ntype: project\n---\n# 展示项目标题\n")
        write_file(os.path.join(self.kb_dir, "content", "knowledge", "子目录", "知识 空格.md"), "---\ntype: concept\n---\n# 知识标题 & 内容\n")

        # 1. First build
        code, env = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "success")

        manifest_file = os.path.join(self.dest_dir, ".kb-static-manifest.json")
        self.assertTrue(os.path.isfile(manifest_file))
        with open(manifest_file, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)
        digest = manifest["navigation_digest"]
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", digest))

        # Check leaf HTML breadcrumbs
        leaf_html_path = os.path.join(self.dest_dir, "笔记", "条目 中文.html")
        self.assertTrue(os.path.isfile(leaf_html_path))
        with open(leaf_html_path, "r", encoding="utf-8") as lf:
            leaf_html = lf.read()

        bc_match = re.search(r"(?s)<nav class=\"kb-breadcrumb\".*?</nav>", leaf_html)
        self.assertIsNotNone(bc_match)
        bc_text = bc_match.group(0)
        self.assertTrue(re.search(r"我的首页.*主题 H1.*工程 H1.*条目 H1", bc_text, re.DOTALL))
        self.assertTrue(re.search(r'href="\.\./(?:%E9%A6%96%E9%A1%B5|首页)\.html"', bc_text))
        self.assertIsNone(re.search(r"目录|kb-directory", bc_text))

        # Check auxiliary indexes
        proj_idx_file = os.path.join(self.dest_dir, "projects", "index.html")
        self.assertTrue(os.path.isfile(proj_idx_file))
        with open(proj_idx_file, "r", encoding="utf-8") as pf:
            proj_idx = pf.read()
        self.assertIn("全部项目", proj_idx)
        self.assertIn("展示项目标题", proj_idx)

        know_idx_file = os.path.join(self.dest_dir, "knowledge", "index.html")
        self.assertTrue(os.path.isfile(know_idx_file))
        with open(know_idx_file, "r", encoding="utf-8") as kf:
            know_idx = kf.read()
        self.assertIn("全部知识条目", know_idx)
        self.assertIn("知识标题 &amp; 内容", know_idx)
        self.assertTrue(re.search(r'href="[^"]*%20[^"]*\.html"', know_idx))

        indexed_leaf_file = os.path.join(self.dest_dir, "knowledge", "子目录", "知识 空格.html")
        self.assertTrue(os.path.isfile(indexed_leaf_file))
        with open(indexed_leaf_file, "r", encoding="utf-8") as ilf:
            indexed_leaf = ilf.read()
        self.assertIn("kb-uncollected", indexed_leaf)
        indexed_crumb = re.search(r"(?s)<nav class=\"kb-breadcrumb\".*?</nav>", indexed_leaf).group(0)
        self.assertIsNone(re.search(r"全部知识条目|子目录", indexed_crumb))

        # 2. Unchanged rebuild
        code2, env2 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code2, 0)
        self.assertEqual(env2.data["generated"], 0)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            self.assertEqual(json.load(mf)["navigation_digest"], digest)

        # 3. Body-only change
        write_file(leaf_path, "---\ntype: concept\n---\n# 条目 H1\n\n正文 B，只有正文变化。\n")
        code3, env3 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code3, 0)
        self.assertEqual(env3.data["generated"], 1)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            self.assertEqual(json.load(mf)["navigation_digest"], digest)

        # 4. Nested list in collection region
        nested_home_text = "# 我的首页\n\n" + nav_block("- [主题](集合/主题.md)\n  - [工程](../项目/工程.md)")
        write_file(os.path.join(self.kb_dir, "content", "首页.md"), nested_home_text)
        code4, env4 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code4, 0)

        with open(leaf_html_path, "r", encoding="utf-8") as lf:
            leaf4_html = lf.read()
        bc4 = re.search(r"(?s)<nav class=\"kb-breadcrumb\".*?</nav>", leaf4_html).group(0)
        self.assertTrue(re.search(r"我的首页.*主题 H1.*工程 H1.*条目 H1", bc4, re.DOTALL))
        self.assertNotIn('<nav class="kb-collections"', leaf4_html)

        # Direct model inspection
        all_mds = sorted(glob.glob(os.path.join(self.kb_dir, "content", "**", "*.md"), recursive=True))
        nav_curr = get_static_navigation_model(
            markdown_files=all_mds,
            content_root=os.path.join(self.kb_dir, "content"),
            entry_source_path=os.path.join(self.kb_dir, "content", "首页.md"),
        )
        self.assertEqual(nav_curr.pages["首页.md"].children, ["集合/主题.md"])
        self.assertEqual(nav_curr.pages["项目/工程.md"].parents, ["集合/主题.md"])

        # Restore home text
        write_file(os.path.join(self.kb_dir, "content", "首页.md"), home_text)

        # 5. Renamed title invalidates digest
        renamed_map = map_text.replace("# 主题 H1", "# 新主题标题")
        write_file(os.path.join(self.kb_dir, "content", "集合", "主题.md"), renamed_map)
        code5, env5 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code5, 0)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            new_digest = json.load(mf)["navigation_digest"]
        self.assertNotEqual(new_digest, digest)
        self.assertGreater(env5.data["generated"], 1)
        with open(leaf_html_path, "r", encoding="utf-8") as lf:
            self.assertIn("新主题标题", lf.read())

        # 6. Multiple parents
        write_file(
            os.path.join(self.kb_dir, "content", "项目", "第二工程.md"),
            "---\ntype: project\n---\n# 第二工程 H1\n" + nav_block("- [条目](<../笔记/条目 中文.md>)"),
        )
        write_file(
            os.path.join(self.kb_dir, "content", "首页.md"),
            "# 我的首页\n" + nav_block("- [主题](集合/主题.md)\n- [第二工程](项目/第二工程.md)"),
        )
        code6, env6 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code6, 0)

        with open(leaf_html_path, "r", encoding="utf-8") as lf:
            multi_html = lf.read()
        colls_match = re.search(r"(?s)<nav class=\"kb-collections\".*?</nav>", multi_html)
        self.assertIsNotNone(colls_match)
        colls = colls_match.group(0)
        self.assertIn("工程 H1", colls)
        self.assertIn("第二工程 H1", colls)
        self.assertEqual(len(re.findall(r"<a\s", colls)), 2)

        multi_crumb = re.search(r"(?s)<nav class=\"kb-breadcrumb\".*?</nav>", multi_html).group(0)
        self.assertIsNone(re.search(r"新主题标题|工程 H1", multi_crumb))

        with open(os.path.join(self.dest_dir, "笔记", "孤立.html"), "r", encoding="utf-8") as of:
            orph_html = of.read()
        self.assertIn("kb-uncollected", orph_html)
        self.assertTrue("尚未被项目或主题收录" in orph_html or "Not yet collected" in orph_html)

        # 7. Edge-only change
        with open(manifest_file, "r", encoding="utf-8") as mf:
            before_edge = json.load(mf)["navigation_digest"]
        write_file(os.path.join(self.kb_dir, "content", "项目", "工程.md"), "---\ntype: project\n---\n# 工程 H1\n")
        code7, env7 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code7, 0)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            after_edge = json.load(mf)["navigation_digest"]
        self.assertNotEqual(after_edge, before_edge)
        self.assertGreater(env7.data["generated"], 1)

        with open(leaf_html_path, "r", encoding="utf-8") as lf:
            single_crumb = re.search(r"(?s)<nav class=\"kb-breadcrumb\".*?</nav>", lf.read()).group(0)
        self.assertTrue(re.search(r"我的首页.*第二工程 H1.*条目 H1", single_crumb, re.DOTALL))

        # 8. Renamed child with updated edges
        with open(manifest_file, "r", encoding="utf-8") as mf:
            before_rename = json.load(mf)["navigation_digest"]
        renamed_leaf_path = os.path.join(self.kb_dir, "content", "笔记", "重命名 中文.md")
        os.rename(leaf_path, renamed_leaf_path)
        write_file(
            os.path.join(self.kb_dir, "content", "项目", "第二工程.md"),
            "---\ntype: project\n---\n# 第二工程 H1\n" + nav_block("- [条目](<../笔记/重命名 中文.md>)"),
        )
        code8, env8 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code8, 0)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            after_rename = json.load(mf)["navigation_digest"]
        self.assertNotEqual(after_rename, before_rename)
        self.assertFalse(os.path.exists(leaf_html_path))
        self.assertTrue(os.path.exists(os.path.join(self.dest_dir, "笔记", "重命名 中文.html")))

        # 9. Deleted child with removed edges
        with open(manifest_file, "r", encoding="utf-8") as mf:
            before_del = json.load(mf)["navigation_digest"]
        os.remove(renamed_leaf_path)
        write_file(
            os.path.join(self.kb_dir, "content", "项目", "第二工程.md"),
            "---\ntype: project\n---\n# 第二工程 H1\n",
        )
        code9, env9 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code9, 0)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            after_del = json.load(mf)["navigation_digest"]
        self.assertNotEqual(after_del, before_del)
        self.assertFalse(os.path.exists(os.path.join(self.dest_dir, "笔记", "重命名 中文.html")))

        # 10. Pre-navigation manifest upgrade
        with open(manifest_file, "r", encoding="utf-8") as mf:
            old_mf_data = json.load(mf)
        old_mf_data.pop("navigation_digest", None)
        with open(manifest_file, "w", encoding="utf-8") as mf:
            json.dump(old_mf_data, mf)
        code10, env10 = execute_static_build(self.kb_dir, self.dest_dir, katex_assets_root=self.assets_dir)
        self.assertEqual(code10, 0)
        self.assertGreater(env10.data["generated"], 1)
        with open(manifest_file, "r", encoding="utf-8") as mf:
            self.assertTrue(re.match(r"^[0-9a-f]{64}$", json.load(mf)["navigation_digest"]))

    def test_legacy_knowledge_base_without_declarations(self) -> None:
        legacy_kb = os.path.join(self.test_root, "legacy")
        legacy_dest = os.path.join(self.test_root, "legacy-output")
        setup_test_kb(legacy_kb, "# 旧首页\n- [普通链接](leaf.md)\n")
        write_file(os.path.join(legacy_kb, "content", "leaf.md"), "# 旧条目\n")

        code, env = execute_static_build(legacy_kb, legacy_dest, katex_assets_root=self.assets_dir)
        self.assertEqual(code, 0)
        leaf_html_file = os.path.join(legacy_dest, "leaf.html")
        with open(leaf_html_file, "r", encoding="utf-8") as f:
            self.assertIn("kb-uncollected", f.read())

    def test_invalid_navigation_cases_block_before_write(self) -> None:
        cases = [
            ("self", "# 首页\n" + nav_block("- [自己](首页.md)"), None),
            ("missing", "# 首页\n" + nav_block("- [缺失](missing.md)"), None),
            ("external", "# 首页\n" + nav_block("- [外部](https://example.com/x.md)"), None),
            ("outside", "# 首页\n" + nav_block("- [越界](../outside.md)"), None),
            ("unclosed", "# 首页\n<!-- kb-nav:children:start -->\n- [页](leaf.md)", None),
            ("cycle", "# 首页\n" + nav_block("- [映射](leaf.md)"), "---\ntype: map\n---\n# 映射\n" + nav_block("- [首页](首页.md)")),
            ("leaf-declaration", "# 首页\n", "---\ntype: concept\n---\n# 普通条目\n" + nav_block("- [首页](首页.md)")),
        ]
        for name, home, leaf in cases:
            bad_kb = os.path.join(self.test_root, f"bad-{name}")
            bad_dest = os.path.join(self.test_root, f"bad-output-{name}")
            setup_test_kb(bad_kb, home)
            write_file(os.path.join(bad_kb, "content", "leaf.md"), leaf if leaf else "# Leaf")
            write_file(os.path.join(bad_kb, "outside.md"), "# Outside content")

            code, env = execute_static_build(bad_kb, bad_dest, katex_assets_root=self.assets_dir)
            self.assertNotEqual(code, 0, f"{name} must block with non-zero exit code")
            self.assertFalse(os.path.exists(bad_dest), f"{name} must fail before creating destination")


class TestStaticGraph(unittest.TestCase):
    """Port of tests/test-kb-static-graph.ps1."""

    def setUp(self) -> None:
        self.test_root = create_temp_dir("kb-py-graph-")

    def tearDown(self) -> None:
        cleanup_dir(self.test_root)

    def test_heading_anchor_unification(self) -> None:
        html_sample = (
            '<div id="kb-heading-1">Existing collision div</div>\n'
            '<h1>Page H1</h1>\n'
            '<p>Intro paragraph.</p>\n'
            '<h2>Section Alpha</h2>\n'
            '<p>Alpha content.</p>\n'
            '<pre><code><h2>Code heading ignored</h2></code></pre>\n'
            '<h5>Deep Level 5</h5>\n'
            '<p>Deep content.</p>\n'
            '<h3>Sub Alpha 1</h3>\n'
            '<p>Sub content.</p>\n'
            '<h2 id="explicit-id">Explicit Section</h2>\n'
            '<p>Explicit content.</p>\n'
            '<h2 id="dup-id">Duplicate Heading 1</h2>\n'
            '<h3 id="dup-id">Duplicate Heading 2</h3>\n'
        )
        res = update_heading_anchors(html_sample, owner_page_id="page:id:p1", source_path="test.md")
        self.assertIsNotNone(res.html)
        self.assertEqual(len(res.sections), 6)

        sec_alpha = next(s for s in res.sections if s.title == "Section Alpha")
        sub_alpha = next(s for s in res.sections if s.title == "Sub Alpha 1")
        deep_lvl5 = next(s for s in res.sections if s.title == "Deep Level 5")
        explicit_sec = next(s for s in res.sections if s.title == "Explicit Section")

        self.assertEqual(sec_alpha.fragment, "kb-heading-2")
        self.assertEqual(sub_alpha.fragment, "kb-heading-3")
        self.assertEqual(deep_lvl5.fragment, "kb-heading-4")
        self.assertEqual(explicit_sec.fragment, "explicit-id")

        self.assertEqual(sec_alpha.parent_node_id, "page:id:p1")
        self.assertEqual(deep_lvl5.parent_node_id, sec_alpha.node_id)
        self.assertEqual(sub_alpha.parent_node_id, sec_alpha.node_id)
        self.assertEqual(explicit_sec.parent_node_id, "page:id:p1")

        dup_diags = [d for d in res.diagnostics if d["code"] == "duplicate_heading_id"]
        self.assertEqual(len(dup_diags), 1)

        self.assertIn("<code><h2>Code heading ignored</h2></code>", res.html)

    def test_frontmatter_parsing(self) -> None:
        fm_sample = (
            "---\n"
            "id: kb-20260910-abcd\n"
            "type: concept\n"
            "status: draft\n"
            "tags:\n"
            "  - math\n"
            "  - logic\n"
            "---\n"
            "# Title\n"
        )
        fm = get_page_frontmatter(fm_sample)
        self.assertEqual(fm["id"], "kb-20260910-abcd")
        self.assertEqual(fm["type"], "concept")
        self.assertEqual(fm["status"], "draft")
        self.assertEqual(fm["tags"], ["math", "logic"])

        fm_inline = (
            "---\n"
            'id: "kb-inline"\n'
            "type: 'map'\n"
            "status: STABLE\n"
            'tags: [tagA, "tagB"]\n'
            "---\n"
        )
        fm2 = get_page_frontmatter(fm_inline)
        self.assertEqual(fm2["id"], "kb-inline")
        self.assertEqual(fm2["type"], "map")
        self.assertEqual(fm2["status"], "stable")
        self.assertEqual(fm2["tags"], ["tagA", "tagB"])

    def test_excerpt_extraction(self) -> None:
        excerpt_html = (
            "<script>var x = 1;</script>\n"
            "<style>.body { color: red; }</style>\n"
            "<!-- kb-nav:children:start -->\n"
            "<p>Nav child paragraph ignored</p>\n"
            "<!-- kb-nav:children:end -->\n"
            "<pre><code><p>Code paragraph ignored</p></code></pre>\n"
            "<p>Hello <b>World</b> &amp; Antigravity assistant! This is a <i>clean</i> paragraph.</p>\n"
            "<p>Second paragraph ignored.</p>\n"
        )
        exc = get_text_excerpt(excerpt_html, max_length=600)
        self.assertEqual(exc["mode"], "excerpt")
        self.assertEqual(exc["text"], "Hello World & Antigravity assistant! This is a clean paragraph.")
        self.assertFalse(exc["truncated"])

        # Long text truncation
        long_p = "<p>" + ("A" * 700) + "</p>"
        exc_long = get_text_excerpt(long_p, max_length=600)
        self.assertEqual(exc_long["mode"], "excerpt")
        self.assertEqual(len(exc_long["text"]), 600)
        self.assertTrue(exc_long["truncated"])

        # Unavailable fallback
        empty_html = "<h1>Only Title</h1><pre><code>Code only</code></pre>"
        exc_empty = get_text_excerpt(empty_html)
        self.assertEqual(exc_empty["mode"], "unavailable")
        self.assertEqual(exc_empty["text"], "")

    def test_full_graph_model_extraction_and_digests(self) -> None:
        kb = os.path.join(self.test_root, "kb")
        content = os.path.join(kb, "content")
        write_file(os.path.join(kb, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")

        write_file(
            os.path.join(content, "index.md"),
            "# 知识库主页\n\n欢迎来到知识库。\n\n"
            + nav_block("- [项目 Alpha](projects/alpha.md)\n- [概览地图](maps/overview.md)\n"),
        )
        write_file(
            os.path.join(content, "projects", "alpha.md"),
            "---\n"
            "id: kb-20260910-0001\n"
            "type: project\n"
            "status: stable\n"
            "tags:\n"
            "  - core\n"
            "---\n"
            "# 项目 Alpha\n\n"
            "这是项目 Alpha 的主说明。\n\n"
            "## 架构规划\n\n"
            "在架构方面，请参考 [概览地图](<../maps/overview.md#sec-deep>) 的深度分析。\n\n"
            "### 详细实现\n\n"
            "此处引用了核心概念：[核心概念](../knowledge/concept.md)。\n"
            "另可参考规范：[在线标准](https://example.com/spec?v=1#intro)。\n\n"
            "## 资源清单\n\n"
            "- 本地源码：[Local Project](file:///C:/projects/myrepo) <!-- kb-external-local -->\n"
            "- 规格说明书：[Attachment Spec](../assets/spec.pdf)\n"
            "- 概念再读：[再读核心概念](../knowledge/concept.md#sub-concept)\n"
            "- 自引用章节：[查看架构规划](#kb-heading-1)\n",
        )
        write_file(
            os.path.join(content, "maps", "overview.md"),
            "---\n"
            "id: kb-20260910-0002\n"
            "type: map\n"
            "status: draft\n"
            "---\n"
            "# 概览地图\n\n"
            "知识库全景地图。\n\n"
            "## 模块总览\n\n"
            "此模块与 [项目 Alpha](../projects/alpha.md) 紧密相连。\n\n"
            '<h4 id="sec-deep">深度切面</h4>\n\n'
            "这是深度切面正文。\n",
        )
        write_file(
            os.path.join(content, "knowledge", "concept.md"),
            "---\n"
            "id: kb-20260910-0003\n"
            "type: concept\n"
            "status: stable\n"
            "---\n"
            "# 核心概念\n\n"
            "核心概念定义。\n\n"
            "## 概念详解\n\n"
            "这是概念正文。\n\n"
            "### 子概念说明\n\n"
            "这是子概念详情。\n",
        )
        write_file(os.path.join(content, "assets", "spec.pdf"), "disposable pdf binary content")
        write_file(
            os.path.join(content, "broken.md"),
            "# 诊断测试页\n\n"
            '<h2 id="dup-heading">标题一</h2>\n'
            '<h3 id="dup-heading">标题二</h3>\n\n'
            "- [不存在的文件](missing-file.md)\n"
            "- [不存在的锚点](maps/overview.md#non-existent-frag)\n",
        )

        md_files = sorted(glob.glob(os.path.join(content, "**", "*.md"), recursive=True))
        nav_model = get_static_navigation_model(
            markdown_files=md_files,
            content_root=content,
            entry_source_path=os.path.join(content, "index.md"),
        )
        graph_res = get_graph_model(content_root=content, navigation=nav_model, markdown_files=md_files)

        gd = graph_res.graph_data
        pd = graph_res.preview_data

        self.assertEqual(gd["schema"], "kb-graph")
        self.assertEqual(gd["schema_version"], 1)
        self.assertEqual(pd["schema"], "kb-graph-previews")
        self.assertEqual(pd["schema_version"], 1)

        self.assertEqual(gd["entry_id"], "page:path:index.md")

        node_map = {n["id"]: n for n in gd["nodes"]}
        self.assertIn("page:path:index.md", node_map)
        self.assertIn("page:id:kb-20260910-0001", node_map)
        self.assertIn("page:id:kb-20260910-0002", node_map)
        self.assertIn("page:id:kb-20260910-0003", node_map)
        self.assertIn("page:path:broken.md", node_map)

        alpha_node = node_map["page:id:kb-20260910-0001"]
        self.assertEqual(alpha_node["kind"], "page")
        self.assertEqual(alpha_node["title"], "项目 Alpha")
        self.assertEqual(alpha_node["target"]["kind"], "internal")
        self.assertEqual(alpha_node["target"]["path"], "projects/alpha.html")
        self.assertEqual(alpha_node["page"]["kb_id"], "kb-20260910-0001")
        self.assertEqual(alpha_node["page"]["type"], "project")
        self.assertEqual(alpha_node["page"]["status"], "stable")
        self.assertIn("core", alpha_node["page"]["tags"])

        deep_sec = node_map.get("section:page:id:kb-20260910-0002#sec-deep")
        self.assertIsNotNone(deep_sec)
        self.assertEqual(deep_sec["kind"], "section")
        self.assertEqual(deep_sec["title"], "深度切面")
        self.assertEqual(deep_sec["section"]["owner_page"], "page:id:kb-20260910-0002")
        self.assertEqual(deep_sec["section"]["heading_level"], 4)

        # Collects edges
        edge_map = {e["id"]: e for e in gd["edges"]}
        c1 = edge_map.get("edge:collects:page:path:index.md->page:id:kb-20260910-0001")
        c2 = edge_map.get("edge:collects:page:path:index.md->page:id:kb-20260910-0002")
        self.assertIsNotNone(c1)
        self.assertIsNotNone(c2)
        self.assertEqual(c1["order"], 0)
        self.assertEqual(c2["order"], 1)

        # Contains edges
        contains_alpha = [e for e in gd["edges"] if e["kind"] == "contains" and e["source"] == "page:id:kb-20260910-0001"]
        self.assertGreaterEqual(len(contains_alpha), 2)

        # References edges
        ref_concept = edge_map.get("edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0003")
        self.assertIsNotNone(ref_concept)
        self.assertEqual(ref_concept["kind"], "references")
        self.assertEqual(len(ref_concept["occurrences"]), 2)
        self.assertEqual(ref_concept["occurrences"][0]["label"], "核心概念")
        self.assertEqual(ref_concept["occurrences"][1]["label"], "再读核心概念")
        self.assertEqual(ref_concept["occurrences"][1]["target_fragment"], "sub-concept")
        self.assertTrue(ref_concept["occurrences"][0]["source_section"].startswith("section:page:id:kb-20260910-0001#"))

        # Cyclic reference
        ref_a_to_o = edge_map.get("edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0002")
        ref_o_to_a = edge_map.get("edge:references:page:id:kb-20260910-0002->page:id:kb-20260910-0001")
        self.assertIsNotNone(ref_a_to_o)
        self.assertIsNotNone(ref_o_to_a)

        # Self-reference
        ref_self = edge_map.get("edge:references:page:id:kb-20260910-0001->page:id:kb-20260910-0001")
        self.assertIsNotNone(ref_self)
        self.assertEqual(ref_self["occurrences"][0]["target_fragment"], "kb-heading-1")

        # External local reference: display-only, no machine path
        ext_local = next(n for n in gd["nodes"] if (n.get("reference") or {}).get("medium") == "external-local")
        self.assertEqual(ext_local["target"]["kind"], "display-only")
        self.assertEqual(ext_local["target"]["reason"], "external-local")
        self.assertNotIn("url", ext_local["target"])

        # Attachment reference
        att_node = next(n for n in gd["nodes"] if (n.get("reference") or {}).get("medium") == "attachment")
        self.assertEqual(att_node["target"]["kind"], "internal")
        self.assertEqual(att_node["target"]["path"], "assets/spec.pdf")

        # Diagnostics
        diag_codes = [d["code"] for d in gd["diagnostics"]]
        self.assertIn("missing_target", diag_codes)
        self.assertIn("missing_fragment", diag_codes)
        self.assertIn("duplicate_heading_id", diag_codes)

        self.assertTrue(re.match(r"^[0-9a-f]{64}$", gd["graph_digest"]))
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", pd["preview_digest"]))
        self.assertEqual(pd["graph_digest"], gd["graph_digest"])

        # Determinism & body-only independent digest test
        graph_res2 = get_graph_model(content_root=content, navigation=nav_model, markdown_files=md_files)
        self.assertEqual(graph_res2.graph_data["graph_digest"], gd["graph_digest"])
        self.assertEqual(graph_res2.preview_data["preview_digest"], pd["preview_digest"])

        # Modify only body paragraph in concept.md
        mod_concept = (
            "---\n"
            "id: kb-20260910-0003\n"
            "type: concept\n"
            "status: stable\n"
            "---\n"
            "# 核心概念\n\n"
            "核心概念定义已经被更新了，这里有全新的一段正文内容！\n\n"
            "## 概念详解\n\n"
            "这是概念正文修改版。\n\n"
            "### 子概念说明\n\n"
            "这是子概念详情。\n"
        )
        write_file(os.path.join(content, "knowledge", "concept.md"), mod_concept)
        md_updated = sorted(glob.glob(os.path.join(content, "**", "*.md"), recursive=True))
        graph_res3 = get_graph_model(content_root=content, navigation=nav_model, markdown_files=md_updated)
        self.assertEqual(graph_res3.graph_data["graph_digest"], gd["graph_digest"])
        self.assertNotEqual(graph_res3.preview_data["preview_digest"], pd["preview_digest"])

    def test_duplicate_formal_id_throws_blocker(self) -> None:
        kb = os.path.join(self.test_root, "dup-kb")
        content = os.path.join(kb, "content")
        write_file(os.path.join(kb, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")
        write_file(os.path.join(content, "index.md"), "# Index\n")
        write_file(os.path.join(content, "p1.md"), "---\nid: kb-dup-id\n---\n# Page 1\n")
        write_file(os.path.join(content, "p2.md"), "---\nid: kb-dup-id\n---\n# Page 2\n")

        md_files = sorted(glob.glob(os.path.join(content, "**", "*.md"), recursive=True))
        nav_model = get_static_navigation_model(
            markdown_files=md_files,
            content_root=content,
            entry_source_path=os.path.join(content, "index.md"),
        )
        with self.assertRaises((RuntimeError, ValueError)) as ctx:
            get_graph_model(content_root=content, navigation=nav_model, markdown_files=md_files)
        self.assertIn("BLOCKER: duplicate formal id", str(ctx.exception))

    def test_javascript_serialization_and_xss_safety(self) -> None:
        xss_graph = {
            "schema": "kb-graph",
            "title": '<script>alert("xss")</script>',
            "content": '<img src=x onerror=alert(1)> & "quotes"',
            "tags": ["<b>bold</b>"],
        }
        js_data = convert_to_graph_javascript(xss_graph)
        self.assertTrue(js_data.startswith("window.__KB_GRAPH_DATA__ = "))
        self.assertTrue(js_data.rstrip().endswith(";"))
        self.assertNotIn("<script", js_data)
        self.assertNotIn("<img", js_data)
        self.assertIn("\\u003cscript\\u003e", js_data)
        self.assertIn("\\u0026", js_data)

        xss_prev = {
            "schema": "kb-graph-previews",
            "records": [{"text": "</script><script>eval()</script>"}],
        }
        js_prev = convert_to_graph_previews_javascript(xss_prev)
        self.assertTrue(js_prev.startswith("window.__KB_GRAPH_PREVIEWS__ = "))
        self.assertNotIn("</script>", js_prev)

    def test_inbox_and_archive_exclusion(self) -> None:
        kb = os.path.join(self.test_root, "inbox-kb")
        content = os.path.join(kb, "content")
        write_file(os.path.join(kb, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")
        write_file(
            os.path.join(content, "index.md"),
            "# 主页\n\n## 待整理\n- [草稿](inbox/draft-note.md)\n- [归档](archive/historical.md)\n",
        )
        write_file(os.path.join(content, "inbox", "draft-note.md"), "# 暂存草稿笔记\n\n这是收件箱中的草稿笔记。\n")
        write_file(os.path.join(content, "archive", "historical.md"), "---\nid: kb-9999\nstatus: deprecated\n---\n# 归档条目\n")

        md_files = sorted(glob.glob(os.path.join(content, "**", "*.md"), recursive=True))
        nav_model = get_static_navigation_model(
            markdown_files=md_files,
            content_root=content,
            entry_source_path=os.path.join(content, "index.md"),
        )
        graph_res = get_graph_model(content_root=content, navigation=nav_model, markdown_files=md_files)
        gd = graph_res.graph_data

        inbox_nodes = [
            n for n in gd["nodes"]
            if "inbox" in n["id"].lower()
            or "archive" in n["id"].lower()
            or (n.get("page", {}).get("source_path", "").lower().startswith(("inbox/", "archive/")))
        ]
        self.assertEqual(len(inbox_nodes), 0)

        inbox_edges = [
            e for e in gd["edges"]
            if "inbox" in e["source"].lower()
            or "inbox" in e["target"].lower()
            or "archive" in e["source"].lower()
            or "archive" in e["target"].lower()
        ]
        self.assertEqual(len(inbox_edges), 0)

        index_secs = [n for n in gd["nodes"] if n.get("kind") == "section" and n.get("section", {}).get("owner_page") == "page:path:index.md"]
        self.assertEqual(len(index_secs), 0)


class TestStaticBuild(unittest.TestCase):
    """Port of tests/test-kb-build-static.ps1."""

    def setUp(self) -> None:
        self.test_root = create_temp_dir("kb-py-build-")
        self.kb = os.path.join(self.test_root, "知识库 空格")
        self.destination = os.path.join(self.test_root, "静态 页面 空格")
        self.katex_assets = os.path.join(self.test_root, "fake katex assets")
        make_fake_katex_assets(self.katex_assets)

        write_file(os.path.join(self.kb, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")
        write_file(
            os.path.join(self.kb, "content", "index.md"),
            "---\n"
            "id: kb-20260831-index\n"
            "type: map\n"
            "---\n"
            "# 首页\n\n"
            "- [中文条目](<资料 空格/条目 中文.md#小节>)\n"
            "- [资料目录](<资料 空格/>)\n",
        )
        self.entry_path = os.path.join(self.kb, "content", "资料 空格", "条目 中文.md")
        entry_md = (
            "---\n"
            "id: kb-20260831-entry\n"
            "type: concept\n"
            "---\n"
            "# 中文条目\n\n"
            "Alpha.\n\n"
            "行内公式：$P(X=x \\mid accepted)$。\n\n"
            "$$\n"
            "R_K = ARK_{K_1} \\circ SR\n"
            "$$\n\n"
            "| 项目 | 状态 |\n"
            "| :--- | ---: |\n"
            "| [返回首页](../index.md) | ~~旧状态~~ |\n\n"
            "- [x] 已检查的 gate\n"
            "- [ ] 待检查的 gate\n\n"
            "1. 外层步骤\n"
            "   - 内层条件\n\n"
            "> 边界：这是一项静态阅读器可见的警告。\n\n"
            "> [!NOTE]\n"
            "> 这是一项 renderer profile 已验证的提示。\n\n"
            "保留可追溯说明[^render-profile]。\n\n"
            "[^render-profile]: 脚注保留在静态页面中。\n\n"
            "```powershell\n"
            "Get-Item\n"
            "```\n\n"
            "<details>\n"
            "<summary>展开补充说明</summary>\n\n"
            "折叠中的 **重点** 与 [返回首页](../index.md)。\n\n"
            "```text\n"
            "折叠中的代码 <>& \n"
            "```\n\n"
            "</details>\n\n"
            "## 小节\n\n"
            "[返回](../index.md)\n\n"
            "<h2>无ID小节</h2>\n"
        )
        write_file(self.entry_path, entry_md)
        with open(self.entry_path, "rb") as f:
            self.source_before = f.read()

    def tearDown(self) -> None:
        cleanup_dir(self.test_root)

    def test_full_static_build_and_markup_generation(self) -> None:
        code, env = execute_static_build(
            root=self.kb,
            destination=self.destination,
            katex_assets_root=self.katex_assets,
        )
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "success")
        self.assertFalse(env.data["force_rebuild"])
        self.assertGreaterEqual(env.data["generated"], 3)

        manifest_path = os.path.join(self.destination, ".kb-static-manifest.json")
        self.assertTrue(os.path.isfile(manifest_path))
        with open(manifest_path, "r", encoding="utf-8") as mf:
            manifest = json.load(mf)

        self.assertEqual(manifest["schema"], "knowledge-base-static-site")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(manifest["template_version"], "9")
        self.assertEqual(manifest["entry_output_path"], "index.html")
        self.assertEqual(len(manifest["pages"]), 2)
        self.assertEqual(manifest["katex"]["asset_version"], "0.18.1")
        self.assertEqual(len(manifest["katex"]["assets"]), 4)
        self.assertEqual(manifest["graph"]["asset_version"], "1.0.0")
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", manifest["graph"]["graph_digest"]))
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", manifest["graph"]["preview_digest"]))
        self.assertEqual(manifest["graph"]["navigation_page"]["output_path"], "kb-navigation.html")
        self.assertTrue(re.match(r"^[0-9a-f]{64}$", manifest["graph"]["navigation_page"]["output_sha256"]))
        self.assertGreaterEqual(len(manifest["graph"]["assets"]), 2)
        self.assertEqual(len(manifest["graph"]["data_assets"]), 2)

        # Source Markdown remains byte identical
        with open(self.entry_path, "rb") as f:
            self.assertEqual(self.source_before, f.read())

        # Inspect generated HTML
        with open(os.path.join(self.destination, "index.html"), "r", encoding="utf-8") as f:
            index_html = f.read()
        entry_html_path = os.path.join(self.destination, "资料 空格", "条目 中文.html")
        with open(entry_html_path, "r", encoding="utf-8") as f:
            entry_html = f.read()

        for page in (index_html, entry_html):
            self.assertEqual(len(re.findall(r'<style id="kb-theme">', page)), 1)
            self.assertIn('<script id="kb-toc-script">', page)
            self.assertIn('<aside id="kb-toc"', page)
            self.assertTrue(re.search(r'(?s)<main class="kb-paper">.*?<nav class="kb-breadcrumb".*?<div class="kb-content">.*?</div>.*?</main>', page))

        self.assertTrue(index_html.strip().lower().startswith("<!doctype html>"))
        self.assertTrue(re.search(r'href="[^"]+\.html#', index_html))
        self.assertIsNone(re.search(r'\.md(?:[?#\"])', index_html))
        self.assertTrue(re.search(r'href="[^"]+index\.html"', index_html))

        # Semantic markup in entry_html
        self.assertTrue(re.search(r"<h1[^>]*>中文条目</h1>", entry_html))
        content_block = re.search(r"(?s)<div class=\"kb-content\">.*?</div>", entry_html).group(0)
        self.assertNotIn("kb-20260831-entry", content_block)
        self.assertIn('href="../index.html"', entry_html)
        self.assertTrue(re.search(r'(?is)<table.*?<thead>.*?<th[^>]*style="text-align: left;"[^>]*>项目</th>.*?<th[^>]*style="text-align: right;"[^>]*>状态</th>.*?<tbody>.*?</table>', entry_html))
        self.assertTrue(re.search(r'(?is)<table.*?href="\.\./index\.html".*?</table>', entry_html))
        self.assertIsNone(re.search(r'(?is)<table.*?\.md.*?</table>', entry_html))
        self.assertTrue(re.search(r'(?is)<ul class="contains-task-list">.*?<input[^>]*disabled="disabled"[^>]*type="checkbox".*?</ul>', entry_html))
        self.assertTrue(re.search(r'(?is)<ol>.*?<ul>.*?</ul>.*?</ol>', entry_html))
        self.assertTrue(re.search(r'(?is)<blockquote>.*?静态阅读器可见的警告.*?</blockquote>', entry_html))
        self.assertTrue(re.search(r'(?is)<div class="markdown-alert markdown-alert-note">.*?<p class="markdown-alert-title"[^>]*>.*?Note</p>.*?renderer profile 已验证的提示.*?</div>', entry_html))
        self.assertIn("<del>旧状态</del>", entry_html)
        self.assertTrue(re.search(r'(?is)<a[^>]*class="footnote-ref"[^>]*><sup>1</sup></a>.*?<div class="footnotes">', entry_html))
        self.assertTrue(re.search(r'(?is)<pre><code class="language-powershell">Get-Item.*?</code></pre>', entry_html))
        self.assertTrue(re.search(r'(?s)<details>\s*<summary>展开补充说明</summary>.*?<strong>重点</strong>.*?href="../index.html".*?<pre><code class="language-text">折叠中的代码 &lt;&gt;&amp;.*?</details>', entry_html))

        # CSS tokens in static template
        for css_token in (
            "table{display:block", "th,td{border:", "ul.contains-task-list",
            ".task-list-item", "blockquote{", ".markdown-alert{",
            ".markdown-alert-title{", ".footnotes{", "hr{", "del{", "pre{", "img{max-width:100%"
        ):
            self.assertIn(css_token, entry_html)

        # KaTeX relative path depth
        self.assertTrue(re.search(r'href="\./_assets/katex/katex\.min\.css"', index_html))
        self.assertTrue(re.search(r'href="\.\./_assets/katex/katex\.min\.css"', entry_html))
        self.assertTrue(re.search(r'class="math"', entry_html))
        self.assertIn(r"\(", entry_html)
        self.assertIn(r"\[", entry_html)

        # Graph components
        self.assertIn('id="kb-graph-inline"', index_html)
        self.assertIn('id="kb-graph-app"', index_html)
        self.assertIn("mode: 'inline'", index_html)
        self.assertIn('id="kb-graph-trigger"', entry_html)
        self.assertIn("mode: 'overlay'", entry_html)
        self.assertIn('class="kb-inbox-trigger-btn"', index_html)
        self.assertIn('class="kb-inbox-badge kb-inbox-badge-empty"', index_html)
        self.assertIn(">0</span>", index_html)
        self.assertIn('href="inbox/index.html"', index_html)

        # Standalone nav page
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "kb-navigation.html")))
        with open(os.path.join(self.destination, "kb-navigation.html"), "r", encoding="utf-8") as f:
            nav_page = f.read()
        self.assertIn('id="kb-nav-app"', nav_page)
        self.assertIn("mode: 'standalone'", nav_page)

        # Assets copied
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "_assets", "graph", "graph.css")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "_assets", "graph", "graph.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "_assets", "graph", "graph-data.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "_assets", "graph", "graph-previews.js")))
        self.assertTrue(os.path.isfile(os.path.join(self.destination, "_assets", "katex", "katex.min.js")))

        # 2. Incremental second build skips all
        code2, env2 = execute_static_build(
            root=self.kb,
            destination=self.destination,
            katex_assets_root=self.katex_assets,
        )
        self.assertEqual(code2, 0)
        self.assertEqual(env2.data["generated"], 0)
        self.assertGreaterEqual(env2.data["skipped"], 3)
        self.assertEqual(env2.data["assets_generated"], 0)
        self.assertEqual(env2.data["assets_skipped"], 4)
        self.assertEqual(env2.data["graph_assets_generated"], 0)
        self.assertGreaterEqual(env2.data["graph_assets_skipped"], 4)

        # 3. Force rebuild
        force_extra = os.path.join(self.destination, "force-preserve.txt")
        write_file(force_extra, "unrelated destination file")
        code_f, env_f = execute_static_build(
            root=self.kb,
            destination=self.destination,
            katex_assets_root=self.katex_assets,
            force=True,
        )
        self.assertEqual(code_f, 0)
        self.assertTrue(env_f.data["force_rebuild"])
        self.assertGreaterEqual(env_f.data["generated"], 3)
        self.assertEqual(env_f.data["assets_generated"], 4)
        self.assertGreaterEqual(env_f.data["graph_assets_generated"], 4)
        self.assertTrue(os.path.isfile(force_extra))
        with open(force_extra, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "unrelated destination file")

        # 4. Asset repair
        os.remove(os.path.join(self.destination, "_assets", "katex", "fonts", "KaTeX_Main-Regular.woff2"))
        with open(os.path.join(self.destination, "_assets", "katex", "katex.min.js"), "w", encoding="utf-8") as f:
            f.write("tampered KaTeX asset")
        code_rep, env_rep = execute_static_build(
            root=self.kb,
            destination=self.destination,
            katex_assets_root=self.katex_assets,
        )
        self.assertEqual(code_rep, 0)
        self.assertEqual(env_rep.data["assets_generated"], 2)
        self.assertEqual(env_rep.data["generated"], 0)

        # 5. Stale asset with changed hash not cleaned up
        obs_source = os.path.join(self.katex_assets, "contrib", "obsolete.txt")
        obs_output = os.path.join(self.destination, "_assets", "katex", "contrib", "obsolete.txt")
        write_file(obs_source, "obsolete bundled asset")
        execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        os.remove(obs_source)
        write_file(obs_output, "user replacement must survive")
        execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertTrue(os.path.isfile(obs_output))
        with open(obs_output, "r", encoding="utf-8") as f:
            self.assertEqual(f.read(), "user replacement must survive")

        # 6. Template version change
        with open(manifest_path, "r", encoding="utf-8") as mf:
            old_tmpl_mf = json.load(mf)
        old_tmpl_mf["template_version"] = "obsolete-template"
        with open(manifest_path, "w", encoding="utf-8") as mf:
            json.dump(old_tmpl_mf, mf)
        code_tc, env_tc = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_tc, 0)
        self.assertGreaterEqual(env_tc.data["generated"], 3)

        # 7. Tampered HTML regenerated
        write_file(entry_html_path, "tampered")
        code_t, env_t = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_t, 0)
        self.assertEqual(env_t.data["generated"], 1)
        self.assertIn("资料 空格/条目 中文.html", env_t.data["generated_paths"])

        # 8. Same size, same mtime content modification
        mtime = os.path.getmtime(self.entry_path)
        with open(self.entry_path, "r", encoding="utf-8") as f:
            cur_content = f.read()
        write_file(self.entry_path, cur_content.replace("Alpha", "Bravo"))
        os.utime(self.entry_path, (mtime, mtime))
        code_sc, env_sc = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_sc, 0)
        self.assertEqual(env_sc.data["generated"], 1)

        # 9. Added and removed Markdown
        new_md = os.path.join(self.kb, "content", "资料 空格", "新建.md")
        write_file(new_md, "# 新建\n")
        code_new, env_new = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_new, 0)
        self.assertIn("资料 空格/新建.html", env_new.data["generated_paths"])

        user_extra = os.path.join(self.destination, "user-extra.txt")
        write_file(user_extra, "must survive")
        os.remove(self.entry_path)
        code_rem, env_rem = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_rem, 0)
        self.assertIn("资料 空格/条目 中文.html", env_rem.data["removed_paths"])
        self.assertFalse(os.path.exists(entry_html_path))
        self.assertTrue(os.path.isfile(user_extra))

        os.remove(new_md)
        shutil.rmtree(os.path.dirname(new_md))
        code_remdir, env_remdir = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_remdir, 0)
        self.assertIn("资料 空格/index.html", env_remdir.data["removed_paths"])

    def test_inbox_dynamic_button_and_badge(self) -> None:
        execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        inbox_draft = os.path.join(self.kb, "content", "inbox", "draft.md")
        write_file(
            inbox_draft,
            "---\nid: kb-draft\ntitle: 待整理草稿\n---\n# 待整理草稿\n\n草稿正文。\n",
        )
        code_in, env_in = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_in, 0)

        with open(os.path.join(self.destination, "index.html"), "r", encoding="utf-8") as f:
            idx_inbox = f.read()
        self.assertIn('class="kb-inbox-badge kb-inbox-badge-active"', idx_inbox)
        self.assertIn(">1</span>", idx_inbox)

        inbox_idx_file = os.path.join(self.destination, "inbox", "index.html")
        self.assertTrue(os.path.isfile(inbox_idx_file))
        with open(inbox_idx_file, "r", encoding="utf-8") as f:
            inbox_idx = f.read()
        self.assertIn('href="draft.html"', inbox_idx)
        self.assertIn("待整理草稿", inbox_idx)

        # Remove draft and verify return to empty
        os.remove(inbox_draft)
        code_empty, env_empty = execute_static_build(self.kb, self.destination, katex_assets_root=self.katex_assets)
        self.assertEqual(code_empty, 0)

        with open(os.path.join(self.destination, "index.html"), "r", encoding="utf-8") as f:
            idx_empty = f.read()
        self.assertIn('class="kb-inbox-badge kb-inbox-badge-empty"', idx_empty)
        self.assertIn(">0</span>", idx_empty)

        with open(inbox_idx_file, "r", encoding="utf-8") as f:
            inbox_empty_html = f.read()
        self.assertIn("收件箱为空，暂无待整理笔记。", inbox_empty_html)

    def test_blockers_and_conflict_safety(self) -> None:
        conflict_kb = os.path.join(self.test_root, "conflict kb")
        conflict_dest = os.path.join(self.test_root, "conflict dest")
        setup_test_kb(conflict_kb, "# Conflict\n", entrypoint="content/index.md")

        # Conflict 1: unowned index.html in destination
        write_file(os.path.join(conflict_dest, "index.html"), "user-owned output")
        code, env = execute_static_build(conflict_kb, conflict_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")

        # Force must also respect unowned output
        code_f, env_f = execute_static_build(conflict_kb, conflict_dest, katex_assets_root=self.katex_assets, force=True)
        self.assertEqual(code_f, 2)
        self.assertEqual(env_f.status, "blocked")

        # Conflict 2: unowned asset
        asset_conflict_dest = os.path.join(self.test_root, "asset conflict dest")
        write_file(os.path.join(asset_conflict_dest, "_assets", "katex", "katex.min.js"), "user katex")
        code_a, env_a = execute_static_build(conflict_kb, asset_conflict_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code_a, 2)
        self.assertEqual(env_a.status, "blocked")

        # Conflict 3: unowned graph asset
        graph_conflict_dest = os.path.join(self.test_root, "graph conflict dest")
        write_file(os.path.join(graph_conflict_dest, "_assets", "graph", "graph.css"), "user css")
        code_g, env_g = execute_static_build(conflict_kb, graph_conflict_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code_g, 2)
        self.assertEqual(env_g.status, "blocked")

        # Conflict 4: unowned kb-navigation.html
        nav_conflict_dest = os.path.join(self.test_root, "nav conflict dest")
        write_file(os.path.join(nav_conflict_dest, "kb-navigation.html"), "user nav")
        code_n, env_n = execute_static_build(conflict_kb, nav_conflict_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code_n, 2)
        self.assertEqual(env_n.status, "blocked")

        # Conflict 5: reserved kb-navigation.md source page
        reserved_kb = os.path.join(self.test_root, "reserved kb")
        reserved_dest = os.path.join(self.test_root, "reserved dest")
        setup_test_kb(reserved_kb, "# Home\n", entrypoint="content/index.md")
        write_file(os.path.join(reserved_kb, "content", "kb-navigation.md"), "# Reserved Conflict\n")
        code_r, env_r = execute_static_build(reserved_kb, reserved_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code_r, 2)
        self.assertEqual(env_r.status, "blocked")
        self.assertIn("reserved navigation page name", env_r.data["message"])

        # Destination inside KB
        code_in, env_in = execute_static_build(self.kb, os.path.join(self.kb, "static"), katex_assets_root=self.katex_assets)
        self.assertEqual(code_in, 2)
        self.assertEqual(env_in.status, "blocked")

        # Destination containing KB
        code_cnt, env_cnt = execute_static_build(self.kb, self.test_root, katex_assets_root=self.katex_assets)
        self.assertEqual(code_cnt, 2)
        self.assertEqual(env_cnt.status, "blocked")

    def test_cli_build_static_invocation(self) -> None:
        out_dest = os.path.join(self.test_root, "cli-output")
        kb_script = str(SCRIPTS_DIR / "kb.py")

        # Text format
        cmd_text = [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            kb_script,
            "build-static",
            "--root",
            self.kb,
            "--destination",
            out_dest,
            "--katex-assets-root",
            self.katex_assets,
        ]
        res_text = subprocess.run(cmd_text, capture_output=True, text=True, check=True)
        output = res_text.stdout
        self.assertIn("Command: build-static (Status: success)", output)
        self.assertIn("Pages generated:", output)

        # JSON format
        cmd_json = [
            sys.executable,
            "-B",
            "-X",
            "utf8",
            kb_script,
            "--format",
            "json",
            "build-static",
            "--root",
            self.kb,
            "--destination",
            out_dest,
            "--katex-assets-root",
            self.katex_assets,
        ]
        res_json = subprocess.run(cmd_json, capture_output=True, text=True, check=True)
        json_envelope = json.loads(res_json.stdout)
        self.assertEqual(json_envelope["command"], "build-static")
        self.assertEqual(json_envelope["status"], "success")
        self.assertEqual(json_envelope["data"]["skipped"], len(json_envelope["data"]["skipped_paths"]))

    def test_generated_page_math_runtime_delimiters(self) -> None:
        """Verify that generated HTML pages contain correctly escaped KaTeX delimiters and Node executes them with \\( and \\[."""
        out_dest = os.path.join(self.test_root, "math-delimiter-output")
        code, env = execute_static_build(self.kb, out_dest, katex_assets_root=self.katex_assets)
        self.assertEqual(code, 0)
        index_html = os.path.join(out_dest, "index.html")
        self.assertTrue(os.path.isfile(index_html))
        with open(index_html, "r", encoding="utf-8") as f:
            content = f.read()

        # Verify literal delimiters in script tag (two backslashes in HTML so JS evaluates to single backslash)
        self.assertIn(r"left:'\\('", content)
        self.assertIn(r"left:'\\['", content)

        # If node is available, execute the script tag in Node to verify options object
        node_exe = shutil.which("node")
        if node_exe:
            script = next(
                s
                for s in re.findall(r"<script[^>]*>(.*?)</script>", content, re.S)
                if "renderMathInElement" in s
            )
            js = (
                "global.document={body:{},addEventListener:(_,f)=>f()};"
                "global.renderMathInElement=(_,options)=>console.log(JSON.stringify(options));\n"
                + script
            )
            proc = subprocess.run(["node", "-e", js], capture_output=True, text=True, check=True)
            opts = json.loads(proc.stdout)
            delims = opts.get("delimiters", [])
            self.assertEqual(len(delims), 2)
            self.assertEqual(delims[0], {"left": r"\(", "right": r"\)", "display": False})
            self.assertEqual(delims[1], {"left": r"\[", "right": r"\]", "display": True})


if __name__ == "__main__":
    unittest.main()
