"""Regression tests for the strict full-test runner, using only disposable fixtures."""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import unittest
import importlib.util
import json
from pathlib import Path

TESTS = Path(__file__).resolve().parent


class TestStrictRunner(unittest.TestCase):
    def setUp(self) -> None:
        self.root = Path(tempfile.mkdtemp(prefix="kb-runner-gate-"))
        self.tests = self.root / "tests"; self.tests.mkdir()
        shutil.copy2(TESTS / "run-all-tests.py", self.tests / "run-all-tests.py")
        shutil.copy2(TESTS / "python_test_report_runner.py", self.tests / "python_test_report_runner.py")
        shutil.copy2(TESTS / "node_test_report.cjs", self.tests / "node_test_report.cjs")
        (self.root / "knowledge-base-manager").mkdir()
        (self.root / ".github" / "workflows").mkdir(parents=True)
        for suite in ["test-kb-python-parser.py", "test-kb-python-query.py", "test-kb-python-audit.py", "test-kb-python-workflow.py", "test-kb-python-static.py", "test-kb-python-vendor.py", "test-kb-python-runner.py"]:
            (self.tests / suite).write_text("import unittest\nclass T(unittest.TestCase):\n def test_ok(self): self.assertTrue(True)\nif __name__ == '__main__': unittest.main()\n", encoding="utf-8")
        (self.tests / "test-kb-python-backup.py").write_text(
            "import sys, unittest\n"
            "class TestKbBackup(unittest.TestCase):\n"
            " @unittest.skipUnless(sys.platform == 'win32', 'Windows-only junction fixture')\n"
            " def test_junction_rejections(self): self.assertTrue(True)\n"
            " @unittest.skipUnless(sys.platform != 'win32', 'Symlink fixture is required on non-Windows')\n"
            " def test_symlink_rejections(self): self.assertTrue(True)\n"
            " @unittest.skipUnless(sys.platform == 'win32', 'Windows-only reparse fixture')\n"
            " def test_win32_reparse_probe_failures_block_backup_paths(self): self.assertTrue(True)\n"
            "if __name__ == '__main__': unittest.main()\n",
            encoding="utf-8",
        )
        for suite in ["test-kb-static-copy.cjs", "test-kb-static-toc.cjs", "test-kb-static-graph-component.cjs"]:
            (self.tests / suite).write_text("const {instrument,emitComplete}=require('./node_test_report.cjs'); const assert=instrument(require('node:assert/strict')); assert.ok(true); emitComplete({suite:require('node:path').basename(__filename),assert});\n", encoding="utf-8")

    def tearDown(self) -> None:
        shutil.rmtree(self.root, ignore_errors=True)

    def _run(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run([sys.executable, "-B", "-X", "utf8", str(self.tests / "run-all-tests.py")], cwd=self.root, text=True, capture_output=True, encoding="utf-8")

    def test_valid_fixture_passes(self) -> None:
        result = self._run()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_critical_skip_fails(self) -> None:
        (self.tests / "test-kb-python-parser.py").write_text("import unittest\nclass T(unittest.TestCase):\n @unittest.skip('safety unavailable')\n def test_required(self): pass\n def test_smoke(self): self.assertTrue(True)\nif __name__ == '__main__': unittest.main()\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("required test skipped", result.stdout)

    def test_zero_python_tests_fails(self) -> None:
        (self.tests / "test-kb-python-query.py").write_text("import unittest\nif __name__ == '__main__': unittest.main()\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("zero tests executed", result.stdout)

    def test_zero_node_assertions_fails(self) -> None:
        (self.tests / "test-kb-static-copy.cjs").write_text("const {emitComplete}=require('./node_test_report.cjs'); emitComplete({suite:require('node:path').basename(__filename)});\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("zero assertions", result.stdout)

    def test_active_powershell_and_yaml_comment_boundary(self) -> None:
        (self.root / "knowledge-base-manager" / "obsolete.ps1").write_text("Write-Host x", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active PowerShell file", result.stdout)
        (self.root / "knowledge-base-manager" / "obsolete.ps1").unlink()
        workflow = self.root / ".github" / "workflows" / "check.yaml"
        workflow.write_text("jobs:\n  check:\n    steps:\n      - run: |\n          # historical pwsh mention only\n          echo safe\n", encoding="utf-8")
        self.assertEqual(self._run().returncode, 0)
        workflow.write_text("jobs:\n  check:\n    steps:\n      - run: pwsh ./legacy.ps1\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("workflow invocation", result.stdout)

    def test_active_python_invocation_and_unreadable_workflow_fail_closed(self) -> None:
        (self.root / "knowledge-base-manager" / "invoke.py").write_text("import subprocess\nsubprocess.run(['pwsh', '-File', 'legacy.ps1'])\n", encoding="utf-8")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("active PowerShell invocation", result.stdout)
        (self.root / "knowledge-base-manager" / "invoke.py").unlink()
        (self.root / ".github" / "workflows" / "invalid.yml").write_bytes(b"\xff")
        result = self._run()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot inspect workflow", result.stdout)

    def test_nonwindows_skip_allowlist_is_exact_and_keeps_symlink_required(self) -> None:
        spec = importlib.util.spec_from_file_location("runner_under_test", TESTS / "run-all-tests.py")
        assert spec and spec.loader
        runner = importlib.util.module_from_spec(spec); spec.loader.exec_module(runner)
        old_platform = runner.sys.platform; runner.sys.platform = "linux"
        try:
            def report(skipped: list[str], successful: list[str]) -> str:
                return runner.PYTHON_REPORT_PREFIX + json.dumps({"suite": "test-kb-python-backup.py", "tests_run": 3, "failures": 0, "errors": 0, "unexpected_successes": 0, "skipped": skipped, "successful": successful})
            allowed = ["__main__.TestKbBackup.test_junction_rejections", "__main__.TestKbBackup.test_win32_reparse_probe_failures_block_backup_paths"]
            self.assertEqual(runner._validate_python("test-kb-python-backup.py", 0, report(allowed, ["__main__.TestKbBackup.test_symlink_rejections"])), "")
            self.assertIn("required test skipped", runner._validate_python("test-kb-python-backup.py", 0, report(["__main__.TestKbBackup.test_safety"], ["__main__.TestKbBackup.test_symlink_rejections"])))
            self.assertIn("missing required platform substitute", runner._validate_python("test-kb-python-backup.py", 0, report(allowed, [])))
        finally:
            runner.sys.platform = old_platform


if __name__ == "__main__":
    unittest.main()
