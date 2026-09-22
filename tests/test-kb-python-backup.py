"""Exhaustive tests for Python backup, verify-backup, and restore (Gate G5 / Phase B).

Ported from tests/test-kb-backup.ps1.
"""

from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

TEST_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TEST_DIR.parent
SCRIPTS_DIR = PROJECT_ROOT / "knowledge-base-manager" / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from kb_core.audit import audit_command
from kb_core.backup import (
    execute_backup,
    get_backup_plan,
    get_plan_digest,
    get_plan_change_summary,
    get_sha256,
    new_snapshot_record,
    restore_backup,
    test_snapshot_record,
    verify_backup,
)
from kb_core.paths import (
    get_canonical_path,
    get_safe_tree_files,
    test_path_inside_root,
)
from kb_python_test_support import cleanup_dir, create_temp_dir, write_file


class Fixture:
    def __init__(self, root: str, project: str, source: str):
        self.root = root
        self.project = project
        self.source = source


def new_fixture(temp_dir: str, name: str) -> Fixture:
    root = os.path.join(temp_dir, name, "知识库 空格")
    project = os.path.join(temp_dir, name, "项目 空格")
    os.makedirs(root, exist_ok=True)
    os.makedirs(project, exist_ok=True)

    write_file(
        os.path.join(root, "kb.yaml"),
        "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\nunknown_field: preserve-me\n",
    )
    write_file(
        os.path.join(root, "content", "index.md"),
        "# KB\n\n- [来源](knowledge/来源 note.md)\n",
    )
    source_file = os.path.join(project, "资料", "证据 文件.txt")
    write_file(source_file, "evidence unicode")
    source_forward = source_file.replace("\\", "/")

    来源_note = f"""---
id: kb-20260830-a1b2
type: source
status: draft
created: 2026-08-30
updated: 2026-08-30
---
# 来源 note

- Project: `Demo Project`; project-id: `demo-project`; project-relative source: `资料/证据 文件.txt`; provenance prose keeps {source_forward} unchanged; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [证据]({source_forward}); verified: 2026-08-30; version-state: unversioned.
- Project: `Demo Project`; project-id: `demo-project`; project-relative source: `资料/证据 文件.txt`; external local path (outside knowledge base; machine-specific) <!-- kb-external-local -->: [重复一]({source_forward}) and [重复二]({source_forward}); verified: 2026-08-30; version-state: unversioned.
"""
    write_file(os.path.join(root, "content", "knowledge", "来源 note.md"), 来源_note)
    return Fixture(root=root, project=project, source=source_file)


def update_bundle_checksums(bundle: str) -> None:
    checksum_path = os.path.join(bundle, "CHECKSUMS.sha256")
    files = [
        f
        for f in get_safe_tree_files(bundle, "portable bundle")
        if f.lower() != checksum_path.lower()
    ]
    lines = [
        f"{get_sha256(f)}  {os.path.relpath(f, bundle).replace(os.sep, '/')}"
        for f in sorted(files)
    ]
    with open(checksum_path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


class TestKbBackup(unittest.TestCase):
    def setUp(self):
        self.temp = create_temp_dir("kb-backup-tests-")

    def tearDown(self):
        cleanup_dir(self.temp)

    def test_path_safety_primitives(self):
        if sys.platform == "win32":
            self.assertEqual(get_canonical_path("C:\\"), "C:")
            self.assertTrue(test_path_inside_root("C:\\Windows", "C:\\"))

    def test_plan_determinism_and_content(self):
        fixture = new_fixture(self.temp, "main")
        parent = os.path.join(self.temp, "backup parent")

        plan1 = get_backup_plan(fixture.root, parent, mode="ReferenceComplete")
        plan2 = get_backup_plan(fixture.root, parent, mode="ReferenceComplete")
        self.assertEqual(plan1["plan_digest"], plan2["plan_digest"])

        files = plan1["files"]
        self.assertEqual(len(files), 4)
        file_keys = [f"{r['kind']}|{r['portable_path']}" for r in files]
        expected_keys = [
            "kb_manifest|kb.yaml",
            "content|content/index.md",
            "content|content/knowledge/来源 note.md",
            "external|external/projects/demo-project/资料/证据 文件.txt",
        ]
        self.assertEqual(file_keys, expected_keys)

        for rec in files:
            self.assertTrue(bool(rec["source_path"]))
            self.assertGreaterEqual(rec["size_bytes"], 0)
            self.assertTrue(bool(rec["mtime_utc"]))
            self.assertRegex(rec["sha256"], r"^[0-9a-f]{64}$")

        ext_recs = [r for r in files if r["kind"] == "external"]
        self.assertEqual(len(ext_recs), 1)
        self.assertEqual(ext_recs[0]["project_id"], "demo-project")
        self.assertEqual(ext_recs[0]["project_relative_source"], "资料/证据 文件.txt")

        # Read-only plan must not create destination or bundle
        self.assertFalse(os.path.exists(parent))
        self.assertFalse(os.path.exists(os.path.join(parent, "portable-kb")))

    def test_confirmation_required_and_reconfirm_required(self):
        fixture = new_fixture(self.temp, "main")

        # Execute without digest
        missing_dest = os.path.join(self.temp, "missing confirmation")
        code, env = execute_backup(
            root=fixture.root,
            destination=missing_dest,
            execute=True,
            confirmed_plan_digest="",
        )
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "confirmation_required")
        self.assertFalse(os.path.exists(missing_dest))

        # Execute with wrong digest
        wrong_dest = os.path.join(self.temp, "wrong confirmation")
        code, env = execute_backup(
            root=fixture.root,
            destination=wrong_dest,
            execute=True,
            confirmed_plan_digest="0" * 64,
        )
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "reconfirm_required")
        self.assertRegex(env.data["plan"]["plan_digest"], r"^[0-9a-f]{64}$")
        self.assertGreater(len(env.data["change_summary"]), 0)
        self.assertFalse(os.path.exists(wrong_dest))

    def test_backup_execution_and_byte_preservation(self):
        fixture = new_fixture(self.temp, "main")
        parent = os.path.join(self.temp, "backup parent")
        orig_note = os.path.join(fixture.root, "content", "knowledge", "来源 note.md")
        with open(orig_note, "rb") as f:
            before_bytes = f.read()

        # Step 1: get plan
        code, plan_env = execute_backup(root=fixture.root, destination=parent, execute=False)
        self.assertEqual(code, 0)
        self.assertEqual(plan_env.status, "plan")
        digest = plan_env.data["plan"]["plan_digest"]

        # Step 2: execute with confirmed digest
        code, created_env = execute_backup(
            root=fixture.root,
            destination=parent,
            execute=True,
            confirmed_plan_digest=digest,
        )
        self.assertEqual(code, 0)
        self.assertEqual(created_env.status, "created")

        # Live KB must remain byte-identical
        with open(orig_note, "rb") as f:
            after_bytes = f.read()
        self.assertEqual(before_bytes, after_bytes)

        # Copied marked links rewritten, provenance prose kept
        bundle = os.path.join(parent, "portable-kb")
        copy_note = os.path.join(bundle, "content", "knowledge", "来源 note.md")
        with open(copy_note, "r", encoding="utf-8") as f:
            copy_text = f.read()
        self.assertIn("kb-portable-source", copy_text)
        self.assertNotIn("kb-external-local", copy_text)
        self.assertIn(fixture.source.replace("\\", "/"), copy_text)

        # Deduplication of external files
        ext_files = get_safe_tree_files(os.path.join(bundle, "external"), "external")
        self.assertEqual(len(ext_files), 1)

        # Unknown kb.yaml fields survive backup
        with open(os.path.join(bundle, "kb.yaml"), "r", encoding="utf-8") as f:
            manifest_text = f.read()
        self.assertIn("unknown_field: preserve-me", manifest_text)
        self.assertIn("external_dir: external", manifest_text)

        # Verification passes
        v_code, v_env = verify_backup(bundle)
        self.assertEqual(v_code, 0)
        self.assertEqual(v_env.status, "valid")

        # Audit passes
        a_code, a_env = audit_command(bundle, profile="legacy")
        self.assertEqual(a_code, 0)
        self.assertEqual(a_env.status, "ok")

        # Restore flow: isolate original project
        isolated_proj = os.path.join(self.temp, "main", "isolated-original-project")
        shutil.move(fixture.project, isolated_proj)

        restore_dest = os.path.join(self.temp, "other-drive-neutral", "restored")
        # Restore plan
        r_plan_code, r_plan_env = restore_backup(bundle=bundle, destination=restore_dest, execute=False)
        self.assertEqual(r_plan_code, 0)
        self.assertEqual(r_plan_env.status, "plan")

        # Restore execute
        r_code, r_env = restore_backup(bundle=bundle, destination=restore_dest, execute=True)
        self.assertEqual(r_code, 0)
        self.assertEqual(r_env.status, "restored")

        # Restored KB passes audit
        r_audit_code, r_audit_env = audit_command(restore_dest, profile="legacy")
        self.assertEqual(r_audit_code, 0)

        # Restore to existing directory refuses
        conflict_code, _ = restore_backup(bundle=bundle, destination=restore_dest, execute=True)
        self.assertEqual(conflict_code, 2)

        # Tampering causes verify failure
        ext_target = os.path.join(bundle, "external", "projects", "demo-project", "资料", "证据 文件.txt")
        with open(ext_target, "a", encoding="utf-8") as f:
            f.write("tamper")
        tamper_code, tamper_env = verify_backup(bundle)
        self.assertEqual(tamper_code, 2)
        self.assertEqual(tamper_env.status, "invalid")

    def test_missing_registered_source_blocks_backup(self):
        missing = new_fixture(self.temp, "missing")
        os.remove(missing.source)
        code, env = execute_backup(root=missing.root, destination=os.path.join(self.temp, "missing backup"))
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")

    def test_unmarked_legacy_absolute_path_and_ignore(self):
        legacy = new_fixture(self.temp, "legacy")
        note_path = os.path.join(legacy.root, "content", "knowledge", "来源 note.md")
        with open(note_path, "a", encoding="utf-8") as f:
            f.write(f"\n[legacy]({legacy.source})\n")

        code, env = execute_backup(root=legacy.root, destination=os.path.join(self.temp, "legacy backup"))
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")

        # Ignored legacy path succeeds
        code_ign, env_ign = execute_backup(
            root=legacy.root,
            destination=os.path.join(self.temp, "legacy ignored"),
            ignore_legacy_path=[f"{legacy.source}|historical duplicate locator"],
        )
        self.assertEqual(code_ign, 0)
        self.assertEqual(env_ign.status, "plan")

    def test_project_relative_traversal_blocks_backup(self):
        traversal = new_fixture(self.temp, "traversal")
        note_path = os.path.join(traversal.root, "content", "knowledge", "来源 note.md")
        with open(note_path, "r", encoding="utf-8") as f:
            txt = f.read()
        with open(note_path, "w", encoding="utf-8") as f:
            f.write(txt.replace("资料/证据 文件.txt", "../escape.txt"))

        code, env = execute_backup(root=traversal.root, destination=os.path.join(self.temp, "traversal backup"))
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")

    def test_destination_inside_source_root_blocks(self):
        fixture = new_fixture(self.temp, "inside")
        code, env = execute_backup(root=fixture.root, destination=os.path.join(fixture.root, "bad destination"))
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")

    def test_mode_blockers(self):
        fixture = new_fixture(self.temp, "mode-blockers")
        # ProjectSnapshot blocker
        code_snap, env_snap = execute_backup(
            root=fixture.root,
            destination=os.path.join(self.temp, "snap"),
            mode="ProjectSnapshot",
        )
        self.assertEqual(code_snap, 2)
        self.assertIn("ProjectSnapshot is deliberately deferred", env_snap.data["message"])

        # Relink restore blocker
        code_rel, env_rel = restore_backup(
            bundle=os.path.join(self.temp, "dummy"),
            destination=os.path.join(self.temp, "relink"),
            mode="Relink",
        )
        self.assertEqual(code_rel, 2)
        self.assertIn("Relink restore is not implemented", env_rel.data["message"])

    def test_zero_external_sources(self):
        zero = os.path.join(self.temp, "zero external", "kb")
        os.makedirs(zero, exist_ok=True)
        write_file(
            os.path.join(zero, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )
        write_file(os.path.join(zero, "content", "index.md"), "# Zero external\n")

        zero_parent = os.path.join(self.temp, "zero external backup")
        code_plan, env_plan = execute_backup(root=zero, destination=zero_parent, execute=False)
        self.assertEqual(code_plan, 0)
        digest = env_plan.data["plan"]["plan_digest"]

        code_exec, env_exec = execute_backup(
            root=zero, destination=zero_parent, execute=True, confirmed_plan_digest=digest
        )
        self.assertEqual(code_exec, 0)

        zero_bundle = os.path.join(zero_parent, "portable-kb")
        self.assertTrue(os.path.isdir(os.path.join(zero_bundle, "external", "projects")))

        v_code, v_env = verify_backup(zero_bundle)
        self.assertEqual(v_code, 0)

        # Restore to empty existing destination rejected
        existing_empty = os.path.join(self.temp, "existing empty restore")
        os.makedirs(existing_empty, exist_ok=True)
        r_code, _ = restore_backup(bundle=zero_bundle, destination=existing_empty)
        self.assertEqual(r_code, 2)

    @unittest.skipUnless(sys.platform == "win32", "Junction tests require Windows")
    def test_junction_rejections(self):
        zero = os.path.join(self.temp, "zero-junc", "kb")
        os.makedirs(zero, exist_ok=True)
        write_file(
            os.path.join(zero, "kb.yaml"),
            "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n",
        )
        write_file(os.path.join(zero, "content", "index.md"), "# Zero\n")

        # 1. Junction in backup destination ancestors
        redirect_target = os.path.join(self.temp, "redirect target")
        redirect_parent = os.path.join(self.temp, "redirect parent")
        os.makedirs(redirect_target, exist_ok=True)
        subprocess.run(["cmd", "/c", "mklink", "/J", redirect_parent, redirect_target], check=True, capture_output=True)

        try:
            code_rb, env_rb = execute_backup(root=zero, destination=os.path.join(redirect_parent, "backup"))
            self.assertEqual(code_rb, 2)
            self.assertRegex(env_rb.data["message"], r"junction|symbolic link")

            code_rr, env_rr = restore_backup(bundle=zero, destination=os.path.join(redirect_parent, "restored"))
            self.assertEqual(code_rr, 2)
            self.assertRegex(env_rr.data["message"], r"junction|symbolic link")
        finally:
            subprocess.run(["cmd", "/c", "rmdir", redirect_parent], capture_output=True)

        # 2. Junction in content tree
        junc_kb = os.path.join(self.temp, "junction source kb")
        junc_content_tgt = os.path.join(self.temp, "junction source content")
        os.makedirs(junc_kb, exist_ok=True)
        os.makedirs(junc_content_tgt, exist_ok=True)
        write_file(os.path.join(junc_kb, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")
        write_file(os.path.join(junc_content_tgt, "index.md"), "# Junction source\n")
        junc_content_path = os.path.join(junc_kb, "content")
        subprocess.run(["cmd", "/c", "mklink", "/J", junc_content_path, junc_content_tgt], check=True, capture_output=True)

        try:
            code_js, env_js = execute_backup(root=junc_kb, destination=os.path.join(self.temp, "junction backup"))
            self.assertEqual(code_js, 2)
            self.assertRegex(env_js.data["message"], r"junction|symbolic link")
        finally:
            subprocess.run(["cmd", "/c", "rmdir", junc_content_path], capture_output=True)

        # 3. Junction inside bundle rejected by verify
        bundle_parent = os.path.join(self.temp, "valid bundle parent")
        _, p_env = execute_backup(root=zero, destination=bundle_parent, execute=False)
        execute_backup(root=zero, destination=bundle_parent, execute=True, confirmed_plan_digest=p_env.data["plan"]["plan_digest"])
        bundle_path = os.path.join(bundle_parent, "portable-kb")

        bundle_junc = os.path.join(bundle_path, "redirected")
        subprocess.run(["cmd", "/c", "mklink", "/J", bundle_junc, redirect_target], check=True, capture_output=True)
        try:
            v_code, v_env = verify_backup(bundle_path)
            self.assertEqual(v_code, 3)
            self.assertEqual(v_env.status, "fatal")
            self.assertRegex(v_env.data["issues"][0], r"junction|symbolic link")
        finally:
            subprocess.run(["cmd", "/c", "rmdir", bundle_junc], capture_output=True)

    def test_missing_and_invalid_project_id(self):
        missing_id = new_fixture(self.temp, "missing-id")
        note_path = os.path.join(missing_id.root, "content", "knowledge", "来源 note.md")
        with open(note_path, "r", encoding="utf-8") as f:
            txt = f.read()
        with open(note_path, "w", encoding="utf-8") as f:
            import re
            f.write(re.sub(r"project-id:[^;；]+;\s*", "", txt))

        code, _ = execute_backup(root=missing_id.root, destination=os.path.join(self.temp, "missing-id backup"))
        self.assertEqual(code, 2)

        invalid_id = new_fixture(self.temp, "invalid-id")
        note_path2 = os.path.join(invalid_id.root, "content", "knowledge", "来源 note.md")
        with open(note_path2, "r", encoding="utf-8") as f:
            txt2 = f.read()
        with open(note_path2, "w", encoding="utf-8") as f:
            f.write(txt2.replace("demo-project", "Invalid Project"))

        code2, _ = execute_backup(root=invalid_id.root, destination=os.path.join(self.temp, "invalid-id backup"))
        self.assertEqual(code2, 2)

    def test_absolute_code_span_blocks(self):
        code_legacy = new_fixture(self.temp, "code-legacy")
        note_path = os.path.join(code_legacy.root, "content", "knowledge", "来源 note.md")
        with open(note_path, "a", encoding="utf-8") as f:
            f.write(f"\nLegacy path: `{code_legacy.source}`\n")

        code, _ = execute_backup(root=code_legacy.root, destination=os.path.join(self.temp, "code legacy backup"))
        self.assertEqual(code, 2)

    def test_pre_write_drift_detection(self):
        # 1. External content mutation
        ext_drift = new_fixture(self.temp, "external-drift")
        parent = os.path.join(self.temp, "ext drift parent")
        _, plan_env = execute_backup(root=ext_drift.root, destination=parent, execute=False)
        digest = plan_env.data["plan"]["plan_digest"]

        # Mutate external source
        with open(ext_drift.source, "r+b") as f:
            b = bytearray(f.read())
            b[0] ^= 1
            f.seek(0)
            f.write(b)

        code, env = execute_backup(root=ext_drift.root, destination=parent, execute=True, confirmed_plan_digest=digest)
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "reconfirm_required")
        self.assertFalse(os.path.exists(parent))

        # 2. Mtime drift
        mtime_drift = new_fixture(self.temp, "mtime-drift")
        m_parent = os.path.join(self.temp, "mtime drift parent")
        _, m_plan = execute_backup(root=mtime_drift.root, destination=m_parent, execute=False)
        m_digest = m_plan.data["plan"]["plan_digest"]

        idx_path = os.path.join(mtime_drift.root, "content", "index.md")
        st = os.stat(idx_path)
        os.utime(idx_path, (st.st_atime + 5, st.st_mtime + 5))

        m_code, m_env = execute_backup(root=mtime_drift.root, destination=m_parent, execute=True, confirmed_plan_digest=m_digest)
        m_actual_plan = get_backup_plan(mtime_drift.root, m_parent, mode="ReferenceComplete")
        self.assertEqual(m_code, 2)
        self.assertEqual(m_env.status, "reconfirm_required")
        self.assertNotEqual(m_actual_plan["plan_digest"], m_digest)
        m_summary = get_plan_change_summary(m_plan.data["plan"], m_actual_plan)
        self.assertTrue(any("mtime_utc" in c for c in m_summary))

        # 3. Addition drift
        add_drift = new_fixture(self.temp, "add-drift")
        a_parent = os.path.join(self.temp, "add drift parent")
        _, a_plan = execute_backup(root=add_drift.root, destination=a_parent, execute=False)
        a_digest = a_plan.data["plan"]["plan_digest"]

        write_file(os.path.join(add_drift.root, "content", "new.md"), "# added\n")
        a_code, a_env = execute_backup(root=add_drift.root, destination=a_parent, execute=True, confirmed_plan_digest=a_digest)
        a_actual_plan = get_backup_plan(add_drift.root, a_parent, mode="ReferenceComplete")
        self.assertEqual(a_code, 2)
        self.assertEqual(a_env.status, "reconfirm_required")
        a_summary = get_plan_change_summary(a_plan.data["plan"], a_actual_plan)
        self.assertTrue(any("source added" in c for c in a_summary))

        # 4. Rename drift
        ren_drift = new_fixture(self.temp, "ren-drift")
        r_parent = os.path.join(self.temp, "ren drift parent")
        _, r_plan = execute_backup(root=ren_drift.root, destination=r_parent, execute=False)
        r_digest = r_plan.data["plan"]["plan_digest"]

        shutil.move(os.path.join(ren_drift.root, "content", "index.md"), os.path.join(ren_drift.root, "content", "renamed.md"))
        ren_code, ren_env = execute_backup(root=ren_drift.root, destination=r_parent, execute=True, confirmed_plan_digest=r_digest)
        self.assertEqual(ren_code, 2)
        self.assertEqual(ren_env.status, "reconfirm_required")

        # 5. Mapping drift
        map_drift = new_fixture(self.temp, "map-drift")
        map_parent = os.path.join(self.temp, "map drift parent")
        _, map_plan = execute_backup(root=map_drift.root, destination=map_parent, execute=False)
        map_digest = map_plan.data["plan"]["plan_digest"]

        note_file = os.path.join(map_drift.root, "content", "knowledge", "来源 note.md")
        with open(note_file, "r", encoding="utf-8") as f:
            n_txt = f.read()
        with open(note_file, "w", encoding="utf-8") as f:
            f.write(n_txt.replace("version-state: unversioned", "version-state: changed-state"))

        map_code, map_env = execute_backup(root=map_drift.root, destination=map_parent, execute=True, confirmed_plan_digest=map_digest)
        map_actual_plan = get_backup_plan(map_drift.root, map_parent, mode="ReferenceComplete")
        self.assertEqual(map_code, 2)
        self.assertEqual(map_env.status, "reconfirm_required")
        map_summary = get_plan_change_summary(map_plan.data["plan"], map_actual_plan)
        self.assertTrue(any("reference mapping" in c for c in map_summary))

        # 6. Manifest drift
        man_drift = new_fixture(self.temp, "man-drift")
        man_parent = os.path.join(self.temp, "man drift parent")
        _, man_plan = execute_backup(root=man_drift.root, destination=man_parent, execute=False)
        man_digest = man_plan.data["plan"]["plan_digest"]

        kb_yaml = os.path.join(man_drift.root, "kb.yaml")
        with open(kb_yaml, "r", encoding="utf-8") as f:
            y_txt = f.read()
        with open(kb_yaml, "w", encoding="utf-8") as f:
            f.write(y_txt.replace("unknown_field: preserve-me", "unknown_field: changed-after-plan"))

        man_code, man_env = execute_backup(root=man_drift.root, destination=man_parent, execute=True, confirmed_plan_digest=man_digest)
        man_actual_plan = get_backup_plan(man_drift.root, man_parent, mode="ReferenceComplete")
        self.assertEqual(man_code, 2)
        self.assertEqual(man_env.status, "reconfirm_required")
        man_summary = get_plan_change_summary(man_plan.data["plan"], man_actual_plan)
        self.assertTrue(any("kb_manifest" in c for c in man_summary))

    def test_snapshot_record_comparison(self):
        fixture = new_fixture(self.temp, "record-comp")
        plan = get_backup_plan(fixture.root, os.path.join(self.temp, "rc-parent"))
        ext_record = [r for r in plan["files"] if r["kind"] == "external"][0]
        self.assertTrue(test_snapshot_record(ext_record))

        st = os.stat(ext_record["source_path"])
        os.utime(ext_record["source_path"], (st.st_atime + 7, st.st_mtime + 7))
        self.assertFalse(test_snapshot_record(ext_record))

    def test_staging_audit_failure(self):
        stage_bad = os.path.join(self.temp, "stage-bad", "kb")
        os.makedirs(stage_bad, exist_ok=True)
        write_file(os.path.join(stage_bad, "kb.yaml"), "schema_version: 1\ncontent_dir: content\nentrypoint: content/index.md\n")
        write_file(os.path.join(stage_bad, "content", "index.md"), "# Bad\n\n[missing](missing.md)\n")

        stage_parent = os.path.join(self.temp, "stage bad backup")
        _, plan = execute_backup(root=stage_bad, destination=stage_parent, execute=False)
        code, env = execute_backup(root=stage_bad, destination=stage_parent, execute=True, confirmed_plan_digest=plan.data["plan"]["plan_digest"])
        self.assertEqual(code, 3)
        self.assertIn("incomplete_bundle", env.data)
        self.assertFalse(os.path.exists(os.path.join(stage_parent, "portable-kb")))

    def test_checksum_and_manifest_tampering(self):
        fixture = new_fixture(self.temp, "checksum-coverage")
        parent = os.path.join(self.temp, "coverage parent")
        _, plan = execute_backup(root=fixture.root, destination=parent, execute=False)
        execute_backup(root=fixture.root, destination=parent, execute=True, confirmed_plan_digest=plan.data["plan"]["plan_digest"])
        bundle = os.path.join(parent, "portable-kb")

        # 1. Uncovered file
        write_file(os.path.join(bundle, "uncovered.txt"), "not checksummed")
        c_code, _ = verify_backup(bundle)
        self.assertEqual(c_code, 2)
        os.remove(os.path.join(bundle, "uncovered.txt"))

        # 2. Duplicate checksum
        checksum_path = os.path.join(bundle, "CHECKSUMS.sha256")
        with open(checksum_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        with open(checksum_path, "a", encoding="utf-8") as f:
            f.write(lines[0])
        d_code, _ = verify_backup(bundle)
        self.assertEqual(d_code, 2)
        with open(checksum_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # 3. Ghost checksum
        with open(checksum_path, "a", encoding="utf-8") as f:
            f.write(("0" * 64) + "  ghost.txt\n")
        g_code, _ = verify_backup(bundle)
        self.assertEqual(g_code, 2)
        with open(checksum_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # 4. Reference mismatch
        manifest_file = os.path.join(bundle, "backup-manifest.json")
        with open(manifest_file, "r", encoding="utf-8") as f:
            man = json.load(f)
        man["references"][0]["portable_path"] = "external/projects/demo-project/missing.txt"
        with open(manifest_file, "w", encoding="utf-8") as f:
            json.dump(man, f, indent=2)
        update_bundle_checksums(bundle)
        ref_code, _ = verify_backup(bundle)
        self.assertEqual(ref_code, 2)

    def test_cli_end_to_end_json_envelope(self):
        fixture = new_fixture(self.temp, "cli-e2e")
        parent = os.path.join(self.temp, "cli-backup")
        kb_script = str(SCRIPTS_DIR / "kb.py")

        # 1. Plan via CLI
        cmd_plan = [
            sys.executable,
            "-X",
            "utf8",
            kb_script,
            "--format",
            "json",
            "backup",
            "--root",
            fixture.root,
            "--destination",
            parent,
        ]
        res_plan = subprocess.run(cmd_plan, capture_output=True, text=True, check=True)
        data_plan = json.loads(res_plan.stdout)
        self.assertEqual(data_plan["command"], "backup")
        self.assertEqual(data_plan["status"], "plan")
        digest = data_plan["data"]["plan"]["plan_digest"]

        # 2. Execute via CLI
        cmd_exec = [
            sys.executable,
            "-X",
            "utf8",
            kb_script,
            "--format",
            "json",
            "backup",
            "--root",
            fixture.root,
            "--destination",
            parent,
            "--execute",
            "--confirmed-plan-digest",
            digest,
        ]
        res_exec = subprocess.run(cmd_exec, capture_output=True, text=True, check=True)
        data_exec = json.loads(res_exec.stdout)
        self.assertEqual(data_exec["status"], "created")

        bundle = os.path.join(parent, "portable-kb")
        self.assertTrue(os.path.isdir(bundle))

        # 3. Verify via CLI
        cmd_ver = [
            sys.executable,
            "-X",
            "utf8",
            kb_script,
            "--format",
            "json",
            "verify-backup",
            "--bundle",
            bundle,
        ]
        res_ver = subprocess.run(cmd_ver, capture_output=True, text=True, check=True)
        data_ver = json.loads(res_ver.stdout)
        self.assertEqual(data_ver["status"], "valid")

        # 4. Restore via CLI
        rest_dest = os.path.join(self.temp, "cli-restored")
        cmd_rest = [
            sys.executable,
            "-X",
            "utf8",
            kb_script,
            "--format",
            "json",
            "restore",
            "--bundle",
            bundle,
            "--destination",
            rest_dest,
            "--execute",
        ]
        res_rest = subprocess.run(cmd_rest, capture_output=True, text=True, check=True)
        data_rest = json.loads(res_rest.stdout)
        self.assertEqual(data_rest["status"], "restored")
        self.assertTrue(os.path.isdir(rest_dest))

    def test_fenced_code_external_source_declaration_ignored(self) -> None:
        """Verify external source declaration inside fenced code block is not registered as external file."""
        fx = new_fixture(self.temp, "fenced-code-test")
        os.remove(os.path.join(fx.root, "content", "knowledge", "来源 note.md"))
        decl = (
            f"- [source]({fx.source.replace(os.sep, '/')}); Project: fixture; project-id: demo-project; "
            f"project-relative source: 资料/证据 文件.txt; verified: 2026-09-21; version-state: unversioned <!-- kb-external-local -->"
        )
        idx_path = os.path.join(fx.root, "content", "index.md")
        write_file(idx_path, f"# Home\n```markdown\n{decl}\n```\n")

        dest = os.path.join(self.temp, "backup-fenced")
        code, env = execute_backup(fx.root, dest)
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "plan")
        self.assertEqual(env.data["plan"]["totals"]["external_files"], 0)

    def test_posix_unregistered_absolute_path_blocked(self) -> None:
        """Verify that POSIX absolute paths starting with / are recognized as absolute and blocked when unregistered."""
        fx = new_fixture(self.temp, "posix-unregistered-test")
        idx_path = os.path.join(fx.root, "content", "index.md")
        write_file(idx_path, "# Home\n[unregistered](/tmp/unregistered-source.md)\n")

        dest = os.path.join(self.temp, "backup-posix")
        code, env = execute_backup(fx.root, dest)
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")
        self.assertIn("BLOCKER: legacy absolute local link at index.md:2 -> /tmp/unregistered-source.md", env.data["message"])

    def test_inline_code_span_absolute_path_blocked(self) -> None:
        """Verify that unregistered absolute path inside an inline code span blocks backup."""
        fx = new_fixture(self.temp, "code-span-blocked-test")
        idx_path = os.path.join(fx.root, "content", "index.md")
        write_file(idx_path, "# Home\nSee code span `/tmp/unregistered-span.md` here.\n")

        dest = os.path.join(self.temp, "backup-codespan")
        code, env = execute_backup(fx.root, dest)
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")
        self.assertIn("BLOCKER: legacy absolute local path in code span", env.data["message"])

    def test_inline_code_span_valid_fields_accepted(self) -> None:
        """Verify that inline code spans containing valid metadata fields are accepted without blocking."""
        fx = new_fixture(self.temp, "code-span-valid-test")
        os.remove(os.path.join(fx.root, "content", "knowledge", "来源 note.md"))
        decl = (
            f"- Project: `fixture`; project-id: `demo-project`; project-relative source: `资料/证据 文件.txt`; "
            f"[source]({fx.source.replace(os.sep, '/')}); `verified: 2026-09-21`; `version-state: unversioned` <!-- kb-external-local -->"
        )
        idx_path = os.path.join(fx.root, "content", "index.md")
        write_file(idx_path, f"# Home\n{decl}\n")

        dest = os.path.join(self.temp, "backup-codespan-valid")
        code, env = execute_backup(fx.root, dest)
        self.assertEqual(code, 0)
        self.assertEqual(env.status, "plan")
        self.assertEqual(env.data["plan"]["totals"]["external_files"], 1)

    def test_default_text_plan_source_path_visible(self) -> None:
        """Verify that default text output of backup plan displays all source files."""
        fx = new_fixture(self.temp, "text-plan-visible-test")
        from kb_core.cli import format_text_output
        dest = os.path.join(self.temp, "backup-text-visible")
        code, env = execute_backup(fx.root, dest)
        self.assertEqual(code, 0)
        rendered = format_text_output(env)
        self.assertIn("Source files:", rendered)
        self.assertIn(fx.source, rendered)

    def test_fail_if_exists_publish_refusal(self) -> None:
        """Verify that publish_dir_fail_if_exists refuses to overwrite existing destination."""
        from kb_core.backup import publish_dir_fail_if_exists
        src = os.path.join(self.temp, "pub-src")
        dst = os.path.join(self.temp, "pub-dst")
        os.makedirs(src, exist_ok=True)
        os.makedirs(dst, exist_ok=True)
        with self.assertRaises(FileExistsError):
            publish_dir_fail_if_exists(src, dst)

    def test_inline_code_marker_does_not_register_external_source(self) -> None:
        fx = new_fixture(self.temp, "inline-code-marker")
        index = os.path.join(fx.root, "content", "index.md")
        declaration = (
            f"[source]({fx.source.replace(os.sep, '/')}); Project: fixture; project-id: demo-project; "
            "project-relative source: 资料/证据 文件.txt; verified: 2026-09-21; "
            "version-state: unversioned; `<!-- kb-external-local -->`"
        )
        write_file(index, f"# Home\n{declaration}\n")
        code, env = execute_backup(fx.root, os.path.join(self.temp, "marker-plan"))
        self.assertEqual(code, 2)
        self.assertEqual(env.status, "blocked")
        self.assertIn("legacy absolute local link", env.data["message"])

    def test_angle_bracket_parenthesized_target_rewrites_and_restores(self) -> None:
        fx = new_fixture(self.temp, "parenthesized-target")
        special = os.path.join(os.path.dirname(fx.source), "evidence(note).txt")
        write_file(special, "parenthesized external evidence")
        index = os.path.join(fx.root, "content", "index.md")
        target = special.replace(os.sep, "/")
        write_file(
            index,
            "# Home\n"
            f"[source](<{target}>); Project: fixture; project-id: demo-project; "
            "project-relative source: 资料/evidence(note).txt; verified: 2026-09-21; "
            "version-state: unversioned <!-- kb-external-local -->\n",
        )
        destination = os.path.join(self.temp, "parenthesized-backup")
        code, env = execute_backup(fx.root, destination)
        self.assertEqual((code, env.status), (0, "plan"))
        digest = env.data["plan"]["plan_digest"]
        code, env = execute_backup(fx.root, destination, execute=True, confirmed_plan_digest=digest)
        self.assertEqual((code, env.status), (0, "created"))
        bundle = os.path.join(destination, "portable-kb")
        self.assertEqual(verify_backup(bundle)[0], 0)
        restored = os.path.join(self.temp, "parenthesized-restored")
        self.assertEqual(restore_backup(bundle, restored, execute=True)[0], 0)

    def test_plan_v2_protocol_is_stable_and_rejects_prior_digest(self) -> None:
        fx = new_fixture(self.temp, "plan-v2")
        for name in ["a-b.md", "ab.md", "a_b.md", "é.md", "中文.md", "😀.md", "Z.md"]:
            write_file(os.path.join(fx.root, "content", name), "# fixture\n")
        destination = os.path.join(self.temp, "plan-v2-backup")
        first = get_backup_plan(fx.root, destination)
        second = get_backup_plan(fx.root, destination)
        self.assertEqual(first["plan_schema_version"], 2)
        self.assertEqual(first["plan_digest"], second["plan_digest"])
        for kind in ("content", "external"):
            paths = [record["portable_path"] for record in first["files"] if record["kind"] == kind]
            self.assertEqual(paths, sorted(paths, key=lambda value: tuple(ord(char) for char in value)))
        prior_protocol = dict(first)
        prior_protocol.pop("plan_digest")
        prior_protocol.pop("plan_schema_version")
        old_digest = __import__("hashlib").sha256(
            json.dumps(prior_protocol, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        code, env = execute_backup(fx.root, destination, execute=True, confirmed_plan_digest=old_digest)
        self.assertEqual((code, env.status), (2, "reconfirm_required"))
        self.assertFalse(os.path.exists(destination))

    def test_plan_digest_rejects_unknown_plan_schema(self) -> None:
        with self.assertRaises(ValueError):
            get_plan_digest({"plan_schema_version": 999})

    def test_native_publish_unavailable_fails_closed(self) -> None:
        from kb_core import backup

        with (
            patch.object(backup.os, "name", "posix"),
            patch.object(backup.sys, "platform", "linux"),
            patch.object(backup, "_linux_rename_noreplace", return_value=False),
            patch.object(backup.os, "rename") as ordinary_rename,
        ):
            with self.assertRaisesRegex(RuntimeError, "non-atomic publish"):
                backup.publish_dir_fail_if_exists(
                    os.path.join(self.temp, "unpublished-src"),
                    os.path.join(self.temp, "unpublished-dst"),
                )
        ordinary_rename.assert_not_called()

    @unittest.skipIf(sys.platform == "win32", "Symlink creation requires a Windows privilege")
    def test_symlink_rejections(self) -> None:
        """Backup and verification reject both live and broken symlinks on POSIX."""
        fx = new_fixture(self.temp, "symlink-rejections")
        live_link = os.path.join(fx.root, "content", "linked-source.md")
        os.symlink(fx.source, live_link)
        code, env = execute_backup(fx.root, os.path.join(self.temp, "symlink-source-backup"))
        self.assertEqual((code, env.status), (2, "blocked"))
        self.assertRegex(env.data["message"], r"symbolic link|reparse")
        os.unlink(live_link)

        broken_link = os.path.join(fx.root, "content", "broken-source.md")
        os.symlink(os.path.join(self.temp, "missing-target.md"), broken_link)
        code, env = execute_backup(fx.root, os.path.join(self.temp, "broken-symlink-backup"))
        self.assertEqual((code, env.status), (2, "blocked"))
        self.assertRegex(env.data["message"], r"symbolic link|reparse")
        os.unlink(broken_link)

        destination = os.path.join(self.temp, "valid-symlink-bundle")
        _, plan = execute_backup(fx.root, destination)
        self.assertEqual(
            execute_backup(
                fx.root,
                destination,
                execute=True,
                confirmed_plan_digest=plan.data["plan"]["plan_digest"],
            )[0],
            0,
        )
        bundle = os.path.join(destination, "portable-kb")
        os.symlink(fx.source, os.path.join(bundle, "linked-bundle-source.md"))
        code, env = verify_backup(bundle)
        self.assertEqual((code, env.status), (3, "fatal"))
        self.assertRegex(env.data["issues"][0], r"symbolic link|reparse")

    @unittest.skipUnless(sys.platform == "win32", "Win32 reparse API failure injection requires Windows")
    def test_win32_reparse_probe_failures_block_backup_paths(self) -> None:
        """A failed Win32 safety probe is an error, never an implicit safe result."""
        from kb_core import paths

        target = os.path.join(self.temp, "reparse-probe-target")
        os.makedirs(target)
        with patch.object(paths.kernel32, "GetFileAttributesW", return_value=0xFFFFFFFF):
            with self.assertRaises(OSError):
                paths.is_redirecting_reparse_point(target)

        with patch.object(
            paths.kernel32,
            "GetFileAttributesW",
            return_value=paths.FILE_ATTRIBUTE_REPARSE_POINT,
        ), patch.object(paths, "CreateFileW", return_value=paths.INVALID_HANDLE_VALUE):
            with self.assertRaises(OSError):
                paths.is_redirecting_reparse_point(target)

        with patch.object(
            paths.kernel32,
            "GetFileAttributesW",
            return_value=paths.FILE_ATTRIBUTE_REPARSE_POINT,
        ), patch.object(paths, "CreateFileW", return_value=123), patch.object(
            paths, "GetFileInformationByHandleEx", return_value=False
        ), patch.object(paths, "CloseHandle"):
            with self.assertRaises(OSError):
                paths.is_redirecting_reparse_point(target)

    def test_known_dependency_error_has_actionable_no_write_envelope(self) -> None:
        from kb_core.cli import dependency_missing_envelope

        missing = ImportError("No module named 'markdown_it'")
        missing.name = "markdown_it"
        envelope = dependency_missing_envelope("backup", os.path.join(self.temp, "kb"), missing)
        self.assertIsNotNone(envelope)
        assert envelope is not None
        self.assertEqual(envelope.diagnostics[0].code, "DEPENDENCY_MISSING")
        self.assertEqual(envelope.diagnostics[0].target, "markdown-it-py")
        self.assertIn(sys.executable, envelope.diagnostics[0].message)
        unknown = ImportError("broken internal import")
        unknown.name = "kb_core.internal_bug"
        self.assertIsNone(dependency_missing_envelope("backup", None, unknown))


if __name__ == "__main__":
    unittest.main()
