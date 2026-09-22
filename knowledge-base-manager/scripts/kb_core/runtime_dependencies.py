"""Runtime dependency loader and integrity validation for bundled vendor packages.

Standard library only. Ensures pure-Python dependencies (PyYAML, markdown-it-py,
mdit-py-plugins, mdurl) are loaded exclusively from the Skill's bundled vendor/
directory without relying on system site-packages, pip, or network access.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

# Invariant: Never create bytecode (.pyc) files in vendor or skill directories
sys.dont_write_bytecode = True

from .model import Diagnostic, Envelope

# Required packages defined by canonical name -> (top_module, display_name, entrypoint_file)
# No versions are hardcoded here: versions are verified dynamically against manifest.json.
_REQUIRED_PACKAGES = {
    "pyyaml": ("yaml", "PyYAML", "yaml/__init__.py"),
    "markdown-it-py": ("markdown_it", "markdown-it-py", "markdown_it/__init__.py"),
    "mdit-py-plugins": ("mdit_py_plugins", "mdit-py-plugins", "mdit_py_plugins/__init__.py"),
    "mdurl": ("mdurl", "mdurl", "mdurl/__init__.py"),
}

_WATCHED_TOPLEVELS = ("yaml", "_yaml", "markdown_it", "mdit_py_plugins", "mdurl")

_INITIALIZED = False


def get_vendor_dir() -> Path:
    """Locate the vendor directory relative to this source file, independent of cwd."""
    return Path(__file__).resolve().parent.parent.parent / "vendor"


def _make_error_envelope(
    code: str,
    message: str,
    target: str | None = None,
    command: str = "cli",
    root: str | None = None,
) -> Envelope:
    return Envelope(
        command=command,
        status="failed",
        root=root,
        data=None,
        diagnostics=[
            Diagnostic(
                code=code,
                severity="error",
                file=None,
                span=None,
                target=target,
                message=message,
            )
        ],
    )


def _check_manifest_structure(manifest_data: Any) -> tuple[bool, str | None, dict[str, dict[str, Any]]]:
    """Validate manifest JSON structure and package fields.

    Returns:
        (True, None, packages_dict) on success.
        (False, error_message, {}) on failure.
    """
    if not isinstance(manifest_data, dict):
        return False, "top-level must be a JSON object", {}

    if manifest_data.get("schema_version") != 1:
        return False, f"unsupported schema_version: {manifest_data.get('schema_version')}", {}

    packages_list = manifest_data.get("packages")
    if not isinstance(packages_list, list) or len(packages_list) == 0:
        return False, "'packages' must be a non-empty list", {}

    manifest_packages: dict[str, dict[str, Any]] = {}
    for idx, p in enumerate(packages_list):
        if not isinstance(p, dict):
            return False, f"package entry #{idx} is not a JSON object", {}
        for f in ("canonical_name", "version", "artifact_filename", "artifact_sha256"):
            val = p.get(f)
            if not isinstance(val, str) or not val.strip():
                return False, f"package entry #{idx} missing or invalid string field '{f}'", {}
        roots = p.get("import_roots")
        if not isinstance(roots, list) or len(roots) == 0 or not all(isinstance(r, str) and r.strip() for r in roots):
            return False, f"package entry #{idx} missing or invalid 'import_roots'", {}
        mapping = p.get("extraction_mapping")
        if not isinstance(mapping, dict) or len(mapping) == 0:
            return False, f"package entry #{idx} missing or invalid 'extraction_mapping'", {}
        cname = str(p["canonical_name"]).lower()
        if cname in manifest_packages:
            return False, f"duplicate package entry: {cname}", {}
        manifest_packages[cname] = p

    return True, None, manifest_packages


def ensure_runtime_dependencies(command: str = "cli", root: str | None = None) -> tuple[bool, Envelope | None]:
    """Verify and initialize bundled dependencies for the CLI.

    Returns:
        (True, None) on success.
        (False, Envelope) on failure (with diagnostic code DEPENDENCY_MISSING,
        DEPENDENCY_INVALID, or DEPENDENCY_CONFLICT). Exit code should be 3.
    """
    global _INITIALIZED

    sys.dont_write_bytecode = True

    if _INITIALIZED:
        return True, None

    vendor_dir = get_vendor_dir()
    vendor_resolved = vendor_dir.resolve()

    # 1. Vendor directory and manifest existence
    if not vendor_dir.is_dir():
        msg = (
            f"Bundled vendor directory not found at '{vendor_dir}' (interpreter: {sys.executable}). "
            "Please re-download or reinstall the complete Skill distribution package."
        )
        return False, _make_error_envelope("DEPENDENCY_MISSING", msg, "vendor", command, root)

    manifest_path = vendor_dir / "manifest.json"
    if not manifest_path.is_file():
        msg = (
            f"Bundled vendor manifest missing at '{manifest_path}'. "
            "Please re-download or reinstall the complete Skill distribution package."
        )
        return False, _make_error_envelope("DEPENDENCY_MISSING", msg, "manifest", command, root)

    # 2. Read and parse manifest with strict structural validation
    try:
        manifest_data = json.loads(manifest_path.read_bytes().decode("utf-8"))
    except Exception as e:
        msg = f"Bundled vendor manifest at '{manifest_path}' is corrupted: {e}"
        return False, _make_error_envelope("DEPENDENCY_INVALID", msg, "manifest", command, root)

    valid, err_msg, manifest_packages = _check_manifest_structure(manifest_data)
    if not valid:
        msg = f"Bundled vendor manifest at '{manifest_path}' is invalid: {err_msg}"
        return False, _make_error_envelope("DEPENDENCY_INVALID", msg, "manifest", command, root)

    # 3. Verify all required packages exist in manifest and entrypoints exist on disk
    for canon_name, (mod_name, disp_name, entry_rel) in _REQUIRED_PACKAGES.items():
        if canon_name not in manifest_packages:
            msg = f"Package '{disp_name}' is missing from vendor manifest."
            return False, _make_error_envelope("DEPENDENCY_INVALID", msg, disp_name, command, root)

        entry_path = vendor_dir / Path(entry_rel)
        if not entry_path.is_file():
            msg = (
                f"Required entrypoint '{entry_rel}' for '{disp_name}' is missing in vendor directory. "
                "Please re-download or reinstall the complete Skill distribution package."
            )
            return False, _make_error_envelope("DEPENDENCY_MISSING", msg, disp_name, command, root)

    # 4. Check sys.modules for pre-existing modules loaded from outside vendor
    for mod_key, mod in list(sys.modules.items()):
        if mod is None:
            continue
        top_name = mod_key.split(".", 1)[0]
        if top_name in _WATCHED_TOPLEVELS:
            mod_file = getattr(mod, "__file__", None)
            is_conflicting = False
            if mod_file is None:
                # A watched package loaded without __file__ (e.g. C extension / built-in / stub) is conflicting
                is_conflicting = True
            else:
                try:
                    mod_path = Path(mod_file).resolve()
                    if not mod_path.is_relative_to(vendor_resolved):
                        is_conflicting = True
                except Exception:
                    is_conflicting = True

            if is_conflicting:
                msg = (
                    f"Conflicting package '{mod_key}' is already loaded from '{mod_file}', "
                    f"which is outside the bundled vendor directory '{vendor_dir}'. "
                    "Please run the Skill entrypoint in a clean Python process without preloaded external packages."
                )
                return False, _make_error_envelope("DEPENDENCY_CONFLICT", msg, top_name, command, root)

    # 5. Idempotent insertion into sys.path
    vendor_str = str(vendor_dir)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)

    # 6. Import packages and verify runtime invariants
    try:
        import yaml
        import markdown_it
        import mdit_py_plugins
        import mdurl
    except ImportError as ie:
        mod_failed = getattr(ie, "name", "") or str(ie)
        disp_name = mod_failed
        for _, (m, d, _) in _REQUIRED_PACKAGES.items():
            if m == mod_failed.split(".", 1)[0]:
                disp_name = d
                break
        msg = (
            f"Failed to import bundled dependency '{mod_failed}': {ie}. "
            "Please re-download or reinstall the complete Skill distribution package."
        )
        return False, _make_error_envelope("DEPENDENCY_MISSING", msg, disp_name, command, root)

    # Verify modules were loaded from vendor and runtime version matches manifest
    for canon_name, (mod_name, disp_name, _) in _REQUIRED_PACKAGES.items():
        mod = sys.modules.get(mod_name)
        if mod is None:
            msg = f"Required module '{mod_name}' was not loaded."
            return False, _make_error_envelope("DEPENDENCY_MISSING", msg, disp_name, command, root)

        mod_file = getattr(mod, "__file__", None)
        if not mod_file:
            msg = f"Loaded module '{mod_name}' has no __file__ attribute."
            return False, _make_error_envelope("DEPENDENCY_INVALID", msg, mod_name, command, root)
        try:
            if not Path(mod_file).resolve().is_relative_to(vendor_resolved):
                msg = f"Module '{mod_name}' was loaded from '{mod_file}' instead of vendor directory '{vendor_dir}'."
                return False, _make_error_envelope("DEPENDENCY_INVALID", msg, mod_name, command, root)
        except Exception as e:
            msg = f"Could not verify source location for module '{mod_name}': {e}"
            return False, _make_error_envelope("DEPENDENCY_INVALID", msg, mod_name, command, root)

        # Check actual runtime __version__ against manifest declared version
        actual_ver = getattr(mod, "__version__", None)
        expected_ver = str(manifest_packages[canon_name]["version"])
        if actual_ver != expected_ver:
            msg = f"Runtime version mismatch for '{mod_name}': expected {expected_ver}, got {actual_ver}."
            return False, _make_error_envelope("DEPENDENCY_INVALID", msg, mod_name, command, root)

    # Verify PyYAML uses pure-Python SafeLoader without libyaml C extension
    if getattr(yaml, "__with_libyaml__", False):
        msg = "PyYAML loaded with LibYAML C extension, which violates pure-Python portable vendor requirements."
        return False, _make_error_envelope("DEPENDENCY_INVALID", msg, "yaml", command, root)

    _INITIALIZED = True
    return True, None
