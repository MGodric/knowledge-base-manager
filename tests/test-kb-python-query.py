"""Unit tests for Python inspect, search, and read queries (Gate G2)."""

from __future__ import annotations

import hashlib
import os
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "knowledge-base-manager" / "scripts"))

from kb_core.query import inspect_command, read_command, search_command
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


class TestQueryCommands(unittest.TestCase):
    def setUp(self):
        self.temp_dir = create_temp_dir("kb-query-test-")
        self.kb_root = os.path.join(self.temp_dir, "test_kb")
        os.makedirs(self.kb_root, exist_ok=True)

        # Create kb.yaml
        write_file(
            os.path.join(self.kb_root, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )

        # Create content files
        self.c_index = write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            "# Knowledge Home\n\nWelcome to the knowledge base.\n- [Detection Method](knowledge/detection.md)\n",
        )
        self.c_det = write_file(
            os.path.join(self.kb_root, "content", "knowledge", "detection.md"),
            """---
id: kb-20260913-a001
type: method
status: draft
created: 2026-09-13
updated: 2026-09-13
tags:
  - testing
  - quality
---
# 检测方法

这里是检测方法的说明。

## 讨论

此方法有局限。详细限制见后续分析。

## 外部证据

- Project: `Core`; project-id: `core`; project-relative source: `docs/spec.md`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [spec.md](D:/Projects/core/docs/spec.md); `verified: 2026-09-13`; `revision: rev101`; supports: 局限性分析.
""",
        )
        self.c_math = write_file(
            os.path.join(self.kb_root, "content", "knowledge", "math_theory.md"),
            """---
id: kb-20260913-a002
type: concept
status: stable
created: 2026-09-13
updated: 2026-09-13
tags:
  - math
---
# 数学原理

公式内容：$\\mathrm{GF}(2^8)$。
""",
        )
        self.c_arch = write_file(
            os.path.join(self.kb_root, "content", "archive", "old_detection.md"),
            """---
id: kb-20260913-a003
type: method
status: deprecated
created: 2026-01-01
updated: 2026-01-01
---
# 旧检测方法

已废弃的检测方法。
""",
        )

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def _get_tree_hashes(self) -> dict[str, str]:
        hashes = {}
        for dp, _, fns in os.walk(self.kb_root):
            for fn in fns:
                fp = os.path.join(dp, fn)
                with open(fp, "rb") as f:
                    hashes[fp] = hashlib.sha256(f.read()).hexdigest()
        return hashes

    def test_inspect_list_and_paging(self):
        # 1. Default inspect lists content without archive
        code, env = inspect_command(root=self.kb_root)
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "ok")
        paths = [item["path"] for item in env.data["items"]]
        self.assertIn("index.md", paths)
        self.assertIn("knowledge/detection.md", paths)
        self.assertIn("knowledge/math_theory.md", paths)
        self.assertNotIn("archive/old_detection.md", paths)
        self.assertEqual(env.data["total"], 3)
        self.assertFalse(env.data["has_more"])

        # 2. Include archive
        code, env_arch = inspect_command(root=self.kb_root, include_archive=True)
        self.assertEqual(code, 0)
        self.assertEqual(env_arch.data["total"], 4)
        arch_paths = [item["path"] for item in env_arch.data["items"]]
        self.assertIn("archive/old_detection.md", arch_paths)

        # 3. Pagination with limit=1, offset=0
        code, env_p1 = inspect_command(root=self.kb_root, limit=1, offset=0)
        self.assertEqual(code, 0)
        self.assertEqual(len(env_p1.data["items"]), 1)
        self.assertTrue(env_p1.data["has_more"])
        view_id = env_p1.data["view_id"]

        # Pagination next page with expect_view
        code, env_p2 = inspect_command(root=self.kb_root, limit=1, offset=1, expect_view=view_id)
        self.assertEqual(code, 0)
        self.assertEqual(len(env_p2.data["items"]), 1)
        self.assertNotEqual(env_p1.data["items"][0]["path"], env_p2.data["items"][0]["path"])

        # Stale view_id rejected
        code, env_stale = inspect_command(
            root=self.kb_root, limit=1, offset=1, expect_view="invalid_view_id_12345"
        )
        self.assertEqual(code, 3)
        self.assertEqual(env_stale.status, "stale")
        self.assertTrue(any(d.code == "VIEW_CHANGED" for d in env_stale.diagnostics))

        # 4. Scope filter
        code, env_scope = inspect_command(root=self.kb_root, scope="knowledge")
        self.assertEqual(code, 0)
        self.assertEqual(env_scope.data["total"], 2)

        # 5. Type and status filter
        code, env_type = inspect_command(root=self.kb_root, page_type="concept")
        self.assertEqual(code, 0)
        self.assertEqual(env_type.data["total"], 1)
        self.assertEqual(env_type.data["items"][0]["id"], "kb-20260913-a002")

    def test_inspect_single_page(self):
        # Inspect single page with sections, relations, sources
        code, env = inspect_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            include=["sections", "relations", "sources"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "ok")
        page = env.data["page"]
        self.assertEqual(page["id"], "kb-20260913-a001")
        self.assertEqual(page["title"], "检测方法")

        # Sections
        sections = env.data["sections"]
        self.assertEqual(len(sections), 3)
        self.assertEqual(sections[0]["key"], "s1")
        self.assertEqual(sections[1]["key"], "s2")
        self.assertEqual(sections[1]["title"], "讨论")
        self.assertEqual(sections[1]["heading_path"], ["检测方法", "讨论"])

        # Sources
        sources = env.data["sources"]
        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0]["project_id"], "core")
        self.assertEqual(sources[0]["recognition"], "structured")

        # Non-existent page returns not_found / 3
        code, env_nf = inspect_command(root=self.kb_root, path="knowledge/missing.md")
        self.assertEqual(code, 3)
        self.assertEqual(env_nf.status, "not_found")

        # Escaping path returns invalid / 4
        code, env_esc = inspect_command(root=self.kb_root, path="../../escape.md")
        self.assertEqual(code, 4)
        self.assertEqual(env_esc.status, "invalid")

    def test_search_exact_ranking_and_hits(self):
        # 1. Search for Chinese phrase "局限"
        code, env = search_command(root=self.kb_root, queries=["局限"])
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "ok")
        self.assertEqual(env.data["total"], 1)
        item = env.data["items"][0]
        self.assertEqual(item["page"]["id"], "kb-20260913-a001")
        self.assertIn("局限", item["matched_queries"])
        self.assertIn("body", item["matched_fields"])

        hit = item["hits"][0]
        self.assertIn("局限", hit["snippet"])
        self.assertEqual(hit["section_key"], "s2")
        self.assertEqual(hit["heading_path"], ["检测方法", "讨论"])

        # 2. Search for exact title match "检测方法" vs body mention
        code, env_title = search_command(root=self.kb_root, queries=["检测方法"])
        self.assertEqual(code, 0)
        self.assertGreaterEqual(env_title.data["total"], 1)
        # Top hit must be the exact title match page
        top_page = env_title.data["items"][0]["page"]
        self.assertEqual(top_page["title"], "检测方法")

        # 3. No match returns 0 with status ok
        code, env_none = search_command(root=self.kb_root, queries=["绝对不存在的内容短语"])
        self.assertEqual(code, 0)
        self.assertEqual(env_none.status, "ok")
        self.assertEqual(env_none.data["total"], 0)
        self.assertEqual(len(env_none.data["items"]), 0)

        # 4. Search pagination and expect_view
        view_id = env_title.data["view_id"]
        code, env_pg = search_command(
            root=self.kb_root, queries=["检测方法"], limit=1, offset=0, expect_view=view_id
        )
        self.assertEqual(code, 0)

        # Invalid expect_view returns stale
        code, env_stale = search_command(
            root=self.kb_root, queries=["检测方法"], expect_view="stale_view_123"
        )
        self.assertEqual(code, 3)
        self.assertEqual(env_stale.status, "stale")

    def test_read_position_and_stale(self):
        # 1. Inspect detection.md to get content_hash
        _, env_insp = inspect_command(root=self.kb_root, path="knowledge/detection.md")
        page_hash = env_insp.data["page"]["content_hash"]

        # 2. Full page read
        code, env_full = read_command(
            root=self.kb_root, path="knowledge/detection.md", expect_hash=page_hash
        )
        self.assertEqual(code, 0)
        self.assertEqual(env_full.status, "ok")
        self.assertFalse(env_full.data["truncated"])
        self.assertIn("# 检测方法", env_full.data["text"])

        # 3. Read section s2 ("讨论")
        code, env_s2 = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            section_key="s2",
            expect_hash=page_hash,
        )
        self.assertEqual(code, 0)
        self.assertIn("## 讨论", env_s2.data["text"])
        self.assertIn("此方法有局限。", env_s2.data["text"])
        self.assertNotIn("## 外部证据", env_s2.data["text"])

        # 4. Read specific lines 17:19
        code, env_lines = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            lines_range="17:19",
            expect_hash=page_hash,
        )
        self.assertEqual(code, 0)
        self.assertEqual(env_lines.data["requested_range"]["start_line"], 17)
        self.assertEqual(env_lines.data["requested_range"]["end_line"], 19)

        # 5. Char truncation and pagination with next_offset
        code, env_trunc = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            lines_range="17:19",
            expect_hash=page_hash,
            max_chars=10,
        )
        self.assertEqual(code, 0)
        self.assertTrue(env_trunc.data["truncated"])
        self.assertEqual(len(env_trunc.data["text"]), 10)
        next_off = env_trunc.data["next_offset"]
        self.assertEqual(next_off, 10)

        # Continuation read with offset=10
        code, env_cont = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            lines_range="17:19",
            expect_hash=page_hash,
            max_chars=1000,
            offset=10,
        )
        self.assertEqual(code, 0)
        # Splicing chunk 1 + chunk 2 must reconstruct the full line range text
        spliced = env_trunc.data["text"] + env_cont.data["text"]
        self.assertEqual(spliced, env_lines.data["text"])

        # 6. Wrong hash triggers CONTENT_CHANGED / stale
        code, env_stale = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            section_key="s2",
            expect_hash="0000000000000000000000000000000000000000000000000000000000000000",
        )
        self.assertEqual(code, 3)
        self.assertEqual(env_stale.status, "stale")
        self.assertIsNone(env_stale.data)
        self.assertTrue(any(d.code == "CONTENT_CHANGED" for d in env_stale.diagnostics))

        # 7. Positional read without expect_hash returns invalid / 4
        code, env_nohash = read_command(
            root=self.kb_root,
            path="knowledge/detection.md",
            section_key="s2",
        )
        self.assertEqual(code, 4)
        self.assertEqual(env_nohash.status, "invalid")

    def test_read_only_integrity(self):
        # Record file hashes before queries
        before_hashes = self._get_tree_hashes()

        # Run inspect, search, and read
        inspect_command(root=self.kb_root, include_archive=True)
        search_command(root=self.kb_root, queries=["检测"])
        read_command(root=self.kb_root, path="knowledge/detection.md")

        # Compare hashes after queries
        after_hashes = self._get_tree_hashes()
        self.assertEqual(before_hashes, after_hashes)

    def test_escaped_manifest_and_scope_bounds(self):
        # 1. Invalid limit bounds
        rc, env = inspect_command(root=self.kb_root, limit=0)
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        rc, env = inspect_command(root=self.kb_root, limit=201)
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")

        # 2. Invalid scope
        rc, env = search_command(root=self.kb_root, queries=["检测"], scope="../outside")
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")

        # 3. Escaped manifest containment
        bad_kb = os.path.join(self.temp_dir, "bad_kb")
        os.makedirs(bad_kb, exist_ok=True)
        write_file(
            os.path.join(bad_kb, "kb.yaml"),
            "schema_version: 999\ncontent_dir: ../outside\nentrypoint: ../outside/outside.md\n",
        )
        for cmd_fn in (
            lambda: inspect_command(bad_kb),
            lambda: search_command(bad_kb, queries=["test"]),
            lambda: read_command(bad_kb, path="outside.md"),
        ):
            code, env = cmd_fn()
            self.assertEqual(code, 4)
            self.assertEqual(env.status, "invalid")
            self.assertTrue(any(d.code == "PATH_OUTSIDE_SCOPE" for d in env.diagnostics))

    def test_nested_collection_and_inbound_relations(self):
        # Map collects A (direct) and B (nested under A)
        m_path = os.path.join(self.kb_root, "content", "maps", "m.md")
        write_file(
            m_path,
            """---
id: kb-20260913-m001
type: map
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Map

<!-- kb-nav:children:start -->
- [Detection Method](../knowledge/detection.md)
  - [Math Theory](../knowledge/math_theory.md)
<!-- kb-nav:children:end -->
""",
        )
        # Inspect of map: only Detection Method is direct collection child
        rc, env_m = inspect_command(self.kb_root, path="maps/m.md", include=["relations"])
        self.assertEqual(rc, 0)
        colls = [r for r in env_m.data["relations"] if r["kind"] == "collection"]
        self.assertEqual(len(colls), 1)
        self.assertEqual(colls[0]["to"]["locator"], "knowledge/detection.md")
        self.assertEqual(colls[0]["evidence_refs"], ["link-1"])

        # Inspect of child page: inbound collection from map is discovered
        rc, env_c = inspect_command(self.kb_root, path="knowledge/detection.md", include=["relations"])
        self.assertEqual(rc, 0)
        inbound_colls = [r for r in env_c.data["relations"] if r["kind"] == "collection" and r["to"]["locator"] == "knowledge/detection.md"]
        self.assertEqual(len(inbound_colls), 1)
        self.assertEqual(inbound_colls[0]["from"]["locator"], "maps/m.md")
        self.assertEqual(inbound_colls[0]["evidence_refs"], ["link-1"])

    def test_unreadable_sibling_returns_partial_status(self):
        bad_path = os.path.join(self.kb_root, "content", "knowledge", "bad.md")
        with open(bad_path, "wb") as f:
            f.write(b"\xff\xfe\x80")
        try:
            # When relations requested: sibling scan fails -> partial / exit 2
            rc, env = inspect_command(self.kb_root, path="knowledge/detection.md", include=["relations"])
            self.assertEqual(rc, 2)
            self.assertEqual(env.status, "partial")
            self.assertTrue(any(d.code == "FILE_UNREADABLE" for d in env.diagnostics))

            # When relations NOT requested: sibling scan not performed -> ok / exit 0
            rc_sec, env_sec = inspect_command(self.kb_root, path="knowledge/detection.md", include=["sections"])
            self.assertEqual(rc_sec, 0)
            self.assertEqual(env_sec.status, "ok")
        finally:
            if os.path.exists(bad_path):
                os.remove(bad_path)

    def test_source_without_link_does_not_invent_provenance_relation(self):
        src_page = os.path.join(self.kb_root, "content", "knowledge", "nolink_source.md")
        write_file(
            src_page,
            """---
id: kb-20260913-s999
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# No Link Source

- Project: demo; project-id: demo; project-relative source: file.md; verified: 2026-09-13; revision: abc;
""",
        )
        try:
            rc, env = inspect_command(
                self.kb_root,
                path="knowledge/nolink_source.md",
                include=["sources", "relations"],
            )
            self.assertEqual(rc, 0)
            self.assertEqual(len(env.data["sources"]), 1)
            self.assertIsNone(env.data["sources"][0]["locator"])
            prov_relations = [r for r in env.data["relations"] if r["kind"] == "provenance"]
            self.assertEqual(len(prov_relations), 0)
        finally:
            if os.path.exists(src_page):
                os.remove(src_page)

    def test_parameter_enum_and_combination_validation(self):
        # 1. Invalid type enum
        rc, env = inspect_command(self.kb_root, page_type="invalid-type")
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        self.assertEqual(env.diagnostics[0].code, "INVALID_ARGUMENT")

        # 2. Invalid status enum
        rc, env = inspect_command(self.kb_root, status="invalid-status")
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        self.assertEqual(env.diagnostics[0].code, "INVALID_ARGUMENT")

        # 3. Invalid include item
        rc, env = inspect_command(self.kb_root, path="knowledge/detection.md", include=["not_an_include"])
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        self.assertEqual(env.diagnostics[0].code, "INVALID_ARGUMENT")

        # 4. Single page with explicit limit
        rc, env = inspect_command(self.kb_root, path="knowledge/detection.md", limit=10)
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        self.assertEqual(env.diagnostics[0].code, "INVALID_ARGUMENT")

        # 5. List mode with include
        rc, env = inspect_command(self.kb_root, include=["sections"])
        self.assertEqual(rc, 4)
        self.assertEqual(env.status, "invalid")
        self.assertEqual(env.diagnostics[0].code, "INVALID_ARGUMENT")

    def test_multiline_link_block_precision_does_not_generate_provenance(self):
        # R3-01: Multiline link in block precision must not borrow source line fields
        # and must not generate a provenance relation.
        multiline_content = """---
id: kb-20260913-0099
type: concept
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Multiline Link Page

[Actual
label](detection.md)
project-id: demo; project-relative source: detection.md; verified: 2026-09-13; revision: abc;
"""
        write_file(os.path.join(self.kb_root, "content", "knowledge", "multiline.md"), multiline_content)
        rc, env = inspect_command(self.kb_root, path="knowledge/multiline.md", include=["sources", "relations"])
        self.assertEqual(rc, 0)
        self.assertEqual(env.status, "ok")
        # Sources has structured metadata but locator is null
        sources = env.data["sources"]
        self.assertEqual(len(sources), 1)
        self.assertIsNone(sources[0]["locator"])
        self.assertEqual(sources[0]["recognition"], "structured")
        # Relations must not contain any provenance relation
        provenance_rels = [r for r in env.data["relations"] if r["kind"] == "provenance"]
        self.assertEqual(len(provenance_rels), 0)


if __name__ == "__main__":
    unittest.main()
