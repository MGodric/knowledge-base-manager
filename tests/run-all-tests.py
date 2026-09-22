"""Strict unified test runner for the Python-only Knowledge Base Manager runtime."""
from __future__ import annotations

import ast
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

TESTS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = TESTS_DIR.parent
PYTHON_REPORT_RUNNER = TESTS_DIR / "python_test_report_runner.py"
PYTHON_REPORT_PREFIX = "KB_PYTHON_TEST_REPORT "
NODE_REPORT_PREFIX = "KB_NODE_TEST_REPORT "
PYTHON_SUITES = ["test-kb-python-parser.py", "test-kb-python-query.py", "test-kb-python-audit.py", "test-kb-python-workflow.py", "test-kb-python-backup.py", "test-kb-python-static.py", "test-kb-python-vendor.py", "test-kb-python-runner.py"]
NODE_SUITES = ["test-kb-static-copy.cjs", "test-kb-static-toc.cjs", "test-kb-static-graph-component.cjs"]
WINDOWS_ALLOWED_SKIPS = {"test-kb-python-backup.py": {"__main__.TestKbBackup.test_symlink_rejections"}}
NONWINDOWS_ALLOWED_SKIPS = {"test-kb-python-backup.py": {
    "__main__.TestKbBackup.test_junction_rejections",
    "__main__.TestKbBackup.test_win32_reparse_probe_failures_block_backup_paths",
}}
REQUIRED_NONWINDOWS_TESTS = {"test-kb-python-backup.py": {"__main__.TestKbBackup.test_symlink_rejections"}}


def _extract_json_report(output: str, prefix: str) -> tuple[dict[str, Any] | None, str]:
    reports: list[dict[str, Any]] = []
    for line in output.splitlines():
        if line.startswith(prefix):
            try:
                report = json.loads(line[len(prefix):])
            except json.JSONDecodeError as error:
                return None, f"malformed structured report: {error.msg}"
            if not isinstance(report, dict):
                return None, "structured report is not an object"
            reports.append(report)
    return (reports[0], "") if len(reports) == 1 else (None, f"expected exactly one structured report, found {len(reports)}")


def _command_mentions_powershell(tree: ast.AST) -> bool:
    command_functions = {"run", "Popen", "call", "check_call", "check_output", "system", "spawn", "exec", "execFile"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        if name not in command_functions or not node.args:
            continue
        for literal in ast.walk(node.args[0]):
            if isinstance(literal, ast.Constant) and isinstance(literal.value, str):
                command = literal.value.lower()
                if re.search(r"(^|[\\/\s])(?:pwsh|powershell)(?:\.exe)?($|[\\/\s])", command) or ".ps1" in command:
                    return True
    return False


def _javascript_mentions_powershell(source: str) -> bool:
    """Inspect command-launch calls only; ordinary comments and prose do not count."""
    active = re.sub(r"/\*[\s\S]*?\*/|^\s*//.*$", "", source, flags=re.M)
    for call in re.findall(r"\b(?:spawn|exec|execFile|spawnSync|execSync)\s*\(([^)]*)\)", active, re.S):
        if re.search(r"\b(?:pwsh|powershell)(?:\.exe)?\b|\S+\.ps1\b", call, re.I):
            return True
    return False


def _yaml_execution_mentions_powershell(value: Any) -> bool:
    if isinstance(value, dict):
        for key, item in value.items():
            if str(key).lower() in {"run", "shell", "command"} and isinstance(item, str):
                active = "\n".join(line for line in item.splitlines() if not line.lstrip().startswith("#"))
                if re.search(r"\b(?:pwsh|powershell)(?:\.exe)?\b|\S+\.ps1\b", active, re.I):
                    return True
            if _yaml_execution_mentions_powershell(item):
                return True
    return any(_yaml_execution_mentions_powershell(item) for item in value) if isinstance(value, list) else False


def check_no_active_powershell_files() -> tuple[bool, list[str]]:
    """Reject active PowerShell files and executable invocation edges; read errors fail closed."""
    findings: list[str] = []
    for root in (PROJECT_ROOT / "knowledge-base-manager", TESTS_DIR):
        if not root.exists():
            continue
        for item in root.rglob("*"):
            try:
                if not item.is_file():
                    continue
                relative = item.relative_to(PROJECT_ROOT)
                if item.suffix.lower() == ".ps1":
                    findings.append(f"{relative} (active PowerShell file)")
                elif item.suffix.lower() in {".py", ".js", ".cjs", ".mjs"}:
                    source = item.read_text(encoding="utf-8")
                    if (item.suffix.lower() == ".py" and _command_mentions_powershell(ast.parse(source, filename=str(item)))) or (item.suffix.lower() != ".py" and _javascript_mentions_powershell(source)):
                        findings.append(f"{relative} (active PowerShell invocation)")
            except Exception as error:
                findings.append(f"{item} (cannot inspect active source: {error})")
    workflows = PROJECT_ROOT / ".github" / "workflows"
    if workflows.exists():
        try:
            import yaml
        except Exception as error:
            findings.append(f"workflow YAML parser unavailable: {error}")
        else:
            for item in workflows.rglob("*"):
                if not item.is_file() or item.suffix.lower() not in {".yaml", ".yml"}:
                    continue
                try:
                    if _yaml_execution_mentions_powershell(yaml.safe_load(item.read_text(encoding="utf-8"))):
                        findings.append(f"{item.relative_to(PROJECT_ROOT)} (active PowerShell workflow invocation)")
                except Exception as error:
                    findings.append(f"{item.relative_to(PROJECT_ROOT)} (cannot inspect workflow: {error})")
    return not findings, findings


def run_command(command: list[str], cwd: Path) -> tuple[int, str, float]:
    start = time.perf_counter()
    env = os.environ.copy(); env["PYTHONUNBUFFERED"] = "1"
    proc = subprocess.run(command, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", env=env)
    return proc.returncode, proc.stdout, time.perf_counter() - start


def _validate_python(suite: str, code: int, output: str) -> str:
    report, reason = _extract_json_report(output, PYTHON_REPORT_PREFIX)
    if reason: return f"exit code {code}" if code != 0 else reason
    assert report is not None
    if report.get("suite") != suite: return "report suite identity mismatch"
    if not isinstance(report.get("tests_run"), int) or report["tests_run"] <= 0: return "zero tests executed"
    if any(report.get(key, 0) for key in ("failures", "errors", "unexpected_successes")): return "report contains failures, errors, or unexpected successes"
    if code != 0: return f"exit code {code}"
    skipped = report.get("skipped")
    if not isinstance(skipped, list): return "report skipped field is invalid"
    allowed = (WINDOWS_ALLOWED_SKIPS if sys.platform == "win32" else NONWINDOWS_ALLOWED_SKIPS).get(suite, set())
    unexpected = [item for item in skipped if item not in allowed]
    if unexpected: return f"required test skipped: {', '.join(unexpected)}"
    required = REQUIRED_NONWINDOWS_TESTS.get(suite, set()) if sys.platform != "win32" else set()
    completed = set(report.get("successful", []))
    missing = required - completed
    return f"missing required platform substitute: {', '.join(sorted(missing))}" if missing else ""


def _validate_node(suite: str, code: int, output: str) -> str:
    if code != 0: return f"exit code {code}"
    report, reason = _extract_json_report(output, NODE_REPORT_PREFIX)
    if reason: return reason
    assert report is not None
    if report.get("suite") != suite or report.get("status") != "passed": return "invalid Node report identity or status"
    if not isinstance(report.get("assertions"), int) or report["assertions"] <= 0: return "Node suite made zero assertions"
    return ""


def _record(results: list[tuple[str, bool, float, str, str]], suite: str, command: list[str], validator: Any) -> None:
    code, output, elapsed = run_command(command, PROJECT_ROOT); reason = validator(suite, code, output)
    results.append((suite, not reason, elapsed, reason, output))


def main() -> int:
    print("=" * 64); print("Knowledge Base Manager - Strict Full Test Runner")
    node = shutil.which("node"); print(f"Python: {sys.executable}\nNode:   {node or 'NOT FOUND'}\nRoot:   {PROJECT_ROOT}")
    results: list[tuple[str, bool, float, str, str]] = []
    if not PYTHON_REPORT_RUNNER.is_file(): results.append((PYTHON_REPORT_RUNNER.name, False, 0, "missing required Python report runner", ""))
    for suite in PYTHON_SUITES:
        path = TESTS_DIR / suite
        if not path.is_file(): results.append((suite, False, 0, "missing required test suite", ""))
        elif PYTHON_REPORT_RUNNER.is_file(): _record(results, suite, [sys.executable, "-B", "-X", "utf8", str(PYTHON_REPORT_RUNNER), str(path)], _validate_python)
    for suite in NODE_SUITES:
        path = TESTS_DIR / suite
        if not node: results.append((suite, False, 0, "Node.js executable not found", ""))
        elif not path.is_file(): results.append((suite, False, 0, "missing required test suite", ""))
        else: _record(results, suite, [node, str(path)], _validate_node)
    no_ps, findings = check_no_active_powershell_files()
    results.append(("active PowerShell dependency gate", no_ps, 0, "; ".join(findings), ""))
    for name, passed, elapsed, reason, _ in results: print(f"[{'PASS' if passed else 'FAIL'}] {name:<42} ({elapsed:6.2f}s){'' if passed else f' ({reason})'}")
    failures = [result for result in results if not result[1]]
    print(f"\nSummary: {len(results) - len(failures)}/{len(results)} gates passed, {len(failures)} failed.")
    if failures:
        for name, _, _, _, output in failures:
            if output: print(f"\n--- {name} output ---\n{output.strip()}")
        return 1
    return 0


if __name__ == "__main__": sys.exit(main())
