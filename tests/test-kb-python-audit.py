"""Unit tests for Python audit command (legacy and write profiles) (Gate G3)."""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
sys.path.insert(0, str(PROJECT_ROOT / "knowledge-base-manager" / "scripts"))

from kb_core.audit import audit_command
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


class TestAuditCommand(unittest.TestCase):
    def setUp(self):
        self.temp_dir = create_temp_dir("kb-audit-test-")
        self.kb_root = os.path.join(self.temp_dir, "test_kb")
        os.makedirs(self.kb_root, exist_ok=True)

        write_file(
            os.path.join(self.kb_root, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def _setup_valid_kb(self) -> None:
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Project A](projects/proj_a.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "projects", "proj_a.md"),
            """---
id: kb-20260913-0001
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Project A

<!-- kb-nav:children:start -->
- [Entry 1](../knowledge/entry_1.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "entry_1.md"),
            """---
id: kb-20260913-0002
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Entry 1

Detailed concept explanation.
""",
        )

    def test_legacy_profile_valid_kb(self):
        self._setup_valid_kb()
        code, env = audit_command(root=self.kb_root, profile="legacy")
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "ok")
        self.assertEqual(env.data["errors"], 0)
        self.assertEqual(env.data["warnings"], 0)
        self.assertEqual(env.data["checked_scope"]["collection"], "none")

    def test_write_profile_valid_kb(self):
        self._setup_valid_kb()
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/entry_1.md", "projects/proj_a.md"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "ok")
        self.assertEqual(env.data["errors"], 0)
        self.assertEqual(env.data["checked_scope"]["collection"], "full")

    def test_write_profile_changed_nonexistent_returns_4(self):
        self._setup_valid_kb()
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/non_existent.md"],
        )
        self.assertEqual(code, 4)
        self.assertEqual(env.status, "invalid")
        self.assertTrue(any(d.code == "INVALID_ARGUMENT" for d in env.diagnostics))

    def test_write_profile_parent_missing(self):
        # Entry 2 is a formal entry with no collection parent
        self._setup_valid_kb()
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "entry_2.md"),
            """---
id: kb-20260913-0003
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Entry 2

Orphan concept.
""",
        )
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/entry_2.md"],
        )
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "validation_failed")
        issues = env.data["issues"]
        p_missing = [i for i in issues if i["code"] == "COLLECTION_PARENT_MISSING"]
        self.assertEqual(len(p_missing), 1)
        self.assertEqual(p_missing[0]["file"], "knowledge/entry_2.md")
        self.assertTrue(p_missing[0]["in_changed"])

    def test_write_profile_plain_reference_not_collection(self):
        # Entry 2 has an ordinary body reference from index.md, but NOT inside a collection block
        self._setup_valid_kb()
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "entry_2.md"),
            """---
id: kb-20260913-0003
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Entry 2

Plain referenced concept.
""",
        )
        # Add plain link outside collection block in index.md
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Project A](projects/proj_a.md)
<!-- kb-nav:children:end -->

See also: [Entry 2](knowledge/entry_2.md)
""",
        )
        # In legacy profile: no errors, no warnings (inboundCount > 0, so no orphan warning)
        code_leg, env_leg = audit_command(root=self.kb_root, profile="legacy")
        self.assertEqual(code_leg, 0)

        # In write profile: ordinary reference does NOT satisfy collection parent requirement
        code_wr, env_wr = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/entry_2.md"],
        )
        self.assertEqual(code_wr, 2)
        p_missing = [i for i in env_wr.data["issues"] if i["code"] == "COLLECTION_PARENT_MISSING"]
        self.assertEqual(len(p_missing), 1)
        self.assertEqual(p_missing[0]["file"], "knowledge/entry_2.md")

    def test_write_profile_nested_collection_list_not_direct_parent(self):
        # Nested list item inside collection block does not count as direct collection edge
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Project A](projects/proj_a.md)
  - [Nested Entry](knowledge/nested.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "projects", "proj_a.md"),
            """---
id: kb-20260913-0001
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Project A
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "nested.md"),
            """---
id: kb-20260913-0004
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Nested Entry
""",
        )
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/nested.md"],
        )
        self.assertEqual(code, 2)
        # Nested entry has no direct collection parent
        p_missing = [i for i in env.data["issues"] if i["code"] == "COLLECTION_PARENT_MISSING"]
        self.assertEqual(len(p_missing), 1)
        self.assertEqual(p_missing[0]["file"], "knowledge/nested.md")

    def test_write_profile_multiple_parents_valid(self):
        # Entry 1 collected by both Project A and Map B: completely valid!
        self._setup_valid_kb()
        # Add Map B which also collects Entry 1
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Project A](projects/proj_a.md)
- [Map B](maps/map_b.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "maps", "map_b.md"),
            """---
id: kb-20260913-0005
type: map
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Map B

<!-- kb-nav:children:start -->
- [Entry 1](../knowledge/entry_1.md)
<!-- kb-nav:children:end -->
""",
        )
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["knowledge/entry_1.md"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(env.data["errors"], 0)

    def test_write_profile_collection_cycle(self):
        # Project A collects Project B, and Project B collects Project A -> cycle!
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Project A](projects/proj_a.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "projects", "proj_a.md"),
            """---
id: kb-20260913-0001
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Project A

<!-- kb-nav:children:start -->
- [Project B](proj_b.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "projects", "proj_b.md"),
            """---
id: kb-20260913-0006
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Project B

<!-- kb-nav:children:start -->
- [Project A](proj_a.md)
<!-- kb-nav:children:end -->
""",
        )
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["projects/proj_a.md"],
        )
        self.assertEqual(code, 2)
        cycles = [i for i in env.data["issues"] if i["code"] == "COLLECTION_CYCLE"]
        self.assertGreater(len(cycles), 0)

    def test_write_profile_ordered_list_collection(self):
        # Ordered list inside collection block should pass write audit without false COLLECTION_PARENT_MISSING
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Map](maps/m.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "maps", "m.md"),
            """---
id: kb-20260913-b001
type: map
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Map

<!-- kb-nav:children:start -->
1. [Entry 1](../knowledge/entry_1.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "entry_1.md"),
            """---
id: kb-20260913-b002
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Entry 1

Detailed concept explanation.
""",
        )
        code, env = audit_command(
            root=self.kb_root,
            profile="write",
            changed=["maps/m.md"],
        )
        self.assertEqual(code, 0)
        self.assertEqual(env.data["errors"], 0)

    def test_escaped_manifest_audit(self):
        bad_kb = os.path.join(self.temp_dir, "bad_kb_audit")
        os.makedirs(bad_kb, exist_ok=True)
        write_file(
            os.path.join(bad_kb, "kb.yaml"),
            "schema_version: 999\ncontent_dir: ../outside\nentrypoint: ../outside/outside.md\n",
        )
        code, env = audit_command(bad_kb, profile="write")
        self.assertEqual(code, 3)
        self.assertEqual(env.status, "failed")
        self.assertTrue(any(i["code"] == "SCHEMA_VERSION_UNSUPPORTED" for i in env.data["issues"]))

    def test_encoded_hash_filename_link_valid(self):
        # A file named a#b.md linked via a%23b.md resolves cleanly without LINK_BROKEN
        write_file(
            os.path.join(self.kb_root, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            "# Home\n\n- [Hash](knowledge/a%23b.md)\n",
        )
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "a#b.md"),
            """---
id: kb-20260913-0009
type: concept
status: draft
created: 2026-09-13
updated: 2026-09-13
---
# Hash Page

Content.
""",
        )
        code, env = audit_command(self.kb_root, profile="legacy")
        self.assertEqual(code, 0)
        self.assertEqual(len(env.data["issues"]), 0)

    def test_nested_configured_homepage_directory_links_permitted(self):
        # R3-03: Configured homepage may link to top-level directories outside collections
        os.makedirs(os.path.join(self.kb_root, "content", "home"), exist_ok=True)
        types = ("projects", "maps", "knowledge", "sources", "decisions", "inbox", "archive", "assets")
        for name in types:
            os.makedirs(os.path.join(self.kb_root, "content", name), exist_ok=True)

        write_file(
            os.path.join(self.kb_root, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/home/start.md\n",
        )
        type_links = "\n".join(f"- [Type](../{name}/)" for name in types)
        write_file(
            os.path.join(self.kb_root, "content", "home", "start.md"),
            f"# Home\n\n{type_links}\n",
        )

        code, env = audit_command(self.kb_root, profile="legacy")
        self.assertEqual(code, 0)
        self.assertEqual(env.data["errors"], 0)
        self.assertEqual(env.data["warnings"], 0)
        self.assertEqual(len(env.data["issues"]), 0)


if __name__ == "__main__":
    unittest.main()
