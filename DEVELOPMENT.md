# Python development environment

Python (with PyYAML and markdown-it-py) powers the entire knowledge-base management CLI toolset (`kb.py`: resolve, inspect, search, read, audit, build-static, backup, verify-backup, restore). All legacy PowerShell scripts have been completely replaced with cross-platform Python. This environment provides the shared Python environment for developing and validating both the Python core and the Skill.

## Create the environment

Run from the repository root. Choose an installed, user-managed Python explicitly;
the locally verified baseline is CPython 3.14.7 (Windows x64). Do not install this
project's dependencies into the Codex-managed runtime or system site-packages.

```powershell
# Replace with your installed Python's absolute path before running.
$projectBasePython = 'C:\path\to\python.exe'
& $projectBasePython -X utf8 -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
& '.\.venv\Scripts\python.exe' -X utf8 -m pip --isolated install --index-url https://pypi.org/simple -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed.' }
```

Create only when `.venv` is absent; inspect an existing environment before changing
it. Keep the default isolation (no `--system-site-packages`). Do not copy packages
between Python versions or inject another interpreter's site-packages through
`PYTHONPATH`. `.venv/` is Git-ignored, disposable and not portable; recreate it on
another machine from the chosen Python and `requirements-dev.txt`.

## Shared Codex / Gemini convention

- Run Python checks from the repository root using
  `.venv\Scripts\python.exe -X utf8`. From another directory, use absolute paths
  for both the interpreter and inputs. Activation is optional and never relied on.
- Do not silently fall back to `python`, `py`, system Python or Codex's bundled
  Python. If the environment is absent, inaccessible or incompatible, report the
  interpreter path and actual error before taking a recovery action.
- Declare new development dependencies in `requirements-dev.txt`; a dependency
  installation does not authorize a change to Skill runtime requirements.
- Handoff and acceptance evidence must identify the Python executable/version,
  relevant dependency versions, exact check, result and permission context.
- Use `-X utf8` because Windows' default output encoding can reject Chinese paths.

## Verify

```powershell
& '.\.venv\Scripts\python.exe' -X utf8 -c 'import sys, yaml; print(sys.executable); print(sys.version); print(yaml.__version__); print(yaml.__file__); assert sys.prefix != sys.base_prefix'
if ($LASTEXITCODE -ne 0) { throw 'Environment check failed.' }
& '.\.venv\Scripts\python.exe' -X utf8 -m pip check
if ($LASTEXITCODE -ne 0) { throw 'Dependency check failed.' }

# Verify bundled vendor dependencies integrity
& '.\.venv\Scripts\python.exe' -X utf8 tools/vendor_dependencies.py --check
if ($LASTEXITCODE -ne 0) { throw 'Vendor integrity check failed.' }

# Locate the installed skill-creator's existing validator on this machine.
# Replace the placeholder; the validator is not bundled with this repository.
$skillValidator = 'C:\path\to\skill-creator\scripts\quick_validate.py'
& '.\.venv\Scripts\python.exe' -X utf8 $skillValidator '.\knowledge-base-manager'
if ($LASTEXITCODE -ne 0) { throw 'Skill structural validation failed.' }

# Run all test suites
& '.\.venv\Scripts\python.exe' -X utf8 tests/run-all-tests.py

# Or run individual Python core test suites
$projectPython = (Resolve-Path '.\.venv\Scripts\python.exe').Path
& $projectPython -B -X utf8 tests/test-kb-python-parser.py
& $projectPython -B -X utf8 tests/test-kb-python-query.py
& $projectPython -B -X utf8 tests/test-kb-python-audit.py
& $projectPython -B -X utf8 tests/test-kb-python-workflow.py
& $projectPython -B -X utf8 tests/test-kb-python-backup.py
& $projectPython -B -X utf8 tests/test-kb-python-static.py
& $projectPython -B -X utf8 tests/test-kb-python-vendor.py
```

The validator requires an installed `skill-creator`; it is an external development
tool, not a runtime dependency. If unavailable, report that limitation and perform
the equivalent manual structural checks. Do not report manual checks as a passed
validator run. Structural validation does not replace relevant behavior tests.

## Bundled Vendor Dependencies

Pure-Python runtime dependencies (`PyYAML 6.0.3`, `markdown-it-py 4.2.0`, `mdit-py-plugins 0.6.1`, `mdurl 0.1.2`) are bundled under `knowledge-base-manager/vendor/` with deterministic `manifest.json` and `THIRD_PARTY.md`. End users do not require virtual environments or `pip install` at runtime.

Vendor maintenance uses standard library only via `tools/vendor_dependencies.py`:
- `python -X utf8 tools/vendor_dependencies.py --check`: Read-only offline verification of vendor files and manifest SHA-256 digests.
- `python -X utf8 tools/vendor_dependencies.py --rebuild`: Deterministic offline clean extraction and manifest generation from cached wheels/sdist.
- `python -X utf8 tools/vendor_dependencies.py --refresh`: Offline check followed by rebuild if needed.
- `python -X utf8 tools/vendor_dependencies.py --fetch`: Download pinned packages from PyPI to local cache (maintainer-only).

## Windows sandbox boundary

A virtual environment still depends on its base Python. On the verified local
Codex setup, the default sandbox cannot start this system-Python-backed `.venv`;
the environment and validator passed using approved execution outside that
sandbox. This is not a persistent sandbox permission fix.

When denied, use the harness's supported per-command approval mechanism within
the task's authorization, and record that execution context. Do not silently
switch interpreters, change global PATH/ACLs or disable sandbox protection.
Gemini must verify access from its own execution context; Codex's successful run
does not establish Gemini's permissions.
