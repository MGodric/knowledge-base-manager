"""End-to-end small loop workflow test for Gate G4.

Flow: resolve -> search -> read -> test-driven write -> audit write -> pwsh static build.
"""

from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "knowledge-base-manager" / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from kb_core.audit import audit_command
from kb_core.paths import resolve_root
from kb_core.query import inspect_command, read_command, search_command
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


class TestWorkflowLoop(unittest.TestCase):
    def setUp(self):
        self.temp_dir = create_temp_dir("kb-workflow-loop-")
        self.kb_root = os.path.join(self.temp_dir, "test_kb")
        os.makedirs(self.kb_root, exist_ok=True)

        write_file(
            os.path.join(self.kb_root, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )
        write_file(
            os.path.join(self.kb_root, "content", "index.md"),
            """# Home Page

<!-- kb-nav:children:start -->
- [Main Project](projects/main.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "projects", "main.md"),
            """---
id: kb-20260913-0001
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Main Project

<!-- kb-nav:children:start -->
- [Existing Note](../knowledge/existing.md)
<!-- kb-nav:children:end -->
""",
        )
        write_file(
            os.path.join(self.kb_root, "content", "knowledge", "existing.md"),
            """---
id: kb-20260913-0002
type: concept
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Existing Note

Existing research concept.

## Details

Important background details for the project.
""",
        )

    def tearDown(self):
        cleanup_dir(self.temp_dir)

    def test_end_to_end_small_loop(self):
        # Step 1: resolve root
        res_code, res_env = resolve_root(requested=self.kb_root)
        self.assertEqual(res_code, 0)
        self.assertEqual(res_env.status, "resolved")
        resolved_root = res_env.data["resolved_root"]
        self.assertTrue(os.path.isdir(resolved_root))

        # Step 2: search for existing knowledge
        s_code, s_env = search_command(root=resolved_root, queries=["Existing Note"])
        self.assertEqual(s_code, 0)
        self.assertGreaterEqual(s_env.data["total"], 1)
        found_path = s_env.data["items"][0]["page"]["path"]
        self.assertEqual(found_path, "knowledge/existing.md")
        found_hash = s_env.data["items"][0]["page"]["content_hash"]

        # Step 3: read section 'Details' from the found page
        r_code, r_env = read_command(
            root=resolved_root,
            path=found_path,
            section_key="s2",
            expect_hash=found_hash,
        )
        self.assertEqual(r_code, 0)
        self.assertIn("## Details", r_env.data["text"])
        self.assertIn("Important background details", r_env.data["text"])

        # Step 4: test-driven write - create a new concept page and update parent project collection
        new_entry_rel = "knowledge/new_method.md"
        new_entry_full = os.path.join(resolved_root, "content", "knowledge", "new_method.md")
        write_file(
            new_entry_full,
            """---
id: kb-20260913-0003
type: method
status: draft
created: 2026-09-13
updated: 2026-09-13
tags:
  - workflow
---
# New Method

This method builds on Existing Note.

## Sources and reproduction

- Project: `Core`; project-id: `core`; project-relative source: `docs/guide.md`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [guide.md](D:/Projects/core/docs/guide.md); `verified: 2026-09-13`; `revision: rev202`; supports: new method validation.
""",
        )

        parent_proj_rel = "projects/main.md"
        parent_proj_full = os.path.join(resolved_root, "content", "projects", "main.md")
        write_file(
            parent_proj_full,
            """---
id: kb-20260913-0001
type: project
status: stable
created: 2026-09-13
updated: 2026-09-13
---
# Main Project

<!-- kb-nav:children:start -->
- [Existing Note](../knowledge/existing.md)
- [New Method](../knowledge/new_method.md)
<!-- kb-nav:children:end -->
""",
        )

        # Step 5: audit write profile with changed files
        aud_code, aud_env = audit_command(
            root=resolved_root,
            profile="write",
            changed=[new_entry_rel, parent_proj_rel],
        )
        self.assertEqual(aud_code, 0)
        self.assertEqual(aud_env.status, "ok")
        self.assertEqual(aud_env.data["errors"], 0)
        self.assertEqual(aud_env.data["warnings"], 0)

        # Step 6: PowerShell static site build interoperability check
        build_script = SCRIPTS_DIR / "kb-build-static.ps1"
        out_site_dir = os.path.join(self.temp_dir, "site_out")
        if build_script.is_file():
            ps_cmd = [
                "pwsh",
                "-NoProfile",
                "-File",
                str(build_script),
                "-Root",
                resolved_root,
                "-Destination",
                out_site_dir,
            ]
            res = subprocess.run(ps_cmd, capture_output=True, text=True, encoding="utf-8")
            self.assertEqual(
                res.returncode,
                0,
                f"Static build failed (code {res.returncode}):\n{res.stdout}\n{res.stderr}",
            )
            # Verify that output site contains generated html
            self.assertTrue(os.path.isfile(os.path.join(out_site_dir, "index.html")))
            self.assertTrue(os.path.isfile(os.path.join(out_site_dir, "projects", "main.html")))
            self.assertTrue(
                os.path.isfile(os.path.join(out_site_dir, "knowledge", "new_method.html"))
            )


if __name__ == "__main__":
    unittest.main()
