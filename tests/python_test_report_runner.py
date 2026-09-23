"""Execute one unittest script and emit its exact outcome for run-all-tests.py."""
from __future__ import annotations
import json
import runpy
import sys
import unittest
from pathlib import Path

PREFIX = "KB_PYTHON_TEST_REPORT "


def _iter_cases(suite: unittest.TestSuite):
    for item in suite:
        if isinstance(item, unittest.TestSuite): yield from _iter_cases(item)
        elif isinstance(item, unittest.TestCase): yield item


def main() -> int:
    if len(sys.argv) != 2: return 2
    suite_path = Path(sys.argv[1]).resolve(); original_run = unittest.TextTestRunner.run
    successful: list[str] = []
    original_add_success = unittest.TextTestResult.addSuccess
    def recording_add_success(self: unittest.TextTestResult, test: unittest.TestCase) -> None:
        original_add_success(self, test)
        successful.append(test.id())
    unittest.TextTestResult.addSuccess = recording_add_success  # type: ignore[method-assign]
    def reporting_run(self: unittest.TextTestRunner, test: unittest.TestSuite) -> unittest.TestResult:
        result = original_run(self, test); skipped = [case.id() for case, _ in result.skipped]
        print(PREFIX + json.dumps({"suite": suite_path.name, "tests_run": result.testsRun, "failures": len(result.failures), "errors": len(result.errors), "unexpected_successes": len(result.unexpectedSuccesses), "skipped": skipped, "successful": successful}, sort_keys=True))
        return result
    unittest.TextTestRunner.run = reporting_run  # type: ignore[method-assign]
    old_argv = sys.argv
    sys.argv = [str(suite_path)]
    try: runpy.run_path(str(suite_path), run_name="__main__")
    except SystemExit as error: return error.code if isinstance(error.code, int) else (0 if error.code is None else 1)
    finally: sys.argv = old_argv
    return 0


if __name__ == "__main__": sys.exit(main())
